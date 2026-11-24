CREATE TABLE IF NOT EXISTS award_normalization_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_type TEXT NOT NULL DEFAULT 'general_books',
    match_type TEXT NOT NULL CHECK (match_type IN ('exact', 'contains')),
    raw_pattern TEXT NOT NULL,
    normalized_award TEXT NOT NULL,
    eligibility_label TEXT NOT NULL,
    award_notes_mode TEXT NOT NULL DEFAULT 'empty' CHECK (award_notes_mode IN ('empty', 'raw_award')),
    priority INTEGER NOT NULL,
    confidence REAL NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

INSERT INTO award_normalization_rules
    (project_type, match_type, raw_pattern, normalized_award, eligibility_label, award_notes_mode, priority, confidence, enabled, created_at, updated_at)
VALUES
    ('general_books', 'exact', '自選', '學校自選(請備註原因)', '自選', 'empty', 10, 0.95, 1, datetime('now'), datetime('now')),
    ('general_books', 'contains', '金鼎獎', '金鼎獎', '推薦', 'empty', 20, 0.9, 1, datetime('now'), datetime('now')),
    ('general_books', 'contains', '好書大家讀', '好書大家讀', '推薦', 'empty', 20, 0.9, 1, datetime('now'), datetime('now')),
    ('general_books', 'contains', '喜閱網', '喜閱網', '推薦', 'empty', 20, 0.9, 1, datetime('now'), datetime('now')),
    ('general_books', 'contains', '文化部第', '文化部中小學生優良課外讀物選介', '推薦', 'empty', 20, 0.85, 1, datetime('now'), datetime('now')),
    ('general_books', 'contains', '國教署', '國民中小學新生閱讀推動活動入選書單', '推薦', 'empty', 20, 0.85, 1, datetime('now'), datetime('now')),
    ('general_books', 'contains', '國民中小學新生', '國民中小學新生閱讀推動活動入選書單', '推薦', 'empty', 20, 0.85, 1, datetime('now'), datetime('now')),
    ('general_books', 'contains', '新生閱讀入選', '國民中小學新生閱讀推動活動入選書單', '推薦', 'empty', 20, 0.85, 1, datetime('now'), datetime('now')),
    ('general_books', 'contains', '新生閱讀', '國民中小學新生閱讀推動活動入選書單', '推薦', 'empty', 20, 0.85, 1, datetime('now'), datetime('now')),
    ('general_books', 'contains', 'SEL', '圖書分級推薦書目、臺灣歷史文化分級推薦書目', '推薦', 'raw_award', 30, 0.5, 1, datetime('now'), datetime('now')),
    ('general_books', 'contains', 'SDGS', '圖書分級推薦書目、臺灣歷史文化分級推薦書目', '推薦', 'raw_award', 30, 0.5, 1, datetime('now'), datetime('now'));
