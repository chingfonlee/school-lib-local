"""Tests for admin template save endpoint security and validation."""
import sqlite3
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from app.main import app
from app.auth import require_auth
import app.routers.admin as admin_mod


_FULL_LOCAL_CULTURE = {
    "sort_order": "A", "title": "B", "author": "C",
    "publisher": "D", "isbn": "E", "quantity": "F",
    "price": "G", "subtotal": "H", "award_item": "I", "notes": "J",
}

_SAVE_BASE: dict = {
    "project_type": "local_culture",
    "tmp_path": "",           # filled per test
    "original_filename": "template.xlsx",
    "sheet_name": "Sheet1",
    "header_row": 4,
    "data_start_row": 6,
    "max_rows": 50,
    "school_name_cell": "A3",
    "approved_budget_cell": "E3",
    "column_mappings": _FULL_LOCAL_CULTURE,
}


@pytest.fixture
def admin_tmp(monkeypatch, tmp_path):
    """
    Fixture:
    - Redirects _TMP_DIR to a temp dir so path-traversal tests are deterministic.
    - Bypasses require_auth.
    - Yields (client, allowed_tmp_dir, other_tmp_dir).
    """
    allowed = tmp_path / "00_source" / ".tmp"
    allowed.mkdir(parents=True)
    monkeypatch.setattr(admin_mod, "_TMP_DIR", allowed)

    app.dependency_overrides[require_auth] = lambda: 1
    client = TestClient(app, raise_server_exceptions=True)
    yield client, allowed, tmp_path
    app.dependency_overrides.clear()


class _NoClose:
    """Wrap a sqlite3 connection so close() is a no-op (keep alive for multiple calls)."""
    def __init__(self, c):
        self._c = c
    def close(self):
        pass
    def commit(self):
        self._c.commit()
    def execute(self, *a, **kw):
        return self._c.execute(*a, **kw)
    def __getattr__(self, name):
        return getattr(self._c, name)


@pytest.fixture
def admin_db(monkeypatch):
    """In-memory export_templates DB patched into admin router."""
    real_conn = sqlite3.connect(":memory:", check_same_thread=False)
    real_conn.row_factory = sqlite3.Row
    real_conn.execute("""CREATE TABLE export_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, project_type TEXT,
        template_file_path TEXT, sheet_name TEXT,
        header_row INTEGER, data_start_row INTEGER, max_rows INTEGER,
        school_name_cell TEXT, approved_budget_cell TEXT,
        column_mappings TEXT, created_at TEXT, updated_at TEXT
    )""")
    real_conn.commit()
    monkeypatch.setattr(admin_mod, "get_connection", lambda: _NoClose(real_conn))
    yield real_conn
    real_conn.close()


# ── 副檔名驗證 ─────────────────────────────────────────────────────────────


def test_save_rejects_non_xlsx_extension(admin_tmp):
    client, allowed, _ = admin_tmp
    body = {**_SAVE_BASE, "original_filename": "evil.csv"}
    resp = client.post("/api/admin/templates/save", json=body)
    assert resp.status_code == 400
    assert "xlsx" in resp.json()["detail"]


def test_save_rejects_double_extension(admin_tmp):
    """Filenames like 'template.xlsx.bat' must be rejected."""
    client, allowed, _ = admin_tmp
    body = {**_SAVE_BASE, "original_filename": "template.xlsx.bat"}
    resp = client.post("/api/admin/templates/save", json=body)
    assert resp.status_code == 400


# ── 路徑穿越驗證 ───────────────────────────────────────────────────────────


def test_save_rejects_path_outside_tmp(admin_tmp):
    """tmp_path pointing outside allowed dir returns 400."""
    client, allowed, outer = admin_tmp
    evil = outer / "evil.xlsx"   # sibling of allowed dir, not inside it
    evil.write_bytes(b"data")
    body = {**_SAVE_BASE, "tmp_path": str(evil)}
    resp = client.post("/api/admin/templates/save", json=body)
    assert resp.status_code == 400
    assert "暫存路徑" in resp.json()["detail"]


def test_save_rejects_absolute_system_path(admin_tmp):
    """Absolute path to a system location returns 400 even if file might exist."""
    client, _, _ = admin_tmp
    # Use a path clearly outside the allowed tmp dir
    body = {**_SAVE_BASE, "tmp_path": "/etc/passwd"}
    resp = client.post("/api/admin/templates/save", json=body)
    # Must fail at path-traversal check (400), not at file-not-found (also 400)
    assert resp.status_code == 400
    assert "暫存路徑" in resp.json()["detail"]


# ── 必填欄位驗證 ───────────────────────────────────────────────────────────


def test_save_rejects_missing_required_fields(admin_tmp):
    """column_mappings missing required fields returns 400."""
    client, allowed, _ = admin_tmp
    xlsx = allowed / "abc_test.xlsx"
    xlsx.write_bytes(b"fake xlsx")
    incomplete = {"sort_order": "A", "title": "B"}   # many required fields absent
    body = {**_SAVE_BASE, "tmp_path": str(xlsx), "column_mappings": incomplete}
    resp = client.post("/api/admin/templates/save", json=body)
    assert resp.status_code == 400
    assert "必填欄位" in resp.json()["detail"]


def test_save_error_names_missing_fields(admin_tmp):
    """400 detail should name the missing required field(s)."""
    client, allowed, _ = admin_tmp
    xlsx = allowed / "abc2_test.xlsx"
    xlsx.write_bytes(b"fake xlsx")
    # All required except 'title'
    mapping = {k: v for k, v in _FULL_LOCAL_CULTURE.items() if k != "title"}
    body = {**_SAVE_BASE, "tmp_path": str(xlsx), "column_mappings": mapping}
    resp = client.post("/api/admin/templates/save", json=body)
    assert resp.status_code == 400
    assert "書名" in resp.json()["detail"]   # FIELD_LABELS["title"] = "書名"


# ── 穩定目的路徑：不同 project_type 不互相覆蓋 ───────────────────────────


def test_save_stable_path_per_project_type(admin_tmp, admin_db, monkeypatch, tmp_path):
    """
    Two different project_types with the same original_filename must be saved
    to distinct paths (00_source/templates/{project_type}.xlsx).
    """
    client, allowed, outer = admin_tmp

    moved: dict[str, str] = {}

    def mock_move(src, dst):
        moved[dst] = src

    monkeypatch.setattr(admin_mod.shutil, "move", mock_move)

    # Dest dir must exist (normally created by mkdir in save_template)
    dest_dir = Path("00_source") / "templates"
    dest_dir.mkdir(parents=True, exist_ok=True)

    for project_type, mapping in [
        ("local_culture",    _FULL_LOCAL_CULTURE),
        ("local_culture_jh", _FULL_LOCAL_CULTURE),
    ]:
        xlsx = allowed / f"same_name.xlsx"
        xlsx.write_bytes(b"fake xlsx")
        body = {
            **_SAVE_BASE,
            "project_type": project_type,
            "tmp_path": str(xlsx),
            "original_filename": "same_name.xlsx",
            "column_mappings": mapping,
        }
        resp = client.post("/api/admin/templates/save", json=body)
        assert resp.status_code == 200, resp.text

    paths = [Path(p).as_posix() for p in moved.keys()]
    assert len(paths) == 2, f"expected 2 distinct moves, got: {paths}"
    assert paths[0] != paths[1], "same-name templates overwrote each other"
    assert any("local_culture.xlsx" in p and "local_culture_jh" not in p for p in paths)
    assert any("local_culture_jh.xlsx" in p for p in paths)
