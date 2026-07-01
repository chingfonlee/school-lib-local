# Plan: task-export-footer-merged-format

## 實作步驟

### 1. 閱讀現有程式行為（已完成於 Phase A）

- `_extend_data_rows(ws, template_row, insert_at, extra_rows)` 的執行順序：
  1. `ws.insert_rows(insert_at, extra_rows)` — 位移儲存格資料；openpyxl 不更新 `ws.merged_cells.ranges` 行號
  2. `_unmerge_ranges_overlapping_rows(ws, insert_at, last_inserted_row)` — 移除插入區間內的合併範圍
  3. `_copy_row_style(ws, template_row, insert_at, last_inserted_row)` — 複製樣式至新列
- Footer 合併範圍（`min_row >= insert_at`）在 step 1 後仍停留舊行號，`extra_rows >= 2` 時會落入 step 2 的掃描區間而被誤刪。

### 2. 新增 helper：插列前擷取並移除 footer 合併範圍

新增 `_pop_footer_merged_ranges(ws, insert_at)` 於 `_extend_data_rows` 之前（私有 helper）：

- 掃描 `ws.merged_cells.ranges`，找出所有 `min_row >= insert_at` 的範圍（footer 邊界，見 spec 邊界定義）。
- 跨越插入點（`min_row < insert_at` 且 `max_row >= insert_at`）的範圍**不保存**，由後續 `_unmerge_ranges_overlapping_rows` 處理。
- 對每個要保存的範圍：
  - 先 `copy()` 取得快照
  - 呼叫 `ws.merged_cells.remove(range)` 移除範圍記錄
  - 清理 `ws._cells` 中該範圍 non-master 格的 `MergedCell` 物件（同 `_unmerge_ranges_overlapping_rows` 的做法）
- 回傳 `list[tuple[int, int, int, int]]`，每項為 `(min_row, min_col, max_row, max_col)`。

### 3. 新增 helper：插列後重建位移後的 footer 合併範圍

新增 `_push_footer_merged_ranges(ws, saved_ranges, extra_rows)` 於 `_copy_row_style` 之後（私有 helper）：

- 對每個 `(min_row, min_col, max_row, max_col)` in `saved_ranges`：
  - 呼叫 `ws.merge_cells(start_row=min_row + extra_rows, end_row=max_row + extra_rows, start_column=min_col, end_column=max_col)`
- 不操作 `ws._cells`（`merge_cells` 自動建立 MergedCell 物件）。

### 4. 修改 `_extend_data_rows`

```python
def _extend_data_rows(ws, template_row, insert_at, extra_rows):
    if extra_rows <= 0:
        return
    saved = _pop_footer_merged_ranges(ws, insert_at)   # 新增：插列前保存
    ws.insert_rows(insert_at, extra_rows)
    last_inserted_row = insert_at + extra_rows - 1
    _unmerge_ranges_overlapping_rows(ws, insert_at, last_inserted_row)
    _copy_row_style(ws, template_row, insert_at, last_inserted_row)
    _push_footer_merged_ranges(ws, saved, extra_rows)  # 新增：插列後重建
```

呼叫介面（`export_local_culture`、`export_general_books`）不變。

### 5. 更新既有測試 `test_extend_data_rows_unmerges_ranges_that_overlap_inserted_data_rows`

原測試斷言 `assert "A80:L80" in merged_ranges`，此斷言固定了 openpyxl 的不完整位移行為（footer 範圍停留舊行號）。修正後，`A80:L80`（`min_row=80 >= insert_at=56`）應被保存並位移為 `A83:L83`（`80 + extra_rows=3`）。

更新後的斷言：
- `assert "A57:L57" not in merged_ranges`（插入區內，應被移除）
- `assert "A58:L58" not in merged_ranges`（插入區內，應被移除）
- `assert "A83:L83" in merged_ranges`（`A80` 位移 +3，應保留）

### 6. 新增測試至 `tests/test_export_row_extension.py`

#### 6a. Footer 合併範圍保留並正確位移

