# Spec: task-duplicate-purchase-prevention

## 目標

目前系統的館藏比對只依賴 ISBN 精確一致，實務上老師選書時仍有四個常見的「誤買重複書」盲點：
1. 後端雖已計算 `same_title_different_isbn`（同書名但不同版／不同 ISBN），但 `GET /api/books/matches` 與前端完全隱藏此資訊，老師在選書頁看不到提醒。
2. 書名比對僅移除空白，對全半形、標點符號與常見版本括號字樣（如「精裝」「平裝」「修訂版」）過於嚴格，改版或再版書容易漏判。
3. 學校同時執行多個採購補助案（如本土文化、一般圖書、偏鄉閱讀）時，在 A 專案已選購但尚未入館藏系統的書目，在 B 專案選書完全沒有提醒。
4. 館藏只顯示「已館藏」，未顯示目前館藏共有幾冊，老師無法快速判斷是「已有 1 冊想補買」還是「已有多冊不應重複採購」。

本 task 在**不變更資料庫 schema、不破壞既有 `match_status` 語意**的前提下，全面升級防重複買書提醒機制，涵蓋同名不同版警示、書名正規化輔助比對、跨專案已選購提醒與館藏複本數顯示。

## 需求範圍

1. **書名正規化輔助比對（`app/services/match_service.py`）**
   - 新增 `normalize_title_for_match(title: str | None) -> str`：
     - 使用 `unicodedata.normalize("NFKC", title)` 統一全半形並轉小寫。
     - 移除括號（`(...)`、`[...]`) 內常見版本／裝幀字樣（如精裝、平裝、修訂版、增訂版、新版、二版、三版、繪本版等）。
     - 移除中英文標點符號與所有空白字元。
     - 若正規化後長度小於 2 個字元（避免單字誤報），回傳空字串不參與書名比對。
   - `run_match()` 在建立 `title_index` 與比對 `same_title_different_isbn` 時改用 `normalize_title_for_match()`。

2. **比對結果與統計 API 擴充（`app/routers/books.py`）**
   - 保持 `GET /api/books/matches` 每筆書目的既有欄位與 `match_status`（`available` / `already_owned`）不變，額外附加三個只讀輔助欄位（批次查詢，不可逐筆 N+1）：
     - `holding_copies: int`：該書 `isbn_normalized` 在 `library_holdings` 的總冊數（無館藏為 `0`）。
     - `similar_holding: dict | None`：若該書於 `book_matches` 有 `same_title_different_isbn` 記錄，回傳對應館藏的 `{title, author, publisher, isbn}`；否則為 `None`。
     - `other_project_selections: list[dict]`：其他專案（`si.project_id != project_id` 且 `si.selected_quantity > 0`）中具有相同 `isbn_normalized` 的選書紀錄，回傳去重後的 `[{"project_id": int, "project_name": str}]`。
   - `GET /api/books/matches` 支援新增可選篩選參數（或在前端整合篩選），並於 `GET /api/books/stats` 額外回傳：
     - `same_title_different_isbn_count: int`（目前專案有同名不同 ISBN 警示的書目筆數）
     - `other_project_duplicate_count: int`（目前專案與其他專案重複選購的書目筆數）

3. **比對頁與選書頁防重複 UI 呈現（`app/static/match.html`、`app/static/selection.html`、`app/static/css/style.css`）**
   - **館藏複本數**：當 `match_status === 'already_owned'` 且 `holding_copies > 0` 時，顯示為 `已館藏（N冊）`（或於徽章旁清楚標註冊數）。
   - **疑似同名館藏警示**：當 `similar_holding` 非空時，顯示醒目黃色徽章「疑似同名館藏」，並於文字或提示區顯示比對到的館藏書名、作者與 ISBN（所有動態欄位皆使用 `esc()` 跳脫）。此提醒僅作警示，不強制阻擋加入選書。
   - **跨專案重複選購警示**：當 `other_project_selections.length > 0` 時，顯示醒目提示徽章「他案已選」並列出對應專案名稱（以 `esc()` 跳脫）。此提醒僅作警示，不強制阻擋加入選書。
   - **統計與篩選**：
     - `match.html` 統計列新增「疑似同名館藏」與「他案已選」統計卡片，篩選下拉新增「疑似同名館藏」與「他案已選」篩選選項。
     - `selection.html` 比對狀態篩選下拉新增「疑似同名館藏」與「他案已選」選項，方便老師快速檢視所有潛在重複書目。

## 不做的事

- 不新增資料庫 migration 或變更既有資料表結構。
- 不將「疑似同名館藏」或「他案已選」設為匯出阻擋（blocking）條件，仍保留老師最終判斷權。
- 不變更既有 `already_owned` 與 `force_owned` 的匯出檢查與匯出規則。
- 不在此 task 實作多書商累加匯入、館藏增量匯入或無 ISBN 模糊比對（已排入 Backlog 階段 2 與階段 3）。

## 驗收條件

1. `normalize_title_for_match()` 正確將 `魔法校車：人體大冒險（精裝）` 與 `魔法校車 人體大冒險` 正規化為相同鍵值，且單字書名不誤觸發比對。
2. `run_match()` 能偵測含標點／版本差異的同名不同 ISBN 書目並寫入 `same_title_different_isbn`。
3. `GET /api/books/matches` 正確回傳 `holding_copies`、`similar_holding`、`other_project_selections`，且不破壞既有欄位與 `match_status`。
4. `GET /api/books/stats` 正確回傳 `same_title_different_isbn_count` 與 `other_project_duplicate_count`。
5. `match.html` 與 `selection.html` 正確渲染館藏冊數、疑似同名館藏警示（含館藏書名／ISBN）與他案已選警示（含專案名稱），且皆經 `esc()` 跳脫、支援篩選、通過 `node --check` 語法檢查。
6. 全套驗證指令（`compileall`、`ruff check`、`ruff format --check`、`mypy`、`pytest -q`）全數通過。
