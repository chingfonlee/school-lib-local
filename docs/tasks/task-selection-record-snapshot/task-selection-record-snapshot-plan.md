# Plan: task-selection-record-snapshot

## Phase B 前置確認

進入 Phase B 實作前，必須先確認以下狀態：

1. **上一個 task 狀態**：`task-library-holdings-reimport-multisheet` 目前在 `docs/STATUS.md` Active Tasks 中仍為 `active`（branch: `fix/task-library-holdings-reimport-multisheet`）。Phase B B-6 建立 branch 前，需先確認此 task 已 close，或明確確認兩 task 可並行且工作樹乾淨。
2. **Git working tree**：Phase B B-6 前，working tree 必須只有 `docs/STATUS.md` 與 `docs/tasks/task-selection-record-snapshot/` 相關異動（untracked 可接受）；不可有其他 staged 或 modified 的程式碼變更。
3. **Base branch**：`planning_base_branch: main`。建立 `fix/task-selection-record-snapshot` 前需先確認目前 branch 為 `main`（而非 `fix/task-library-holdings-reimport-multisheet`），且 `fix/task-selection-record-snapshot` branch 不應已存在。
4. **Branch 切換步驟**：若目前 working tree 在 `fix/task-library-holdings-reimport-multisheet`，執行 `git checkout main` 後，`docs/tasks/task-selection-record-snapshot/` 目錄（untracked）仍會保留，可繼續 Phase B。

## 實作步驟

### Step 1：建立 migration 003 — vendor_books 新增欄位

建立 `migrations/003_selection_snapshot.sql`，第一段新增 vendor_books 欄位：

```sql
ALTER TABLE vendor_books ADD COLUMN category TEXT;
ALTER TABLE vendor_books ADD COLUMN book_type TEXT;
ALTER TABLE vendor_books ADD COLUMN summary TEXT;
ALTER TABLE vendor_books ADD COLUMN source_url TEXT;
ALTER TABLE vendor_books ADD COLUMN recommendation_source TEXT;
ALTER TABLE vendor_books ADD COLUMN eligibility_label TEXT;
```

### Step 2：重建 selection_items — migration 003 第二段

SQLite 不支援 `ALTER COLUMN` 修改 NOT NULL 或 FK constraint，必須使用 create-copy-drop-rename。

```sql
-- 關閉 FK 檢查，允許操作期間的弱關聯
PRAGMA foreign_keys = OFF;

-- 2-1. 建立新表（vendor_book_id 為 nullable，不設 REFERENCES）
CREATE TABLE selection_items_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES procurement_projects(id),
    vendor_book_id INTEGER,           -- nullable，弱關聯，不設 REFERENCES FK
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

-- 2-2. Backfill：從舊表 JOIN vendor_books / import_batches / book_matches 複製資料
--      若 vendor_books 已不存在（LEFT JOIN 返回 NULL），快照欄位填 NULL，僅保留採購紀錄欄位
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
    vb.user_overrides,             -- 將 vendor_books 既有 overrides 搬移到 selection_items（僅 backfill）
    vb.extra_fields,
    vb.raw_row,
    NULL                           AS book_snapshot,
    si.created_by, si.created_at, si.updated_at
FROM selection_items si
LEFT JOIN vendor_books vb ON vb.id = si.vendor_book_id
LEFT JOIN import_batches ib ON ib.id = vb.batch_id;

-- 2-3. 刪舊表
DROP TABLE selection_items;

-- 2-4. 重命名
ALTER TABLE selection_items_new RENAME TO selection_items;

-- 重新開啟 FK 檢查
PRAGMA foreign_keys = ON;
```

**Backfill 容錯策略**：若 vendor_books 已被刪除，LEFT JOIN 返回 NULL，快照欄位全部為 NULL。此類 selection_items 仍保留採購數量與備註，export readiness 會標示缺少必填欄位，使用者需手動補齊或重新選書。

