-- Migration 012: Support custom project type and add project management/archive fields.
--
-- SQLite cannot ALTER an existing CHECK constraint, so rebuild procurement_projects
-- while preserving all existing rows and primary keys.

PRAGMA foreign_keys = OFF;

BEGIN TRANSACTION;

CREATE TABLE procurement_projects_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    project_type TEXT NOT NULL CHECK(project_type IN (
        'local_culture', 'general_books', 'local_culture_jh', 'general_books_jh', 'custom'
    )),
    budget_amount REAL,
    export_template_type TEXT NOT NULL DEFAULT 'local_culture',
    price_field TEXT NOT NULL DEFAULT 'purchase_price'
        CHECK(price_field IN ('list_price', 'purchase_price')),
    subtotal_mode TEXT NOT NULL DEFAULT 'quantity_times_purchase_price'
        CHECK(subtotal_mode IN ('quantity_times_list_price', 'quantity_times_purchase_price')),
    academic_year TEXT,
    funding_source TEXT,
    project_notes TEXT,
    is_archived INTEGER NOT NULL DEFAULT 0,
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

COMMIT;

PRAGMA foreign_keys = ON;
