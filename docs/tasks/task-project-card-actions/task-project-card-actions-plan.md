# Plan：task-project-card-actions

- task-id: task-project-card-actions
- type: feat
- base branch: main
- status: planning

---

## 可能影響的檔案

| 檔案 | 變動類型 |
|------|---------|
| `app/static/projects.html` | 修改（卡片 onclick、按鈕傳 event、confirmDelete 邏輯、delete modal 新增警告 div） |
| `app/static/css/style.css` | 修改（`.project-card` 加 hover state） |
| `app/routers/projects.py` | **不修改**（後端已支援刪除任何專案） |
| `tests/` | **不新增測試**（純前端 JS / CSS 變更，無新 API） |

---

## 前端事件設計

### 卡片 onclick：`selectCard(id, name)`

```
.project-card[onclick="selectCard(id, name)"]
  └─ div（內容區）
  └─ div.project-actions
       ├─ button[onclick="selectProject(event, id, name)"]  ← stopPropagation
       ├─ button[onclick="openEdit(event, id, name, ...)"]  ← stopPropagation
       └─ button[onclick="confirmDelete(event, id, name)"]  ← stopPropagation
```

card onclick（`selectCard`）：直接 `setProject` + 導頁，不呼叫 `stopPropagation`。

button onclick：傳入 `event`，函式第一行 `event.stopPropagation()` 截斷冒泡。

### 為何用卡片整體 onclick 而非只包左側內容

整張卡片作為點擊目標（Click Target）提供更大的可點擊面積，符合現代 UX 慣例。按鈕區（`.project-actions`）以 `stopPropagation` 攔截，不影響按鈕本身功能。

---

## CSS hover/active 樣式策略

### 需求一實作狀態（已完成）

Step 1 已加入 `cursor: pointer`、`transition: box-shadow 0.15s`、基礎 hover shadow：

```css
.project-card { /* ... */ cursor: pointer; transition: box-shadow 0.15s; }
.project-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.12); }
```

### 需求四強化（Step 5 待實作）

在既有 CSS 基礎上疊加，完整覆蓋後的目標狀態：

```css
/* 更新既有 .project-card：加上 position + border + 擴充 transition */
.project-card {
  background: #fff; border-radius: 12px; padding: 20px 24px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.07);
  display: flex; align-items: center; gap: 16px; margin-bottom: 12px;
  cursor: pointer;
  position: relative;
  border: 1px solid rgba(0,0,0,0.04);
  transition: box-shadow 0.15s, transform 0.15s, border-color 0.15s;
}

/* 新增：左側導引線偽元素 */
.project-card::before {
  content: '';
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3px;
  border-radius: 12px 0 0 12px;
  background: transparent;
  transition: background 0.15s;
}

/* 更新：hover 狀態（加 transform + border-color；原 box-shadow 提升） */
.project-card:hover {
  box-shadow: 0 8px 24px rgba(0,0,0,0.14);
  transform: translateY(-1px);
  border-color: rgba(0,113,227,0.22);
}
.project-card:hover::before {
  background: #0071e3;
}

/* 新增：current 卡片持續狀態 */
.project-card.current {
  border-color: rgba(0,113,227,0.22);
}
.project-card.current::before {
  background: #0071e3;
}
```

### 不做

- 不加大面積藍色背景（hover 只用導引線 + 陰影 + 淡 border）
- 不加 background 顏色變化

---

## Delete modal 調整策略

### 現有 delete-modal 結構

```
h2「確認刪除專案」
p 專案名稱
div#delete-stats（統計列表）
p（紅色不可復原警告）
div（按鈕組）
```

### 調整後（新增 #delete-current-warning）

```
h2「確認刪除專案」
p 專案名稱
div#delete-stats（統計列表）
div#delete-current-warning（★ 新增，預設 display:none）
p（紅色不可復原警告）
div（按鈕組）
```

### `#delete-current-warning` 的 HTML

```html
<div id="delete-current-warning" class="alert alert-warn" style="display:none">
  ⚠ 這是目前使用中的專案。刪除後系統會清除目前使用狀態，請重新選擇專案。
</div>
```

使用既有 `.alert.alert-warn`（`background: #fef9e7; color: #7d6608`），橙黃色與紅色不可復原警告形成視覺層次。

### JS 切換警告顯示

在 `confirmDelete` 中，取得 preview 後：

```javascript
const isCurrent = (getProjectId() == id);
document.getElementById('delete-current-warning').style.display = isCurrent ? 'block' : 'none';
```

---

## 後端調整

**不需要修改後端。**

確認依據：`DELETE /api/projects/{project_id}` 只做 404 check，無 current project 限制。後端不追蹤 current project（session 無此資訊），由前端判斷。

---

## 實作步驟

### ✓ Step 1：CSS — `.project-card` 加 hover 提示（已完成）

**檔案**：`app/static/css/style.css`

