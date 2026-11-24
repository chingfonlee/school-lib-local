# Plan: task-holdings-incremental-and-xls-resilience

## 實作步驟

1. **在 `app/services/import_service.py` 實作輕量 HTML 偽裝 `.xls` 解析層與貨幣格式容錯（零新依賴）**
   - 新增純標準庫 `html.parser.HTMLParser` 子類 `_HtmlTableParser`，支援解析單一或多個 `<table>`、展開基本 `colspan`、清理儲存格空白。
   - 新增 `_is_html_table_bytes(file_bytes: bytes) -> bool`（先排除 ZIP `PK\x03\x04` 與 OLE2 `\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1`，再檢查前 4096 bytes 是否含 `<html`、`<!doctype`、`<table`）與 `_decode_html_bytes(file_bytes: bytes) -> str`（依序嘗試 `utf-8-sig` → `cp950` → `big5` → `gb18030` → `utf-8 (replace)`）。
   - 新增統一檔案讀取 helper：
     - `_detect_file_engine(file_bytes: bytes, filename: str) -> str`（回傳 `"html"` / `"xlrd"` / `"openpyxl"`）。
     - `_list_excel_sheets(file_bytes: bytes, engine: str) -> list[str]` 擴充支援 `"html"`。
     - `_read_raw_sheet(file_bytes: bytes, engine: str, sheet_name=0, header=None, nrows=None) -> pd.DataFrame` 統一封裝 HTML table 與 `pd.read_excel`。
   - 讓 `_detect_header_row`、`_read_excel_with_detected_header`、`preview_excel`、`preview_award_groups`、`confirm_import`、`import_vendor_books`、`import_library_holdings` 全面改走統一 helper。
   - 強化 `_to_float(v)`：移除 `NT$`、`NTD`、`TW$`、`$`、`＄`、`新台幣`、`新臺幣`、`元`、`整`、半形／全形空白與千分位逗號後再轉 `float`，保留 `math.isfinite()` 防護。

2. **在 `app/services/import_service.py` 與 `app/routers/imports.py` 實作館藏雙模式匯入（`replace` / `append`）**
   - 新增 `VALID_HOLDINGS_IMPORT_MODES = {"replace", "append"}`。
   - 新增去重輔助邏輯（共用 `match_service.normalize_title_for_match`）：
     - 有 `library_record_id` 時鍵為 `(isbn_normalized or "", library_record_id.strip())`。
     - 無 `library_record_id` 時鍵為 `(isbn_normalized or "", normalize_title_for_match(title) or (title or "").strip().lower())`。
   - 更新 `import_library_holdings(..., import_mode: str = "replace")` 與 `_insert_library_holding_rows(...)`：
     - `replace` 模式維持既有清空後匯入行為。
     - `append` 模式不清空既有館藏，預載既有去重鍵集合並於多工作表寫入時即時更新，略過重複列並回報 `skipped_duplicate_count`。
     - 延後寫入 `import_batches` 至確認 `records_inserted > 0`；若全數為重複（`records_inserted == 0` 且 `skipped_duplicate_count > 0`），不建空批次並友善回傳 `batch_id=None, record_count=0, skipped_duplicate_count=N, match_rerun=False`。
   - 更新 `POST /api/imports/holdings` 接受可選 `import_mode: str = Form("replace")`。

3. **實作「採購完成一鍵回流記入館藏」服務與 API**
   - 在 `app/services/import_service.py` 新增 `commit_project_selections_to_holdings(project_id: int, user_id: int) -> dict`：
     - 查詢 `procurement_projects` 驗證專案存在（不存在拋 `LookupError` 或明確錯誤由 router 轉 404）。
     - 讀取該專案 `selection_items` 中 `selected_quantity > 0` 的項目；若無則拋 `ValueError`。
     - 解析每筆 `user_overrides`，合併 `title`、`author`、`publisher`、`isbn`（重算 `isbn_normalized` / `isbn_status`）、`publish_date`、`price`。
     - 產生 `library_record_id = f"PO-{project_id}-{si['id']}"`，比對既有 `library_holdings` 的 `library_record_id`（以及 `(isbn_normalized, library_record_id)`）執行冪等去重。
     - 有新增筆數時建立 `import_batches`（`project_id=NULL`、`batch_type='library_holdings'`、`original_filename=f"採購回流：{project_name}"`）並以 `executemany` 寫入 `library_holdings`，commit 後呼叫 `run_match()`。
   - 在 `app/routers/exports.py` 新增 `POST /api/exports/commit-to-holdings`（body: `CommitToHoldingsRequest(project_id: int)`），回傳 `project_id`、`project_name`、`batch_id`、`inserted_count`、`skipped_count`、`match_rerun`、`match_stats`。

