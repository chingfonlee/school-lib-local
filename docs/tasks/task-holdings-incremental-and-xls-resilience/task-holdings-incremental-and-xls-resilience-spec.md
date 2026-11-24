# Spec: task-holdings-incremental-and-xls-resilience

## 目標

讓學校館藏能隨新書入館與採購完成持續累積更新，避免剛買完的書在下一個補助案重複採購；同時補強台灣圖書館與書商常見的 HTML 偽裝 `.xls`、貨幣格式價格與無 ISBN 書目弱比對提示，全程不引入任何新第三方 Python 套件、不新增資料庫 migration。

## 需求範圍

### 1. 學校館藏雙模式匯入（全校覆蓋 / 增量追加）

- `import_library_holdings()` 與 `POST /api/imports/holdings` 新增可選參數 `import_mode`，僅允許 `"replace"` 或 `"append"`，預設維持 `"replace"` 以確保完全向後相容；非法值回傳 400。
- `replace` 模式：維持既有行為（清空既有 `library_holdings` 與相關 `import_batches` / `book_matches` 後寫入新館藏，完成後重跑 `run_match()`），回傳 `import_mode: "replace"`、`replaced: True`、`skipped_duplicate_count: 0`。
- `append` 模式：
  - 不清空既有 `library_holdings`。
  - 預先載入既有館藏去重鍵集合，並在本次多工作表寫入過程中同步更新，同時防範「與既有館藏重複」及「同檔內重複列」：
    - 該列具有非空 `library_record_id` 時，去重鍵為 `(isbn_normalized or "", library_record_id.strip())`。
    - 該列無 `library_record_id` 時，去重鍵為 `(isbn_normalized or "", normalize_title_for_match(title) or (title or "").strip().lower())`。
  - 略過重複列並累計 `skipped_duplicate_count`，僅以 `executemany` 批次寫入新增館藏。
  - 若有新增館藏（`record_count > 0`），建立 `import_batches` 紀錄並在 commit 後自動重跑 `run_match()`；若全檔有效列皆為重複（`record_count == 0` 且 `skipped_duplicate_count > 0`），不建立空批次、不拋錯，回傳 `batch_id: None`、`record_count: 0`、`skipped_duplicate_count: N`、`match_rerun: False`；若完全未解析到任何有效列（`record_count == 0` 且 `skipped_duplicate_count == 0`），維持拋出 `ValueError`。
  - 回傳 `import_mode: "append"`、`replaced: False`、`record_count`（本次新增筆數）、`skipped_duplicate_count`（略過重複筆數）。
- 前端 `app/static/import.html` 館藏分頁：
  - 新增「匯入模式」選擇：全校覆蓋（預設）／增量追加（新書入館）。
  - 依所選模式調整二次確認文案（覆蓋模式警告覆蓋既有館藏；增量模式說明將保留既有館藏並略過重複）。
  - 上傳結果顯示新增筆數與略過重複筆數（含全數重複時的友善提示）。

### 2. 採購完成一鍵回流記入館藏

- 新增 `POST /api/exports/commit-to-holdings`（請求 body：`{"project_id": int}`）及對應服務函式 `commit_project_selections_to_holdings(project_id, user_id)`：
  - 驗證 `project_id` 存在（不存在回 404）；讀取該專案 `selection_items` 中 `selected_quantity > 0` 的書目，若無任何已選購書目回 400。
  - 欄位優先套用 `user_overrides` 修正後的 `title`、`author`、`publisher`、`isbn`（並重新計算 `isbn_normalized` / `isbn_status`）、`publish_date`（寫入 `publish_year`）與價格（優先 `purchase_price`，次之 `list_price`）。
  - 每筆選書產生唯一回流識別號 `library_record_id = f"PO-{project_id}-{si.id}"`。
  - 具備冪等／防重複保護：若該 `library_record_id` 已存在於 `library_holdings`（或已存在相同 `(isbn_normalized, library_record_id)`），則略過並計入 `skipped_count`。
  - 若有新寫入筆數（`inserted_count > 0`），建立一筆 `import_batches`（`project_id = NULL`、`batch_type = 'library_holdings'`、`original_filename = f"採購回流：{project_name}"`、`record_count = inserted_count`），批次 `executemany` 寫入 `library_holdings`，commit 後自動執行 `run_match()` 更新共用書單池比對狀態；若全數已回流過（`inserted_count == 0`），不建立空批次，回傳 `batch_id: None`、`inserted_count: 0`、`skipped_count: N`、`match_rerun: False`。
- 前端 `app/static/export.html`：
  - 於匯出紀錄區提供「將本案已採購書目記入館藏」按鈕與簡短說明。
  - 點擊後顯示二次確認（說明本案預計回流筆數、記入館藏後可避免下個補助案重複採購，且重複操作會自動略過已回流書目）。
  - 完成後顯示新增筆數、略過筆數與比對更新結果，並更新畫面狀態。

### 3. 常見問題 `.xls` 與格式容錯（零新第三方依賴）

