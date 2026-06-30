-- Migration 006: map junior-high general-books K column to recommendation_source.
-- Existing databases seeded the K column as award_notes; the vendor list stores
-- the dropdown value in award_template, imported as vendor_books.recommendation_source.

UPDATE export_templates
SET column_mappings = REPLACE(
    column_mappings,
    '"award_notes": "K"',
    '"recommendation_source": "K"'
)
WHERE project_type = 'general_books_jh'
  AND column_mappings LIKE '%"award_notes": "K"%'
  AND column_mappings NOT LIKE '%"recommendation_source": "K"%';

UPDATE export_templates
SET column_mappings = REPLACE(
    column_mappings,
    '"award_notes":"K"',
    '"recommendation_source":"K"'
)
WHERE project_type = 'general_books_jh'
  AND column_mappings LIKE '%"award_notes":"K"%'
  AND column_mappings NOT LIKE '%"recommendation_source":"K"%';
