from pathlib import Path

import pytest
from starlette.testclient import TestClient

from app import database as db
from app.auth import require_auth
from app.main import app
from app.services import match_service


def _setup_migrated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_file = tmp_path / "match_perf.db"
    monkeypatch.setattr(db, "get_db_path", lambda: str(db_file))
    db.run_migrations()
    with db.db_session() as conn:
        conn.execute(
            "INSERT INTO users(id, username, password_hash, display_name, created_at, updated_at) "
            "VALUES (1, 'admin', 'x', '管理員', '', '')"
        )
        conn.commit()
    return db_file


def test_migration_011_selection_isbn_index_exists_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_migrated_db(tmp_path, monkeypatch)

    with db.db_session() as conn:
        indexes = {row["name"] for row in conn.execute("PRAGMA index_list(selection_items)").fetchall()}
        assert "idx_selection_items_isbn_normalized" in indexes

        sql_text = Path("migrations/011_add_selection_isbn_index.sql").read_text(encoding="utf-8")
        conn.executescript(sql_text)
        indexes_after = {row["name"] for row in conn.execute("PRAGMA index_list(selection_items)").fetchall()}
        assert "idx_selection_items_isbn_normalized" in indexes_after


def test_get_matches_excludes_large_fields_and_supports_pagination_and_skip_offers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_migrated_db(tmp_path, monkeypatch)

    with db.db_session() as conn:
        conn.execute(
            "INSERT INTO procurement_projects(id, name, project_type, export_template_type, created_at, updated_at) "
            "VALUES (1, '114一般圖書', 'general_books', 'general_books', '', '')"
        )
        conn.execute(
            "INSERT INTO import_batches(id, project_id, batch_type, vendor_name, original_filename, imported_at) "
            "VALUES "
            "(1, 1, 'vendor_books', '甲書商', 'v1.xlsx', ''), "
            "(2, 1, 'vendor_books', '乙書商', 'v2.xlsx', '')"
        )
        # Book 101 and 105 share the same ISBN across two vendors so other_vendor_offers is populated
        conn.execute(
            "INSERT INTO vendor_books("
            "  id, batch_id, title, author, publisher, isbn, isbn_normalized, isbn_status, "
            "  list_price, purchase_price, summary, raw_row, extra_fields, completeness_status"
            ") VALUES "
            "(101, 1, '書一', '作者一', '社一', '9789860000001', '9789860000001', 'valid', "
            "  300, 240, '簡介一', '{\"raw\":1}', '{\"extra\":1}', 'export_ready'), "
            "(102, 1, '書二', '作者二', '社二', '9789860000002', '9789860000002', 'valid', "
            "  320, 250, '簡介二', '{\"raw\":2}', '{\"extra\":2}', 'export_ready'), "
            "(103, 1, '書三', '作者三', '社三', '9789860000003', '9789860000003', 'valid', "
            "  350, 260, '簡介三', '{\"raw\":3}', '{\"extra\":3}', 'export_ready'), "
            "(104, 1, '書四', '作者四', '社四', '9789860000004', '9789860000004', 'valid', "
            "  380, 280, '簡介四', '{\"raw\":4}', '{\"extra\":4}', 'export_ready'), "
            "(105, 2, '書一（乙商）', '作者一', '社一', '9789860000001', '9789860000001', 'valid', "
            "  300, 220, '簡介五', '{\"raw\":5}', '{\"extra\":5}', 'export_ready')"
        )
        conn.commit()

    match_service.run_match(1)

    app.dependency_overrides[require_auth] = lambda: 1
    try:
        client = TestClient(app)

        # Backward-compatible mode (no page param): list without raw_row/extra_fields, keeps summary & offers
        res_all = client.get("/api/books/matches", params={"project_id": 1})
        assert res_all.status_code == 200
        data_all = res_all.json()
        assert isinstance(data_all, list)
        assert len(data_all) == 5
        for item in data_all:
            assert "raw_row" not in item
            assert "extra_fields" not in item
            assert "summary" in item
        by_id = {item["id"]: item for item in data_all}
        assert by_id[101]["summary"] == "簡介一"
        assert len(by_id[101]["other_vendor_offers"]) == 1
        assert by_id[101]["other_vendor_offers"][0]["vendor_name"] == "乙書商"

        # Paginated mode with include_offers=false
        res_p1 = client.get(
            "/api/books/matches",
            params={"project_id": 1, "page": 1, "page_size": 2, "include_offers": "false"},
        )
        assert res_p1.status_code == 200
        p1 = res_p1.json()
        assert isinstance(p1, dict)
        assert p1["total"] == 5
        assert p1["page"] == 1
        assert p1["page_size"] == 2
        assert p1["total_pages"] == 3
        assert [item["id"] for item in p1["items"]] == [101, 102]
        for item in p1["items"]:
            assert item["other_vendor_offers"] == []
            assert "raw_row" not in item
            assert "extra_fields" not in item

        # Last page
        res_p3 = client.get(
            "/api/books/matches",
            params={"project_id": 1, "page": 3, "page_size": 2, "include_offers": "false"},
        )
        assert res_p3.status_code == 200
        p3 = res_p3.json()
        assert [item["id"] for item in p3["items"]] == [105]
        assert p3["items"][0]["other_vendor_offers"] == []

        # Out-of-range page returns empty items with valid metadata
        res_p9 = client.get(
            "/api/books/matches",
            params={"project_id": 1, "page": 9, "page_size": 2, "include_offers": "false"},
        )
        assert res_p9.status_code == 200
        p9 = res_p9.json()
        assert p9 == {"items": [], "total": 5, "page": 9, "page_size": 2, "total_pages": 3}

        # Empty result set respects both paginated and non-paginated formats
        res_empty_page = client.get(
            "/api/books/matches",
            params={"project_id": 1, "vendor_name": "不存在書商", "page": 1, "page_size": 10},
        )
        assert res_empty_page.status_code == 200
        assert res_empty_page.json() == {"items": [], "total": 0, "page": 1, "page_size": 10, "total_pages": 0}

        res_empty_list = client.get(
            "/api/books/matches",
            params={"project_id": 1, "vendor_name": "不存在書商"},
        )
        assert res_empty_list.status_code == 200
        assert res_empty_list.json() == []
    finally:
        app.dependency_overrides.clear()


