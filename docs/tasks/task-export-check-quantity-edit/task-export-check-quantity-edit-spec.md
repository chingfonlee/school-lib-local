# Spec: task-export-check-quantity-edit

## 目標

使用者在「匯出前檢查」頁（export-check.html）可以為每本已選書目個別修改採購數量，修改後即時反映於預算摘要、匯出前檢查狀態與 Excel 匯出內容。

## 需求範圍

### 使用者行為

- 使用者在 export-check.html 的已選書目表格中，每列可見一個數量輸入欄（number input）。
- 初始值為該 selection 的 `selected_quantity`（預設 1）。
- 使用者修改數量後觸發即時更新（`change` 事件）。
- 更新成功後重新呼叫 `runCheck()`，刷新：
  - 匯出前檢查統計與詳細表格
  - 預算摘要（金額 × 數量）
  - 匯出提示文字
- 更新失敗時以 `showToast()` 顯示錯誤，並呼叫 `runCheck()` 還原畫面資料。

### 數量驗證規則

- 數量必須是整數且 >= 1。
- 數量 = 0、負數、非整數均不合法，API 應回傳 422。
- 移除書目仍由「移除」按鈕（`DELETE /api/selections/{id}`）處理，不在此功能範圍內。

### API

- 新增 `PATCH /api/selections/{selection_id}/quantity`。
- Request body：`{ "quantity": <int> }`。
- 成功回傳：`{ "selection_id": <id>, "selected_quantity": <quantity> }`。
- `selection_id` 不存在回 404。
- 數量不合法回 422。

### Service

- 新增 `update_selection_quantity(selection_id: int, quantity: int, user_id: int) -> dict`。
- 只更新 `selected_quantity` 與 `updated_at`。
- 不修改 `notes`。
- 不修改 `user_overrides`。
- `selection_id` 不存在時 `raise ValueError`。

### 資料庫

- 不做 DB migration（`selection_items.selected_quantity` 欄位已存在）。

### 匯出

- 不更改 Excel 匯出格式或邏輯；`selected_quantity` 本已用於計算數量與小計，更新後自動反映。

## 不做的事

- 不修改選書頁加入書本行為（仍預設 quantity=1）。
- 不把 quantity=0 視為移除（移除仍由 DELETE 端點處理）。
- 不更動 `notes`、`user_overrides` 的現有行為。
- 不做 DB migration。
- 不改 Excel 匯出欄位結構。
- 不重構不相關流程或檔案。

## 驗收條件

1. `PATCH /api/selections/{id}/quantity` body `{"quantity": 3}` 可成功將 `selected_quantity` 從 1 更新為 3。
2. PATCH 不清空 `notes`，不清空 `user_overrides`。
3. PATCH `quantity=0`、`quantity=-1`、非整數均回 422。
4. PATCH `selection_id` 不存在回 404。
5. export-check.html 表格每列顯示數量 input，初始值與 `selected_quantity` 一致。
6. 修改數量後，預算摘要金額正確反映（金額 × 新數量）。
7. 匯出 Excel 後數量欄與小計欄顯示更新後數量。
8. 輸入非法值（0、負數）時 UI 不寫入，並顯示錯誤提示。
