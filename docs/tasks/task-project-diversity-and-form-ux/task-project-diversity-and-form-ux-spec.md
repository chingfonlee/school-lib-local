# Spec: task-project-diversity-and-form-ux

## 目標

擴充採購專案資料模型與操作體驗，讓系統除了既有 4 種制式補助案（國小／國中本土文化、國小／國中一般圖書）外，也能支援校內自籌、家長會補助或一般通用採購，同時簡化新建專案、計價設定與跨年度專案管理流程，並確保 100% 向後相容、零新增第三方套件。

## 需求範圍

### 1. 通用／自訂採購類型（`custom`）與內建通用 Excel 匯出

- **資料庫 Migration（`migrations/012_project_diversity_fields.sql`）**：
  - 比照 `005_expand_project_type_checks.sql` 的安全重建模式（包 `PRAGMA foreign_keys = OFF;`、交易與結尾恢復 `PRAGMA foreign_keys = ON;`），重建 `procurement_projects`：
    - `project_type` CHECK 擴充為 `('local_culture', 'general_books', 'local_culture_jh', 'general_books_jh', 'custom')`。
    - 新增 4 個選填／預設欄位：`academic_year TEXT`、`funding_source TEXT`、`project_notes TEXT`、`is_archived INTEGER NOT NULL DEFAULT 0`。
    - 完整保留所有既有專案資料與主鍵 `id`。
- **完整度與匯出前檢核支援 `custom`**：
  - `app/services/completeness_service.py`：當 `project_type == "custom"` 時，必填僅為「書名」與「任一價格（定價或採購單價）」；不強制檢查 `award_item`、`eligibility_label` 或 `recommendation_source`；若缺作者或出版社則標記 `needs_review`，其餘為 `export_ready`。
  - `app/services/validation_service.py`：當 `project_type == "custom"` 時，阻擋匯出的必填僅為「書名」、「計價欄位價格 > 0」、「採購數量 > 0」；不擋 `GENERAL_BOOKS_H_ALLOWED` 獲獎名稱或無效／缺失 ISBN；缺作者、出版社或 ISBN 僅列入 `missing_review_fields`（`needs_review` 提示）。
- **內建通用 Excel 匯出（`export_generic_books`）**：
  - `app/services/export_service.py` 新增 `export_generic_books(settings: ExportSettings) -> str`，直接使用既有依賴 `openpyxl` 產生格式整齊的 `.xlsx`（檔名 `通用採購書單_{ts}_{uuid6}.xlsx`），免上傳空白範本即可匯出。
  - 工作表內容包含：標題列（專案名稱）、專案資訊列（校名、年度、經費來源、核定金額，有值才顯示）、表頭列（序號、書名、作者、出版社、ISBN、數量、單價、小計、備註）、書目資料列（ISBN 以文字格式寫入避免科學記號、單價與小計依 `price_field` 與 `subtotal_mode` 計算）與合計列（總數量、總金額）。
  - 延用既有可匯出過濾條件（`available` / `missing_isbn` / `invalid_isbn` 或 `already_owned` 且 `force_owned=true`），並同樣寫入 `export_jobs`（`template_path = 'generic_builtin'`、`export_template_id = NULL`）。

### 2. 採購類型與匯出範本解耦

- **專案 API 擴充（`app/routers/projects.py`）**：
  - `ProjectCreate` 支援選填 `export_template_type`（允許值：`generic_builtin`、`local_culture`、`general_books`、`local_culture_jh`、`general_books_jh`；未提供時，`custom` 預設為 `generic_builtin`，其餘預設等同 `project_type`），並支援選填 `academic_year`、`funding_source`、`project_notes`、`is_archived`。
  - `ProjectUpdate` 支援更新 `export_template_type`、`academic_year`、`funding_source`、`project_notes`、`is_archived`（允許以 `null` 或空字串清除選填文字欄位）。
  - 既有專案因 `export_template_type == project_type`，行為 100% 向後相容。
- **匯出路由解耦（`app/routers/exports.py`）**：
  - `POST /api/exports/local-culture` 改依專案的 `export_template_type`（而非寫死 `project_type`）分派：
    - `generic_builtin`（或 `project_type == 'custom'` 且未指定其他範本）→ `export_generic_books(settings)`
    - `general_books` / `general_books_jh` → `export_general_books(settings)`
    - `local_culture` / `local_culture_jh` → `export_local_culture(settings)`
- **前端表單與匯出頁對應**：
  - `app/static/js/common.js` 補上 `custom` 標籤（`通用／自訂採購`）、匯出範本顯示名稱函式與各採購類型的一行檢核規則說明。
  - `app/static/projects.html` 新增／編輯專案表單提供「匯出範本」下拉選單，動態讀取 `/api/admin/templates` 已設定範本並固定包含內建「通用採購清單（免範本）」。切換採購類型時自動預帶推薦範本並更新一行檢核規則說明。
  - `app/static/export.html` 依 `proj.export_template_type` 判斷校名是否必填與欄位標題（使用 `generic_builtin` 時校名為選填並顯示使用內建通用格式提示）。
  - `app/static/export-check.html` 針對 `custom` 類型顯示貼合通用規則的缺少欄位提示文字。

