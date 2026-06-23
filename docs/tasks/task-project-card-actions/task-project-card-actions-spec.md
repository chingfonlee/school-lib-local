# Spec：task-project-card-actions

- task-id: task-project-card-actions
- type: feat
- base branch: main
- status: planning

---

## 背景與問題

目前「採購專案」頁面（`projects.html`）的操作體驗存在兩個問題：

1. **卡片不可點擊**：使用者必須找到並點擊「選擇」按鈕才能進入專案，卡片本身沒有點擊反應，對熟悉現代 Web UI 的使用者來說不夠直覺。

2. **刪除目前使用中專案的限制過嚴**：`task-project-delete-backup-restore` 的 MVP 策略是完全阻擋刪除 current project（toast 提示「請先選擇其他專案後再刪除此專案」）。但在只有一個專案的情境下，使用者無法刪除任何專案，體驗不佳。正確做法是允許刪除，但提供更明確的警告。

---

## 使用者目標

1. 直覺點擊專案卡片主要區域即可選擇專案並進入下一步（匯入頁）。
2. 仍可透過「選擇」按鈕選擇專案（行為不變，但導向頁面與卡片點擊一致）。
3. 可刪除目前使用中的專案，且在確認前看到明確的額外警告。

---

## 現況分析（技術前提）

### 前端 current project 管理

`common.js` 中的三個函式管理 current project 狀態：

- `getProjectId()`：依序讀 sessionStorage / localStorage 的 `current_project_id`
- `setProject(id, name)`：同時寫 sessionStorage 與 localStorage
- `clearProject()`：清除 sessionStorage 與 localStorage

後端不追蹤 current project，無法在 API 層區分「目前使用中的專案」。

### 後端 DELETE API 現況

`DELETE /api/projects/{project_id}`（`app/routers/projects.py`）：

- 只確認專案存在（404 if not found）
- **無** current project 限制
- 刪除任何存在的專案均成功
- **不需要修改後端**

### 現有前端刪除防呆（需移除）

`confirmDelete` 函式目前有：

```javascript
const cur = getProjectId();
if (cur == id) {
  showToast('請先選擇其他專案後再刪除此專案');
  return;  // ← 本任務要移除此早期 return
}
```

本任務改為：不 early return，改在 delete modal 內顯示額外警告。

### 現有 `selectProject` 導向頁面

目前導向 `/index.html`，本任務改為 `/import.html`（stepper 第 2 步）。

### 現有按鈕 onclick 無 event 參數

現有按鈕使用 inline onclick 但不傳 event：

```html
onclick="confirmDelete(${p.id},'${p.name}')"
```

本任務改為顯式傳入 event，以便在函式內呼叫 `event.stopPropagation()`。

### 現有 `.project-card` CSS

```css
.project-card {
  background: #fff; border-radius: 12px; padding: 20px 24px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.07);
  display: flex; align-items: center; gap: 16px; margin-bottom: 12px;
}
```

目前無 hover state、無 `cursor: pointer`。

---

## 需求一：卡片可點擊

### 點擊行為

- 點擊 `.project-card` 主體（整張卡片）應視為「選擇此專案」。
- 觸發：呼叫 `setProject(id, name)` 後立即導向 `/import.html`。
- 無 toast 延遲（直接導頁）。

### 目前使用中的卡片

- 目前使用中的卡片（有「目前使用」badge）同樣可點擊。
- 點擊後呼叫 `setProject(id, name)`（效果等同重設）再導向 `/import.html`。
- badge 顯示保留。

### 「選擇」按鈕行為

- 保留「選擇」按鈕。
- 行為：呼叫 `setProject(id, name)` → 顯示 toast → 導向 `/import.html`（改自原 `/index.html`）。
- 點擊按鈕**不得觸發**卡片的 onclick（需 `stopPropagation`）。

### 視覺提示

- 卡片整體加上 `cursor: pointer`。
- hover 時略微提高陰影（`box-shadow: 0 4px 12px rgba(0,0,0,0.12)`），延續白卡片風格，不使用邊框或顏色變化。
- 過渡動畫：`transition: box-shadow 0.15s`（已在 `.project-card` 外其他元素有使用相同模式）。

---

## 需求二：按鈕事件不得誤觸卡片

### 需要防止冒泡的按鈕

