# Plan: task-export-check-quantity-edit

## 實作步驟

1. 新增 service function（`app/services/selection_service.py`）
   - 加入 `update_selection_quantity(selection_id, quantity, user_id)`
   - 先查詢 `selection_id` 是否存在；不存在則 `raise ValueError`
   - 只更新 `selected_quantity` 與 `updated_at`
   - 回傳 `{"selection_id": selection_id, "selected_quantity": quantity}`

2. 新增 API endpoint（`app/routers/selections.py`）
   - 加入 `QuantityPatch(BaseModel)` with `quantity: int`
   - 加入 `PATCH /api/selections/{selection_id}/quantity`
   - 使用 Pydantic `field_validator` 驗證 `quantity >= 1`（或在 router 層回 422）
   - 匯入並呼叫 `update_selection_quantity`
   - ValueError → 404

3. 更新 export-check.html（`app/static/export-check.html`）
   - `<thead>` 新增「數量」欄（位於「書名」之後，「比對狀態」之前）
   - `renderDetails()` 每列加入 `<td><input type="number" ...></td>` 含 sel_id 對應
   - input 屬性：`min="1"`, `step="1"`, `value="${selQty}"`
   - 數量從 `bookDataMap` 中依 `vendor_book_id` 取 `selected_quantity`；注意 `bookDataMap` 的 key 是 `vendor_book_id`（因 get_selected_books 把 id 設為 vendor_book_id）；`d.sel_id` 是 selection_items.id
   - 新增 `async function patchQuantity(selId, input)` 處理 change 事件
   - 建立 `selIdMap`：key=vendor_book_id → sel_id，用以在 renderDetails 取得 sel_id
   - 驗證 input value 是整數且 >= 1；不合法直接 showToast 並 runCheck()
   - 呼叫 `PATCH /api/selections/${selId}/quantity`
   - 成功 → `runCheck()`；失敗 → `showToast(error)` + `runCheck()`
   - 調整空狀態 `colspan`（由 6 改為 7）
   - 調整 inline edit row `colspan`（由 6 改為 7）

4. 新增測試（`tests/test_selection_quantity.py`）
   - fixture：在 conftest 的 `selection_items` 基礎上插入一筆含 notes 與 user_overrides 的 selection
   - 需為 conftest `_TEST_SCHEMA` 的 `selection_items` 補齊 `notes TEXT`, `user_overrides TEXT`, `updated_at TEXT` 欄位（目前 conftest schema 較精簡）
   - 實際做法：在測試 fixture 中建立完整的 in-memory DB
   - 測試案例：
     - `test_patch_quantity_updates_selected_quantity`：quantity 1 → 3，驗證回傳與 DB
     - `test_patch_quantity_does_not_clear_notes`：更新後 notes 不變
     - `test_patch_quantity_does_not_clear_user_overrides`：更新後 user_overrides 不變
     - `test_patch_quantity_zero_returns_422`：quantity=0 → 422
     - `test_patch_quantity_negative_returns_422`：quantity=-1 → 422
     - `test_patch_quantity_not_found_returns_404`：不存在 selection_id → 404

## 風險與注意事項

- `bookDataMap` 的 key 是 `vendor_book_id`，但前端 `renderDetails` 用 `d.sel_id`（selection_items.id）呼叫 API；需要另外建立 `selIdMap`（vendor_book_id → sel_id）或直接從 details 中取 sel_id。
  - **選擇**：`runCheck()` 已同時取得 `selData.items`（含 sel_id 與 vendor_book_id），在 renderBudgetSummary 之前建立 `selIdMap`；`renderDetails` 的 `d.sel_id` 即來自 `/api/exports/check` details，直接用即可。
- conftest `_TEST_SCHEMA` 的 `selection_items` 欄位精簡，測試需自建完整 fixture 或擴充 conftest（不擴充 conftest，避免影響其他測試）。
- export-check.html 加欄後，colspan 需同步調整，否則空狀態行與 inline edit 行版面錯位。

## 預計影響範圍

- `app/services/selection_service.py`：新增函式，不改既有函式
- `app/routers/selections.py`：新增 model 與 endpoint，不改既有 endpoint
- `app/static/export-check.html`：表格加欄、新增 JS 函式、調整 colspan
- `tests/test_selection_quantity.py`：新增測試檔

## 驗證指令

- lint: 不適用（無 lint 設定）
- format: 不適用（無 formatter 設定）
- typecheck: 不適用（無 mypy 設定）
- test: `.venv/Scripts/python -m pytest tests/test_selection_quantity.py -v`
- 完整測試: `.venv/Scripts/python -m pytest -v`
- build: 不適用

## 成果報告

- result_report_mode: none
