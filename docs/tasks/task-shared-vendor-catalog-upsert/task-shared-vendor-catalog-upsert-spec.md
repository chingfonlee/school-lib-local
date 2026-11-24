# Spec: task-shared-vendor-catalog-upsert

## 目標

將書商書單從單一專案綁定升級為**全校共用長期書單池（模式 B）**，讓各年度與各補助案能共享累積的多家書商書目資料庫；同時支援依「書商名稱 + ISBN」進行增量更新（保留老師既有的手動補齊與獲獎整理結果）、跨書商同 ISBN 比價提示、他案「已匯出／選書中」狀態區分，以及上傳書單時自動推薦既有的欄位設定檔（`import_profiles`）。

## 需求範圍

### 1. 全校共用長期書單池（模式 B）與向後相容

- **Schema 擴充（`migrations/010_shared_vendor_catalog.sql`）**：
  - `import_batches` 新增 `vendor_name TEXT` 欄位，並建立複合索引 `idx_import_batches_batch_type_vendor ON import_batches(batch_type, vendor_name)`。
  - 沿用既有可為 `NULL` 的 `import_batches.project_id`；新匯入的書商書單批次一律以 `project_id = NULL` 寫入（與 `library_holdings` 一致）。
- **既有舊資料向後相容**：
  - 查詢共用書單池（比對、統計、選書、比價）時，以 `ib.batch_type = 'vendor_books'` 為範圍，**同時納入**新匯入的共用批次（`project_id IS NULL`）與舊專案已匯入的批次（`project_id IS NOT NULL`），不需破壞性資料搬遷，舊資料完全不遺失。
  - `vendor_name` 為 `NULL` 或空白的舊批次，於顯示與比對時統一正規化為 `未指定書商`。
- **刪除專案安全性（`app/routers/projects.py`）**：
  - `DELETE /api/projects/{project_id}` 不再刪除任何書商書單資料；僅刪除該專案的 `selection_items` 與 `export_jobs`（以及若有綁定該專案的舊館藏批次）。
  - 若該專案仍掛有舊版非共用書商批次（`batch_type = 'vendor_books' AND project_id = ?`），於刪除專案前將其 `project_id` 更新為 `NULL` 併入共用書單池，避免外鍵錯誤或誤刪共用書單。
  - `GET /api/projects/{project_id}/delete-preview` 與 `projects.html` 刪除確認視窗明確告知共用書單庫會保留，僅刪除該專案的選書與匯出紀錄。
- **專案列表摘要（`GET /api/projects/`）**：
  - `vendor_book_count`、`already_owned_count`、`last_import` 改反映全校共用書單池狀態，讓新建專案即可直接進入選書，不必重複匯入同一批書單。
- **依專案類型動態計算完整度**：
  - 共用書單可能同時被本土文化（`local_culture*`）與一般圖書（`general_books*`）專案使用；`GET /api/books/matches` 與 `GET /api/books/stats` 依目前查詢的 `project_id` 所屬 `project_type` 計算各書目當下適用的 `completeness_status`。
  - `completeness_service.recompute_for_book()` 改用 `LEFT JOIN procurement_projects` 並支援傳入 `project_type`，避免 `import_batches.project_id IS NULL` 時查無資料。

### 2. 多書商累加、依 ISBN 增量更新（Upsert）與書商清理管理

- **書商名稱與匯入模式（`confirm_import` / `POST /api/imports/vendor-books/confirm`）**：
  - 新增參數 `vendor_name`（去除前後空白，若未提供則預設 `未指定書商`）與 `import_mode`（`upsert` 預設 / `replace_vendor`）；`project_id` 改為選填（僅供獲獎整理與初始完整度計算參考）。
  - **`upsert`（合併更新，預設）**：
    - 以同 `vendor_name` + 同 `isbn_normalized`（且 `isbn_status = 'valid'`）比對既有書商書目。
    - 命中既有書目時，**原地更新（UPDATE）**價格（`list_price`、`purchase_price`）、基本書目欄位、最新 `batch_id` 與 `raw_row`（保留原 `vendor_books.id` 以維持既有 `selection_items` 關聯）。
    - **保留老師手動補齊資料**：絕不覆寫既有的 `user_overrides`，並統計 `preserved_override_count`。
    - **保留既有獲獎整理結果**：若本次匯入未提供新的 `award_overrides` 覆寫，保留既有非空的 `recommendation_source`、`eligibility_label`、`award_notes`。
    - 未命中既有書目（新 ISBN 或無有效 ISBN）則新增（INSERT）。
    - 若同一份匯入檔內含重複 ISBN，依後列更新前列原則避免同書商產生重複列。
    - 回傳 `batch_id`、`vendor_name`、`import_mode`、`record_count`（`inserted_count + updated_count`，維持向後相容）、`inserted_count`、`updated_count`、`preserved_override_count`、`skipped_count`、`match_stats`。
  - **`replace_vendor`（取代指定書商）**：
    - 僅清除該 `vendor_name` 既有的 `vendor_books`、對應 `book_matches` 與所屬 `import_batches`，完全不影響其他書商的書單與既有 `selection_items` 快照，再匯入本次書單。
- **全校館藏比對同步（`app/services/match_service.py`）**：
  - `run_match(project_id: int | None = None)` 改對全校共用書單池所有有效 ISBN 書目執行館藏比對（維持既有 `project_id` 選填簽名確保向後相容）。
  - 匯入館藏或書商書單後自動執行一次全校書單比對。
