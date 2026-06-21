# Plan: task-vendor-classification-fields

## 實作步驟

### Step 1：新增 migration 004（classification_number 欄位）

建立 `migrations/004_vendor_classification_fields.sql`：

```sql
-- Migration 004: 新增 classification_number 欄位至 vendor_books 與 selection_items

ALTER TABLE vendor_books ADD COLUMN classification_number TEXT;
ALTER TABLE selection_items ADD COLUMN classification_number TEXT;
```

兩者皆以 ALTER TABLE ADD COLUMN 完成，不重建資料表，不影響既有資料。

### Step 2：套用 migration

執行 migration 至開發用 DB（`app/school_lib.db`）：

```
python -c "
import sqlite3
with open('migrations/004_vendor_classification_fields.sql') as f:
    sql = f.read()
conn = sqlite3.connect('app/school_lib.db')
conn.executescript(sql)
conn.commit()
conn.close()
print('OK')
"
```

### Step 3：修改 import_service.py — VENDOR_COLUMN_HINTS

在 `VENDOR_COLUMN_HINTS` 中新增兩個缺漏欄位：

```python
"policy_topic": ["topic", "議題", "policy_topic"],
"classification_number": ["CIP", "分類號", "圖書分類號", "類號"],
```

位置：接在現有的 `eligibility_label` 條目之後。

**不修改的現有 hints（已正確）：**
- `category: ["分類", "category"]` — 不動
- `book_type: ["類型", "書本類型", "book_type"]` — 不動
- `summary: ["summary_80_120", "摘要", "summary"]` — 不動
- `eligibility_label: ["eligible_label", "資格標籤", "必選推薦", "eligibility_label"]` — 不動

### Step 4：修改 import_service.py — confirm_import() INSERT

目前 vendor_books INSERT 欄位列（`app/services/import_service.py` 第 284–285 行附近）：

```python
"category, book_type, summary, source_url, recommendation_source, eligibility_label) "
```

改為：

```python
"category, book_type, policy_topic, summary, source_url, recommendation_source, "
"eligibility_label, classification_number) "
```

對應 VALUES tuple 新增兩個值（緊接 `get_field("book_type")` 之後、`get_field("summary")` 之前，以及末尾）：

```python
get_field("book_type"),
get_field("policy_topic"),          # 新增
get_field("summary"),
...
get_field("eligibility_label"),
get_field("classification_number"), # 新增
```

VALUES 佔位符從 `?` × 23 改為 `?` × 25。

### Step 5：修改 import_service.py — import_vendor_books() INSERT

同 Step 4，`import_vendor_books()` 有相同結構的 INSERT（第 496–523 行附近）：
- 欄位列新增 `policy_topic`、`classification_number`
- VALUES tuple 新增 `get_field("policy_topic")`、`get_field("classification_number")`
- VALUES 佔位符同樣從 23 個 `?` 改為 25 個

### Step 6：修改 selection_service.py — upsert_selection() INSERT

`upsert_selection()` 的 snap SELECT 已使用 `vb.*`，migration 004 套用後自動包含 `classification_number`。

需修改的是 selection_items INSERT 欄位列與 VALUES（`app/services/selection_service.py` 第 62–117 行附近）：

欄位列新增 `classification_number`（接在 `eligibility_label` 之後）：

```python
"category, book_type, policy_topic, summary, "
"source_url, recommendation_source, eligibility_label, award_notes, "
"classification_number, "                   # 新增
"completeness_status, ..."
```

VALUES tuple 新增：

```python
snap.get("eligibility_label"),
snap.get("award_notes"),
snap.get("classification_number"),          # 新增
completeness,
```

VALUES 佔位符從 36 個 `?` 改為 37 個。

**不修改：**
- snap SELECT 不需動（`vb.*` 自動涵蓋新欄位）
- `get_selected_books()` 不需動（`si.*` 自然回傳 `classification_number`）
- `update_selection_overrides()` 不需動

### Step 7：驗證

見「驗證指令」章節。

---

## 風險與注意事項

1. **舊資料無 classification_number / policy_topic**：重新匯入書商書單後才有值；已選書的 snapshot 不自動更新（快照設計屬預期行為）。

2. **category / book_type 0 值原因**：與本次 migration 無關。這兩欄的 VENDOR_COLUMN_HINTS 與 INSERT 已正確，問題是舊資料在 migration 003 加欄前匯入，重新匯入書商書單即可填值，不需修改任何程式碼。

