from pathlib import Path
import re
import shutil
import sqlite3
import subprocess

import openpyxl
import pytest
from starlette.testclient import TestClient

from app.auth import require_auth
from app.database import run_migrations
from app.main import app
from app.services.completeness_service import compute as compute_completeness
from app.services.export_service import ExportSettings, export_generic_books
from app.services.validation_service import check_export_readiness

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "migrations"


def _make_migrated_db(tmp_path: Path, monkeypatch) -> Path:
    db_path = tmp_path / "test_diversity.db"

    def _connect() -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    monkeypatch.setattr("app.database.get_db_path", lambda: str(db_path))
    monkeypatch.setattr("app.database.get_connection", _connect)
    monkeypatch.setattr("app.routers.projects.get_connection", _connect)
    monkeypatch.setattr("app.routers.exports.get_connection", _connect)
    monkeypatch.setattr("app.routers.books.get_connection", _connect)
    monkeypatch.setattr("app.services.export_service.get_connection", _connect)
    monkeypatch.setattr("app.services.validation_service.get_connection", _connect)
    run_migrations(MIGRATIONS_DIR)
    return db_path


def _seed_user(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    cur = conn.execute(
        "INSERT INTO users(username, password_hash, display_name, created_at, updated_at) "
        "VALUES ('admin', 'hash', '管理員', '2026-01-01', '2026-01-01')"
    )
    user_id = cur.lastrowid
    conn.commit()
    conn.close()
    return int(user_id)


# ---------------------------------------------------------------------------
# 1. Migration 012: Upgrade & Existing Data Preservation
# ---------------------------------------------------------------------------


def test_migration_012_preserves_existing_data_and_supports_custom(tmp_path):
    db_path = tmp_path / "upgrade_012.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    pre_012 = [f for f in sql_files if not f.name.startswith("012_")]
    mig_012 = next(f for f in sql_files if f.name.startswith("012_"))

    for f in pre_012:
        conn.executescript(f.read_text(encoding="utf-8"))
        conn.execute("PRAGMA foreign_keys = ON")

    conn.execute(
        "INSERT INTO users(id, username, password_hash, display_name, created_at, updated_at) "
        "VALUES (1, 'u1', 'h', 'Admin', '2026-01-01', '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO procurement_projects("
        "id, name, project_type, budget_amount, export_template_type, "
        "price_field, subtotal_mode, created_at, updated_at"
        ") VALUES (42, '舊本土案', 'local_culture', 50000, 'local_culture', "
        "'purchase_price', 'quantity_times_purchase_price', '2026-01-01', '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO selection_items("
        "project_id, selected_quantity, title, created_by, created_at, updated_at"
        ") VALUES (42, 2, '既有選書', 1, '2026-01-02', '2026-01-02')"
    )
    conn.commit()

    conn.executescript(mig_012.read_text(encoding="utf-8"))

    # PRAGMA foreign_keys must be ON after migration
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    # Existing project ID, columns, and child row preserved
    row = conn.execute("SELECT * FROM procurement_projects WHERE id = 42").fetchone()
    assert row is not None
    assert row["name"] == "舊本土案"
    assert row["project_type"] == "local_culture"
    assert row["budget_amount"] == 50000
    assert row["academic_year"] is None
    assert row["funding_source"] is None
    assert row["project_notes"] is None
    assert row["is_archived"] == 0

    sel = conn.execute("SELECT title FROM selection_items WHERE project_id = 42").fetchone()
    assert sel["title"] == "既有選書"

    # Can insert custom project type
    conn.execute(
        "INSERT INTO procurement_projects("
        "name, project_type, export_template_type, academic_year, funding_source, "
        "project_notes, is_archived, created_at, updated_at"
        ") VALUES ('家長會贈書', 'custom', 'generic_builtin', '115學年度', "
        "'家長會', '優先繪本', 0, '2026-02-01', '2026-02-01')"
    )
    conn.commit()

    # Invalid project_type still rejected by CHECK constraint
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO procurement_projects(name, project_type, created_at, updated_at) "
            "VALUES ('非法案', 'invalid_type', '2026-02-01', '2026-02-01')"
        )
    conn.close()


