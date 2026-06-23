# Plan：task-project-budget-summary

- task-id: task-project-budget-summary
- type: feat
- base branch: main
- status: planning

---

## 實作步驟

### Step 1：後端 `app/routers/projects.py`

**1-A：新增 Pydantic validator（非負數驗證）**

為 `ProjectCreate` 和 `ProjectUpdate` 加入 validator：

```python
from pydantic import BaseModel, field_validator

class ProjectCreate(BaseModel):
    name: str
    project_type: str = "local_culture"
    budget_amount: float | None = None
    price_field: str = "purchase_price"
    subtotal_mode: str = "quantity_times_purchase_price"

    @field_validator('budget_amount')
    @classmethod
    def budget_non_negative(cls, v):
        if v is not None and v < 0:
            raise ValueError('budget_amount 不可為負數')
        return v


class ProjectUpdate(BaseModel):
    name: str | None = None
    budget_amount: float | None = None
    price_field: str | None = None
    subtotal_mode: str | None = None

    @field_validator('budget_amount')
    @classmethod
    def budget_non_negative(cls, v):
        if v is not None and v < 0:
            raise ValueError('budget_amount 不可為負數')
        return v
```

**1-B：修正 `update_project` null 支援**

將：

```python
if body.budget_amount is not None:
    updates["budget_amount"] = body.budget_amount
```

改為：

```python
if "budget_amount" in body.model_fields_set:
    updates["budget_amount"] = body.budget_amount
```

---

### Step 2：前端 `app/static/projects.html`

**2-A：新增專案表單加入預算欄位**

在 `new-form` 的 `form-row` 中加入第二個 `form-row`（插在「採購類型」那列之後）：

```html
<div class="form-row">
  <div class="form-group">
    <label>專案預算（元）<span style="color:#888;font-size:12px;font-weight:400">（選填）</span></label>
    <input type="number" id="new-budget" placeholder="例：45000" min="0">
  </div>
</div>
```

**2-B：`createProject()` 加入 budget 驗證和送出**

```js
async function createProject() {
  const name = document.getElementById('new-name').value.trim();
  if (!name) return showToast('請填入專案名稱');
  const budgetRaw = document.getElementById('new-budget').value;
  const budget = budgetRaw === '' ? null : parseFloat(budgetRaw);
  if (budget !== null && budget < 0) return showToast('預算不可為負數');
  await api('/api/projects/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name,
      project_type: document.getElementById('new-type').value,
      budget_amount: budget,
      price_field: document.getElementById('new-price-field').value,
      subtotal_mode: document.getElementById('new-subtotal').value,
    })
  });
  ...
}
```

**2-C：專案卡片顯示預算**

在 `loadProjects()` 的模板中，`.project-meta` 第二行加入預算資訊：

```js
const budgetText = p.budget_amount != null
  ? `NT$ ${p.budget_amount.toLocaleString('zh-TW')} 元`
  : '<span style="color:#999">未設定</span>';
```

加入卡片 HTML：

```html
<div class="project-meta" style="margin-top:4px;font-size:12px;color:#666">
  專案預算：${budgetText}
</div>
```

**2-D：編輯 Modal 加入預算欄位**

在 Modal 中加入預算欄位（放在專案名稱欄位下方）：

```html
<div class="form-group">
  <label>專案預算（元）<span style="color:#888;font-size:12px;font-weight:400">（選填）</span></label>
  <input type="number" id="edit-budget" min="0">
</div>
```

**2-E：`openEdit()` 預填 budget**

```js
function openEdit(id, name, budget, pf, sm) {
  document.getElementById('edit-id').value = id;
  document.getElementById('edit-name').value = name;
  document.getElementById('edit-budget').value = budget != null ? budget : '';
  document.getElementById('edit-price-field').value = pf;
  document.getElementById('edit-subtotal').value = sm;
  document.getElementById('edit-modal').style.display = 'flex';
}
```

**2-F：`saveEdit()` 送出 budget（含 null 清空）**

