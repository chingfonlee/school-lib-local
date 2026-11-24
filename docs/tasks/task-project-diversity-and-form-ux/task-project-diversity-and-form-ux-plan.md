# Plan: task-project-diversity-and-form-ux

## 實作步驟

1. **新增資料庫 Migration（`migrations/012_project_diversity_fields.sql`）**
   - 比照 `005_expand_project_type_checks.sql`，以 `PRAGMA foreign_keys = OFF;`、重建 `procurement_projects_new`、搬移所有既有欄位與資料、`DROP` + `RENAME`、`PRAGMA foreign_keys = ON;` 完成安全升級。
   - 擴充 `project_type` CHECK 為 `('local_culture', 'general_books', 'local_culture_jh', 'general_books_jh', 'custom')`，並新增 `academic_year TEXT`、`funding_source TEXT`、`project_notes TEXT`、`is_archived INTEGER NOT NULL DEFAULT 0`。
2. **擴充完整度與匯出前檢核服務（`completeness_service.py`、`validation_service.py`）**
   - 在 `app/services/completeness_service.py` 新增 `project_type == "custom"` 分支：僅檢查書名與價格，缺作者或出版社時回傳 `needs_review`，其餘回傳 `export_ready`。
   - 在 `app/services/validation_service.py` 新增 `project_type == "custom"` 分支：只對書名、計價價格 > 0、數量 > 0 做 `missing_blocking`；將缺作者、出版社、無效／缺失 ISBN 列入 `missing_review`，不檢核 `GENERAL_BOOKS_H_ALLOWED`。
3. **新增內建通用 Excel 匯出（`app/services/export_service.py`）**
   - 新增 `export_generic_books(settings: ExportSettings) -> str`，以 `openpyxl.Workbook()` 產生格式整齊的通用採購書單 `.xlsx`（標題、校名／年度／經費來源／核定金額、9 欄表頭、資料列與文字格式 ISBN、合計列、欄寬與框線樣式）。
   - 延用 `_fetch_selection_items_for_export` 與 `force_owned` 過濾規則，並寫入 `export_jobs`（`template_path = 'generic_builtin'`、`export_template_id = NULL`）。
4. **擴充專案與匯出路由（`app/routers/projects.py`、`app/routers/exports.py`）**
   - `app/routers/projects.py`：
     - 定義 `VALID_PROJECT_TYPES` 與 `VALID_EXPORT_TEMPLATE_TYPES`。
     - `ProjectCreate` 與 `ProjectUpdate` 加入 `export_template_type`、`academic_year`、`funding_source`、`project_notes`、`is_archived`，並做好欄位驗證與字串清理（空字串轉 `None`）。
     - `POST /api/projects/` 回傳 `{"id": project_id, "name": body.name}`（向後相容並修復既有前端取 `created.name` 的問題）。
     - `GET /api/projects/` 排序調整為 `ORDER BY p.is_archived ASC, p.created_at DESC`。
   - `app/routers/exports.py`：
     - `do_export` 查詢 `project_type` 與 `export_template_type`，依 `export_template_type`（或 `custom` 預設 `generic_builtin`）路由至 `export_generic_books`、`export_general_books` 或 `export_local_culture`。
5. **更新前端共用工具與頁面（`common.js`、`projects.html`、`selection.html`、`export-check.html`、`export.html`）**
   - `app/static/js/common.js`：加入 `custom` 標籤、`exportTemplateLabel()` 與 `projectTypeRuleHint()`。
   - `app/static/projects.html`：
     - 載入 `/api/admin/templates` 動態組裝「匯出範本」選單（含內建 `generic_builtin`）；切換採購類型時自動帶入推薦範本與一行規則說明。
     - 新建與編輯表單改以白話「計價基準」為主，將原 `price_field` / `subtotal_mode` 收納於 `<details>`「進階計價設定」折疊區，並雙向同步。
     - 加入年度、經費來源、採購備忘輸入欄，於專案卡片顯示標籤與摘要。
     - 加入「複製設定」、「封存／取消封存」按鈕與「顯示已封存專案」開關（預設隱藏已封存專案）。
   - `app/static/selection.html`：載入專案後若 `proj.project_notes` 非空，於頁面上方顯示精簡採購備忘提示條。
   - `app/static/export.html` 與 `app/static/export-check.html`：依 `export_template_type` 與 `project_type` 調整 `generic_builtin`／`custom` 的表單必填與提示文字。
