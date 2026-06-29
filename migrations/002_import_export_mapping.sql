-- Migration 002: Add extra_fields / source_row_number to vendor_books,
-- expand import_profiles, add export_templates, add export_template_id to export_jobs.
-- Assumes clean 001_initial_schema applied first.

ALTER TABLE vendor_books ADD COLUMN extra_fields TEXT;
ALTER TABLE vendor_books ADD COLUMN source_row_number INTEGER;

ALTER TABLE import_profiles ADD COLUMN project_type TEXT;
ALTER TABLE import_profiles ADD COLUMN source_type TEXT;
ALTER TABLE import_profiles ADD COLUMN header_row INTEGER DEFAULT 0;
ALTER TABLE import_profiles ADD COLUMN mappings TEXT;
ALTER TABLE import_profiles ADD COLUMN extra_field_settings TEXT;

CREATE TABLE IF NOT EXISTS export_templates (
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

ALTER TABLE export_jobs ADD COLUMN export_template_id INTEGER;
