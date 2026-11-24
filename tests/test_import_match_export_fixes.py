import io
import json
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

from app import database as db
from app.services import (
    completeness_service,
    export_service,
    import_service,
    isbn_service,
    selection_service,
    validation_service,
)


def _setup_migrated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(db, "get_db_path", lambda: str(db_file))
    db.run_migrations()
    with db.db_session() as conn:
        conn.execute(
            "INSERT INTO users(id, username, password_hash, display_name, created_at, updated_at) "
            "VALUES (1, 'admin', 'x', '管理員', '', '')"
        )
        conn.commit()
    return db_file


def test_isbn_normalization_fullwidth_nan_and_isbn10_to_13() -> None:
    # Fullwidth digits & hyphens normalize cleanly to ASCII ISBN-13
    assert isbn_service.normalize_isbn("９７８－９８６－４４３－１９９－１") == "9789864431991"
    # ISBN-10 with trailing X / x converts to valid ISBN-13
    assert isbn_service.normalize_isbn("957-33-1724-X") == "9789573317241"
    assert isbn_service.normalize_isbn("957331724x") == "9789573317241"
    assert isbn_service.get_isbn_status("957331724X") == "valid"
    # NaN / inf do not crash and are treated as missing
    assert isbn_service.normalize_isbn(float("nan")) is None
    assert isbn_service.normalize_isbn(float("inf")) is None
    assert isbn_service.get_isbn_status(float("nan")) == "missing"


def test_completeness_general_books_jh_uses_general_rules() -> None:
    book = {
        "title": "國中測試書",
        "list_price": 300,
        "purchase_price": 240,
        "author": "作者",
        "publisher": "出版社",
        "eligibility_label": "",
        "recommendation_source": "",
    }
    assert completeness_service.compute(book, project_type="general_books_jh") == "missing_required"

    book["eligibility_label"] = "必選"
    book["recommendation_source"] = "金鼎獎"
    assert completeness_service.compute(book, project_type="general_books_jh") == "export_ready"


def test_selection_inherits_overrides_recomputes_and_deduplicates_bulk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_migrated_db(tmp_path, monkeypatch)
    with db.db_session() as conn:
        conn.execute(
            "INSERT INTO procurement_projects(id, name, project_type, export_template_type, created_at, updated_at) "
            "VALUES (1, '國中一般', 'general_books_jh', 'general_books_jh', '', '')"
        )
        conn.execute(
            "INSERT INTO import_batches(id, project_id, batch_type, original_filename, imported_at) "
            "VALUES (1, 1, 'vendor_books', 'v.xlsx', '')"
        )
        conn.execute(
            "INSERT INTO vendor_books(id, batch_id, title, isbn, isbn_normalized, isbn_status, "
            "list_price, purchase_price, completeness_status, user_overrides) "
            "VALUES (10, 1, '測試書', '9789864431991', '9789864431991', 'valid', 300, 240, "
            "'missing_required', ?)",
            (json.dumps({"author": "既有作者", "publisher": "既有出版社"}, ensure_ascii=False),),
        )
        conn.commit()

    # Bulk add with duplicate vendor_book_id in the same request only adds once and inherits overrides + force_owned
    res = selection_service.bulk_add_selections(
        1,
        [{"vendor_book_id": 10, "force_owned": True}, {"vendor_book_id": 10, "force_owned": True}],
        user_id=1,
    )
    assert res == {"added": 1, "skipped": 1}

    with db.db_session() as conn:
        si = conn.execute("SELECT * FROM selection_items WHERE vendor_book_id = 10").fetchone()
    ov = json.loads(si["user_overrides"])
    assert ov["author"] == "既有作者"
    assert ov["force_owned"] is True

    # Updating overrides recomputes completeness_status on selection_items
    updated = selection_service.update_selection_overrides(
        si["id"],
        {"eligibility_label": "必選", "recommendation_source": "金鼎獎"},
        user_id=1,
    )
    assert updated["completeness_status"] == "export_ready"
    with db.db_session() as conn:
        status = conn.execute("SELECT completeness_status FROM selection_items WHERE id = ?", (si["id"],)).fetchone()[0]
    assert status == "export_ready"


