# Spec: task-selection-ux-and-project-merge

## 目標

減輕老師與圖書管理員在大量書商書單中挑書的認知負擔、避免在選書頁誤點重複購買多本，並提供跨專案選書匯整能力，支援將各班級或師生推薦專案的選書清單安全匯入正式採購專案。

本任務嚴守務實與 Ponytail 簡化原則：**零新增第三方套件、零資料庫 migration**，全面沿用既有 SQLite schema、FastAPI 架構與原生靜態 HTML/CSS/JS。

## 需求範圍

### 1. 出版年排序與近幾年新書快篩（`selection.html`）

- 排序下拉選單 `#filter-sort` 新增兩個選項：
  - `pub_desc`：「出版最新優先（新→舊）」
  - `pub_asc`：「出版年份（舊→新）」
- 實作輕量日期解析函式 `parsePublishSortKey(raw)`（以及年份提取 helper）：
  - 相容常見書商格式：`YYYY/MM/DD`、`YYYY-MM-DD`、`YYYY.MM.DD`、`YYYY/MM`、`YYYY-MM`、`YYYY年MM月DD日`、`YYYY年MM月`、`YYYY年`、`YYYY`。
  - 相容民國年格式：3 位數年份（如 `114/05/01`、`114/05`、`114年`、`114`）自動 `+1911` 轉為西元年。
  - 轉換為可比較整數 `YYYYMMDD`（缺月補 `01`、缺日補 `01`）；空值或無法解析為合理年份（西元 1900–2100）者回傳 `null`。
  - 在 `pub_desc` 與 `pub_asc` 兩種排序下，無出版日或無法解析者皆**固定置底**，同值時依 `id` 穩定排序。
- 新增「出版年份」篩選下拉 `#filter-pub-year`：
  - 選項：`全部`、`近 1 年`、`近 2 年`、`近 3 年`、`近 5 年`。
  - 依當年西元年份（`new Date().getFullYear()`）計算門檻（例如「近 3 年」為 `currentYear - 2` 起，「近 1 年」為當年）；無出版日或無法解析者不納入該篩選結果。
  - 納入 `FILTER_IDS`、`resetFilters()` 與 `sessionStorage` 記憶。

### 2. 一鍵情境快捷按鈕與選書鎖定規則（`selection.html`、`style.css`）

- **選書鎖定規則（防止誤點重複買多本）**：
  - 在 `selection.html` 選書時，點選「＋ 加入選書」預設以數量 `1` 加入。
  - 一旦書目已加入本案選書（`selected_quantity > 0`），該書的操作按鈕自動鎖定為 `disabled`：
    - 數量為 1 時顯示：`✓ 已加入（1本）`
    - 數量大於 1 時顯示：`✓ 已加入（N本）`
    - 按鈕 `title` 提示：「已加入選書，如需調整數量或移除請至「5 匯出前檢查」」。
  - 不可在選書頁重複點擊累加數量，亦不在選書頁點擊已加入按鈕直接取消；如需購買 2 本以上或移除單本，統一前往「5 匯出前檢查（`export-check.html`）」調整數量或移除。
  - 既有「加入本頁」功能維持自動略過已選書目，與鎖定規則一致。
- **一鍵情境快捷按鈕（Preset Chips）**：
  - 於篩選列上方提供 4 個快捷按鈕（再次點擊已啟用中的快捷鈕可取消該快捷條件）：
    1. `只看可買新書`：設比對狀態為 `available`、出版年份為 `近 3 年`、排序為 `pub_desc`。
    2. `只看已獲獎好書`：設比對狀態為 `available`，並篩選具官方／主要獎項之書目（`recommendation_source` 非空且非 `學校自選(請備註原因)`，或 `award_item` 非空且非 `自選`／`學校自選(請備註原因)`；同時納入 `user_overrides` 覆寫值判斷）。
    3. `只看未選書目`：僅顯示尚未加入本案選書清單的書目（`!selMap[b.id]`），方便越挑越清爽。
    4. `只看已選清單`：僅顯示本案已加入選書的書目（`selMap[b.id] > 0`），並於書目列表上方顯示明顯的「前往匯出前檢查調整數量 →」提示與連結。
  - 快捷篩選狀態（已獲獎篩選、未選／已選篩選）隨篩選條件記憶於 `sessionStorage`，並於「重設篩選」時一併清除。