4. **升級 `app/services/match_service.py` 與 `app/routers/books.py` 支援無 ISBN 書目弱比對**
   - `app/services/match_service.py`：
     - 新增 `normalize_author_for_match(author: str | None) -> str` 與 `_authors_compatible(a: str, b: str) -> bool`。
     - `run_match()` 查詢 `library_holdings` 時移除 `WHERE isbn_normalized IS NOT NULL`，讓無 ISBN 老館藏也進入 `title_index`。
     - 查詢 `vendor_books` 納入 `vb.isbn_status IN ('valid', 'missing', 'invalid')`：
       - `valid`：維持既有 `already_owned` / `available` 與 `same_title_different_isbn` 規則（同時可比對到無 ISBN 館藏）。
       - `missing` / `invalid`：寫入對應主狀態 `missing_isbn` / `invalid_isbn`；若正規化書名命中 `title_index` 且作者相容，補寫一筆 `same_title_different_isbn`。
   - `app/routers/books.py`：
     - `GET /api/books/matches` 新增可選參數 `include_missing_isbn: bool = Query(False)`：
       - 預設維持 `vb.isbn_status = 'valid'`（100% 向後相容）。
       - 當 `match_status in ("missing_isbn", "invalid_isbn")` 或 `include_missing_isbn=True` 時放寬 `vb.isbn_status` 條件，並一併回傳 `similar_holding`。
     - `GET /api/books/stats` 維持既有欄位語意不變，新增 `missing_isbn_similar_count`。

5. **更新前端頁面：`import.html`、`export.html`、`match.html`**
   - `app/static/import.html`：
     - 館藏分頁新增 `#holdings-import-mode` 模式選擇（預設 `replace`／可切 `append`），更新 `uploadHoldings()` 的確認文案、`FormData` 參數與結果顯示（含略過重複筆數）。
     - 修正 `applyRecommendedProfile()` 使用正規化表頭（去空白、不分大小寫）比對 `previewData.source_columns`。
     - 微調 `formatImportError()` 錯誤文案支援 `.xls` 提示。
   - `app/static/export.html`：
     - 於匯出紀錄區新增「將本案已採購書目記入館藏」按鈕（`#commit-holdings-btn`）、說明與結果區塊（`#commit-holdings-result`），點擊先二次確認再呼叫 `POST /api/exports/commit-to-holdings` 並顯示回流結果。
   - `app/static/match.html`：
     - `#filter-match` 新增 `missing_isbn`（「缺 ISBN（含弱比對）」）與 `invalid_isbn`（「無效 ISBN（含弱比對）」）選項。

6. **撰寫完整回歸測試並執行全套驗證**
   - 新增 `tests/test_holdings_incremental_and_xls_resilience.py`，覆蓋：
     - 館藏 `replace` 與 `append` 模式（含 `library_record_id` 去重、無 `library_record_id` 時 `isbn + normalized_title` 去重、同檔重複列、全檔重複友善回傳、非法模式 400、新增後重跑 `run_match()`）。
     - 採購完成回流記入館藏（套用 `user_overrides`、建立 `採購回流：{project_name}` 批次、回流後 `run_match()` 轉 `already_owned`、重複呼叫冪等性、無選書回 400、專案不存在回 404）。
     - HTML 偽裝 `.xls`（UTF-8 與 Big5/CP950、多 `<table>`、`colspan`）在 `preview_excel`、`confirm_import`、`import_vendor_books`、`import_library_holdings` 的完整解析。
     - `_to_float()` 貨幣格式與邊界值（`NT$`、`NTD`、`$`、`元`、全形空白與千分位、`nan`/`inf`）。
     - 無 ISBN 弱比對（老館藏無 ISBN 命中書商有 ISBN 書目；書商缺／無效 ISBN 命中館藏書名＋作者弱比對；不同作者同名書不誤報；`GET /api/books/matches` 預設行為不變且指定 `missing_isbn`/`invalid_isbn` 可查詢）。
     - 前端標記與 `applyRecommendedProfile()` 正規化比對檢查。
   - 執行全套驗證工具鏈，確認零錯誤、既有測試全數通過。