- **書商清單與清除管理 API / UI**：
  - 新增 `GET /api/imports/vendors`，回傳共用書單庫中各書商名稱、書目筆數、批次數與最後匯入時間。
  - 擴充 `DELETE /api/imports/vendor-books` 支援指定 `vendor_name` 單獨清除該書商書單，或指定 `clear_all=true` 清空全部共用書單庫（皆保留所有 `selection_items` 快照，並回傳 `preserved_selection_items`）。
  - `import.html` 書商書單分頁不再強制要求先選專案才能匯入；提供書商名稱輸入（含既有書商 `<datalist>` 建議）、匯入模式切換、匯入明細結果顯示，以及指定書商清除／清空全部共用書單庫操作（含雙重確認）。

### 3. 跨書商比價、書商篩選與他案狀態區分

- **跨書商同 ISBN 比價提示（`other_vendor_offers`）**：
  - `GET /api/books/matches` 對共用書單池中同 `isbn_normalized` 出現於多家書商的書目，回傳 `other_vendor_offers` 陣列，每筆包含 `vendor_book_id`、`vendor_name`、`purchase_price`、`list_price`（依有效價格由低到高排序，不含自身）。
  - `selection.html` 書目卡片顯示書商標籤，並於 `other_vendor_offers` 非空時顯示「多家供貨／比價提示」（列出其他書商與單價／定價，若有更低價以清楚標示提醒）。
- **書商篩選**：
  - `GET /api/books/matches` 與 `GET /api/books/stats` 支援 `vendor_name` 篩選參數。
  - `selection.html` 與 `match.html` 皆新增「書商」篩選下拉選單，並於 `match.html` 表格顯示書商欄位。
- **他案已匯出 vs 選書中區分**：
  - `GET /api/books/matches` 回傳的 `other_project_selections` 項目新增 `has_exported: bool`（依該專案於 `export_jobs` 是否有匯出紀錄判定）。
  - `selection.html` 與 `match.html` 依 `has_exported` 區分顯示「他案已匯出」與「他案選書中」警示徽章。

### 4. 書商設定檔（`import_profiles`）自動推薦

- `preview_excel()` 讀取既有 `file_type = 'vendor_books'` 的 `import_profiles`，以正規化表頭計算各設定檔已對應來源欄位與上傳檔案表頭的重疊度。
- 若最高重疊度的設定檔達門檻（至少重疊 2 欄且重疊率 `>= 0.5`），回傳 `recommended_profile`（含 `id`、`name`、`header_row`、`mappings`、`extra_field_settings`、`matched_columns`、`total_profile_columns`、`overlap_ratio`）；否則回傳 `null`。
- `import.html` 欄位對應精靈顯示推薦提示橫幅與「一鍵套用」按鈕，點擊後自動套用對應欄位與額外欄位勾選。

## 不做的事

- 不在此 task 實作學校館藏增量匯入（依 ISBN + 登錄號去重）或採購完成一鍵回流館藏（屬於階段 3）。
- 不在此 task 處理 HTML 偽裝 `.xls`、貨幣符號（`NT$` / `元`）解析強化或無 ISBN 書名＋作者弱比對（屬於階段 3）。
- 不修改既有 `selection_items` 快照結構與 Excel 匯出範本／公式規則。
- 不引入額外第三方 Python 或前端套件（維持原生 FastAPI + SQLite + 靜態 HTML/JS/CSS）。

## 驗收條件

1. **共用書單池與向後相容**：
   - `migrations/010_shared_vendor_catalog.sql` 套用後，`import_batches` 具備 `vendor_name` 欄位與索引；新匯入書單 `project_id` 為 `NULL`。
   - 既有帶 `project_id` 的舊書商書單與新匯入的共用書單在 `GET /api/books/matches`、`GET /api/books/stats`、`selection.html`、`match.html` 皆可正常顯示與比對。
   - 刪除專案只刪除該專案的 `selection_items` 與 `export_jobs`，絕不刪除共用書單（含既有舊書商批次自動轉為共用保留）。
2. **多書商 Upsert 與單商取代**：
   - 匯入書商 A、書商 B 書單後，共用書單庫同時保留兩家書商書目。
   - 以 `import_mode=upsert` 再次匯入書商 A 更新價格與新書時：既有同 ISBN 更新價格與欄位、**既有 `user_overrides` 與獲獎整理欄位完好保留**、新書新增，且回傳正確的 `inserted_count`、`updated_count`、`preserved_override_count`、`skipped_count`。
   - 以 `import_mode=replace_vendor` 重新匯入書商 A 時，僅取代書商 A 書目，書商 B 與所有專案的 `selection_items` 不受影響。
   - 可透過管理 API 與 UI 單獨清除指定書商或清空全部共用書單庫，且 `selection_items` 快照保留。
3. **跨書商比價、書商篩選與他案狀態**：
   - 同 ISBN 出現於兩家以上書商時，`GET /api/books/matches` 回傳正確的 `other_vendor_offers`，且 `selection.html` 呈現比價提示。
   - `selection.html` 與 `match.html` 皆可依書商篩選。
   - `other_project_selections` 正確回傳 `has_exported`，前端明確區分「他案已匯出」與「他案選書中」。
4. **設定檔自動推薦**：
   - 上傳與既有 `import_profiles` 表頭重疊達門檻的 Excel 時，`POST /api/imports/vendor-books/preview` 回傳 `recommended_profile`，前端可一鍵套用對應。
5. **全套驗證通過**：
   - `compileall`、`ruff check`、`ruff format --check`、`mypy`、`pytest -q`（含前端 HTML `<script>` 的 `node --check` 檢查）全數通過。
