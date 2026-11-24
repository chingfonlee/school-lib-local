-- 010: Support shared vendor catalog pool with vendor_name on import_batches

ALTER TABLE import_batches ADD COLUMN vendor_name TEXT;

CREATE INDEX IF NOT EXISTS idx_import_batches_batch_type_vendor
    ON import_batches(batch_type, vendor_name);