# ---------------------------------------------------------------------------
# 2. Projects API: custom, decoupled template, metadata, archive & dup check
# ---------------------------------------------------------------------------


def test_projects_api_custom_metadata_and_archive(tmp_path, monkeypatch):
    db_path = _make_migrated_db(tmp_path, monkeypatch)
    user_id = _seed_user(db_path)

    app.dependency_overrides[require_auth] = lambda: user_id
    try:
        client = TestClient(app, raise_server_exceptions=True)

        # Create custom project without export_template_type -> defaults to generic_builtin
        r1 = client.post(
            "/api/projects/",
            json={
                "name": "  115 家長會自籌採購  ",
                "project_type": "custom",
                "budget_amount": 30000,
                "academic_year": " 115學年度 ",
                "funding_source": " 家長會補助 ",
                "project_notes": " 繪本單價不超過 500 元 ",
            },
        )
        assert r1.status_code == 200
        data1 = r1.json()
        assert data1["name"] == "115 家長會自籌採購"
        p1_id = data1["id"]

        p1 = client.get(f"/api/projects/{p1_id}").json()
        assert p1["project_type"] == "custom"
        assert p1["export_template_type"] == "generic_builtin"
        assert p1["academic_year"] == "115學年度"
        assert p1["funding_source"] == "家長會補助"
        assert p1["project_notes"] == "繪本單價不超過 500 元"
        assert p1["is_archived"] == 0

        # Backward compatibility: local_culture without export_template_type defaults to local_culture
        r2 = client.post(
            "/api/projects/",
            json={"name": "國小本土案", "project_type": "local_culture"},
        )
        assert r2.status_code == 200
        p2_id = r2.json()["id"]
        p2 = client.get(f"/api/projects/{p2_id}").json()
        assert p2["export_template_type"] == "local_culture"

        # Invalid project_type / export_template_type -> 400
        assert client.post("/api/projects/", json={"name": "壞案", "project_type": "nope"}).status_code == 400
        assert (
            client.post(
                "/api/projects/",
                json={"name": "壞範本", "project_type": "custom", "export_template_type": "nope"},
            ).status_code
            == 400
        )

        # Update: clear optional fields with empty string / null, change template & archive
        u1 = client.put(
            f"/api/projects/{p1_id}",
            json={
                "export_template_type": "local_culture",
                "academic_year": "",
                "funding_source": None,
                "project_notes": "   ",
                "is_archived": True,
            },
        )
        assert u1.status_code == 200
        p1_after = client.get(f"/api/projects/{p1_id}").json()
        assert p1_after["export_template_type"] == "local_culture"
        assert p1_after["academic_year"] is None
        assert p1_after["funding_source"] is None
        assert p1_after["project_notes"] is None
        assert p1_after["is_archived"] == 1

        # List ordering: active projects first, archived projects last
        listed = client.get("/api/projects/").json()
        ids = [p["id"] for p in listed]
        assert ids.index(p2_id) < ids.index(p1_id)
    finally:
        app.dependency_overrides.clear()


