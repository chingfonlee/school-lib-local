-- Migration 004: 新增 classification_number 欄位至 vendor_books 與 selection_items

ALTER TABLE vendor_books ADD COLUMN classification_number TEXT;
ALTER TABLE selection_items ADD COLUMN classification_number TEXT;
