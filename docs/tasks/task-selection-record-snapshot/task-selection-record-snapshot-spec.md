# Spec: task-selection-record-snapshot

## 目標

將採購專案選書紀錄從「依賴 vendor_books 外鍵才能顯示書目資料」改為「自含正規化書目快照」。使用者把書加入選書時，系統將 vendor_books 中已 mapping 的固定正規化欄位複製到 selection_items。之後即使 vendor_books 被清除或重匯，採購專案仍可正常列表、統計、驗證、匯出，不遺失任何採購紀錄。

## 需求範圍

### 資料來源與採購紀錄的責任邊界

- **來源資料**（可清除、可重匯）：`vendor_books`、`library_holdings`、`import_batches`、`book_matches`。每年採購作業可能使用新書商 Excel，欄位名稱可能改變，舊資料可被整批清除。
- **採購紀錄**（須長期保存）：`procurement_projects`、`selection_items`。採購專案代表特定年度的選書決定，需跨年度可追溯，不應因來源資料異動而失效。

書商書單是**工具**，採購紀錄才是**目的**。工具可以每年更換，目的必須永久保存。

### 目前問題

1. `selection_items.vendor_book_id` 為 `NOT NULL REFERENCES vendor_books(id)`，FK 強制依賴導致：
   - 刪除 vendor_books 前需先刪 selection_items（`_clear_vendor_books_for_project()` 目前即如此）
   - 重匯書商書單等同於清除採購選書紀錄
2. 選書列表、統計、匯出、驗證均 `JOIN vendor_books`，vendor_books 不存在時功能完全失效。
3. 書商 Excel 欄位名稱可能每年不同，若只存 `raw_row` 或原始欄位名稱，後續無法穩定追溯固定語意。
4. 使用者人工修正（user_overrides）目前寫回 `vendor_books.user_overrides`，這是來源資料的欄位，不適合作為採購紀錄長期保存。

### 核心設計原則

- **固定正規化欄位為主資料**：選書時將 title、isbn、list_price、purchase_price、award_item 等以固定欄位名稱寫入 selection_items，不依賴 JOIN 才能讀到。
- **JSON 欄位為追溯補充**：`raw_row`、`extra_fields`、`book_snapshot` 只作追溯，不可作為功能主要資料來源。
- **vendor_book_id 改為弱關聯**：nullable，且不設 REFERENCES FK，只作來源追蹤。專案功能不依賴此欄位。
- **user_overrides 屬於選書紀錄**：儲存在 `selection_items.user_overrides`，不在 `vendor_books.user_overrides`。
- **清除 vendor_books 不得刪除 selection_items**：`_clear_vendor_books_for_project()` 只清除書商書目與比對資料，selection_items 保持不動。
- **數量更新不覆蓋快照**：更新 selected_quantity / notes 時，不覆蓋既有書目快照欄位，避免來源資料後續變更影響採購紀錄。

