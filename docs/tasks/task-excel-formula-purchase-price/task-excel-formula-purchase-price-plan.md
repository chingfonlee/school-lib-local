# Plan: task-excel-formula-purchase-price

## 實作步驟

1. 在 `app/services/import_service.py` 的 `_to_float` 之後新增三個 helper 函式：

   **`_parse_formula_multiplier(formula: str) -> float | None`**
   - 用 regex `\*\s*(\d+(?:\.\d+)?)\s*%` 從公式提取百分比數字
   - 回傳 `float(N) / 100`；無符合則回傳 `None`

   **`_resolve_formula_purchase_price(formula: str, list_price: float | None) -> float | None`**
   - 若 `list_price` 為 None 或公式提不出乘數，回傳 None
   - 若公式（大小寫不分）含 `ROUND`，回傳 `float(round(list_price * multiplier))`
   - 否則回傳 `list_price * multiplier`

   **`_build_formula_fallback(file_bytes: bytes, sheet, header_row: int, pp_src_col: str) -> dict[int, str]`**
   - 用 `openpyxl.load_workbook(data_only=False, read_only=True)` 開啟
   - 讀標題列（Excel 1-based：`header_row + 1`）定位 `pp_src_col` 欄的欄號
   - 從資料起始列（`header_row + 2`）逐列讀該欄，收集以 `=` 開頭的儲存格
   - 回傳 `{data_row_0based: formula_string}`（key = `cell.row - (header_row + 2)`）
   - 所有例外靜默捕捉（`except Exception: return {}`）

2. 修改 `confirm_import`（覆蓋 preview → confirm 兩步驟匯入路徑）：
   - 在 `pd.read_excel` 之前，若 `engine == "openpyxl"` 且 `mappings.get("purchase_price")` 有值，
     呼叫 `_build_formula_fallback(file_bytes, sheet, header_row, mappings["purchase_price"])`
     取得 `pp_formula_map`（否則為空 dict）
   - 迴圈中，先分開計算：
     ```python
     list_price = _to_float(get_field("list_price"))
     purchase_price = _to_float(get_field("purchase_price"))
     if purchase_price is None and list_price is not None:
         formula = pp_formula_map.get(enum_idx)
         if formula:
             purchase_price = _resolve_formula_purchase_price(formula, list_price)
     ```
   - `book` dict 改用已解析的 `list_price` 與 `purchase_price` 變數

3. 修改 `import_vendor_books`（覆蓋舊版單步驟匯入路徑）：
   - `for _, row in df.iterrows()` 改為 `for enum_idx, (_, row) in enumerate(df.iterrows())`
   - 建立 `reverse_map` 後，若 `reverse_map.get("purchase_price")` 有值，
     呼叫 `_detect_header_row(file_bytes, "openpyxl", VENDOR_COLUMN_HINTS)` 取得 `detected_header_row`，
     再呼叫 `_build_formula_fallback(file_bytes, 0, detected_header_row, reverse_map["purchase_price"])`
     取得 `pp_formula_map`
   - 迴圈中補上與 `confirm_import` 相同的 formula fallback 邏輯

4. 執行驗證（見驗證指令）

## 風險與注意事項

- `_build_formula_fallback` 額外讀一次 Excel 檔；對本土書單大小（數百列）可接受
- `_detect_header_row` 在 `import_vendor_books` 路徑中被呼叫兩次（均只讀 20 列），可接受
- 若公式欄位參照不是同列的 list_price（如跨列加總），regex 可能提到無意義的乘數；
  目前確認的公式格式均為 `=ROUND(Gx*75%,0)`，風險低；即使算錯，欄位仍有值，比 null 好
- `.xls` 格式不受本次修正影響

## 預計影響範圍

- `app/services/import_service.py`：新增 3 個 helper 函式，修改 `confirm_import` 與 `import_vendor_books`
- 不影響其他 Python 檔案、DB schema、API 規格或前端

## 驗證指令

- lint: 無
- format: 無
- typecheck: 無
- test: 無
- build: `python -m compileall app`

## 成果報告

- result_report_mode: none
- 適用情境：不需
- 報告路徑（若 mode 非 none）：無
