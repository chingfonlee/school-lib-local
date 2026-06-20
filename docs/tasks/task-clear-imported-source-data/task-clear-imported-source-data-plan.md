# Plan: task-clear-imported-source-data

## 實作步驟

### 步驟 1：確認現有 helper 狀態

1. 確認 `_clear_vendor_books_for_project(conn, project_id)` 已存在於 `app/services/import_service.py`（line 592），且不刪除 `selection_items`，不自行 commit。
2. 確認 `_clear_library_holdings(conn)` **尚未存在**，需新增。

### 步驟 2：`app/services/import_service.py` — 新增 helper 與 public functions

**2-a. 新增 private helper `_clear_library_holdings(conn)`**

在 `_clear_vendor_books_for_project` 前方新增此 helper。刪除順序：

1. `DELETE FROM book_matches WHERE holding_id IS NOT NULL`（清除引用館藏的比對紀錄）
2. `DELETE FROM library_holdings`
3. 取得 `import_batches` 中 `batch_type='library_holdings'` 的 id 列表後刪除
4. 不自行 commit（caller 負責 transaction）
5. 回傳 None

**2-b. 新增 public function `clear_library_holdings(user_id: int) -> dict`**

```
連線
計算刪除前筆數：
  - holdings_count = SELECT COUNT(*) FROM library_holdings
  - matches_count = 引用 holding_id 的 book_matches 數
  - batches_count = batch_type='library_holdings' 的 import_batches 數
呼叫 _clear_library_holdings(conn)
commit
rollback on exception（並 raise）
close
回傳：
{
  "deleted_holdings": <int>,
  "deleted_matches": <int>,
  "deleted_batches": <int>
}
```

**2-c. 新增 public function `clear_vendor_books(project_id: int, user_id: int) -> dict`**

```
連線
確認 project 存在（SELECT id FROM procurement_projects WHERE id=?），若不存在 raise ValueError
計算刪除前筆數：
  - old_batch_ids = batch_type='vendor_books' AND project_id=?
  - vendor_books_count = SELECT COUNT(*) FROM vendor_books WHERE batch_id IN (old_batch_ids)
  - matches_count = book_matches 引用上述 vendor_book_id 數
  - batches_count = len(old_batch_ids)
  - preserved_count = SELECT COUNT(*) FROM selection_items WHERE project_id=?
呼叫 _clear_vendor_books_for_project(conn, project_id)
commit
rollback on exception（並 raise）
close
回傳：
{
  "project_id": <int>,
  "deleted_vendor_books": <int>,
  "deleted_matches": <int>,
  "deleted_batches": <int>,
  "preserved_selection_items": <int>
}
```

### 步驟 3：`app/routers/imports.py` — 新增 DELETE 端點

**3-a. 新增 import**

在現有 import 中加入 `clear_library_holdings`、`clear_vendor_books`。

**3-b. 新增 `DELETE /api/imports/holdings`**

```python
@router.delete("/holdings")
async def delete_holdings(user_id: int = Depends(require_auth)):
    try:
        result = clear_library_holdings(user_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result
```

**3-c. 新增 `DELETE /api/imports/vendor-books`**

```python
@router.delete("/vendor-books")
async def delete_vendor_books(project_id: int, user_id: int = Depends(require_auth)):
    try:
        result = clear_vendor_books(project_id, user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result
```

`project_id` 作為 query parameter（FastAPI 預設）。

注意：現有 `POST /vendor-books`、`POST /vendor-books/preview`、`POST /vendor-books/confirm` 路由不受影響。

### 步驟 4：`app/static/import.html` — 前端清除按鈕

**4-a. 「學校館藏」區塊加入清除按鈕**

- 加入紅色/危險樣式按鈕「清除學校館藏」。
- 呼叫 `clearHoldings()` function。

**4-b. 「書商書單」區塊加入清除按鈕**

