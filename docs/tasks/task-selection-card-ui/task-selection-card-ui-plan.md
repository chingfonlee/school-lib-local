# Plan: task-selection-card-ui

## 實作步驟

1. 在 `app/static/css/style.css` 補充卡片樣式：
   - `.books-grid`：CSS Grid，預設 3 欄，breakpoint 縮至 2 欄（≤768px）及 1 欄（≤480px）
   - `.book-card`、`.book-card-body`、`.book-card-footer`：卡片結構、白底、圓角、陰影
   - `.book-cta`：primary 藍色全寬按鈕；disabled 狀態灰色
   - `.book-card-edit`：卡片內 override 展開區，沿用 `.inline-edit` 結構

2. 修改 `app/static/selection.html` 的 HTML 容器：
   - 移除 `<div class="card" style="padding:0">` 與其內的 `<table>` / `<tbody id="book-body">` 結構
   - 改為 `<div id="book-grid" class="books-grid"></div>` 容器

3. 重寫 `render(books)` 函式（改名邏輯不變，只改輸出格式）：
   - 輸出卡片 HTML 至 `#book-grid`
   - 卡片必備欄位：書名、作者、ISBN、定價、採購價、得獎項目、完整度 badge
   - CTA 按鈕：`selMap[b.id] > 0` 時輸出「已加入」disabled；否則輸出「＋ 加入選書」並綁定 `addBook(b.id)`
   - 查館藏連結：保留原有 `holdingsUrl` 邏輯，target="_blank" rel="noopener"
   - override 編輯區：將原有 `<div class="inline-edit">` 包在卡片底部，`id="edit-${b.id}"`，初始隱藏；「修正資料」連結呼叫 `toggleEdit(b.id)`

4. 新增 `addBook(bookId)` 函式，替代每張卡片的選書操作：
   - 呼叫現有 API：`api('/api/selections/', { method: 'POST', body: JSON.stringify({ project_id: pid, vendor_book_id: bookId, quantity: 1 }) })`
   - 成功後：`selMap[bookId] = 1`，呼叫 `refreshBudget()`，更新該卡片的 CTA 按鈕狀態（disabled + 文字「已加入」）
   - 失敗時：顯示 toast 錯誤訊息

5. 移除原有 `updateQty` 函式與所有數量 `<input class="qty-input">` 相關程式碼

6. 執行驗證（見驗證指令）

## 風險與注意事項

- `selMap` 目前存放 `selected_quantity`（整數）；改卡片後以 `selMap[id] > 0` 判斷已選，不影響既有 loadData / refreshBudget 邏輯
- `clearAll()` 呼叫 `loadData()`，loadData 後整個 grid 重新 render，清空後狀態自動重置，無需特別處理
- `saveOverrides()` 後也呼叫 `loadData()`，override 儲存後 grid 整個重繪，行為與現有表格一致
- `toggleEdit(id)` 指向 `#edit-${id}`，只要 id 存在於 DOM 即可運作，從 table row 移到 card 內不影響邏輯

## 預計影響範圍

- `app/static/selection.html`：全面修改 `render()` 函式及 HTML 骨架；移除 table；新增 `addBook()`；移除 `updateQty()`
- `app/static/css/style.css`：新增約 60 行卡片 CSS，不影響其他頁面樣式
- 不影響 Python 後端、routes、models 或其他 HTML 頁面

## 驗證指令

- lint: 無（專案目前無前端 lint 設定）
- format: 無
- typecheck: 無
- test: 無
- build: `python -m compileall app`

## 成果報告

- result_report_mode: none
- 適用情境：不需
- 報告路徑（若 mode 非 none）：無