6. **撰寫完整測試與執行全套驗證**
   - 新增 `tests/test_project_diversity_and_form_ux.py`，覆蓋：
     - Migration 012 升級與既有資料保留。
     - `custom` 專案建立、更新（含清除選填欄位）、封存切換與防重比對保留（`books.py`）。
     - `completeness_service` 與 `validation_service` 在 `custom` 與既有類型下的行為。
     - `export_generic_books` 產出 `.xlsx` 結構、金額計算、`export_jobs` 紀錄，以及 `exports.py` 依 `export_template_type` 解耦路由。
     - 前端頁面結構與內嵌 JS 語法檢查。
   - 執行全套 5 項驗證指令（含 `node --check` 檢查 `common.js` 與相關 HTML 內嵌 JS），確認全部通過。

## 風險與注意事項

- **SQLite 重建資料表外鍵安全**：`migrations/012_project_diversity_fields.sql` 重建 `procurement_projects` 時必須先 `PRAGMA foreign_keys = OFF;`，完整複製所有欄位與主鍵 `id` 後再 `PRAGMA foreign_keys = ON;`，避免 `selection_items`、`export_jobs`、`import_batches` 外鍵受影響。
- **既有 API 與前端相容**：
  - 既有客戶端或測試呼叫 `POST /api/projects/` 不帶 `export_template_type` 時，必須維持原預設行為（既有 4 類型預設 `export_template_type = project_type`；`custom` 預設 `generic_builtin`）。
  - `projects.html` 折疊區保留 `#new-price-field`、`#new-subtotal`、`#edit-price-field`、`#edit-subtotal` 原有 ID，確保任何既有腳本或操作不受影響。
- **封存專案與目前使用中專案**：若使用者封存當前已選擇的專案，仍可透過開啟「顯示已封存專案」存取或取消封存，且不主動破壞該專案資料；跨專案防重比對（`books.py`）不得過濾 `is_archived = 1`。
- **ISBN 科學記號問題**：`export_generic_books` 寫入 ISBN 儲存格時需明確設為字串型別並指定 `number_format = "@"`，避免 Excel 自動轉成科學記號。
- **XSS 防護**：年度、經費來源、採購備忘等使用者輸入文字在 `projects.html` 與 `selection.html` 呈現時必須全部使用 `esc()` 跳脫。

## 預計影響範圍

- `migrations/012_project_diversity_fields.sql`（新增）
- `app/services/completeness_service.py`（修改）
- `app/services/validation_service.py`（修改）
- `app/services/export_service.py`（修改）
- `app/routers/projects.py`（修改）
- `app/routers/exports.py`（修改）
- `app/static/js/common.js`（修改）
- `app/static/projects.html`（修改）
- `app/static/selection.html`（修改）
- `app/static/export-check.html`（修改）
- `app/static/export.html`（修改）
- `tests/test_project_diversity_and_form_ux.py`（新增）
- `docs/STATUS.md`、`docs/BACKLOG.md`、`docs/tasks/task-project-diversity-and-form-ux/*`（任務紀錄）

## 驗證指令

- compile: `.venv\Scripts\python.exe -m compileall -q app run_server.py setup_first_run.py`
- lint: `.venv\Scripts\python.exe -m ruff check app tests run_server.py setup_first_run.py`
- format: `.venv\Scripts\python.exe -m ruff format --check app/routers/projects.py app/routers/exports.py app/services/completeness_service.py app/services/validation_service.py app/services/export_service.py tests/test_project_diversity_and_form_ux.py`
- typecheck: `.venv\Scripts\python.exe -m mypy app/logging_config.py app/database.py app/main.py app/config.py app/auth.py app/routers/backup.py app/routers/projects.py app/services/isbn_service.py app/services/completeness_service.py app/services/match_service.py app/services/validation_service.py run_server.py`
- test: `.venv\Scripts\python.exe -m pytest -q`
- js-check: `node --check app/static/js/common.js`（以及以 node 驗證 `projects.html`、`selection.html`、`export-check.html`、`export.html` 內嵌 `<script>` 語法）

## 成果報告

- result_report_mode: none
- 適用情境：一般功能擴充與前端體驗優化，驗證結果直接於回覆與 log 記錄即可。
- 報告路徑（若 mode 非 none）：`docs/reports/task-project-diversity-and-form-ux/`
