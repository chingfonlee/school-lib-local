# Spec: task-export-check-edit

## 目標

在「匯出前檢查」頁（`export-check.html`）的書單表格中，對每本書新增「移除」與「修正」操作，讓使用者可直接在此頁處理缺填書目，無需切換回選書頁。

## 問題現象

匯出前檢查頁顯示缺填書目清單，但無法在此直接操作：
- 若書目不打算採購，使用者必須切換到選書頁才能移除。
- 若書目需補填欄位，使用者必須切換到選書頁才能修正。
- 在有 6750 筆書目的一般圖書採購中，切換回選書頁再找到該書需要額外步驟。

## 使用者期望行為

1. 匯出前檢查書單每行有「移除」按鈕：點擊後從選書清單移除該書，表格即時刷新。
2. 匯出前檢查書單每行有「修正」按鈕：展開 inline 修正表單，填入後儲存，表格即時刷新顯示新的完整度狀態。
3. 修正欄位與選書頁一致（書名、作者、出版社、定價、單價、獲獎項目；一般圖書採購加 A/H/L 欄位）。
4. 移除與修正後，統計數字（可匯出、需補資料、不可匯出）自動更新。
5. 既有匯出流程不受影響。

## 需求範圍

### 後端

**`app/services/validation_service.py`**：
- `check_export_readiness()` 的每筆 `details` 補上 `sel_id`（即 `selection_items.id`）。

**`app/services/selection_service.py`**：
- 新增 `remove_selection(selection_id: int) -> dict`：刪除單筆 `selection_items` 記錄。

**`app/routers/selections.py`**：
- 新增 `DELETE /api/selections/{selection_id}` endpoint，呼叫 `remove_selection()`。

### 前端（`app/static/export-check.html`）

- 頁面載入時，同時取得 `selData`（已有）並建立 `bookDataMap[vendor_book_id] = selData.items[i]`，供修正表單預填使用。
- 取得 `proj.project_type`，存為 `projectType`，供修正表單決定是否顯示 A/H/L 欄位。
- 表格新增「操作」欄，每行顯示：
  - **移除**：呼叫 `DELETE /api/selections/{sel_id}`，成功後重跑 `runCheck()`。
  - **修正**：展開 inline 表單，欄位與 `selection.html` 的「修正資料」一致；儲存呼叫 `/api/books/{vendor_book_id}/overrides`（PATCH）與 `/api/selections/{sel_id}/overrides`（PATCH），成功後重跑 `runCheck()`。
- `H_ALLOWED` 常數（H 欄合法值清單）複製至 `export-check.html` 供下拉選單使用。

## 不做的事

- 不修改 `check_export_readiness()` 以外的後端 API 回傳格式。
- 不新增「批次移除」或「批次修正」功能。
- 不修改選書頁（`selection.html`）的任何邏輯。
- 不修改 `already_owned` 書目的顯示或操作（此類書目不在操作範圍內，可隱藏按鈕）。
- 不改變匯出流程或 Excel 輸出格式。
- 不引入新的前端框架或 dependency。

## 驗收條件

1. 匯出前檢查頁的書單表格有「操作」欄，顯示「移除」與「修正」按鈕。
2. 點「移除」後，該書從清單移除，統計數字即時更新，不需重新整理頁面。
3. 點「修正」後，展開 inline 表單，欄位已預填現有值（包含 override 值）。
4. 修正表單儲存後，表格即時刷新，該書的完整度狀態更新正確。
5. 一般圖書採購的修正表單包含 A 欄（必選/推薦）、H 欄（推薦來源）、L 欄（備註）欄位；本土文化採購不顯示這三個欄位。
6. `already_owned` 書目的操作欄不顯示按鈕（或按鈕 disabled）。
7. 移除 / 修正後，「繼續匯出」按鈕的提示文字隨新的缺填數量正確更新。
8. `python -m compileall app` 通過。