def test_confirm_import_zero_rows_preserves_existing_books_and_rejects_nan_float(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_migrated_db(tmp_path, monkeypatch)
    assert import_service._to_float("nan") is None
    assert import_service._to_float("inf") is None
    assert import_service._to_float("1,250.5") == 1250.5

    with db.db_session() as conn:
        conn.execute(
            "INSERT INTO procurement_projects(id, name, project_type, export_template_type, created_at, updated_at) "
            "VALUES (1, '測試', 'local_culture', 'local_culture', '', '')"
        )
        conn.execute(
            "INSERT INTO import_batches(id, project_id, batch_type, original_filename, imported_at) "
            "VALUES (1, 1, 'vendor_books', 'old.xlsx', '')"
        )
        conn.execute(
            "INSERT INTO vendor_books(id, batch_id, title, isbn, isbn_normalized, isbn_status) "
            "VALUES (1, 1, '舊書', '9789864431991', '9789864431991', 'valid')"
        )
        conn.commit()

    # Build an Excel with only blank/total rows (0 valid rows)
    buf = io.BytesIO()
    pd.DataFrame([{"書名": "合計", "ISBN": ""}]).to_excel(buf, index=False)
    excel_bytes = buf.getvalue()

    with pytest.raises(ValueError, match="未解析到任何有效書目資料"):
        import_service.confirm_import(
            excel_bytes,
            "empty.xlsx",
            project_id=1,
            sheet_name=None,
            header_row=0,
            mappings={"title": "書名", "isbn": "ISBN"},
            extra_field_settings=[],
            user_id=1,
        )

    # Original vendor book must remain intact (rolled back)
    with db.db_session() as conn:
        count = conn.execute("SELECT COUNT(*) FROM vendor_books").fetchone()[0]
    assert count == 1


def test_detached_selection_detects_new_holdings_and_zero_price_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_migrated_db(tmp_path, monkeypatch)
    with db.db_session() as conn:
        conn.execute(
            "INSERT INTO procurement_projects(id, name, project_type, export_template_type, created_at, updated_at) "
            "VALUES (1, '本土', 'local_culture', 'local_culture', '', '')"
        )
        # Detached selection snapshot (no vendor_book / no book_matches) with price 0
        conn.execute(
            "INSERT INTO selection_items(id, project_id, vendor_book_id, selected_quantity, "
            "title, isbn, isbn_normalized, isbn_status, list_price, purchase_price, "
            "completeness_status, match_status_at_selection, created_at, updated_at) "
            "VALUES (1, 1, 999, 1, '脫鉤書', '9789864431991', '9789864431991', 'valid', "
            "0, 0, 'export_ready', 'available', '', '')"
        )
        # Newly imported holding with matching ISBN
        conn.execute(
            "INSERT INTO import_batches(id, project_id, batch_type, original_filename, imported_at) "
            "VALUES (2, NULL, 'library_holdings', 'h.xlsx', '')"
        )
        conn.execute(
            "INSERT INTO library_holdings(batch_id, isbn, isbn_normalized, title, isbn_status) "
            "VALUES (2, '9789864431991', '9789864431991', '脫鉤書', 'valid')"
        )
        conn.commit()

    check = validation_service.check_export_readiness(1, "purchase_price")
    assert check["already_owned"] == 1
    assert check["missing_required"] == 1
    assert check["details"][0]["match_status"] == "already_owned"
    assert "定價(單價)" in check["details"][0]["missing_blocking_fields"]
    assert check["details"][0]["can_export"] is False


def test_export_preserves_header_without_example_row_writes_notes_override_and_validates_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_migrated_db(tmp_path, monkeypatch)

    # Create a minimal template where data_start_row == header_row + 1 (no example row)
    tmpl_path = tmp_path / "no_example_template.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = "校名："
    headers = ["序號", "書名", "作者", "出版社", "ISBN", "數量", "單價", "小計", "獲獎", "備註"]
    for idx, h in enumerate(headers, start=1):
        ws.cell(row=2, column=idx, value=h)
    wb.save(tmpl_path)
    wb.close()

    col_map = {
        "sort_order": "A",
        "title": "B",
        "author": "C",
        "publisher": "D",
        "isbn": "E",
        "quantity": "F",
        "price": "G",
        "subtotal": "H",
        "award_item": "I",
        "notes": "J",
    }

    with db.db_session() as conn:
        conn.execute(
            "INSERT INTO procurement_projects(id, name, project_type, export_template_type, created_at, updated_at) "
            "VALUES (1, '本土無範例列', 'local_culture', 'local_culture', '', '')"
        )
        conn.execute(
            "INSERT INTO export_templates(name, project_type, template_file_path, header_row, "
            "data_start_row, max_rows, school_name_cell, approved_budget_cell, column_mappings, "
            "created_at, updated_at) VALUES ('t1', 'local_culture', ?, 2, 3, 5, 'A1', '', ?, '', '')",
            (str(tmpl_path), json.dumps(col_map)),
        )
        conn.execute(
            "INSERT INTO selection_items(id, project_id, vendor_book_id, selected_quantity, "
            "title, author, publisher, isbn, isbn_normalized, isbn_status, list_price, purchase_price, "
            "completeness_status, match_status_at_selection, user_overrides, created_at, updated_at) "
            "VALUES (1, 1, 100, 2, '書一', '作者一', '社一', '9789864431991', '9789864431991', 'valid', "
            "300, 200, 'export_ready', 'available', ?, '', '')",
            (json.dumps({"notes": "覆寫備註內容"}, ensure_ascii=False),),
        )
        conn.commit()

    out_dir = tmp_path / "exports"
    settings = export_service.ExportSettings(
        project_id=1,
        school_name="測試國小",
        approved_budget=None,
        price_field="purchase_price",
        subtotal_mode="quantity_times_purchase_price",
        output_dir=str(out_dir),
        exported_by=1,
    )
    job_id = export_service.export_local_culture(settings)
    assert job_id

    exported_files = list(out_dir.glob("*.xlsx"))
    assert len(exported_files) == 1
    out_wb = openpyxl.load_workbook(exported_files[0])
    try:
        out_ws = out_wb.active
        # Header row (row 2) must NOT be cleared!
        assert out_ws["B2"].value == "書名"
        # Row 3 has data and overridden notes
        assert out_ws["B3"].value == "書一"
        assert out_ws["J3"].value == "覆寫備註內容"
    finally:
        out_wb.close()

    # Missing template file raises clear ValueError and leaves no partial file
    tmpl_path.unlink()
    before_count = len(list(out_dir.glob("*.xlsx")))
    with pytest.raises(ValueError, match="找不到匯出範本檔案"):
        export_service.export_local_culture(settings)
    assert len(list(out_dir.glob("*.xlsx"))) == before_count
