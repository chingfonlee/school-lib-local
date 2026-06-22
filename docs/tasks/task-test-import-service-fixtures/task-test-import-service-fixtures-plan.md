# Plan: task-test-import-service-fixtures

## 實作步驟

### 步驟 0：盤點（已完成）

**import_service.py 函式分類：**

| 函式 | 相依 | 可測方式 |
|------|------|---------|
| `_normalize_header()` | 無 | 純函式，直接呼叫 |
| `_match_columns()` | 無 | 純函式，直接呼叫 |
| `_is_blank_or_total_row()` | pandas（isna） | 純函式，直接呼叫 |
| `_to_float()` | 無 | 純函式，直接呼叫 |
| `_parse_formula_multiplier()` | 無 | 純函式，直接呼叫 |
| `_resolve_formula_purchase_price()` | 無 | 純函式，直接呼叫 |
| `_detect_header_row()` | pandas + Excel bytes | 需要最小 xlsx |
| `confirm_import()` | DB + Excel bytes + run_match | monkeypatch × 2 + in-memory SQLite + 最小 xlsx |
| `import_vendor_books()` | DB + Excel bytes + run_match | 成本同上，本 task 不測 |
| `import_library_holdings()` | DB + Excel bytes + run_match | 成本同上，本 task 不測 |

**現有基礎（task-test-foundation-core-services 已完成）：**
- pytest 已在 requirements.txt
- tests/ 目錄與 `__init__.py` 已存在

---

### 步驟 1：撰寫 `tests/test_import_service_helpers.py`（Tier 1，必做）

**`_match_columns()` 測試**

測試 VENDOR_COLUMN_HINTS 的 general_books 新增欄位對應，包含：

1. `eligible_label` → `eligibility_label`（hints 第一位）
2. `必選推薦` → `eligibility_label`（hints 備選）
3. `award_template` → `recommendation_source`（hints 第一位）
4. `推薦來源` → `recommendation_source`（hints 備選）
5. `award_notes` → `award_notes`（完全一致）
6. `備註` → `award_notes`（hints 備選）
7. `topic` → `policy_topic`（hints 第一位）
8. `summary_80_120` → `summary`（hints 第一位）
9. `摘要` → `summary`（hints 備選）
10. 欄名含空白與大寫（`" Summary_80_120 "`）→ 仍對應到 `summary`
11. 完全不認識的欄名 → mapping 為空，所有欄位在 unmapped

**`_is_blank_or_total_row()` 測試**

1. `[None, "", None]` → `True`
2. `["合計", "100"]` → `True`
3. `["總計"]` → `True`
4. `["某書", "作者甲", "出版社乙"]` → `False`

---

### 步驟 2：修正 confirm_import() 與 import_vendor_books() 的 book dict bug

**問題**：兩處傳給 `compute_completeness()` 的 `book` dict 缺少 `eligibility_label` 與 `recommendation_source`，導致 general_books 匯入後 completeness 永遠是 `missing_required`。

**修正 `confirm_import()`（L276–283）：**

原本：
```python
book = {
    "title": title,
    "list_price": list_price,
    "purchase_price": purchase_price,
    "author": get_field("author"),
    "publisher": get_field("publisher"),
    "award_item": get_field("award_item"),
}
```

改為：
```python
book = {
    "title": title,
    "list_price": list_price,
    "purchase_price": purchase_price,
    "author": get_field("author"),
    "publisher": get_field("publisher"),
    "award_item": get_field("award_item"),
    "eligibility_label": get_field("eligibility_label"),
    "recommendation_source": get_field("recommendation_source"),
}
```

**修正 `import_vendor_books()`（L496–503）：** 相同方式補入兩個欄位。

修正後立即執行 `python -m compileall app` 確認語法。

---

### 步驟 3：評估並決定 Tier 2 是否實作

在開始 Tier 2 前，先評估 `confirm_import()` 最小路徑的 fixture 準備量：

**所需 monkeypatch 目標：**

```python
monkeypatch.setattr("app.services.import_service.get_connection", lambda: in_mem_conn)
monkeypatch.setattr("app.services.import_service.run_match", lambda pid: {})
```

共 2 個 monkeypatch，在可接受範圍內。

**所需最小 schema（4 個 table）：**

```sql
CREATE TABLE procurement_projects (id INTEGER PRIMARY KEY, project_type TEXT NOT NULL)
CREATE TABLE import_batches (
    id INTEGER PRIMARY KEY, project_id INTEGER, batch_type TEXT,
    original_filename TEXT, profile_id INTEGER, imported_by INTEGER,
    imported_at TEXT, record_count INTEGER
)
CREATE TABLE vendor_books (
    id INTEGER PRIMARY KEY, batch_id INTEGER, award_item TEXT, vendor_seq TEXT,
    title TEXT, author TEXT, isbn TEXT, isbn_normalized TEXT, publish_date TEXT,
    list_price REAL, purchase_price REAL, publisher TEXT, age_range TEXT,
    isbn_status TEXT, completeness_status TEXT, extra_fields TEXT,
    source_row_number INTEGER, raw_row TEXT, category TEXT, book_type TEXT,
    policy_topic TEXT, summary TEXT, source_url TEXT, recommendation_source TEXT,
    eligibility_label TEXT, classification_number TEXT, award_notes TEXT
)
CREATE TABLE book_matches (id INTEGER PRIMARY KEY, vendor_book_id INTEGER, holding_id INTEGER)
```

