# Spec: task-frontend-flow-and-safety

## 目標

目前前端（`app/static/`）在跨步驟流程銜接、狀態同步、特殊字元處理與防呆上有多處影響教師實際操作順暢度與穩定性的問題：包含全站多數頁面直接拼接書名／專案名進 `innerHTML` 與 `onclick` 易破版、新建專案或點入無書單專案未引導至匯入頁、選書頁剛加入就點「修正資料」不同步且儲存修正會被踢回第 1 頁、匯出檢查頁無法單筆移除「已館藏（異常）」書目且計價設定無法帶到匯出頁、匯出頁預覽未套用覆寫價格、401 逾時體驗不一致與 422 錯誤顯示 `[object Object]` 等。

本 task 在維持現有原生 HTML / CSS / JS 輕量架構下，全面補齊前端安全性（跳脫與 401 統一處理）、修復狀態同步與 UI Bug，並打通「專案 → 匯入 → 比對 → 選書 → 檢查 → 匯出」的順暢操作流程。

## 需求範圍

1. **共用工具加固（`app/static/js/common.js`、`app/static/login.html`）**
   - 集中提供 `esc(str)`（跳脫 `&`, `<`, `>`, `"`, `'`）、`safeParseJson(str, fallback)`、`H_ALLOWED` 常數與 `requireProject(containerId)`（未選專案時在頁面頂部渲染帶連結的警告橫幅，不再永久停在「載入中...」）。
   - `showToast()` 清除前一次計時器，避免連續 Toast 提早消失。
   - `api()` 將 FastAPI 422 陣列 `detail` 與網路斷線轉為友善中文訊息（不再顯示 `[object Object]` 或 `Failed to fetch`）；遇 401 改導向 `/login.html?expired=1`，並在 `login.html` 顯示「登入已逾時，請重新登入」。

2. **全站防破版與既有 UI Bug 修復**
   - `projects.html`、`selection.html`、`match.html`、`export-check.html`、`export.html`、`import.html`、`admin-templates.html` 所有動態文字輸出改用 `esc()`；`projects.html` 卡片 `onclick` 改傳 `p.id`（從暫存陣列反查專案名稱），徹底根治含 `"`/`'`/`\` 專案名導致按鈕失效。
   - 修正繞過 `api()` 的 `fetch()`（`projects.html` 還原資料庫、`admin-templates.html` 分析範本），補齊 401 導回登入與安全錯誤解析。
   - 修復 `match.html` 使用非標準全域 `event.target`（改傳 `this`）、`projects.html` 編輯彈窗雙重 `display` 閃現、`admin-templates.html` `resetUpload()` 漏解鎖 `save-btn`。

3. **跨步驟銜接與高頻操作流暢度**
   - **`projects.html`**：建立新專案後自動切換為目前專案並引導前往 `import.html?tab=vendor`；點擊 0 本書單的專案自動導向 `import.html?tab=vendor`；編輯專案檢查非空名稱並於改名後同步 `setProject()`；還原資料庫加上二次確認與按鈕防連點。
   - **`import.html`**：支援 `?tab=vendor`（或已有館藏時預設切到書商書單分頁）；選檔後清空 `input.value` 支援同檔名重傳；步驟 C/D 手動調整欄位對應後按「上一步」不洗掉已設定對應；館藏上傳前若已有館藏顯示覆蓋確認、完成後同時提供「下一步：匯入書商書單」；步驟 E 清楚標示覆蓋說明並在匯入完成後提供「匯入另一份書單」重設鈕。
   - **`match.html`**：補上「前往選書 →」主要按鈕、未選專案橫幅、載入中狀態與錯誤處理。
   - **`selection.html`**：
     - 修復剛加入選書就點「修正資料」時 `selId` 為 `null` 的狀態不同步（`refreshBudget()` 同步回填 `selIdMap`，`saveOverrides(bookId)` 即時讀取 `selIdMap[bookId]`）。
     - 「已加入」按鈕改為可點擊取消選書；儲存單筆修正後保留目前頁碼與捲動位置；用 `sessionStorage` 暫存篩選條件。
     - `budget-bar` 改為 `position: sticky` 並顯示核定預算與剩餘／超支金額；關鍵字搜尋加上 200ms debounce 與中文組字保護；關鍵按鈕防連點。
   - **`export-check.html` 與 `export.html`**：
     - `export-check.html` 對「已館藏（異常）」書目保留「移除」按鈕；修正已清除來源的快照書目時只呼叫 `PATCH /api/selections/{selId}/overrides`；變更計價設定時透過 query 參數帶往 `export.html`；修改數量時鎖定當列輸入防連點競態；無選書時禁用「繼續匯出」。
     - `export.html` 讀取 query 參數同步計價設定、下拉選單綁定 `onchange="loadPreview()"`、預覽表定價／單價改讀 `user_overrides`、自動預填專案 `budget_amount`、用 `localStorage` 記憶上次匯出 `school_name`、無選書時禁用「產生 Excel」。

## 不做的事

- 不引入前端框架（React / Vue）或 bundler 工具鏈，維持原生靜態 HTML / CSS / JS。
- 不修改後端 API 路由結構與資料庫 schema。
- 不實作階段提示按鈕光暈動畫（仍留於 `docs/BACKLOG.md`）。

## 驗收條件

1. 所有 `app/static/*.html` 內嵌 `<script>` 與 `app/static/js/common.js` 均通過 `node --check` 語法檢查。
2. `common.js` 提供 `esc()`、`safeParseJson()`、`H_ALLOWED`、`requireProject()`，且 401 導向 `/login.html?expired=1`、422 陣列錯誤轉為可讀中文。
3. 專案名稱或書名包含 `<script>`、`"`、`'` 時不會破版或讓按鈕失效。
4. 選書頁剛加入書目後立即修正欄位會同步寫入選書快照，儲存修正後保留頁碼；「已館藏（異常）」書目可在檢查頁單筆移除；`export-check.html` 切換計價選項會正確帶至 `export.html`，且 `export.html` 預覽表顯示覆寫後價格。
5. 新增前端靜態與行為驗證測試（`tests/test_frontend_flow_and_safety.py`），且全套驗證指令（`compileall`、`ruff check`、`mypy`、`pytest -q`、JS 語法檢查）全數通過。
