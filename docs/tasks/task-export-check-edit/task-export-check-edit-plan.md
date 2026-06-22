# Plan: task-export-check-edit

## 實作步驟

### 步驟 1：`validation_service.py` 補 `sel_id`

在 `check_export_readiness()` 的 SQL 查詢中，`selection_items si` 已有 `si.id`，在 `details.append(...)` 補上：

```python
"sel_id": r["id"],
```

（`r` 為 `selection_items` 的 row，`r["id"]` 即 `selection_items.id`）

### 步驟 2：`selection_service.py` 新增 `remove_selection()`

```python
def remove_selection(selection_id: int) -> dict:
    conn = get_connection()
    result = conn.execute(
        "DELETE FROM selection_items WHERE id = ?", (selection_id,)
    )
    count = result.rowcount
    conn.commit()
    conn.close()
    if count == 0:
        raise ValueError(f"selection_items.id={selection_id} 不存在")
    return {"deleted": True, "selection_id": selection_id}
```

### 步驟 3：`selections.py` 新增單筆刪除 endpoint

在 `router.delete("/")` 之後新增：

```python
@router.delete("/{selection_id}")
async def delete_selection(
    selection_id: int,
    user_id: int = Depends(require_auth),
):
    try:
        result = remove_selection(selection_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result
```

同時在 import 行補上 `remove_selection`。

### 步驟 4：`export-check.html` 前端修改

#### 4-1 新增頁面狀態變數

```js
let projectType = null;
let bookDataMap = {};
```

#### 4-2 `requireAuth()` 區塊補取 `projectType` 與建 `bookDataMap`

在現有的 `proj = await api(...)` 之後補：

```js
projectType = proj.project_type;
```

在 `runCheck()` 結束後，將 `selData.items` 建成 lookup map：

```js
bookDataMap = {};
selData.items.forEach(b => { bookDataMap[b.id] = b; });
```

（`selData` 已由 `runCheck()` 的 `Promise.all` 取得）

#### 4-3 `renderDetails()` 表格新增「操作」欄

表頭 `<thead>` 補 `<th>操作</th>`。

每行 `<tr>` 補：

```js
const isOwned = d.match_status === 'already_owned';
const actionCell = isOwned ? '<td></td>' : `<td>
  <button class="btn btn-secondary btn-sm" onclick="removeBook(${d.sel_id})">移除</button>
  <button class="btn btn-secondary btn-sm" onclick="toggleCheckEdit(${d.sel_id}, ${d.vendor_book_id})" style="margin-left:4px">修正</button>
</td>`;
```

每行後插入可展開的修正列：

```js
`<tr id="check-edit-row-${d.sel_id}" style="display:none">
  <td colspan="6">${buildEditForm(d.sel_id, d.vendor_book_id)}</td>
</tr>`
```

#### 4-4 新增 `H_ALLOWED` 常數

複製 `selection.html` 的 `H_ALLOWED` 陣列至 `export-check.html`。

#### 4-5 新增 `buildEditForm(selId, vendorBookId)`

從 `bookDataMap[vendorBookId]` 取現有值（含 overrides），產生與 `selection.html` 相同的 inline edit 表單 HTML：
- 共用欄位：書名、作者、出版社、獲獎項目、定價、單價
- 一般圖書採購額外欄位（`projectType === 'general_books'`）：必選/推薦（A欄）、H欄推薦來源、備註（L欄）
- 按鈕：「儲存修正」（呼叫 `saveCheckEdit(selId, vendorBookId)`）、「取消」

#### 4-6 新增 `toggleCheckEdit(selId, vendorBookId)`

```js
function toggleCheckEdit(selId, vendorBookId) {
  const row = document.getElementById('check-edit-row-' + selId);
  row.style.display = row.style.display === 'none' ? '' : 'none';
}
```

#### 4-7 新增 `removeBook(selId)`