### 3. 「卡片模式 ⇄ 精簡列表模式」切換（`selection.html`、`style.css`）

- 提供檢視模式切換按鈕（`卡片模式` / `精簡列表`），使用者偏好記憶於 `localStorage`（預設為 `卡片模式`）。
- **精簡列表模式**：
  - 以緊湊表格一列呈現一本書，欄位包含：
    - 書名（附關鍵徽章：書商、比對狀態含館藏冊數、完整度、疑似同名館藏、他案已匯出／選書中、多家供貨比價摘要）
    - 作者
    - 出版社
    - 出版年
    - 單價（優先顯示採購單價，無則顯示定價）
    - 操作：`＋加入`／`✓ 已加入（N本）` 鎖定鈕、`修正` 連結、`查館藏` 連結
  - 點擊「修正」可在該列下方展開既有的內嵌「修正資料」表單，共用 `saveOverrides()` 儲存邏輯。
  - 與分頁（每頁 50 筆）、篩選、排序、「加入本頁」完全相容。

### 4. 置頂「視覺預算進度條 ＋ 年段／分類分佈小統計」（`selection.html`、`style.css`）

- **視覺預算進度條**：
  - 在置頂 `#budget-bar` 中，當專案有設定 `budget_amount > 0` 時，顯示預算達成率進度條（依專案 `subtotal_mode` 計算已用金額與達成率 `%`）與剩餘／超支金額。
  - 進度條顏色規則：
    - `< 90%`：藍色
    - `90%–100%`：綠色
    - `> 100%`：紅色（條寬度上限 `100%`，文字標示實際 `%` 與超支金額）
  - 未設定預算或 `budget_amount <= 0` 時不顯示進度條。
- **年段／分類分佈小統計**：
  - 在置頂 `#budget-bar` 旁提供可展開／收合的「已選分佈」按鈕與精簡面板。
  - 即時統計本案已選書目（`selData.items`）的**適讀年齡**（`age_range`）與**分類**（`category`）各幾本（空值歸為「未標示」），並於每次選書、清空或匯入後自動更新。

### 5. 多專案選書匯整（「從其他專案匯入選書」）

- **後端 Service（`app/services/selection_service.py`）**：
  - 新增 `import_selections_from_projects(target_project_id: int, source_project_ids: list[int], user_id: int, skip_already_owned: bool = True) -> dict[str, int]`：
    - 驗證 `target_project_id` 存在（不存在時拋出 `ValueError`），讀取其 `project_type`。
    - 自動排除 `target_project_id` 自身並去重 `source_project_ids`。
    - 從指定來源專案讀取 `selected_quantity > 0` 的 `selection_items`。
    - **自動去重**：若目標專案已選同一本（依 `vendor_book_id` 或非空 `isbn_normalized` 判斷，含本次多來源匯入過程中已新增的項目），則略過並計入 `skipped_duplicate`（不累加數量）。
    - **自動略過已館藏（預設開啟 `skip_already_owned=True`）**：若該書對應 `vendor_book_id` 目前在 `book_matches` 最新有效比對狀態為 `already_owned`，或其非空 `isbn_normalized` 已存在於 `library_holdings`，則略過並計入 `skipped_owned`。
    - **寫入目標專案**：符合條件者以 `selected_quantity = 1` 複製完整快照（含 `user_overrides`、`extra_fields`、`raw_row`、來源批次資訊），並依目標專案 `project_type` 重算 `completeness_status` 後寫入 `selection_items`。
    - 回傳 `{"added": int, "skipped_duplicate": int, "skipped_owned": int}`。
