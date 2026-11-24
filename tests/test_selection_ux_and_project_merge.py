"""Tests for task-selection-ux-and-project-merge: multi-project merge & selection UX."""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from app.auth import require_auth
from app.main import app
from app.services.selection_service import import_selections_from_projects

STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "static"
COMMON_JS = STATIC_DIR / "js" / "common.js"
SELECTION_HTML = STATIC_DIR / "selection.html"
INLINE_SCRIPT_RE = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE)


class _NoCloseConn:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def close(self) -> None:
        pass

    def __getattr__(self, name: str):
        return getattr(self._conn, name)


_MERGE_SCHEMA = [
    """CREATE TABLE procurement_projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        project_type TEXT NOT NULL DEFAULT 'local_culture',
        budget_amount REAL,
        export_template_type TEXT NOT NULL DEFAULT 'local_culture',
        price_field TEXT NOT NULL DEFAULT 'purchase_price',
        subtotal_mode TEXT NOT NULL DEFAULT 'quantity_times_purchase_price',
        academic_year TEXT,
        funding_source TEXT,
        project_notes TEXT,
        is_archived INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT ''
    )""",
    """CREATE TABLE import_batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER,
        batch_type TEXT NOT NULL DEFAULT 'vendor_books',
        original_filename TEXT NOT NULL DEFAULT '',
        vendor_name TEXT,
        imported_at TEXT NOT NULL DEFAULT ''
    )""",
    """CREATE TABLE vendor_books (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id INTEGER,
        title TEXT,
        isbn TEXT,
        isbn_normalized TEXT
    )""",
    """CREATE TABLE library_holdings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id INTEGER,
        isbn TEXT,
        isbn_normalized TEXT,
        title TEXT
    )""",
    """CREATE TABLE book_matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_book_id INTEGER,
        holding_id INTEGER,
        match_status TEXT NOT NULL DEFAULT 'available',
        matched_at TEXT NOT NULL DEFAULT '',
        batch_run_id TEXT NOT NULL DEFAULT ''
    )""",
    """CREATE TABLE selection_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        vendor_book_id INTEGER,
        source_batch_id INTEGER,
        source_original_filename TEXT,
        source_row_number INTEGER,
        selected_quantity INTEGER NOT NULL DEFAULT 1,
        notes TEXT,
        title TEXT,
        author TEXT,
        publisher TEXT,
        isbn TEXT,
        isbn_normalized TEXT,
        isbn_status TEXT,
        publish_date TEXT,
        list_price REAL,
        purchase_price REAL,
        award_item TEXT,
        vendor_seq TEXT,
        age_range TEXT,
        category TEXT,
        book_type TEXT,
        policy_topic TEXT,
        summary TEXT,
        source_url TEXT,
        recommendation_source TEXT,
        eligibility_label TEXT,
        award_notes TEXT,
        classification_number TEXT,
        completeness_status TEXT,
        match_status_at_selection TEXT,
        holding_id_at_selection INTEGER,
        user_overrides TEXT,
        extra_fields TEXT,
        raw_row TEXT,
        created_by INTEGER,
        created_at TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT ''
    )""",
]


@pytest.fixture
def merge_db(monkeypatch):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    for stmt in _MERGE_SCHEMA:
        conn.execute(stmt)
    conn.execute(
        "INSERT INTO procurement_projects(id, name, project_type) VALUES (1, '正式一般圖書案', 'general_books')"
    )
    conn.execute("INSERT INTO procurement_projects(id, name, project_type) VALUES (2, '班級推薦A', 'custom')")
    conn.execute("INSERT INTO procurement_projects(id, name, project_type) VALUES (3, '班級推薦B', 'custom')")
    conn.execute(
        "INSERT INTO procurement_projects(id, name, project_type) VALUES (4, '正式本土文化案', 'local_culture')"
    )
    conn.commit()

    wrapped = _NoCloseConn(conn)
    monkeypatch.setattr("app.services.selection_service.get_connection", lambda: wrapped)
    yield conn
    conn.close()


