# Plan: task-shared-vendor-catalog-upsert

## 實作步驟

1. **新增資料庫遷移 `migrations/010_shared_vendor_catalog.sql`**
   - 於 `import_batches` 新增欄位 `vendor_name TEXT`。
   - 建立索引 `idx_import_batches_batch_type_vendor ON import_batches(batch_type, vendor_name)`。
   - 維持純 DDL 與索引（不更動既有資料列），由查詢層與刪除邏輯無縫相容舊版 `project_id IS NOT NULL` 批次。

2. **重構 `app/services/match_service.py` 與 `app/services/completeness_service.py` 支援共用書單池**
   - `match_service.run_match(project_id: int | None = None)`：
     - 改對所有 `ib.batch_type = 'vendor_books' AND vb.isbn_status = 'valid'` 的書目執行全校館藏比對，並在執行前清除該範圍既有的 `book_matches`。
     - 保留選填參數 `project_id: int | None = None` 以向後相容現有呼叫端與測試。
   - `completeness_service.recompute_for_book(vendor_book_id: int, project_type: str | None = None)`：
     - 將 `JOIN procurement_projects` 改為 `LEFT JOIN procurement_projects`，若呼叫端傳入 `project_type` 優先採用，否則回退至 `pp.project_type`（可為 `None`）。

3. **升級 `app/services/import_service.py` 支援共用書單池、Upsert、單商清除與設定檔推薦**
   - 新增共用常數與小工具：
     - `DEFAULT_VENDOR_NAME = "未指定書商"`、`normalize_vendor_name(vendor_name: str | None) -> str`。
     - `_recommend_import_profile(source_columns: list[str]) -> dict | None`：查詢 `import_profiles`（`file_type = 'vendor_books'`），計算正規化表頭重疊度（門檻：`matched_columns >= 2` 且 `overlap_ratio >= 0.5`），回傳最佳匹配；以安全錯誤處理確保無 DB 環境的純單元測試不受影響。
   - `preview_excel()`：回傳結果新增 `recommended_profile` 欄位。
   - 重構 `_insert_vendor_books_core()` 與 `confirm_import()`：
     - `project_id: int | None = None`、`vendor_name: str | None = None`、`import_mode: str = "upsert"`（僅允許 `upsert` / `replace_vendor`，非法值拋 `ValueError`）。
     - `import_batches` 以 `project_id = NULL` 與正規化後的 `vendor_name` 寫入。
     - `replace_vendor` 模式：呼叫 `_clear_vendor_books_by_vendor(conn, normalized_vendor)` 僅清除該書商既有書目與批次，再批次插入新書。
     - `upsert` 模式：預載該書商既有 `isbn_status = 'valid'` 的書目映射（同 ISBN 多筆時取最新 `id`），逐筆判定：
       - 命中同書商同 `isbn_normalized`：原地 `UPDATE vendor_books`，更新價格與最新欄位及 `batch_id`，**保留 `user_overrides`**（非空時 `preserved_override_count += 1`），若未提供 `award_overrides` 則保留既有非空的 `recommendation_source`、`eligibility_label`、`award_notes`，並以合併後資料重算 `completeness_status`。
       - 未命中：執行 `INSERT`，並於同批次內同步更新記憶體索引避免單檔重複 ISBN 產生多列。
     - 回傳 `batch_id`、`vendor_name`、`import_mode`、`record_count`、`inserted_count`、`updated_count`、`preserved_override_count`、`skipped_count`，並自動呼叫 `run_match()` 回傳 `match_stats`。
   - `import_vendor_books()`（舊單步匯入）：同步支援選填 `vendor_name`、`import_mode="upsert"` 並寫入共用書單池。
   - `import_library_holdings()`：館藏更新後呼叫一次 `run_match()` 重算全校共用書單比對結果，並保留回傳欄位向後相容。
   - 新增書商管理與清除函式：
     - `list_vendors() -> list[dict]`：彙整共用書單池各書商之 `vendor_name`、`book_count`、`batch_count`、`last_imported_at`。
     - `clear_vendor_books(project_id: int | None = None, user_id: int = 0, vendor_name: str | None = None, clear_all: bool = False) -> dict`：支援依 `vendor_name` 單商清除、`clear_all=True` 清空全部共用書單庫，或舊版 `project_id` 呼叫相容；一律保留 `selection_items`。

