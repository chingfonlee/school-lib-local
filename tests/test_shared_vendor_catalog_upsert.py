"""Tests for shared vendor catalog pool (Mode B), upsert, price comparison, and profile recommendation."""

import io
import json
from pathlib import Path

import openpyxl
import pytest
from starlette.testclient import TestClient

from app import database as db
from app.auth import require_auth
from app.main import app
from app.services import completeness_service, import_service, match_service


def _setup_migrated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_file = tmp_path / "shared_catalog_test.db"
    monkeypatch.setattr(db, "get_db_path", lambda: str(db_file))
    db.run_migrations()
    with db.db_session() as conn:
        conn.execute(
            "INSERT INTO users(id, username, password_hash, display_name, created_at, updated_at) "
            "VALUES (1, 'admin', 'x', '管理員', '', '')"
        )
        conn.commit()
    return db_file


def _make_xlsx(headers: list[str], rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


BASIC_HEADERS = ["書名", "作者", "出版社", "條碼", "定價", "單價", "獲獎項目"]
BASIC_MAPPINGS = {
    "title": "書名",
    "author": "作者",
    "publisher": "出版社",
    "isbn": "條碼",
    "list_price": "定價",
    "purchase_price": "單價",
    "award_item": "獲獎項目",
}


def test_migration_010_adds_vendor_name_column_and_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_migrated_db(tmp_path, monkeypatch)
    with db.db_session() as conn:
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(import_batches)").fetchall()]
        indexes = [r["name"] for r in conn.execute("PRAGMA index_list(import_batches)").fetchall()]
    assert "vendor_name" in cols
    assert "idx_import_batches_batch_type_vendor" in indexes


def test_multi_vendor_accumulation_and_upsert_preserves_overrides_and_awards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_migrated_db(tmp_path, monkeypatch)

    with db.db_session() as conn:
        conn.execute(
            "INSERT INTO procurement_projects(id, name, project_type, export_template_type, created_at, updated_at) "
            "VALUES (1, '115一般圖書', 'general_books', 'general_books', '', '')"
        )
        conn.commit()

    # 1. Import Vendor A with award overrides (and without requiring project_id)
    xlsx_a1 = _make_xlsx(
        BASIC_HEADERS,
        [
            ["科學大冒險", "作者甲", "遠流", "9789861111111", "400", "320", "中小學生讀物選介"],
            ["故事繪本", "作者乙", "信誼", "9789862222222", "300", "240", "好書大家讀"],
            ["合計", "", "", "", "700", "560", ""],
        ],
    )
    res_a1 = import_service.confirm_import(
        file_bytes=xlsx_a1,
        filename="vendor_a_v1.xlsx",
        project_id=None,
        sheet_name=None,
        header_row=0,
        mappings=BASIC_MAPPINGS,
        extra_field_settings=[],
        user_id=1,
        vendor_name="書商A",
        import_mode="upsert",
        award_overrides={
            "中小學生讀物選介": {
                "recommendation_source": "文化部中小學生讀物選介",
                "eligibility_label": "推薦",
                "award_notes": "第46次",
            }
        },
    )
    assert res_a1["vendor_name"] == "書商A"
    assert res_a1["import_mode"] == "upsert"
    assert res_a1["inserted_count"] == 2
    assert res_a1["updated_count"] == 0
    assert res_a1["preserved_override_count"] == 0
    assert res_a1["skipped_count"] == 1
    assert res_a1["record_count"] == 2

    with db.db_session() as conn:
        batch_row = conn.execute(
            "SELECT project_id, vendor_name FROM import_batches WHERE id = ?", (res_a1["batch_id"],)
        ).fetchone()
        assert batch_row["project_id"] is None
        assert batch_row["vendor_name"] == "書商A"

        book1 = conn.execute(
            "SELECT id, purchase_price, recommendation_source, eligibility_label, award_notes "
            "FROM vendor_books WHERE isbn_normalized = '9789861111111'"
        ).fetchone()
        book1_id = book1["id"]
        assert book1["purchase_price"] == 320.0
        assert book1["recommendation_source"] == "文化部中小學生讀物選介"
        assert book1["eligibility_label"] == "推薦"
        assert book1["award_notes"] == "第46次"

        # Teacher manually overrides author & adds a selection item referencing book1_id
        conn.execute(
            "UPDATE vendor_books SET user_overrides = ? WHERE id = ?",
            (json.dumps({"author": "老師修正作者"}, ensure_ascii=False), book1_id),
        )
        conn.execute(
            "INSERT INTO selection_items(project_id, vendor_book_id, selected_quantity, "
            "title, isbn, isbn_normalized, isbn_status, completeness_status, created_at, updated_at) "
            "VALUES (1, ?, 1, '科學大冒險', '9789861111111', '9789861111111', 'valid', 'export_ready', '', '')",
            (book1_id,),
        )
        conn.commit()

    # 2. Import Vendor B (accumulates alongside Vendor A)
    xlsx_b = _make_xlsx(
        BASIC_HEADERS,
        [["科學大冒險", "作者甲", "遠流", "9789861111111", "400", "290", "好書獎"]],
    )
    res_b = import_service.confirm_import(
        file_bytes=xlsx_b,
        filename="vendor_b.xlsx",
        project_id=None,
        sheet_name=None,
        header_row=0,
        mappings=BASIC_MAPPINGS,
        extra_field_settings=[],
        user_id=1,
        vendor_name="書商B",
        import_mode="upsert",
    )
    assert res_b["inserted_count"] == 1

    # 3. Upsert Vendor A with updated price, a new book, and a duplicate ISBN inside the same file
    xlsx_a2 = _make_xlsx(
        BASIC_HEADERS,
        [
            ["科學大冒險（新版）", "作者甲", "遠流", "9789861111111", "420", "310", "中小學生讀物選介"],
            ["新書一", "作者丙", "天下", "9789863333333", "350", "280", "好書獎"],
            ["新書一（更正價）", "作者丙", "天下", "9789863333333", "350", "270", "好書獎"],
        ],
    )
    res_a2 = import_service.confirm_import(
        file_bytes=xlsx_a2,
        filename="vendor_a_v2.xlsx",
        project_id=1,
        sheet_name=None,
        header_row=0,
        mappings=BASIC_MAPPINGS,
        extra_field_settings=[],
        user_id=1,
        vendor_name="書商A",
        import_mode="upsert",
    )
    assert res_a2["inserted_count"] == 1
    assert res_a2["updated_count"] == 1
    assert res_a2["preserved_override_count"] == 1
    assert res_a2["record_count"] == 2

    with db.db_session() as conn:
        # Original vendor_books.id preserved, price updated, user_overrides & awards preserved
        updated_book1 = conn.execute("SELECT * FROM vendor_books WHERE id = ?", (book1_id,)).fetchone()
        assert updated_book1 is not None
        assert updated_book1["title"] == "科學大冒險（新版）"
        assert updated_book1["list_price"] == 420.0
        assert updated_book1["purchase_price"] == 310.0
        assert json.loads(updated_book1["user_overrides"]) == {"author": "老師修正作者"}
        assert updated_book1["recommendation_source"] == "文化部中小學生讀物選介"
        assert updated_book1["eligibility_label"] == "推薦"
        assert updated_book1["award_notes"] == "第46次"

        # Same-file duplicate ISBN collapsed to a single row with last row's price
        dup_rows = conn.execute(
            "SELECT title, purchase_price FROM vendor_books WHERE isbn_normalized = '9789863333333'"
        ).fetchall()
        assert len(dup_rows) == 1
        assert dup_rows[0]["title"] == "新書一（更正價）"
        assert dup_rows[0]["purchase_price"] == 270.0

        # Total books across Vendor A (3) + Vendor B (1) = 4
        total_books = conn.execute("SELECT COUNT(*) FROM vendor_books").fetchone()[0]
        assert total_books == 4


def test_replace_vendor_and_vendor_clear_management(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_migrated_db(tmp_path, monkeypatch)

    with db.db_session() as conn:
        conn.execute(
            "INSERT INTO procurement_projects(id, name, project_type, export_template_type, created_at, updated_at) "
            "VALUES (1, '專案甲', 'local_culture', 'local_culture', '', '')"
        )
        conn.commit()

    xlsx_a = _make_xlsx(
        BASIC_HEADERS,
        [
            ["A書1", "作者1", "社1", "9789861000001", "300", "240", "獎"],
            ["A書2", "作者2", "社2", "9789861000002", "300", "240", "獎"],
        ],
    )
    xlsx_b = _make_xlsx(
        BASIC_HEADERS,
        [["B書1", "作者B", "社B", "9789862000001", "350", "280", "獎"]],
    )
    import_service.confirm_import(xlsx_a, "a1.xlsx", mappings=BASIC_MAPPINGS, vendor_name="書商A", user_id=1)
    import_service.confirm_import(xlsx_b, "b1.xlsx", mappings=BASIC_MAPPINGS, vendor_name="書商B", user_id=1)

    with db.db_session() as conn:
        a_id = conn.execute("SELECT id FROM vendor_books WHERE isbn_normalized = '9789861000001'").fetchone()["id"]
        conn.execute(
            "INSERT INTO selection_items(project_id, vendor_book_id, selected_quantity, "
            "title, isbn, isbn_normalized, isbn_status, completeness_status, created_at, updated_at) "
            "VALUES (1, ?, 1, 'A書1', '9789861000001', '9789861000001', 'valid', 'export_ready', '', '')",
            (a_id,),
        )
        conn.commit()

    # replace_vendor on 書商A: only 書商A replaced, 書商B & selection_items untouched
    xlsx_a_new = _make_xlsx(
        BASIC_HEADERS,
        [["A新書", "作者新", "社新", "9789861000099", "280", "220", "獎"]],
    )
    res_rep = import_service.confirm_import(
        xlsx_a_new,
        "a2.xlsx",
        mappings=BASIC_MAPPINGS,
        vendor_name="書商A",
        import_mode="replace_vendor",
        user_id=1,
    )
    assert res_rep["inserted_count"] == 1
    assert res_rep["updated_count"] == 0

    vendors = {v["vendor_name"]: v for v in import_service.list_vendors()}
    assert set(vendors.keys()) == {"書商A", "書商B"}
    assert vendors["書商A"]["book_count"] == 1
    assert vendors["書商B"]["book_count"] == 1

    app.dependency_overrides[require_auth] = lambda: 1
    try:
        client = TestClient(app, raise_server_exceptions=True)

        # GET /api/imports/vendors
        res_v = client.get("/api/imports/vendors")
        assert res_v.status_code == 200
        assert len(res_v.json()) == 2

        # DELETE without params -> 400
        res_bad = client.delete("/api/imports/vendor-books")
        assert res_bad.status_code == 400

        # DELETE single vendor -> preserves 書商B and selection_items
        res_del_a = client.delete("/api/imports/vendor-books", params={"vendor_name": "書商A"})
        assert res_del_a.status_code == 200
        assert res_del_a.json()["deleted_vendor_books"] == 1
        assert res_del_a.json()["preserved_selection_items"] == 1

        remaining_vendors = client.get("/api/imports/vendors").json()
        assert [v["vendor_name"] for v in remaining_vendors] == ["書商B"]

        # DELETE clear_all=true -> clears all remaining vendor books, preserves selection_items
        res_del_all = client.delete("/api/imports/vendor-books", params={"clear_all": "true"})
        assert res_del_all.status_code == 200
        assert res_del_all.json()["deleted_vendor_books"] == 1
        assert res_del_all.json()["preserved_selection_items"] == 1
        assert client.get("/api/imports/vendors").json() == []
    finally:
        app.dependency_overrides.clear()


def test_matches_price_compare_vendor_filter_has_exported_and_dynamic_completeness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_migrated_db(tmp_path, monkeypatch)

    with db.db_session() as conn:
        conn.execute(
            "INSERT INTO procurement_projects(id, name, project_type, export_template_type, created_at, updated_at) "
            "VALUES "
            "(1, '115本土文化', 'local_culture', 'local_culture', '', ''), "
            "(2, '115一般圖書', 'general_books', 'general_books', '', ''), "
            "(3, '115偏鄉已匯出', 'local_culture', 'local_culture', '', '')"
        )
        # Legacy batch with project_id=1 and vendor_name=NULL -> normalized to 未指定書商
        conn.execute(
            "INSERT INTO import_batches(id, project_id, batch_type, original_filename, vendor_name, imported_at) "
            "VALUES "
            "(1, 1, 'vendor_books', 'legacy.xlsx', NULL, '2026-01-01T00:00:00'), "
            "(2, NULL, 'vendor_books', 'vendor_a.xlsx', '書商A', '2026-02-01T00:00:00'), "
            "(3, NULL, 'vendor_books', 'vendor_b.xlsx', '書商B', '2026-02-02T00:00:00')"
        )
        # Book 101 (未指定書商): has title, author, publisher, price, award_item, NO eligibility/recommendation
        #   -> export_ready for local_culture, missing_required for general_books!
        # Book 102 (書商A) & Book 103 (書商B): same ISBN 9789865555555, prices 300 vs 250
        conn.execute(
            "INSERT INTO vendor_books(id, batch_id, title, author, publisher, isbn, isbn_normalized, "
            "list_price, purchase_price, award_item, isbn_status, completeness_status) "
            "VALUES "
            "(101, 1, '舊批次本土書', '作者1', '出版1', '9789864444444', '9789864444444', "
            "300, 240, '好書獎', 'valid', 'export_ready'), "
            "(102, 2, '跨書商比價書', '作者2', '出版2', '9789865555555', '9789865555555', "
            "400, 300, '好書獎', 'valid', 'export_ready'), "
            "(103, 3, '跨書商比價書', '作者2', '出版2', '9789865555555', '9789865555555', "
            "400, 250, '好書獎', 'valid', 'export_ready')"
        )
        # Project 2 selects ISBN 9789865555555 (NOT exported), Project 3 selects it AND has export_jobs
        conn.execute(
            "INSERT INTO selection_items(project_id, vendor_book_id, selected_quantity, "
            "title, isbn, isbn_normalized, isbn_status, completeness_status, created_at, updated_at) "
            "VALUES "
            "(2, 102, 1, '跨書商比價書', '9789865555555', '9789865555555', 'valid', 'export_ready', '', ''), "
            "(3, 103, 1, '跨書商比價書', '9789865555555', '9789865555555', 'valid', 'export_ready', '', '')"
        )
        conn.execute(
            "INSERT INTO export_jobs(project_id, price_field, subtotal_mode, exported_at) "
            "VALUES (3, 'purchase_price', 'quantity_times_purchase_price', '2026-03-01T00:00:00')"
        )
        conn.commit()

    match_service.run_match()

    app.dependency_overrides[require_auth] = lambda: 1
    try:
        client = TestClient(app, raise_server_exceptions=True)

        # Query under project 1 (local_culture): all 3 books visible, legacy batch normalized to 未指定書商
        res1 = client.get("/api/books/matches", params={"project_id": 1})
        assert res1.status_code == 200
        by_id_p1 = {b["id"]: b for b in res1.json()}
        assert set(by_id_p1.keys()) == {101, 102, 103}
        assert by_id_p1[101]["vendor_name"] == "未指定書商"
        assert by_id_p1[101]["completeness_status"] == "export_ready"

        # Cross-vendor offers on 102 (書商A) should list 書商B (250)
        assert by_id_p1[102]["other_vendor_offers"] == [
            {
                "vendor_book_id": 103,
                "vendor_name": "書商B",
                "purchase_price": 250.0,
                "list_price": 400.0,
            }
        ]
        # Other project selections distinguish has_exported
        assert by_id_p1[102]["other_project_selections"] == [
            {"project_id": 2, "project_name": "115一般圖書", "has_exported": False},
            {"project_id": 3, "project_name": "115偏鄉已匯出", "has_exported": True},
        ]

        # Query under project 2 (general_books): dynamic completeness_status is missing_required
        res2 = client.get("/api/books/matches", params={"project_id": 2})
        assert res2.status_code == 200
        by_id_p2 = {b["id"]: b for b in res2.json()}
        assert by_id_p2[101]["completeness_status"] == "missing_required"

        # Filter by vendor_name and dynamic completeness_status
        res_filtered = client.get(
            "/api/books/matches",
            params={"project_id": 2, "vendor_name": "書商A", "completeness_status": "missing_required"},
        )
        assert [b["id"] for b in res_filtered.json()] == [102]
        # Even when filtered to 書商A, other_vendor_offers still shows 書商B!
        assert res_filtered.json()[0]["other_vendor_offers"][0]["vendor_name"] == "書商B"

        # Stats with vendor_name filter & dynamic completeness_status
        stats_p2 = client.get("/api/books/stats", params={"project_id": 2, "vendor_name": "書商A"}).json()
        assert stats_p2["total_vendor_books"] == 1
        assert stats_p2["completeness_status"] == {"missing_required": 1}

        # PATCH overrides with project_id=2 recomputes for general_books on shared book (batch.project_id IS NULL)
        patch_res = client.patch(
            "/api/books/102/overrides",
            params={"project_id": 2},
            json={"overrides": {"eligibility_label": "必選", "recommendation_source": "喜閱網"}},
        )
        assert patch_res.status_code == 200
        assert patch_res.json()["completeness_status"] == "export_ready"

        # recompute_for_book works directly on shared book (project_id IS NULL)
        assert completeness_service.recompute_for_book(102, project_type="general_books") == "export_ready"

        # Projects list reflects shared vendor catalog pool for newly created project
        projects = client.get("/api/projects/").json()
        proj2 = next(p for p in projects if p["id"] == 2)
        assert proj2["vendor_book_count"] == 3
        assert proj2["last_import"] == "2026-02-02T00:00:00"
    finally:
        app.dependency_overrides.clear()


def test_preview_excel_recommends_matching_import_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_migrated_db(tmp_path, monkeypatch)

    with db.db_session() as conn:
        conn.execute(
            "INSERT INTO import_profiles"
            "(name, file_type, column_mappings, project_type, source_type, header_row, "
            "mappings, extra_field_settings, created_at, updated_at) "
            "VALUES (?, 'vendor_books', ?, 'general_books', 'excel', 0, ?, ?, '', '')",
            (
                "聯經標準格式",
                json.dumps(
                    {"title": "品名", "isbn": "國際書碼", "list_price": "原價", "author": "著譯者"}, ensure_ascii=False
                ),
                json.dumps(
                    {"title": "品名", "isbn": "國際書碼", "list_price": "原價", "author": "著譯者"}, ensure_ascii=False
                ),
                json.dumps(["備註欄"], ensure_ascii=False),
            ),
        )
        conn.commit()

    # Matching 3 of 4 columns (0.75 >= 0.5 and >= 2) -> recommended!
    matching_xlsx = _make_xlsx(["品名", "國際書碼", "原價", "備註欄"], [["書一", "9789861111111", "300", "特價"]])
    res_hit = import_service.preview_excel(matching_xlsx, "lianjing.xlsx", header_row=0)
    rec = res_hit["recommended_profile"]
    assert rec is not None
    assert rec["name"] == "聯經標準格式"
    assert rec["matched_columns"] == 3
    assert rec["total_profile_columns"] == 4
    assert rec["overlap_ratio"] == 0.75
    assert rec["extra_field_settings"] == ["備註欄"]

    # Matching only 1 of 4 columns -> below threshold -> None
    non_matching_xlsx = _make_xlsx(["品名", "ISBN", "售價", "出版社"], [["書一", "9789861111111", "300", "遠流"]])
    res_miss = import_service.preview_excel(non_matching_xlsx, "other.xlsx", header_row=0)
    assert res_miss["recommended_profile"] is None


def test_frontend_shared_catalog_markers_present() -> None:
    import_html = Path("app/static/import.html").read_text(encoding="utf-8")
    selection_html = Path("app/static/selection.html").read_text(encoding="utf-8")
    match_html = Path("app/static/match.html").read_text(encoding="utf-8")
    projects_html = Path("app/static/projects.html").read_text(encoding="utf-8")

    assert 'id="vendor-name-input"' in import_html
    assert 'id="import-mode-select"' in import_html
    assert 'id="profile-rec-banner"' in import_html
    assert "applyRecommendedProfile" in import_html
    assert "clearSelectedVendor" in import_html
    assert "clearAllVendorBooks" in import_html

    assert 'id="filter-vendor"' in selection_html
    assert "other_vendor_offers" in selection_html
    assert "他案已匯出" in selection_html
    assert "他案選書中" in selection_html

    assert 'id="filter-vendor"' in match_html
    assert "他案已匯出" in match_html
    assert "他案選書中" in match_html

    assert "全校共用書商書單庫" in projects_html
