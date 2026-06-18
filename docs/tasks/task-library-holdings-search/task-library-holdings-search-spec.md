# Spec: task-library-holdings-search

## 目標

在既有圖書採購系統中新增**獨立的館藏查詢功能**，讓老師在採購與選書過程中能獨立查詢學校既有館藏，確認某本書是否已在書庫中。此功能與「選書搜尋」明確分離，避免使用者混淆書商書單與學校館藏。

## 需求範圍

### 使用者目標

- 老師可以查詢學校既有館藏（`library_holdings`），確認是否已有某本書。
- 支援以 ISBN、書名、作者、出版社、書目識別號等條件查詢。
- 查詢結果只來自 `library_holdings`，不查書商書單（`vendor_books`）。
- 館藏查詢不影響選書清單（`selection_items`）、不修改比對結果（`book_matches`），只作為採購判斷的輔助工具。

### 功能範圍

**新增獨立頁面：館藏查詢（`/holdings.html`）**

- 導覽列新增「館藏查詢」入口（所有含 nav 的頁面）。
- 頁面標題：館藏查詢。

**搜尋支援**

- **通用關鍵字（q）**：同時搜尋多個欄位，以 OR 合併，詳見「搜尋規則」章節。
- **ISBN 精準查詢**：呼叫 `isbn_service.normalize_isbn` 正規化後比對 `isbn_normalized`。
- **書名包含查詢**：LIKE `%keyword%`。
- **作者包含查詢**：LIKE `%keyword%`。
- **出版社包含查詢**（選填）：LIKE `%keyword%`。
- **書目識別號查詢**（選填）：`library_record_id` LIKE `%keyword%`。
- 各欄位條件以 AND 合併；`q` 與指定欄位可同時使用，搜尋範圍縮小。
- 缺 ISBN 的館藏（`isbn_status = 'missing'`）仍可透過書名 / 作者 / 書目識別號查詢到。

**搜尋規則**

通用關鍵字 `q` 的 OR 條件如下：

1. 若 `isbn_service.normalize_isbn(q)` 不為 None，加入 `isbn_normalized = ?`（正規化後精準比對）。
2. `isbn LIKE %q%`（原始 ISBN 欄位包含查詢）。
3. `title LIKE %q%`。
4. `author LIKE %q%`。
5. `publisher LIKE %q%`。
6. `library_record_id LIKE %q%`。

上述六條件取 OR 合集；`q` 有值時整組以 AND 串接至其他指定欄位條件。

此設計確保輸入含連字號或空白的 ISBN（如 `978-986-137-158-0`）仍可透過正規化後的精準比對找到館藏。

**搜尋結果顯示**

每筆結果包含：書名、作者、出版社、出版年、ISBN、書目識別號、價格（若有）。

- 顯示結果總筆數。
- 支援 `limit` / `offset` 分頁，`limit` 預設 50，最大 200。
- 搜尋結果依 `title ASC`、`library_record_id ASC` 排序。

**狀態顯示**

- 空狀態：未輸入搜尋條件時顯示提示文字。
- 無結果狀態：搜尋後無匹配時顯示提示。
- 錯誤狀態：API 呼叫失敗時顯示錯誤訊息。

**明確的功能邊界**

- 館藏查詢結果不提供「加入選書」操作。
- 頁面標題與說明文字明確標示「查詢學校既有館藏」而非「搜尋可採購書目」。

### 與選書功能的邊界

| 功能 | 資料來源 | 影響範圍 |
|------|---------|---------|
| 選書頁搜尋 | `vendor_books`（書商書單） | 建立 `selection_items` |
| 館藏查詢 | `library_holdings`（學校館藏） | 唯讀，不影響任何選書或比對資料 |

- 館藏查詢不建立 `selection_items`。
- 館藏查詢不修改 `match_status`。
- 館藏查詢不影響匯出。
- 兩個頁面的 UI 標題與說明文字須可明確區分。

### 選書頁輔助入口

- 選書頁（`selection.html`）每筆書目旁新增「查館藏」連結，使用 `target="_blank" rel="noopener"` 開啟新頁面。
- 帶入 query string：
  - 有有效 ISBN：`/holdings.html?isbn={isbn_normalized}`
  - 無有效 ISBN：`/holdings.html?q={title}`
- `holdings.html` 載入時若 URL 帶有參數，自動帶入搜尋欄位並執行搜尋。
- V1 使用新頁面，不做 modal 或側邊欄。

