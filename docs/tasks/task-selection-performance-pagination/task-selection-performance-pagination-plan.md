# Plan: task-selection-performance-pagination

## 實作步驟

### 步驟 1：加入分頁狀態變數

在 `app/static/selection.html` JS 區塊頂部（`let allBooks = [];` 附近）新增：

```js
const PAGE_SIZE = 100;
let currentPage = 1;
let filteredBooks = [];
```

### 步驟 2：修改 `applyFilter()`

在 `applyFilter()` 結尾，將 `render(filtered)` 改為：

```js
filteredBooks = filtered;
currentPage = 1;
updateResultCount();
renderCurrentPage();
```

說明：
- `filteredBooks` 保存完整篩選排序後的結果（不截斷），供翻頁使用。
- `currentPage` 重設為 1（篩選條件一旦改變，必須回到第 1 頁）。
- `updateResultCount()` 更新頁碼資訊顯示。
- `renderCurrentPage()` 只 render 當前頁範圍的書卡。

### 步驟 3：新增 `renderCurrentPage()`

```js
function renderCurrentPage() {
  const start = (currentPage - 1) * PAGE_SIZE;
  const end = Math.min(start + PAGE_SIZE, filteredBooks.length);
  render(filteredBooks.slice(start, end));
  updatePagination();
}
```

### 步驟 4：新增 `updateResultCount()`

取代現有 `applyFilter()` 中的 `result-count` 更新：

```js
function updateResultCount() {
  const total = filteredBooks.length;
  if (total === 0) {
    document.getElementById('result-count').textContent = '';
    return;
  }
  const start = (currentPage - 1) * PAGE_SIZE + 1;
  const end = Math.min(currentPage * PAGE_SIZE, total);
  document.getElementById('result-count').textContent =
    `第 ${start}–${end} 筆 / 共 ${total} 筆`;
}
```

### 步驟 5：新增分頁控制 HTML

在 `<div id="book-grid" ...>` 前後各加一個分頁列容器（或擇一加在下方），建議加在書卡網格下方：

```html
<div id="pagination" style="display:none;margin-top:16px;justify-content:center;align-items:center;gap:8px">
  <button class="btn btn-secondary btn-sm" id="page-prev" onclick="goPage(-1)">上一頁</button>
  <span id="page-info" style="font-size:13px;color:#666"></span>
  <button class="btn btn-secondary btn-sm" id="page-next" onclick="goPage(1)">下一頁</button>
</div>
```

初始以 `display:none` 隱藏；`updatePagination()` 在 `totalPages > 1` 時設 `pag.style.display = 'flex'`，在 `totalPages <= 1` 時設回 `'none'`。

### 步驟 6：新增 `updatePagination()` 與 `goPage()`

```js
function updatePagination() {
  const total = filteredBooks.length;
  const totalPages = Math.ceil(total / PAGE_SIZE);
  const pag = document.getElementById('pagination');
  if (totalPages <= 1) {
    pag.style.display = 'none';
    return;
  }
  pag.style.display = 'flex';
  document.getElementById('page-prev').disabled = currentPage <= 1;
  document.getElementById('page-next').disabled = currentPage >= totalPages;
  document.getElementById('page-info').textContent =
    `第 ${currentPage} 頁 / 共 ${totalPages} 頁`;
}

function goPage(delta) {
  const totalPages = Math.ceil(filteredBooks.length / PAGE_SIZE);
  const next = currentPage + delta;
  if (next < 1 || next > totalPages) return;
  currentPage = next;
  updateResultCount();
  renderCurrentPage();
  document.getElementById('book-grid').scrollIntoView({ behavior: 'smooth', block: 'start' });
}
```

翻頁後 scroll 到網格頂部，避免使用者迷失位置。

### 步驟 7：確認 `render()` 不需修改

`render(books)` 維持現有邏輯，僅接受傳入的子集 slice 即可。無需改動 `render()` 本身。

### 步驟 8：執行驗證指令並手動測試（見「驗證指令」與「手動驗證步驟」）

### 步驟 9：commit

```
fix(task-selection-performance-pagination): add client-side pagination to selection page
```

## 風險與注意事項

1. **`addBook()` 後 render 行為**：`addBook()` 只更新 DOM 中既有書卡的按鈕狀態（`cta-{id}`），不重新呼叫 render，不受分頁影響。若書卡在目前頁以外，按鈕狀態正確（`selMap` 已更新，下次翻頁時 render 會取用新值）。  
   → 不需要修改 `addBook()`。