def test_get_stats_other_project_duplicate_count_accuracy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_migrated_db(tmp_path, monkeypatch)

    with db.db_session() as conn:
        conn.execute(
            "INSERT INTO procurement_projects(id, name, project_type, export_template_type, created_at, updated_at) "
            "VALUES "
            "(1, '專案甲', 'general_books', 'general_books', '', ''), "
            "(2, '專案乙', 'local_culture', 'local_culture', '', '')"
        )
        conn.execute(
            "INSERT INTO import_batches(id, project_id, batch_type, vendor_name, original_filename, imported_at) "
            "VALUES "
            "(1, 1, 'vendor_books', '書商A', 'a.xlsx', ''), "
            "(2, 1, 'vendor_books', '書商B', 'b.xlsx', '')"
        )
        conn.execute(
            "INSERT INTO vendor_books(id, batch_id, title, isbn, isbn_normalized, isbn_status, completeness_status) "
            "VALUES "
            "(1, 1, '他案已選1', '9789861111111', '9789861111111', 'valid', 'export_ready'), "
            "(2, 2, '他案已選2', '9789862222222', '9789862222222', 'valid', 'export_ready'), "
            "(3, 1, '他案數量為0', '9789863333333', '9789863333333', 'valid', 'export_ready'), "
            "(4, 1, '僅本案已選', '9789864444444', '9789864444444', 'valid', 'export_ready')"
        )
        # Other project selections: 1 and 2 have qty > 0, 3 has qty = 0, plus empty/NULL ISBN rows
        conn.execute(
            "INSERT INTO selection_items("
            "  project_id, vendor_book_id, selected_quantity, isbn_normalized, created_at, updated_at"
            ") VALUES "
            "(2, 1, 2, '9789861111111', '', ''), "
            "(2, 2, 1, '9789862222222', '', ''), "
            "(2, 3, 0, '9789863333333', '', ''), "
            "(2, 901, 1, '', '', ''), "
            "(2, 902, 1, NULL, '', ''), "
            "(1, 4, 1, '9789864444444', '', '')"
        )
        conn.commit()

    match_service.run_match(1)

    app.dependency_overrides[require_auth] = lambda: 1
    try:
        client = TestClient(app)

        stats_all = client.get("/api/books/stats", params={"project_id": 1})
        assert stats_all.status_code == 200
        assert stats_all.json()["other_project_duplicate_count"] == 2

        stats_a = client.get("/api/books/stats", params={"project_id": 1, "vendor_name": "書商A"})
        assert stats_a.status_code == 200
        assert stats_a.json()["other_project_duplicate_count"] == 1

        stats_b = client.get("/api/books/stats", params={"project_id": 1, "vendor_name": "書商B"})
        assert stats_b.status_code == 200
        assert stats_b.json()["other_project_duplicate_count"] == 1
    finally:
        app.dependency_overrides.clear()


def test_match_html_contains_pagination_and_parallel_loading() -> None:
    html = Path("app/static/match.html").read_text(encoding="utf-8")

    # Paginated API call with include_offers=false
    assert "page=${currentPage}&page_size=${PAGE_SIZE}&include_offers=false" in html
    assert "const PAGE_SIZE = 100;" in html

    # Pagination controls
    assert 'id="pagination"' in html
    assert 'id="page-prev"' in html
    assert 'id="page-info"' in html
    assert 'id="page-next"' in html
    assert "上一頁" in html
    assert "下一頁" in html
    assert "第 ${currentPage} / ${totalPages} 頁，共 ${total} 筆" in html

    # Parallel loading of stats and books
    assert html.count("Promise.all([loadStats(), loadBooks()])") >= 3

    # Existing element IDs preserved
    for elem_id in (
        "project-label",
        "stats-row",
        "filter-vendor",
        "filter-match",
        "filter-comp",
        "result-count",
        "book-table",
        "book-body",
    ):
        assert f'id="{elem_id}"' in html