def _insert_selection(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    vendor_book_id: int | None,
    title: str,
    isbn_normalized: str | None = None,
    selected_quantity: int = 1,
    author: str = "作者甲",
    publisher: str = "出版社甲",
    purchase_price: float = 250.0,
    award_item: str | None = None,
    eligibility_label: str | None = None,
    recommendation_source: str | None = None,
    user_overrides: dict | None = None,
    completeness_status: str = "export_ready",
) -> None:
    conn.execute(
        "INSERT INTO selection_items("
        "project_id, vendor_book_id, selected_quantity, title, author, publisher, "
        "isbn, isbn_normalized, list_price, purchase_price, award_item, "
        "eligibility_label, recommendation_source, user_overrides, completeness_status, "
        "created_by, created_at, updated_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, '2026-01-01', '2026-01-01')",
        (
            project_id,
            vendor_book_id,
            selected_quantity,
            title,
            author,
            publisher,
            isbn_normalized,
            isbn_normalized,
            300.0,
            purchase_price,
            award_item,
            eligibility_label,
            recommendation_source,
            json.dumps(user_overrides, ensure_ascii=False) if user_overrides else None,
            completeness_status,
        ),
    )


def test_import_selections_basic_overrides_and_recompute_completeness(merge_db: sqlite3.Connection) -> None:
    # Project 2 (custom): 1 book missing general_books required fields, 1 book with overrides supplying them
    _insert_selection(
        merge_db,
        project_id=2,
        vendor_book_id=101,
        title="未補推薦來源的書",
        isbn_normalized="9789860000001",
        selected_quantity=3,  # should be reset to 1
    )
    _insert_selection(
        merge_db,
        project_id=2,
        vendor_book_id=None,  # cleared source catalog snapshot
        title="已清除來源但有覆寫的書",
        isbn_normalized="9789860000002",
        selected_quantity=2,
        user_overrides={
            "eligibility_label": "必選",
            "recommendation_source": "喜閱網",
            "title": "覆寫後書名",
        },
    )
    merge_db.commit()

    res = import_selections_from_projects(1, [2], user_id=9, skip_already_owned=True)
    assert res == {"added": 2, "skipped_duplicate": 0, "skipped_owned": 0}

    rows = merge_db.execute("SELECT * FROM selection_items WHERE project_id = 1 ORDER BY id").fetchall()
    assert len(rows) == 2

    # First book: quantity forced to 1, completeness recomputed for general_books -> missing_required
    assert rows[0]["vendor_book_id"] == 101
    assert rows[0]["selected_quantity"] == 1
    assert rows[0]["completeness_status"] == "missing_required"
    assert rows[0]["created_by"] == 9

    # Second book: detached snapshot (vendor_book_id is NULL) preserved, overrides preserved -> export_ready
    assert rows[1]["vendor_book_id"] is None
    assert rows[1]["selected_quantity"] == 1
    assert rows[1]["completeness_status"] == "export_ready"
    assert json.loads(rows[1]["user_overrides"])["title"] == "覆寫後書名"


def test_import_selections_dedup_by_vbid_isbn_and_multi_source(merge_db: sqlite3.Connection) -> None:
    # Target project 4 already has vbid=10 and isbn=9789860000011
    _insert_selection(merge_db, project_id=4, vendor_book_id=10, title="既有書1", isbn_normalized="9789860000010")
    _insert_selection(merge_db, project_id=4, vendor_book_id=11, title="既有書2", isbn_normalized="9789860000011")

    # Source project 2:
    # - vbid=10 (dup by vbid)
    # - vbid=21 with isbn=9789860000011 (dup by isbn across vendors)
    # - vbid=22 with isbn=9789860000022 (new)
    _insert_selection(merge_db, project_id=2, vendor_book_id=10, title="既有書1", isbn_normalized="9789860000010")
    _insert_selection(merge_db, project_id=2, vendor_book_id=21, title="異書商同ISBN", isbn_normalized="9789860000011")
    _insert_selection(
        merge_db,
        project_id=2,
        vendor_book_id=22,
        title="多來源共有新書",
        isbn_normalized="9789860000022",
        award_item="好書大家讀",
    )

    # Source project 3:
    # - vbid=32 with same isbn 9789860000022 (dup against project 2 added in same run)
    # - vbid=33 unique new book without award_item (local_culture -> needs_review)
    _insert_selection(
        merge_db, project_id=3, vendor_book_id=32, title="多來源共有新書B", isbn_normalized="9789860000022"
    )
    _insert_selection(merge_db, project_id=3, vendor_book_id=33, title="獨立新書", isbn_normalized="9789860000033")
    merge_db.commit()

    # Include target id (4) and duplicate source id (2) to verify cleanup
    res = import_selections_from_projects(4, [4, 2, 2, 3], user_id=1, skip_already_owned=True)
    assert res == {"added": 2, "skipped_duplicate": 3, "skipped_owned": 0}

    added_rows = merge_db.execute(
        "SELECT vendor_book_id, completeness_status FROM selection_items "
        "WHERE project_id = 4 AND vendor_book_id IN (22, 33) ORDER BY vendor_book_id"
    ).fetchall()
    assert [(r["vendor_book_id"], r["completeness_status"]) for r in added_rows] == [
        (22, "export_ready"),
        (33, "needs_review"),
    ]


