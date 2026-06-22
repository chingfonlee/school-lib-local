import io
import sqlite3
import pytest
import openpyxl

from app.services.import_service import confirm_import


SCHEMA = """
CREATE TABLE procurement_projects (
    id INTEGER PRIMARY KEY,
    project_type TEXT NOT NULL
);
CREATE TABLE import_batches (
    id INTEGER PRIMARY KEY,
    project_id INTEGER,
    batch_type TEXT,
    original_filename TEXT,
    profile_id INTEGER,
    imported_by INTEGER,
    imported_at TEXT,
    record_count INTEGER
);
CREATE TABLE vendor_books (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER,
    award_item TEXT,
    vendor_seq TEXT,
    title TEXT,
    author TEXT,
    isbn TEXT,
    isbn_normalized TEXT,
    publish_date TEXT,
    list_price REAL,
    purchase_price REAL,
    publisher TEXT,
    age_range TEXT,
    isbn_status TEXT,
    completeness_status TEXT,
    extra_fields TEXT,
    source_row_number INTEGER,
    raw_row TEXT,
    category TEXT,
    book_type TEXT,
    policy_topic TEXT,
    summary TEXT,
    source_url TEXT,
    recommendation_source TEXT,
    eligibility_label TEXT,
    classification_number TEXT,
    award_notes TEXT
);
CREATE TABLE book_matches (
    id INTEGER PRIMARY KEY,
    vendor_book_id INTEGER,
    holding_id INTEGER
);
"""


class _NoCloseConn:
    """Delegate all attributes to the real conn; close() is a no-op."""
    def __init__(self, conn):
        self._conn = conn

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._conn, name)


@pytest.fixture
def db(monkeypatch):
    real_conn = sqlite3.connect(":memory:")
    real_conn.row_factory = sqlite3.Row
    for stmt in SCHEMA.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            real_conn.execute(stmt)
    real_conn.execute("INSERT INTO procurement_projects VALUES (1, 'general_books')")
    real_conn.commit()

    monkeypatch.setattr(
        "app.services.import_service.get_connection",
        lambda: _NoCloseConn(real_conn),
    )
    monkeypatch.setattr(
        "app.services.import_service.run_match",
        lambda pid: {},
    )

    yield real_conn
    real_conn.close()


def make_xlsx(headers: list, rows: list) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


GENERAL_HEADERS = [
    "書名", "定價", "作者", "出版社",
    "eligible_label", "award_template", "award_notes", "topic", "summary_80_120",
]

MAPPINGS = {
    "title": "書名",
    "list_price": "定價",
    "author": "作者",
    "publisher": "出版社",
    "eligibility_label": "eligible_label",
    "recommendation_source": "award_template",
    "award_notes": "award_notes",
    "policy_topic": "topic",
    "summary": "summary_80_120",
}


class TestConfirmImportGeneralBooks:
    def test_general_books_fields_written_to_vendor_books(self, db):
        xlsx = make_xlsx(
            GENERAL_HEADERS,
            [["台灣故事", "300", "王作者", "好書出版", "必選", "教育部推薦", "精選好書", "本土文化", "這是摘要"]],
        )
        result = confirm_import(
            xlsx, "test.xlsx", project_id=1,
            sheet_name=None, header_row=0,
            mappings=MAPPINGS, extra_field_settings=[],
            user_id=1,
        )
        assert result["record_count"] == 1

        row = db.execute("SELECT * FROM vendor_books").fetchone()
        assert row["eligibility_label"] == "必選"
        assert row["recommendation_source"] == "教育部推薦"
        assert row["award_notes"] == "精選好書"
        assert row["policy_topic"] == "本土文化"
        assert row["summary"] == "這是摘要"

    def test_general_books_completeness_export_ready(self, db):
        xlsx = make_xlsx(
            GENERAL_HEADERS,
            [["台灣故事", "300", "王作者", "好書出版", "必選", "教育部推薦", "", "", ""]],
        )
        confirm_import(
            xlsx, "test.xlsx", project_id=1,
            sheet_name=None, header_row=0,
            mappings=MAPPINGS, extra_field_settings=[],
            user_id=1,
        )
        row = db.execute("SELECT completeness_status FROM vendor_books").fetchone()
        assert row["completeness_status"] == "export_ready"

    def test_general_books_completeness_missing_eligibility(self, db):
        xlsx = make_xlsx(
            GENERAL_HEADERS,
            [["台灣故事", "300", "王作者", "好書出版", "", "教育部推薦", "", "", ""]],
        )
        confirm_import(
            xlsx, "test.xlsx", project_id=1,
            sheet_name=None, header_row=0,
            mappings=MAPPINGS, extra_field_settings=[],
            user_id=1,
        )
        row = db.execute("SELECT completeness_status FROM vendor_books").fetchone()
        assert row["completeness_status"] == "missing_required"

    def test_general_books_completeness_needs_review_missing_author(self, db):
        xlsx = make_xlsx(
            GENERAL_HEADERS,
            [["台灣故事", "300", "", "好書出版", "必選", "教育部推薦", "", "", ""]],
        )
        confirm_import(
            xlsx, "test.xlsx", project_id=1,
            sheet_name=None, header_row=0,
            mappings=MAPPINGS, extra_field_settings=[],
            user_id=1,
        )
        row = db.execute("SELECT completeness_status FROM vendor_books").fetchone()
        assert row["completeness_status"] == "needs_review"

    def test_blank_and_total_rows_not_imported(self, db):
        xlsx = make_xlsx(
            GENERAL_HEADERS,
            [
                ["台灣故事", "300", "王作者", "好書出版", "必選", "教育部推薦", "", "", ""],
                ["", "", "", "", "", "", "", "", ""],
                ["合計", "300", "", "", "", "", "", "", ""],
            ],
        )
        result = confirm_import(
            xlsx, "test.xlsx", project_id=1,
            sheet_name=None, header_row=0,
            mappings=MAPPINGS, extra_field_settings=[],
            user_id=1,
        )
        assert result["record_count"] == 1
        assert result["skipped_count"] == 2