### selection_items 正規化欄位定義

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | INTEGER PK | 主鍵 |
| `project_id` | INTEGER NOT NULL | 採購專案 ID（REFERENCES procurement_projects） |
| `vendor_book_id` | INTEGER | 來源書商書目 ID（nullable，弱關聯，不設 REFERENCES） |
| `source_batch_id` | INTEGER | 來源匯入批次 ID（nullable，snapshot 用） |
| `source_original_filename` | TEXT | 來源 Excel 檔案名稱（nullable） |
| `source_row_number` | INTEGER | 來源資料列號（nullable） |
| `selected_quantity` | INTEGER NOT NULL DEFAULT 0 | 採購數量（正式，由 selected_quantity × price 計算金額） |
| `notes` | TEXT | 備註 |
| `title` | TEXT | 書名（快照） |
| `author` | TEXT | 作者（快照） |
| `publisher` | TEXT | 出版社（快照） |
| `isbn` | TEXT | 原始 ISBN（快照） |
| `isbn_normalized` | TEXT | 正規化 ISBN（快照） |
| `isbn_status` | TEXT | ISBN 狀態：valid / missing / invalid（快照） |
| `publish_date` | TEXT | 出版日期（快照） |
| `list_price` | REAL | 定價（快照） |
| `purchase_price` | REAL | 單價（快照） |
| `award_item` | TEXT | 獲獎項目（快照） |
| `vendor_seq` | TEXT | 書商排序號（快照） |
| `age_range` | TEXT | 適合年齡（快照） |
| `category` | TEXT | 大分類，例如「語文類」、「國內史地傳記類」（快照） |
| `book_type` | TEXT | 書本類型/細分類路徑，例如「童書/青少年文學>橋樑書>校園生活」（快照） |
| `policy_topic` | TEXT | 議題分類，例如「品德教育」、「閱讀素養教育」（快照） |
| `summary` | TEXT | 書籍摘要，來源可能是 summary_80_120（快照） |
| `source_url` | TEXT | 書籍來源或查詢連結（快照） |
| `recommendation_source` | TEXT | 推薦來源模板，例如「喜閱網」（快照） |
| `eligibility_label` | TEXT | 採購資格標籤，例如「必選」、「推薦」（快照） |
| `award_notes` | TEXT | 推薦、SEL、SDGs 等補充標籤（快照） |
| `completeness_status` | TEXT | 完整度狀態（選書時計算並寫入） |
| `match_status_at_selection` | TEXT | 選書時的館藏比對狀態（nullable，快照，供 vendor_books 清除後仍可判斷） |
| `holding_id_at_selection` | INTEGER | 選書時對應的館藏 ID（nullable） |
| `user_overrides` | TEXT | 使用者人工修正（JSON，選書紀錄層級） |
| `extra_fields` | TEXT | 非標準欄位補充（JSON） |
| `raw_row` | TEXT | 來源 Excel 原始列資料（JSON，追溯用） |
| `book_snapshot` | TEXT | 選書當下 vendor_books 完整快照（JSON，追溯用） |
| `created_by` | INTEGER | 操作者 user_id |
| `created_at` | TEXT NOT NULL | 建立時間（ISO 8601） |
| `updated_at` | TEXT NOT NULL | 更新時間（ISO 8601） |

**關於來源 Excel 的 `數量` 與 `總價`**：不作為採購正式數量/金額。`selected_quantity` 才是正式採購數量，金額由 `selected_quantity × price` 計算。來源 Excel 的原始數量與總價保留在 `raw_row`，不新增 `source_quantity` / `source_total_price` 欄位（可在後續版本評估）。

### 需同步新增至 vendor_books 的欄位

為讓匯入後可在 vendor_books 中保存正規化資料，並供後續選書 snapshot 複製，需在 vendor_books 新增：

| 欄位 | 說明 |
|------|------|
| `category` | 大分類 |
| `book_type` | 書本類型/細分類路徑 |
| `summary` | 書籍摘要（來源：summary_80_120 等欄位） |
| `source_url` | 書籍來源或查詢連結 |
| `recommendation_source` | 推薦來源模板 |
| `eligibility_label` | 採購資格標籤 |

（`policy_topic` 與 `award_notes` 在 vendor_books 中已存在，本任務不重複新增。）

### VENDOR_COLUMN_HINTS 需新增的映射

| 系統欄位 | 來源候選名稱 |
|---------|------------|
| `category` | 分類、category |
| `book_type` | 類型、書本類型、book_type |
| `summary` | summary_80_120、摘要、summary |
| `source_url` | 連結、url、link、source_url |
| `recommendation_source` | award_template、推薦來源、recommendation_source |
| `eligibility_label` | eligible_label、資格標籤、必選推薦、eligibility_label |

### 功能層行為規範

- **選書列表（get_selected_books）**：以 selection_items 快照欄位為主資料，可 LEFT JOIN vendor_books 補充「書商書目是否仍存在」，但書名、ISBN、價格等不可依賴 JOIN。
- **統計（get_selection_summary）**：讀 si.list_price、si.purchase_price、si.user_overrides，不 JOIN vendor_books。
- **匯出（export_local_culture）**：讀 si.* 快照欄位，不 JOIN vendor_books 作為必要資料來源。
- **驗證（check_export_readiness）**：讀 si.title、si.isbn_normalized、si.isbn_status、si.list_price、si.purchase_price、si.award_item，user_overrides 讀自 si.user_overrides。
- **人工修正 override**：透過新 API `PATCH /api/selections/{selection_id}/overrides` 寫入 `selection_items.user_overrides`。`vendor_books.user_overrides` 不再作為採購專案紀錄的主要 override 儲存位置。原 `PATCH /api/books/{book_id}/overrides` 保留相容但不再是選書修正主要入口。
- **人工修正 override 前端 MVP 行為**：已加入選書的書目，前端編輯時應呼叫 `PATCH /api/selections/{selection_id}/overrides`，傳入 `selection_id`（selection_items.id）。尚未加入選書的候選書，MVP 規劃為「先加入選書，再編輯」，不實作「直接在候選書上編輯後建立 selection_item」的流程。`selection.html` 現有呼叫 `PATCH /api/books/{book_id}/overrides` 的前端 JS 本 task 暫不修改，向後相容保留，但不應再作為採購紀錄的主要 override 寫入路徑。