### API 設計

**新增 router：`app/routers/holdings.py`**

端點：`GET /api/holdings/search`

Query parameters：

| 參數 | 類型 | 預設 | 說明 |
|-----|------|-----|------|
| `q` | string | — | 通用關鍵字（OR 查 isbn_normalized / isbn / 書名 / 作者 / 出版社 / 書目識別號） |
| `isbn` | string | — | ISBN 精準查詢（normalize 後比對 `isbn_normalized`） |
| `title` | string | — | 書名 contains 查詢 |
| `author` | string | — | 作者 contains 查詢 |
| `publisher` | string | — | 出版社 contains 查詢 |
| `library_record_id` | string | — | 書目識別號 contains 查詢 |
| `limit` | int | 50 | 最大 200，超過強制截斷 |
| `offset` | int | 0 | 分頁偏移 |

**空查詢行為**：若 `q`、`isbn`、`title`、`author`、`publisher`、`library_record_id` 全部未提供，API 直接回傳 `{"total": 0, "limit": limit, "offset": 0, "items": []}`，不列出全館館藏。

回傳格式：

```json
{
  "total": 42,
  "limit": 50,
  "offset": 0,
  "items": [
    {
      "id": 1,
      "title": "書名",
      "author": "作者",
      "publisher": "出版社",
      "publish_year": "2022",
      "isbn": "9789861371580",
      "library_record_id": "B123456",
      "price": 280.0
    }
  ]
}
```

所有 `/api/` 路由加 `Depends(require_auth)` 保護。

### 前端設計

**新增：`app/static/holdings.html`**

頁面結構：

1. **導覽列**：與現有頁面一致，「館藏查詢」加 `class="active"`。
2. **頁面標題區**：`館藏查詢` + 副標題「查詢學校既有館藏，確認是否已有某本書」。
3. **搜尋區塊**：通用搜尋框（q）、「進階搜尋」可摺疊區（`<details>`，含 ISBN、書名、作者、出版社、書目識別號輸入框）、搜尋按鈕、清除按鈕。
4. **結果資訊列**：「共找到 N 筆館藏」。
5. **結果表格**：書名、作者、出版社、出版年、ISBN、書目識別號、價格。
6. **狀態提示**：空狀態（初始）/ 無結果 / 錯誤。

UI 風格沿用現有靜態頁面：白底、`#f5f5f7` 次要背景、`8px` 圓角、乾淨表格、字型 `system-ui`。

## 不做的事

- 不查詢外部書籍資料 API。
- 不做模糊比對或相似度搜尋。
- 不修改匯入流程。
- 不修改比對邏輯（`match_status`）。
- 不修改選書資料（`selection_items`）。
- 不提供刪除或編輯館藏功能。
- 不做正式館藏編目或 OPAC 功能。
- 不在查詢結果上提供「加入選書」操作。
- 不新增資料庫 schema（`library_holdings` 現有結構已足夠）。
- 不重構共用 nav（各頁面個別新增連結）。

## 驗收條件

1. 匯入學校館藏後，可在館藏查詢頁搜尋到資料。
2. 輸入有效 ISBN 可找到對應館藏記錄（以 `isbn_normalized` 精準比對）。
3. 輸入含連字號或空白的 ISBN（如 `978-986-137-158-0`），可透過 `q` 通用搜尋的正規化精準比對找到館藏。
4. 輸入書名關鍵字可找到多筆館藏。
5. 輸入作者關鍵字可找到多筆館藏。
6. 輸入書目識別號關鍵字可找到對應館藏。
7. 缺 ISBN 的館藏（`isbn_status = 'missing'`）可透過書名 / 作者 / 書目識別號查詢到。
8. 館藏查詢結果頁無「加入選書」按鈕，查詢不改變任何 `selection_items` 或 `match_status`。
9. 選書頁「查館藏」連結帶入 ISBN 或書名後，館藏查詢頁自動執行搜尋。
10. 未登入時呼叫 `/api/holdings/search` 回傳 401。
11. `/api/holdings/search` 支援 `limit` / `offset`，`limit` 最大 200，超過時截斷而非報錯。
12. 所有搜尋條件均為空時，API 回傳 `total: 0, items: []`，不列出全館館藏；前端顯示空狀態提示。
13. 既有本土圖書採購流程（匯入、比對、選書、匯出）不受影響。
