# Plan: task-cleared-source-selection-display

## 實作步驟

### 步驟 1：確認現況（不實作）

確認以下現況，不修改任何程式碼：

**後端（已確認，不需更動）：**
- `selection_service.get_selected_books()` (line 153)：已回傳 `vendor_book_still_exists`（`vb.id IS NOT NULL`），透過 `LEFT JOIN vendor_books`。
- `validation_service.check_export_readiness()` (line 6)：已用 `COALESCE(bm.match_status, si.match_status_at_selection)` 回退；清除後驗證邏輯正確。
- `export_service.export_local_culture()` (line 64)：SQL 已用 COALESCE 回退至 snapshot；清除後匯出資料正確。
- 無需新增任何 API 端點或後端欄位。

**前端確認問題：**
- `selection.html` `loadData()`：`allBooks` 來自 `/api/books/matches`（vendor_books）；清除後為空陣列，grid 顯示「無資料」，但 budget bar 顯示 N 已選。
- `selection.html` `render()`：使用 `b.id`（來自 allBooks，即 vendor_book_id），與 `selMap[b.id]` 比對已選狀態。
- `selection.html` `saveOverrides()`：呼叫 `/api/books/${bookId}/overrides`，非 `/api/selections/{sel_id}/overrides`。
- `export.html` `loadPreview()`：filter 使用 `b.match_status === 'available'`；migration 003 後欄位為 `match_status_at_selection`，造成預覽永遠空白。
- `export-check.html`：不做任何來源狀態說明。

### 步驟 2：`app/static/selection.html` — 已選書目快照區塊

**2-a. 修改 `loadData()` 函式**

現有 `loadData()` 已同時呼叫 `/api/books/matches` 和 `/api/selections/`。在取得 `selData` 後：

```
const clearedItems = selData.items.filter(s => s.vendor_book_still_exists === false || s.vendor_book_still_exists === 0);
```

注意：SQLite boolean 以整數 0/1 回傳，JavaScript 端需同時判斷 `=== false` 和 `=== 0`（或用 `!s.vendor_book_still_exists`，因為 0 和 false 在 `!` 下行為一致）。

**2-b. 新增 `renderClearedItems(items)` 函式**

- 若 `items.length === 0`：確保 `#cleared-section` 隱藏，直接 return。
- 若 `items.length > 0`：顯示 `#cleared-section`，渲染快照書目卡片。

每筆 `s` 使用 `s.title`、`s.author`、`s.isbn_normalized || s.isbn`、`s.list_price`、`s.purchase_price`、`s.selected_quantity`，以及 `s.sel_id`（selection_items.id）。

- 不顯示「加入選書」按鈕。
- 保留「修正資料」按鈕，ID 使用 `sel-${s.sel_id}`，overrides 儲存呼叫 `saveSelectionOverrides(s.sel_id, s)` 而非 `saveOverrides(s.id)`。
- 新增 `saveSelectionOverrides(selId, b)` 函式，呼叫 `PATCH /api/selections/${selId}/overrides`。

**2-c. 新增 `#cleared-section` HTML 區塊**

在 `#book-grid` 之後加入：

```html
<div id="cleared-section" style="display:none;margin-top:24px">
  <h3 style="font-size:15px;color:#6e6e73;margin-bottom:12px">
    已選書目（書商書單來源已清除，以下資料來自保存的採購紀錄快照）
  </h3>
  <div id="cleared-grid" class="books-grid"></div>
</div>
```

**2-d. 在 `loadData()` 末尾呼叫**

```javascript
renderClearedItems(clearedItems);
```

### 步驟 3：`app/static/export.html` — 修正預覽 bug 與來源說明

**3-a. 修正 `loadPreview()` filter**

現有（有 bug）：
```javascript
const items = sel.items.filter(b => b.match_status === 'available' && b.selected_quantity > 0);
```

修正為：
```javascript
const items = sel.items.filter(b =>
  b.selected_quantity > 0 &&
  (b.match_status_at_selection !== 'already_owned' && b.match_status_at_selection !== null ||
   !b.vendor_book_still_exists)
);
```

最簡版（直接顯示所有有數量的紀錄，由後端 export_service 篩選）：
```javascript
const items = sel.items.filter(b => b.selected_quantity > 0);
```

建議採最簡版，因為 export_service 已在 SQL 中做篩選，preview 顯示全部已選、在說明中交代即可。

**3-b. 新增來源說明**

在 `loadPreview()` 中，檢查是否有 `vendor_book_still_exists === false` 的項目：
```javascript
const hasCleared = sel.items.some(b => !b.vendor_book_still_exists);
if (hasCleared) {
  // 在 #preview-card h2 前或後加入 info 說明
}
```

在 `#preview-card` 的 `<h2>` 下方加入 `id="preview-source-note"` div：

