# Spec：task-project-budget-summary

- task-id: task-project-budget-summary
- type: feat
- base branch: main
- status: planning

---

## 背景與問題

採購流程進入「匯出前置檢查」時，使用者目前無法得知：

1. 本次採購書目的總金額是否超出核定預算。
2. 採購專案設定的預算金額是多少。

雖然資料庫已有 `procurement_projects.budget_amount REAL` 欄位，後端 API 也已支援讀寫，但前端 `projects.html` 尚未顯示也未提供輸入介面，`export-check.html` 也未提供金額摘要。

---

## 用詞定義

| 情境 | 用詞 |
|------|------|
| 採購專案管理（projects.html）| 「專案預算」 |
| 匯出前置檢查（export-check.html）| 「專案預算」 |
| 匯出 Excel（export.html）| 「核定金額」（維持現有用詞） |
| 資料庫欄位 | `budget_amount`（現有，不改） |
| 匯出 API 參數 | `approved_budget`（現有，不改） |

---

## 使用者目標

1. 建立採購專案時可設定預算（或留空表示「未設定」）。
2. 編輯採購專案時可修改或清除預算。
3. 採購專案清單卡片可看到各專案預算。
4. 在「匯出前置檢查」頁面確認目前選書金額是否超出預算，再決定是否繼續匯出。

---

## 功能需求

### 1. 採購專案預算欄位（projects.html）

#### 1.1 新增專案表單

- 新增「專案預算（元）」輸入欄位（`type="number"`, `min="0"`，非必填）。
- 空白表示未設定（送出時傳 `null`）。
- 輸入負數時，前端驗證阻止送出，提示「預算不可為負數」。
- 送出時帶入 `budget_amount`（數值或 null）到 POST `/api/projects/`。

#### 1.2 專案卡片顯示

- 卡片 `.project-meta` 增加一行：`預算：NT$ 45,000 元` 或 `預算：未設定`。
- 格式：千分位整數，加上「元」後綴；未設定時顯示灰色「未設定」。

#### 1.3 編輯專案 Modal（設定）

- Modal 中新增「專案預算（元）」輸入欄位（`type="number"`, `min="0"`，非必填）。
- 開啟 Modal 時，用目前 `budget_amount`（可能為 null）預填欄位。
- 儲存時：
  - 欄位有效數值 → 送出 `budget_amount: <number>`。
  - 欄位清空 → 送出 `budget_amount: null`（清除預算）。
  - 負數 → 前端阻止送出，提示錯誤。
- PUT `/api/projects/{id}` 必須正確處理 `budget_amount: null`（清空為「未設定」）。

### 2. 匯出前置檢查頁金額摘要（export-check.html）

在現有統計卡片列（`.stats-row`）與書目明細表格之間，新增「預算摘要」卡片 `.card`。

#### 2.1 顯示項目

| 項目 | 說明 |
|------|------|
| 專案預算 | `proj.budget_amount`，未設定顯示「未設定」 |
| 定價總額 | `Σ(quantity × list_price_eff)` |
| 採購單價總額 | `Σ(quantity × purchase_price_eff)` |
| 應付金額 | 依 `subtotal_mode` 選擇使用定價或採購單價總額 |
| 與預算差額 | `應付金額 - 專案預算`（正數=超支，負數=剩餘） |

`list_price_eff` / `purchase_price_eff`：優先用 `user_overrides[field]`，其次用 `b[field]`，其次 0（與 `export_service._get_price` 邏輯一致）。

#### 2.2 顯示規則

- 所有金額使用千分位格式（`toLocaleString('zh-TW')`），加「元」後綴。
- 當 `proj.budget_amount` 未設定時：
  - 顯示「未設定」取代金額。
  - 不顯示差額列。
  - 不顯示超支警示。
  - 不阻擋「繼續匯出」按鈕。
- 當 `proj.budget_amount` 已設定且差額 > 0（超支）：
  - 差額顯示紅色（`color: #c0392b` 或 `.alert.alert-warn` 樣式）。
  - 文字顯示「超支 NT$ X 元」。
- 當差額 ≤ 0（未超支）：
  - 差額顯示綠色或正常文字。
  - 文字顯示「剩餘 NT$ X 元」。

#### 2.3 更新時機

- `runCheck()` 完成後重新計算並渲染摘要（因 `price-field` / `subtotal-mode` 下拉可能變更，每次 runCheck 後都重算）。
- `proj` 物件在頁面初始化時載入一次。

