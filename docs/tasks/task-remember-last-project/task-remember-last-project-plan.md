# Plan: task-remember-last-project

## 實作步驟

1. 讀取 `app/static/js/common.js`，確認 `getProjectId`、`getProjectName`、
   `setProject`、`logout` 的完整現況。
2. 確認 `index.html`、`projects.html`、`import.html`、`match.html`、
   `selection.html`、`export-check.html`、`export.html`、`holdings.html`
   各頁如何呼叫 `getProjectId` 及是否已有 `/api/projects/{pid}` 呼叫。
3. 修改 `app/static/js/common.js`：
   a. `getProjectId()`：先讀 sessionStorage，無值再讀 localStorage
      （`parseInt` 後需 > 0，否則回傳 null）。
   b. `getProjectName()`：先讀 sessionStorage，無值再讀 localStorage；
      無值回傳「未選擇專案」。
   c. `setProject(id, name)`：同時寫入 sessionStorage 與 localStorage。
   d. 新增 `clearProject()`：同時 `removeItem` 兩處的兩個 key。
   e. `logout()`：在 `fetch /api/auth/logout` 後、導向前呼叫 `clearProject()`。
4. 確認 `projects.html` 的選取流程使用 `setProject(id, name)`
   （若已如此不需改；若有例外路徑漏寫，補上）。
5. 逐一調整步驟 2 確認的各功能頁：
   - 各頁既有 `api('/api/projects/${pid}')` 呼叫失敗時，補上
     `clearProject()`、顯示「請先選擇採購專案」、停止後續載入。
   - 以最小改動為原則：在既有 try/catch 或 .catch 內補處理，
     不新增額外驗證函式，不重構頁面整體結構。

## 風險與注意事項

- `getProjectId()` 讀取 localStorage 需確認 `parseInt > 0`，防止殘留
  `null` / `"undefined"` 字串被誤採用。
- 若某功能頁原本不呼叫 `/api/projects/{pid}`，只在 `getProjectId()` 取得
  非 null id 後才觸發驗證，不影響「未選擇專案」的提示路徑。
- localStorage 為瀏覽器本機，不區分帳號；多位教師共用同一台電腦但
  個別登入時，logout 清除可避免串號，但共用帳號仍會互相影響。
  此為已知 MVP 限制，建議 README 補一行說明，不在本任務修正。

## 預計影響範圍

- `app/static/js/common.js`（必改）
- `app/static/projects.html`（確認後可能不需改）
- 可能涉及：`app/static/index.html`、`import.html`、`match.html`、
  `selection.html`、`export-check.html`、`export.html`、`holdings.html`
  （視步驟 2 結果而定）
- 不修改 database schema、routers、services

## 驗證指令

- lint: 無既有 JS lint 指令；手動目視審查修改的 JS 函式
- format: 不適用（vanilla JS，維持現有縮排風格）
- typecheck: 不適用（vanilla JS）
- test: 無既有自動化前端測試；依手動測試步驟驗收
- build: `python -m compileall app`

手動測試步驟（啟動：`python -m uvicorn app.main:app --host 127.0.0.1 --port 8765`）：

1. 選擇專案 → DevTools → Application → localStorage，確認有
   `current_project_id`、`current_project_name`。
2. 重新整理頁面，確認專案名稱正確顯示。
3. 關閉分頁後重新開啟，確認專案名稱仍正確顯示。
4. 手動把 localStorage 的 `current_project_id` 改成不存在的 id，
   進入功能頁，確認清除並提示「請先選擇採購專案」。
5. 登出後查看 localStorage，確認兩個 key 已清除。
6. 匯入、比對、選書、匯出流程正常操作，確認不受影響。

## 成果報告

- result_report_mode: none
- 適用情境：純前端邏輯修改，無需產出報告
- 報告路徑（若 mode 非 none）：`docs/reports/task-remember-last-project/`
