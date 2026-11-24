# Plan: task-selection-ux-and-project-merge

## 實作步驟

1. **實作多專案選書匯整後端 Service（`app/services/selection_service.py`）**
   - 新增 `import_selections_from_projects(target_project_id: int, source_project_ids: list[int], user_id: int, skip_already_owned: bool = True) -> dict[str, int]`：
     - 在單一 `db_session` 中查詢目標專案（取得 `project_type`，不存在則 raise `ValueError`）。
     - 清理 `source_project_ids`（去重、排除 `target_project_id`）；若為空直接回傳全 0 計數。
     - 預載目標專案既有 `selection_items` 的 `vendor_book_id` 與非空 `isbn_normalized` 集合。
     - 若 `skip_already_owned=True`，預載 `library_holdings` 的非空 `isbn_normalized` 集合，並在查詢來源 `selection_items` 時一併查出最新有效 `book_matches`（排除 `same_title_different_isbn`）的 `match_status` 與 `holding_id`。
     - 逐筆走訪來源專案 `selected_quantity > 0` 的 `selection_items`：
       - 若 `vendor_book_id` 或非空 `isbn_normalized` 已存在於目標集合 → `skipped_duplicate += 1`。
       - 若 `skip_already_owned=True` 且最新 `match_status == 'already_owned'` 或 `isbn_normalized` 在館藏集合 → `skipped_owned += 1`。
       - 否則複製快照欄位（保留 `user_overrides`、`extra_fields`、`raw_row`、`notes` 等），固定設 `selected_quantity = 1`，依目標專案 `project_type` 呼叫 `compute_completeness()` 重算 `completeness_status`，寫入 `selection_items`，並更新目標去重集合與 `added += 1`。
     - Commit 後回傳 `{"added": added, "skipped_duplicate": skipped_duplicate, "skipped_owned": skipped_owned}`。
2. **新增多專案選書匯整 API 端點（`app/routers/selections.py`）**
   - 定義 `ImportFromProjectsRequest(BaseModel)`：`target_project_id: int`、`source_project_ids: list[int] = Field(..., min_length=1)`、`skip_already_owned: bool = True`。
   - 新增 `POST /api/selections/import-from-projects`（`Depends(require_auth)`），呼叫 `import_selections_from_projects`，捕捉 `ValueError` 回傳 `HTTPException(status_code=404, detail=str(e))`。
3. **新增選書頁樣式（`app/static/css/style.css`）**
   - 補充以下輕量純 CSS 樣式：
     - 視覺預算進度條（`.budget-progress-wrap`、`.budget-progress-track`、`.budget-progress-fill` 及 `.is-normal` / `.is-near` / `.is-over` 三色狀態）與已選分佈展開面板（`.selection-dist-panel`、`.dist-chip`）。
     - 一鍵情境快捷按鈕列（`.preset-chips-bar`、`.preset-chip`、`.preset-chip.active`）。
     - 精簡列表模式表格（`.books-list-table`、徽章緊湊排列、內嵌修正列樣式）與檢視切換按鈕群組（`.view-toggle`）。
     - 選書鎖定按鈕狀態（`.book-cta.selected` 改為鎖定禁用樣式，移除原本 hover 變紅取消樣式）。
     - 「從其他專案匯入選書」小型彈窗（`.modal-backdrop`、`.modal-dialog`、`.modal-project-list`）。
4. **升級選書頁前端功能（`app/static/selection.html`）**
   - **出版年解析、排序與快篩**：
     - 實作 `parsePublishSortKey(raw)` 與 `parsePublishYear(raw)`（支援西元多種分隔／中文年月與民國 3 位數年 `+1911`，無效值回傳 `null`）。
     - `#filter-sort` 新增 `pub_desc` 與 `pub_asc`，更新 `compareBooks()` 使 `null` 固定置底。
     - 新增 `#filter-pub-year`（全部 / 近 1 年 / 近 2 年 / 近 3 年 / 近 5 年），納入 `FILTER_IDS`、`applyFilter()` 與 `resetFilters()`。
   - **選書鎖定規則**：
     - 更新卡片與精簡列表的 CTA 渲染：已選書目顯示 `disabled` 的 `✓ 已加入（${qty}本）` 與引導 tooltip；`addBook()` 成功後改為鎖定狀態並移除 `removeBook()` 呼叫路徑。
   - **一鍵情境快捷按鈕（Preset Chips）**：
     - 新增 4 個快捷按鈕（`只看可買新書`、`只看已獲獎好書`、`只看未選書目`、`只看已選清單`）與對應狀態變數 `awardOnly`、`selFilterMode`（同步存取於 `sessionStorage`）。
     - 實作 `hasOfficialAward(b)` 判斷（支援 `user_overrides` 覆寫值）。
     - 啟用 `只看已選清單` 時於列表上方顯示「前往匯出前檢查調整數量 →」引導提示條。
   - **卡片 ⇄ 精簡列表模式切換**：
     - 新增檢視切換按鈕，偏好存於 `localStorage`（key: `selection_view_mode`）。
     - 實作 `renderListView(books)`，在緊湊表格中呈現書名＋關鍵徽章、作者、出版社、出版年、單價、鎖定態加入按鈕、展開式「修正資料」列與「查館藏」連結。
   - **置頂預算進度條與已選分佈小統計**：
     - 更新 `updateBudgetBar(summary)` 計算並渲染進度條寬度、百分比、三段顏色與剩餘／超支金額。
     - 儲存最新 `currentSelectionItems`（來自 `selData.items`），實作 `renderSelectionDistribution(items)` 即時彙整適讀年齡與分類本數，並提供收合切換按鈕。
   - **多專案選書匯整彈窗**：
     - 頂部操作區新增「從其他專案匯入選書」按鈕與 modal HTML。
     - 實作開啟彈窗載入 `/api/projects/`、勾選其他專案與「自動略過已館藏書目」、送出 `POST /api/selections/import-from-projects`、顯示結果摘要並呼叫 `loadData()` 刷新。