```js
async function saveEdit() {
  const id = document.getElementById('edit-id').value;
  const budgetRaw = document.getElementById('edit-budget').value;
  const budget = budgetRaw === '' ? null : parseFloat(budgetRaw);
  if (budget !== null && budget < 0) return showToast('預算不可為負數');
  await api(`/api/projects/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: document.getElementById('edit-name').value.trim(),
      budget_amount: budget,
      price_field: document.getElementById('edit-price-field').value,
      subtotal_mode: document.getElementById('edit-subtotal').value,
    })
  });
  ...
}
```

**2-G：openEdit 呼叫端傳入 budget**

```js
<button ... onclick="openEdit(${p.id},'${p.name.replace(...)}',${p.budget_amount},'${p.price_field}','${p.subtotal_mode}')">設定</button>
```

注意：`p.budget_amount` 為 null 時，JS template literal 會產生 `null`（字串），`openEdit` 判斷 `budget != null` 為 false，欄位留空，正確。

---

### Step 3：前端 `app/static/export-check.html`

**3-A：宣告頂層 `proj` 變數**

```js
let pid = null;
let proj = null;   // ← 新增
let lastCheck = null;
...
```

在初始化時儲存 `proj`：

```js
proj = await api(`/api/projects/${pid}`);
```

**3-B：`runCheck()` 呼叫後計算並渲染預算摘要**

在 `runCheck()` 函式末尾新增：

```js
renderBudgetSummary(selData.items);
```

**3-C：新增 `renderBudgetSummary()` 函式**

```js
function renderBudgetSummary(items) {
  const el = document.getElementById('budget-summary');
  if (!el) return;

  const pf = document.getElementById('price-field').value;
  const sm = document.getElementById('subtotal-mode').value;
  const budget = proj && proj.budget_amount != null ? proj.budget_amount : null;

  let totalListAmount = 0, totalPurchaseAmount = 0;
  items.forEach(b => {
    let ov = {};
    try { ov = JSON.parse(b.user_overrides || '{}'); } catch { ov = {}; }
    const lp = parseFloat(ov.list_price || b.list_price || 0) || 0;
    const pp = parseFloat(ov.purchase_price || b.purchase_price || 0) || 0;
    const qty = parseInt(b.selected_quantity || 0, 10);
    totalListAmount += lp * qty;
    totalPurchaseAmount += pp * qty;
  });

  const subtotalAmount = sm === 'quantity_times_list_price' ? totalListAmount : totalPurchaseAmount;
  const fmt = n => Math.round(n).toLocaleString('zh-TW');

  let diffHtml = '';
  if (budget !== null) {
    const diff = subtotalAmount - budget;
    if (diff > 0) {
      diffHtml = `<tr><td>與預算差額</td><td style="color:#c0392b;font-weight:600">超支 NT$ ${fmt(diff)} 元</td></tr>`;
    } else {
      diffHtml = `<tr><td>與預算差額</td><td style="color:#27ae60">剩餘 NT$ ${fmt(-diff)} 元</td></tr>`;
    }
  }

  el.innerHTML = `
    <table style="width:auto;border:none">
      <tr><td style="padding:4px 16px 4px 0;color:#666">專案預算</td>
          <td style="padding:4px 0">${budget !== null ? `NT$ ${fmt(budget)} 元` : '<span style="color:#999">未設定</span>'}</td></tr>
      <tr><td style="padding:4px 16px 4px 0;color:#666">定價總額</td>
          <td style="padding:4px 0">NT$ ${fmt(totalListAmount)} 元</td></tr>
      <tr><td style="padding:4px 16px 4px 0;color:#666">採購單價總額</td>
          <td style="padding:4px 0">NT$ ${fmt(totalPurchaseAmount)} 元</td></tr>
      <tr><td style="padding:4px 16px 4px 0;color:#666">應付金額（${sm === 'quantity_times_list_price' ? '依定價' : '依採購單價'}）</td>
          <td style="padding:4px 0;font-weight:600">NT$ ${fmt(subtotalAmount)} 元</td></tr>
      ${diffHtml}
    </table>`;
}
```

**3-D：HTML 加入 budget-summary 容器**

在 `.stats-row` 和 `#source-note` 之間插入：

```html
<div class="card" id="budget-summary-card" style="margin-bottom:8px">
  <h3 style="margin:0 0 8px 0;font-size:14px;font-weight:600;color:#1d1d1f">金額摘要</h3>
  <div id="budget-summary"></div>
</div>
```

---

### Step 4（可選）：`app/static/export.html` 自動填入核定金額

在初始化後加入：

```js
if (proj.budget_amount != null) {
  document.getElementById('budget').value = proj.budget_amount;
}
```

（僅在 `local_culture` 類型下生效，`general_books` 已隱藏 `budget-group`。）

---

## 可能影響的檔案

| 檔案 | 變更類型 |
|------|---------|
| `app/routers/projects.py` | 後端邏輯修正（validator + null 支援） |
| `app/static/projects.html` | 前端 UI（新增/編輯表單、卡片顯示） |
| `app/static/export-check.html` | 前端 UI（預算摘要區） |
| `app/static/export.html` | 前端 UI（可選：自動填入） |

