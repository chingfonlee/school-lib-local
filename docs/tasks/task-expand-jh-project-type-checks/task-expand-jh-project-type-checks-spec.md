# Spec: task-expand-jh-project-type-checks

## 目標

將 SQLite CHECK constraint 同步擴展，使 `procurement_projects.project_type` 與 `export_templates.project_type` 接受四種合法值：`local_culture`、`general_books`、`local_culture_jh`、`general_books_jh`。

目前 UI、API（`app/routers/projects.py`）、admin API（`app/routers/admin.py`）與 `template_analyzer.py` 已支援國中類型，但 DB schema 的 CHECK constraint 仍停留在 001/002 migration 定義的兩種值，導致 fresh DB 或 existing DB 在寫入國中資料時發生 `SQLITE_CONSTRAINT_CHECK`。

---

## 問題說明

### 不一致的現況

| 層級 | 國中類型支援 |
|------|-------------|
| UI（projects.html、admin-templates.html） | ✓ 已支援 |
| API 驗證（routers/projects.py:80） | ✓ 已支援 |
| admin 範本管理（routers/admin.py） | ✓ 已支援 |
| template_analyzer.py | ✓ 已支援 |
| migrations/001_initial_schema.sql — procurement_projects.project_type | ✗ 僅允許 local_culture、general_books |
| migrations/002_import_export_mapping.sql — export_templates.project_type | ✗ 僅允許 local_culture、general_books |

### 失敗情境

- **fresh DB**：依序套用 001→002→…→004 後，INSERT `local_culture_jh` / `general_books_jh` 進 `procurement_projects` 或 `export_templates` 時觸發 CHECK constraint failed。
- **existing DB**：schema 版本仍沿用舊 CHECK（SQLite 不支援 ALTER COLUMN 修改 CHECK），同樣無法寫入國中資料。
- **export_service.py**：找不到範本時的錯誤訊息引導使用者修改 `config.yaml export_templates`，此說法在本專案已不適用（範本現由 UI 管理）。

---

## 需求範圍

### 1. Schema 修正

- `procurement_projects.project_type` CHECK 擴展為：`IN ('local_culture', 'general_books', 'local_culture_jh', 'general_books_jh')`
- `export_templates.project_type` CHECK 擴展為：`IN ('local_culture', 'general_books', 'local_culture_jh', 'general_books_jh')`
- `procurement_projects.export_template_type` 目前無 CHECK constraint（001_initial_schema.sql 只有 DEFAULT 'local_culture'），不在本次修正範圍內，但需於 plan 確認。

### 2. Fresh DB 策略

- 同步更新 `migrations/001_initial_schema.sql` 與 `migrations/002_import_export_mapping.sql` 的 `CREATE TABLE` 陳述式，使新安裝時即建出正確 schema。
- 新增 `migrations/005_expand_project_type_checks.sql`，供既有 DB 升級。

### 3. 錯誤訊息修正

- `app/services/export_service.py:57`：將「請確認 config.yaml export_templates 已設定並重新啟動服務」改為「請至範本管理確認範本已設定」。

### 4. 測試

- 新增或更新測試，驗證 fresh DB 套 migration 後四種 project_type 均可寫入，且無效值仍被拒絕。

---

## 影響範圍

- `migrations/001_initial_schema.sql`（CREATE TABLE procurement_projects — CHECK 修改）
- `migrations/002_import_export_mapping.sql`（CREATE TABLE export_templates — CHECK 修改）
- `migrations/005_expand_project_type_checks.sql`（新增，供 existing DB 升級）
- `app/services/export_service.py`（錯誤訊息）
- `tests/`（新增 project_type CHECK 驗證測試）

**不受影響**（確認後無需變更）：

- `app/routers/projects.py` — API 驗證已正確
- `app/routers/admin.py` — template 管理已正確
- `app/services/template_analyzer.py` — 已支援國中類型
- `app/static/*.html` — 前端已正確
- `app/database.py` — seed 行為依 config 內容寫入，問題源頭在 schema CHECK，修正 schema 後自然解決

---

## 不做的事

- 不重做或新增國中匯出格式邏輯（匯出功能本身留待後續 task）
- 不更動 UI 文案，除了 export_service.py 的錯誤訊息
- 不新增截圖或操作說明
- 不修改除 005 以外的 migration 實際資料遷移邏輯（001/002 只改 CREATE TABLE DDL）
- 不修改 `procurement_projects.export_template_type` 的 DEFAULT 值

---

## 驗收條件

1. `migrations/005_expand_project_type_checks.sql` 套用後，existing DB 的 `procurement_projects.project_type` 與 `export_templates.project_type` 接受四種合法值。
2. Fresh DB（從零套用 001→002→003→004→005）可建立 `local_culture_jh` / `general_books_jh` 專案。
3. Fresh DB 可在 `export_templates` 插入 `local_culture_jh` / `general_books_jh`。
4. 既有 `local_culture` / `general_books` 資料在 005 migration 後仍完整保留。
5. 插入非合法 project_type（如 `invalid_type`）仍觸發 CHECK constraint failed。
6. `export_service.py` 錯誤訊息不再提及 `config.yaml`。
7. `pytest -q` 全部通過。