def test_import_selections_skip_already_owned_flag(merge_db: sqlite3.Connection) -> None:
    # Book 50: matched as already_owned in book_matches
    merge_db.execute(
        "INSERT INTO book_matches(vendor_book_id, holding_id, match_status) VALUES (50, 1, 'already_owned')"
    )
    # Book 51: latest non-similar match is available, even though a same_title_different_isbn exists
    merge_db.execute(
        "INSERT INTO book_matches(vendor_book_id, holding_id, match_status) VALUES (51, NULL, 'available')"
    )
    merge_db.execute(
        "INSERT INTO book_matches(vendor_book_id, holding_id, match_status) VALUES (51, 2, 'same_title_different_isbn')"
    )
    # Holding by ISBN only (book 52 has no book_matches row)
    merge_db.execute(
        "INSERT INTO library_holdings(batch_id, isbn, isbn_normalized, title) "
        "VALUES (1, '9789860000052', '9789860000052', '已館藏書')"
    )

    _insert_selection(merge_db, project_id=2, vendor_book_id=50, title="館藏比對書", isbn_normalized="9789860000050")
    _insert_selection(merge_db, project_id=2, vendor_book_id=51, title="可買同名書", isbn_normalized="9789860000051")
    _insert_selection(merge_db, project_id=2, vendor_book_id=52, title="館藏ISBN書", isbn_normalized="9789860000052")
    merge_db.commit()

    res_skip = import_selections_from_projects(4, [2], user_id=1, skip_already_owned=True)
    assert res_skip == {"added": 1, "skipped_duplicate": 0, "skipped_owned": 2}

    # With skip_already_owned=False, the 2 previously skipped owned books can be imported; book 51 is now duplicate
    res_allow = import_selections_from_projects(4, [2], user_id=1, skip_already_owned=False)
    assert res_allow == {"added": 2, "skipped_duplicate": 1, "skipped_owned": 0}


def test_import_selections_missing_target_project_raises(merge_db: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="不存在"):
        import_selections_from_projects(999, [2], user_id=1)


