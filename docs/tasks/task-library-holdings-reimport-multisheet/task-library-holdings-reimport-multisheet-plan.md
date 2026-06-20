# Plan: task-library-holdings-reimport-multisheet

## 實作步驟

### 步驟 1：新增 `_list_excel_sheets(file_bytes, engine)` helper

位置：`app/services/import_service.py`，在 `_detect_header_row()` 之前。

抽出 `preview_excel()` 中現有的 sheet 列舉邏輯（openpyxl 用 `wb.sheetnames`，xlrd 用 `wb.sheet_names()`），回傳 `list[str]`。

### 步驟 2：新增 `_clear_library_holdings(conn)` helper

位置：緊接在 `_clear_vendor_books_for_project()` 之後。

清除邏輯（不 commit，呼叫者負責 transaction）：

1. 查詢 `SELECT id FROM import_batches WHERE batch_type='library_holdings'`，取得所有舊 batch ID。
2. 若無舊批次，直接 return。
3. 刪除 `book_matches WHERE holding_id IN (SELECT id FROM library_holdings WHERE batch_id IN (...))`。
4. 刪除 `library_holdings WHERE batch_id IN (...)`。
5. 刪除 `import_batches WHERE id IN (...)`。

注意：`library_holdings.id` 被 `book_matches.holding_id` 外鍵參照，`get_connection()` 已啟用 `PRAGMA foreign_keys = ON`，刪除順序必須先刪 `book_matches` 才能刪 `library_holdings`。

### 步驟 3：新增 `_read_library_sheet(file_bytes, engine, sheet_name)` helper

回傳 `tuple[pd.DataFrame, dict, list] | None`：

- 呼叫 `_read_excel_with_detected_header(file_bytes, engine, LIBRARY_COLUMN_HINTS, sheet_name=sheet_name)`，標準化欄位名稱（`str(c).strip()`）
- 呼叫 `_match_columns(list(df.columns), LIBRARY_COLUMN_HINTS)` 取得 `(mapping, unmapped)`
- 有效性判斷：`mapping` 的 values 中包含 `"isbn"` 或 `"title"` 至少一個才算有效
- 有效時回傳 `(df, mapping, unmapped)`；無有效欄位時回傳 `None`（表示略過此 sheet）

### 步驟 4：新增 `_insert_library_holding_rows(conn, batch_id, df, mapping)` helper

回傳 `int`（插入筆數）。

抽出目前 `import_library_holdings()` 中的 row 迭代與 INSERT 邏輯：

- 建立 `reverse_map = {v: k for k, v in mapping.items()}`
- 逐列判斷 `_is_blank_or_total_row`，略過空白與合計列
- 執行 `INSERT INTO library_holdings(...) VALUES (...)`
- 回傳 `records_inserted`

### 步驟 5：改寫 `import_library_holdings()`

新流程：

```
1. 判斷 engine（xlrd / openpyxl）
2. 呼叫 _list_excel_sheets(file_bytes, engine) 取得 sheets 清單
3. 建立 conn = get_connection()
4. try：
   a. _clear_library_holdings(conn)（清除舊館藏，不 commit）
   b. INSERT import_batches（project_id=NULL，batch_type='library_holdings'，不含 record_count）
   c. records_inserted = 0
      sheet_summaries = []
      skipped_sheets = []
      last_mapping = {}
      last_unmapped = []
   d. 逐 sheet：
      - result = _read_library_sheet(file_bytes, engine, sheet_name)
      - 若 result is None：skipped_sheets.append({"sheet_name": sheet_name, "reason": "無 isbn 或 title 欄位"})；continue
      - df, mapping, unmapped = result
      - 若有 column_overrides：mapping.update(column_overrides)
      - n = _insert_library_holding_rows(conn, batch_id, df, mapping)
      - records_inserted += n
      - sheet_summaries.append({"sheet_name": str(sheet_name), "record_count": n})
      - last_mapping, last_unmapped = mapping, unmapped
   e. 零有效匯入保護：
      - 若 records_inserted == 0：raise ValueError("館藏檔案未匯入任何有效資料，請確認 Excel 格式")
      - 此 raise 會被 except 捕捉並 rollback，舊館藏維持不變
   f. UPDATE import_batches SET record_count = records_inserted WHERE id = batch_id
   g. conn.commit()
5. except Exception：conn.rollback()；raise
6. finally：conn.close()
7. 回傳：
   {
     "batch_id": batch_id,
     "replaced": True,
     "record_count": records_inserted,
     "sheet_summaries": sheet_summaries,
     "skipped_sheets": skipped_sheets,
     "unmapped_fields": last_unmapped,
     "column_mapping": last_mapping,
   }
```

