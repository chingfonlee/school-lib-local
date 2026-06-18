# Plan: task-library-holdings-search

## 實作步驟

### Step 1：新增後端 router（app/routers/holdings.py）

新增 `app/routers/holdings.py`，實作 `GET /api/holdings/search`：

- `router = APIRouter(prefix="/api/holdings", tags=["holdings"])`
- 加 `Depends(require_auth)` 保護。
- 接受 query params：`q`、`isbn`、`title`、`author`、`publisher`、`library_record_id`、`limit`（預設 50）、`offset`（預設 0）。
- `limit` 超過 200 強制截斷為 200；`offset` 小於 0 設為 0。

**空查詢捷徑**：若 `q`、`isbn`、`title`、`author`、`publisher`、`library_record_id` 全部為空，直接回傳 `{"total": 0, "limit": limit, "offset": 0, "items": []}`，不執行 SQL 查詢。

**SQL 條件建構邏輯：**

指定欄位條件（AND 串接）：

- `isbn` 有值：呼叫 `isbn_service.normalize_isbn(isbn)`。若結果不為 None，加 `isbn_normalized = ?`（精準）；若 normalize 結果為 None，加 `isbn LIKE ?`（`%isbn%`）。
- `title` 有值：加 `title LIKE ?`（`%title%`）。
- `author` 有值：加 `author LIKE ?`（`%author%`）。
- `publisher` 有值：加 `publisher LIKE ?`（`%publisher%`）。
- `library_record_id` 有值：加 `library_record_id LIKE ?`（`%library_record_id%`）。

通用關鍵字條件（OR 合集，整組以 AND 串接至上述指定欄位條件）：

- `q` 有值時，建立 OR 條件：
  1. `isbn_service.normalize_isbn(q)` 不為 None → `isbn_normalized = ?`
  2. `isbn LIKE ?`（`%q%`）
  3. `title LIKE ?`（`%q%`）
  4. `author LIKE ?`（`%q%`）
  5. `publisher LIKE ?`（`%q%`）
  6. `library_record_id LIKE ?`（`%q%`）
  - 組合為：`(isbn_normalized = ? OR isbn LIKE ? OR title LIKE ? OR author LIKE ? OR publisher LIKE ? OR library_record_id LIKE ?)`

排序：`ORDER BY title ASC, library_record_id ASC`

執行：先 `SELECT COUNT(*) FROM library_holdings WHERE ...` 取 `total`，再 `SELECT ... LIMIT ? OFFSET ?` 取分頁資料。

回傳：`{total, limit, offset, items}`；每筆 item 欄位：`id`、`title`、`author`、`publisher`、`publish_year`、`isbn`、`library_record_id`、`price`。

### Step 2：掛載 router（app/main.py）

在 `app/main.py` 新增兩行（放在現有 `app.include_router(exports.router)` 之後）：

```python
from app.routers import holdings
app.include_router(holdings.router)
```

### Step 3：新增前端頁面（app/static/holdings.html）

建立 `app/static/holdings.html`，結構參考現有 `match.html`：

1. **導覽列**：複製現有 nav，「館藏查詢」加 `class="active"`。
2. **頁面主體**：
   - `<h2>館藏查詢</h2>` + `<p class="subtitle">查詢學校既有館藏，確認是否已有某本書</p>`
   - 搜尋卡片：通用搜尋框 `id="q-input"`。
   - `<details>` 進階搜尋：`isbn-input`、`title-input`、`author-input`、`publisher-input`、`library-record-id-input`（共 5 個）。
   - 按鈕列：「搜尋」（`id="search-btn"`）、「清除」（`id="clear-btn"`）。
   - `<div id="result-info" hidden>共找到 <span id="result-count"></span> 筆館藏</div>`
   - `<div id="empty-state">請輸入搜尋條件</div>`
   - `<div id="no-result-state" hidden>找不到符合的館藏</div>`
   - `<div id="error-state" hidden></div>`
   - `<table id="results-table" hidden>` 欄位：書名、作者、出版社、出版年、ISBN、書目識別號、價格。
3. **`<script>` 區塊**：
   - `loadFromUrl()`：讀取 `URLSearchParams`，帶入各輸入框；有值時呼叫 `doSearch()`。
   - `doSearch()`：收集所有輸入值，若全部為空則停在空狀態，否則組合 query string 呼叫 `GET /api/holdings/search`，依回傳結果顯示對應狀態。
   - `renderResults(data)`：渲染表格，`total === 0` 時顯示無結果狀態，否則渲染表格列並更新 `result-count`。
   - `clearAll()`：清空所有輸入，切換回空狀態。
   - 事件綁定：搜尋按鈕 click、清除按鈕 click、Enter 鍵（所有輸入框）。
   - 登出函式（與現有頁面一致）。

### Step 4：更新各頁面導覽列