**不需異動：**
- `migrations/*.sql`（`budget_amount` 已在 migration 001）
- `app/services/validation_service.py`
- `app/services/export_service.py`
- `app/database.py`
- `app/static/css/style.css`

> Step 4（可選）影響檔案應為 `app/static/export.html`（非 export-check.html，前述為筆誤）。

---

## Migration 策略

**不需新增 migration。**

`budget_amount REAL` 欄位已在 `migrations/001_initial_schema.sql` 中定義，允許 NULL，對既有資料無影響。

---

## 後端 API 調整策略

1. 加入 `field_validator` 驗證非負數（`budget_amount >= 0`），422 回傳清楚錯誤訊息。
2. 修正 `update_project` 使用 `body.model_fields_set` 判斷是否需要更新 `budget_amount`，支援清空為 null。
3. 不新增 API 端點；金額加總由前端計算。

---

## 前端 UI 調整策略

- `projects.html`：最小侵入式修改，在現有 form-row 結構內插入欄位，維持現有排版風格。
- `export-check.html`：新增一張 `.card` 卡片放置金額摘要 table，不破壞現有統計列與明細表格。
- 前端解析 `user_overrides` 時，邏輯與 `export_service._get_price` 保持一致：優先取 `user_overrides[field]`，其次取 `b[field]`，其次 0。

---

## 金額格式化與驗證策略

| 場景 | 方式 |
|------|------|
| 顯示金額 | `Math.round(n).toLocaleString('zh-TW')` + `元` |
| 前端輸入驗證 | `budget < 0` → showToast 阻止送出 |
| 後端輸入驗證 | Pydantic `field_validator`，`v < 0` → 422 |
| null 判斷 | `budget_amount != null`（排除 null 和 undefined，允許 0） |

---

## 測試與手動驗證方式

本專案無自動化測試指令（`pytest` 需有測試檔案），以下列出手動驗證清單。

### 後端 API 驗證（curl）

```bash
# 新增帶預算的專案
curl -s -X POST http://127.0.0.1:8000/api/projects/ \
  -H "Content-Type: application/json" \
  -d '{"name":"測試預算","budget_amount":45000}' \
  -b "session=<token>"

# 嘗試負數（應 422）
curl -s -X POST http://127.0.0.1:8000/api/projects/ \
  -H "Content-Type: application/json" \
  -d '{"name":"測試","budget_amount":-1}' \
  -b "session=<token>"

# 更新為 null（清空預算）
curl -s -X PUT http://127.0.0.1:8000/api/projects/1 \
  -H "Content-Type: application/json" \
  -d '{"budget_amount":null}' \
  -b "session=<token>"

# 確認 GET 回傳 budget_amount
curl -s http://127.0.0.1:8000/api/projects/1 -b "session=<token>"
```

### 前端手動驗證流程

1. `projects.html`：
   - 新增專案，填入預算 → 儲存 → 確認卡片顯示千分位金額。
   - 新增專案，預算留空 → 儲存 → 確認卡片顯示「未設定」。
   - 新增專案，填入負數 → 確認前端錯誤提示，未送出。
   - 開啟設定 Modal → 預算欄位預填 → 修改後儲存 → 確認卡片更新。
   - 設定 Modal 清空預算 → 儲存 → 確認卡片顯示「未設定」。

2. `export-check.html`：
   - 有預算專案：確認金額摘要顯示正確，超支時紅色警示。
   - 無預算專案：確認「未設定」，無差額列。
   - 切換 subtotal_mode → 確認應付金額即時更新。
   - 切換 price_field → 確認各金額即時更新。

3. `export.html`（若實作可選項）：確認核定金額欄位自動填入。

### 截圖驗證

建議截圖確認：
- `projects.html`：有預算/無預算兩種卡片樣式。
- `export-check.html`：超支警示（紅色）、未超支（綠色）、未設定三種狀態。

---

## Lint / Format / Typecheck / Test / Build 檢查

| 類型 | 指令 | 說明 |
|------|------|------|
| Python lint | 不適用（無 ruff/flake8 設定） | 手動確認縮排與語法 |
| Python typecheck | 不適用（無 mypy 設定） | 手動確認 Pydantic 用法 |
| Python test | `.venv\Scripts\pytest.exe tests/ -v` | 執行既有測試確認不迴歸；本任務未新增測試，以手動 curl 驗證補足 |
| JS lint | 不適用（無 ESLint 設定） | 手動確認 |
| Build | 不適用（靜態 HTML，FastAPI StaticFiles serve） | 啟動 uvicorn 後直接驗證 |
| 服務啟動 | `.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000` | 手動啟動後驗證 |
