from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any
import uuid

from app.config import get_config
from app.logging_config import get_logger

BASE_DIR = Path(__file__).resolve().parent.parent
DB_TIMEOUT_SECONDS = 10.0
BUSY_TIMEOUT_MS = 10000
PRE_MIGRATION_KEEP = 5

logger = get_logger("database")


def get_db_path() -> str:
    return get_config().database_path


def get_connection() -> sqlite3.Connection:
    path = get_db_path()
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=DB_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    return conn


@contextmanager
def db_session(conn_factory: Callable[[], Any] | None = None) -> Iterator[Any]:
    """Yield a SQLite connection, rolling back on error and always closing."""
    conn = (conn_factory or get_connection)()
    try:
        yield conn
    except Exception:
        try:
            conn.rollback()
        except Exception:
            logger.warning("SQLite rollback failed during exception handling", exc_info=True)
        raise
    finally:
        conn.close()


def prune_old_files(directory: Path, pattern: str, keep: int) -> None:
    """Keep the newest `keep` files matching `pattern` by name order, deleting older ones."""
    if keep < 0 or not directory.is_dir():
        return
    matched = sorted(directory.glob(pattern))
    if len(matched) <= keep:
        return
    for old_file in matched[: len(matched) - keep]:
        try:
            old_file.unlink(missing_ok=True)
        except Exception:
            logger.warning("Failed to remove old backup file: %s", old_file, exc_info=True)


def _backup_before_migration(db_path: str) -> Path | None:
    if db_path == ":memory:":
        return None
    src_path = Path(db_path)
    if not src_path.is_file() or src_path.stat().st_size == 0:
        return None

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    backup_path = src_path.parent / f"pre_migration_{ts}_{suffix}.db"

    src: sqlite3.Connection | None = None
    dst: sqlite3.Connection | None = None
    try:
        src = sqlite3.connect(str(src_path), timeout=DB_TIMEOUT_SECONDS)
        dst = sqlite3.connect(str(backup_path), timeout=DB_TIMEOUT_SECONDS)
        src.backup(dst)
    finally:
        if dst is not None:
            dst.close()
        if src is not None:
            src.close()

    prune_old_files(src_path.parent, "pre_migration_*.db", PRE_MIGRATION_KEEP)
    logger.info("Created pre-migration backup: %s", backup_path)
    return backup_path


def run_migrations(migrations_dir: Path | None = None) -> None:
    mig_dir = migrations_dir if migrations_dir is not None else BASE_DIR / "migrations"
    if not mig_dir.is_dir():
        logger.error("Migrations directory not found: %s", mig_dir)
        raise FileNotFoundError(f"找不到 migrations 目錄：{mig_dir}")

    sql_files = sorted(mig_dir.glob("*.sql"))

    with db_session(get_connection) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        conn.commit()

        applied = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations").fetchall()}
        pending_files = [f for f in sql_files if f.stem not in applied]

        if not pending_files:
            return

        _backup_before_migration(get_db_path())

        for sql_file in pending_files:
            version = sql_file.stem
            logger.info("Applying migration: %s", version)
            try:
                sql = sql_file.read_text(encoding="utf-8")
                conn.executescript(sql)
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (version, datetime.now(timezone.utc).isoformat()),
                )
                conn.commit()
            except Exception:
                logger.exception("Migration failed: %s", version)
                raise


def ensure_initial_data() -> None:
    from passlib.hash import bcrypt

    cfg = get_config()
    now = datetime.now(timezone.utc).isoformat()

    with db_session(get_connection) as conn:
        user = conn.execute("SELECT id FROM users LIMIT 1").fetchone()
        if user is None:
            pw_hash = bcrypt.hash(cfg.default_admin_password)
            conn.execute(
                "INSERT INTO users(username, password_hash, display_name, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (cfg.default_admin_username, pw_hash, "管理員", now, now),
            )

        project = conn.execute("SELECT id FROM procurement_projects LIMIT 1").fetchone()
        if project is None:
            conn.execute(
                "INSERT INTO procurement_projects"
                "(name, project_type, export_template_type, price_field, subtotal_mode, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    cfg.default_project_name,
                    cfg.default_project_type,
                    cfg.default_project_type,
                    cfg.default_price_field,
                    cfg.default_subtotal_mode,
                    now,
                    now,
                ),
            )

        for tmpl in cfg.export_templates:
            col_map = tmpl.get("column_mappings", {})
            col_map_json = json.dumps(col_map, ensure_ascii=False) if isinstance(col_map, dict) else str(col_map)
            conn.execute(
                "INSERT OR IGNORE INTO export_templates"
                "(name, project_type, template_file_path, sheet_name, header_row, data_start_row, "
                "max_rows, school_name_cell, approved_budget_cell, column_mappings, "
                "created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    tmpl["name"],
                    tmpl["project_type"],
                    tmpl["template_file_path"],
                    tmpl.get("sheet_name") or None,
                    tmpl.get("header_row", 4),
                    tmpl.get("data_start_row", 6),
                    tmpl.get("max_rows", 50),
                    tmpl.get("school_name_cell", "A3"),
                    tmpl.get("approved_budget_cell", "E3"),
                    col_map_json,
                    now,
                    now,
                ),
            )

        conn.commit()