### 前端 ID 對應注意事項

`selection.html` 目前以 `b.id`（vendor_books.id）識別候選書，並以是否存在對應 `vendor_book_id` 的 selection_item 判斷已選狀態。snapshot 後 `/api/selections/` 回傳需明確區分：

- `id`（候選書列表）：代表 vendor_books.id，供加入選書操作使用。
- `sel_id`（或 `selection_id`）：代表 selection_items.id，供更新數量、override、刪除操作使用。
- `vendor_book_id`：selection_items 儲存的來源書商 ID，可為 NULL（手動建立紀錄時）。

前端 `selMap` 應以 `vendor_book_id` 作為識別鍵（對應候選書的 `b.id`），不以 `sel_id` 作為鍵，避免 selection_items.id 與 vendor_books.id 混用。已選書的操作（更新數量、override、刪除）應以 `selection_id`（sel_id）為主。候選書加入選書仍用 vendor_book_id（即目前的 `b.id`）。

### 匯出頁面相容性

`export-check.html` 與 `export.html` 依賴 API 回傳欄位；snapshot 後資料來源改為 selection_items，回傳欄位名稱應保持向後相容：

| 頁面 | 依賴欄位 | 變更後資料來源 |
|------|---------|-------------|
| `export-check.html` | `vendor_book_id`、`title`、`match_status`、`completeness_status` | 改讀 si.*；match_status 改用 COALESCE(即時 bm.match_status, si.match_status_at_selection) |
| `export.html` | `user_overrides`、`selected_quantity`、`list_price`、`purchase_price` | 改讀 si.user_overrides、si.list_price、si.purchase_price |

目標：API 回傳欄位名稱不變，僅資料來源從 vendor_books JOIN 改為 selection_items 快照欄位。若欄位需要改名（例如 match_status → resolved_match_status），須在 API 層同時回傳舊欄位名稱以維持相容。

## 不做的事

- 不建立正式「清除書商書單」或「清除館藏」UI（只修正 _clear_vendor_books_for_project 使其不刪 selection_items）
- 不重設整個資料庫
- 不改變書商書單匯入 wizard 的整體流程與 UI
- 不支援跨年度專案彙總報表（但資料模型保留長期追溯能力）
- 不新增 `source_quantity` / `source_total_price` 欄位（可在 V2 評估）
- 不刪除 `PATCH /api/books/{book_id}/overrides`（保留相容）
- 不修改 `selection.html` 前端的 override 呼叫邏輯（現有呼叫 `PATCH /api/books/{book_id}/overrides` 的 JS 本 task 暫不修改；MVP 行為為先加入選書再編輯）

## 驗收條件

1. **資料不遺失**：migration 完成後，既有 selection_items 紀錄（project_id、selected_quantity、notes）不遺失。
2. **快照可讀**：手動刪除 vendor_books 與相關 import_batches 後，selection 列表仍可顯示書名、ISBN、價格、數量、category、book_type、summary。
3. **統計正確**：總金額（total_list_price、total_purchase_price）在 vendor_books 刪除後仍可正確計算。
4. **驗證可執行**：`check_export_readiness` 在 vendor_books 刪除後可正常執行，不報錯。
5. **匯出可產生**：`export_local_culture` 在 vendor_books 刪除後可產生正確 Excel。
6. **重匯不覆蓋快照**：重新匯入新的書商書單後，既有 selection_items 快照欄位不被覆蓋。
7. **清空選書不影響來源**：`clear_all_selections` 只刪 selection_items，不影響 vendor_books。
8. **新欄位可匯入並快照**：使用含 category、book_type、summary、source_url、recommendation_source、eligibility_label 欄位（例如 `必選推薦-欄位調整-topic-summary-v6-final.xlsx`）匯入後加入選書，snapshot 中可查到這些欄位的值。
9. **語法無錯誤**：`python -m compileall app` 無錯誤。
