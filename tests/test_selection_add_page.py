"""Tests for bulk_add_selections service function."""

import json
import sqlite3
from unittest.mock import patch

import pytest

from app.services.selection_service import bulk_add_selections

_SCHEMA = """
CREATE TABLE procurement_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL DEFAULT '',
    project_type TEXT NOT NULL DEFAULT 'local_culture'
);

CREATE TABLE import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    batch_type TEXT NOT NULL DEFAULT 'vendor_books',
    original_filename TEXT NOT NULL DEFAULT 'test.xlsx',
    profile_id INTEGER,
    imported_by INTEGER,
    imported_at TEXT NOT NULL DEFAULT '',
    record_count INTEGER,
    notes TEXT
);

CREATE TABLE vendor_books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL,
    title TEXT,
    author TEXT,
    isbn TEXT,
    isbn_normalized TEXT,
    isbn_status TEXT NOT NULL DEFAULT 'valid',
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
    completeness_status TEXT NOT NULL DEFAULT 'unknown',
    user_overrides TEXT,
    extra_fields TEXT,
    raw_row TEXT,
    source_row_number TEXT
);

CREATE TABLE book_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor_book_id INTEGER,
    holding_id INTEGER,
    match_status TEXT NOT NULL DEFAULT 'available',
    matched_at TEXT NOT NULL DEFAULT '',
    batch_run_id TEXT NOT NULL DEFAULT ''
);

CREATE TABLE selection_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    vendor_book_id INTEGER,
    source_batch_id INTEGER,
    source_original_filename TEXT,
    source_row_number TEXT,
    selected_quantity INTEGER NOT NULL DEFAULT 0,
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
    completeness_status TEXT NOT NULL DEFAULT 'unknown',
    match_status_at_selection TEXT,
    holding_id_at_selection INTEGER,
    user_overrides TEXT,
    extra_fields TEXT,
    raw_row TEXT,
    created_by INTEGER,
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    UNIQUE(project_id, vendor_book_id)
);

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE DEFAULT 'admin'
);
"""


class _NoClose:
    def __init__(self, conn):
        self._conn = conn

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._conn, name)


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.execute("INSERT INTO procurement_projects(name) VALUES ('測試專案')")
    conn.execute("INSERT INTO users(username) VALUES ('admin')")
    conn.execute("INSERT INTO import_batches(project_id) VALUES (1)")
    conn.execute(
        "INSERT INTO vendor_books(batch_id, title, completeness_status) VALUES (1, '可採購書A', 'export_ready')"
    )
    conn.execute(
        "INSERT INTO vendor_books(batch_id, title, completeness_status) VALUES (1, '可採購書B', 'export_ready')"
    )
    conn.execute(
        "INSERT INTO vendor_books(batch_id, title, completeness_status) VALUES (1, '已館藏書C', 'export_ready')"
    )
    conn.execute(
        "INSERT INTO book_matches(vendor_book_id, match_status, batch_run_id) "
        "VALUES (1, 'available', 'r1')"
    )
    conn.execute(
        "INSERT INTO book_matches(vendor_book_id, match_status, batch_run_id) "
        "VALUES (2, 'available', 'r1')"
    )
    conn.execute(
        "INSERT INTO book_matches(vendor_book_id, match_status, batch_run_id) "
        "VALUES (3, 'already_owned', 'r1')"
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def patched_conn(db):
    wrapped = _NoClose(db)
    with patch("app.services.selection_service.get_connection", return_value=wrapped):
        yield db


def test_bulk_add_available_books(patched_conn):
    result = bulk_add_selections(1, [
        {"vendor_book_id": 1, "force_owned": False},
        {"vendor_book_id": 2, "force_owned": False},
    ], user_id=1)

    assert result["added"] == 2
    assert result["skipped"] == 0

    rows = patched_conn.execute(
        "SELECT vendor_book_id, user_overrides FROM selection_items WHERE project_id = 1"
    ).fetchall()
    assert len(rows) == 2
    for row in rows:
        assert row["user_overrides"] is None


def test_bulk_add_force_owned(patched_conn):
    result = bulk_add_selections(1, [
        {"vendor_book_id": 3, "force_owned": True},
    ], user_id=1)

    assert result["added"] == 1
    assert result["skipped"] == 0

    row = patched_conn.execute(
        "SELECT user_overrides FROM selection_items WHERE vendor_book_id = 3"
    ).fetchone()
    assert row is not None
    overrides = json.loads(row["user_overrides"])
    assert overrides.get("force_owned") is True


def test_bulk_add_already_in_list_skipped(patched_conn):
    # Pre-insert book 1 to simulate it already being in the list
    patched_conn.execute(
        "INSERT INTO selection_items(project_id, vendor_book_id, selected_quantity, created_at, updated_at) "
        "VALUES (1, 1, 1, '', '')"
    )
    patched_conn.commit()

    result = bulk_add_selections(1, [
        {"vendor_book_id": 1, "force_owned": False},
        {"vendor_book_id": 2, "force_owned": False},
    ], user_id=1)

    assert result["added"] == 1
    assert result["skipped"] == 1

    # Existing record should be untouched
    row = patched_conn.execute(
        "SELECT selected_quantity FROM selection_items WHERE vendor_book_id = 1"
    ).fetchone()
    assert row["selected_quantity"] == 1


def test_bulk_add_mixed(patched_conn):
    # Pre-insert book 2
    patched_conn.execute(
        "INSERT INTO selection_items(project_id, vendor_book_id, selected_quantity, created_at, updated_at) "
        "VALUES (1, 2, 1, '', '')"
    )
    patched_conn.commit()

    result = bulk_add_selections(1, [
        {"vendor_book_id": 1, "force_owned": False},   # new available
        {"vendor_book_id": 2, "force_owned": False},   # already in list → skip
        {"vendor_book_id": 3, "force_owned": True},    # new already_owned
    ], user_id=1)

    assert result["added"] == 2
    assert result["skipped"] == 1

    owned_row = patched_conn.execute(
        "SELECT user_overrides FROM selection_items WHERE vendor_book_id = 3"
    ).fetchone()
    assert json.loads(owned_row["user_overrides"]).get("force_owned") is True


def test_bulk_add_nonexistent_book_skipped(patched_conn):
    result = bulk_add_selections(1, [
        {"vendor_book_id": 999, "force_owned": False},
        {"vendor_book_id": 1, "force_owned": False},
    ], user_id=1)

    assert result["added"] == 1
    assert result["skipped"] == 1
