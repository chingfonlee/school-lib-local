# Spec: task-library-holdings-reimport-multisheet

## 目標

修正學校館藏 (`library_holdings`) 的匯入行為，實現「全量快照覆蓋」與多 sheet 匯入，消除重複匯入累加的問題，並確保匯入具備交易安全。

## 需求範圍

### 問題一：重複匯入累加

目前 `import_library_holdings()`（`app/services/import_service.py`）每次均直接 INSERT 新資料，不清除舊批次，導致同一份館藏檔重複匯入後 `library_holdings` 筆數翻倍。

**修正方式：全量快照覆蓋**

每次成功匯入新館藏後，系統只保留最新批次資料。舊的 `library_holdings`、對應 `book_matches`（`holding_id` 參照舊館藏的紀錄）、及舊 `import_batches`（`batch_type='library_holdings'`）均在本次交易開始時一併清除。

### 問題二：多 sheet 匯入不完整

目前 `import_library_holdings()` 呼叫 `_read_excel_with_detected_header()` 未指定 `sheet_name`，預設為 `sheet_name=0`，只讀取第一張 sheet，其餘 sheet 的館藏資料不會被匯入。

**修正方式：逐 sheet 全量匯入**

所有 sheet 均嘗試偵測 header row 並匯入；無法對應至 `isbn` 或 `title` 欄位的 sheet 視為非資料 sheet（如封面頁、說明頁），安全略過，不產生錯誤。

### 交易安全

清除舊館藏與插入新館藏必須在同一個 SQLite transaction 內完成。若中途發生 exception，需執行 rollback，確保不會出現舊館藏已清除但新資料未完成的狀態。

### 零有效匯入保護

若上傳的 Excel 所有 sheet 均被判定為非資料 sheet，或所有有效 sheet 加總後 `records_inserted == 0`，`import_library_holdings()` 必須 raise exception 並 rollback，不得 commit 覆蓋舊館藏。覆蓋操作須滿足「至少一個有效資料 sheet 且 records_inserted > 0」才可執行。

### API 回傳格式擴充（向後相容）

`POST /api/imports/holdings` 的回傳新增以下欄位，不移除現有欄位（`batch_id`、`record_count`、`unmapped_fields`、`column_mapping`）：

- `replaced`：布林值，固定回傳 `true`，表示此次為覆蓋匯入
- `sheet_summaries`：各有效 sheet 的匯入摘要，格式 `[{"sheet_name": str, "record_count": int}]`
- `skipped_sheets`：略過的 sheet 清單，格式 `[{"sheet_name": str, "reason": str}]`

### 前端顯示

`app/static/import.html` 中 `uploadHoldings()` 的匯入完成訊息調整為：

- 顯示「已覆蓋既有館藏，共 N 筆」
- 若 `sheet_summaries` 含多個有效 sheet，列出各 sheet 名稱與筆數
- 若有 `skipped_sheets`，顯示略過的 sheet 名稱

### 匯入後比對同步

館藏覆蓋完成後，`book_matches` 因 `_clear_library_holdings` 已被清除，第一次進入比對頁時無可採購 / 已館藏數量。

**修正方式：匯入 commit 成功後自動重新執行 `run_match`**

- **館藏匯入**（`import_library_holdings`）：commit 成功後，查詢目前有 `vendor_books` 的所有 `project_id`，逐一呼叫 `run_match(project_id)`。無 vendor_books project 時不視為錯誤。
- **書商書單匯入**（`confirm_import` / `import_vendor_books`）：commit 成功後，對本次匯入的 `project_id` 呼叫 `run_match(project_id)`。

Transaction 安全：`run_match` 在匯入 commit **之後**執行，不影響匯入的 rollback 保護。若 `run_match` 失敗，回傳 `match_rerun_error`，不讓匯入失敗。

API 回傳格式擴充（向後相容，現有欄位不移除）：

- 館藏匯入回傳新增：
  - `match_rerun`：布林值，表示是否執行了自動比對
  - `affected_projects`：有 vendor_books 且執行過 run_match 的 project_id 清單
  - `match_stats_by_project`：`{ project_id: stats }` 各 project 的比對結果
  - `match_rerun_error`：（僅在 run_match 失敗時）錯誤訊息字串
- 書商書單匯入（confirm_import / import_vendor_books）回傳新增：
  - `match_stats`：本次 project 的比對結果（`run_match` 回傳的 stats dict）
  - `match_rerun_error`：（僅在 run_match 失敗時）錯誤訊息字串

前端顯示：

- 館藏匯入成功後，若 `affected_projects` 非空，顯示「已重新執行比對（N 個書單專案）」
- 書商書單匯入成功後，若有 `match_stats`，顯示可採購 / 已館藏數量
- 若有 `match_rerun_error`，顯示提醒：匯入成功，但自動比對失敗，可到比對頁手動重新比對

## 不做的事

- 不新增資料庫 schema（不需 migration，不新增 UNIQUE constraint 或新欄位）
- 不為館藏匯入增加多步驟 wizard 流程（維持現有單步上傳 UI）
- 不變更 `POST /api/imports/holdings` 的輸入參數格式
- 不修改 `run_match` 的比對邏輯
- 不調整 `column_overrides` 參數的行為語意（維持現有邏輯）
- 不修改 selection_items snapshot 邏輯與 export 邏輯

## 驗收條件

1. 同一份館藏 Excel 連續匯入兩次後，`library_holdings` 總筆數等於單次匯入的筆數（不翻倍）。
2. 匯入完成後，`import_batches WHERE batch_type='library_holdings'` 只剩最新一筆（舊批次已清除）。
3. 多 sheet 館藏 Excel 匯入後，`library_holdings` 總筆數等於所有有效 sheet 的資料列加總；API 回傳 `sheet_summaries` 正確列出各 sheet 筆數。
4. 非資料 sheet（無法對應 `isbn` 或 `title`）不產生匯入錯誤，API 回傳 `skipped_sheets` 列出略過原因。
5. 匯入中途若發生 exception，`library_holdings` 不應出現半套資料（transaction rollback 有效，舊館藏應保持原狀）。
6. 若上傳的 Excel 所有 sheet 均被略過，或有效匯入筆數為 0，API 回傳 HTTP 400 錯誤且 `library_holdings` 維持匯入前的狀態（rollback，不清空舊館藏）。
7. 匯入完成後可正常執行館藏查詢與書單比對，`book_matches` 可重新產生，無 FK 違反或殘留舊 match 問題。
8. 前端匯入完成訊息顯示「已覆蓋既有館藏」，多 sheet 情況下顯示各 sheet 筆數；有略過 sheet 時顯示略過名稱。
9. 館藏匯入後，若已有書商書單，第一次打開 match.html 即顯示可採購 / 已館藏數量（不需手動按「重新比對」）。
10. 書商書單匯入後，第一次打開 match.html 即顯示可採購 / 已館藏數量。
11. 若 `run_match` 失敗，匯入本身仍成功回傳，前端顯示比對失敗提示。