## 風險與注意事項

- **向後相容性**：
  - `import_library_holdings` 預設維持 `import_mode="replace"`；`GET /api/books/matches` 預設維持只回傳 `vb.isbn_status = 'valid'`，不影響既有測試與選書流程。
  - `run_match()` 寫入 `missing_isbn` / `invalid_isbn` 至 `book_matches` 時，`GET /api/books/stats` 的 `match_status` 查詢仍帶有 `vb.isbn_status = 'valid'` 條件，因此既有統計數字不受影響。
- **HTML 偽裝 `.xls` 誤判防護**：必須先檢查 ZIP (`PK\x03\x04`) 與 OLE2 (`\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1`) magic bytes，確認非真實 Excel 二進位檔後才進行 HTML 偵測，避免誤判正常 `.xlsx`/`.xls`。
- **回流冪等性**：使用 `PO-{project_id}-{selection_item_id}` 作為 `library_record_id`，即使老師事後修改 `user_overrides` 或重複點擊按鈕，同一筆選書也不會重複插入兩筆館藏。
- **零新依賴與零 migration**：不修改 `requirements.txt`，不新增 `migrations/*.sql`。

## 預計影響範圍

| 路徑 | 說明 |
|---|---|
| `app/services/import_service.py` | HTML 偽裝 `.xls` 解析層、`_to_float()` 貨幣容錯、館藏雙模式 `replace`/`append` 去重、`commit_project_selections_to_holdings()` |
| `app/services/match_service.py` | 納入無 ISBN 館藏與無／無效 ISBN 書商書目之書名＋作者弱比對 |
| `app/routers/imports.py` | `POST /api/imports/holdings` 新增 `import_mode` 表單參數 |
| `app/routers/exports.py` | 新增 `POST /api/exports/commit-to-holdings` 端點 |
| `app/routers/books.py` | `GET /api/books/matches` 支援查詢 `missing_isbn`/`invalid_isbn` 與 `include_missing_isbn`；`stats` 新增 `missing_isbn_similar_count` |
| `app/static/import.html` | 館藏雙模式切換與確認文案、`applyRecommendedProfile()` 正規化表頭比對 |
| `app/static/export.html` | 新增「將本案已採購書目記入館藏」按鈕、二次確認與結果顯示 |
| `app/static/match.html` | 比對狀態篩選新增「缺 ISBN（含弱比對）」「無效 ISBN（含弱比對）」 |
| `tests/test_holdings_incremental_and_xls_resilience.py`（新增） | 階段 3 全功能與邊界條件回歸測試 |

## 驗證指令

- lint: `.venv\Scripts\python.exe -m ruff check app tests run_server.py setup_first_run.py`
- format: `.venv\Scripts\python.exe -m ruff format --check app/services/import_service.py app/services/match_service.py app/routers/imports.py app/routers/exports.py app/routers/books.py tests/test_holdings_incremental_and_xls_resilience.py`
- typecheck: `.venv\Scripts\python.exe -m mypy app/logging_config.py app/database.py app/main.py app/config.py app/auth.py app/routers/backup.py app/routers/projects.py app/services/isbn_service.py app/services/completeness_service.py app/services/match_service.py app/services/validation_service.py run_server.py`
- test: `.venv\Scripts\python.exe -m pytest -q`（含所有前端 JS `node --check` 檢查）
- build: `.venv\Scripts\python.exe -m compileall -q app run_server.py setup_first_run.py`

## 成果報告

- result_report_mode: none
- 適用情境：無
- 報告路徑（若 mode 非 none）：`docs/reports/task-holdings-incremental-and-xls-resilience/`