def test_import_from_projects_api_endpoint(merge_db: sqlite3.Connection) -> None:
    _insert_selection(merge_db, project_id=2, vendor_book_id=77, title="推薦好書", isbn_normalized="9789860000077")
    merge_db.commit()

    app.dependency_overrides[require_auth] = lambda: 1
    try:
        client = TestClient(app, raise_server_exceptions=True)

        resp_ok = client.post(
            "/api/selections/import-from-projects",
            json={"target_project_id": 4, "source_project_ids": [2], "skip_already_owned": True},
        )
        assert resp_ok.status_code == 200
        assert resp_ok.json() == {"added": 1, "skipped_duplicate": 0, "skipped_owned": 0}

        resp_404 = client.post(
            "/api/selections/import-from-projects",
            json={"target_project_id": 999, "source_project_ids": [2]},
        )
        assert resp_404.status_code == 404

        resp_422 = client.post(
            "/api/selections/import-from-projects",
            json={"target_project_id": 4, "source_project_ids": []},
        )
        assert resp_422.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_selection_html_parse_publish_date_and_helpers_runtime() -> None:
    node = shutil.which("node")
    assert node is not None, "node is required to verify selection.html JS helpers"

    html = SELECTION_HTML.read_text(encoding="utf-8")
    scripts = INLINE_SCRIPT_RE.findall(html)
    assert scripts, "Expected inline script in selection.html"
    inline_js = scripts[-1]
    common_js = COMMON_JS.read_text(encoding="utf-8")

    # Stub browser globals so the inline script can be evaluated safely in Node
    harness = f"""
global.localStorage = {{ getItem() {{ return null; }}, setItem() {{}}, removeItem() {{}} }};
global.sessionStorage = {{ getItem() {{ return null; }}, setItem() {{}}, removeItem() {{}} }};
global.window = {{ location: {{ pathname: '/selection.html', href: '' }}, scrollTo() {{}} }};
global.document = {{
  getElementById() {{ return null; }},
  querySelector() {{ return null; }},
  querySelectorAll() {{ return []; }},
  addEventListener() {{}},
}};
{common_js}
// Prevent requireAuth() from calling fetch during unit test
requireAuth = () => ({{ then() {{}} }});
{inline_js}

const samples = [
  ['2025/05/01', 20250501],
  ['2025-05-01', 20250501],
  ['2025.5.9', 20250509],
  ['2025/05', 20250501],
  ['2025-05', 20250501],
  ['2025年5月1日', 20250501],
  ['2025年05月', 20250501],
  ['2025年', 20250101],
  ['2025', 20250101],
  ['114/05/01', 20250501],
  ['114/05', 20250501],
  ['114年', 20250101],
  ['114', 20250101],
  ['民國114年5月', 20250501],
  ['', null],
  [null, null],
  ['abc', null],
  ['12345', null],
  ['99', null],
  ['9999', null],
  ['2025/13/01', null],
];
const parsed = samples.map(([raw, expected]) => ({{
  raw,
  expected,
  actual: parsePublishSortKey(raw),
}}));

const books = [
  {{ id: 1, publish_date: '' }},
  {{ id: 2, publish_date: '2022/03/01' }},
  {{ id: 3, publish_date: '114/05' }},
  {{ id: 4, publish_date: 'invalid' }},
  {{ id: 5, publish_date: '2025/05/01' }},
];
const descIds = [...books].sort((a, b) => compareBooks(a, b, 'pub_desc')).map(b => b.id);
const ascIds = [...books].sort((a, b) => compareBooks(a, b, 'pub_asc')).map(b => b.id);

const awards = {{
  officialRec: hasOfficialAward({{ recommendation_source: '喜閱網' }}),
  selfRec: hasOfficialAward({{ recommendation_source: '學校自選(請備註原因)' }}),
  officialAward: hasOfficialAward({{ award_item: '金鼎獎' }}),
  selfAward: hasOfficialAward({{ award_item: '自選' }}),
  overrideAward: hasOfficialAward({{ award_item: '', user_overrides: JSON.stringify({{ award_item: '好書大家讀' }}) }}),
  none: hasOfficialAward({{}}),
}};

console.log(JSON.stringify({{ parsed, descIds, ascIds, awards }}));
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as tmp:
        tmp.write(harness)
        tmp_path = Path(tmp.name)
    try:
        proc = subprocess.run(
            [node, str(tmp_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert proc.returncode == 0, f"Node harness failed:\n{proc.stderr}"
    finally:
        tmp_path.unlink(missing_ok=True)
    out = json.loads(proc.stdout.strip())
    for item in out["parsed"]:
        assert item["actual"] == item["expected"], f"parsePublishSortKey({item['raw']!r}) != {item['expected']}"

    # 114/05 (id=3) and 2025/05/01 (id=5) both resolve to 20250501 -> tie-break by id (3 before 5)
    # Empty (id=1) and invalid (id=4) always sink to the bottom in both desc and asc
    assert out["descIds"] == [3, 5, 2, 1, 4]
    assert out["ascIds"] == [2, 3, 5, 1, 4]

    assert out["awards"] == {
        "officialRec": True,
        "selfRec": False,
        "officialAward": True,
        "selfAward": False,
        "overrideAward": True,
        "none": False,
    }


def test_selection_html_ux_elements_and_lock_rules() -> None:
    html = SELECTION_HTML.read_text(encoding="utf-8")

    # Selection lock rule
    assert "function removeBook(" not in html
    assert "✓ 已加入（${qty}本）" in html
    assert 'id="cta-${b.id}" disabled' in html
    assert "如需調整數量或移除請至「5 匯出前檢查」" in html

    # Pub year sort & filter
    assert 'value="pub_desc"' in html
    assert 'value="pub_asc"' in html
    assert 'id="filter-pub-year"' in html

    # Preset chips & selected-only banner
    assert 'id="preset-new-books"' in html
    assert 'id="preset-award-books"' in html
    assert 'id="preset-unselected"' in html
    assert 'id="preset-selected"' in html
    assert 'id="selected-only-banner"' in html

    # View toggle & compact list
    assert 'id="btn-view-cards"' in html
    assert 'id="btn-view-list"' in html
    assert "function renderListView(" in html
    assert "selection_view_mode" in html

    # Budget progress bar & distribution panel
    assert 'id="budget-progress-wrap"' in html
    assert 'id="budget-progress-fill"' in html
    assert 'id="btn-toggle-dist"' in html
    assert 'id="selection-dist-panel"' in html

    # Import from other projects modal
    assert 'id="btn-import-projects"' in html
    assert 'id="import-projects-modal"' in html
    assert "/api/selections/import-from-projects" in html