- **後端 API（`app/routers/selections.py`）**：
  - 新增 `POST /api/selections/import-from-projects`（需登入驗證 `require_auth`）：
    - Request body：`{"target_project_id": int, "source_project_ids": list[int], "skip_already_owned": bool = True}`（`source_project_ids` 至少 1 筆）。
    - Response：`{"added": int, "skipped_duplicate": int, "skipped_owned": int}`；目標專案不存在時回傳 `404`。
- **前端介面（`app/static/selection.html`、`app/static/css/style.css`）**：
  - 於頁面上方操作區新增「從其他專案匯入選書」按鈕。
  - 點擊開啟小型彈窗，呼叫 `GET /api/projects/` 列出除目前專案外的其他專案（顯示專案名稱、年度、採購類型、已選筆數、封存標記）供多選勾選。
  - 提供「自動略過已館藏書目」勾選框（預設勾選）。
  - 執行匯入後顯示結果摘要（新增／略過重複／略過已館藏本數）並重新載入選書頁資料與預算統計。

## 不做的事

- 不新增任何第三方 Python 或前端套件。
- 不新增或修改資料庫 schema（零 DB migration）。
- 不在 `selection.html` 提供將單本數量直接調高至 2 本以上的輸入框，也不提供在選書頁直接點已加入按鈕取消單本（調整數量與移除維持統一在 `export-check.html` 進行）。
- 不修改 `export-check.html` 的既有核對、數量編輯與移除邏輯。
- 不實作多人即時協作鎖定或跨專案雙向同步（匯入為一次性快照複製）。

## 驗收條件

1. **出版年排序與快篩**：
   - `parsePublishSortKey` 正確解析 `YYYY/MM/DD`、`YYYY-MM-DD`、`YYYY/MM`、`YYYY` 及民國年（如 `114/05`、`114年`），無出版日或無法解析者在「新→舊」與「舊→新」排序皆固定置底。
   - 「出版年份」下拉可正確篩選近 1／2／3／5 年新書，且篩選值可於 `sessionStorage` 記憶並由「重設篩選」清除。
2. **選書鎖定與情境快捷鈕**：
   - 點選「＋ 加入選書」後按鈕立即鎖定為 `disabled` 的 `✓ 已加入（1本）`（若於 `export-check.html` 改為 N 本，回選書頁顯示 `✓ 已加入（N本）` 且維持鎖定），無法在選書頁重複點擊多買。
   - 四個快捷按鈕（`只看可買新書`、`只看已獲獎好書`、`只看未選書目`、`只看已選清單`）均可正確套用與取消；「只看已選清單」時呈現前往匯出前檢查的明顯引導連結。
3. **卡片 ⇄ 精簡列表切換**：
   - 可在卡片模式與精簡列表模式間即時切換並記憶於 `localStorage`；精簡列表正確顯示關鍵徽章、價格、鎖定態加入按鈕，且可展開內嵌「修正資料」並儲存。
4. **視覺預算進度條與已選分佈**：
   - 有設定預算時，置頂 `budget-bar` 正確顯示進度條百分比、三段色彩（`< 90%` 藍、`90%–100%` 綠、`> 100%` 紅）與剩餘／超支金額；展開「已選分佈」正確顯示各適讀年齡與分類的本數統計並隨選書即時更新。
5. **多專案選書匯整**：
   - `import_selections_from_projects` 與 `POST /api/selections/import-from-projects` 正確複製來源選書（數量固定為 1、保留 `user_overrides`、依目標專案 `project_type` 重算 `completeness_status`），依 `vendor_book_id`／`isbn_normalized` 自動去重，且 `skip_already_owned=True/False` 行為符合預期。
   - 前端匯入彈窗可多選來源專案、切換是否略過已館藏、顯示匯入結果摘要並刷新選書清單與預算。
6. **品質驗證**：
   - 專案 5 項工具鏈（`compileall`、`ruff check`、`ruff format --check`、`mypy`、`pytest -q`）與 `node --check`（驗證 `selection.html` 內嵌 `<script>` 語法）全部通過。
