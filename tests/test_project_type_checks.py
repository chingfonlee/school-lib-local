"""Tests for project_type CHECK constraints across migrations."""

import sqlite3
from pathlib import Path

import pytest

from app.services.export_service import _load_export_template_for_project


MIGRATIONS = [
    "migrations/001_initial_schema.sql",
    "migrations/002_import_export_mapping.sql",
    "migrations/003_selection_snapshot.sql",
    "migrations/004_vendor_classification_fields.sql",
    "migrations/005_expand_project_type_checks.sql",
]


VALID_PROJECT_TYPES = (
    "local_culture",
    "general_books",
    "local_culture_jh",
    "general_books_jh",
)


def _apply_migration(conn: sqlite3.Connection, path: str) -> None:
    conn.executescript(Path(path).read_text(encoding="utf-8"))


def _apply_all_migrations(conn: sqlite3.Connection) -> None:
    for path in MIGRATIONS:
        _apply_migration(conn, path)


def _insert_project(conn: sqlite3.Connection, project_type: str, name: str = "Test") -> None:
    conn.execute(
        "INSERT INTO procurement_projects "
        "(name, project_type, export_template_type, created_at, updated_at) "
        "VALUES (?, ?, ?, '2026-01-01T00:00:00', '2026-01-01T00:00:00')",
        (name, project_type, project_type),
    )


def _insert_export_template(
    conn: sqlite3.Connection, project_type: str, name: str = "template"
) -> None:
    conn.execute(
        "INSERT INTO export_templates "
        "(name, project_type, template_file_path, column_mappings, created_at, updated_at) "
        "VALUES (?, ?, './template.xlsx', '{}', '2026-01-01T00:00:00', '2026-01-01T00:00:00')",
        (name, project_type),
    )


def test_fresh_migrations_accept_all_project_types():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        _apply_all_migrations(conn)

        for project_type in VALID_PROJECT_TYPES:
            _insert_project(conn, project_type, f"project-{project_type}")
            _insert_export_template(conn, project_type, f"template-{project_type}")

        project_count = conn.execute("SELECT COUNT(*) FROM procurement_projects").fetchone()[0]
        template_count = conn.execute("SELECT COUNT(*) FROM export_templates").fetchone()[0]

        assert project_count == len(VALID_PROJECT_TYPES)
        assert template_count == len(VALID_PROJECT_TYPES)
    finally:
        conn.close()


def test_fresh_migrations_reject_invalid_project_types():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        _apply_all_migrations(conn)

        with pytest.raises(sqlite3.IntegrityError):
            _insert_project(conn, "invalid_type", "invalid-project")

        with pytest.raises(sqlite3.IntegrityError):
            _insert_export_template(conn, "invalid_type", "invalid-template")
    finally:
        conn.close()


def _create_old_check_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE procurement_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            project_type TEXT NOT NULL CHECK(project_type IN ('local_culture', 'general_books')),
            budget_amount REAL,
            export_template_type TEXT NOT NULL DEFAULT 'local_culture',
            price_field TEXT NOT NULL DEFAULT 'purchase_price'
                CHECK(price_field IN ('list_price', 'purchase_price')),
            subtotal_mode TEXT NOT NULL DEFAULT 'quantity_times_purchase_price'
                CHECK(subtotal_mode IN ('quantity_times_list_price', 'quantity_times_purchase_price')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE export_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            project_type TEXT NOT NULL CHECK(project_type IN ('local_culture', 'general_books')),
            template_file_path TEXT NOT NULL,
            sheet_name TEXT,
            header_row INTEGER NOT NULL DEFAULT 3,
            data_start_row INTEGER NOT NULL DEFAULT 6,
            max_rows INTEGER NOT NULL DEFAULT 50,
            school_name_cell TEXT NOT NULL DEFAULT 'A3',
            approved_budget_cell TEXT NOT NULL DEFAULT 'E3',
            total_quantity_cell TEXT,
            total_amount_cell TEXT,
            column_mappings TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )


def test_005_migrates_existing_old_check_schema_and_preserves_rows():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        _create_old_check_schema(conn)
        _insert_project(conn, "local_culture", "existing-local")
        _insert_project(conn, "general_books", "existing-general")
        _insert_export_template(conn, "local_culture", "existing-local-template")
        _insert_export_template(conn, "general_books", "existing-general-template")

        _apply_migration(conn, "migrations/005_expand_project_type_checks.sql")

        existing_projects = conn.execute(
            "SELECT name, project_type FROM procurement_projects ORDER BY id"
        ).fetchall()
        existing_templates = conn.execute(
            "SELECT name, project_type FROM export_templates ORDER BY id"
        ).fetchall()

        assert existing_projects == [
            ("existing-local", "local_culture"),
            ("existing-general", "general_books"),
        ]
        assert existing_templates == [
            ("existing-local-template", "local_culture"),
            ("existing-general-template", "general_books"),
        ]

        _insert_project(conn, "local_culture_jh", "new-local-jh")
        _insert_project(conn, "general_books_jh", "new-general-jh")
        _insert_export_template(conn, "local_culture_jh", "new-local-jh-template")
        _insert_export_template(conn, "general_books_jh", "new-general-jh-template")

        with pytest.raises(sqlite3.IntegrityError):
            _insert_project(conn, "invalid_type", "invalid-project")

        with pytest.raises(sqlite3.IntegrityError):
            _insert_export_template(conn, "invalid_type", "invalid-template")
    finally:
        conn.close()


def test_missing_export_template_error_points_to_template_management():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(
            """
            CREATE TABLE procurement_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                export_template_type TEXT NOT NULL
            );
            CREATE TABLE export_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_type TEXT NOT NULL
            );
            INSERT INTO procurement_projects(export_template_type) VALUES ('local_culture_jh');
            """
        )

        with pytest.raises(ValueError) as exc:
            _load_export_template_for_project(1, conn)

        message = str(exc.value)
        assert "範本管理" in message
        assert "config.yaml" not in message
    finally:
        conn.close()