def test_archived_project_still_participates_in_cross_project_duplicate_check(tmp_path, monkeypatch):
    db_path = _make_migrated_db(tmp_path, monkeypatch)
    user_id = _seed_user(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO procurement_projects("
        "id, name, project_type, export_template_type, is_archived, created_at, updated_at"
        ") VALUES (1, '已結案封存專案', 'custom', 'generic_builtin', 1, '2026-01-01', '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO procurement_projects("
        "id, name, project_type, export_template_type, is_archived, created_at, updated_at"
        ") VALUES (2, '新學年採購專案', 'custom', 'generic_builtin', 0, '2026-02-01', '2026-02-01')"
    )
    conn.execute(
        "INSERT INTO import_batches("
        "id, project_id, batch_type, original_filename, vendor_name, imported_by, imported_at"
        ") VALUES (10, NULL, 'vendor_books', 'v.xlsx', '測試書商', ?, '2026-01-01')",
        (user_id,),
    )
    conn.execute(
        "INSERT INTO vendor_books("
        "id, batch_id, title, author, publisher, isbn, isbn_normalized, isbn_status, "
        "list_price, purchase_price, completeness_status"
        ") VALUES (100, 10, '台灣小百科', '王小明', '小樹出版', '9789571111117', "
        "'9789571111117', 'valid', 300, 240, 'export_ready')"
    )
    conn.execute(
        "INSERT INTO book_matches(vendor_book_id, holding_id, match_status, matched_at, batch_run_id) "
        "VALUES (100, NULL, 'available', '2026-01-01', 'run1')"
    )
    conn.execute(
        "INSERT INTO selection_items("
        "project_id, vendor_book_id, selected_quantity, title, isbn_normalized, "
        "isbn_status, list_price, purchase_price, created_by, created_at, updated_at"
        ") VALUES (1, 100, 1, '台灣小百科', '9789571111117', 'valid', 300, 240, ?, "
        "'2026-01-02', '2026-01-02')",
        (user_id,),
    )
    conn.commit()
    conn.close()

    app.dependency_overrides[require_auth] = lambda: user_id
    try:
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/api/books/matches?project_id=2")
        assert resp.status_code == 200
        books = resp.json()
        assert len(books) == 1
        assert len(books[0]["other_project_selections"]) == 1
        assert books[0]["other_project_selections"][0]["project_name"] == "已結案封存專案"

        stats = client.get("/api/books/stats?project_id=2")
        assert stats.status_code == 200
        assert stats.json()["other_project_duplicate_count"] == 1
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 3. Completeness & Validation Services for custom vs existing types
# ---------------------------------------------------------------------------


def test_completeness_service_custom_rules():
    # Title + price + author + publisher -> export_ready (no award_item or eligibility needed)
    assert (
        compute_completeness(
            {"title": "繪本A", "purchase_price": 250, "author": "作者A", "publisher": "出版社A"},
            project_type="custom",
        )
        == "export_ready"
    )
    # Missing author or publisher -> needs_review
    assert (
        compute_completeness(
            {"title": "繪本B", "list_price": 300, "author": "", "publisher": "出版社B"},
            project_type="custom",
        )
        == "needs_review"
    )
    # Missing title or both prices -> missing_required
    assert (
        compute_completeness(
            {"title": "繪本C", "author": "作者C", "publisher": "出版社C"},
            project_type="custom",
        )
        == "missing_required"
    )
    assert (
        compute_completeness(
            {"title": "", "purchase_price": 200, "author": "作者C", "publisher": "出版社C"},
            project_type="custom",
        )
        == "missing_required"
    )
    # Existing local_culture still requires award_item for export_ready
    assert (
        compute_completeness(
            {"title": "本土A", "purchase_price": 250, "author": "作者A", "publisher": "出版社A"},
            project_type="local_culture",
        )
        == "needs_review"
    )


def test_validation_service_custom_rules(tmp_path, monkeypatch):
    db_path = _make_migrated_db(tmp_path, monkeypatch)
    user_id = _seed_user(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO procurement_projects("
        "id, name, project_type, export_template_type, created_at, updated_at"
        ") VALUES (1, '通用採購', 'custom', 'generic_builtin', '2026-01-01', '2026-01-01')"
    )
    # Book 1: valid title & price & qty, missing author/publisher & invalid ISBN -> can_export=True, needs_review
    conn.execute(
        "INSERT INTO selection_items("
        "id, project_id, selected_quantity, title, author, publisher, isbn_status, "
        "list_price, purchase_price, match_status_at_selection, created_by, created_at, updated_at"
        ") VALUES (1, 1, 2, '自購繪本', '', '', 'invalid_isbn', 300, 240, 'invalid_isbn', ?, "
        "'2026-01-01', '2026-01-01')",
        (user_id,),
    )
    # Book 2: all fields valid -> export_ready
    conn.execute(
        "INSERT INTO selection_items("
        "id, project_id, selected_quantity, title, author, publisher, isbn_normalized, isbn_status, "
        "list_price, purchase_price, match_status_at_selection, created_by, created_at, updated_at"
        ") VALUES (2, 1, 1, '完整書', '作者', '出版社', '9789571111117', 'valid', 300, 240, 'available', ?, "
        "'2026-01-01', '2026-01-01')",
        (user_id,),
    )
    # Book 3: missing price -> missing_required (can_export=False)
    conn.execute(
        "INSERT INTO selection_items("
        "id, project_id, selected_quantity, title, author, publisher, isbn_normalized, isbn_status, "
        "list_price, purchase_price, match_status_at_selection, created_by, created_at, updated_at"
        ") VALUES (3, 1, 1, '缺價書', '作者', '出版社', '9789572222224', 'valid', 0, 0, 'available', ?, "
        "'2026-01-01', '2026-01-01')",
        (user_id,),
    )
    conn.commit()
    conn.close()

    res = check_export_readiness(1, "purchase_price")
    assert res["total_selected"] == 3
    assert res["export_ready"] == 1
    assert res["needs_review"] == 1
    assert res["missing_required"] == 1

    by_id = {d["sel_id"]: d for d in res["details"]}
    assert by_id[1]["can_export"] is True
    assert by_id[1]["missing_blocking_fields"] == []
    assert set(by_id[1]["missing_review_fields"]) == {"作者", "出版社", "ISBN"}

    assert by_id[2]["can_export"] is True
    assert by_id[2]["missing_blocking_fields"] == []
    assert by_id[2]["missing_review_fields"] == []

    assert by_id[3]["can_export"] is False
    assert "定價(單價)" in by_id[3]["missing_blocking_fields"]


# ---------------------------------------------------------------------------
# 4. Generic Builtin Excel Export & Decoupled Routing
# ---------------------------------------------------------------------------


def test_export_generic_books_xlsx_and_job_record(tmp_path, monkeypatch):
    db_path = _make_migrated_db(tmp_path, monkeypatch)
    user_id = _seed_user(db_path)

    conn = sqlite3.connect(str(db_path))
    assert conn.execute("SELECT COUNT(*) FROM export_templates").fetchone()[0] == 0
    conn.execute(
        "INSERT INTO procurement_projects("
        "id, name, project_type, export_template_type, budget_amount, "
        "academic_year, funding_source, created_at, updated_at"
        ") VALUES (1, '115 家長會贈書', 'custom', 'generic_builtin', 20000, "
        "'115學年度', '家長會補助', '2026-01-01', '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO selection_items("
        "project_id, selected_quantity, title, author, publisher, isbn, isbn_normalized, "
        "isbn_status, list_price, purchase_price, notes, match_status_at_selection, "
        "created_by, created_at, updated_at"
        ") VALUES (1, 2, '科學大冒險', '林老師', '科學社', '9789571234567', '9789571234567', "
        "'valid', 400, 300, '優先購買', 'available', ?, '2026-01-01', '2026-01-01')",
        (user_id,),
    )
    conn.execute(
        "INSERT INTO selection_items("
        "project_id, selected_quantity, title, author, publisher, isbn, isbn_normalized, "
        "isbn_status, list_price, purchase_price, notes, match_status_at_selection, "
        "created_by, created_at, updated_at"
        ") VALUES (1, 1, '無ISBN繪本', '陳作者', '繪本社', '', '', "
        "'missing_isbn', 350, 280, '', 'missing_isbn', ?, '2026-01-01', '2026-01-01')",
        (user_id,),
    )
    # Already owned without force_owned -> should be excluded
    conn.execute(
        "INSERT INTO selection_items("
        "project_id, selected_quantity, title, isbn_normalized, isbn_status, "
        "list_price, purchase_price, match_status_at_selection, created_by, created_at, updated_at"
        ") VALUES (1, 1, '已館藏書', '9789570000001', 'valid', 500, 400, 'already_owned', ?, "
        "'2026-01-01', '2026-01-01')",
        (user_id,),
    )
    conn.commit()
    conn.close()

    out_dir = tmp_path / "exports"
    settings = ExportSettings(
        project_id=1,
        school_name="幸福國小",
        approved_budget=20000,
        price_field="purchase_price",
        subtotal_mode="quantity_times_purchase_price",
        output_dir=str(out_dir),
        exported_by=user_id,
    )
    job_id = export_generic_books(settings)
    assert int(job_id) > 0

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    job = conn.execute("SELECT * FROM export_jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()

    assert job["template_path"] == "generic_builtin"
    assert job["export_template_id"] is None
    assert job["record_count"] == 2
    assert job["total_amount"] == 880.0
    assert job["output_filename"].startswith("通用採購書單_")
    assert Path(job["output_path"]).is_file()

    wb = openpyxl.load_workbook(job["output_path"])
    try:
        ws = wb.active
        assert ws["A1"].value == "115 家長會贈書"
        assert "校名：幸福國小" in ws["A2"].value
        assert "年度：115學年度" in ws["A2"].value
        assert "經費來源：家長會補助" in ws["A2"].value
        assert "20,000" in ws["A2"].value

        # Row 3: Headers
        headers = [ws.cell(3, c).value for c in range(1, 10)]
        assert headers == ["序號", "書名", "作者", "出版社", "ISBN", "數量", "單價", "小計", "備註"]

        # Row 4: Book 1 (ISBN stored as string with '@' number format)
        assert ws.cell(4, 1).value == 1
        assert ws.cell(4, 2).value == "科學大冒險"
        assert ws.cell(4, 5).value == "9789571234567"
        assert isinstance(ws.cell(4, 5).value, str)
        assert ws.cell(4, 5).number_format == "@"
        assert ws.cell(4, 6).value == 2
        assert ws.cell(4, 7).value == 300
        assert ws.cell(4, 8).value == 600
        assert ws.cell(4, 9).value == "優先購買"

        # Row 5: Book 2
        assert ws.cell(5, 2).value == "無ISBN繪本"
        assert ws.cell(5, 8).value == 280

        # Row 6: Summary
        assert ws.cell(6, 1).value == "合計"
        assert ws.cell(6, 6).value == 3
        assert ws.cell(6, 8).value == 880
    finally:
        wb.close()


def test_export_generic_books_cleans_up_partial_file_on_save_error(tmp_path, monkeypatch):
    db_path = _make_migrated_db(tmp_path, monkeypatch)
    user_id = _seed_user(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO procurement_projects("
        "id, name, project_type, export_template_type, created_at, updated_at"
        ") VALUES (1, '失敗測試', 'custom', 'generic_builtin', '2026-01-01', '2026-01-01')"
    )
    conn.commit()
    conn.close()

    def _failing_save(self, filename):
        Path(filename).write_bytes(b"partial")
        raise OSError("disk full")

    monkeypatch.setattr(openpyxl.Workbook, "save", _failing_save)

    out_dir = tmp_path / "exports_fail"
    settings = ExportSettings(
        project_id=1,
        school_name="",
        approved_budget=None,
        price_field="purchase_price",
        subtotal_mode="quantity_times_purchase_price",
        output_dir=str(out_dir),
        exported_by=user_id,
    )
    with pytest.raises(OSError, match="disk full"):
        export_generic_books(settings)

    assert list(out_dir.glob("*.xlsx")) == []


def test_exports_router_dispatches_by_export_template_type(tmp_path, monkeypatch):
    db_path = _make_migrated_db(tmp_path, monkeypatch)
    user_id = _seed_user(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO procurement_projects(id, name, project_type, export_template_type, created_at, updated_at) "
        "VALUES (1, '本土用通用範本', 'local_culture', 'generic_builtin', '2026-01-01', '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO procurement_projects(id, name, project_type, export_template_type, created_at, updated_at) "
        "VALUES (2, '自訂用本土範本', 'custom', 'local_culture', '2026-01-01', '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO procurement_projects(id, name, project_type, export_template_type, created_at, updated_at) "
        "VALUES (3, '自訂用一般範本', 'custom', 'general_books', '2026-01-01', '2026-01-01')"
    )
    conn.commit()
    conn.close()

    called: list[str] = []
    monkeypatch.setattr("app.routers.exports.export_generic_books", lambda s: (called.append("generic"), "101")[1])
    monkeypatch.setattr("app.routers.exports.export_local_culture", lambda s: (called.append("local"), "102")[1])
    monkeypatch.setattr("app.routers.exports.export_general_books", lambda s: (called.append("general"), "103")[1])

    app.dependency_overrides[require_auth] = lambda: user_id
    try:
        client = TestClient(app, raise_server_exceptions=True)
        r1 = client.post("/api/exports/local-culture", json={"project_id": 1})
        r2 = client.post("/api/exports/local-culture", json={"project_id": 2})
        r3 = client.post("/api/exports/local-culture", json={"project_id": 3})
        assert r1.status_code == 200 and r1.json()["job_id"] == "101"
        assert r2.status_code == 200 and r2.json()["job_id"] == "102"
        assert r3.status_code == 200 and r3.json()["job_id"] == "103"
        assert called == ["generic", "local", "general"]
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 5. Frontend Structure & JS Syntax Checks
# ---------------------------------------------------------------------------


def test_frontend_elements_and_js_syntax(tmp_path):
    static_dir = REPO_ROOT / "app" / "static"
    projects_html = (static_dir / "projects.html").read_text(encoding="utf-8")
    selection_html = (static_dir / "selection.html").read_text(encoding="utf-8")
    export_html = (static_dir / "export.html").read_text(encoding="utf-8")
    common_js = (static_dir / "js" / "common.js").read_text(encoding="utf-8")

    # Preserved & new IDs in projects.html
    for required_id in (
        'id="new-price-field"',
        'id="new-subtotal"',
        'id="edit-price-field"',
        'id="edit-subtotal"',
        'id="new-export-template"',
        'id="edit-export-template"',
        'id="new-pricing-preset"',
        'id="edit-pricing-preset"',
        'id="new-pricing-advanced"',
        'id="edit-pricing-advanced"',
        'id="new-academic-year"',
        'id="new-funding-source"',
        'id="new-project-notes"',
        'id="show-archived-toggle"',
        'value="custom"',
    ):
        assert required_id in projects_html

    assert 'id="project-notes-banner"' in selection_html
    assert 'id="generic-template-note"' in export_html
    assert "function exportTemplateLabel" in common_js
    assert "function projectTypeRuleHint" in common_js

    # Node JS syntax check on common.js and embedded <script> blocks
    node_bin = shutil.which("node")
    if node_bin:
        res = subprocess.run(
            [node_bin, "--check", str(static_dir / "js" / "common.js")], capture_output=True, text=True
        )
        assert res.returncode == 0, res.stderr

        script_re = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE)
        for page in ("projects.html", "selection.html", "export-check.html", "export.html"):
            html = (static_dir / page).read_text(encoding="utf-8")
            scripts = script_re.findall(html)
            assert scripts, f"No inline script found in {page}"
            tmp_js = tmp_path / f"{page}.js"
            tmp_js.write_text("\n".join(scripts), encoding="utf-8")
            r = subprocess.run([node_bin, "--check", str(tmp_js)], capture_output=True, text=True)
            assert r.returncode == 0, f"{page} JS syntax error: {r.stderr}"