4. **更新 API 路由：`app/routers/imports.py`、`app/routers/books.py`、`app/routers/projects.py`**
   - `app/routers/imports.py`：
     - `POST /api/imports/vendor-books/confirm`：`project_id` 改為選填，新增 `vendor_name: str | None = Form(None)`、`import_mode: str = Form("upsert")`。
     - 新增 `GET /api/imports/vendors` 回傳書商摘要清單。
     - `DELETE /api/imports/vendor-books` 改為接收選填 `vendor_name`、`clear_all: bool = False`、`project_id: int | None = None`（皆未指定時回 400）。
     - `GET /api/imports/batches` 預設回傳含共用批次與 `vendor_name` 的匯入紀錄（若帶 `project_id`，同時包含 `project_id IS NULL` 的共用批次）。
   - `app/routers/books.py`：
     - `GET /api/books/matches`：
       - 查詢範圍改為全校共用書單池（`ib.batch_type = 'vendor_books'`），回傳每筆書目的 `vendor_name`。
       - 新增選填 `vendor_name: str | None = Query(None)` 篩選參數。
       - 依查詢的 `project_id` 取得 `project_type`，對每筆書目動態計算該專案適用的 `completeness_status`（套用 `completeness_status` 篩選時亦以動態結果判定）。
       - 批次查詢同 `isbn_normalized` 的其他書商報價，組裝 `other_vendor_offers`（依有效價格由低至高排序）。
       - `other_project_selections` 查詢加入 `EXISTS (SELECT 1 FROM export_jobs ej WHERE ej.project_id = pp.id) AS has_exported`，回傳 `has_exported: bool`。
     - `GET /api/books/stats`：
       - 查詢範圍改為全校共用書單池，支援選填 `vendor_name` 篩選，並依 `project_type` 統計 `completeness_status`。
     - `POST /api/books/run-match`：`project_id` 改為選填，執行全校共用書單比對。
     - `PATCH /api/books/{book_id}/overrides`：接受選填 `project_id` query/body 參數傳入 `recompute_for_book()`。
   - `app/routers/projects.py`：
     - `GET /api/projects/`：`vendor_book_count`、`already_owned_count`、`last_import` 改統計全校共用書單池（`ib.batch_type = 'vendor_books'`）。
     - `GET /api/projects/{project_id}/delete-preview`：保留既有回傳鍵名，`vendor_book_count` 回傳 0（共用書單不會被刪除），新增 `shared_catalog_preserved: True`。
     - `DELETE /api/projects/{project_id}`：先將任何仍掛在該專案下的舊書商批次 `UPDATE import_batches SET project_id = NULL WHERE project_id = ? AND batch_type = 'vendor_books'`，再刪除該專案的 `selection_items`、`export_jobs`（以及若存在的舊專案綁定館藏批次）與 `procurement_projects`。

5. **更新前端頁面與樣式：`import.html`、`selection.html`、`match.html`、`projects.html`、`style.css`**
   - `app/static/css/style.css`：新增書商標籤（`.badge-vendor`）、跨書商比價提示塊（`.vendor-compare-box`）與他案已匯出徽章（`.badge-other-exported`）樣式。
   - `app/static/import.html`：
     - 移除書商書單分頁的強制選專案阻擋，改顯示共用書單庫說明提示。
     - 步驟 A／步驟 E 加入書商名稱輸入（綁定 `GET /api/imports/vendors` 的 `<datalist>`）與匯入模式選擇（預設 `upsert`／可切 `replace_vendor`）。
     - 步驟 C 顯示 `recommended_profile` 推薦橫幅與「一鍵套用」按鈕。
     - 步驟 E 匯入完成訊息顯示新增、更新、保留手動修正、略過空白筆數。
     - 底部危險操作區改為「清除指定書商書單」下拉選單＋按鈕與「清空全部共用書單庫」按鈕（維持雙重確認）。
     - 匯入紀錄表格新增「書商」欄。
   - `app/static/selection.html`：
     - 篩選列新增「書商」下拉（`#filter-vendor`，納入 `FILTER_IDS` 與 `resetFilters()`）。
     - 書目卡片顯示書商標籤、`other_vendor_offers` 多家供貨比價提示（若有更低價標註「較低價」），並依 `has_exported` 區分「他案已匯出」與「他案選書中」。
     - `saveOverrides()` 呼叫 `PATCH /api/books/{id}/overrides?project_id=${pid}` 以維持當前專案完整度顯示。
   - `app/static/match.html`：
     - 篩選列新增「書商」下拉（`#filter-vendor`），連動 `/api/books/matches` 與 `/api/books/stats`。
     - 表格新增「書商」欄；比對狀態欄依 `has_exported` 區分「他案已匯出」與「他案選書中」。
   - `app/static/projects.html`：
     - 刪除確認 modal 文案明確說明僅刪除本專案的選書與匯出紀錄，全校共用書商書單庫會完整保留。

6. **撰寫與更新測試並執行全套驗證**
   - 新增 `tests/test_shared_vendor_catalog_upsert.py`，覆蓋：
     - Migration `010_shared_vendor_catalog.sql` 欄位與索引建立。
     - 多書商累加、`upsert` 原地更新（驗證價格更新、保留 `user_overrides`、保留既有獲獎整理結果、保留 `vendor_books.id` 與 `selection_items` 關聯、回傳統計數字）與同檔重複 ISBN 處理。
     - `replace_vendor` 僅取代目標書商且不影響其他書商與選書快照。
     - 既有帶 `project_id` 舊批次與新共用批次並存查詢、清除指定書商／清空全部共用書單庫。
     - 刪除專案保留共用書單與舊書商批次自動轉共用。
     - `GET /api/books/matches` 與 `GET /api/books/stats` 的書商篩選、`other_vendor_offers` 跨書商比價、`other_project_selections.has_exported` 區分、依 `project_type` 動態計算 `completeness_status`。
     - `preview_excel()` 依表頭重疊度自動推薦 `import_profiles`（命中門檻與未達門檻情境）。
   - 同步更新既有測試中依賴舊單專案書單假設的斷言（例如 `tests/conftest.py` 補上 `vendor_name` 欄位、`tests/test_project_delete.py` 改驗共用書單保留行為，並確認 `test_confirm_import.py`、`test_project_list.py`、`test_duplicate_purchase_prevention.py`、`test_frontend_flow_and_safety.py` 全數通過）。

