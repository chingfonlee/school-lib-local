"""Tests for project delete, backup, and restore API endpoints."""
import io
import sqlite3
import tempfile
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from app.main import app
from app.auth import require_auth


# ---------------------------------------------------------------------------
# delete-preview tests
# ---------------------------------------------------------------------------

def test_delete_preview_returns_expected_keys(auth_client, project_db):
    """delete-preview should return all expected stats keys."""
    project_id = project_db.execute(
        "SELECT id FROM procurement_projects WHERE name='測試專案'"
    ).fetchone()[0]
    resp = auth_client.get(f"/api/projects/{project_id}/delete-preview")
    assert resp.status_code == 200
    data = resp.json()
    for key in ("project_id", "project_name", "selection_count", "export_job_count",
                "import_batch_count", "vendor_book_count", "holding_count"):
        assert key in data, f"missing key: {key}"
    assert data["project_name"] == "測試專案"
    assert data["selection_count"] == 0
    assert data["vendor_book_count"] == 0


def test_delete_preview_counts_related_data(auth_client, project_db):
    """delete-preview should reflect actual related record counts."""
    project_id = project_db.execute(
        "SELECT id FROM procurement_projects WHERE name='測試專案'"
    ).fetchone()[0]
    # Insert related data
    project_db.execute(
        "INSERT INTO import_batches(project_id, batch_type, original_filename, imported_at) "
        "VALUES (?, 'vendor_books', 'test.xlsx', '2026-01-01')", (project_id,)
    )
    batch_id = project_db.execute("SELECT last_insert_rowid()").fetchone()[0]
    project_db.execute(
        "INSERT INTO vendor_books(batch_id, title) VALUES (?, 'Book A')", (batch_id,)
    )
    project_db.execute(
        "INSERT INTO selection_items(project_id, vendor_book_id) VALUES (?, 1)", (project_id,)
    )
    project_db.commit()

    resp = auth_client.get(f"/api/projects/{project_id}/delete-preview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["import_batch_count"] == 1
    assert data["vendor_book_count"] == 1
    assert data["selection_count"] == 1


def test_delete_preview_nonexistent_returns_404(auth_client, project_db):
    resp = auth_client.get("/api/projects/9999/delete-preview")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE project tests
# ---------------------------------------------------------------------------

def test_delete_nonexistent_project_returns_404(auth_client, project_db):
    resp = auth_client.delete("/api/projects/9999")
    assert resp.status_code == 404


def test_delete_project_success(auth_client, project_db):
    """Deleting an existing project returns ok and removes it from the DB."""
    project_id = project_db.execute(
        "SELECT id FROM procurement_projects WHERE name='測試專案'"
    ).fetchone()[0]
    resp = auth_client.delete(f"/api/projects/{project_id}")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    row = project_db.execute(
        "SELECT id FROM procurement_projects WHERE id = ?", (project_id,)
    ).fetchone()
    assert row is None


def test_delete_project_cascades_related_data(auth_client, project_db):
    """Deleting a project removes its batches, vendor_books, selection_items, export_jobs."""
    project_id = project_db.execute(
        "SELECT id FROM procurement_projects WHERE name='測試專案'"
    ).fetchone()[0]

    project_db.execute(
        "INSERT INTO import_batches(project_id, batch_type, original_filename, imported_at) "
        "VALUES (?, 'vendor_books', 'f.xlsx', '2026-01-01')", (project_id,)
    )
    batch_id = project_db.execute("SELECT last_insert_rowid()").fetchone()[0]
    project_db.execute(
        "INSERT INTO vendor_books(batch_id, title) VALUES (?, 'Book A')", (batch_id,)
    )
    vb_id = project_db.execute("SELECT last_insert_rowid()").fetchone()[0]
    project_db.execute(
        "INSERT INTO book_matches(vendor_book_id, holding_id) VALUES (?, NULL)", (vb_id,)
    )
    project_db.execute(
        "INSERT INTO selection_items(project_id, vendor_book_id) VALUES (?, ?)", (project_id, vb_id)
    )
    project_db.execute(
        "INSERT INTO export_jobs(project_id, exported_at) VALUES (?, '2026-01-01')", (project_id,)
    )
    project_db.commit()

    resp = auth_client.delete(f"/api/projects/{project_id}")
    assert resp.status_code == 200

    assert project_db.execute(
        "SELECT COUNT(*) FROM import_batches WHERE project_id = ?", (project_id,)
    ).fetchone()[0] == 0
    assert project_db.execute(
        "SELECT COUNT(*) FROM vendor_books WHERE batch_id = ?", (batch_id,)
    ).fetchone()[0] == 0
    assert project_db.execute(
        "SELECT COUNT(*) FROM selection_items WHERE project_id = ?", (project_id,)
    ).fetchone()[0] == 0
    assert project_db.execute(
        "SELECT COUNT(*) FROM export_jobs WHERE project_id = ?", (project_id,)
    ).fetchone()[0] == 0
    assert project_db.execute(
        "SELECT COUNT(*) FROM book_matches WHERE vendor_book_id = ?", (vb_id,)
    ).fetchone()[0] == 0


def test_delete_project_nullifies_cross_project_holding_references(auth_client, project_db):
    """Deleting a project nullifies book_matches.holding_id from other projects."""
    # Project A has library_holdings; project B has vendor_books matched against them
    proj_a_id = project_db.execute(
        "SELECT id FROM procurement_projects WHERE name='測試專案'"
    ).fetchone()[0]
    proj_b_id = project_db.execute(
        "SELECT id FROM procurement_projects WHERE name='另一專案'"
    ).fetchone()[0]

    # Project A: import batch + library_holdings
    project_db.execute(
        "INSERT INTO import_batches(project_id, batch_type, original_filename, imported_at) "
        "VALUES (?, 'library_holdings', 'h.xlsx', '2026-01-01')", (proj_a_id,)
    )
    batch_a = project_db.execute("SELECT last_insert_rowid()").fetchone()[0]
    project_db.execute(
        "INSERT INTO library_holdings(batch_id, isbn_status) VALUES (?, 'valid')", (batch_a,)
    )
    holding_id = project_db.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Project B: import batch + vendor_books matched against project A's holding
    project_db.execute(
        "INSERT INTO import_batches(project_id, batch_type, original_filename, imported_at) "
        "VALUES (?, 'vendor_books', 'v.xlsx', '2026-01-01')", (proj_b_id,)
    )
    batch_b = project_db.execute("SELECT last_insert_rowid()").fetchone()[0]
    project_db.execute(
        "INSERT INTO vendor_books(batch_id, title) VALUES (?, 'Book B')", (batch_b,)
    )
    vb_id = project_db.execute("SELECT last_insert_rowid()").fetchone()[0]
    project_db.execute(
        "INSERT INTO book_matches(vendor_book_id, holding_id) VALUES (?, ?)", (vb_id, holding_id)
    )
    project_db.commit()

    # Delete project A — should nullify book_matches.holding_id without FK error
    resp = auth_client.delete(f"/api/projects/{proj_a_id}")
    assert resp.status_code == 200

    match = project_db.execute(
        "SELECT holding_id FROM book_matches WHERE vendor_book_id = ?", (vb_id,)
    ).fetchone()
    assert match is not None
    assert match[0] is None  # holding_id nullified


def test_delete_project_does_not_affect_other_projects(auth_client, project_db):
    """Deleting one project leaves other projects intact."""
    proj_a_id = project_db.execute(
        "SELECT id FROM procurement_projects WHERE name='測試專案'"
    ).fetchone()[0]
    proj_b_id = project_db.execute(
        "SELECT id FROM procurement_projects WHERE name='另一專案'"
    ).fetchone()[0]

    resp = auth_client.delete(f"/api/projects/{proj_a_id}")
    assert resp.status_code == 200

    row = project_db.execute(
        "SELECT id FROM procurement_projects WHERE id = ?", (proj_b_id,)
    ).fetchone()
    assert row is not None


# ---------------------------------------------------------------------------
# Backup / restore tests (use real temp-file DB)
# ---------------------------------------------------------------------------

def _make_valid_sqlite_bytes() -> bytes:
    """Create a minimal valid SQLite DB in memory and return its bytes."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp = f.name
    conn = sqlite3.connect(tmp)
    conn.execute("CREATE TABLE procurement_projects (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT '')")
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    Path(tmp).unlink()
    return data


@pytest.fixture
def backup_client(tmp_path, monkeypatch):
    """TestClient with require_auth overridden and get_db_path pointing at a temp DB."""
    db_path = str(tmp_path / "test.db")
    # Create minimal DB at temp path
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE procurement_projects (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT '')")
    conn.commit()
    conn.close()

    monkeypatch.setattr("app.routers.backup.get_db_path", lambda: db_path)
    app.dependency_overrides[require_auth] = lambda: 1
    client = TestClient(app, raise_server_exceptions=True)
    yield client
    app.dependency_overrides.clear()


def test_backup_database_returns_file(backup_client):
    resp = backup_client.get("/api/backup/database")
    assert resp.status_code == 200
    assert "attachment" in resp.headers.get("content-disposition", "")
    assert ".db" in resp.headers.get("content-disposition", "")
    # Response body should start with SQLite magic bytes
    assert resp.content[:16] == b"SQLite format 3\x00"


def test_restore_invalid_file_returns_400(backup_client):
    resp = backup_client.post(
        "/api/backup/restore",
        files={"file": ("not_sqlite.db", b"this is not a sqlite file", "application/octet-stream")},
    )
    assert resp.status_code == 400
    assert "magic bytes" in resp.json()["detail"]


def test_restore_empty_file_returns_400(backup_client):
    resp = backup_client.post(
        "/api/backup/restore",
        files={"file": ("empty.db", b"", "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_restore_missing_tables_returns_400(backup_client, tmp_path):
    """A valid SQLite file that lacks required tables should be rejected."""
    bad_db_path = str(tmp_path / "bad.db")
    conn = sqlite3.connect(bad_db_path)
    conn.execute("CREATE TABLE some_table (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
    data = Path(bad_db_path).read_bytes()

    resp = backup_client.post(
        "/api/backup/restore",
        files={"file": ("bad.db", data, "application/octet-stream")},
    )
    assert resp.status_code == 400
    assert "缺少必要資料表" in resp.json()["detail"]


def test_restore_valid_db_succeeds(backup_client):
    valid_bytes = _make_valid_sqlite_bytes()
    resp = backup_client.post(
        "/api/backup/restore",
        files={"file": ("backup.db", valid_bytes, "application/octet-stream")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "safety_backup_path" in data
    assert "還原成功" in data["message"]