**book_matches 多筆問題（已在 SQL 中解決）**：backfill 不使用 `LEFT JOIN book_matches`，改用 correlated subquery（`SELECT ... WHERE vendor_book_id = si.vendor_book_id AND ... ORDER BY id DESC LIMIT 1`），每個 selection_items 只取一筆最新代表性 match，不會因多筆 book_matches 導致重複 INSERT 或 UNIQUE constraint 違反。

### Step 3：更新 VENDOR_COLUMN_HINTS

在 `app/services/import_service.py` 的 `VENDOR_COLUMN_HINTS` 字典新增六個欄位：

```python
"category": ["分類", "category"],
"book_type": ["類型", "書本類型", "book_type"],
"summary": ["summary_80_120", "摘要", "summary"],
"source_url": ["連結", "url", "link", "source_url"],
"recommendation_source": ["award_template", "推薦來源", "recommendation_source"],
"eligibility_label": ["eligible_label", "資格標籤", "必選推薦", "eligibility_label"],
```

### Step 4：更新 vendor books import 寫入邏輯

`confirm_import()` 與 `import_vendor_books()` 兩個函式中，INSERT INTO vendor_books 的 SQL 與參數均需補入六個新欄位：category、book_type、summary、source_url、recommendation_source、eligibility_label。

具體做法：在各函式的 `get_field()` 讀取新欄位值，加入 INSERT 欄位清單與 VALUES 參數。

### Step 5：修改 selection_service.py

#### upsert_selection()

函式簽名不變（project_id, vendor_book_id, quantity, notes, user_id）。

- **新 INSERT**：改為先查詢 vendor_books + book_matches + import_batches 取得快照資料，再 INSERT 所有正規化欄位。
- **已有紀錄 UPDATE**：只更新 `selected_quantity`、`notes`、`updated_at`，不覆蓋快照欄位。
- **刪除（quantity=0）**：行為不變，DELETE FROM selection_items。

INSERT 時讀取快照資料的查詢範例：

```python
snap = conn.execute(
    "SELECT vb.*, ib.id AS source_batch_id, ib.original_filename, "
    "(SELECT bm.match_status FROM book_matches bm "
    "  WHERE bm.vendor_book_id = vb.id "
    "    AND bm.match_status != 'same_title_different_isbn' "
    "  ORDER BY bm.id DESC LIMIT 1) AS match_status, "
    "(SELECT bm.holding_id FROM book_matches bm "
    "  WHERE bm.vendor_book_id = vb.id "
    "    AND bm.match_status != 'same_title_different_isbn' "
    "  ORDER BY bm.id DESC LIMIT 1) AS holding_id "
    "FROM vendor_books vb "
    "JOIN import_batches ib ON ib.id = vb.batch_id "
    "WHERE vb.id = ?",
    (vendor_book_id,),
).fetchone()
```

若 vendor_books 已不存在（snap 為 None），拒絕 INSERT 並向呼叫端回傳錯誤（來源書目不存在，無法建立選書快照）。

#### get_selection_summary()

改為讀 selection_items 快照欄位，不 JOIN vendor_books：

```python
rows = conn.execute(
    "SELECT si.selected_quantity, si.list_price, si.purchase_price, si.user_overrides "
    "FROM selection_items si WHERE si.project_id = ?",
    (project_id,),
).fetchall()
```

#### get_selected_books()

改為 `SELECT si.*`，只補充 vendor_books 的存在狀態（optional LEFT JOIN）：

```python
rows = conn.execute(
    "SELECT si.*, "
    "(SELECT bm.match_status FROM book_matches bm "
    "  WHERE bm.vendor_book_id = si.vendor_book_id "
    "    AND bm.match_status != 'same_title_different_isbn' "
    "  ORDER BY bm.id DESC LIMIT 1) AS current_match_status, "
    "(vb.id IS NOT NULL) AS vendor_book_still_exists "
    "FROM selection_items si "
    "LEFT JOIN vendor_books vb ON vb.id = si.vendor_book_id "
    "WHERE si.project_id = ? ORDER BY si.id",
    (project_id,),
).fetchall()
```

