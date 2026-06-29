CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS procurement_projects (
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

CREATE TABLE IF NOT EXISTS import_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    file_type TEXT NOT NULL CHECK(file_type IN ('library_holdings', 'vendor_books')),
    column_mappings TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES procurement_projects(id),
    batch_type TEXT NOT NULL CHECK(batch_type IN ('library_holdings', 'vendor_books')),
    original_filename TEXT NOT NULL,
    profile_id INTEGER REFERENCES import_profiles(id),
    record_count INTEGER,
    imported_by INTEGER REFERENCES users(id),
    imported_at TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS library_holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES import_batches(id),
    isbn TEXT,
    isbn_normalized TEXT,
    title TEXT,
    author TEXT,
    publisher TEXT,
    publish_year TEXT,
    price REAL,
    library_record_id TEXT,
    isbn_status TEXT NOT NULL CHECK(isbn_status IN ('valid', 'missing', 'invalid')),
    raw_row TEXT
);

CREATE TABLE IF NOT EXISTS vendor_books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES import_batches(id),
    award_item TEXT,
    vendor_seq TEXT,
    title TEXT,
    author TEXT,
    isbn TEXT,
    isbn_normalized TEXT,
    publish_date TEXT,
    list_price REAL,
    purchase_price REAL,
    publisher TEXT,
    age_range TEXT,
    isbn_status TEXT NOT NULL CHECK(isbn_status IN ('valid', 'missing', 'invalid')),
    completeness_status TEXT NOT NULL DEFAULT 'unknown'
        CHECK(completeness_status IN ('export_ready', 'needs_review', 'missing_required', 'unknown')),
    policy_topic TEXT,
    award_notes TEXT,
    user_overrides TEXT,
    raw_row TEXT
);

CREATE TABLE IF NOT EXISTS book_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor_book_id INTEGER NOT NULL REFERENCES vendor_books(id),
    holding_id INTEGER REFERENCES library_holdings(id),
    match_status TEXT NOT NULL CHECK(match_status IN (
        'available', 'already_owned', 'missing_isbn', 'invalid_isbn', 'same_title_different_isbn'
    )),
    matched_at TEXT NOT NULL,
    batch_run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS selection_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES procurement_projects(id),
    vendor_book_id INTEGER NOT NULL REFERENCES vendor_books(id),
    selected_quantity INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(project_id, vendor_book_id)
);

CREATE TABLE IF NOT EXISTS export_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES procurement_projects(id),
    school_name TEXT,
    approved_budget REAL,
    price_field TEXT NOT NULL CHECK(price_field IN ('list_price', 'purchase_price')),
    subtotal_mode TEXT NOT NULL CHECK(subtotal_mode IN (
        'quantity_times_list_price', 'quantity_times_purchase_price'
    )),
    template_path TEXT,
    output_filename TEXT,
    output_path TEXT,
    exported_by INTEGER REFERENCES users(id),
    exported_at TEXT NOT NULL,
    record_count INTEGER,
    total_amount REAL
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);