## 風險與注意事項

- **SQLite `IN (...)` 參數數量上限**：跨書商比價查詢、館藏複本查詢與他案選書查詢皆改用子查詢或表掃描配合索引（`idx_vendor_books_isbn_normalized`、`idx_import_batches_batch_type_vendor`），避免展開大型 `IN (?, ?, ...)` 清單。
- **跨專案類型完整度差異**：同一本共用書目在 `local_culture` 與 `general_books` 專案的必填欄位不同；查詢時依 `project_id` 對應的 `project_type` 動態計算，避免兩類專案互相汙染 `vendor_books.completeness_status`。
- **`upsert` 保留 `vendor_books.id`**：命中既有同書商同 ISBN 時以 `UPDATE` 而非 `DELETE + INSERT`，確保既有 `selection_items.vendor_book_id` 關聯與 `vendor_book_still_exists` 狀態維持正確。
- **向後相容性**：所有現有測試與舊版資料庫（含 `project_id IS NOT NULL` 與 `vendor_name IS NULL` 的舊批次）皆可無痛升級，不需手動重建資料庫。
- **測試 fixture 同步**：`tests/conftest.py` 的精簡 `_TEST_SCHEMA` 需補上 `import_batches.vendor_name TEXT`，以免既有路由測試缺欄位。

## 預計影響範圍

| 路徑 | 說明 |
|---|---|
| `migrations/010_shared_vendor_catalog.sql`（新增） | `import_batches` 新增 `vendor_name` 欄位與索引 |
| `app/services/match_service.py` | `run_match()` 改為全校共用書單池比對（相容選填 `project_id`） |
| `app/services/completeness_service.py` | `recompute_for_book()` 改 `LEFT JOIN` 並支援傳入 `project_type` |
| `app/services/import_service.py` | 共用書單寫入、`upsert` / `replace_vendor`、設定檔自動推薦、`list_vendors()`、單商／全清管理 |
| `app/routers/imports.py` | 擴充 `confirm`、新增 `/vendors`、擴充 `DELETE /vendor-books` 與 `/batches` |
| `app/routers/books.py` | 共用書單查詢、書商篩選、動態完整度、`other_vendor_offers`、`has_exported` |
| `app/routers/projects.py` | 專案摘要改讀共用書單池；刪除專案保留共用書單（舊書商批次轉共用） |
| `app/static/css/style.css` | 新增書商標籤、比價提示與他案已匯出樣式 |
| `app/static/import.html` | 書商名稱、匯入模式、設定檔推薦一鍵套用、單商／全清管理與紀錄欄 |
| `app/static/selection.html` | 書商篩選、書商標籤、跨書商比價提示、他案已匯出／選書中區分 |
| `app/static/match.html` | 書商篩選、書商欄、他案已匯出／選書中區分 |
| `app/static/projects.html` | 更新刪除確認視窗提示共用書單庫不受影響 |
| `tests/conftest.py`、`tests/test_project_delete.py` | 同步精簡 schema 與模式 B 刪除專案行為斷言 |
| `tests/test_shared_vendor_catalog_upsert.py`（新增） | 共用書單池、Upsert、比價、他案狀態、設定檔推薦與向後相容回歸測試 |

## 驗證指令

- lint: `.venv\Scripts\python.exe -m ruff check app tests run_server.py setup_first_run.py`
- format: `.venv\Scripts\python.exe -m ruff format --check app/services/import_service.py app/services/match_service.py app/services/completeness_service.py app/routers/imports.py app/routers/books.py app/routers/projects.py tests/test_shared_vendor_catalog_upsert.py`
- typecheck: `.venv\Scripts\python.exe -m mypy app/logging_config.py app/database.py app/main.py app/config.py app/auth.py app/routers/backup.py app/routers/projects.py app/services/isbn_service.py app/services/completeness_service.py app/services/match_service.py app/services/validation_service.py run_server.py`
- test: `.venv\Scripts\python.exe -m pytest -q`（含所有前端 JS `node --check` 檢查）
- build: `.venv\Scripts\python.exe -m compileall -q app run_server.py setup_first_run.py`

## 成果報告

- result_report_mode: none
- 適用情境：無
- 報告路徑（若 mode 非 none）：`docs/reports/task-shared-vendor-catalog-upsert/`