返回資料中確保包含 `sel_id`（= si.id）、`vendor_book_id`（供前端判斷已選狀態）、所有快照欄位。

### Step 6：修改 export_service.py

#### export_local_culture() 主查詢

改為讀 selection_items 快照欄位，書目資料不再依賴 JOIN vendor_books：

```python
books = conn.execute(
    "SELECT si.*, "
    "COALESCE("
    "  (SELECT bm.match_status FROM book_matches bm "
    "   WHERE bm.vendor_book_id = si.vendor_book_id "
    "     AND bm.match_status != 'same_title_different_isbn' "
    "   ORDER BY bm.id DESC LIMIT 1), "
    "  si.match_status_at_selection, 'available'"
    ") AS match_status "
    "FROM selection_items si "
    "WHERE si.project_id = ? AND si.selected_quantity > 0 "
    "  AND COALESCE("
    "    (SELECT bm.match_status FROM book_matches bm "
    "     WHERE bm.vendor_book_id = si.vendor_book_id "
    "       AND bm.match_status != 'same_title_different_isbn' "
    "     ORDER BY bm.id DESC LIMIT 1), "
    "    si.match_status_at_selection, 'available'"
    "  ) IN ('available', 'missing_isbn', 'invalid_isbn') "
    "ORDER BY si.vendor_seq, si.id",
    (settings.project_id,),
).fetchall()
```

（過濾邏輯：已擁有 already_owned 不匯出；available 或 match 狀態為 NULL 的書目均匯出。）

#### _resolve_field()

直接從 dict 讀快照欄位（si 已包含書目欄位），移除讀 raw_row 的 fallback（raw_row 仍作追溯，不作功能來源）。

#### _get_price()

讀 si.user_overrides、si.list_price、si.purchase_price。

### Step 7：修改 validation_service.py

#### check_export_readiness()

改為讀 selection_items 快照欄位：

```python
rows = conn.execute(
    "SELECT si.*, "
    "COALESCE("
    "  (SELECT bm.match_status FROM book_matches bm "
    "   WHERE bm.vendor_book_id = si.vendor_book_id "
    "     AND bm.match_status != 'same_title_different_isbn' "
    "   ORDER BY bm.id DESC LIMIT 1), "
    "  si.match_status_at_selection"
    ") AS resolved_match_status "
    "FROM selection_items si "
    "WHERE si.project_id = ?",
    (project_id,),
).fetchall()
```

欄位讀取改為 `si.title`、`si.isbn_normalized`、`si.isbn_status`、`si.list_price`、`si.purchase_price`、`si.award_item`，overrides 讀自 `si.user_overrides`。

### Step 8：修改 import_service._clear_vendor_books_for_project()

移除 `DELETE FROM selection_items` 步驟。清除順序改為：

1. DELETE book_matches（WHERE vendor_book_id IN vendor_books of old batches）
2. DELETE vendor_books（WHERE batch_id IN old batches）
3. DELETE import_batches（WHERE id IN old batches）

不再觸碰 selection_items。

### Step 9：新增 selections override API

在 `app/routers/selections.py` 新增端點：

```
PATCH /api/selections/{selection_id}/overrides
```

行為：讀取 selection_items.user_overrides（JSON merge），更新 updated_at，回傳更新後的 user_overrides。

### Step 10：驗收測試（手動執行）

**Migration 驗證（啟動服務前先用臨時 DB 驗）**

0-a. 執行 migration-check（見「驗證指令」），確認：
  - `PRAGMA table_info(selection_items)` 含所有快照欄位，`vendor_book_id` 為 nullable。
  - `PRAGMA table_info(vendor_books)` 含 category、book_type、summary、source_url、recommendation_source、eligibility_label。
  - `SELECT version FROM schema_migrations WHERE version='003_selection_snapshot'` 回傳一筆。

