# Spec: task-export-include-incomplete

## 目標

已加入選書清單的書目，無論欄位是否完整，匯出時均應寫入 Excel，缺少的欄位留空。  
若使用者認為某本書不應採購，應在選書頁將其從選書清單移除，而非依賴匯出邏輯排除。

## 問題現象

目前 `export_local_culture()` 與 `export_general_books()` 在匯出前會呼叫 `check_export_readiness()`，若有任何書目缺少必填欄位（書名、定價、ISBN 等），後端拋出 `ValueError`，前端收到 400 錯誤，整批匯出失敗。  
使用者無法匯出含缺填書目的選書清單，即使其餘書目均已完整。

## 使用者期望行為

1. 點擊「繼續匯出」→「執行匯出」，所有已選書目均寫入 Excel。
2. 欄位有值者正常填入；欄位缺失者對應儲存格留空（`None`）。
3. 匯出前檢查頁仍顯示缺填警告，讓使用者知悉缺填狀況，但不阻擋匯出。
4. 缺填書目不應在匯出時被自動排除；移除書目的操作應在選書頁進行。

## 需求範圍

### 後端

- 移除 `export_local_culture()` 開頭的 `blocking` 檢查與 `raise ValueError`。
- 移除 `export_general_books()` 開頭的 `blocking` 檢查與 `raise ValueError`。
- `check_export_readiness()` 與 `validation_service.py` 邏輯不變（`can_export` 欄位供前端顯示用，仍正確計算）。
- SQL 查詢已涵蓋 `available`、`missing_isbn`、`invalid_isbn` 三種比對狀態，不需修改。
- `already_owned`（已館藏）書目仍不寫入 Excel，現有行為維持不變。

### 前端（export-check.html）

- `renderHint()` 在 `missing_required > 0` 時：
  - 按鈕改回 `btn-primary`（移除 `btn-danger`，不再暗示阻擋）
  - 提示文字改為「有 N 本書缺少必填欄位，匯出後對應欄位將留空」
  - alert 訊息改為說明性提醒，不說「自動排除」

## 不做的事

- 不修改 `check_export_readiness()` 或 `validation_service.py` 的計算邏輯。
- 不修改 `already_owned` 的排除行為（已館藏書目仍不匯出）。
- 不修改選書頁（selection.html）的任何功能。
- 不修改匯出 Excel 的欄位格式或樣板。
- 不加入「強制填入預設值」邏輯，缺填欄位一律留空。

## 驗收條件

1. 選書清單中含缺填書目時，點擊「執行匯出」可成功產生 Excel，不出現 400 錯誤。
2. 缺填書目寫入 Excel，缺失欄位對應儲存格為空白。
3. 完整書目的欄位正常填入，不受影響。
4. `already_owned` 書目仍不寫入 Excel。
5. `export-check.html` 顯示缺填書目數量警告，但按鈕為 `btn-primary`，提示文字說明「欄位將留空」而非「將排除」。
6. 無缺填書目時，匯出前檢查與匯出行為與現在相同。
7. `python -m compileall app` 通過。
