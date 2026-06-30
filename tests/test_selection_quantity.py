"""Tests for PATCH /api/selections/{id}/quantity endpoint."""

import json
import sqlite3

import pytest
from starlette.testclient import TestClient

from app.main import app
from app.auth import require_auth


_SCHEMA = [
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
    """CREATE TABLE selection_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER REFERENCES procurement_projects(id),
        vendor_book_id INTEGER,
        selected_quantity INTEGER NOT NULL DEFAULT 1,
        notes TEXT,
        user_overrides TEXT,
        list_price REAL,
        purchase_price REAL,
        created_by INTEGER,
        created_at TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT ''
    )""",
]


class _NoCloseConn:
    def __init__(self, conn):
        self._conn = conn

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._conn, name)


@pytest.fixture
def qty_db(monkeypatch):
    real_conn = sqlite3.connect(":memory:", check_same_thread=False)
    real_conn.row_factory = sqlite3.Row
    for stmt in _SCHEMA:
        real_conn.execute(stmt)
    real_conn.execute("INSERT INTO procurement_projects(name) VALUES ('測試')")
    real_conn.execute(
        "INSERT INTO selection_items(project_id, vendor_book_id, selected_quantity, notes, user_overrides) "
        "VALUES (1, 10, 1, '測試備註', '{\"list_price\": \"99\"}')"
    )
    real_conn.commit()

    wrapped = _NoCloseConn(real_conn)
    monkeypatch.setattr("app.services.selection_service.get_connection", lambda: wrapped)
    app.dependency_overrides[require_auth] = lambda: 1
    yield real_conn, TestClient(app, raise_server_exceptions=True)
    app.dependency_overrides.clear()
    real_conn.close()


def test_patch_quantity_updates_selected_quantity(qty_db):
    conn, client = qty_db
    r = client.patch("/api/selections/1/quantity", json={"quantity": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["selection_id"] == 1
    assert body["selected_quantity"] == 3
    row = conn.execute("SELECT selected_quantity FROM selection_items WHERE id=1").fetchone()
    assert row["selected_quantity"] == 3


def test_patch_quantity_does_not_clear_notes(qty_db):
    conn, client = qty_db
    client.patch("/api/selections/1/quantity", json={"quantity": 2})
    row = conn.execute("SELECT notes FROM selection_items WHERE id=1").fetchone()
    assert row["notes"] == "測試備註"


def test_patch_quantity_does_not_clear_user_overrides(qty_db):
    conn, client = qty_db
    client.patch("/api/selections/1/quantity", json={"quantity": 2})
    row = conn.execute("SELECT user_overrides FROM selection_items WHERE id=1").fetchone()
    data = json.loads(row["user_overrides"])
    assert data.get("list_price") == "99"


def test_patch_quantity_zero_returns_422(qty_db):
    _, client = qty_db
    r = client.patch("/api/selections/1/quantity", json={"quantity": 0})
    assert r.status_code == 422


def test_patch_quantity_negative_returns_422(qty_db):
    _, client = qty_db
    r = client.patch("/api/selections/1/quantity", json={"quantity": -1})
    assert r.status_code == 422


def test_patch_quantity_not_found_returns_404(qty_db):
    _, client = qty_db
    r = client.patch("/api/selections/999/quantity", json={"quantity": 1})
    assert r.status_code == 404