0-b. 在既有 selection_items 有資料時執行 migration，確認採購紀錄（project_id、selected_quantity、notes）不遺失，快照欄位若 vendor_books 已不存在則為 NULL。

0-c. migration 後：刪除對應 vendor_books 紀錄，確認 selection_items 不被級聯刪除（FK 已解除）。`vendor_book_id` 欄位仍保留原值，`vendor_book_still_exists` 回傳 false。

**功能驗收（服務啟動後）**

1. 啟動服務，確認 migration 003 已套用（`schema_migrations` 表含 `003_selection_snapshot`）。
2. 匯入 `00_source/必選推薦-欄位調整-topic-summary-v6-final.xlsx`，確認 vendor_books 含 category、book_type、summary、source_url、recommendation_source、eligibility_label 欄位值。
3. 加入數本書至選書清單，確認 selection_items 已存入快照欄位（可直接查 DB）。
4. 確認 book_matches 多筆不造成重複：`SELECT COUNT(*) FROM selection_items WHERE project_id=?` 應與加入書本數一致。
5. 手動刪除 book_matches、vendor_books、import_batches（`vendor_books` batch），確認：
   - GET /api/selections/ 仍回傳書名、ISBN、price
   - GET /api/selections/summary 金額正確
   - POST /api/exports/readiness 可執行
   - POST /api/exports/export 可產生 Excel
6. 重新匯入書商書單，確認既有 selection_items 快照未被覆蓋。
7. `python -m compileall app` 無錯誤。

## 風險與注意事項

1. **SQLite PRAGMA foreign_keys = OFF**：migration 003 第二段必須在 `foreign_keys = OFF` 下執行，否則 DROP TABLE 可能因 FK 被其他表參照而失敗。migration 結尾恢復 `PRAGMA foreign_keys = ON`。
   - `run_migrations()` 使用 `conn.executescript()`，會隱式 commit 所有未提交事務；需確認 PRAGMA 指令在 executescript 內可正確執行。

2. **book_matches 多筆風險（已解決）**：backfill SQL、upsert_selection 快照查詢、get_selected_books、export_local_culture、check_export_readiness 均不使用普通 `LEFT JOIN book_matches`，改用 correlated subquery（`SELECT bm.match_status ... ORDER BY bm.id DESC LIMIT 1`）取一筆代表性 match，排除 `same_title_different_isbn`。確保任何查詢不會因同一 vendor_book_id 有多筆 book_matches 而產生重複列或重複 INSERT。驗收需確認：(a) `SELECT COUNT(*) FROM selection_items WHERE project_id=?` 與加入書本數一致；(b) GET /api/selections/、readiness details、export 不出現重複的 selection 紀錄。

3. **UNIQUE(project_id, vendor_book_id) 保留**：SQLite 允許 UNIQUE 欄位中有多個 NULL 值，因此 vendor_book_id IS NULL 的列不受此約束影響。目前所有選書均透過 vendor_book_id 加入，此約束仍有效。

4. **前端 selected 狀態判斷**：selection.html 用 `vendor_book_id` 判斷書是否已選；migration 後 `vendor_book_id` 仍在 selection_items，GET /api/selections/ 回傳中應確保 `vendor_book_id` 欄位存在，前端不需修改。

5. **Backfill 時 user_overrides 搬移**：backfill 將 vendor_books.user_overrides 複製到 selection_items.user_overrides。此為 best-effort，vendor_books.user_overrides 原始資料不刪除（vendor_books 後續仍可能被清除，但不是本任務刪除）。

6. **export 過濾邏輯**：原查詢過濾 `bm.match_status = 'available' OR bm.match_status IS NULL`。新查詢使用 `COALESCE(correlated subquery 取得的最新 match_status, si.match_status_at_selection, 'available')`，若結果為 `already_owned` 則不匯出，其餘均匯出。此行為需與 check_export_readiness 邏輯對齊。