找到現有 `.project-card` rule（第 232–239 行），在既有屬性末尾加上 `cursor: pointer;` 與 `transition: box-shadow 0.15s;`；新增獨立的 `.project-card:hover` rule：

```css
.project-card {
  background: #fff; border-radius: 12px; padding: 20px 24px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.07);
  display: flex; align-items: center; gap: 16px; margin-bottom: 12px;
  cursor: pointer;
  transition: box-shadow 0.15s;
}
.project-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.12); }
```

### ✓ Step 2：HTML — delete modal 新增警告 div（已完成）

**檔案**：`app/static/projects.html`

在 `div#delete-stats` 之後、`p`（紅色警告）之前，插入：

```html
<div id="delete-current-warning" class="alert alert-warn" style="display:none">
  ⚠ 這是目前使用中的專案。刪除後系統會清除目前使用狀態，請重新選擇專案。
</div>
```

### ✓ Step 3：HTML — 卡片加 onclick，按鈕傳 event（已完成）

**檔案**：`app/static/projects.html`（`loadProjects` 中的 card template）

**前（現有）**：

```html
<div class="project-card">
  <div>
    ...
  </div>
  <div class="project-actions">
    <button class="btn btn-primary btn-sm" onclick="selectProject(${p.id},'${escaped}')">選擇</button>
    <button class="btn btn-secondary btn-sm" onclick="openEdit(${p.id},'${escaped}',${p.budget_amount},'${p.price_field}','${p.subtotal_mode}')">設定</button>
    <button class="btn btn-danger-outline btn-sm" onclick="confirmDelete(${p.id},'${escaped}')">刪除</button>
  </div>
</div>
```

**後（修改）**：

```html
<div class="project-card" onclick="selectCard(${p.id},'${escaped}')">
  <div>
    ...（內容不變）
  </div>
  <div class="project-actions">
    <button class="btn btn-primary btn-sm" onclick="selectProject(event,${p.id},'${escaped}')">選擇</button>
    <button class="btn btn-secondary btn-sm" onclick="openEdit(event,${p.id},'${escaped}',${p.budget_amount},'${p.price_field}','${p.subtotal_mode}')">設定</button>
    <button class="btn btn-danger-outline btn-sm" onclick="confirmDelete(event,${p.id},'${escaped}')">刪除</button>
  </div>
</div>
```

注意 name escape：現有程式碼已有 `p.name.replace(/'/g,"\\'")` 處理引號，保持不變。

### ✓ Step 4：JS — 新增 `selectCard`，更新三個函式（已完成）

**檔案**：`app/static/projects.html`（`<script>` 區塊）

#### 新增 `enterProject`（共用 helper）

卡片點擊與「選擇」按鈕行為統一，共用此 helper：

```javascript
function enterProject(id, name) {
  setProject(id, name);
  window.location.href = '/import.html';
}
```

#### 新增 `selectCard`（呼叫 helper）

```javascript
function selectCard(id, name) {
  enterProject(id, name);
}
```

#### 更新 `selectProject`（加 event 參數 + stopPropagation + 呼叫 helper）

```javascript
function selectProject(event, id, name) {
  event.stopPropagation();
  enterProject(id, name);
}
```

（改動：加 `event` 參數、`stopPropagation()`、原有 toast + delay 移除，改為與卡片點擊行為一致）

#### 更新 `openEdit`（加 event 參數 + stopPropagation）

```javascript
function openEdit(event, id, name, budget, pf, sm) {
  event.stopPropagation();
  document.getElementById('edit-id').value = id;
  // ...其餘邏輯不變
}
```

#### 更新 `confirmDelete`（加 event + stopPropagation + 移除 early return + 加警告）

```javascript
async function confirmDelete(event, id, name) {
  event.stopPropagation();
  // 移除舊有 early return：
  // ~~const cur = getProjectId(); if (cur == id) { showToast(...); return; }~~
  let preview;
  try {
    preview = await api(`/api/projects/${id}/delete-preview`);
  } catch (e) {
    showToast('無法取得刪除預覽：' + e.message);
    return;
  }
  document.getElementById('delete-project-name').textContent = preview.project_name;
  document.getElementById('delete-stats').innerHTML = `
    <ul style="margin:8px 0;padding-left:20px;color:#555;font-size:14px">
      <li>選書項目：${preview.selection_count} 筆</li>
      <li>匯出記錄：${preview.export_job_count} 筆</li>
      <li>匯入批次：${preview.import_batch_count} 批</li>
      <li>書商書目：${preview.vendor_book_count} 筆</li>
      <li>館藏紀錄：${preview.holding_count} 筆</li>
    </ul>`;
  // 新增：current project 警告切換
  const isCurrent = (getProjectId() == id);
  document.getElementById('delete-current-warning').style.display = isCurrent ? 'block' : 'none';
  document.getElementById('delete-confirm-btn').onclick = () => doDelete(id);
  document.getElementById('delete-modal').style.display = 'flex';
}
```

