# Spec: task-cleared-source-selection-display

## 目標

當書商書單來源資料已被清除後，選書頁、匯出檢查頁、匯出頁應能正確顯示「採購紀錄來自保存快照」，而非讓使用者誤以為資料遺失或系統錯誤。同時修正 `export.html` 預覽表格的篩選邏輯錯誤（pre-existing bug）。

## 需求範圍

### 問題說明

`vendor_books` 是可清除的匯入來源資料；`selection_items` 是長期保存的採購紀錄快照，清除 `vendor_books` 後仍保留完整書目資料。

目前的 UI 問題：

1. **`selection.html` 選書頁**：書目候選清單來自 `/api/books/matches`（vendor_books），清除後 grid 顯示「無資料」。但 budget bar 仍顯示「N 已選書目」，造成矛盾，使用者無從確認已選了什麼。

2. **`export.html` 預覽表格（pre-existing bug）**：preview filter 使用 `b.match_status === 'available'`，但 migration 003 後欄位已改名為 `match_status_at_selection`。導致預覽表格一直空白，與實際匯出結果不符。

3. **`export-check.html` 與 `export.html` 缺少說明文字**：當部分書目的 `vendor_book_still_exists === false` 時，使用者看不到任何說明，不知道資料來自快照，可能誤以為系統異常。

### 現況確認（不需更動）

- `get_selected_books()` 已回傳 `vendor_book_still_exists`（boolean，`vb.id IS NOT NULL`）。
- `check_export_readiness()` 已用 COALESCE 回退至 `match_status_at_selection`，清除後驗證邏輯正確。
- `export_local_culture()` SQL 已用 COALESCE 回退至 snapshot，清除後匯出資料正確。
- 後端不需新增欄位或端點。

### 功能一：`selection.html` — 已選書目快照視圖

- 頁面載入時，同時從 `/api/selections/?project_id=N` 取得 `selData.items`。
- 若 `selData.items` 中存在 `vendor_book_still_exists === false` 的紀錄，在主要候選 grid 下方顯示「已選書目（來源已清除）」區塊。
- 該區塊顯示 snapshot 欄位（書名、作者、ISBN、定價、採購單價、數量）。
- 來源已清除的紀錄以低干擾的標示（如灰色邊框或小標籤「來源已清除」）區分。
- 不顯示「加入選書」按鈕；保留「修正資料」功能，但該功能應使用 `sel_id` 呼叫 `/api/selections/{sel_id}/overrides`（而非 `/api/books/{vendor_book_id}/overrides`）。
- 若所有 `selData.items` 均有 `vendor_book_still_exists === true`，不顯示此區塊（維持現有體驗）。

### 功能二：`export.html` — 預覽表格修正與來源說明

- **修正 pre-existing bug**：preview filter 改用 `b.match_status_at_selection` 判斷是否可顯示，或直接顯示所有 `selected_quantity > 0` 的紀錄。
- 若任何選書紀錄 `vendor_book_still_exists === false`，在「選書預覽」標題旁或上方顯示說明：「部分書目來自保存的採購紀錄快照，書商書單來源資料已清除，不影響匯出結果。」
- 說明文字使用 info 樣式（非錯誤、非警告），不阻擋匯出。

### 功能三：`export-check.html` — 來源說明（非阻擋）

- 執行匯出前檢查後，額外取得 `/api/selections/?project_id=N` 的 `items` 列表。
- 若其中任何 `vendor_book_still_exists === false`，在結果頁面顯示 info 訊息：「部分書目的書商書單來源已清除，比對狀態以選書當時快照為準，不影響匯出準備度判斷。」
- 不計入 `missing_required` 或錯誤計數。

## 不做的事

- 不修改 `selection_items` schema。
- 不修改清除來源資料的邏輯（`clear_library_holdings`、`clear_vendor_books`）。
- 不重新設計匯出流程或 export API。
- 不刪除 `selection_items`。
- 不處理 `task-library-holdings-reimport-multisheet`（paused）。
- 不做大型 UI redesign（不重構 selection.html 候選清單與已選清單的整體架構）。
- 不新增後端 API 端點或 schema 欄位（`vendor_book_still_exists` 已存在）。

## 驗收條件

1. 清除書商書單後，`GET /api/selections/?project_id=N` 仍回傳選書紀錄，且 `vendor_book_still_exists === false`。
2. `selection.html`：若有來源已清除的選書，頁面顯示「已選書目（來源已清除）」區塊，包含 snapshot 書目資料，不顯示「加入選書」按鈕。
3. `selection.html`：書商書單仍存在時，頁面行為與現有完全相同，不出現空白區塊。
4. `export.html`：預覽表格正確顯示已選書目（修正 `match_status` 欄位名稱錯誤）。
5. `export.html`：有來源已清除紀錄時顯示 info 說明，不阻擋匯出。
6. `export-check.html`：有來源已清除紀錄時顯示 info 說明，不列為 `missing_required`。
7. 清除書商書單後，實際匯出結果正確（validation_service / export_service 使用 snapshot 資料）。
8. `python -m compileall app` 通過（後端無修改，應自動通過）。
