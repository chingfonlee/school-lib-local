"""Regression tests for task-holdings-incremental-and-xls-resilience."""

from __future__ import annotations

import io
import json
import math
from pathlib import Path
import shutil
import subprocess

import openpyxl
import pytest
from starlette.testclient import TestClient

from app import database as db
from app.auth import require_auth
from app.main import app
from app.services import import_service, match_service, selection_service


STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "static"


def _setup_migrated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_file = tmp_path / "holdings_resilience_test.db"
    monkeypatch.setattr(db, "get_db_path", lambda: str(db_file))
    db.run_migrations()
    with db.db_session() as conn:
        conn.execute(
            "INSERT INTO users(id, username, password_hash, display_name, created_at, updated_at) "
            "VALUES (1, 'admin', 'x', '管理員', '', '')"
        )
        conn.commit()
    return db_file


def _create_project(name: str = "115年度本土採購", project_type: str = "local_culture") -> int:
    with db.db_session() as conn:
        cur = conn.execute(
            "INSERT INTO procurement_projects(name, project_type, created_at, updated_at) VALUES (?, ?, '', '')",
            (name, project_type),
        )
        conn.commit()
        return int(cur.lastrowid)


def _make_xlsx(headers: list[str], rows: list[list], sheet_name: str = "Sheet1") -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _make_client() -> TestClient:
    app.dependency_overrides[require_auth] = lambda: 1
    return TestClient(app, raise_server_exceptions=True)


# ── 1. Holdings dual-mode import (replace / append) ──────────────────────────