```html
<div id="preview-source-note" style="display:none" class="alert alert-info">
  部分書目的書商書單來源已清除，書目資料來自保存的採購紀錄快照，不影響匯出結果。
</div>
```

`loadPreview()` 中依 `hasCleared` 顯示或隱藏。

### 步驟 4：`app/static/export-check.html` — 非阻擋來源說明

**4-a. 修改 `runCheck()` 函式**

在現有 `api('/api/exports/check?...')` 呼叫之後，額外呼叫 `/api/selections/?project_id=${pid}` 取得 `selData`：

```javascript
const [data, selData] = await Promise.all([
  api(`/api/exports/check?project_id=${pid}&price_field=${pf}&subtotal_mode=${sm}`),
  api(`/api/selections/?project_id=${pid}`)
]);
```

**4-b. 在 `renderHint()` 或 `runCheck()` 末尾加入來源說明**

```javascript
const hasCleared = selData.items.some(b => !b.vendor_book_still_exists);
const sourceNote = document.getElementById('source-note');
if (sourceNote) {
  sourceNote.style.display = hasCleared ? 'block' : 'none';
}
```

**4-c. 新增 `#source-note` HTML**

在 `<div class="card" style="padding:0">` 前（即 detail 表格前）加入：

```html
<div id="source-note" class="alert alert-info" style="display:none;margin-bottom:12px">
  部分書目的書商書單來源已清除，比對狀態以選書當時快照為準，不影響匯出準備度判斷。
</div>
```

### 步驟 5：驗證

**5-a. 語法驗證（後端未修改，自動通過）**

```
python -m compileall app
```

**5-b. 手動瀏覽器驗證流程**

1. 登入，選定採購專案。
2. 匯入書商書單。
3. 執行比對，確認有 available 書目。
4. 選書頁加入至少 2 本書。
5. **清除書商書單**（`DELETE /api/imports/vendor-books?project_id=N`）。
6. 選書頁：
   - Budget bar 仍顯示 2 已選書目。
   - 主 grid 顯示「無資料」（無候選書）。
   - `#cleared-section` 出現，顯示 2 筆已選快照書目。
7. 匯出前檢查頁：
   - 所有書目仍出現在表格中。
   - `#source-note` 出現，說明來源已清除。
   - `missing_required` 計數不因來源清除而增加。
8. 匯出頁：
   - 預覽表格顯示 2 筆書目（不再空白）。
   - `#preview-source-note` 出現。
   - 點「產生 Excel」，下載結果正確。
9. **書商書單仍存在時（未清除）**：
   - 選書頁無 `#cleared-section`。
   - 匯出頁 `#preview-source-note` 隱藏。
   - 匯出前檢查頁 `#source-note` 隱藏。
   - 現有功能不受影響。

## 風險與注意事項

- `vendor_book_still_exists` 為 SQLite 整數（0 / 1），JavaScript 判斷時用 `!s.vendor_book_still_exists` 或 `s.vendor_book_still_exists == 0`，避免嚴格 `=== false` 遺漏 0。
- `selection.html` 使用兩套 ID 命名空間：`b.id`（vendor_book_id，來自 allBooks）與 `s.sel_id`（selection_items.id，來自 selData.items）。清除後渲染的 cleared section 必須使用 `sel_id`，避免與主 grid 衝突。
- `saveSelectionOverrides` 呼叫 `/api/selections/{sel_id}/overrides`（PATCH），而非 `/api/books/{vendor_book_id}/overrides`；這兩條路由用途不同，不可混用。
- `export.html` 預覽 filter 修正後顯示的書目數量可能多於修正前（原本因 bug 為零）。需確認渲染邏輯不因此引入新問題。
- `export-check.html` 追加 `/api/selections/` API 呼叫，需確認 Promise.all 正確合併兩個 API 結果。
- 若 `selData.items` 中某筆 `sel_id` 為 null（理論上不應發生），渲染時需防禦性處理。

## 預計影響範圍

- `app/static/selection.html`：新增 `#cleared-section` HTML、新增 `renderClearedItems` 與 `saveSelectionOverrides` 函式、修改 `loadData()`（約 50–70 行）。
- `app/static/export.html`：修正 preview filter（2 行）、新增 `#preview-source-note` HTML 與顯示邏輯（約 15 行）。
- `app/static/export-check.html`：修改 `runCheck()` 追加 API 呼叫、新增 `#source-note` HTML 與顯示邏輯（約 20 行）。
- 不修改任何後端程式碼。
- 不修改 CSS（使用已有的 `alert alert-info` 樣式）。

## 驗證指令

- lint: 無既有 lint 設定
- format: 無既有 format 設定
- typecheck: 無既有 typecheck 設定
- test: `python -m compileall app`（後端未修改，自動通過）
- build: 無 build 步驟

## 成果報告

- result_report_mode: none
- 適用情境：純前端 UI 修正，驗收依手動瀏覽器驗證步驟（步驟 5-b）確認