`unmapped_fields` 與 `column_mapping` 取最後一個有效 sheet 的結果（維持現有 API 向後相容）。

### 步驟 6：修改 `app/static/import.html` 的 `uploadHoldings()` 函式

將現有成功訊息區塊替換為：

```javascript
const replaced = result.replaced ? '已覆蓋既有館藏，' : '';
let sheetInfo = '';
if (result.sheet_summaries && result.sheet_summaries.length > 1) {
  sheetInfo = '<br>各工作表：' + result.sheet_summaries
    .map(s => `${s.sheet_name}（${s.record_count} 筆）`).join('、');
}
let skippedInfo = '';
if (result.skipped_sheets && result.skipped_sheets.length) {
  skippedInfo = '<br>略過工作表：' + result.skipped_sheets
    .map(s => s.sheet_name).join('、');
}
el.innerHTML = `
  <div class="alert alert-success">
    ✓ ${replaced}共 <strong>${result.record_count}</strong> 筆
    ${result.unmapped_fields && result.unmapped_fields.length
      ? `<br>未對應欄位：${result.unmapped_fields.join('、')}` : ''}
    ${sheetInfo}${skippedInfo}
  </div>`;
```

### 步驟 7：DB migration

不需要。覆蓋策略在應用層實作（先刪後插），不依賴 UNIQUE constraint。現有 schema 已足夠。

### 步驟 8：匯入後自動重新比對（auto-match）

**8a. `import_library_holdings()` 尾端補充（在 `conn.close()` 之後）**

```python
match_rerun = False
affected_projects = []
match_stats_by_project = {}
try:
    conn2 = get_connection()
    project_ids = [
        r[0] for r in conn2.execute(
            "SELECT DISTINCT project_id FROM import_batches "
            "WHERE batch_type='vendor_books' AND project_id IS NOT NULL"
        ).fetchall()
    ]
    conn2.close()
    for pid in project_ids:
        stats = run_match(pid)
        affected_projects.append(pid)
        match_stats_by_project[str(pid)] = stats
    match_rerun = bool(affected_projects)
except Exception as e:
    result["match_rerun_error"] = str(e)
```

回傳 dict 新增：`match_rerun`、`affected_projects`、`match_stats_by_project`（以及可能的 `match_rerun_error`）。

**8b. `confirm_import()` 尾端補充**

```python
match_rerun_error = None
try:
    match_stats = run_match(project_id)
except Exception as e:
    match_stats = None
    match_rerun_error = str(e)
```

回傳 dict 新增：`match_stats`（以及可能的 `match_rerun_error`）。

**8c. `import_vendor_books()` 尾端補充**（legacy path，同 8b 邏輯）

**8d. `import` 語句**

在 `app/services/import_service.py` 頂部 import 區新增：

```python
from app.services.match_service import run_match
```

### 步驟 9：修改 `app/static/import.html` — 自動比對結果顯示

**9a. `uploadHoldings()` 成功訊息補充**

在現有 sheetInfo / skippedInfo 之後，依 `result.affected_projects` 與 `result.match_rerun_error` 條件插入：

```javascript
let matchInfo = '';
if (result.match_rerun_error) {
  matchInfo = `<br><span class="text-warning">⚠ 匯入成功，但自動比對失敗，請到比對頁手動重新比對。</span>`;
} else if (result.affected_projects && result.affected_projects.length) {
  matchInfo = `<br>已重新執行比對（${result.affected_projects.length} 個書單專案）`;
}
```

**9b. confirm_vendor_books 的成功訊息補充**（`uploadVendorBooks()` 函式）

在現有「✓ 匯入完成：共 N 筆」後，依 `result.match_stats` 插入：

```javascript
let matchSummary = '';
if (result.match_rerun_error) {
  matchSummary = `<br><span class="text-warning">⚠ 匯入成功，但自動比對失敗，請到比對頁手動重新比對。</span>`;
} else if (result.match_stats) {
  matchSummary = `<br>可採購 <strong>${result.match_stats.available ?? 0}</strong> 筆・已館藏 <strong>${result.match_stats.already_owned ?? 0}</strong> 筆`;
}
```

## 風險與注意事項

1. **FK 刪除順序**：`book_matches.holding_id` 外鍵參照 `library_holdings.id`，`PRAGMA foreign_keys = ON` 有效時，必須先刪 `book_matches` 才能刪 `library_holdings`，否則觸發 FK 違反。`_clear_library_holdings()` 中已明確依序刪除。

