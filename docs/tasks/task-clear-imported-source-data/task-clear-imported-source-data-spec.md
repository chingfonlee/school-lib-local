# Spec: task-clear-imported-source-data

## 目標

提供正式的「清除來源資料」功能，讓使用者能在不影響已選書紀錄的前提下，清除全域學校館藏或指定專案的書商書單，以便重新匯入乾淨的來源資料。

## 需求範圍

### 問題描述

目前系統只能透過重匯覆蓋來源資料，沒有正式的清除機制。當館藏或書商書單需要完全替換時，使用者無法在 UI 上執行清除；只能手動操作資料庫，有遺漏孤兒資料的風險。

### 功能一：清除全域館藏來源資料

- `library_holdings` 是全域（不屬於特定 project）的來源資料，可清除。
- 清除後 `library_holdings` 表清空，相關 `book_matches.holding_id` 紀錄一併清除，對應的 `import_batches`（batch_type='library_holdings'）一併清除。
- 清除後館藏比對結果失效；重新匯入館藏後需重新執行比對。

### 功能二：清除指定 project 書商書單來源資料

- `vendor_books` 是指定 project 的書商書單來源資料，可清除。
- 清除後該 project 的 `vendor_books` 清空，相關 `book_matches.vendor_book_id` 紀錄一併清除，對應的 `import_batches`（batch_type='vendor_books'）一併清除。
- `selection_items` 不可因清除書商書單而被刪除；`selection_items` 已為 snapshot 記錄，清除後仍完整保留。

### 功能三：前端操作介面

- `import.html` 在「學校館藏」區塊加入「清除學校館藏」按鈕。
- `import.html` 在「書商書單」區塊加入「清除目前專案書商書單」按鈕。
- 清除是危險操作，前端必須雙重確認：先 `confirm()`、再 `prompt()` 要求輸入「清除」後才呼叫 API。
- 清除按鈕使用明顯的危險樣式（紅色或警示色）。
- 清除成功後顯示刪除筆數摘要。
- 清除書商書單時若未選定 project，顯示錯誤訊息，不呼叫 API。

## 不做的事

- 不刪除 `selection_items`（已選書紀錄）。
- 不刪除 `procurement_projects`（採購專案）。
- 不刪除 `export_jobs`。
- 不重置整個資料庫。
- 不清除 `import_profiles`（匯入設定檔）。
- 不新增跨年度報表或統計功能。
- 不提供批次清除多個 project 的介面。

## 驗收條件

1. `DELETE /api/imports/holdings` 可正常呼叫，回傳刪除筆數摘要，需身份驗證。
2. `DELETE /api/imports/vendor-books?project_id=N` 可正常呼叫，回傳刪除筆數摘要，需身份驗證；project_id 缺失或不存在時回傳 HTTP 400/404。
3. 清除館藏後：`library_holdings` 筆數為 0，對應 `book_matches` 與 `import_batches` 被清除。
4. 清除書商書單後：該 project 的 `vendor_books` 筆數為 0，對應 `book_matches` 與 `import_batches` 被清除，`selection_items` 保留原有筆數。
5. 清除書商書單後，以下功能仍可正常使用：
   - `GET /api/selections/?project_id=N` 回傳已選書列表。
   - `get_selection_summary()` 統計正確。
   - `check_export_readiness()` 可執行。
   - 若 export template 存在，`export_local_culture()` 可執行。
6. 前端「清除」按鈕有雙重確認（confirm + prompt 輸入「清除」）。
7. `python -m compileall app` 通過。
