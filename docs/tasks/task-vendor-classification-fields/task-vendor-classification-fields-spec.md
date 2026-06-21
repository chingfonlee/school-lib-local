# Spec: task-vendor-classification-fields

## 目標

讓書商 Excel（`00_source/本土書單.xlsx`）的分類相關欄位正確保存到資料庫，使 selection.html 的類型下拉與分類/議題篩選能正常運作。

## 問題說明

### 現況調查結果

**Schema 狀態：**

| 欄位 | vendor_books | selection_items | 說明 |
|------|-------------|----------------|------|
| `category` | ✓ (migration 003) | ✓ (migration 003) | 已有欄位 |
| `book_type` | ✓ (migration 003) | ✓ (migration 003) | 已有欄位 |
| `policy_topic` | ✓ (001 原始 schema) | ✓ (migration 003) | 已有欄位 |
| `summary` | ✓ (migration 003) | ✓ (migration 003) | 已有欄位 |
| `eligibility_label` | ✓ (migration 003) | ✓ (migration 003) | 已有欄位 |
| `classification_number` | ✗ 不存在 | ✗ 不存在 | 需新增 |

**VENDOR_COLUMN_HINTS 狀態：**

| 系統欄位 | 現有 hints | 狀態 |
|---------|-----------|------|
| `category` | `["分類", "category"]` | ✓ 已有 |
| `book_type` | `["類型", "書本類型", "book_type"]` | ✓ 已有 |
| `summary` | `["summary_80_120", "摘要", "summary"]` | ✓ 已有 |
| `eligibility_label` | `["eligible_label", "資格標籤", "必選推薦", "eligibility_label"]` | ✓ 已有 |
| `policy_topic` | 無任何 hint | ✗ 缺漏 |
| `classification_number` | 不存在 | ✗ 缺漏 |

**vendor_books INSERT 狀態（confirm_import 與 import_vendor_books 兩者相同）：**

| 欄位 | 已在 INSERT | 說明 |
|------|------------|------|
| `category` | ✓ | 正常寫入 |
| `book_type` | ✓ | 正常寫入 |
| `summary` | ✓ | 正常寫入 |
| `eligibility_label` | ✓ | 正常寫入 |
| `policy_topic` | ✗ 缺漏 | 欄位存在但 INSERT 未包含 |
| `classification_number` | ✗ 缺漏 | 欄位不存在 |

**selection_items INSERT 狀態（upsert_selection）：**

| 欄位 | 已在 INSERT | 說明 |
|------|------------|------|
| `category` | ✓ | 正常 |
| `book_type` | ✓ | 正常 |
| `policy_topic` | ✓ | 正常（但 vendor_books.policy_topic 始終 NULL，因 import 未寫入） |
| `summary` | ✓ | 正常 |
| `eligibility_label` | ✓ | 正常 |
| `classification_number` | ✗ 缺漏 | 欄位不存在 |

### 根本原因

1. **`category` 與 `book_type` 有值筆數為 0**：欄位於 migration 003 新增後，舊資料未 backfill。需重新匯入書商書單後才會有值。VENDOR_COLUMN_HINTS 的 hints 本身正確（`分類`→`category`、`類型`→`book_type`），不需修改。

2. **`policy_topic` 始終 NULL**：VENDOR_COLUMN_HINTS 完全沒有 `policy_topic` 的 hint；`confirm_import` 與 `import_vendor_books` 的 vendor_books INSERT 也未包含此欄位。即使書商 Excel 有 "topic" 欄位，也不會被讀取。

3. **`classification_number` 不存在**：schema 無此欄位，VENDOR_COLUMN_HINTS 無對應 hint，Excel 的 `CIP` 欄位目前流入 `extra_fields`（書卡已移除書商資訊，extra_fields 不再顯示）。

4. **`extra_fields` 不適合承載老師需要的欄位**：extra_fields 是匯入時剩餘欄位的 fallback 儲存，並非正規化資料，且書卡已不顯示。

## 需求範圍

### 1. Schema

- 新增 `migrations/004_vendor_classification_fields.sql`：
  - `vendor_books` 新增 `classification_number TEXT`
  - `selection_items` 新增 `classification_number TEXT`
  - 兩者皆以 `ALTER TABLE ... ADD COLUMN` 完成，不重建資料表
  - 已有欄位（category、book_type、policy_topic）不重建

### 2. VENDOR_COLUMN_HINTS 補充

- 新增 `classification_number: ["CIP", "分類號", "圖書分類號", "類號"]`
- 新增 `policy_topic: ["topic", "議題", "policy_topic"]`

### 3. import_service 修改

- `confirm_import()` 的 vendor_books INSERT：新增 `policy_topic, classification_number` 欄位及對應值
- `import_vendor_books()` 的 vendor_books INSERT：同上

### 4. selection_service 修改

- `upsert_selection()` 的 selection_items INSERT：新增 `classification_number` 欄位及對應值（snap query 使用 `vb.*`，自動涵蓋新欄位）

### 5. 前端

- `selection.html` 不需修改：
  - `filter-book-type` 下拉已依 `b.book_type` 動態填入，有資料後自動出現選項
  - `filter-category` 已依 `b.category` 與 `b.policy_topic` 搜尋，有資料後自動顯示
  - 類型下拉與分類/議題搜尋欄在無資料時自動隱藏，有資料後自動顯示（現有邏輯）

### 6. 舊資料

- 舊匯入批次的 vendor_books 資料不 backfill（風險過高）
- 使用者需重新匯入書商書單，才會使 category、book_type、policy_topic、classification_number 有值
- selection_items 已選書的 snapshot 保持不變（快照設計）

## 不做的事

- 不重新顯示 extra_fields（書卡「書商資訊」不恢復）
- 不修改 export_service（匯出不讀 classification_number）
- 不修改 validation_service（驗證不讀 classification_number）
- 不修改館藏匯入流程
- 不做 CIP 分類號轉中文分類名稱
- 不做外部 ISBN/CIP 查詢
- 不修改 selection.html 的篩選 UI 結構
- 不修改內網部署或 backlog 文件
- 不 backfill 舊資料

## 驗收條件

1. `python -m compileall app` pass（無語法錯誤）
2. migration 004 可在臨時 DB 套用（不破壞既有資料）
3. 匯入 `00_source/本土書單.xlsx` 後：
   - `SELECT COUNT(*) FROM vendor_books WHERE category IS NOT NULL AND trim(category) != ''` > 0
   - `SELECT COUNT(*) FROM vendor_books WHERE book_type IS NOT NULL AND trim(book_type) != ''` > 0
   - `SELECT COUNT(*) FROM vendor_books WHERE classification_number IS NOT NULL AND trim(classification_number) != ''` > 0（若 Excel 有 CIP 欄）
4. `selection.html` 類型下拉出現選項（filter-book-type 有書目後顯示）
5. `selection.html` 分類/議題搜尋可找到分類（filter-category 搜尋 category 可篩選）
6. 選一本書後，`selection_items` snapshot 包含 classification_number、category、book_type、policy_topic
7. 清除書商來源後，`selection_items` 仍保留分類相關欄位（快照設計不受影響）
8. 書卡不顯示「書商資訊」（extra_fields 不出現在 UI）
