# Spec：task-project-card-status-actions

- task-id: task-project-card-status-actions
- type: feat
- base branch: main
- status: planning

---

## 背景與問題

目前「採購專案」列表頁（`projects.html`）的每張卡片僅顯示有限資訊：
- 已選書本數（`selection_count`）
- 上次匯出時間（`last_export`）
- 定價欄 / 小計設定
- 專案預算金額

使用者無法在列表頁判斷：
1. 書商書目是否已匯入（及數量）
2. 館藏比對後有多少重複館藏
3. 已選書目的實際小計金額（需進入選書頁才能看到）
4. 預算使用進度（百分比）

此外，進入任何工作步驟都需先點卡片（導向匯入頁），再從 stepper 導航到目的頁。若使用者已知道要繼續選書或匯出，無法直接跳步。

---

## 使用者目標

1. 在專案列表頁直接看到每個專案的工作進度摘要（匯入、比對、選書、預算、匯出）。
2. 透過快速操作按鈕，一鍵選定專案並跳轉至指定的工作步驟（匯入、選書、匯出前檢查、匯出）。

---

## 現況分析（技術前提）

### `GET /api/projects/` 現有欄位

```python
"SELECT p.*, "
"(SELECT COUNT(*) FROM selection_items si WHERE si.project_id = p.id) as selection_count, "
"(SELECT exported_at FROM export_jobs ej WHERE ej.project_id = p.id "
" ORDER BY ej.exported_at DESC LIMIT 1) as last_export "
"FROM procurement_projects p ORDER BY p.created_at DESC"
```

已有：`selection_count`、`last_export`、以及 `procurement_projects` 所有欄位（含 `budget_amount`、`price_field`、`subtotal_mode`）。

### selection_items 快照欄位（migration 003）

`selection_items` 在建立選書記錄時快照了 `vendor_books` 的關鍵欄位，包含：
- `selected_quantity`
- `list_price`（快照自 `vendor_books.list_price`）
- `purchase_price`（快照自 `vendor_books.purchase_price`）

因此計算選書小計可直接在 `selection_items` 上做 `SUM`，無需 JOIN `vendor_books`。

### book_matches 最新比對狀態邏輯

比對結果以「最新一筆 book_match（排除 `same_title_different_isbn`）」為準，與 `export_service.py` 一致：

```sql
(SELECT bm.match_status FROM book_matches bm
 WHERE bm.vendor_book_id = vb.id
   AND bm.match_status != 'same_title_different_isbn'
 ORDER BY bm.id DESC LIMIT 1)
```

### API 選項評估

| 選項 | 說明 | 優缺點 |
|------|------|--------|
| A | 擴充 `GET /api/projects/`，新增 subquery 欄位 | 單次請求，無 N+1；subquery 增多，但 SQLite 本地查詢效能可接受 |
| B | 新增 `GET /api/projects/{id}/summary`（per-project） | N+1 問題（N 個專案 = N 個額外請求） |
| C | 新增 `GET /api/projects/summary`（all-at-once） | 需要兩次請求；解耦但增加複雜度 |

**選擇 Option A**：避免 N+1，與 `loadProjects()` 的單次 `api('/api/projects/')` 呼叫相符，改動範圍最小。

---

## 需求一：擴充 `GET /api/projects/` 回傳欄位

### 新增四個欄位

| 欄位 | 類型 | 說明 |
|------|------|------|
| `last_import` | ISO string \| null | 該專案最後一次 `batch_type = 'vendor_books'` 的 import_batches.imported_at |
| `vendor_book_count` | int | 該專案所有 import_batches 下的 vendor_books 總數 |
| `already_owned_count` | int | vendor_books 中最新 match_status = 'already_owned' 的數量 |
| `selection_amount` | float | 依 subtotal_mode 計算的選書小計（0 if 無選書） |

### SQL

在既有 `list_projects` 查詢中，於 `last_export` subquery 後新增：

```sql
-- last_import（只查 batch_type='vendor_books'，避免館藏匯入時間誤導）
"(SELECT imported_at FROM import_batches ib2 "
"  WHERE ib2.project_id = p.id AND ib2.batch_type = 'vendor_books' "
"  ORDER BY ib2.imported_at DESC LIMIT 1) as last_import, "

-- vendor_book_count
"(SELECT COUNT(*) FROM vendor_books vb "
"  JOIN import_batches ib ON ib.id = vb.batch_id "
"  WHERE ib.project_id = p.id) as vendor_book_count, "

-- already_owned_count
"(SELECT COUNT(*) FROM vendor_books vb2 "
"  JOIN import_batches ib3 ON ib3.id = vb2.batch_id "
"  WHERE ib3.project_id = p.id "
"  AND (SELECT bm.match_status FROM book_matches bm "
"       WHERE bm.vendor_book_id = vb2.id "
"         AND bm.match_status != 'same_title_different_isbn' "
"       ORDER BY bm.id DESC LIMIT 1) = 'already_owned'"
") as already_owned_count, "

-- selection_amount
"COALESCE("
"  (SELECT CASE p.subtotal_mode "
"     WHEN 'quantity_times_list_price' "
"       THEN SUM(si.selected_quantity * si.list_price) "
"     ELSE SUM(si.selected_quantity * si.purchase_price) "
"   END "
"   FROM selection_items si "
"   WHERE si.project_id = p.id AND si.selected_quantity > 0), "
"  0"
") as selection_amount "
```