- **HTML 表格偽裝的 `.xls`**：
  - 僅使用 Python 標準庫 `html.parser.HTMLParser` 實作輕量表格解析器，不引入 `lxml`、`beautifulsoup4` 或 `html5lib`。
  - 當檔案位元組非 ZIP (`PK\x03\x04`) 且非 OLE2 (`\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1`)，且開頭偵測含 HTML 標記（如 `<html`、`<!doctype`、`<table`）時，自動切換為 HTML 表格解析模式。
  - 自動依序嘗試 `utf-8-sig`、`cp950`、`big5`、`gb18030`、`utf-8 (replace)` 解碼，支援多 `<table>` 視為多工作表、處理基本 `colspan` 展開並轉為 `pd.DataFrame`。
  - `preview_excel()`、`preview_award_groups()`、`confirm_import()`、`import_vendor_books()`、`import_library_holdings()` 全數共用統一讀取層，無縫支援 HTML 偽裝 `.xls`。
- **貨幣格式容錯**：
  - `_to_float()` 清理常見前綴、單位與符號（`NT$`、`NTD`、`TW$`、`$`、`＄`、`新台幣`、`新臺幣`、`元`、`整`、半形／全形空白、半形／全形千分位逗號），維持 `math.isfinite()` 防護與既有行為相容。
- **無 ISBN 書目弱比對**：
  - `match_service.run_match()`：
    - 讀取 `library_holdings` 時納入無 ISBN 的老館藏進入 `title_index`，讓有 ISBN 的書商書目也能偵測與無 ISBN 館藏的同名重複（`same_title_different_isbn`）。
    - 新增對 `vb.isbn_status IN ('missing', 'invalid')` 書商書目的處理：寫入對應主狀態 `missing_isbn` 或 `invalid_isbn` 至 `book_matches`，並以「正規化書名＋作者相容（雙方皆有作者時須相符或互相包含；任一方缺作者時採同名命中）」比對 `library_holdings`，命中時補寫一筆 `same_title_different_isbn` 指向該 `holding_id`。
  - `GET /api/books/matches`：
    - 預設行為不變（仍只回傳 `vb.isbn_status = 'valid'`，不影響既有選書清單與測試）。
    - 當查詢參數 `match_status` 為 `missing_isbn` 或 `invalid_isbn`（或 `include_missing_isbn=true`）時，回傳對應缺／無效 ISBN 書目與其 `similar_holding` 弱比對提示。
  - `GET /api/books/stats`：
    - 維持既有欄位語意不變，額外回傳 `missing_isbn_similar_count`（缺／無效 ISBN 書目中弱比對命中館藏的筆數）。
  - 前端 `app/static/match.html`：
    - 比對狀態篩選下拉新增 `missing_isbn`（「缺 ISBN（含弱比對）」）與 `invalid_isbn`（「無效 ISBN（含弱比對）」）選項，供館員檢視無 ISBN 書目與其疑似館藏提示。

### 4. 小細節收斂

- `app/static/import.html` 的 `applyRecommendedProfile()` 改以正規化表頭（去空白、不分大小寫）比對 `previewData.source_columns`，對齊後端 `_recommend_import_profile()`。

## 不做的事

- 不新增任何第三方 Python 套件（`requirements.txt` 保持不變）。
- 不新增資料庫 migration（全程沿用既有 `import_batches`、`library_holdings`、`book_matches`、`selection_items` 欄位與既有 `CHECK` 約束）。
- 不變更 `selection.html` 預設選書清單的無 ISBN 過濾行為（無 ISBN 書目不在選書頁預設混入）。
- 不實作使用者密碼修改 UI，也不更新 `docs/user-guide/` 截圖（留待後續獨立處理）。
- 不實作 CSV / PDF 匯入或其他超出上述 4 項的匯入格式。

## 驗收條件

1. `POST /api/imports/holdings` 支援 `import_mode="replace"`（預設）與 `import_mode="append"`；`append` 模式保留既有館藏、正確依 `(isbn_normalized, library_record_id)` 與 `(isbn_normalized, normalized_title)` 去重、略過重複列、回報 `record_count` 與 `skipped_duplicate_count`，並在有新增時自動重跑 `run_match()`。
2. `POST /api/exports/commit-to-holdings` 能將指定專案 `selected_quantity > 0` 的書目（套用 `user_overrides`）回流寫入 `library_holdings` 並重跑 `run_match()`；重複呼叫具備冪等性，已回流書目不重複寫入並正確回報 `skipped_count`。
3. 以 HTML `<table>` 偽裝的 `.xls`（含 UTF-8 與 Big5/CP950 編碼）可順利通過 `preview_excel()`、`confirm_import()`、`import_vendor_books()`、`import_library_holdings()`，且無任何新第三方套件依賴。
4. `_to_float()` 可正確解析 `NT$350`、`NTD 1,200`、`$480`、`350元`、`　350 元` 等常見貨幣格式，並保留 `None` / `NaN` / `inf` 防護。
5. `run_match()` 與 `GET /api/books/matches`：
   - 既有有 ISBN 書目可偵測與無 ISBN 館藏的同名重複；
   - 查詢 `match_status=missing_isbn` 或 `invalid_isbn` 時可取得缺／無效 ISBN 書目與書名＋作者弱比對的 `similar_holding` 提示；
   - 預設呼叫（未指定 `missing_isbn` / `invalid_isbn`）結果與既有行為完全相容。
6. `import.html`、`export.html`、`match.html` 的新增 UI 與 `applyRecommendedProfile()` 正規化比對運作正常，且所有前端 inline JS 通過 `node --check`。
7. 全套驗證指令（`compileall`、`ruff check`、`ruff format --check`、`mypy`、`pytest -q`）全數通過。
