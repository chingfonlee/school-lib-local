import logging
from pathlib import Path
import sqlite3

import pytest
from starlette.testclient import TestClient

from app import database as db
from app.auth import require_auth
from app.logging_config import LOGGER_NAME, setup_logging
from app.main import app
from app.routers import backup as backup_router
from app.routers import projects as projects_router

EXPECTED_INDEXES = {
    "idx_import_batches_project_id",
    "idx_vendor_books_batch_id",
    "idx_vendor_books_isbn_normalized",
    "idx_library_holdings_batch_id",
    "idx_library_holdings_isbn_normalized",
    "idx_book_matches_vendor_book_id",
    "idx_book_matches_holding_id",
    "idx_selection_items_project_id",
    "idx_export_jobs_project_id",
}


def test_get_connection_pragmas(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(db, "get_db_path", lambda: str(db_file))

    conn = db.get_connection()
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 10000
    finally:
        conn.close()


def test_db_session_closes_and_rolls_back_on_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_file = tmp_path / "session.db"
    monkeypatch.setattr(db, "get_db_path", lambda: str(db_file))

    with db.db_session() as conn:
        conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
        conn.commit()
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")

    with pytest.raises(RuntimeError, match="boom"):
        with db.db_session() as conn2:
            conn2.execute("INSERT INTO items(name) VALUES ('rolled_back')")
            raise RuntimeError("boom")

    with pytest.raises(sqlite3.ProgrammingError):
        conn2.execute("SELECT 1")

    with db.db_session() as conn3:
        count = conn3.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    assert count == 0


def test_run_migrations_enables_wal_creates_indexes_and_backups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_file = tmp_path / "migrated.db"
    monkeypatch.setattr(db, "get_db_path", lambda: str(db_file))

    db.run_migrations()

    with db.db_session() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert str(mode).lower() == "wal"
        indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    assert EXPECTED_INDEXES.issubset(indexes)

    # Re-running with no pending migrations should be idempotent and not create backups.
    before_backups = list(tmp_path.glob("pre_migration_*.db"))
    db.run_migrations()
    after_backups = list(tmp_path.glob("pre_migration_*.db"))
    assert len(after_backups) == len(before_backups)

    # Simulate a new pending migration and verify pre-migration backup + pruning (keep 5).
    for i in range(6):
        (tmp_path / f"pre_migration_20260101_00000{i}_old.db").write_bytes(b"old")

    custom_mig_dir = tmp_path / "migs"
    custom_mig_dir.mkdir()
    (custom_mig_dir / "999_dummy_test.sql").write_text(
        "CREATE TABLE IF NOT EXISTS dummy_migration_check (id INTEGER PRIMARY KEY);\n",
        encoding="utf-8",
    )
    db.run_migrations(migrations_dir=custom_mig_dir)

    kept_backups = sorted(tmp_path.glob("pre_migration_*.db"))
    assert len(kept_backups) == db.PRE_MIGRATION_KEEP


def test_backup_validate_rejects_corrupted_sqlite(tmp_path: Path) -> None:
    corrupt_path = tmp_path / "corrupt.db"
    # Valid SQLite magic header followed by garbage bytes.
    corrupt_path.write_bytes(backup_router.SQLITE_MAGIC + b"\xff" * 4096)

    with pytest.raises(Exception) as exc_info:
        backup_router._validate_sqlite(str(corrupt_path))
    assert getattr(exc_info.value, "status_code", None) == 400


def test_restore_runs_migrations_and_prunes_safety_backups(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    live_db = tmp_path / "live.db"
    old_backup_db = tmp_path / "old_backup.db"

    # Build an "old" backup DB that has migrations 001..007 but NOT 008_add_indexes.
    mig_dir = db.BASE_DIR / "migrations"
    conn = sqlite3.connect(str(old_backup_db))
    conn.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    for sql_file in sorted(mig_dir.glob("*.sql")):
        if sql_file.stem == "008_add_indexes":
            continue
        conn.executescript(sql_file.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, '2026-01-01T00:00:00Z')",
            (sql_file.stem,),
        )
    conn.commit()
    conn.close()

    # Initialize live DB.
    monkeypatch.setattr(db, "get_db_path", lambda: str(live_db))
    monkeypatch.setattr(backup_router, "get_db_path", lambda: str(live_db))
    db.run_migrations()

    # Seed 6 old safety backups to verify pruning keeps at most 5.
    for i in range(6):
        (tmp_path / f"restore_safety_backup_20260101_00000{i}_seed.db").write_bytes(b"old")

    app.dependency_overrides[require_auth] = lambda: 1
    try:
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post(
            "/api/backup/restore",
            files={"file": ("backup.db", old_backup_db.read_bytes(), "application/octet-stream")},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert list(tmp_path.glob("restore_pending_*.db")) == []
    assert len(list(tmp_path.glob("restore_safety_backup_*.db"))) == backup_router.SAFETY_BACKUP_KEEP

    # Verify migration 008 was applied automatically after restore.
    with db.db_session() as verify_conn:
        indexes = {r[0] for r in verify_conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    assert EXPECTED_INDEXES.issubset(indexes)


def test_logging_setup_and_unhandled_exception_handler(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    logger = setup_logging(log_dir=tmp_path)
    handler_count = len(logger.handlers)
    assert handler_count == 2

    # Calling setup_logging() without log_dir should not attach duplicate handlers.
    logger_again = setup_logging()
    assert len(logger_again.handlers) == handler_count

    logger.info("test log message")
    for h in logger.handlers:
        h.flush()

    log_file = tmp_path / "app.log"
    assert log_file.is_file()
    assert "test log message" in log_file.read_text(encoding="utf-8")

    # Smoke test /api/health and global 500 handler via a simulated DB crash.
    def _boom_conn():
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(projects_router, "get_connection", _boom_conn)
    app.dependency_overrides[require_auth] = lambda: 1
    try:
        client = TestClient(app, raise_server_exceptions=False)
        health_resp = client.get("/api/health")
        assert health_resp.status_code == 200
        assert health_resp.json() == {"status": "ok"}

        boom_resp = client.get("/api/projects/")
        assert boom_resp.status_code == 500
        detail = boom_resp.json()["detail"]
        assert "系統發生未預期錯誤" in detail
        assert "data/app.log" in detail
    finally:
        app.dependency_overrides.clear()
        # Close handlers pointing to tmp_path so Windows can clean up tmp_path cleanly.
        target_logger = logging.getLogger(LOGGER_NAME)
        for h in list(target_logger.handlers):
            target_logger.removeHandler(h)
            h.close()