7. **migration 中 vb.category 等欄位**：backfill 讀 vb.category 等欄位時，需在 Step 1 的 ALTER TABLE vendor_books 已執行後才能讀到（migration 003 是同一個 SQL 檔，須確保 ALTER TABLE 段落在 INSERT 段落之前執行）。

## 預計影響範圍

| 檔案 | 變更類型 |
|------|---------|
| `migrations/003_selection_snapshot.sql` | 新增 |
| `app/services/import_service.py` | 修改：VENDOR_COLUMN_HINTS、confirm_import、import_vendor_books、_clear_vendor_books_for_project |
| `app/services/selection_service.py` | 修改：upsert_selection、get_selection_summary、get_selected_books |
| `app/services/export_service.py` | 修改：export_local_culture 主查詢、_resolve_field、_get_price |
| `app/services/validation_service.py` | 修改：check_export_readiness |
| `app/routers/selections.py` | 修改：新增 PATCH /{selection_id}/overrides |

**不影響**：
- `app/routers/books.py`（PATCH /{book_id}/overrides 保留相容，不改功能）
- `app/services/match_service.py`（不受影響）
- `app/services/completeness_service.py`（不受影響）
- `app/static/selection.html`：本 task 不修改前端 JS。現有 `PATCH /api/books/{book_id}/overrides` 呼叫保留向後相容；`selMap` 以 `vendor_book_id` 為鍵的邏輯不需修改（API 回傳仍含 `vendor_book_id`）。
- `app/static/export-check.html`：依賴 `vendor_book_id`、`title`、`match_status`、`completeness_status`；API 回傳欄位名稱不變（資料來源改為 si.*，match_status 改用 COALESCE）。
- `app/static/export.html`：依賴 `user_overrides`、`selected_quantity`、`list_price`、`purchase_price`；API 回傳欄位名稱不變（資料來源改為 si.*）。

## 驗證指令

- lint: `python -m py_compile app/services/selection_service.py app/services/export_service.py app/services/validation_service.py app/services/import_service.py app/routers/selections.py`
- format: 無既有設定，不強制執行
- typecheck: 無既有設定，不強制執行
- test: `python -m compileall app`
- migration-check: 建立臨時 SQLite DB，執行 `run_migrations()`，確認 migration 003 可成功套用：
  ```python
  import sqlite3, sys
  sys.path.insert(0, '.')
  from app.database import run_migrations
  conn = sqlite3.connect(':memory:')
  run_migrations(conn)
  # 確認 migration 版本已記錄
  print(conn.execute("SELECT version FROM schema_migrations WHERE version='003_selection_snapshot'").fetchone())
  # 確認 selection_items 欄位結構（含 vendor_book_id nullable、快照欄位）
  for row in conn.execute("PRAGMA table_info(selection_items)"): print(row)
  # 確認 vendor_books 新增欄位
  for row in conn.execute("PRAGMA table_info(vendor_books)"): print(row)
  conn.close()
  ```
- build: `uvicorn app.main:app --reload`（啟動後確認無錯誤、migration 003 已套用）

## 清除書商書單鋪路說明

本 task 不實作正式「清除書商書單」UI 或 API，但完成後為後續清除功能鋪路：

- Step 8 修改後，`_clear_vendor_books_for_project()` 不再刪除 `selection_items`。
- 後續若新增「清除書商書單」功能，應只刪除：
  - `book_matches`（WHERE vendor_book_id IN 對應 vendor_books）
  - `vendor_books`（WHERE batch_id IN 對應 import_batches）
  - `import_batches`（WHERE id IN 對應 batches）
- **不刪 `selection_items`**：採購紀錄已包含快照，與 vendor_books 解耦，不受書商書單清除影響。
- 清除後，selection_items 的 `vendor_book_id` 仍保留原值（指向已不存在的 vendor_books），前端應以 `vendor_book_still_exists: false` 欄位顯示「書商書目已清除，採購紀錄保留」的狀態。

## 成果報告

- result_report_mode: none
- 適用情境：資料完整性修正任務，驗收依手動測試步驟（Step 10）確認