### 注意事項

- `last_import` 只查 `batch_type = 'vendor_books'` 的批次，排除 `library_holdings` 批次，避免使用者看到的「最後匯入」時間是館藏匯入而非書商書目匯入。
- `already_owned_count` 的 `already_owned` 判斷邏輯與 `export_service.py` 一致，取最新非 `same_title_different_isbn` 的 match_status。
- `selection_amount` 使用 `selection_items` 快照欄位（`list_price`、`purchase_price`），不 JOIN `vendor_books`。
- **MVP 限制：`selection_amount` 不套用 `user_overrides`**。若使用者在選書或匯出前檢查頁面覆蓋了個別書目的定價，卡片顯示的小計可能**低於**實際匯出金額（`export_jobs.total_amount` 已套用 `user_overrides`）。本任務不修正此差異；如需修正，應建立獨立任務。
- `COALESCE(..., 0)` 確保無選書記錄時回傳 `0` 而非 `null`。
- `p.subtotal_mode` 在 correlated subquery 中引用外層 row，SQLite 支援。
- 不修改回傳格式的其他欄位，舊前端行為不受影響。

---

## 需求二：卡片狀態摘要 UI

### 卡片 HTML 結構調整

現有卡片結構（橫向 flex：左文字 | 右按鈕）調整為**縱向 flex**：

```
[project-card]  ← flex-direction: column
  [project-card-top]  ← display: flex; align-items: flex-start
    [project-info]    ← flex: 1
      .project-name  + badge
      .project-meta  (type · 定價/小計設定)
    [project-actions]  ← 靠右，[選擇][設定][刪除]
  [project-card-status]  ← 新增；狀態摘要 4 行
  [project-card-nav]    ← 新增；快速步驟按鈕
```

**注意**：移除現有第 2、3 條 `.project-meta` 行（定價/小計設定已整併至第 1 meta 行；預算、選書數、匯出時間移至 status 區）。

### 狀態摘要格式

`.project-card-status` 顯示 4 個資訊項目（逐行排列，文字小，灰色）：

| 項目 | 空值狀態 | 有值狀態 |
|------|---------|---------|
| 書商書目 | `vendor_book_count == 0` → "尚未匯入書商書目" | "書商書目 {N} 本（{date}）" + 若 `already_owned_count > 0`：" · 館藏重複 {M} 本" |
| 選書 | `selection_count == 0` → "尚未選書" | "已選 {N} 本 · 小計 NT$ {amount} 元" |
| 預算 | `budget_amount == null` → "預算未設定" | remaining ≥ 0："預算剩餘 NT$ {remaining} 元（已用 {%}%）"；remaining < 0："預算超支 NT$ {overrun} 元" |
| 匯出 | `last_export == null` → "尚未匯出" | "上次匯出 {date}" |

**格式輔助：**
- 日期：`new Date(iso).toLocaleDateString('zh-TW')`
- 金額：`Math.round(n).toLocaleString('zh-TW')`（負數取絕對值後格式化）
- `remaining = budget_amount - selection_amount`
- 已用百分比：`Math.round(selection_amount / budget_amount * 100)`
- `selection_amount === 0` 時：顯示「預算 NT$ {budget_amount} 元（未使用）」

---

## 需求三：快速步驟按鈕

### 新增 `goToStep` helper

```javascript
function goToStep(event, url, id, name) {
  event.stopPropagation();
  setProject(id, name);
  window.location.href = url;
}
```

### `.project-card-nav` 按鈕組

```html
<div class="project-card-nav">
  <button class="btn btn-secondary btn-sm"
    onclick="goToStep(event,'/import.html',${id},'${escapedName}')">匯入</button>
  <button class="btn btn-secondary btn-sm"
    onclick="goToStep(event,'/selection.html',${id},'${escapedName}')">選書</button>
  <button class="btn btn-secondary btn-sm"
    onclick="goToStep(event,'/export-check.html',${id},'${escapedName}')">匯出前檢查</button>
  <button class="btn btn-secondary btn-sm"
    onclick="goToStep(event,'/export.html',${id},'${escapedName}')">匯出 Excel</button>
</div>
```