`doDelete`：**不修改**（現有邏輯已包含 `if (getProjectId() == id) clearProject()`）。

### Step 5：CSS — 視覺回饋強化（需求四）

**檔案**：`app/static/css/style.css`

找到已修改的 `.project-card` rule，進行以下更新（完整替換該 rule 及其 hover rule）：

1. 在 `.project-card` 加入 `position: relative; border: 1px solid rgba(0,0,0,0.04);`，並將 `transition` 從 `box-shadow 0.15s` 改為 `box-shadow 0.15s, transform 0.15s, border-color 0.15s`。

2. 新增 `.project-card::before`（左側導引線）：

```css
.project-card::before {
  content: '';
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3px;
  border-radius: 12px 0 0 12px;
  background: transparent;
  transition: background 0.15s;
}
```

3. 更新 `.project-card:hover`（加 transform + border-color，提升 box-shadow）：

```css
.project-card:hover {
  box-shadow: 0 8px 24px rgba(0,0,0,0.14);
  transform: translateY(-1px);
  border-color: rgba(0,113,227,0.22);
}
```

4. 新增 `.project-card:hover::before`、`.project-card.current`、`.project-card.current::before`：

```css
.project-card:hover::before { background: #0071e3; }
.project-card.current { border-color: rgba(0,113,227,0.22); }
.project-card.current::before { background: #0071e3; }
```

### Step 6：HTML — card template 加 `.current` class

**檔案**：`app/static/projects.html`（`loadProjects` 中的 card template）

`loadProjects` 開頭已有 `const cur = getProjectId();`。在 card div class 加入條件：

```html
<!-- 前 -->
<div class="project-card" onclick="selectCard(...)">

<!-- 後 -->
<div class="project-card${cur == p.id ? ' current' : ''}" onclick="selectCard(...)">
```

不改 badge 顯示邏輯（`${cur == p.id ? '<span class="badge badge-available">目前使用</span>' : ''}` 保持不變）。

---

## 手動驗證方式

```
1. 啟動服務：.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000
2. 瀏覽器開啟 http://127.0.0.1:8000/projects.html，確認已有至少一個專案。
```

| 驗證項目 | 步驟 | 預期結果 |
|---------|------|---------|
| 卡片 hover（非 current） | 滑鼠移至卡片文字區 | 左側藍色導引線出現、卡片浮起、陰影加深、淡藍 border |
| 卡片 hover（current） | 滑鼠移至 current 卡片 | 在既有導引線基礎上疊加 hover 效果 |
| current 卡片靜止狀態 | 不 hover，觀察 current 專案卡片 | 左側藍色導引線永久可見，淡藍 border |
| 「目前使用」badge | current 卡片 | badge 保留，與導引線並存 |
| 卡片點擊（非 current） | 點擊卡片左側文字區 | 導向 /import.html，current project 已設定 |
| 卡片點擊（current project） | 點擊有「目前使用」badge 的卡片 | 同上，重設 current project 後導頁 |
| 「選擇」按鈕 | 點擊「選擇」按鈕 | 直接導向 /import.html（同卡片點擊行為），不觸發卡片 onclick |
| 「設定」按鈕 | 點擊「設定」按鈕 | edit modal 開啟，URL 不跳轉 |
| 「刪除」按鈕（非 current） | 點擊「刪除」 | delete modal 開啟，無橙黃警告，URL 不跳轉 |
| 「刪除」按鈕（current project） | 點擊「刪除」 | delete modal 開啟，顯示橙黃警告文字 |
| 確認刪除 current project | 點「確認刪除」 | 刪除成功，列表重載，toast，不自動跳頁 |
| 確認刪除後 current project 已清除 | 刪除後回到 projects.html，確認 stepper nav 等頁面不顯示舊專案名 | clearProject() 已執行 |
| 取消刪除 | 點「取消」 | modal 關閉，current project 不變 |
| 刪除唯一專案後 | 刪除列表中僅有的專案 | 顯示 empty state「尚無採購專案」 |
| 背景圖存在時 | 在有背景圖的頁面觀察 hover | 卡片效果清楚可見，白卡片不受背景干擾 |

---

## Lint / Format / Typecheck / Test / Build 檢查

| 類型 | 指令 | 說明 |
|------|------|------|
| Python lint | 不適用（無 ruff/flake8 設定） | 本 task 無 Python 變更 |
| Python typecheck | 不適用（無 mypy 設定） | 本 task 無 Python 變更 |
| Python test（既有） | `.venv\Scripts\pytest.exe tests/ -v` | 確認 58 tests 仍通過（無新測試） |
| JS lint | 不適用（無 ESLint 設定） | 手動確認語法正確性 |
| Build | 不適用（FastAPI StaticFiles serve） | 啟動 uvicorn 後手動驗證 |
| 服務啟動 | `.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000` | 手動驗證所有場景 |