2. **Transaction 邊界**：Python `sqlite3` 在 DML 前隱式 BEGIN，所有 `_clear_library_holdings` 的刪除與後續 INSERT 都在同一 `conn` 未 commit 前屬同一 transaction，`rollback()` 可完整還原。呼叫 `conn.commit()` 只執行一次（步驟 4f），不在 helper 內提前 commit。

3. **`_list_excel_sheets` 與後續讀取各自開啟 BytesIO**：對學校館藏 xls/xlsx 規模（通常 < 10MB）可接受，不需特別優化。

4. **有效 sheet 但資料列為 0**：sheet 存在 `isbn` 或 `title` 欄位但所有列均被 `_is_blank_or_total_row` 略過時，`sheet_summaries` 中仍會出現該 sheet（`record_count: 0`），不單獨報錯。但所有 sheet 加總後若 `records_inserted == 0`，會觸發零有效匯入保護（步驟 4e），整體 rollback。

5. **零有效匯入保護的邏輯位置**：保護檢查在 `conn.commit()` 之前、`UPDATE import_batches` 之前執行（步驟 4e）。raise 後被 except 捕捉，conn.rollback() 將本次 clear 與所有 INSERT 一併還原，舊館藏完整保持。

6. **`column_overrides` 套用至所有 sheet**：若使用者提供 `column_overrides`，會套用至每個有效 sheet 的 `mapping`，維持現有行為，不做 per-sheet 個別設定。

## 預計影響範圍

- `app/services/import_service.py`：新增 4 個 helper（`_list_excel_sheets`、`_clear_library_holdings`、`_read_library_sheet`、`_insert_library_holding_rows`），改寫 `import_library_holdings()`，共約 +60 / -20 行
- `app/static/import.html`：修改 `uploadHoldings()` 約 10 行
- `app/routers/imports.py`：不修改（API 輸入格式不變，回傳格式向後擴充）
- 無 migration 檔案變更

## 驗證指令

- lint: 無既有 linter 設定；以 `python -m compileall app` 確認語法無誤
- format: 無既有 formatter 設定；目視確認縮排一致（4 空格）
- typecheck: 無既有 mypy 設定；跳過
- test: 手動驗證（見下方「手動驗證方式」）
- build: `python -c "import app.services.import_service"` 確認模組可正常匯入

### 手動驗證方式

**測試資料準備**

若無現有館藏 Excel，自行建立最小測試檔案：

`test_holdings_single.xlsx`（1 個有效 sheet，含 isbn 和 title 欄位，3 筆資料）

`test_holdings_multisheet.xlsx`（3 個 sheet）：

- Sheet1：含 isbn、title 欄位，2 筆資料
- Sheet2：含 isbn、title 欄位，3 筆資料
- Sheet3：欄位為「說明」、「注意事項」，無 isbn 或 title（預期略過）

**驗證步驟**

1. 匯入 `test_holdings_single.xlsx`，確認 `library_holdings` 筆數 = 3。
2. 再次匯入 `test_holdings_single.xlsx`，確認 `library_holdings` 筆數仍 = 3（不翻倍）。
3. 確認 `SELECT COUNT(*) FROM import_batches WHERE batch_type='library_holdings'` = 1（只剩最新批次）。
4. 匯入 `test_holdings_multisheet.xlsx`：
   - 確認 `library_holdings` 筆數 = 5（Sheet1 的 2 + Sheet2 的 3）。
   - 確認 API 回傳 `sheet_summaries` 含 2 個有效 sheet，筆數各正確。
   - 確認 API 回傳 `skipped_sheets` 含 Sheet3 及略過原因。
   - 確認前端訊息顯示各 sheet 筆數與略過 sheet 名稱。
5. 建立 `test_holdings_nodata.xlsx`（所有 sheet 欄位均為「說明」、「注意事項」，無 isbn/title），匯入後確認 API 回傳 HTTP 400 錯誤，且 `library_holdings` 筆數維持匯入前狀態（不被清空）。
6. 匯入後執行館藏查詢（`/holdings.html`），確認可正常搜尋到剛匯入的資料。
7. 若有現有 vendor_books，重新執行書單比對，確認 `book_matches` 可重新產生，無 FK 錯誤或殘留舊 match 問題。

## 成果報告

- result_report_mode: none
- 適用情境：內部修正，不需對外報告
- 報告路徑（若 mode 非 none）：`docs/reports/task-library-holdings-reimport-multisheet/`