5. **撰寫單元與整合測試並執行全套驗證**
   - 新增 `tests/test_selection_ux_and_project_merge.py`，覆蓋：
     - `import_selections_from_projects`：正常匯入（`selected_quantity = 1`、保留 `user_overrides`、依目標 `project_type` 重算 `completeness_status`）、`vendor_book_id` 去重、`isbn_normalized` 跨書商去重、多來源同書去重、`skip_already_owned=True`（含 `book_matches` 與 `library_holdings` 兩種情境）與 `skip_already_owned=False`、排除目標自身、目標專案不存在回傳錯誤。
     - `POST /api/selections/import-from-projects` API 端點（正常 200、目標不存在 404、空 `source_project_ids` 422）。
     - 前端 `selection.html` 靜態結構與關鍵函式檢查（`parsePublishSortKey` 邊界案例透過 `node` 腳本實測西元／民國／無效日期、按鈕鎖定規則、4 個 preset chips、列表切換與匯入彈窗元素）。
   - 執行全套 5 項驗證指令與 `node --check`，確認零錯誤、零回歸。

## 風險與注意事項

- **同書異書商去重**：跨專案匯入時，來源專案與目標專案可能選到不同 `vendor_book_id` 但相同 `isbn_normalized` 的書目；去重必須同時檢查 `vendor_book_id` 與非空 `isbn_normalized`，避免目標專案出現重複書目。
- **來源書單已清除的快照**：來源專案的 `selection_items` 可能對應已刪除的 `vendor_book_id`（`vendor_book_id` 為 `NULL` 或 `vendor_books` 已不存在）；匯入邏輯須直接複製 `selection_items` 的快照欄位，不可 `INNER JOIN vendor_books` 導致漏匯。
- **跨專案類型完整度重算**：例如從 `custom` 專案（師生推薦清單）匯入到 `general_books` 或 `local_culture` 正式補助專案時，必須依目標專案的 `project_type` 重算 `completeness_status`，確保匯出前檢查準確。
- **選書鎖定與「只看未選書目」互動**：在「只看未選書目」模式下點擊加入時，按鈕立即鎖定為 `✓ 已加入（1本）` 而不強制整頁瞬間重排，避免卡片／表格突然移位造成老師誤點下一本。
- **XSS 與空值防禦**：精簡列表模式、分佈統計標籤、匯入彈窗內的專案名稱與年度皆須使用 `esc()` 跳脫；日期解析需妥善處理空字串、純數字非年份字串與異常格式，不得拋出例外。
- **零 DB migration**：完全使用既有 `selection_items`、`procurement_projects`、`book_matches`、`library_holdings` 欄位，不變更資料表結構。

## 預計影響範圍

- `app/services/selection_service.py`（修改）
- `app/routers/selections.py`（修改）
- `app/static/selection.html`（修改）
- `app/static/css/style.css`（修改）
- `tests/test_selection_ux_and_project_merge.py`（新增）
- `docs/STATUS.md`、`docs/BACKLOG.md`、`docs/tasks/task-selection-ux-and-project-merge/*`（任務紀錄）

## 驗證指令

- compile: `.venv\Scripts\python.exe -m compileall -q app run_server.py setup_first_run.py`
- lint: `.venv\Scripts\python.exe -m ruff check app tests run_server.py setup_first_run.py`
- format: `.venv\Scripts\python.exe -m ruff format --check app/services/selection_service.py app/routers/selections.py tests/test_selection_ux_and_project_merge.py`
- typecheck: `.venv\Scripts\python.exe -m mypy app/logging_config.py app/database.py app/main.py app/config.py app/auth.py app/routers/backup.py app/routers/projects.py app/routers/selections.py app/services/isbn_service.py app/services/completeness_service.py app/services/match_service.py app/services/selection_service.py app/services/validation_service.py run_server.py`
- test: `.venv\Scripts\python.exe -m pytest -q`
- js-check: 以 `node --check` 驗證 `app/static/selection.html` 內嵌 `<script>` 語法（並以 `node` 驗證 `parsePublishSortKey` 解析行為）

## 成果報告

- result_report_mode: none
- 適用情境：一般功能擴充與前端體驗優化，驗證結果直接於回覆與 log 記錄即可。
- 報告路徑（若 mode 非 none）：`docs/reports/task-selection-ux-and-project-merge/`