### 3. 專案管理欄位、採購備忘與結案封存

- **專案列表與卡片（`app/static/projects.html`）**：
  - 新增／編輯表單提供選填欄位：年度（`academic_year`）、經費來源（`funding_source`）、採購規則備忘（`project_notes`）。
  - 專案卡片顯示年度標籤、經費來源標籤、匯出範本名稱與採購備忘摘要（皆經 `esc()` 跳脫）。
  - 卡片提供「封存」／「取消封存」按鈕，透過 `PUT /api/projects/{id}` 切換 `is_archived`。
  - 工具列提供「顯示已封存專案」開關（顯示已封存數量），預設關閉以保持首頁清爽；已封存專案於顯示時加上「已封存」標籤與淡化樣式。
  - 封存專案不影響 `app/routers/books.py` 的「他案已選／已匯出」跨專案防重複比對。
- **選書頁採購備忘提示（`app/static/selection.html`）**：
  - 若當前專案有 `project_notes`，於選書頁上方顯示精簡提示條呈現備忘內容。

### 4. 白話計價設定與一鍵複製專案設定

- **白話計價基準（`app/static/projects.html`）**：
  - 新增與編輯表單預設顯示白話「計價基準」下拉選單：
    - `依實付單價（折後價）`（同步設定 `price_field = purchase_price`、`subtotal_mode = quantity_times_purchase_price`）
    - `依書本定價`（同步設定 `price_field = list_price`、`subtotal_mode = quantity_times_list_price`）
    - 若專案原設定為混搭模式，則顯示 `自訂進階設定` 並自動展開進階區。
  - 原有 `price_field` 與 `subtotal_mode` 下拉選單收進可展開的 `<details>`「進階計價設定」折疊區，保留既有元素 ID 與後端欄位 100% 相容。
- **一鍵複製專案設定（`app/static/projects.html`）**：
  - 專案卡片新增「複製設定」按鈕，點擊後展開新建專案表單，預填該專案的採購類型、匯出範本、計價設定、年度、經費來源與採購備忘，並於專案名稱帶入 `{原名稱} (複製)` 方便老師修改年度後直接建立。

## 不做的事

- 不新增任何第三方 Python 或前端套件（沿用既有 `openpyxl`、FastAPI、原生 JS）。
- 不建立通用自訂驗證規則引擎（維持 3 套明確檢核規則：本土文化、一般圖書、通用自訂）。
- 不修改 `selection_items`、`vendor_books`、`library_holdings`、`book_matches`、`export_templates` 的資料表結構。
- 不實作批次複製選書清單（複製設定僅複製專案設定，不複製舊專案的選書項目）。
- 不更動既有 4 種制式補助案的匯出範本格式與欄位檢核邏輯。

## 驗收條件

1. **Migration 與資料相容**：既有資料庫執行 `migrations/012_project_diversity_fields.sql` 後，既有專案 `id` 與欄位值完整保留，新增欄位預設正確（`is_archived = 0`、`academic_year/funding_source/project_notes = NULL`），且可成功建立 `project_type = 'custom'` 的專案。
2. **檢核規則正確**：`custom` 專案在 `completeness_service.compute()` 與 `validation_service.check_export_readiness()` 中，缺獲獎名稱或無效 ISBN 不阻擋匯出（僅提示 `needs_review`），缺書名、價格 <= 0 或數量 <= 0 才標記阻擋；既有 4 種 `project_type` 行為完全不變。
3. **內建通用匯出與範本解耦**：
   - `export_template_type == 'generic_builtin'` 不需任何 `export_templates` 記錄即可成功匯出格式完整的 `.xlsx`（含標題、校名／年度／經費來源／核定金額、表頭、書目列、合計列），並於 `export_jobs` 記錄 `template_path = 'generic_builtin'`、`export_template_id = NULL`。
   - 專案 `project_type` 與 `export_template_type` 可獨立搭配（例如 `local_culture` 搭配 `generic_builtin` 或 `custom` 搭配已設定的 `local_culture` 範本），`POST /api/exports/local-culture` 依 `export_template_type` 正確路由。
4. **專案封存與防重相容**：透過 `PUT /api/projects/{id}` 可切換 `is_archived`；首頁預設隱藏已封存專案、開啟開關後可檢視並取消封存；已封存專案的選書仍持續出現在 `books.py` 的 `other_project_selections` 與 `other_project_duplicate_count` 防重結果中。
5. **前端體驗與安全**：
   - `projects.html` 支援動態匯出範本選單、切換類型自動預帶推薦範本與規則說明、白話計價基準＋進階折疊區、年度／經費來源／備忘顯示與一鍵複製設定。
   - `selection.html` 在專案有 `project_notes` 時顯示採購備忘提示條，無備忘時不顯示。
   - 所有動態輸出均經 `esc()` 跳脫，無 JS 語法錯誤。
6. **全套驗證通過**：`compileall`、`ruff check`、`ruff format --check`、`mypy`、`pytest -q` 與前端 JS `node --check` 全部通過。