| 按鈕 | 現有 handler | 防止冒泡策略 |
|------|-------------|-------------|
| 選擇 | `selectProject(id, name)` | 改為 `selectProject(event, id, name)`，函式內 `event.stopPropagation()` |
| 設定 | `openEdit(id, name, ...)` | 改為 `openEdit(event, id, name, ...)`，函式內 `event.stopPropagation()` |
| 刪除 | `confirmDelete(id, name)` | 改為 `confirmDelete(event, id, name)`，函式內 `event.stopPropagation()` |

### inline onclick 改法

```html
<!-- 前 -->
onclick="selectProject(${p.id},'${escapedName}')"

<!-- 後 -->
onclick="selectProject(event,${p.id},'${escapedName}')"
```

在 inline 屬性中，`event` 為瀏覽器自動提供的 event 物件，無需另外宣告。

---

## 需求三：刪除目前使用中的專案

### 觸發條件判斷

在 `confirmDelete` 中，取得 delete-preview 後，比較 `getProjectId() == id`：

- 若為 current project：在 modal 內顯示額外警告文字。
- 若非 current project：不顯示額外警告（保持現有 modal 外觀）。

### 額外警告文字

位置：在 delete-stats 統計列表之後、紅色不可復原警告之前。

樣式：使用既有 `.alert.alert-warn`（橙黃色，`background: #fef9e7; color: #7d6608`），以顏色區分危險等級（不同於紅色不可復原警告）。

文字：「⚠ 這是目前使用中的專案。刪除後系統會清除目前使用狀態，請重新選擇專案。」

ID：`delete-current-warning`，預設 `display:none`，由 JS 切換顯示。

### 刪除成功後

`doDelete` 現有邏輯已包含：

```javascript
if (getProjectId() == id) clearProject();
```

此邏輯保留，**不需要修改 `doDelete`**。

### 空列表 empty state

刪除後若列表為空，`loadProjects` 的現有 empty state 邏輯會顯示：

```html
<div class="empty"><div class="icon">📋</div><p>尚無採購專案</p></div>
```

此行為保留，不需修改。

### 不自動切換

刪除 current project 後，只呼叫 `clearProject()`，不自動導向其他頁面或自動選擇其他專案。使用者需手動選擇。

---

## UI/UX 驗收條件

| 場景 | 預期結果 |
|------|---------|
| 點擊卡片主要區域（任意專案） | `setProject` + 導向 `/import.html` |
| 點擊目前使用中的專案卡片 | 同上 |
| 點擊「選擇」按鈕 | `setProject` + toast + 導向 `/import.html`（無頁面空白跳轉） |
| 點擊「設定」按鈕 | edit modal 開啟，不觸發導頁 |
| 點擊「刪除」按鈕 | delete confirm modal 開啟，不觸發導頁 |
| 刪除非目前使用中專案 | 正常 modal，無額外警告 |
| 刪除目前使用中專案 | modal 內顯示橙黃色額外警告文字 |
| 確認刪除目前使用中專案 | 刪除成功，`clearProject()` 執行，列表重新載入，不跳頁 |
| 取消刪除 | current project 不變 |
| 卡片 hover | box-shadow 加深，cursor 為 pointer |
| 按鈕 hover | 原有 opacity 效果不受影響 |

---

## 非目標

- 不做專案排序或拖曳。
- 不改備份 / 還原 API。
- 不改資料庫 schema，不新增 migration。
- 不做軟刪除或垃圾桶。
- 不做刪除後自動切換到其他專案。
- 不改 stepper nav 結構。
- 不改匯入、比對、選書、匯出流程。
- 不改其他頁面（`import.html`、`selection.html` 等）。
- 不移除「選擇」按鈕文字。

---

## 風險與限制

| 風險 | 說明 | 處理方式 |
|------|------|---------|
| 後端無法識別 current project | API 層無法阻擋刪除 current project | 前端判斷並提示，屬已知設計限制 |
| inline onclick 中 `event` 的可用性 | 在現代瀏覽器 inline 屬性中 `event` 由瀏覽器注入，相容性良好 | 可用，無需 polyfill |
| 卡片整體 cursor:pointer 與按鈕混淆 | 使用者可能不確定哪部分可點 | stopPropagation 確保按鈕行為獨立；hover shadow 給整張卡片提示，體驗一致 |
| 刪除唯一專案後空列表 | 使用者需重新建立專案才能繼續流程 | 顯示現有 empty state，行為合理 |
| `selectProject` 導向改為 `/import.html` | 改變現有按鈕導向（原 `/index.html`） | 確認 `index.html` 在此系統的角色；依 stepper 結構，`import.html` 是正確的下一步 |
