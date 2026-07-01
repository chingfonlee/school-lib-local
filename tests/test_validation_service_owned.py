"""Tests for check_export_readiness with force_owned already_owned items."""

import json
import sqlite3
from unittest.mock import patch

import pytest

from app.services.validation_service import check_export_readiness

_SCHEMA = """
CREATE TABLE procurement_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_type TEXT NOT NULL DEFAULT 'local_culture'
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
    project_id INTEGER NOT NULL,
    vendor_book_id INTEGER,
    selected_quantity INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    title TEXT,
    author TEXT,
    publisher TEXT,
    isbn TEXT,
    isbn_normalized TEXT,
    isbn_status TEXT DEFAULT 'valid',
    publish_date TEXT,
    list_price REAL DEFAULT 100,
    purchase_price REAL DEFAULT 80,
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
    updated_at TEXT NOT NULL DEFAULT ''
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
    conn.execute("INSERT INTO procurement_projects(project_type) VALUES ('local_culture')")
    conn.commit()
    yield conn
    conn.close()


def _insert_item(conn, project_id, vendor_book_id, match_status, user_overrides=None, title="測試書"):
    conn.execute(
        "INSERT INTO selection_items"
        "(project_id, vendor_book_id, selected_quantity, title, isbn, list_price, "
        "match_status_at_selection, user_overrides, completeness_status) "
        "VALUES (?, ?, 1, ?, '9781234567890', 100, ?, ?, 'export_ready')",
        (
            project_id,
            vendor_book_id,
            title,
            match_status,
            json.dumps(user_overrides, ensure_ascii=False) if user_overrides else None,
        ),
    )
    conn.commit()


def test_force_owned_already_owned_can_export(db):
    _insert_item(db, 1, 10, "already_owned", {"force_owned": True})

    wrapped = _NoClose(db)
    with patch("app.services.validation_service.get_connection", return_value=wrapped):
        result = check_export_readiness(1, "list_price")

    item = next(d for d in result["details"] if d["vendor_book_id"] == 10)
    assert item["can_export"] is True
    assert item["match_status"] == "already_owned"


def test_unconfirmed_already_owned_cannot_export(db):
    _insert_item(db, 1, 11, "already_owned", user_overrides=None)

    wrapped = _NoClose(db)
    with patch("app.services.validation_service.get_connection", return_value=wrapped):
        result = check_export_readiness(1, "list_price")

    item = next(d for d in result["details"] if d["vendor_book_id"] == 11)
    assert item["can_export"] is False
    assert item["match_status"] == "already_owned"


def test_available_book_unaffected(db):
    _insert_item(db, 1, 12, "available", user_overrides=None)

    wrapped = _NoClose(db)
    with patch("app.services.validation_service.get_connection", return_value=wrapped):
        result = check_export_readiness(1, "list_price")

    item = next(d for d in result["details"] if d["vendor_book_id"] == 12)
    # available book with no blocking fields → can_export True
    assert item["can_export"] is True
    assert item["match_status"] == "available"


def test_already_owned_count_not_incremented_for_force_owned(db):
    _insert_item(db, 1, 13, "already_owned", {"force_owned": True})
    _insert_item(db, 1, 14, "already_owned", user_overrides=None, title="未確認館藏書")

    wrapped = _NoClose(db)
    with patch("app.services.validation_service.get_connection", return_value=wrapped):
        result = check_export_readiness(1, "list_price")

    # Both count toward already_owned_count regardless of force_owned
    assert result["already_owned"] == 2
    force_item = next(d for d in result["details"] if d["vendor_book_id"] == 13)
    unconfirmed_item = next(d for d in result["details"] if d["vendor_book_id"] == 14)
    assert force_item["can_export"] is True
    assert unconfirmed_item["can_export"] is False
