-- 011: Add index on selection_items(isbn_normalized) to speed up cross-project duplicate queries

CREATE INDEX IF NOT EXISTS idx_selection_items_isbn_normalized
    ON selection_items(isbn_normalized);
