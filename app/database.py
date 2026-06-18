import json
import sqlite3
import os
from pathlib import Path
from datetime import datetime, timezone

from app.config import get_config


def get_db_path() -> str:
    return get_config().database_path


def get_connection() -> sqlite3.Connection:
    path = get_db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def run_migrations() -> None:
    conn = get_connection()
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    conn.commit()

    migrations_dir = Path("migrations")
    sql_files = sorted(migrations_dir.glob("*.sql"))
    for sql_file in sql_files:
        version = sql_file.stem
        row = conn.execute(
            "SELECT version FROM schema_migrations WHERE version = ?", (version,)
        ).fetchone()
        if row is None:
            sql = sql_file.read_text(encoding="utf-8")
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
    conn.close()


def ensure_initial_data() -> None:
    from passlib.hash import bcrypt
    cfg = get_config()
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()

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
        col_map_json = (
            json.dumps(col_map, ensure_ascii=False)
            if isinstance(col_map, dict)
            else str(col_map)
        )
        conn.execute(
            "INSERT OR IGNORE INTO export_templates"
            "(name, project_type, template_file_path, header_row, data_start_row, "
            "max_rows, school_name_cell, approved_budget_cell, column_mappings, "
            "created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tmpl["name"],
                tmpl["project_type"],
                tmpl["template_file_path"],
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
    conn.close()