在以下 7 個頁面的 `<div class="nav-steps">` 中，在 `<a href="/export.html">匯出</a>` 後插入：

```html
<a href="/holdings.html">館藏查詢</a>
```

需修改的頁面（7 個）：`index.html`、`projects.html`、`import.html`、`match.html`、`selection.html`、`export-check.html`、`export.html`。

`holdings.html` 自身的 nav 中，該連結加 `class="active"`，其他 7 個頁面不加。

### Step 5：選書頁新增「查館藏」連結（app/static/selection.html）

`/api/books/matches` 目前回傳 `vb.*`，已包含 `isbn_normalized`，Step 5 可直接使用。

在書目渲染函式中（與「修正資料」連結並排），新增：

```javascript
const holdingsUrl = b.isbn_normalized
  ? `/holdings.html?isbn=${encodeURIComponent(b.isbn_normalized)}`
  : `/holdings.html?q=${encodeURIComponent(b.title || '')}`;
const holdingsLink = `<a href="${holdingsUrl}" target="_blank" rel="noopener" style="font-size:13px">查館藏</a>`;
```

### Step 6：驗收測試（手動）

1. 執行語法檢查：`python -m compileall app`
2. 啟動伺服器：`python -m uvicorn app.main:app --host 127.0.0.1 --port 8765`
3. 使用已匯入的 `學校館藏.xls` 資料依序測試：
   - `GET /api/holdings/search`（無參數）→ `total: 0, items: []`
   - `GET /api/holdings/search?isbn={有效ISBN}` → 有結果
   - `GET /api/holdings/search?q=978-986-137-158-0`（含連字號 ISBN）→ 正規化後精準比對有結果
   - `GET /api/holdings/search?title=台灣` → 有結果
   - `GET /api/holdings/search?author={作者名}` → 有結果
   - `GET /api/holdings/search?library_record_id={識別號片段}` → 有結果
   - `GET /api/holdings/search?q={關鍵字}` → 有結果
   - 查詢 `isbn_status = 'missing'` 的館藏書名 → 透過 title 或 author 可查到
   - `GET /api/holdings/search?limit=201` → limit 截斷為 200，不報錯
4. 打開 `holdings.html`，確認：空狀態 → 搜尋 → 顯示結果 → 無結果提示 → 清除。
5. 確認 URL 帶參數自動執行搜尋（模擬選書頁「查館藏」跳轉）。
6. 在 `selection.html` 點擊「查館藏」，確認新頁面開啟並帶入 ISBN 自動搜尋。
7. 未登入呼叫 `GET /api/holdings/search` → 401。
8. 確認 7 個頁面 nav 均已新增「館藏查詢」入口。
9. 確認既有匯入、比對、選書、匯出流程未受影響。

## 風險與注意事項

1. **館藏重複匯入**：同批次重複匯入時搜尋結果可能出現重複書目；V1 直接顯示不去重，必要時提醒使用者。
2. **缺 ISBN 館藏的精準查詢**：`isbn_normalized` 為 NULL 時，`isbn` 參數的精準比對不會命中該記錄，但書名 / 作者 / 書目識別號查詢仍可找到，符合規格。
3. **SQLite LIKE 查詢限制**：中文不做斷詞，LIKE `%keyword%` 為全字串掃描；V1 接受此限制，資料量增大時可考慮對 `title`、`author` 加 index（不在本任務範圍）。
4. **`q` 與指定欄位同時有值**：搜尋範圍以 AND 縮小，前端可在進階搜尋 `<details>` 開啟時顯示提示「與通用搜尋共同篩選」。
5. **nav 修改 7 個頁面**：修改簡單但數量多，可一次 commit；逐一確認後再提交，避免遺漏。

## 預計影響範圍

**新增**：

- `app/routers/holdings.py`
- `app/static/holdings.html`

**修改**：

- `app/main.py`（新增 router 掛載，2 行）
- `app/static/index.html`（nav +1 連結）
- `app/static/projects.html`（nav +1 連結）
- `app/static/import.html`（nav +1 連結）
- `app/static/match.html`（nav +1 連結）
- `app/static/selection.html`（nav +1 連結 + 每筆書目「查館藏」連結）
- `app/static/export-check.html`（nav +1 連結）
- `app/static/export.html`（nav +1 連結）

**不修改**：

- 資料庫 schema（`library_holdings` 現有結構已足夠）
- 匯入流程、比對邏輯、選書與匯出邏輯

## 驗證指令

- lint: 待確認（與 task-local-cultural-books-mvp 相同工具鏈，使用 ruff 若已安裝）
- format: 待確認
- typecheck: 無（V1 不強制）
- test: `python -m compileall app`
- build/啟動驗證: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8765`

## 成果報告

- result_report_mode: none
- 適用情境：本任務以手動驗收為主，Step 6 驗收流程涵蓋所有驗收條件，無需額外成果報告。