2. **`saveOverrides()` 後 render 行為**：`saveOverrides()` 儲存後會呼叫 `loadData()`（見現有程式碼），`loadData()` 重跑 `applyFilter()`，`applyFilter()` 重設 `currentPage = 1`。  
   → 使用者儲存 override 後，頁面回到第 1 頁是可接受行為；若需保留頁碼，屬 V2 優化。

3. **`clearAll()` 後 render 行為**：`clearAll()` 呼叫 `loadData()`，與 override 同理，頁面回到第 1 頁。

4. **`filteredBooks` 初始值**：頁面剛載入時 `filteredBooks = []`，分頁列應隱藏，`result-count` 保持空字串，直到 `applyFilter()` 被呼叫後才有內容。

5. **本土文化採購（670 筆）**：PAGE_SIZE = 100 時，670 筆共 7 頁，分頁列會出現。若需在 670 筆時隱藏分頁列，只需確認 `updatePagination()` 的 `totalPages <= 1` 條件改為業務上合理的值（目前 spec 允許顯示，770 筆以上才有必要，實作依實際測試調整）。  
   → 本土文化採購仍需手動確認回歸。

6. **HTML 中 `pagination` 初始 display 樣式衝突**：`style="display:none"` 與 JS 後續設 `display:flex` 衝突問題，務必統一用 JS 控制，HTML 只設 `display:none` 初始值。

7. **不改 `render()` 函式簽名**：避免影響任何其他可能呼叫 render 的地方（目前只有 applyFilter 和 renderCurrentPage，確認後無問題）。

## 預計影響範圍

- `app/static/selection.html`：JS 區塊新增 3 個狀態變數、4 個新函式（`renderCurrentPage`、`updateResultCount`、`updatePagination`、`goPage`），修改 `applyFilter()` 尾端，HTML 新增分頁列 `<div id="pagination">`。
- 後端程式碼：不涉及。
- 其他前端頁面：不涉及。
- CSS：不涉及（使用現有 `.btn .btn-secondary .btn-sm` class）。

## 驗證指令

- lint: 無既有設定（無 eslint/flake8 等）
- format: 無既有設定
- typecheck: 無既有設定
- test: 無自動化測試
- build: `python -m compileall app`（Python 語法驗證，不涵蓋前端 JS）

## 手動驗證步驟

1. 執行 `python -m compileall app`，確認無錯誤。
2. 啟動本地服務（`python run.py` 或專案慣用指令）。
3. 以一般圖書採購專案（約 6750 筆）開啟 selection.html：
   a. 確認首次 render 不凍結，只出現最多 PAGE_SIZE 張書卡。
   b. 確認 result-count 顯示「第 1–100 筆 / 共 N 筆」格式。
   c. 確認分頁列出現「第 1 頁 / 共 N 頁」，上一頁 disabled。
4. 篩選與排序測試：
   a. 切換「比對狀態」篩選條件，確認頁面回到第 1 頁，result-count 更新正確。
   b. 切換排序方式，確認頁面回到第 1 頁，書卡順序正確。
   c. 點選「重設篩選」，確認回到第 1 頁、顯示全部書目。
   d. 輸入關鍵字，確認篩選正確且回到第 1 頁。
5. 翻頁測試：
   a. 點「下一頁」，確認書卡更新為第 2 頁範圍，上一頁 enabled。
   b. 翻到最後一頁，確認下一頁 disabled。
   c. 翻回第 1 頁，確認上一頁 disabled。
6. 加入選書測試：
   a. 點「＋ 加入選書」，確認按鈕變「已加入」（disabled）。
   b. 確認預算列「已選書目」、「定價小計」、「採購單價小計」數字更新正確。
7. 修正資料測試：
   a. 展開「修正資料」，修改欄位後點「儲存修正」。
   b. 確認儲存成功（toast 提示），書卡資料更新。
8. 清空選書測試：
   a. 點「清空選書」，確認提示，確認後書目清空，預算歸零。
9. 本土文化採購回歸測試（約 670 筆）：
   a. 切換到本土文化採購專案，開啟 selection.html。
   b. 確認頁面正常顯示，篩選、加入選書、修正資料功能正常。
10. 效能記錄（選擇性）：
    a. 改善前後於瀏覽器 DevTools > Performance 或 console.time 記錄首次 render 耗時。
    b. 將結果記入 session log 的「驗證到哪」。

## 成果報告

- result_report_mode: none
- 適用情境：不適用
- 報告路徑（若 mode 非 none）：`docs/reports/task-selection-performance-pagination/`
