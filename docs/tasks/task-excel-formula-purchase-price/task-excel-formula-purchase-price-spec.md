# Spec: task-excel-formula-purchase-price

## 目標

修正 vendor_books 匯入流程中，Excel 公式欄位（如 `=ROUND(G6*75%,0)`）因 openpyxl `data_only=True`
讀不到快取值，導致 `purchase_price` 全為 null 的問題。匯入後 `vendor_books.purchase_price` 應有從
`list_price` 計算出的數值。

## 需求範圍

- `app/services/import_service.py`：
  - 新增 `_parse_formula_multiplier(formula)` — 從公式字串提取乘數（如 `75%` → `0.75`）
  - 新增 `_resolve_formula_purchase_price(formula, list_price)` — 計算補值，支援 `ROUND` 與直接乘
  - 新增 `_build_formula_fallback(file_bytes, sheet, header_row, pp_src_col)` — 以 openpyxl
    `data_only=False` 讀公式字串，按標題行定位 purchase_price 欄，回傳 `{data_row_0based: formula_string}`
  - 修改 `confirm_import`：當 `purchase_price` 為 null 時，透過公式 fallback 計算補值
  - 修改 `import_vendor_books`：同上，同時補上 `enum_idx` 以支援公式 map 查詢

## 支援公式格式

- `=ROUND(ref*N%,0)` — 計算結果為 `round(list_price * N/100)`
- `=ref*N%` — 計算結果為 `list_price * N/100`
- 其他格式：靜默略過（回傳 None），不影響匯入流程

## 不做的事

- 不修改 DB schema（不新增欄位）
- 不修改 API endpoint 或 request/response 格式
- 不修改前端
- 不處理跨工作表參照或 named range 公式
- 不處理 `.xls` 格式（xlrd 不支援 `data_only=False`）

## 驗收條件

1. `python -m compileall app` 無錯誤
2. 匯入本土書單（`.xlsx`，H 欄為 `=ROUND(G列*75%,0)` 類公式）後，`vendor_books.purchase_price` 有非 null 數值
3. 計算正確：G=700 → H=525（`round(700 * 0.75) = 525`）
4. `/selection.html` 卡片顯示採購單價（如「採購 525」）
5. 若公式格式不符，靜默略過，不拋出例外
