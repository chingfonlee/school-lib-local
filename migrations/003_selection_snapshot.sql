-- Migration 003: Selection record snapshot.
-- Part A: add normalised columns to vendor_books.
-- Part B: rebuild selection_items with snapshot columns and nullable vendor_book_id (no FK).

-- ── Part A: vendor_books new columns ──────────────────────────────────────────
ALTER TABLE vendor_books ADD COLUMN category TEXT;
ALTER TABLE vendor_books ADD COLUMN book_type TEXT;
ALTER TABLE vendor_books ADD COLUMN summary TEXT;
ALTER TABLE vendor_books ADD COLUMN source_url TEXT;
ALTER TABLE vendor_books ADD COLUMN recommendation_source TEXT;
ALTER TABLE vendor_books ADD COLUMN eligibility_label TEXT;

-- ── Part B: rebuild selection_items ───────────────────────────────────────────
PRAGMA foreign_keys = OFF;

CREATE TABLE selection_items_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES procurement_projects(id),
    vendor_book_id INTEGER,
    source_batch_id INTEGER,
    source_original_filename TEXT,
    source_row_number INTEGER,
    selected_quantity INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    title TEXT,
    author TEXT,
    publisher TEXT,
    isbn TEXT,
    isbn_normalized TEXT,
    isbn_status TEXT,
    publish_date TEXT,
    list_price REAL,
    purchase_price REAL,
    award_item TEXT,
    vendor_seq TEXT,
    age_range TEXT,
    category TEXT,
    book_type TEXT,
    policy_topic TEXT,
    summary TEXT,
    source_url TEXT,
    recommendation_source TEXT,
    eligibility_label TEXT,
    award_notes TEXT,
    completeness_status TEXT NOT NULL DEFAULT 'unknown'
        CHECK(completeness_status IN ('export_ready', 'needs_review', 'missing_required', 'unknown')),
    match_status_at_selection TEXT,
    holding_id_at_selection INTEGER,
    user_overrides TEXT,
    extra_fields TEXT,
    raw_row TEXT,
    book_snapshot TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(project_id, vendor_book_id)
);

INSERT INTO selection_items_new (
    id, project_id, vendor_book_id,
    source_batch_id, source_original_filename, source_row_number,
    selected_quantity, notes,
    title, author, publisher, isbn, isbn_normalized, isbn_status,
    publish_date, list_price, purchase_price,
    award_item, vendor_seq, age_range,
    category, book_type, policy_topic, summary,
    source_url, recommendation_source, eligibility_label, award_notes,
    completeness_status,
    match_status_at_selection, holding_id_at_selection,
    user_overrides, extra_fields, raw_row, book_snapshot,
    created_by, created_at, updated_at
)
SELECT
    si.id,
    si.project_id,
    si.vendor_book_id,
    vb.batch_id                    AS source_batch_id,
    ib.original_filename           AS source_original_filename,
    vb.source_row_number           AS source_row_number,
    si.selected_quantity,
    si.notes,
    vb.title, vb.author, vb.publisher, vb.isbn, vb.isbn_normalized, vb.isbn_status,
    vb.publish_date, vb.list_price, vb.purchase_price,
    vb.award_item, vb.vendor_seq, vb.age_range,
    vb.category, vb.book_type, vb.policy_topic, vb.summary,
    vb.source_url, vb.recommendation_source, vb.eligibility_label, vb.award_notes,
    COALESCE(vb.completeness_status, 'unknown') AS completeness_status,
    (SELECT bm.match_status FROM book_matches bm
     WHERE bm.vendor_book_id = si.vendor_book_id
       AND bm.match_status != 'same_title_different_isbn'
     ORDER BY bm.id DESC LIMIT 1) AS match_status_at_selection,
    (SELECT bm.holding_id FROM book_matches bm
     WHERE bm.vendor_book_id = si.vendor_book_id
       AND bm.match_status != 'same_title_different_isbn'
     ORDER BY bm.id DESC LIMIT 1) AS holding_id_at_selection,
    vb.user_overrides,
    vb.extra_fields,
    vb.raw_row,
    NULL                           AS book_snapshot,
    si.created_by, si.created_at, si.updated_at
FROM selection_items si
LEFT JOIN vendor_books vb ON vb.id = si.vendor_book_id
LEFT JOIN import_batches ib ON ib.id = vb.batch_id;

DROP TABLE selection_items;
ALTER TABLE selection_items_new RENAME TO selection_items;

PRAGMA foreign_keys = ON;