### 3. 匯出頁 export.html（可選）

- 頁面初始化時，若 `proj.budget_amount` 不為 null，自動填入「核定金額」欄位（`document.getElementById('budget').value = proj.budget_amount`）。
- 使用者仍可手動修改。
- 此項為 nice-to-have，不影響核心驗收。

---

## 資料模型需求

### 現有欄位（確認）

```sql
-- migration 001（已存在，不需新增 migration）
CREATE TABLE IF NOT EXISTS procurement_projects (
    ...
    budget_amount REAL,   -- 已存在，允許 NULL
    ...
);
```

**無需新增 migration。**

### 後端 API 變更

#### ProjectCreate（projects.py）

現有：`budget_amount: float | None = None` ✅

補充：加入 Pydantic validator，限制 `budget_amount >= 0`：

```python
from pydantic import field_validator

class ProjectCreate(BaseModel):
    ...
    @field_validator('budget_amount')
    @classmethod
    def budget_non_negative(cls, v):
        if v is not None and v < 0:
            raise ValueError('budget_amount 不可為負數')
        return v
```

#### ProjectUpdate（projects.py）

現有：`budget_amount: float | None = None`，PUT handler 使用 `if body.budget_amount is not None:` ⚠️

問題：無法將 budget_amount 清空為 null。

修正：使用 `body.model_fields_set` 判斷是否明確提供 budget_amount：

```python
if "budget_amount" in body.model_fields_set:
    updates["budget_amount"] = body.budget_amount
```

同時為 `ProjectUpdate` 加入 validator（與 `ProjectCreate` 相同邏輯）。

---

## API / 前端影響

| 端點 | 變更類型 |
|------|---------|
| `GET /api/projects/` | 不變（已回傳 `budget_amount`） |
| `GET /api/projects/{id}` | 不變（已回傳 `budget_amount`） |
| `POST /api/projects/` | 加入 validator（非負數驗證） |
| `PUT /api/projects/{id}` | 修正 null 處理邏輯 |
| `GET /api/exports/check` | 不變（金額由前端計算） |
| `GET /api/selections/` | 不變（已回傳 price 欄位） |

---

## 非目標

- 不處理多年度預算。
- 不處理多經費來源。
- 不新增複雜審核流程。
- 不強制使用者設定預算（允許留空）。
- 不改變選書或匯出主流程。
- 不修改匯出 Excel 中 `approved_budget_cell` 的填入邏輯（已由 `export.html` 的「核定金額」欄位控制，與本任務 `budget_amount` 無直接耦合）。
- 不處理 stepper nav 樣式。
- 不新增後端 API 端點（金額加總由前端計算）。

---

## 驗收條件

1. 新增專案時可輸入預算（含空值）。
2. 新增專案時輸入負數，前端顯示錯誤並阻止送出。
3. 編輯專案時可修改預算。
4. 編輯專案時清空預算欄位並儲存，DB 欄位變為 null。
5. 後端 PUT 收到 `budget_amount: null` 時，實際將欄位清空（不保留舊值）。
6. 後端 PUT 收到 `budget_amount: -1` 時，回傳 422 錯誤。
7. 專案卡片顯示預算（千分位）或「未設定」。
8. `export-check.html` 顯示：
   - 專案預算（或「未設定」）
   - 定價總額
   - 採購單價總額
   - 應付金額（依 subtotal_mode）
   - 差額（超支/剩餘），有明顯警示色
9. 預算未設定時，`export-check.html` 不顯示差額列，不阻擋繼續匯出。
10. `price-field` 或 `subtotal-mode` 下拉更改時，`export-check.html` 金額摘要即時更新。
11. 既有採購專案資料不因本任務遺失。

---

## 風險與限制

| 風險 | 說明 | 處理方式 |
|------|------|---------|
| `update_project` null bug | 現有 handler 無法清空 budget_amount | 修正為 `model_fields_set` |
| 前端金額計算與後端不完全一致 | user_overrides 解析邏輯需與 `export_service._get_price` 保持一致 | plan 明確指定解析順序 |
| `general_books` 專案的 budget_amount | 現有 export.html 對 general_books 隱藏「核定金額」欄位，但可透過 projects.html 設定預算 | spec 明確：budget_amount 顯示在 export-check.html，export.html 的行為不變（general_books 隱藏核定金額） |
| 既有資料 budget_amount 為 null | 頁面需正確處理 null 顯示 | spec 已明確要求「未設定」文字處理 |