3. **confirm_import vs import_vendor_books**：兩個函式的 INSERT 欄位列獨立維護，必須同步修改（Step 4 與 Step 5），不可只改其中一個。

4. **VALUES 佔位符數量必須與欄位列一致**：修改後須逐一核對 INSERT 欄位數量與 `?` 數量，否則 sqlite3 會在執行時報 ProgrammingError。

5. **Excel CIP 欄名可能為 "CIP"（全大寫）**：`_normalize_header` 會將其轉為 `"cip"`，而 hints 的 `"CIP"` 同樣會轉為 `"cip"`，所以能正確匹配。

6. **migration 004 為 ALTER TABLE，不需 PRAGMA foreign_keys OFF**：與 migration 003 的重建式不同，ALTER TABLE ADD COLUMN 在 SQLite 中不受 foreign key 影響。

---

## 預計影響範圍

| 檔案 | 變動類型 |
|------|---------|
| `migrations/004_vendor_classification_fields.sql` | 新增 |
| `app/services/import_service.py` | 修改（VENDOR_COLUMN_HINTS + 兩處 INSERT） |
| `app/services/selection_service.py` | 修改（upsert_selection INSERT） |
| `app/static/selection.html` | 不動 |
| `app/services/export_service.py` | 不動 |
| `app/services/validation_service.py` | 不動 |

---

## 驗證指令

### lint / format

- lint: `python -m compileall app`
- format: 無既有設定，不引入新工具

### typecheck / test

- typecheck: 無既有設定
- test: 無既有自動化測試，以手動驗證步驟替代

### build

- build: 不適用（Python 直譯式）

### 手動驗證步驟（依序執行）

**A. migration 臨時 DB 測試：**

```python
python -c "
import sqlite3, tempfile, os
with open('migrations/001_initial_schema.sql') as f: sql001 = f.read()
with open('migrations/002_import_export_mapping.sql') as f: sql002 = f.read()
with open('migrations/003_selection_snapshot.sql') as f: sql003 = f.read()
with open('migrations/004_vendor_classification_fields.sql') as f: sql004 = f.read()
tmp = tempfile.mktemp(suffix='.db')
conn = sqlite3.connect(tmp)
conn.executescript(sql001)
conn.executescript(sql002)
conn.executescript(sql003)
conn.executescript(sql004)
cols_vb = [r[1] for r in conn.execute('PRAGMA table_info(vendor_books)').fetchall()]
cols_si = [r[1] for r in conn.execute('PRAGMA table_info(selection_items)').fetchall()]
assert 'classification_number' in cols_vb, 'vendor_books 缺 classification_number'
assert 'classification_number' in cols_si, 'selection_items 缺 classification_number'
conn.close()
os.remove(tmp)
print('migration 004 臨時 DB 測試通過')
"
```

**B. compileall：**

```
python -m compileall app
```

**C. 匯入 `00_source/本土書單.xlsx` 後查 DB：**

```sql
SELECT COUNT(*) FROM vendor_books WHERE category IS NOT NULL AND trim(category) != '';
SELECT COUNT(*) FROM vendor_books WHERE book_type IS NOT NULL AND trim(book_type) != '';
SELECT COUNT(*) FROM vendor_books WHERE policy_topic IS NOT NULL AND trim(policy_topic) != '';
SELECT COUNT(*) FROM vendor_books WHERE classification_number IS NOT NULL AND trim(classification_number) != '';
```

預期：前三項 > 0；`classification_number` count 視 Excel 是否有 CIP 欄而定。

**D. selection_items snapshot 驗證：**

在 selection.html 選入至少一本書後查：

```sql
SELECT id, category, book_type, policy_topic, classification_number
FROM selection_items
ORDER BY id DESC LIMIT 3;
```

預期：category、book_type 有值；policy_topic 若 Excel 有 "topic" 欄則有值；classification_number 若 Excel 有 "CIP" 欄則有值。

**E. 清除書商書單後快照保留驗證：**

執行「清除書商來源」後：

```sql
SELECT COUNT(*) FROM selection_items WHERE category IS NOT NULL AND trim(category) != '';
```

預期：count 與清除前相同（snapshot 不受來源清除影響）。

**F. 前端目視確認：**

- selection.html：類型下拉（filter-book-type）出現選項
- selection.html：分類/議題搜尋欄（filter-category）顯示，輸入分類值可篩選
- 書卡不顯示「書商資訊」區塊

---

## 成果報告

- result_report_mode: none
- 適用情境：無需產生成果報告，驗收以 DB 查詢與目視確認為準
