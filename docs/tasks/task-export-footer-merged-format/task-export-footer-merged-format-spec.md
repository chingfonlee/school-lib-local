# Spec: task-export-footer-merged-format

## 目標

修正一般圖書採購匯出 Excel 時，選書筆數超過範本最大列數（50 筆）後，尾端備註列與簽核列的合併儲存格格式未正確保留的問題。

## 問題描述

### 重現條件

一般圖書採購（`general_books` / `general_books_jh`）或本土文化採購匯出時，可匯出書目數量超過 `max_rows`（目前為 50），觸發 `_extend_data_rows` 在合計列前插入額外資料列。

### 根本原因

`app/services/export_service.py` 中，`_extend_data_rows(ws, template_row, insert_at, extra_rows)` 的執行順序如下：

1. `ws.insert_rows(insert_at, extra_rows)` — 插入額外列；openpyxl 的此方法會位移儲存格資料，但**不更新 `ws.merged_cells.ranges` 的行號**（現有測試 `test_extend_data_rows_unmerges_ranges_that_overlap_inserted_data_rows` 的斷言已確認此行為）。
2. `_unmerge_ranges_overlapping_rows(ws, insert_at, last_inserted_row)` — 移除插入區間內的合併範圍。

因 footer 的合併範圍（備註列、簽核列）在 `insert_rows` 後仍停留於舊行號，若 `extra_rows >= 2`，舊行號即落入插入區間 `[insert_at, insert_at + extra_rows - 1]`，造成 `_unmerge_ranges_overlapping_rows` 誤刪 footer 合併範圍。最終匯出 Excel 中，備註與簽核文字被擠在單一儲存格，合併格式消失。

### 已知範本 footer 結構（範圍為近似值，依實際範本為準）

| 範本類型 | 備註列合併範圍 | 簽核列合併範圍 |
|---|---|---|
| 國小一般圖書 | `B57:L57`（或類似） | `A58:L58`（或類似） |
| 國中一般圖書 | `A57:L57`（或類似） | `A58:L58`（或類似） |

## 需求範圍

### 修正 `_extend_data_rows`

**邊界定義**

| 合併範圍類型 | 判斷條件 | 處理方式 |
|---|---|---|
| Footer 範圍 | `min_row >= insert_at` | 插列前保存並移除；插列後以 `+extra_rows` 重建 |
| 資料區廢棄範圍 | `min_row < insert_at` 且 `max_row < insert_at` | 不動（`_unmerge_ranges_overlapping_rows` 不會觸及） |
| 跨越插入點 | `min_row < insert_at` 且 `max_row >= insert_at` | **不保存、不重建**；視為資料區範圍，由 `_unmerge_ranges_overlapping_rows` 移除。目前範本不應出現此情況，若出現則保守移除。 |

**執行步驟**

- 插列前，擷取所有 `min_row >= insert_at` 的合併範圍（footer 區塊），並從 `ws.merged_cells` 移除（同時清理 `ws._cells` 中對應的 `MergedCell` 物件），避免 `_unmerge_ranges_overlapping_rows` 誤判。
- 插列後，將暫存的合併範圍以 `+extra_rows` 行號位移重建（呼叫 `ws.merge_cells`）。

### 不改變的行為

- 插入資料列區間內的廢棄合併範圍仍由 `_unmerge_ranges_overlapping_rows` 處理，邏輯不變。
- 插入資料列的樣式複製（`_copy_row_style`）邏輯不變。
- `export_local_culture` 與 `export_general_books` 呼叫 `_extend_data_rows` 的介面不變。

### 測試新增（`tests/test_export_row_extension.py`）

- footer 合併範圍在插列後正確位移至新行號，不被刪除。
- 位移量等於 `extra_rows`（`min_row + extra_rows`、`max_row + extra_rows`）。
- 同一插列作業中有多個 footer 合併範圍（備註 + 簽核）時均正確處理。
- 超出插入區間的 footer 合併範圍同樣正確位移（驗證舊測試斷言因行為修正而需更新）。
- `extra_rows=0` 時，footer 合併範圍不變。

## 不做的事

- 不修改 Excel 範本檔。
- 不重構整個 export service（只修改 `_extend_data_rows` 及其相關 helper）。
- 不改匯出欄位 mapping、欄位順序或計算邏輯。
- 不改匯出前檢查邏輯（`validation_service.py`）。
- 不處理選書頁 UI。
- 不處理 `export_local_culture` / `export_general_books` 以外的匯出路徑。
- 不引入新的 dependency 或安裝新的工具。

## 驗收條件

1. 一般圖書採購匯出（`general_books` / `general_books_jh`）書目超過 50 筆時，匯出的 xlsx 中備註列與簽核列仍保有合併儲存格（橫向合併），格式與範本一致。
2. 書目不超過 50 筆（`extra_rows = 0`）時，現有匯出行為不受影響。
3. `pytest tests/test_export_row_extension.py -q` 全數通過（含新增與更新的測試案例）。
4. `pytest tests/ -q` 全數通過（不引入回歸）。
5. 不依賴實際範本檔案，測試以 openpyxl in-memory Workbook 建構。