```js
async function removeBook(selId) {
  if (!confirm('確定從選書清單移除此書？')) return;
  try {
    await api(`/api/selections/${selId}`, { method: 'DELETE' });
    await runCheck();
  } catch (e) {
    showToast('移除失敗：' + e.message);
  }
}
```

#### 4-8 新增 `saveCheckEdit(selId, vendorBookId)`

收集 `[data-check-bookid="${vendorBookId}"]` 欄位值，呼叫：
1. `PATCH /api/books/{vendorBookId}/overrides`
2. `PATCH /api/selections/{selId}/overrides`（僅 A/H/L 欄位）

成功後呼叫 `runCheck()`。

#### 4-9 `runCheck()` 補更新 `bookDataMap`

`runCheck()` 執行後將新取得的 `selData.items` 更新 `bookDataMap`，確保修正後資料是最新的。

## 風險與注意事項

1. **`renderDetails()` 改為輸出兩個 `<tr>` per 書目**：需確認表格結構正確，colspan 數量與 `<thead>` 欄位數一致（目前 5 欄，加操作後為 6 欄）。

2. **`bookDataMap` 鍵值**：`selData.items` 中 `b.id` 為 `vendor_book_id`（`selection_service.py` 已做別名 `d["id"] = d.get("vendor_book_id")`），`b.sel_id` 為 `selection_items.id`。確認 key 使用 `vendor_book_id`。

3. **`runCheck()` 需回傳 `selData`**：目前 `runCheck()` 內部有 `selData` 但未回傳。需調整使 `bookDataMap` 能在每次 `runCheck()` 後更新，或在 `runCheck()` 內部直接更新 `bookDataMap`。

4. **路由順序（FastAPI）**：`DELETE /api/selections/` 與 `DELETE /api/selections/{selection_id}` 可能衝突。FastAPI 路由依宣告順序匹配，確認 `/{selection_id}` 在 `/` 之後宣告，且 `selection_id` 為 `int`（不會匹配空字串），不會衝突。

5. **`already_owned` 書目的操作欄**：這類書目本就不該被選書（屬異常狀態），不顯示按鈕，避免誤操作。

## 預計影響範圍

- `app/services/validation_service.py`：`details` 補一個欄位 `sel_id`
- `app/services/selection_service.py`：新增 `remove_selection()` 函式
- `app/routers/selections.py`：新增 `DELETE /{selection_id}` endpoint，補 import
- `app/static/export-check.html`：新增狀態變數、`H_ALLOWED`、`buildEditForm()`、`toggleCheckEdit()`、`removeBook()`、`saveCheckEdit()`；修改 `renderDetails()` 與 `runCheck()`

## 驗證指令

- lint: 無既有設定
- format: 無既有設定
- typecheck: 無既有設定
- test: 無自動化測試
- build: `python -m compileall app`

## 手動驗證步驟

1. 執行 `python -m compileall app`，確認無錯誤。
2. 重啟本地服務（程式碼有後端變更，需重啟）。
3. 以含缺填書目的專案開啟 `export-check.html`：
   a. 確認表格有「操作」欄，每行有「移除」與「修正」按鈕。
   b. `already_owned` 書目操作欄為空。
4. 移除測試：點「移除」→ 確認對話框 → 確認後表格刷新，該書消失，統計數字更新。
5. 修正測試（一般圖書採購）：
   a. 點「修正」，確認展開 inline 表單，欄位預填現有值。
   b. 確認含 A/H/L 欄位。
   c. 填入缺失欄位後點「儲存修正」，確認 toast 出現，表格刷新，完整度狀態更新。
6. 修正測試（本土文化採購）：確認表單不含 A/H/L 欄位。
7. 修正後，確認「繼續匯出」按鈕提示文字隨缺填數量正確更新。
8. 確認既有匯出功能正常（繼續匯出 → 下載 Excel 正確）。

## 成果報告

- result_report_mode: none
- 適用情境：不適用
- 報告路徑（若 mode 非 none）：`docs/reports/task-export-check-edit/`
