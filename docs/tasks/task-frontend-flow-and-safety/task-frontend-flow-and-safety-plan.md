# Plan: task-frontend-flow-and-safety

## 實作步驟

1. **強化 `app/static/js/common.js` 與 `app/static/login.html`**
   - 新增 `esc()`、`safeParseJson()`、`H_ALLOWED`、`requireProject()`。
   - 修正 `showToast()` 計時器互蓋問題；強化 `api()` 的 401 `?expired=1` 跳轉與 422／斷線友善中文錯誤解析。
   - `login.html` 偵測 `?expired=1` 顯示逾時提示。

2. **更新 `app/static/projects.html` 與 `app/static/admin-templates.html`**
   - `projects.html`：移除彈窗多餘 `display:flex`；全頁補 `esc()`；卡片 `onclick` 改傳 `p.id` 反查名稱；新建專案自動切換並引導至 `import.html?tab=vendor`；點擊無書單專案自動進 `import.html?tab=vendor`；改名同步 `setProject()`；還原資料庫改用 401 保護、加二次確認與按鈕防連點。
   - `admin-templates.html`：補 `esc()`、`resetUpload()` 恢復 `save-btn.disabled = false`、`analyzeTemplate()` 補 401 處理、改用 `projectTypeLabel()`。

3. **更新 `app/static/import.html` 與 `app/static/match.html`**
   - `import.html`：支援 `?tab=vendor` 與已有館藏自動切分頁；選檔後清空 `input.value`；保留步驟 C/D 已調整的對應；館藏上傳補覆蓋確認與「匯入書商書單」按鈕；步驟 E 補清楚覆蓋說明與「匯入另一份書單」重設鈕；補 `esc()` 與按鈕防連點。
   - `match.html`：補「前往選書 →」主按鈕、`requireProject()`、載入中與 `try/catch`、`runMatch(this)` 取代全域 `event.target`、全頁 `esc()` 與 `safeParseJson()`。

4. **更新 `app/static/selection.html`**
   - 改用共用 `H_ALLOWED`、`esc()`、`safeParseJson()`、`requireProject()`。
   - `refreshBudget()` 同步更新 `selIdMap`，`saveOverrides(bookId)` 即時讀 `selIdMap[bookId]` 修復不同步。
   - 「已加入」按鈕可點擊取消選書；儲存修正保留頁碼與捲動位置；`sessionStorage` 記住篩選條件；`budget-bar` 設 `sticky` 並顯示核定預算與剩餘／超支；搜尋加 200ms debounce 與組字保護；按鈕防連點。

5. **更新 `app/static/export-check.html` 與 `app/static/export.html`**
   - `export-check.html`：改用共用 `H_ALLOWED`、`esc()`、`safeParseJson()`、`requireProject()`；對 `already_owned` 保留「移除」按鈕；修正已清除來源快照時僅呼叫 `PATCH /api/selections/{selId}/overrides`；計價設定帶入「繼續匯出」query；無選書時禁用按鈕；修改數量鎖定當列輸入防競態。
   - `export.html`：改用 `esc()`、`safeParseJson()`、`requireProject()`；讀取 query 同步計價設定、下拉綁定 `onchange="loadPreview()"`、預覽表讀 `ov.list_price`/`ov.purchase_price`、預填 `budget_amount`、記憶 `school_name`、無選書時禁用按鈕。

6. **新增前端驗證測試並執行完整驗證**
   - 新增 `tests/test_frontend_flow_and_safety.py`：
     - 驗證 `app/static/js/common.js` 與所有 `app/static/*.html` 內嵌 `<script>` 皆通過 `node --check` 語法檢查。
     - 驗證關鍵修復回歸項目（`esc()` / `requireProject()` / `H_ALLOWED` 集中、`projects.html` 無雙重 `display`、`admin-templates.html` `resetUpload` 解鎖 `save-btn`、`match.html` 無 `event.target`、`export.html` 預覽套用 `ov.list_price`/`ov.purchase_price` 等）。
   - 執行全套驗證指令確保全數 pass。

## 風險與注意事項

- **既有測試與截圖腳本相容性**：保留既有 HTML 元素 `id` 與 API 路徑不變，避免影響 `scripts/take-screenshots.py` 或使用者手冊說明。
- **`node --check` 在 CI 環境**：GitHub Actions `ubuntu-latest` 預設內建 Node.js，測試中若找不到 `node` 可明確報錯或由測試驗證。

## 預計影響範圍

| 路徑 | 說明 |
|---|---|
| `app/static/js/common.js` | `esc()`、`safeParseJson()`、`H_ALLOWED`、`requireProject()`、401/422 處理、Toast 修復 |
| `app/static/login.html` | 顯示 `?expired=1` 登入逾時提示 |
| `app/static/projects.html` | 跳脫、卡片改傳 `id`、彈窗閃現修復、自動導向 `import.html`、還原防呆 |
| `app/static/import.html` | 預設分頁、同檔名重傳、保留對應、覆蓋確認與重設鈕、跳脫 |
| `app/static/match.html` | 「前往選書 →」按鈕、`runMatch(this)`、未選專案橫幅、跳脫 |
| `app/static/selection.html` | 修復 `selIdMap` 同步、可取消選書、保留頁碼、`sticky` 預算列、debounce、跳脫 |
| `app/static/export-check.html` | 已館藏可移除、脫鉤快照修正、計價設定帶往匯出、數量防競態、跳脫 |
| `app/static/export.html` | 接收計價設定、`onchange` 重算、預覽套用覆寫價、自動帶預算與校名、跳脫 |
| `app/static/admin-templates.html` | `resetUpload` 解鎖按鈕、401 保護、跳脫 |
| `tests/test_frontend_flow_and_safety.py`（新增） | JS 語法檢查與前端回歸驗證測試 |

## 驗證指令

- lint: `.venv\Scripts\python.exe -m ruff check app tests`
- format: `.venv\Scripts\python.exe -m ruff format --check tests/test_frontend_flow_and_safety.py`
- typecheck: `.venv\Scripts\python.exe -m mypy app/logging_config.py app/database.py app/main.py app/routers/backup.py app/routers/projects.py app/services/isbn_service.py app/services/completeness_service.py app/services/match_service.py app/services/validation_service.py`
- test: `.venv\Scripts\python.exe -m pytest -q`（含 `node --check` 檢查所有前端 JS 語法）
- build: `.venv\Scripts\python.exe -m compileall -q app`

## 成果報告

- result_report_mode: none
- 適用情境：無
- 報告路徑（若 mode 非 none）：`docs/reports/task-frontend-flow-and-safety/`