**最小 Excel bytes（openpyxl 動態產生）：**

```python
def make_xlsx(headers, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
```

**評估結果：** fixture 設置估計約 40–50 行（schema DDL + conn fixture + xlsx helper），在 60 行限制內，可實作。

---

### 步驟 4：撰寫 `tests/test_confirm_import.py`（Tier 2，條件做）

**pytest fixture 結構：**

```
conn_fixture       → in-memory SQLite，建立 4 個 table，插入 general_books project
make_xlsx_fixture  → 接受 headers / rows，回傳 xlsx bytes
```

**測試情境（4 個）：**

1. **general_books 欄位寫入**
   - xlsx headers: `["eligible_label", "award_template", "award_notes", "topic", "summary_80_120", "書名", "定價"]`
   - 一筆書目資料，各欄位有值
   - 驗證 `vendor_books` 的 `eligibility_label`、`recommendation_source`、`award_notes`、`policy_topic`、`summary` 均正確寫入

2. **general_books completeness — missing_required（缺 eligibility_label）**
   - xlsx 書目無 `eligibility_label` 欄位
   - 驗證 `completeness_status = "missing_required"`

3. **general_books completeness — needs_review（有 eligibility/recommendation，缺 author）**
   - xlsx 書目有 `eligibility_label`、`award_template`，無作者欄
   - 驗證 `completeness_status = "needs_review"`

4. **空白列與合計列不寫入 vendor_books**
   - xlsx 含 1 筆有效書目 + 1 筆空白列 + 1 筆「合計」列
   - 驗證 `record_count = 1`（只寫入有效書目）

若 Tier 2 在實作過程中發現需要超過 2 個 monkeypatch 或 fixture 超過 60 行，改為在步驟 3 前記錄延後原因並停止，不強行完成。

---

### 步驟 5：驗證

```
python -m compileall app
python -m pytest -v
```

確認：
- 所有既有測試（task-test-foundation-core-services）仍通過
- 新增測試全部通過，0 failures

---

### 步驟 6：Commit

```
chore(task-test-import-service-fixtures): add import service tests
```

涵蓋：`app/services/import_service.py`（bug 修正）、`tests/test_import_service_helpers.py`（必做）、`tests/test_confirm_import.py`（若 Tier 2 實作）。

---

## 風險與注意事項

**`get_connection()` monkeypatch 方式**

`confirm_import()` 呼叫 `conn = get_connection()` 後最終呼叫 `conn.close()`。若直接使用 in-memory SQLite conn，`close()` 後 DB 就消失，無法在測試中查詢結果。

採用 **non-closing wrapper** 方式：

```python
class _NoCloseConn:
    """委派所有屬性給真實 conn，但 close() 是 no-op。"""
    def __init__(self, conn):
        self._conn = conn
    def close(self):
        pass  # no-op
    def __getattr__(self, name):
        return getattr(self._conn, name)
```

pytest fixture 流程：
1. `sqlite3.connect(":memory:")` 建立真實 conn，設好 schema 與初始資料
2. `monkeypatch.setattr(...)` 讓 `get_connection` 每次回傳 `_NoCloseConn(real_conn)`
3. 呼叫 `confirm_import()`；函式內的 `conn.close()` 是 no-op，DB 保持存活
4. 在真實 conn 上查詢 `vendor_books` 驗證結果
5. pytest fixture teardown：關閉真實 conn（`real_conn.close()`）

**`run_match()` monkeypatch**

`run_match` 在 `confirm_import()` 最後以 try/except 呼叫，monkeypatch 回傳 `{}` 即可。若 monkeypatch 失效，`run_match` 會試圖查詢 DB 的 library_holdings（不在 minimal schema 中），會拋出例外並被 except 捕捉，不影響 import 主流程，但測試結果中會多一個 `match_rerun_error` 欄位。

**Tier 2 決策時間點**

評估應在步驟 2 完成後，開始撰寫 test 之前。若 fixture 複雜度超標，在 plan 中記錄「Tier 2 延後」並 commit，不拖延整個 task。

---

## 預計影響範圍

| 路徑 | 說明 |
|------|------|
| `app/services/import_service.py` | 修正 `confirm_import()` 與 `import_vendor_books()` 的 `book` dict，補入 `eligibility_label`、`recommendation_source` |
| `tests/test_import_service_helpers.py` | 新增（Tier 1，必做） |
| `tests/test_confirm_import.py` | 新增（Tier 2，條件做） |

不影響：`requirements.txt`（pytest 已在上一 task 加入）、`migrations/`、其他 app/ 模組。

---

## 驗證指令

```
python -m compileall app
python -m pytest -v
```

## 成果報告

- result_report_mode: none
