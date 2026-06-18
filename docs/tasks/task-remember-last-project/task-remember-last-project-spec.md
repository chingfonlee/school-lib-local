# Spec: task-remember-last-project

## 目標

使用者在 projects.html 選擇採購專案後，系統將該選擇寫入 localStorage，讓使用者
關閉瀏覽器後重新開啟系統時，自動沿用上次最後選擇的專案，無需重新選擇。
若上次專案已不存在，清除記錄並要求重新選擇。
登出時一併清除記錄，避免不同帳號共用瀏覽器時沿用前一位使用者的專案。

## 需求範圍

### 儲存行為

- `current_project_id`、`current_project_name` 同時寫入 sessionStorage 與 localStorage。
- 保留既有 sessionStorage 寫入，不影響頁面間傳遞流程。

### 讀取優先順序

- `getProjectId()`：優先讀 sessionStorage，若無再讀 localStorage；
  localStorage 值 parseInt 後需為正整數，否則視為無值，回傳 null。
- `getProjectName()`：優先讀 sessionStorage，若無再讀 localStorage；
  無值時回傳「未選擇專案」。

### 寫入與清除

- `setProject(id, name)`：同時寫入 sessionStorage 與 localStorage。
- 新增 `clearProject()`：同時移除兩處的 `current_project_id` 與 `current_project_name`。
- `logout()` 在導向 /login.html 前呼叫 `clearProject()`。

### 專案存在性驗證

- 功能頁（index、import、match、selection、export-check、export、holdings）
  在讀取專案 id 後，沿用既有 `/api/projects/{id}` 呼叫；若該 API 失敗，
  呼叫 `clearProject()`，顯示「請先選擇採購專案」，並停止後續載入。
- 不強制導向，避免流程變複雜。

## 不做的事

- 不做雲端同步、不做跨瀏覽器同步。
- 不新增 server-side last_project_id 或帳號 preference。
- 不新增資料庫欄位、不新增 migration。
- 不重構整個前端狀態管理。
- 不修改採購專案資料模型。

## 驗收條件

1. 選擇專案後，localStorage 內有 `current_project_id`、`current_project_name`。
2. 重新整理頁面後，仍保留目前專案。
3. 關閉再重新開啟瀏覽器後，仍可帶入上次專案。
4. 若 localStorage 的 project_id 對應的專案存在，各功能頁正常顯示目前專案。
5. 若 localStorage 的 project_id 已不存在（API 失敗），系統清除兩處記錄
   並提示「請先選擇採購專案」，停止後續載入。
6. 切換或清除專案後，localStorage 與 sessionStorage 狀態一致。
7. 既有匯入、比對、選書、匯出流程不受影響。
8. 登出後，sessionStorage 與 localStorage 的 `current_project_id` /
   `current_project_name` 均被清除。
