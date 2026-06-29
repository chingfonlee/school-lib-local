# Plan: task-expand-jh-project-type-checks

## 實作步驟

### Step 1 — Schema 調查（只讀，不寫）

確認以下現況，不做任何修改：

1. 確認 `migrations/001_initial_schema.sql` 的 `procurement_projects.project_type` CHECK 現值。
2. 確認 `migrations/002_import_export_mapping.sql` 的 `export_templates.project_type` CHECK 現值。
3. 確認 `procurement_projects.export_template_type` 無 CHECK constraint（只有 DEFAULT）。
4. 執行 sqlite schema 確認：

   ```powershell
   .venv\Scripts\python.exe -c "
   import sqlite3, pathlib
   db = pathlib.Path('data/school_lib.db')
   if db.exists():
       conn = sqlite3.connect(db)
       for row in conn.execute(\"SELECT sql FROM sqlite_master WHERE type='table' AND name IN ('procurement_projects','export_templates')\"):
           print(row[0])
   else:
       print('no DB yet (fresh install)')
   "
   ```

5. 確認 `app/routers/projects.py` API 驗證已含四種類型（已知，此步驟只做最終確認）。
6. 確認 `export_service.py:57` 的錯誤訊息文字（已知，此步驟只做最終確認）。

---

### Step 2 — 更新 001/002 的 CREATE TABLE DDL（fresh DB 策略）

**採用方案 B：同步更新 001/002 + 新增 005**

理由：
- 方案 A（只靠 005）：fresh DB 先跑 001/002 建出舊 CHECK，再跑 005 重建，流程正確但 001/002 原始檔案仍有誤導性的舊 DDL，未來難以維護。
- 方案 B：001/002 直接改成正確 DDL；005 負責既有 DB 升級。fresh schema 可讀性好，維護成本低。

**001_initial_schema.sql 修改目標：**

將 `procurement_projects.project_type` 的 CHECK 從：

```sql
CHECK(project_type IN ('local_culture', 'general_books'))
```

改為：

```sql
CHECK(project_type IN ('local_culture', 'general_books', 'local_culture_jh', 'general_books_jh'))
```

**002_import_export_mapping.sql 修改目標：**

將 `export_templates.project_type` 的 CHECK 從：

```sql
CHECK(project_type IN ('local_culture', 'general_books'))
```

改為：

```sql
CHECK(project_type IN ('local_culture', 'general_books', 'local_culture_jh', 'general_books_jh'))
```

---

### Step 3 — 新增 migrations/005_expand_project_type_checks.sql

供 existing DB 升級（fresh DB 透過更新後的 001/002 直接建出正確 schema，不需 005）。

**重建 procurement_projects 策略：**

SQLite 不支援 `ALTER COLUMN … CHECK`，必須重建 table。

參考 migration 003 的做法（`PRAGMA foreign_keys=OFF` + 建新表 + 複製資料 + 改名）。

```sql
-- Step A：關閉 FK 檢查（避免重建過程 FK violation）
PRAGMA foreign_keys = OFF;

-- Step B：建新 procurement_projects（含擴展 CHECK）
CREATE TABLE procurement_projects_new (
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

-- Step C：複製資料
INSERT INTO procurement_projects_new
    SELECT * FROM procurement_projects;

-- Step D：刪舊表，改名
DROP TABLE procurement_projects;
ALTER TABLE procurement_projects_new RENAME TO procurement_projects;

-- Step E：重建 export_templates（同樣需要重建，因為 CHECK 在建表時定義）
CREATE TABLE export_templates_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    project_type TEXT NOT NULL CHECK(project_type IN (
        'local_culture', 'general_books', 'local_culture_jh', 'general_books_jh'
    )),
    template_file_path TEXT NOT NULL,
    sheet_name TEXT,
    header_row INTEGER NOT NULL DEFAULT 3,
    data_start_row INTEGER NOT NULL DEFAULT 6,
    max_rows INTEGER NOT NULL DEFAULT 50,
    school_name_cell TEXT NOT NULL DEFAULT 'A3',
    approved_budget_cell TEXT NOT NULL DEFAULT 'E3',
    total_quantity_cell TEXT,
    total_amount_cell TEXT,
    column_mappings TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

INSERT INTO export_templates_new
    SELECT * FROM export_templates;

DROP TABLE export_templates;
ALTER TABLE export_templates_new RENAME TO export_templates;

-- Step F：恢復 FK 檢查
PRAGMA foreign_keys = ON;
```

**注意事項：**

- `procurement_projects` 的 FK 來自：
  - `selection_items.project_id REFERENCES procurement_projects(id)`
  - `import_batches.project_id REFERENCES procurement_projects(id)`
  - `export_jobs.project_id REFERENCES procurement_projects(id)`
  - 這些全是 FK on `id`，不是 `project_type`，重建後 FK 仍有效（AUTOINCREMENT id 不變）。
- `export_templates` 沒有宣告 FK（`export_jobs.export_template_id` 是用 `ALTER TABLE ADD COLUMN` 加的，無 FK constraint），無需額外處理。
- `selection_items` 在 003 migration 時已重建，有完整欄位定義，無需再動。

---

