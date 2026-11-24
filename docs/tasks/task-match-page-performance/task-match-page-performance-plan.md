# Plan: task-match-page-performance

## 實作步驟

1. 新增 `migrations/011_add_selection_isbn_index.sql`，建立 `idx_selection_items_isbn_normalized` 索引。
2. 優化 `app/routers/books.py`：
   - 將 `get_matches()` 的 `SELECT vb.*` 替換為明確欄位清單（排除 `raw_row` 與 `extra_fields`）。
   - 新增 `page`、`page_size`、`include_offers` 查詢參數，支援 `include_offers=False` 跳過跨書商比價查詢與排序，以及 `page` 分頁切片回傳。
   - 改以 `Response(content=json.dumps(payload, ensure_ascii=False), media_type="application/json")` 回傳。
   - 將 `get_stats()` 的 `other_project_duplicate_count` 改寫為非關聯 `IN (SELECT DISTINCT ...)` 子查詢。
3. 優化 `app/static/match.html`：
   - 加入 `currentPage` / `totalPages` 狀態與分頁控制列（上一頁、下一頁、頁碼與總筆數顯示）。
   - 呼叫 `/api/books/matches` 時帶上 `page=${currentPage}&page_size=100&include_offers=false`，篩選器變更時重設 `currentPage = 1`。
   - 初始化、切換書商與重新比對改用 `await Promise.all([loadStats(), loadBooks()])`。
4. 新增 `tests/test_match_page_performance.py`，覆蓋索引、分頁 API、欄位排除、`include_offers=false`、`get_stats` 計數正確性與 `match.html` 分頁/並行載入驗證。
5. 執行全套 5 項驗證指令，確認全部通過後 commit 變更。

## 風險與注意事項

- `selection.html` 與既有測試呼叫 `/api/books/matches` 時未帶 `page` 與 `include_offers`，預設值必須維持 `page=None` 與 `include_offers=True` 以保證 100% 向後相容。
- `get_matches()` 空結果時若帶 `page`，應回傳標準分頁物件 `{"items": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 0}`（或與非空分支一致的結構），不帶 `page` 則回傳 `[]`。
- `match.html` 不得更動既有元素 ID，且動態文字需持續使用 `esc()` 跳脫以防止 XSS。

## 預計影響範圍

- `migrations/011_add_selection_isbn_index.sql`（新增）
- `app/routers/books.py`（修改）
- `app/static/match.html`（修改）
- `tests/test_match_page_performance.py`（新增）
- `docs/STATUS.md`、`docs/tasks/task-match-page-performance/*`（任務紀錄）

## 驗證指令

- compile: `.venv\Scripts\python.exe -m compileall -q app run_server.py setup_first_run.py`
- lint: `.venv\Scripts\python.exe -m ruff check app tests run_server.py setup_first_run.py`
- format: `.venv\Scripts\python.exe -m ruff format --check app/routers/books.py tests/test_match_page_performance.py`
- typecheck: `.venv\Scripts\python.exe -m mypy app/logging_config.py app/database.py app/main.py app/config.py app/auth.py app/routers/backup.py app/routers/projects.py app/services/isbn_service.py app/services/completeness_service.py app/services/match_service.py app/services/validation_service.py run_server.py`
- test: `.venv\Scripts\python.exe -m pytest -q`

## 成果報告

- result_report_mode: none
- 適用情境：一般效能優化與相容性測試，驗證結果直接於回覆與 log 記錄即可。
- 報告路徑（若 mode 非 none）：`docs/reports/task-match-page-performance/`
