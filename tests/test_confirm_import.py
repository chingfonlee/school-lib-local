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
    vendor_name TEXT,
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
    award_notes TEXT,
    user_overrides TEXT
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
    "書名",
    "定價",
    "作者",
    "出版社",
    "eligible_label",
    "award_template",
    "award_notes",
    "topic",
    "summary_80_120",
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
            xlsx,
            "test.xlsx",
            project_id=1,
            sheet_name=None,
            header_row=0,
            mappings=MAPPINGS,
            extra_field_settings=[],
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
            xlsx,
            "test.xlsx",
            project_id=1,
            sheet_name=None,
            header_row=0,
            mappings=MAPPINGS,
            extra_field_settings=[],
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
            xlsx,
            "test.xlsx",
            project_id=1,
            sheet_name=None,
            header_row=0,
            mappings=MAPPINGS,
            extra_field_settings=[],
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
            xlsx,
            "test.xlsx",
            project_id=1,
            sheet_name=None,
            header_row=0,
            mappings=MAPPINGS,
            extra_field_settings=[],
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
            xlsx,
            "test.xlsx",
            project_id=1,
            sheet_name=None,
            header_row=0,
            mappings=MAPPINGS,
            extra_field_settings=[],
            user_id=1,
        )
        assert result["record_count"] == 1
        assert result["skipped_count"] == 2


class TestConfirmImportAwardOverrides:
    HEADERS_WITH_AWARD = [
        "獲獎項目",
        "書名",
        "定價",
        "作者",
        "出版社",
        "eligible_label",
        "award_template",
        "award_notes",
    ]
    MAPPINGS_WITH_AWARD = {
        "award_item": "獲獎項目",
        "title": "書名",
        "list_price": "定價",
        "author": "作者",
        "publisher": "出版社",
        "eligibility_label": "eligible_label",
        "recommendation_source": "award_template",
        "award_notes": "award_notes",
    }

    def test_award_overrides_applied_to_matched_and_skipped_for_unmatched(self, db):
        xlsx = make_xlsx(
            self.HEADERS_WITH_AWARD,
            [
                [" 2025年好書大家讀 ", "書A", "300", "作者A", "出版A", "", "", "原始備註A"],
                ["SEL情緒", "書B", "320", "作者B", "出版B", "推薦", "舊來源", "舊備註B"],
                ["未覆寫獎項", "書C", "280", "作者C", "出版C", "必選", "喜閱網", "保留備註C"],
            ],
        )
        overrides = {
            "2025年好書大家讀": {
                "recommendation_source": "好書大家讀",
                "eligibility_label": "推薦",
                "award_notes": "",
            },
            "SEL情緒": {
                "recommendation_source": "學校自選(請備註原因)",
                "eligibility_label": "自選",
                "award_notes": "SEL情緒主題書單",
            },
        }
        result = confirm_import(
            xlsx,
            "vendor.xlsx",
            project_id=1,
            sheet_name=None,
            header_row=0,
            mappings=self.MAPPINGS_WITH_AWARD,
            extra_field_settings=[],
            user_id=1,
            award_overrides=overrides,
        )
        assert result["record_count"] == 3

        rows = {
            r["title"]: dict(r)
            for r in db.execute(
                "SELECT title, award_item, recommendation_source, eligibility_label, "
                "award_notes, completeness_status FROM vendor_books"
            ).fetchall()
        }

        # Matched (with stripped key): original award_item preserved, overridden fields written, completeness updated
        assert rows["書A"]["award_item"] == "2025年好書大家讀"
        assert rows["書A"]["recommendation_source"] == "好書大家讀"
        assert rows["書A"]["eligibility_label"] == "推薦"
        assert rows["書A"]["award_notes"] is None
        assert rows["書A"]["completeness_status"] == "export_ready"

        # Matched conflict override: teacher override replaces raw Excel values
        assert rows["書B"]["award_item"] == "SEL情緒"
        assert rows["書B"]["recommendation_source"] == "學校自選(請備註原因)"
        assert rows["書B"]["eligibility_label"] == "自選"
        assert rows["書B"]["award_notes"] == "SEL情緒主題書單"
        assert rows["書B"]["completeness_status"] == "export_ready"

        # Unmatched row: keeps original mapped fields untouched
        assert rows["書C"]["award_item"] == "未覆寫獎項"
        assert rows["書C"]["recommendation_source"] == "喜閱網"
        assert rows["書C"]["eligibility_label"] == "必選"
        assert rows["書C"]["award_notes"] == "保留備註C"

    def test_zero_valid_rows_rolls_back_with_award_overrides(self, db):
        xlsx_ok = make_xlsx(
            self.HEADERS_WITH_AWARD,
            [["2025年金鼎獎", "既有的書", "300", "作者", "出版社", "推薦", "金鼎獎", ""]],
        )
        confirm_import(
            xlsx_ok,
            "first.xlsx",
            project_id=1,
            sheet_name=None,
            header_row=0,
            mappings=self.MAPPINGS_WITH_AWARD,
            extra_field_settings=[],
            user_id=1,
        )
        xlsx_empty = make_xlsx(self.HEADERS_WITH_AWARD, [["", "", "", "", "", "", "", ""]])
        with pytest.raises(ValueError, match="未解析到任何有效書目資料"):
            confirm_import(
                xlsx_empty,
                "empty.xlsx",
                project_id=1,
                sheet_name=None,
                header_row=0,
                mappings=self.MAPPINGS_WITH_AWARD,
                extra_field_settings=[],
                user_id=1,
                award_overrides={
                    "2025年金鼎獎": {"recommendation_source": "金鼎獎", "eligibility_label": "推薦", "award_notes": ""}
                },
            )
        count = db.execute("SELECT COUNT(*) FROM vendor_books").fetchone()[0]
        assert count == 1
