# Plan: task-project-status-dashboard

## 盤點（已完成）

### index.html 現有結構

**HTML 結構（已有）**

```html
<div id="project-banner" class="alert alert-info">...</div>
<div class="stats-row" id="stats-row">
  <div class="stat-card gray">...館藏筆數...</div>
  <div class="stat-card gray">...書商書單...</div>
  <div class="stat-card green">...可採購...</div>
  <div class="stat-card gray">...已選書...</div>
  <div class="stat-card gray">...上次匯出...</div>
</div>
<div class="card">
  <h2>快速導覽</h2>
  ...按鈕...
</div>
```

**JS 流程（已有）**

```javascript
requireAuth().then(async () => {
  const pid = getProjectId();
  // if no pid → return early
  proj = await api(`/api/projects/${pid}`);
  const [stats, selSummary, jobs] = await Promise.all([
    api(`/api/books/stats?project_id=${pid}`),
    api(`/api/selections/?project_id=${pid}`),
    api(`/api/exports/jobs?project_id=${pid}`),
  ]);
  // 填入 stat-holdings, stat-vendor, stat-available, stat-selection, stat-last-export
});
```

**可用 CSS 類別**（不需另外撰寫）

- `.card` — 白色卡片
- `.badge-export_ready` / `.badge-needs_review` / `.badge-missing_required` — 顏色標籤
- `.alert-info` / `.alert-warn` — 提示橫幅

### 既有 `/api/exports/check` 回傳格式

```json
{
  "total_selected": N,
  "export_ready": N,
  "needs_review": N,
  "missing_required": N,
  "already_owned": N,
  "details": [...]
}
```

呼叫需傳 `project_id`、`price_field`、`subtotal_mode`（均可從 `proj` 取得）。

---

## 實作步驟

### 步驟 1：加入「下一步建議」HTML 元素

在 `index.html` 的 `<div class="card">（快速導覽）` **之前**插入：

```html
<div id="next-step-card" class="card" style="display:none;margin-top:16px">
  <h2>下一步</h2>
  <div id="next-step-content"></div>
</div>
```

### 步驟 2：新增 `renderNextStep()` function

在 `<script>` 區段新增：

```javascript
function renderNextStep(stats, selCount, readiness) {
  const card = document.getElementById('next-step-card');
  const el = document.getElementById('next-step-content');
  card.style.display = '';

  const holdings = stats.total_holdings || 0;
  const vendor = stats.total_vendor_books || 0;
  const available = (stats.match_status || {}).available || 0;

  if (holdings === 0) {
    el.innerHTML = '<p>尚未匯入館藏，建議先匯入館藏再繼續。</p>'
      + '<a class="btn btn-secondary" href="/import.html">前往匯入 →</a>';
    return;
  }
  if (vendor === 0) {
    el.innerHTML = '<p>尚未匯入書商書單。</p>'
      + '<a class="btn btn-secondary" href="/import.html">前往匯入 →</a>';
    return;
  }
  if (available === 0) {
    el.innerHTML = '<p>書商書單比對後無可採購書籍，請確認館藏內容是否完整。</p>'
      + '<a class="btn btn-secondary" href="/match.html">查看比對結果 →</a>';
    return;
  }
  if (selCount === 0) {
    el.innerHTML = `<p>有 <strong>${available}</strong> 本可採購，建議前往選書。</p>`
      + '<a class="btn btn-secondary" href="/selection.html">前往選書 →</a>';
    return;
  }
  // 已選書，顯示匯出準備度
  let readyLine = '';
  if (readiness) {
    const r = readiness.export_ready || 0;
    const n = readiness.needs_review || 0;
    const m = readiness.missing_required || 0;
    readyLine = `<p style="margin:8px 0">
      <span class="badge badge-export_ready">就緒 ${r} 本</span>
      <span class="badge badge-needs_review">待補充 ${n} 本</span>
      <span class="badge badge-missing_required">缺必填 ${m} 本</span>
    </p>`;
  }
  el.innerHTML = `<p>已選 <strong>${selCount}</strong> 本書。</p>`
    + readyLine
    + '<a class="btn btn-secondary" href="/export-check.html">前往匯出前檢查 →</a>';
}
```

### 步驟 3：修改主流程，加入條件呼叫與渲染

在現有 `requireAuth().then(...)` 中，於填入統計卡片之後加入：

```javascript
const selCount = selSummary.summary.count || 0;
let readiness = null;
if (selCount > 0) {
  try {
    const pf = encodeURIComponent(proj.price_field || 'purchase_price');
    const sm = encodeURIComponent(proj.subtotal_mode || 'quantity_times_purchase_price');
    readiness = await api(
      `/api/exports/check?project_id=${pid}&price_field=${pf}&subtotal_mode=${sm}`
    );
  } catch { /* 不影響頁面其他內容 */ }
}
renderNextStep(stats, selCount, readiness);
```

### 步驟 4：驗證

**自動驗證**

```
python -m compileall app
python -m pytest -v
```

**手動驗證清單**

| 情境 | 預期下一步建議 |
|------|-------------|
| 館藏 = 0 | 尚未匯入館藏 + 匯入連結 |
| 館藏 > 0、書商書單 = 0 | 尚未匯入書商書單 + 匯入連結 |
| 書單已匯入、可採購 = 0 | 無可採購書籍 + 比對結果連結 |
| 有可採購、已選 = 0 | 有 N 本可採購 + 選書連結 |
| 已選 > 0 | 已選 N 本 + 就緒/待補充/缺必填摘要 + 匯出前檢查連結 |
| 統計卡片 | 既有數字顯示不受影響 |

### 步驟 5：Commit

```
feat(task-project-status-dashboard): add next-step guidance to index page
```

---

## 風險與注意事項

**`/api/exports/check` 呼叫失敗時**

呼叫包裝在 `try/catch` 中，`readiness = null`，`renderNextStep()` 會跳過準備度段落，只顯示「已選 N 本」與匯出前檢查連結。不影響頁面其他功能。

**`stats.match_status.available` 可能為 undefined**

使用 `(stats.match_status || {}).available || 0` 防禦 null。

**`selCount` 計算**

使用 `selSummary.summary.count`（選書記錄數），不是 `selSummary.items.length`（與 summary 一致）。

**手動驗證情境的建立**

部分情境（館藏 = 0、書單 = 0）在開發環境中需手動建立測試資料或直接確認判斷邏輯正確。若無法建立所有情境，至少需驗證「已選書 > 0」情境（最常見的上線狀態）。

---

## 預計影響範圍

| 路徑 | 說明 |
|------|------|
| `app/static/index.html` | 新增 `#next-step-card` HTML 元素、`renderNextStep()` function、主流程修改 |

不影響：後端程式碼、資料庫、其他靜態頁面、tests/。

---

## 驗證指令

```
python -m compileall app
python -m pytest -v
```

手動瀏覽器驗證（見步驟 4 清單）

## 成果報告

- result_report_mode: none
