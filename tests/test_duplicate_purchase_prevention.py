from pathlib import Path

import pytest
from starlette.testclient import TestClient

from app import database as db
from app.auth import require_auth
from app.main import app
from app.services import match_service


def _setup_migrated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_file = tmp_path / "dup_test.db"
    monkeypatch.setattr(db, "get_db_path", lambda: str(db_file))
    db.run_migrations()
    with db.db_session() as conn:
        conn.execute(
            "INSERT INTO users(id, username, password_hash, display_name, created_at, updated_at) "
            "VALUES (1, 'admin', 'x', '管理員', '', '')"
        )
        conn.commit()
    return db_file


def test_normalize_title_for_match_variants_and_boundaries() -> None:
    assert match_service.normalize_title_for_match(
        "魔法校車：人體大冒險（精裝）"
    ) == match_service.normalize_title_for_match("魔法校車 人體大冒險")

    # Fullwidth/halfwidth, case folding, punctuation, edition brackets
    assert match_service.normalize_title_for_match(
        "ＡＢＣ：科學大發現［修訂版］"
    ) == match_service.normalize_title_for_match("abc 科學大發現(平裝)")
    assert match_service.normalize_title_for_match("《台灣繪本》【繪本版】") == match_service.normalize_title_for_match(
        "台灣繪本（二版）"
    )
    assert match_service.normalize_title_for_match("經典故事（全新修訂版）") == match_service.normalize_title_for_match(
        "經典故事(典藏版)"
    )

    # Volume markers in brackets must NOT be stripped
    assert match_service.normalize_title_for_match("小王子（上）") != match_service.normalize_title_for_match(
        "小王子（下）"
    )
    assert match_service.normalize_title_for_match("科學探險(1)") != match_service.normalize_title_for_match(
        "科學探險(2)"
    )

    # Short / empty titles do not participate in title matching
    assert match_service.normalize_title_for_match(None) == ""
    assert match_service.normalize_title_for_match("") == ""
    assert match_service.normalize_title_for_match("   ") == ""
    assert match_service.normalize_title_for_match("家") == ""
    assert match_service.normalize_title_for_match("A!") == ""
    assert match_service.normalize_title_for_match("（精裝）") == ""


