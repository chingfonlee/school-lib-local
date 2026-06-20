# Plan: task-selection-advanced-filters

## 實作步驟

### Step 1：後端 — 確認 `/api/books/matches` 的 isbn_status 過濾

檔案：`app/routers/books.py`

- 僅修改 `get_matches`（`/api/books/matches`）這個端點；`get_stats`（`/api/books/stats`）不動，統計語意不在本 task 範圍
- **保留** `vb.isbn_status = 'valid'`（第一階段不顯示無有效 ISBN 的書，無 ISBN 無法採購）
- `loadData()` 移除 `match_status=available` 硬編碼，改為無限制載入（available + already_owned 均出現）
- 現有 `match_status` 與 `completeness_status` query param 保留不動

### Step 2：前端 — 修改 `loadData()`

檔案：`app/static/selection.html`

- 將 `api('/api/books/matches?project_id=${pid}&match_status=available')` 改為 `api('/api/books/matches?project_id=${pid}')`
- 移除 match_status=available 硬編碼，改由前端 filter-bar 控制

### Step 3：前端 — 擴充 filter-bar HTML

在現有 `.filter-bar` div 中，保留已有的 `filter-comp` select 與 `filter-text` input，並新增：

```
- match_status select (#filter-match)
- book_type select (#filter-book-type)  — 動態選項
- age_range select (#filter-age)        — 動態選項
- category/policy_topic text (#filter-category)
- min_price number (#filter-min-price)
- max_price number (#filter-max-price)
- sort select (#filter-sort)
- 重設篩選 button
- 結果計數 span (#result-count) 保留位置
```

filter-bar 使用 `flex-wrap: wrap` 確保小螢幕不溢出；select / input 高度一致。

### Step 4：前端 — 新增動態選項函式

在 `loadData()` 完成 allBooks 載入後，呼叫 `populateDynamicSelects()`：

```
function populateDynamicSelects() {
  // 從 allBooks 收集 book_type / age_range 的唯一非空值
  // 排序後寫入對應 select（保留「全部」option 在第一位）
  // book_type 選項 <= 1（只有「全部」）→ 隱藏 label#label-book-type + select
  // category / policy_topic 均無有效值 → 隱藏 #filter-category
  // 此邏輯自動適應未來資料補齊的情境
}
```

**目前預期行為（依 DB 確認）**：
- `book_type`：670 筆書中 0 筆有值 → label + select 隱藏
- `category` / `policy_topic`：0 筆有值 → input 隱藏
- `age_range`：670 筆有值 → select 正常顯示

### Step 5：前端 — 新增 helper 函式

```javascript
// 取有效價格（purchase_price fallback list_price）
function getEffectivePrice(book)

// 統一轉小寫去空格，用於模糊比較
function normalizeText(v)

// 關鍵字多欄位包含搜尋
function includesKeyword(book, kw)

// 排序比較子（根據 sortMode）
function compareBooks(a, b, sortMode)
```

### Step 6：前端 — 擴充 `applyFilter()`

讀取所有篩選控件的值，依序套用：

1. match_status filter：使用 effective status = `b.match_status || b.current_match_status || 'unknown'`，exact match，空值 = 全部
2. completeness_status filter（exact match）
3. book_type filter（exact match）
4. age_range filter（exact match）
5. category / policy_topic text（includes，任一符合）
6. min_price / max_price（getEffectivePrice，無價格書在區間篩選中排除）
7. keyword search（includesKeyword，涵蓋九個欄位）
8. 排序（compareBooks，預設 id asc）
9. 更新 #result-count
10. 呼叫 render(filtered)

### Step 7：前端 — 重設篩選

```javascript
function resetFilters() {
  // 所有 select 設回第一個 option（value=""）
  // 所有 text/number input 清空
  // 呼叫 applyFilter()
}
```

### Step 8：驗證

```
python -m compileall app
```

手動測試 selection.html（詳見驗收條件）

## 風險與注意事項

1. **isbn_status 移除後的影響**：`/api/books/matches` 目前只在 selection.html 使用（已確認 books.py 無其他呼叫端）；match.html 使用 `/api/books/stats` 與匹配相關 endpoint，不受影響。實作後仍須手動測試 selection.html 在有 missing_isbn 書的資料下行為正確。

2. **LEFT JOIN 重複列**：若同一 vendor_book 有多筆 book_matches 記錄（不含 same_title_different_isbn），可能導致該書出現多次。此為現況既有問題（match_service 行為未確認是否做 upsert）；本 task 不修正此問題，但需在手動測試中觀察是否出現。

3. **policy_topic 恆為 NULL**：vendor_books schema 有此欄位，但 VENDOR_COLUMN_HINTS 與 import INSERT 均未包含，現有資料中此欄位恆為 NULL。關鍵字搜尋包含此欄位不影響結果正確性（只是對 NULL 的 includes 永遠不符合）；若未來匯入補上此欄位，功能可自動生效。

4. **price 欄位型別**：`list_price` / `purchase_price` 從 API 回傳可能為 number 或 null；`user_overrides` 中的值為字串。`getEffectivePrice` 須 `parseFloat()` 處理，並對 NaN / 0 fallback。

5. **book_type / age_range 動態選項**：值可能含前後空格、大小寫不一致；`populateDynamicSelects` 應 trim 後再去重。選項排序使用 `localeCompare`。

6. **中文關鍵字搜尋**：使用 `String.includes()`，不做斷詞，符合現況資料密度（短文字欄位為主）。

7. **allBooks 資料量**：移除 match_status=available 後載入量增加（納入 already_owned / missing_isbn / invalid_isbn）；一般書商書單數百至千筆，前端篩選可承擔。若未來測試顯示效能不足，再評估後端篩選。

## 預計影響範圍

| 檔案 | 類型 |
|------|------|
| `app/routers/books.py` | 後端：移除一個 WHERE 條件 |
| `app/static/selection.html` | 前端：擴充 filter-bar、loadData、applyFilter、新增 helpers |

不影響：
- DB schema / migrations
- import_service.py
- selection_service.py
- export 相關 router / service
- match.html、export.html、import.html

## 驗證指令

- lint: 無（專案無 lint 設定）
- format: 無（專案無 formatter 設定）
- typecheck: 無（純 Python + 原生 JS）
- test: `python -m compileall app`
- build: 無

## 成果報告

- result_report_mode: none
- 適用情境：純功能改善，無需對外報告