def test_holdings_replace_and_append_dedup_and_match_rerun(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_migrated_db(tmp_path, monkeypatch)
    _create_project("測試專案")

    # Seed vendor catalog with two books
    vendor_xlsx = _make_xlsx(
        ["書名", "作者", "出版社", "條碼", "定價", "單價"],
        [
            ["台灣生態圖鑑", "王小明", "遠流", "9789573280001", "350", "280"],
            ["海洋探險記", "陳大華", "小天下", "9789573280002", "400", "320"],
        ],
    )
    import_service.import_vendor_books(vendor_xlsx, "vendor.xlsx", user_id=1, vendor_name="遠流")

    # Initial replace import (with 1 book having library_record_id and 1 without)
    h1_xlsx = _make_xlsx(
        ["書目識別號", "ISBN", "書名", "作者", "出版社", "定價"],
        [
            ["B001", "9789573280001", "台灣生態圖鑑", "王小明", "遠流", "350"],
            ["", "9789573280003", "老書一本", "林老師", "聯經", "300"],
        ],
    )
    res1 = import_service.import_library_holdings(h1_xlsx, "h1.xlsx", user_id=1)
    assert res1["import_mode"] == "replace"
    assert res1["replaced"] is True
    assert res1["record_count"] == 2
    assert res1["skipped_duplicate_count"] == 0
    assert res1["match_rerun"] is True

    # Append import:
    # - duplicate by (isbn, library_record_id) -> skipped
    # - second copy with different library_record_id -> inserted
    # - duplicate without library_record_id by (isbn, normalized_title) -> skipped
    # - brand new book (matching vendor book #2) + same-file duplicate -> inserted once, skipped once
    h2_xlsx = _make_xlsx(
        ["書目識別號", "ISBN", "書名", "作者", "出版社", "定價"],
        [
            ["B001", "9789573280001", "台灣生態圖鑑", "王小明", "遠流", "350"],
            ["B002", "9789573280001", "台灣生態圖鑑", "王小明", "遠流", "350"],
            ["", "9789573280003", "老書一本（精裝版）", "林老師", "聯經", "300"],
            ["B003", "9789573280002", "海洋探險記", "陳大華", "小天下", "400"],
            ["B003", "9789573280002", "海洋探險記", "陳大華", "小天下", "400"],
        ],
    )
    res2 = import_service.import_library_holdings(h2_xlsx, "h2.xlsx", user_id=1, import_mode="append")
    assert res2["import_mode"] == "append"
    assert res2["replaced"] is False
    assert res2["record_count"] == 2
    assert res2["skipped_duplicate_count"] == 3
    assert res2["batch_id"] is not None
    assert res2["match_rerun"] is True
    assert res2["match_stats"]["already_owned"] == 2
    assert res2["match_stats"]["available"] == 0

    with db.db_session() as conn:
        total_holdings = conn.execute("SELECT COUNT(*) FROM library_holdings").fetchone()[0]
        batches_cnt = conn.execute(
            "SELECT COUNT(*) FROM import_batches WHERE batch_type = 'library_holdings'"
        ).fetchone()[0]
    assert total_holdings == 4
    assert batches_cnt == 2

    # Re-append exact same h2 -> all duplicates, friendly response, no empty batch
    res3 = import_service.import_library_holdings(h2_xlsx, "h2_again.xlsx", user_id=1, import_mode="append")
    assert res3["batch_id"] is None
    assert res3["record_count"] == 0
    assert res3["skipped_duplicate_count"] == 5
    assert res3["match_rerun"] is False

    with db.db_session() as conn:
        batches_cnt_after = conn.execute(
            "SELECT COUNT(*) FROM import_batches WHERE batch_type = 'library_holdings'"
        ).fetchone()[0]
    assert batches_cnt_after == 2


def test_holdings_api_import_mode_validation_and_append(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_migrated_db(tmp_path, monkeypatch)
    client = _make_client()
    try:
        h_xlsx = _make_xlsx(["ISBN", "書名"], [["9789573280001", "測試書A"]])
        bad = client.post(
            "/api/imports/holdings",
            files={"file": ("h.xlsx", h_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"import_mode": "invalid_mode"},
        )
        assert bad.status_code == 400

        ok1 = client.post(
            "/api/imports/holdings",
            files={"file": ("h.xlsx", h_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert ok1.status_code == 200
        assert ok1.json()["import_mode"] == "replace"
        assert ok1.json()["record_count"] == 1

        h2_xlsx = _make_xlsx(["ISBN", "書名"], [["9789573280001", "測試書A"], ["9789573280002", "測試書B"]])
        ok2 = client.post(
            "/api/imports/holdings",
            files={"file": ("h2.xlsx", h2_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"import_mode": "append"},
        )
        assert ok2.status_code == 200
        body = ok2.json()
        assert body["import_mode"] == "append"
        assert body["replaced"] is False
        assert body["record_count"] == 1
        assert body["skipped_duplicate_count"] == 1
    finally:
        app.dependency_overrides.clear()


# ── 2. Commit project selections to holdings ─────────────────────────────────


def test_commit_project_selections_to_holdings_end_to_end_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_migrated_db(tmp_path, monkeypatch)
    pid = _create_project("115本土閱讀補助")

    vendor_xlsx = _make_xlsx(
        ["書名", "作者", "出版社", "條碼", "出版日期", "定價", "單價"],
        [
            ["原書名A", "原作者A", "原社A", "978-957-328-001-8", "2024/05", "380", "300"],
            ["原書名B", "原作者B", "原社B", "9789573280025", "2023", "420", ""],
        ],
    )
    import_service.import_vendor_books(vendor_xlsx, "v.xlsx", project_id=pid, user_id=1, vendor_name="遠流")

    with db.db_session() as conn:
        vb_rows = conn.execute("SELECT id FROM vendor_books ORDER BY id ASC").fetchall()
        vb1, vb2 = int(vb_rows[0]["id"]), int(vb_rows[1]["id"])

    selection_service.upsert_selection(pid, vb1, 2, "備註", user_id=1)
    selection_service.upsert_selection(pid, vb2, 1, None, user_id=1)

    # Apply user_overrides on selection_item 1
    with db.db_session() as conn:
        si1_id = conn.execute(
            "SELECT id FROM selection_items WHERE project_id = ? AND vendor_book_id = ?",
            (pid, vb1),
        ).fetchone()[0]
    selection_service.update_selection_overrides(
        si1_id,
        {
            "title": "修正書名A",
            "author": "修正作者A",
            "publisher": "修正社A",
            "purchase_price": 275,
        },
        user_id=1,
    )

    client = _make_client()
    try:
        resp = client.post("/api/exports/commit-to-holdings", json={"project_id": pid})
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == pid
        assert data["project_name"] == "115本土閱讀補助"
        assert data["inserted_count"] == 2
        assert data["skipped_count"] == 0
        assert data["batch_id"] is not None
        assert data["match_rerun"] is True
        assert data["match_stats"]["already_owned"] == 2

        with db.db_session() as conn:
            batch = conn.execute(
                "SELECT project_id, batch_type, original_filename, record_count FROM import_batches WHERE id = ?",
                (data["batch_id"],),
            ).fetchone()
            assert batch["project_id"] is None
            assert batch["batch_type"] == "library_holdings"
            assert batch["original_filename"] == "採購回流：115本土閱讀補助"
            assert batch["record_count"] == 2

            h1 = conn.execute(
                "SELECT title, author, publisher, isbn_normalized, publish_year, price, library_record_id "
                "FROM library_holdings WHERE library_record_id = ?",
                (f"PO-{pid}-{si1_id}",),
            ).fetchone()
            assert h1["title"] == "修正書名A"
            assert h1["author"] == "修正作者A"
            assert h1["publisher"] == "修正社A"
            assert h1["isbn_normalized"] == "9789573280018"
            assert h1["publish_year"] == "2024/05"
            assert h1["price"] == 275.0

            # Book 2 fell back to list_price when purchase_price is empty
            h2 = conn.execute("SELECT price FROM library_holdings WHERE isbn_normalized = '9789573280025'").fetchone()
            assert h2["price"] == 420.0

        # Idempotent second call
        resp2 = client.post("/api/exports/commit-to-holdings", json={"project_id": pid})
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["inserted_count"] == 0
        assert data2["skipped_count"] == 2
        assert data2["batch_id"] is None
        assert data2["match_rerun"] is False

        # Empty project -> 400
        empty_pid = _create_project("空白專案")
        resp_empty = client.post("/api/exports/commit-to-holdings", json={"project_id": empty_pid})
        assert resp_empty.status_code == 400

        # Missing project -> 404
        resp_404 = client.post("/api/exports/commit-to-holdings", json={"project_id": 999999})
        assert resp_404.status_code == 404
    finally:
        app.dependency_overrides.clear()


# ── 3. HTML-disguised .xls parsing (UTF-8 & Big5/CP950, multi-table, colspan) ─


def test_html_disguised_xls_utf8_and_cp950_across_import_flows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_migrated_db(tmp_path, monkeypatch)
    pid = _create_project("HTML測試案")

    html_vendor = """<!DOCTYPE html>
<html><head><meta charset="big5"></head><body>
<table>
  <tr><td colspan="5">115學年度書商推薦書單</td></tr>
  <tr><th>書名</th><th>作者</th><th>出版社</th><th>ISBN</th><th>定價</th><th>單價</th><th>獲獎項目</th></tr>
  <tr>
    <td>台灣山林故事</td><td>林小花</td><td>遠流</td>
    <td>978-957-328-100-8</td><td>NT$ 380元</td><td>NTD 300</td><td>金鼎獎</td>
  </tr>
  <tr>
    <td>繪本小旅行</td><td>陳阿明</td><td>信誼</td>
    <td>9789573281015</td><td>$450</td><td>360元整</td><td>好書大家讀</td>
  </tr>
</table>
</body></html>
""".encode("cp950")

    assert import_service._detect_file_engine(html_vendor, "vendor_list.xls") == "html"
    # Real xlsx must not be classified as html
    real_xlsx = _make_xlsx(["書名"], [["測試"]])
    assert import_service._detect_file_engine(real_xlsx, "fake.xls") == "openpyxl"
    assert import_service._detect_file_engine(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1<html>", "ole.xls") == "xlrd"

    # preview_excel
    prev = import_service.preview_excel(html_vendor, "vendor_list.xls")
    assert prev["sheets"] == ["Table 1"]
    assert prev["guessed_header_row"] == 1
    assert "書名" in prev["source_columns"]
    assert prev["suggested_mappings"]["isbn"] == "ISBN"

    # preview_award_groups
    groups = import_service.preview_award_groups(
        html_vendor,
        "vendor_list.xls",
        sheet_name="Table 1",
        header_row=1,
        mappings=prev["suggested_mappings"],
        project_type="general_books",
    )
    assert len(groups) == 2

    # confirm_import
    confirmed = import_service.confirm_import(
        html_vendor,
        "vendor_list.xls",
        project_id=pid,
        sheet_name="Table 1",
        header_row=1,
        mappings=prev["suggested_mappings"],
        user_id=1,
        vendor_name="遠流",
    )
    assert confirmed["record_count"] == 2

    # Check currency-parsed prices in DB
    with db.db_session() as conn:
        prices = {
            r["title"]: (r["list_price"], r["purchase_price"])
            for r in conn.execute("SELECT title, list_price, purchase_price FROM vendor_books").fetchall()
        }
    assert prices["台灣山林故事"] == (380.0, 300.0)
    assert prices["繪本小旅行"] == (450.0, 360.0)

    # import_vendor_books (legacy single-step)
    legacy = import_service.import_vendor_books(
        html_vendor, "vendor_legacy.xls", project_id=pid, user_id=1, vendor_name="另一家書商"
    )
    assert legacy["record_count"] == 2

    # Multi-table UTF-8 HTML-disguised .xls for library_holdings
    html_holdings = """<html><body>
<table>
  <tr><th colspan="2">統計摘要</th></tr>
  <tr><td>總計</td><td>2</td></tr>
</table>
<table>
  <tr><th>B04</th><th>B02</th><th>B03</th><th>B07</th><th>B16</th></tr>
  <tr><td>H001</td><td>9789573281008</td><td>台灣山林故事</td><td>林小花</td><td>新台幣 380 元</td></tr>
  <tr><td>H002</td><td></td><td>無條碼老館藏</td><td>張老師</td><td>＄250</td></tr>
</table>
</body></html>
""".encode("utf-8-sig")

    h_res = import_service.import_library_holdings(html_holdings, "holdings_export.xls", user_id=1)
    assert h_res["record_count"] == 2
    assert len(h_res["skipped_sheets"]) == 1
    assert len(h_res["sheet_summaries"]) == 1
    assert h_res["sheet_summaries"][0]["sheet_name"] == "Table 2"


# ── 4. _to_float currency tolerance ──────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("NT$350", 350.0),
        ("nt$ 1,200", 1200.0),
        ("NTD 1,200", 1200.0),
        ("TW$ 480.5", 480.5),
        ("$480", 480.0),
        ("＄1，200", 1200.0),
        ("350元", 350.0),
        ("新台幣 1,200 元整", 1200.0),
        ("新臺幣350元", 350.0),
        ("\u3000350 元", 350.0),
        (420, 420.0),
        (None, None),
        ("", None),
        ("NT$", None),
        ("abc", None),
        ("nan", None),
        ("inf", None),
        (float("nan"), None),
        (float("inf"), None),
    ],
)
def test_to_float_currency_formats_and_boundaries(raw, expected) -> None:
    got = import_service._to_float(raw)
    if expected is None:
        assert got is None
    else:
        assert got is not None and math.isclose(got, expected)


# ── 5. Weak matching for missing/invalid ISBN & no-ISBN old holdings ─────────


def test_weak_matching_for_no_isbn_holdings_and_missing_invalid_vendor_books(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_migrated_db(tmp_path, monkeypatch)
    pid = _create_project("弱比對測試")

    # Holdings:
    # 1. Old holding WITHOUT ISBN ("古老傳說", author "王小明")
    # 2. Normal holding WITH ISBN ("快樂森林", author "陳大華")
    # 3. Normal holding WITH ISBN ("同名異作者", author "張三")
    h_xlsx = _make_xlsx(
        ["ISBN", "書名", "作者", "出版社"],
        [
            ["", "古老傳說", "王小明", "老社"],
            ["9789573282005", "快樂森林", "陳大華", "大社"],
            ["9789573282012", "同名異作者", "張三", "甲社"],
        ],
    )
    import_service.import_library_holdings(h_xlsx, "h.xlsx", user_id=1)

    # Vendor books:
    # 1. Valid ISBN book matching old no-ISBN holding by title -> available + similar_holding
    # 2. Missing ISBN book matching "快樂森林" with compatible author "陳大華著" -> missing_isbn + similar_holding
    # 3. Invalid ISBN book matching "古老傳說" with empty author -> invalid_isbn + similar_holding
    # 4. Missing ISBN book matching "同名異作者" with DIFFERENT author "李四" -> missing_isbn, NO similar_holding
    v_xlsx = _make_xlsx(
        ["書名", "作者", "出版社", "條碼", "定價"],
        [
            ["古老傳說（修訂版）", "王小明", "新社", "9789573282098", "300"],
            ["快樂森林", "陳大華著", "大社", "", "320"],
            ["古老傳說", "", "老社", "12345-BAD", "280"],
            ["同名異作者", "李四", "乙社", "", "350"],
        ],
    )
    import_service.import_vendor_books(v_xlsx, "v.xlsx", project_id=pid, user_id=1, vendor_name="測試書商")

    stats = match_service.run_match()
    assert stats["available"] == 1
    assert stats["missing_isbn"] == 2
    assert stats["invalid_isbn"] == 1
    assert stats["same_title_different_isbn"] == 3

    client = _make_client()
    try:
        # Default GET /api/books/matches returns only valid ISBN books (backward compatible)
        default_resp = client.get(f"/api/books/matches?project_id={pid}")
        assert default_resp.status_code == 200
        default_items = default_resp.json()
        assert len(default_items) == 1
        assert default_items[0]["title"] == "古老傳說（修訂版）"
        assert default_items[0]["similar_holding"] is not None
        assert default_items[0]["similar_holding"]["title"] == "古老傳說"

        # Query match_status=missing_isbn
        missing_resp = client.get(f"/api/books/matches?project_id={pid}&match_status=missing_isbn")
        assert missing_resp.status_code == 200
        missing_by_title = {item["title"]: item for item in missing_resp.json()}
        assert set(missing_by_title.keys()) == {"快樂森林", "同名異作者"}
        assert missing_by_title["快樂森林"]["similar_holding"] is not None
        assert missing_by_title["快樂森林"]["similar_holding"]["title"] == "快樂森林"
        assert missing_by_title["同名異作者"]["similar_holding"] is None

        # Query match_status=invalid_isbn
        invalid_resp = client.get(f"/api/books/matches?project_id={pid}&match_status=invalid_isbn")
        assert invalid_resp.status_code == 200
        invalid_items = invalid_resp.json()
        assert len(invalid_items) == 1
        assert invalid_items[0]["title"] == "古老傳說"
        assert invalid_items[0]["similar_holding"] is not None

        # Query include_missing_isbn=true returns all 4
        all_resp = client.get(f"/api/books/matches?project_id={pid}&include_missing_isbn=true")
        assert all_resp.status_code == 200
        assert len(all_resp.json()) == 4

        # Stats endpoint keeps existing semantics and adds missing_isbn_similar_count
        stats_resp = client.get(f"/api/books/stats?project_id={pid}")
        assert stats_resp.status_code == 200
        s = stats_resp.json()
        assert s["total_vendor_books"] == 1
        assert s["ignored_missing_isbn"] == 2
        assert s["ignored_invalid_isbn"] == 1
        assert s["same_title_different_isbn_count"] == 1
        assert s["missing_isbn_similar_count"] == 2
    finally:
        app.dependency_overrides.clear()


# ── 6. Frontend markers & applyRecommendedProfile normalized matching ────────


def test_frontend_ui_markers_and_normalized_profile_apply() -> None:
    import_html = (STATIC_DIR / "import.html").read_text(encoding="utf-8")
    export_html = (STATIC_DIR / "export.html").read_text(encoding="utf-8")
    match_html = (STATIC_DIR / "match.html").read_text(encoding="utf-8")

    assert 'id="holdings-import-mode"' in import_html
    assert 'value="append"' in import_html
    assert "fd.append('import_mode', importMode)" in import_html

    assert 'id="commit-holdings-btn"' in export_html
    assert 'id="commit-holdings-result"' in export_html
    assert "/api/exports/commit-to-holdings" in export_html

    assert 'value="missing_isbn"' in match_html
    assert 'value="invalid_isbn"' in match_html

    # Verify applyRecommendedProfile matches headers ignoring whitespace and case
    node = shutil.which("node")
    assert node is not None
    start = import_html.index("function normalizeHeader(")
    end = import_html.index("function renderMappingTable(")
    fn_block = import_html[start:end]
    harness = f"""
let savedMappings = null;
let savedExtraFields = null;
let toastMsg = '';
let previewData = {{
  source_columns: ['  Title ', 'isbn 條碼', '備 註'],
  recommended_profile: {{
    name: '遠流範本',
    mappings: {{ title: 'title', isbn: 'ISBN條碼' }},
    extra_field_settings: ['備註'],
  }},
}};
function renderMappingTable() {{}}
function showToast(m) {{ toastMsg = m; }}
{fn_block}
applyRecommendedProfile();
console.log(JSON.stringify({{ savedMappings, savedExtraFields, toastMsg }}));
"""
    proc = subprocess.run(
        [node, "-e", harness],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    out = json.loads(proc.stdout.strip())
    assert out["savedMappings"] == {"title": "  Title ", "isbn": "isbn 條碼"}
    assert out["savedExtraFields"] == ["備 註"]
    assert "遠流範本" in out["toastMsg"]