def test_run_match_detects_normalized_same_title_and_ignores_single_char(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_migrated_db(tmp_path, monkeypatch)

    with db.db_session() as conn:
        conn.execute(
            "INSERT INTO procurement_projects(id, name, project_type, export_template_type, created_at, updated_at) "
            "VALUES (1, '本土專案', 'local_culture', 'local_culture', '', '')"
        )
        conn.execute(
            "INSERT INTO import_batches(id, project_id, batch_type, original_filename, imported_at) "
            "VALUES (1, 1, 'vendor_books', 'v.xlsx', '')"
        )
        conn.execute(
            "INSERT INTO import_batches(id, project_id, batch_type, original_filename, imported_at) "
            "VALUES (2, NULL, 'library_holdings', 'h.xlsx', '')"
        )
        # Holdings: 1 exact ISBN, 1 same normalized title (different ISBN), 1 single-char title
        conn.execute(
            "INSERT INTO library_holdings(batch_id, isbn, isbn_normalized, title, author, publisher, isbn_status) "
            "VALUES "
            "(2, '9789860000001', '9789860000001', '完全相同ISBN書', '作者A', '社A', 'valid'), "
            "(2, '9789860000002', '9789860000002', '魔法校車：人體大冒險（精裝）', '喬安娜', '遠流', 'valid'), "
            "(2, '9789860000003', '9789860000003', '家', '巴金', '社C', 'valid')"
        )
        # Vendor books
        conn.execute(
            "INSERT INTO vendor_books(id, batch_id, title, isbn, isbn_normalized, isbn_status, completeness_status) "
            "VALUES "
            "(10, 1, '完全相同ISBN書', '9789860000001', '9789860000001', 'valid', 'export_ready'), "
            "(11, 1, '魔法校車 人體大冒險', '9789869999002', '9789869999002', 'valid', 'export_ready'), "
            "(12, 1, '家', '9789869999003', '9789869999003', 'valid', 'export_ready')"
        )
        conn.commit()

    stats = match_service.run_match(1)
    assert stats["already_owned"] == 1
    assert stats["available"] == 2
    assert stats["same_title_different_isbn"] == 1

    with db.db_session() as conn:
        sim_rows = conn.execute(
            "SELECT vendor_book_id FROM book_matches WHERE match_status = 'same_title_different_isbn'"
        ).fetchall()
    assert [r["vendor_book_id"] for r in sim_rows] == [11]


def test_books_matches_and_stats_return_copies_similar_other_projects_and_filters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_migrated_db(tmp_path, monkeypatch)

    with db.db_session() as conn:
        conn.execute(
            "INSERT INTO procurement_projects(id, name, project_type, export_template_type, created_at, updated_at) "
            "VALUES "
            "(1, '114本土文化', 'local_culture', 'local_culture', '', ''), "
            "(2, '114一般圖書', 'general_books', 'general_books', '', ''), "
            "(3, '114偏鄉閱讀', 'local_culture', 'local_culture', '', '')"
        )
        conn.execute(
            "INSERT INTO import_batches(id, project_id, batch_type, original_filename, imported_at) "
            "VALUES "
            "(1, 1, 'vendor_books', 'v1.xlsx', ''), "
            "(2, NULL, 'library_holdings', 'h.xlsx', '')"
        )
        # 3 copies of owned ISBN + 1 holding for similar title
        conn.execute(
            "INSERT INTO library_holdings(batch_id, isbn, isbn_normalized, title, author, publisher, isbn_status) "
            "VALUES "
            "(2, '9789861111111', '9789861111111', '館藏多冊書', '作者一', '出版社一', 'valid'), "
            "(2, '9789861111111', '9789861111111', '館藏多冊書', '作者一', '出版社一', 'valid'), "
            "(2, '9789861111111', '9789861111111', '館藏多冊書', '作者一', '出版社一', 'valid'), "
            "(2, '9789862222222', '9789862222222', '小火車做到了！（精裝）', '華蒂', '東方', 'valid')"
        )
        # 4 vendor books in project 1
        conn.execute(
            "INSERT INTO vendor_books(id, batch_id, title, isbn, isbn_normalized, isbn_status, completeness_status) "
            "VALUES "
            "(101, 1, '館藏多冊書', '9789861111111', '9789861111111', 'valid', 'export_ready'), "
            "(102, 1, '小火車做到了', '9789862222999', '9789862222999', 'valid', 'export_ready'), "
            "(103, 1, '跨案選購書', '9789863333333', '9789863333333', 'valid', 'needs_review'), "
            "(104, 1, '全新可買書', '9789864444444', '9789864444444', 'valid', 'export_ready')"
        )
        # Selections:
        # - project 1 selects 104 (same project -> must NOT appear in other_project_selections)
        # - project 2 selects 9789863333333 (qty 2) and 9789864444444 (qty 0 -> must NOT appear)
        # - project 3 selects 9789863333333 (qty 1)
        conn.execute(
            "INSERT INTO selection_items(project_id, vendor_book_id, selected_quantity, "
            "title, isbn, isbn_normalized, isbn_status, completeness_status, created_at, updated_at) "
            "VALUES "
            "(1, 104, 1, '全新可買書', '9789864444444', '9789864444444', 'valid', 'export_ready', '', ''), "
            "(2, 201, 2, '跨案選購書', '9789863333333', '9789863333333', 'valid', 'export_ready', '', ''), "
            "(2, 202, 0, '零數量書', '9789864444444', '9789864444444', 'valid', 'export_ready', '', ''), "
            "(3, 301, 1, '跨案選購書', '9789863333333', '9789863333333', 'valid', 'export_ready', '', '')"
        )
        conn.commit()

    match_service.run_match(1)

    app.dependency_overrides[require_auth] = lambda: 1
    try:
        client = TestClient(app, raise_server_exceptions=True)

        # All matches
        res = client.get("/api/books/matches", params={"project_id": 1})
        assert res.status_code == 200
        by_id = {b["id"]: b for b in res.json()}
        assert len(by_id) == 4

        # 101: already_owned with 3 copies
        assert by_id[101]["match_status"] == "already_owned"
        assert by_id[101]["holding_copies"] == 3
        assert by_id[101]["similar_holding"] is None
        assert by_id[101]["other_project_selections"] == []

        # 102: available + similar_holding
        assert by_id[102]["match_status"] == "available"
        assert by_id[102]["holding_copies"] == 0
        assert by_id[102]["similar_holding"] == {
            "title": "小火車做到了！（精裝）",
            "author": "華蒂",
            "publisher": "東方",
            "isbn": "9789862222222",
        }
        assert by_id[102]["other_project_selections"] == []

        # 103: available + selected in projects 2 and 3
        assert by_id[103]["match_status"] == "available"
        assert by_id[103]["holding_copies"] == 0
        assert by_id[103]["similar_holding"] is None
        assert by_id[103]["other_project_selections"] == [
            {"project_id": 2, "project_name": "114一般圖書", "has_exported": False},
            {"project_id": 3, "project_name": "114偏鄉閱讀", "has_exported": False},
        ]

        # 104: clean available
        assert by_id[104]["match_status"] == "available"
        assert by_id[104]["holding_copies"] == 0
        assert by_id[104]["similar_holding"] is None
        assert by_id[104]["other_project_selections"] == []

        # Filter: same_title_different_isbn
        res_sim = client.get(
            "/api/books/matches",
            params={"project_id": 1, "match_status": "same_title_different_isbn"},
        )
        assert res_sim.status_code == 200
        assert [b["id"] for b in res_sim.json()] == [102]

        # Filter: other_project_selected
        res_other = client.get(
            "/api/books/matches",
            params={"project_id": 1, "match_status": "other_project_selected"},
        )
        assert res_other.status_code == 200
        assert [b["id"] for b in res_other.json()] == [103]

        # Filter: existing already_owned still works
        res_owned = client.get(
            "/api/books/matches",
            params={"project_id": 1, "match_status": "already_owned"},
        )
        assert res_owned.status_code == 200
        assert [b["id"] for b in res_owned.json()] == [101]

        # Stats endpoint
        res_stats = client.get("/api/books/stats", params={"project_id": 1})
        assert res_stats.status_code == 200
        stats = res_stats.json()
        assert stats["match_status"]["already_owned"] == 1
        assert stats["match_status"]["available"] == 3
        assert stats["same_title_different_isbn_count"] == 1
        assert stats["other_project_duplicate_count"] == 1
    finally:
        app.dependency_overrides.clear()


def test_frontend_duplicate_prevention_markers_present() -> None:
    match_html = Path("app/static/match.html").read_text(encoding="utf-8")
    selection_html = Path("app/static/selection.html").read_text(encoding="utf-8")

    for html in (match_html, selection_html):
        assert 'value="same_title_different_isbn"' in html
        assert 'value="other_project_selected"' in html
        assert "holding_copies" in html
        assert "similar_holding" in html
        assert "other_project_selections" in html
        assert "疑似同名館藏" in html
        assert "他案已選" in html
        assert "esc(sh.title" in html
        assert "esc(p.project_name" in html

    assert "same_title_different_isbn_count" in match_html
    assert "other_project_duplicate_count" in match_html
