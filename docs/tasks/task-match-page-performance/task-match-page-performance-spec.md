# Spec: task-match-page-performance

## 目標

解決「比對結果」頁（`match.html`）在大量共享書商書目（例如上萬筆）下的載入緩慢問題，透過資料庫索引、API 精簡欄位與可選分頁、SQL 子查詢改寫與前端分頁及並行請求，在不新增任何依賴且維持 100% 向後相容的前提下大幅縮短頁面回應時間與網路傳輸量。

## 需求範圍

1. **資料庫索引遷移（`migrations/011_add_selection_isbn_index.sql`）**
   - 為 `selection_items(isbn_normalized)` 建立冪等索引 `idx_selection_items_isbn_normalized`，加速跨專案重複採購查詢。
2. **比對結果 API 優化（`app/routers/books.py`）**
   - `get_matches()`：
     - 將 `SELECT vb.*` 改為明確列出前端與測試所需欄位，排除體積龐大的 `raw_row` 與 `extra_fields`（保留 `summary` 等其餘欄位）。
     - 新增可選查詢參數：`page: int | None = Query(None, ge=1)`、`page_size: int = Query(100, ge=1, le=500)`、`include_offers: bool = Query(True)`。
     - 當 `include_offers=False` 時跳過 `other_vendor_offers` 查詢與排序，每筆設為 `[]`。
     - 當 `page is None` 時維持原本回傳 `list` 格式，確保 `selection.html` 與既有測試完全向後相容；當 `page is not None` 時進行分頁切片並回傳 `{"items": page_items, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}`（超出 `total_pages` 時回傳空 `items`）。
     - 統一以 `Response(content=json.dumps(payload, ensure_ascii=False), media_type="application/json")` 回傳，繞過 FastAPI `jsonable_encoder` 對大量 dict 的序列化開銷。
   - `get_stats()`：
     - 將 `other_project_duplicate_count` 的關聯 `EXISTS` 子查詢改寫為非關聯 `vb.isbn_normalized IN (SELECT DISTINCT si.isbn_normalized FROM selection_items si WHERE si.project_id != ? AND si.selected_quantity > 0 AND si.isbn_normalized IS NOT NULL AND si.isbn_normalized != '')`。
3. **比對結果前端頁面優化（`app/static/match.html`）**
   - 呼叫 `/api/books/matches` 時帶上 `page=${currentPage}&page_size=100&include_offers=false`。
   - 表格下方新增簡潔分頁控制列，顯示「第 X / Y 頁，共 N 筆」及「上一頁」「下一頁」按鈕；切換任一篩選器（書商、比對狀態、完整度）時將 `currentPage` 重設為 `1`。
   - 頁面初始化、切換書商、重新比對改用 `await Promise.all([loadStats(), loadBooks()])` 並行載入。
   - 所有動態文字維持 `esc()` 跳脫，不更動既有元素 ID。
4. **自動化測試（`tests/test_match_page_performance.py`）**
   - 驗證 `011` migration 索引存在且可冪等執行。
   - 驗證 `GET /api/books/matches` 不帶 `page` 時回傳 `list` 且不含 `raw_row` / `extra_fields`；帶 `page=1&page_size=2&include_offers=false` 時回傳正確分頁物件與空 `other_vendor_offers`。
   - 驗證 `GET /api/books/stats` 的 `other_project_duplicate_count` 計數正確。
   - 驗證 `match.html` 包含分頁控制與並行載入。

## 不做的事

- 不修改 `selection.html` 的既有請求格式與行為（維持不帶 `page` 的相容路徑）。
- 不新增第三方 Python 或前端依賴套件。
- 不變更資料庫資料表欄位結構或刪除 `raw_row` / `extra_fields` 欄位。
- 不實作全文檢索或進階伺服器端排序。

## 驗收條件

1. `migrations/011_add_selection_isbn_index.sql` 套用後，`selection_items` 存在 `idx_selection_items_isbn_normalized` 索引，重複套用不報錯。
2. `GET /api/books/matches`：
   - 不帶 `page` 時回傳 `list`，每筆項目不包含 `raw_row` 與 `extra_fields`，其餘欄位與既有行為一致。
   - 帶 `page`、`page_size` 與 `include_offers=false` 時回傳正確的分頁結構，且 `other_vendor_offers` 皆為 `[]`。
3. `GET /api/books/stats` 回傳的 `other_project_duplicate_count` 與既有語意完全一致。
4. `match.html` 使用分頁請求與 `Promise.all` 並行載入，具備分頁控制列且不改動既有元素 ID，JS 語法通過 `node --check`。
5. 全套 5 項驗證指令（`compileall`、`ruff check`、`ruff format --check`、`mypy`、`pytest`）全部通過。
