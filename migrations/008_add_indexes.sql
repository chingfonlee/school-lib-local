-- 008: Add secondary indexes on foreign keys and lookup columns to avoid full table scans

CREATE INDEX IF NOT EXISTS idx_import_batches_project_id
    ON import_batches(project_id);

CREATE INDEX IF NOT EXISTS idx_vendor_books_batch_id
    ON vendor_books(batch_id);

CREATE INDEX IF NOT EXISTS idx_vendor_books_isbn_normalized
    ON vendor_books(isbn_normalized);

CREATE INDEX IF NOT EXISTS idx_library_holdings_batch_id
    ON library_holdings(batch_id);

CREATE INDEX IF NOT EXISTS idx_library_holdings_isbn_normalized
    ON library_holdings(isbn_normalized);

CREATE INDEX IF NOT EXISTS idx_book_matches_vendor_book_id
    ON book_matches(vendor_book_id);

CREATE INDEX IF NOT EXISTS idx_book_matches_holding_id
    ON book_matches(holding_id);

CREATE INDEX IF NOT EXISTS idx_selection_items_project_id
    ON selection_items(project_id);

CREATE INDEX IF NOT EXISTS idx_export_jobs_project_id
    ON export_jobs(project_id);
