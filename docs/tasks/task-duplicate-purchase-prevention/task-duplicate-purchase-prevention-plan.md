# Plan: task-duplicate-purchase-prevention

## 實作步驟

1. **強化 `app/services/match_service.py` 書名正規化比對**
   - 新增 `normalize_title_for_match(title: str | None) -> str`：
     - `unicodedata.normalize("NFKC", title).lower()`
     - 以正則移除括號內常見版本／裝幀字樣（如 `(精裝|平裝|修訂版|增訂版|新版|二版|三版|初版|繪本版|典藏版|紀念版|普及版)`）。
     - 移除所有非文字／數字字元（標點與空白）。
     - 若結果長度 `< 2` 回傳 `""`。
   - `run_match()` 建立 `title_index` 與檢查 `vb["title"]` 時全面改用 `normalize_title_for_match()`。

2. **擴充 `app/routers/books.py` 的 `/matches` 與 `/stats`**
   - 在 `get_matches()` 中：
     - 維持現有主查詢（回傳 `vb.*` 與主 `bm.match_status`）。
     - 以單次批次查詢取得本專案各 `isbn_normalized` 在 `library_holdings` 的複本數（`SELECT isbn_normalized, COUNT(*) FROM library_holdings WHERE isbn_normalized IN (...) GROUP BY isbn_normalized`）。
     - 以單次批次查詢取得本專案各 `vendor_book_id` 對應的 `same_title_different_isbn` 館藏明細（JOIN `library_holdings` 取 `title`, `author`, `publisher`, `isbn`）。
     - 以單次批次查詢取得其他專案（`si.project_id != ? AND si.selected_quantity > 0`）同 `isbn_normalized` 的選書專案清單（JOIN `procurement_projects` 取 `project_id`, `name`）。
     - 將 `holding_copies`、`similar_holding`、`other_project_selections` 合併至每筆回傳 dict。
     - 若傳入 `match_status == "same_title_different_isbn"` 或 `match_status == "other_project_selected"`，依對應條件過濾回傳結果（保留既有 `available` / `already_owned` 行為）。
   - 在 `get_stats()` 中補算 `same_title_different_isbn_count` 與 `other_project_duplicate_count`。

3. **更新前端 `app/static/match.html`、`app/static/selection.html` 與 `app/static/css/style.css`**
   - `style.css`：新增清楚不刺眼的輔助警示徽章樣式（例如 `.badge-similar` 黃底棕字、`.badge-other-project` 紫／藍底警示標籤）。
   - `match.html`：
     - 統計列加入「疑似同名館藏」與「他案已選」卡片。
     - 比對狀態篩選下拉新增 `same_title_different_isbn`（疑似同名館藏）與 `other_project_selected`（他案已選）。
     - 表格「比對狀態」欄依序渲染：主狀態（`already_owned` 帶 `（N冊）`）、`similar_holding` 警示與館藏書名／ISBN、`other_project_selections` 警示與專案名稱（全面使用 `esc()`）。
   - `selection.html`：
     - 比對狀態篩選下拉新增「疑似同名館藏」與「他案已選」篩選條件，並在 `applyFilter()` 支援過濾。
     - 書目卡片渲染區顯示 `already_owned` 複本數、`similar_holding` 黃色提示塊（含館藏書名、作者、ISBN）與 `other_project_selections` 跨專案提示塊（含專案名稱），全面使用 `esc()` 跳脫。

4. **撰寫單元與整合測試並執行全套驗證**
   - 新增 `tests/test_duplicate_purchase_prevention.py`，覆蓋：
     - `normalize_title_for_match()` 各種標點、全半形、版本括號字樣與短書名邊界。
     - `run_match()` 命中同名不同 ISBN（含標點／版本差異）。
     - `GET /api/books/matches` 與 `GET /api/books/stats` 正確回傳 `holding_copies`（多冊）、`similar_holding`、`other_project_selections` 與篩選功能。
     - 前端 `match.html`、`selection.html` 關鍵渲染標記與 `node --check` 語法驗證（既有 `test_frontend_flow_and_safety.py` 亦會自動掃描所有 HTML `<script>`）。
   - 執行全套驗證指令確保全數 pass。

## 風險與注意事項

- **SQLite `IN (...)` 參數數量上限**：在 `get_matches()` 批次查詢 `library_holdings`、`book_matches`、`selection_items` 時，若專案有數千本書目，避免將數千個 ISBN 展開進 `IN (?, ?, ...)`；應改用 `JOIN` 或子查詢（例如直接以 `project_id` 為條件查詢），完全避免超過 `SQLITE_MAX_VARIABLE_NUMBER`。
- **向後相容性**：不改變 `match_status` 原有值（`available` / `already_owned`），避免影響 `selection.html` 既有的加入選書／強制加入邏輯與 `export_service` 規則。
- **效能**：所有查詢皆走 Task 1A 建立的索引（`idx_library_holdings_isbn_normalized`、`idx_book_matches_vendor_book_id`、`idx_selection_items_project_id`），在 5,000 筆書單下仍維持毫秒級回應。

## 預計影響範圍

| 路徑 | 說明 |
|---|---|
| `app/services/match_service.py` | 新增 `normalize_title_for_match()` 並用於 `same_title_different_isbn` 比對 |
| `app/routers/books.py` | `/matches` 回傳 `holding_copies`、`similar_holding`、`other_project_selections` 與新篩選；`/stats` 補兩項統計 |
| `app/static/css/style.css` | 新增疑似同名館藏與他案已選徽章／提示樣式 |
| `app/static/match.html` | 顯示冊數、疑似同名館藏、他案已選統計、篩選與警示 |
| `app/static/selection.html` | 書目卡片顯示冊數與防重警示，篩選下拉支援兩種風險篩選 |
| `tests/test_duplicate_purchase_prevention.py`（新增） | 書名正規化、比對、API 回傳與篩選回歸測試 |

## 驗證指令

- lint: `.venv\Scripts\python.exe -m ruff check app tests run_server.py setup_first_run.py`
- format: `.venv\Scripts\python.exe -m ruff format --check app/services/match_service.py app/routers/books.py tests/test_duplicate_purchase_prevention.py`
- typecheck: `.venv\Scripts\python.exe -m mypy app/logging_config.py app/database.py app/main.py app/config.py app/auth.py app/routers/backup.py app/routers/projects.py app/services/isbn_service.py app/services/completeness_service.py app/services/match_service.py app/services/validation_service.py run_server.py`
- test: `.venv\Scripts\python.exe -m pytest -q`（含所有前端 JS `node --check` 檢查）
- build: `.venv\Scripts\python.exe -m compileall -q app run_server.py setup_first_run.py`

## 成果報告

- result_report_mode: none
- 適用情境：無
- 報告路徑（若 mode 非 none）：`docs/reports/task-duplicate-purchase-prevention/`