```
情境：insert_at=56, extra_rows=5
範本包含備註列合併範圍 B57:L57（min_row=57 >= 56）
         簽核列合併範圍 A58:L58（min_row=58 >= 56）
期望：B62:L62 與 A63:L63 出現在 merged_ranges
      B57:L57 與 A58:L58 不出現（已位移）
```

#### 6b. 多個 footer 合併範圍（國小 + 國中兩種結構均模擬）

```
情境：insert_at=56, extra_rows=10
包含 B57:L57（備註），A58:L58（簽核），B59:G59（其他 footer 元素）
期望：B67:L67、A68:L68、B69:G69 各出現於 merged_ranges
```

#### 6c. extra_rows=0 時 footer 合併範圍不變

```
情境：insert_at=56, extra_rows=0
含 A57:L57
期望：A57:L57 仍在 merged_ranges，無任何位移
```

#### 6d. 跨越插入點的合併範圍不保存（保守移除）

```
情境：insert_at=56, extra_rows=3
包含 A50:L60（min_row=50 < 56，max_row=60 >= 56，跨越插入點）
期望：A50:L60 不在 merged_ranges，也不出現於任何位移後名稱（已由 _unmerge_ranges_overlapping_rows 移除）
```

#### 6e. footer row height 位移行為確認測試

先以測試確認 openpyxl 的 `insert_rows` 是否自動位移 `row_dimensions`：

```
情境：insert_at=56, extra_rows=5
ws.row_dimensions[57].height = 20.0（備註列）
ws.row_dimensions[58].height = 22.0（簽核列）
期望：ws.row_dimensions[62].height == 20.0，ws.row_dimensions[63].height == 22.0
```

- 若測試通過：openpyxl 自動位移，不需額外處理，記錄結果。
- 若測試失敗：openpyxl 不自動位移 footer row height，執行步驟 7 補明確位移邏輯。

### 7. （視步驟 6e 結果決定）補 footer row height 明確位移

若 6e 測試失敗，實作明確搬移 footer row_dimensions：

- 在 `_pop_footer_merged_ranges` 呼叫前，額外保存 `{row: height}` for `ws.row_dimensions` 中 `row >= insert_at` 且有自訂高度的列。
- 在 `_push_footer_merged_ranges` 呼叫後，以 `row + extra_rows` 重設對應 row_dimensions.height。

此步驟在 plan 範圍內，不需額外確認。

## 風險與注意事項

- **`_pop_footer_merged_ranges` 移除 MergedCell 物件時的正確性**：需同 `_unmerge_ranges_overlapping_rows` 的做法（`list(range.cells)[1:]`），只清除 non-master 格，避免殘留舊物件在 insert_rows 後被錯誤位移。
- **`ws.merged_cells.ranges` 迭代中不能邊刪邊改**：需先 list comprehension 收集目標，再迴圈移除。
- **跨越插入點範圍的保守移除**：目前範本不應出現，若出現以移除為安全選項（不重建），不影響資料列正確性。
- **回歸風險**：`_extend_data_rows` 同時被 `export_local_culture` 和 `export_general_books` 使用，兩者都需要驗證。
- **`extra_rows=0` 路徑**：函式開頭 `if extra_rows <= 0: return` 已提早退出，新增的 save/restore 邏輯不會執行。

## 預計影響範圍

- `app/services/export_service.py`：新增 `_pop_footer_merged_ranges`、`_push_footer_merged_ranges`；修改 `_extend_data_rows`（約 +20 行）。視步驟 7 結果，可能增加 row height 位移邏輯（約 +10 行）。
- `tests/test_export_row_extension.py`：更新 1 個既有測試（`test_extend_data_rows_unmerges_ranges_that_overlap_inserted_data_rows`）；新增 5 個測試（6a–6e）。
- 不影響 `export_local_culture`、`export_general_books` 的呼叫介面。
- 不影響其他 service（`validation_service`、`selection_service`）。

## 驗證指令

- test：`pytest tests/test_export_row_extension.py -q`
- regression：`pytest tests/ -q`

## 成果報告

- result_report_mode: none
