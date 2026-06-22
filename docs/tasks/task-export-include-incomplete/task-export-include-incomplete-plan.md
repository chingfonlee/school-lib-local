# Plan: task-export-include-incomplete

## 實作步驟

### 步驟 1：移除 `export_local_culture()` 的 blocking 檢查

刪除 `app/services/export_service.py` `export_local_culture()` 開頭的這 5 行：

```python
readiness = check_export_readiness(settings.project_id, settings.price_field)
blocking = [d for d in readiness["details"] if not d["can_export"] and d["match_status"] != "already_owned"]
if blocking:
    titles = "; ".join(d["title"] for d in blocking[:5])
    raise ValueError(f"以下書目缺少必填欄位無法匯出：{titles}")
```

### 步驟 2：移除 `export_general_books()` 的 blocking 檢查

同上，刪除 `export_general_books()` 開頭相同的 5 行。

### 步驟 3：更新 `export-check.html` 的 `renderHint()`

將 `missing_required > 0` 分支由：

```js
btn.className = 'btn btn-danger';
hint.textContent = `有 ${d.missing_required} 本書缺少必填欄位，匯出時將排除這些書目`;
alertArea.innerHTML = `<div class="alert alert-error">有 ${d.missing_required} 本書缺少必填欄位（ISBN無效/缺書名/缺定價），匯出時自動排除。請到選書頁填入資料或取消勾選。</div>`;
```

改為：

```js
btn.className = 'btn btn-primary';
hint.textContent = `有 ${d.missing_required} 本書缺少必填欄位，匯出後對應欄位將留空`;
alertArea.innerHTML = `<div class="alert alert-warn">有 ${d.missing_required} 本書缺少必填欄位（ISBN無效/缺書名/缺定價），匯出後對應欄位將留空。若不打算採購這些書目，請至選書頁移除。</div>`;
```

### 步驟 4：執行驗證指令

### 步驟 5：commit

```
fix(task-export-include-incomplete): export all selected books regardless of missing fields
```

## 風險與注意事項

1. **缺定價書目的小計計算**：`_get_price()` 在無法解析價格時回傳 `0.0`，`subtotal = quantity * 0.0 = 0.0`，寫入儲存格時 `subtotal if subtotal else None` 會寫入 `None`（空白）。整體小計加總仍正確（0 不影響加法）。  
   → 不需額外處理，現有邏輯已正確。

2. **`already_owned` 書目**：SQL 查詢的 `WHERE` 子句已用 `IN ('available', 'missing_isbn', 'invalid_isbn')` 過濾，`already_owned` 書目不在查詢結果內，仍不寫入 Excel，現有行為不變。

3. **`check_export_readiness()` 仍被呼叫**：移除 blocking 檢查後，`readiness` 變數不再被使用，可一併移除 `check_export_readiness()` 的呼叫。  
   → 一起刪除，保持函式簡潔，不留廢棄程式碼。

4. **前端 import 路徑**：`export_service.py` 仍從 `validation_service` import `check_export_readiness`，若步驟 3 的移除已無其他呼叫點，需確認 import 是否可一起清除。  
   → `check_export_readiness` 由 `exports.py` router 直接 import 使用（`/api/exports/check` endpoint），export_service 不是唯一使用方；僅移除 export_service 內的呼叫，import 行視情況保留或移除。

## 預計影響範圍

- `app/services/export_service.py`：刪除 10 行（兩處 readiness 呼叫與 blocking 檢查）
- `app/static/export-check.html`：修改 3 行（按鈕 class、hint 文字、alert 內容）
- `app/services/validation_service.py`：不涉及
- `app/routers/exports.py`：不涉及
- 其他頁面：不涉及

## 驗證指令

- lint: 無既有設定
- format: 無既有設定
- typecheck: 無既有設定
- test: 無自動化測試
- build: `python -m compileall app`

## 手動驗證步驟

1. 執行 `python -m compileall app`，確認無錯誤。
2. 啟動本地服務（`start.bat` 或 `python -m uvicorn app.main:app --host 127.0.0.1 --port 8765`）。
3. 以含缺填書目的專案開啟 `export-check.html`：
   a. 確認缺填書目數量顯示正確。
   b. 確認提示文字為「匯出後對應欄位將留空」（非「將排除」）。
   c. 確認按鈕為 `btn-primary`（藍色，非紅色）。
4. 點「繼續匯出」→ 在 `export.html` 執行匯出：
   a. 確認匯出成功，不出現 400 錯誤。
   b. 開啟下載的 Excel，確認缺填書目已寫入，缺失欄位為空白。
   c. 確認完整書目欄位正常填入。
5. 確認 `already_owned` 書目未寫入 Excel（若測試資料有此狀態書目）。
6. 以無缺填書目的選書清單執行匯出，確認行為與現在相同。

## 成果報告

- result_report_mode: none
- 適用情境：不適用
- 報告路徑（若 mode 非 none）：`docs/reports/task-export-include-incomplete/`
