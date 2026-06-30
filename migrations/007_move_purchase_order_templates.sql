-- Migration 007: move built-in purchase order templates out of ignored 00_source.

UPDATE export_templates
SET template_file_path = REPLACE(template_file_path, './00_source/', './purchase-order-template/')
WHERE project_type IN (
    'local_culture',
    'general_books',
    'local_culture_jh',
    'general_books_jh'
)
  AND template_file_path LIKE './00_source/%';