### Step 4 — 更新 export_service.py 錯誤訊息

`app/services/export_service.py` 第 57 行，將：

```python
"，請確認 config.yaml export_templates 已設定並重新啟動服務。"
```

改為：

```python
"，請至導覽列「範本管理」確認範本已設定。"
```

---

### Step 5 — 新增測試

建議新增 `tests/test_project_type_checks.py`（若既有合適測試檔也可擴充）。

測試策略：使用 in-memory SQLite DB，依序套用 001→002→003→004→005 migration SQL，然後驗證寫入行為。

**測試案例 A — fresh DB（001→002→003→004→005 全套）：**

1. `local_culture_jh` 可寫入 `procurement_projects`
2. `general_books_jh` 可寫入 `procurement_projects`
3. `local_culture_jh` 可寫入 `export_templates`
4. `general_books_jh` 可寫入 `export_templates`
5. 無效類型（如 `invalid_type`）寫入 `procurement_projects` 觸發 `IntegrityError`
6. 無效類型寫入 `export_templates` 觸發 `IntegrityError`
7. 既有 `local_culture` / `general_books` 資料在 005 migration（重建）後仍存在

**測試案例 B — 模擬既有舊 DB（只套 005 升級）：**

此 fixture 用「舊 CHECK schema」（只允許兩種類型）建表，插入國小既有資料，再只套用 005 migration，模擬 existing DB 升級情境：

8. 以含舊 CHECK 的 DDL 建 in-memory DB（不套 001~004，直接寫舊版 CREATE TABLE）
9. 插入 `local_culture` 與 `general_books` 既有資料
10. 套用 `migrations/005_expand_project_type_checks.sql`
11. 確認既有 `local_culture` / `general_books` 資料完整保留（COUNT 相符）
12. 確認升級後可寫入 `local_culture_jh` / `general_books_jh`
13. 確認無效類型仍被拒絕（`IntegrityError`）

**測試 fixture 模式**（參考既有測試）：

```python
import sqlite3, pytest, pathlib

MIGRATIONS = [
    "migrations/001_initial_schema.sql",
    "migrations/002_import_export_mapping.sql",
    "migrations/003_selection_snapshot.sql",
    "migrations/004_vendor_classification_fields.sql",
    "migrations/005_expand_project_type_checks.sql",
]

@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    for path in MIGRATIONS:
        sql = pathlib.Path(path).read_text(encoding="utf-8")
        conn.executescript(sql)
    # 插入必要基礎資料（users 等）...
    yield conn
    conn.close()
```

---

### Step 6 — 驗證

依序執行：

```powershell
git diff --check
.venv\Scripts\python.exe -m pytest -q
```

若有 existing DB，可額外手動確認：

```powershell
.venv\Scripts\python.exe -c "
import sqlite3
conn = sqlite3.connect('data/school_lib.db')
for row in conn.execute(\"SELECT sql FROM sqlite_master WHERE type='table' AND name IN ('procurement_projects','export_templates')\"):
    print(row[0])
"
```

確認 CREATE TABLE 語句已含四種 project_type。

---

## 風險與注意事項

1. **SQLite CHECK 不可 ALTER**：必須重建 table，任何欄位列表或 DEFAULT 遺漏都會導致資料遺失或後續 migration 失敗。Step 3 的新表欄位定義需與 001 + 003 + 004 migration 後的最終 schema 完全一致。
2. **AUTOINCREMENT id 保持不變**：重建前後 `procurement_projects.id` 序列不中斷，FK 參照不受影響。
3. **001/002 修改的時機**：只修改 `CREATE TABLE` DDL，不加任何 ALTER 或資料操作。fresh DB 跑 001/002 後建出新 CHECK；005 的重建邏輯使用新 CHECK DDL，兩者一致。
4. **in-memory 測試 foreign_keys 開啟**：SQLite in-memory DB 預設 foreign_keys=OFF，測試 fixture 必須顯式 `PRAGMA foreign_keys = ON`。
5. **migration 003 precedent**：migration 003 已示範完整的重建流程（PRAGMA off → 建新表 → INSERT SELECT → DROP → RENAME → PRAGMA on），Step 3 沿用相同模式。

---

## 預計影響範圍

| 檔案 | 變更性質 |
|------|---------|
| `migrations/001_initial_schema.sql` | 修改 CHECK 值列表（DDL 文字） |
| `migrations/002_import_export_mapping.sql` | 修改 CHECK 值列表（DDL 文字） |
| `migrations/005_expand_project_type_checks.sql` | 新增（重建兩個 table） |
| `app/services/export_service.py` | 修改錯誤訊息一行 |
| `tests/test_project_type_checks.py` | 新增測試 |

共 5 個檔案（2 修改、2 新增、1 修改）。

---

## 驗證指令

- lint: 無獨立 lint 指令（Python 型態由 mypy 處理，本專案無 mypy 設定，略）
- format: 無 autoformat 設定（略）
- typecheck: 略
- test: `.venv\Scripts\python.exe -m pytest -q`
- build: 不適用（Python 直接執行）
- 額外確認: `git diff --check`

---

## 成果報告

- result_report_mode: none
- 適用情境：schema fix + 測試補強，無需 HTML/MD 報告