- 加入紅色/危險樣式按鈕「清除目前專案書商書單」。
- 呼叫 `clearVendorBooks()` function。

**4-c. 實作 `clearHoldings()` function**

```
if (!confirm('確定要清除所有學校館藏資料？此操作無法復原。')) return
const input = prompt('請輸入「清除」以確認：')
if (input !== '清除') return
呼叫 DELETE /api/imports/holdings
成功：顯示刪除摘要（deleted_holdings、deleted_matches、deleted_batches 筆數）
失敗：顯示錯誤訊息
清除後可選擇性重整匯入歷史列表
```

**4-d. 實作 `clearVendorBooks()` function**

```
if (!pid) { 顯示錯誤「請先選擇採購專案」; return }
if (!confirm('確定要清除目前專案的書商書單？此操作無法復原。選書紀錄將保留。')) return
const input = prompt('請輸入「清除」以確認：')
if (input !== '清除') return
呼叫 DELETE /api/imports/vendor-books?project_id={pid}
成功：顯示刪除摘要（deleted_vendor_books、preserved_selection_items 等）
失敗：顯示錯誤訊息
清除後可選擇性重整匯入歷史列表
```

### 步驟 5：驗證

**5-a. 語法驗證**

```
python -m compileall app
```

**5-b. 資料流驗證（手動或臨時腳本）**

建立測試資料：
- 匯入館藏
- 匯入書商書單（某個 project）
- 加入至少一筆選書（`selection_items`）

清館藏後驗證：
- `SELECT COUNT(*) FROM library_holdings` → 0
- 引用 `holding_id` 的 `book_matches` → 0
- `batch_type='library_holdings'` 的 `import_batches` → 0

清書商書單後驗證：
- 該 project 的 `vendor_books` → 0
- `batch_type='vendor_books'` 的 `import_batches` → 0
- `selection_items` WHERE `project_id=?` → 保留原有筆數
- `GET /api/selections/?project_id=?` → 仍回傳已選書
- `get_selection_summary()` → 仍正確
- `check_export_readiness()` → 可執行
- 若 export template 存在，`export_local_culture()` → 可執行

**5-c. 手動 UI 驗證**

1. 登入。
2. 進入匯入頁，按「清除學校館藏」。
3. 雙重確認流程正確（第二次輸入錯誤應中止）。
4. 觀察成功後顯示的刪除摘要。
5. 按「清除目前專案書商書單」（需先選定 project）。
6. 確認選書列表不消失。

## 風險與注意事項

- `_clear_library_holdings` 尚未存在，需新增；`_clear_vendor_books_for_project` 已存在，直接複用。
- helper 不得自行 commit；service function 負責完整 transaction（commit / rollback / close）。
- 清館藏後即時比對結果失效是預期行為，文件與提示應告知使用者。
- 不得使用 `DELETE FROM selection_items`。
- 前端雙重確認文字必須清楚區分「來源資料」（可清除）與「選書紀錄」（保留）。
- `DELETE /vendor-books` 路由名稱與 `POST /vendor-books` 相同但 method 不同，FastAPI 可共存；實作時注意 route 順序不干擾。

## 預計影響範圍

- `app/services/import_service.py`：新增 `_clear_library_holdings`、`clear_library_holdings`、`clear_vendor_books`（約 60–80 行）。
- `app/routers/imports.py`：新增 2 個 DELETE 路由、更新 import（約 20 行）。
- `app/static/import.html`：新增 2 個按鈕與 2 個 JS function（約 50–70 行）。
- 不修改資料庫 schema。
- 不影響現有 POST 路由與 selection / export 功能。

## 驗證指令

- lint: 無既有 lint 設定；以 `python -m compileall app` 替代
- format: 無既有 format 設定
- typecheck: 無既有 typecheck 設定
- test: `python -m compileall app`
- build: 無 build 步驟（直接執行 FastAPI）

## 成果報告

- result_report_mode: none
- 適用情境：本 task 為功能修補，不需產生成果報告
