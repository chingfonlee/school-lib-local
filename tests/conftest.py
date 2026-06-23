import sqlite3
import pytest
from starlette.testclient import TestClient

from app.main import app
from app.auth import require_auth


class _NoCloseConn:
    """sqlite3 connection wrapper that ignores close() so the fixture holds the conn alive."""
    def __init__(self, conn):
        self._conn = conn

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._conn, name)


# Minimal schema shared across delete/backup tests.
# Mirrors the real schema for the tables used by the delete and backup routers.
_TEST_SCHEMA = [
    """CREATE TABLE procurement_projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        project_type TEXT NOT NULL DEFAULT 'local_culture',
        budget_amount REAL,
        export_template_type TEXT NOT NULL DEFAULT 'local_culture',
        price_field TEXT NOT NULL DEFAULT 'purchase_price',
        subtotal_mode TEXT NOT NULL DEFAULT 'quantity_times_purchase_price',
        created_at TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT ''
    )""",
    """CREATE TABLE import_batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER REFERENCES procurement_projects(id),
        batch_type TEXT NOT NULL DEFAULT 'vendor_books',
        original_filename TEXT NOT NULL DEFAULT '',
        profile_id INTEGER,
        imported_by INTEGER,
        imported_at TEXT NOT NULL DEFAULT '',
        record_count INTEGER,
        notes TEXT
    )""",
    """CREATE TABLE vendor_books (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id INTEGER REFERENCES import_batches(id),
        title TEXT,
        isbn TEXT
    )""",
    """CREATE TABLE library_holdings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id INTEGER NOT NULL REFERENCES import_batches(id),
        isbn TEXT,
        isbn_normalized TEXT,
        title TEXT,
        author TEXT,
        publisher TEXT,
        publish_year TEXT,
        price REAL,
        library_record_id TEXT,
        isbn_status TEXT NOT NULL DEFAULT 'valid',
        raw_row TEXT
    )""",
    """CREATE TABLE book_matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_book_id INTEGER REFERENCES vendor_books(id),
        holding_id INTEGER REFERENCES library_holdings(id)
    )""",
    """CREATE TABLE selection_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER REFERENCES procurement_projects(id),
        vendor_book_id INTEGER,
        selected_quantity INTEGER DEFAULT 1
    )""",
    """CREATE TABLE export_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER REFERENCES procurement_projects(id),
        exported_at TEXT NOT NULL DEFAULT ''
    )""",
    """CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE
    )""",
    """CREATE TABLE schema_migrations (
        version TEXT PRIMARY KEY,
        applied_at TEXT NOT NULL DEFAULT ''
    )""",
]


@pytest.fixture
def project_db(monkeypatch):
    """In-memory SQLite DB with test data; patches get_connection in projects router."""
    real_conn = sqlite3.connect(":memory:", check_same_thread=False)
    real_conn.row_factory = sqlite3.Row
    real_conn.execute("PRAGMA foreign_keys = ON")
    for stmt in _TEST_SCHEMA:
        real_conn.execute(stmt)
    real_conn.execute(
        "INSERT INTO procurement_projects(name, project_type) VALUES ('測試專案', 'local_culture')"
    )
    real_conn.execute(
        "INSERT INTO procurement_projects(name, project_type) VALUES ('另一專案', 'local_culture')"
    )
    real_conn.commit()

    wrapped = _NoCloseConn(real_conn)
    monkeypatch.setattr("app.routers.projects.get_connection", lambda: wrapped)
    yield real_conn
    real_conn.close()


@pytest.fixture
def auth_client(project_db):
    """TestClient with require_auth overridden to return user_id=1."""
    app.dependency_overrides[require_auth] = lambda: 1
    client = TestClient(app, raise_server_exceptions=True)
    yield client
    app.dependency_overrides.clear()
