-- Migration 005: Expand project_type CHECK constraints for junior high project types.
--
-- SQLite cannot ALTER an existing CHECK constraint, so rebuild the two affected
-- tables while preserving ids and existing rows.

PRAGMA foreign_keys = OFF;

CREATE TABLE procurement_projects_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    project_type TEXT NOT NULL CHECK(project_type IN (
        'local_culture', 'general_books', 'local_culture_jh', 'general_books_jh'
    )),
    budget_amount REAL,
    export_template_type TEXT NOT NULL DEFAULT 'local_culture',
    price_field TEXT NOT NULL DEFAULT 'purchase_price'
        CHECK(price_field IN ('list_price', 'purchase_price')),
    subtotal_mode TEXT NOT NULL DEFAULT 'quantity_times_purchase_price'
        CHECK(subtotal_mode IN ('quantity_times_list_price', 'quantity_times_purchase_price')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

INSERT INTO procurement_projects_new (
    id, name, project_type, budget_amount, export_template_type,
    price_field, subtotal_mode, created_at, updated_at
)
SELECT
    id, name, project_type, budget_amount, export_template_type,
    price_field, subtotal_mode, created_at, updated_at
FROM procurement_projects;

DROP TABLE procurement_projects;
ALTER TABLE procurement_projects_new RENAME TO procurement_projects;

CREATE TABLE export_templates_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    project_type TEXT NOT NULL CHECK(project_type IN (
        'local_culture', 'general_books', 'local_culture_jh', 'general_books_jh'
    )),
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

INSERT INTO export_templates_new (
    id, name, project_type, template_file_path, sheet_name,
    header_row, data_start_row, max_rows, school_name_cell,
    approved_budget_cell, total_quantity_cell, total_amount_cell,
    column_mappings, created_at, updated_at
)
SELECT
    id, name, project_type, template_file_path, sheet_name,
    header_row, data_start_row, max_rows, school_name_cell,
    approved_budget_cell, total_quantity_cell, total_amount_cell,
    column_mappings, created_at, updated_at
FROM export_templates;

DROP TABLE export_templates;
ALTER TABLE export_templates_new RENAME TO export_templates;

PRAGMA foreign_keys = ON;