所有按鈕均呼叫 `event.stopPropagation()`（透過 `goToStep` 封裝），不觸發卡片 `onclick`。

---

## CSS 變更

### 調整 `.project-card`

```css
/* 原 display: flex; align-items: center; gap: 16px */
/* 改為 flex-direction: column */
.project-card {
  /* ... 保留其他屬性 ... */
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: stretch;   /* 取代 center */
}
```

`::before` 偽元素（`position: absolute; left: 0; top: 16px; bottom: 16px`）不受影響，仍相對於 `.project-card`（`position: relative`）定位。

### 新增 CSS 類別

```css
.project-card-top {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.project-info {
  flex: 1;
}

.project-card-status {
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 12px;
  color: #6e6e73;
  padding-top: 2px;
  border-top: 1px solid rgba(0,0,0,0.05);
}

.project-card-nav {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
```

### `.project-card .project-actions` 保留不變

`margin-left: auto` 在 `.project-card-top`（row flex）中仍有效，不需修改。

---

## UI/UX 驗收條件

| 場景 | 預期結果 |
|------|---------|
| 有書商書目 + 有館藏重複 | 顯示 "書商書目 N 本（date） · 館藏重複 M 本" |
| 有書商書目 + 無館藏重複 | 顯示 "書商書目 N 本（date）"，無館藏重複文字 |
| 尚未匯入 | 顯示 "尚未匯入書商書目" |
| 有選書記錄 | 顯示 "已選 N 本 · 小計 NT$ X,XXX 元" |
| 無選書記錄 | 顯示 "尚未選書" |
| 已設預算，選書小計未超支 | 顯示 "預算剩餘 NT$ R,RRR 元（已用 Z%）" |
| 已設預算，選書小計已超支 | 顯示 "預算超支 NT$ X,XXX 元" |
| 已設預算但無選書 | 顯示 "預算 NT$ Y,YYY 元（未使用）" |
| 未設預算 | 顯示 "預算未設定" |
| 已匯出 | 顯示 "上次匯出 date" |
| 未匯出 | 顯示 "尚未匯出" |
| 點擊 [匯入] 按鈕 | `setProject` + 導向 `/import.html`，不觸發卡片 onclick |
| 點擊 [選書] 按鈕 | `setProject` + 導向 `/selection.html` |
| 點擊 [匯出前檢查] 按鈕 | `setProject` + 導向 `/export-check.html` |
| 點擊 [匯出 Excel] 按鈕 | `setProject` + 導向 `/export.html`（不直接執行匯出） |
| 點擊卡片主體 | `setProject` + 導向 `/selection.html`（匯入通常只做一次，選書是高頻入口） |
| subtotal_mode = quantity_times_list_price | selection_amount 使用 `list_price` 計算 |
| subtotal_mode = quantity_times_purchase_price | selection_amount 使用 `purchase_price` 計算 |
| `selection_amount` = 0 | 小計仍顯示（"小計 NT$ 0 元"），不當作空值 |

---

## 非目標

- 不在卡片直接觸發 Excel 匯出（[匯出 Excel] 按鈕只導頁，不呼叫 API）。
- 不修改資料庫 schema，不新增 migration。
- 不新增獨立 summary API endpoint。
- 不做每個步驟的「完成」狀態標記（勾號或進度條）。
- 不修改 stepper nav 結構。
- 不改其他頁面（`import.html`、`selection.html` 等）。
- 不修改已選書目的詳細比對狀態統計（只顯示 `already_owned_count`）。
- 不對「書商書目」項目顯示 per-status breakdown（available/missing_isbn/invalid_isbn 等）。

---

## 風險與限制

| 風險 | 說明 | 處理方式 |
|------|------|---------|
| `already_owned_count` subquery 效能 | 含雙層相關子查詢（vendor_books × book_matches）；書目量大時稍慢 | 學校採購場景資料量小（< 1000 本），可接受 |
| `selection_amount` 使用快照價格，未套用 user_overrides | 若使用者覆蓋了定價，卡片小計 ≠ 匯出金額 | MVP 已知限制，列於注意事項；如需修正需建立獨立任務 |
| `selection_amount` 快照欄位可能為 null（migration 003 前舊資料） | `list_price`/`purchase_price` 可能為 null | SUM 遇 null 返回 null → COALESCE 為 0；顯示 "小計 NT$ 0 元" 合理 |
| `last_import` 只取 vendor_books 批次 | 館藏匯入時間不顯示 | 符合意圖，使用者關注的是書商書目匯入 |
| 卡片變高影響滾動體驗 | 每張卡片新增約 3 行文字 + 1 行按鈕 | 可接受；資訊更豐富，UX 整體提升 |
| `p.subtotal_mode` 在 subquery 中的可用性 | SQLite correlated subquery 引用外層欄位 | SQLite 標準行為，已驗證可用 |
