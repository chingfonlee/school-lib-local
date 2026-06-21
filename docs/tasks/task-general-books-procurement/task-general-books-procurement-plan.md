# Plan: task-general-books-procurement

## 實作步驟

### Step 1：config.yaml 新增 general_books 匯出範本

檔案：`config.yaml`

在 `export_templates` 陣列後新增：

```yaml
  - name: "general_books_kaohsiung_115"
    project_type: "general_books"
    template_file_path: "./00_source/高雄市115年度○○區○○國小圖書館（室）圖書採購書單(空白).xlsx"
    sheet_name: "正式書單"
    header_row: 4
    data_start_row: 6
    max_rows: 50
    school_name_cell: ""
    approved_budget_cell: ""
    column_mappings:
      eligibility_label: "A"
      sort_order: "B"
      title: "C"
      author: "D"
      publisher: "E"
      isbn: "F"
      quantity: "G"
      recommendation_source: "H"
      policy_topic: "I"
      price: "J"
      subtotal: "K"
      award_notes: "L"
```

`ensure_initial_data()` 以 `INSERT OR IGNORE` 寫入 export_templates（name 為 UNIQUE），重新啟動後自動 seed。

---

### Step 2：import_service.py 補齊 VENDOR_COLUMN_HINTS

在 `VENDOR_COLUMN_HINTS` 末尾新增：

```python
"award_notes": ["award_notes", "備註", "notes"],
```

---

### Step 3：import.html 補齊 SYSTEM_FIELDS

在 SYSTEM_FIELDS 陣列末尾（classification_number 之後）新增：

```js
{key:'eligibility_label',     label:'必選/推薦（A欄）', required:false},
{key:'recommendation_source', label:'H欄獲獎代碼',      required:false},
{key:'award_notes',           label:'備註（L欄）',      required:false},
```

---

### Step 4：projects.html 啟用 general_books

移除：

```html
<option value="general_books" disabled>一般圖書採購（即將推出）</option>
```

改為：

```html
<option value="general_books">一般圖書採購</option>
```

---

### Step 5：export_service.py 新增常數與 export_general_books()

在 `export_service.py` 頂部新增常數（`import` 後）：

```python
GENERAL_BOOKS_H_ALLOWED = {
    "喜閱網",
    "文化部中小學生優良課外讀物選介",
    "好書大家讀",
    "金鼎獎",
    "文化部Books from Taiwan等具高公信力推薦價值之圖書",
    "國民中小學新生閱讀推動活動入選書單",
    "圖書分級推薦書目、臺灣歷史文化分級推薦書目",
    "其他國內外具公信力單位辦理之獎項(請備註獎項名稱)",
    "學校自選(請備註原因)",
}

GENERAL_BOOKS_H_REQUIRES_NOTES = {
    "其他國內外具公信力單位辦理之獎項(請備註獎項名稱)",
    "學校自選(請備註原因)",
}
```

新增 `export_general_books(settings: ExportSettings) -> str`，結構與 `export_local_culture` 類似，但：

1. 呼叫 `_load_export_template_for_project` 取得 general_books 範本
2. `ws.active` 不夠：需用 `tmpl["sheet_name"]`（若有值）指定工作表
3. 不寫 school_name_cell / approved_budget_cell（欄位為空字串，略過）
4. 清除範例列（data_start_row - 1）各欄值
5. 每本書寫入：
   - A: `eligibility_label`
   - B: sort_order（序號）
   - C: `title`
   - D: `author`
   - E: `publisher`
   - F: `isbn_normalized` or `isbn`
   - G: `selected_quantity`
   - H: `recommendation_source`
   - I: `policy_topic`
   - J: price（list_price or purchase_price 依 price_field）
   - K: subtotal
   - L: `award_notes`
6. 匯出前驗證不在此函式做（validation_service 負責），但函式內若 H 欄值空，可寫空值（由 export-check 事先阻擋）

---

### Step 6：exports.py router 依 project_type 分流

修改 `exports.py`：

1. 從 DB 查詢 project 的 `project_type`
2. 匯入 `export_general_books`
3. 依 `project_type` 決定呼叫哪個函式：

```python
if project["project_type"] == "general_books":
    job_id = export_general_books(settings)
else:
    job_id = export_local_culture(settings)
```

---

### Step 7：validation_service.py 依 project_type 分流

`check_export_readiness(project_id, price_field)` 內部：

1. 查詢 `project_type = conn.execute("SELECT project_type FROM procurement_projects WHERE id = ?", (project_id,)).fetchone()["project_type"]`
2. 依 `project_type` 決定阻擋與提示規則：

**general_books 阻擋（blocking）：**
- 書名空
- 依 price_field 的價格空
- `selected_quantity <= 0`
- `eligibility_label` 空（A 欄）
- `recommendation_source` 空或不在 `GENERAL_BOOKS_H_ALLOWED`（H 欄）
- `recommendation_source` 在 `GENERAL_BOOKS_H_REQUIRES_NOTES` 且 `award_notes` 空（備註必填）

**general_books 提示（needs_review）：**
- 作者空
- 出版社空
- `isbn_status != 'valid'`

3. 將 `GENERAL_BOOKS_H_ALLOWED` 和 `GENERAL_BOOKS_H_REQUIRES_NOTES` 從 `export_service.py` 移到共用常數位置（或在 validation_service 重新定義），避免循環引用。

**最簡做法**：在 `validation_service.py` 直接定義同樣的兩個 set，不引入 export_service。未來若維護需同步修改兩處，在各自檔案的常數定義旁加 comment 說明。

---

### Step 8：selection.html 書卡顯示 summary 與 policy_topic

在書卡 render 函式中，若 `b.summary` 有值，顯示一段縮排文字（例如 3 行省略）；若 `b.policy_topic` 有值，顯示為小 tag/badge。

實作位置：`renderBooks()` 或同等函式的書卡 HTML template 字串。

---

### Step 9：selection.html 書卡可覆寫 eligibility_label / recommendation_source / award_notes

**後端已就緒**：`PATCH /api/selections/{selection_id}/overrides`（`app/routers/selections.py`）已存在，接受任意 `overrides` dict，merge 進 `user_overrides`，無需後端改動。

純前端修改：在書卡 override 編輯介面加入三個欄位：

- `eligibility_label`：`<select>`（必選/推薦/自選）
- `recommendation_source`：`<select>`（9 個 H 欄允許值，與 `GENERAL_BOOKS_H_ALLOWED` 常數一致）
- `award_notes`：`<input type="text">`

呼叫 `PATCH /api/selections/{sel_id}/overrides` 存入，保存後重新整理書卡（重新讀取 allBooks 或更新 selMap）。

---

### Step 11：selection.html 採購類別篩選

**純前端，無後端 / DB 變更。**

1. 全域加入 `let projectType = null;`
2. requireAuth 載入 proj 後設定 `projectType = proj.project_type`；若為 `general_books` 顯示 `#field-purchase-category`
3. 新增 `getPurchaseCategory(b)` helper（見 spec §11）：優先 `eligibility_label`，fallback 依 `recommendation_source` 推導
4. 篩選列 policy-topic 後插入 `<div id="field-purchase-category" style="display:none">` 含 4 個 option
5. `applyFilter()` 讀取 `filter-purchase-category.value`，若非空則 exact match `getPurchaseCategory(b)`
6. `resetFilters()` 在 select 重設清單加入 `filter-purchase-category`

---

### Step 10：export.html 依 project_type 隱藏不適用輸入欄

頁面載入時已有 `proj = await api('/api/projects/${pid}')`。

在取得 proj 後加入：

```js
if (proj.project_type === 'general_books') {
  document.getElementById('school-name-group').style.display = 'none';
  document.getElementById('budget-group').style.display = 'none';
}
```

對「學校名稱」與「核定金額」的 `form-group` 外層加上對應 id（`school-name-group`、`budget-group`）以便隱藏。local_culture 維持現有顯示。

---

## 風險與注意事項

1. **export_local_culture 不得動到** — 本土文化採購流程必須保持完整。所有新增均為平行函式或新分支。

2. **award_item 不得輸出至 H 欄** — `award_item` 為原始多行自由文字，不在 H 欄允許清單內。實作中務必確認 export_general_books() 只讀 `recommendation_source`，不讀 `award_item`。

3. **H 欄允許值重複定義** — `GENERAL_BOOKS_H_ALLOWED` 與 `GENERAL_BOOKS_H_REQUIRES_NOTES` 需在 `export_service.py` 和 `validation_service.py` 各定義一次（避免循環引用）。兩處定義旁各加 comment 說明來源（範本 N5:N13）。MVP 接受此做法。

4. **sheet_name 欄位** — `export_local_culture()` 使用 `wb.active`。`export_general_books()` 需用 `wb[tmpl["sheet_name"]]` 指定「正式書單」工作表，否則寫入到錯誤工作表。

5. **selection.html summary 顯示** — summary 欄位可能超長（80–120 字），需截斷（例如 `-webkit-line-clamp: 3`）或折疊以避免書卡過長。

6. **ensure_initial_data seed 時機** — general_books 範本需重新啟動伺服器後才被 seed（INSERT OR IGNORE）。若本機 DB 已存在但無此範本，重啟服務即可。

---

## 預計影響範圍

| 檔案 | 變動類型 |
|------|---------|
| `config.yaml` | 新增 general_books export_template |
| `app/services/import_service.py` | 新增 VENDOR_COLUMN_HINTS: award_notes |
| `app/static/import.html` | 新增 3 個 SYSTEM_FIELDS |
| `app/static/projects.html` | 移除 `disabled` |
| `app/services/export_service.py` | 新增常數 + export_general_books() |
| `app/routers/exports.py` | 新增 project_type 分流 |
| `app/services/validation_service.py` | 新增 project_type 分流 + general_books 規則 |
| `app/static/selection.html` | 新增卡片顯示 summary/policy_topic + override modal 欄位 |
| `app/static/export.html` | 依 project_type 隱藏學校名稱/核定金額欄 |

不影響：
- `migrations/`（無 migration）
- `app/database.py`（seed 邏輯不變，config 驅動）
- `app/services/selection_service.py`（snapshot 已含所有需要欄位）
- `app/routers/selections.py`（override endpoint 已完整）
- `app/static/export-check.html`（validation API 回傳結果不變，UI 自動顯示新 blocking fields）

---

## 驗證指令

### lint / format
- `python -m compileall app`（確認無語法錯誤）

### typecheck / test
- 無既有自動化測試

### build
- 不適用

### 手動驗證步驟（依序）

**A. compileall：**
```
python -m compileall app
```

**B. seed 驗證：**
- 重啟伺服器後確認 `export_templates` 有 `general_books_kaohsiung_115` 記錄
- `SELECT name, project_type FROM export_templates;`

**C. 建立 general_books 專案：**
- projects.html 可建立一般圖書採購專案
- `SELECT * FROM procurement_projects ORDER BY id DESC LIMIT 1;` 確認 project_type = general_books

**D. 匯入書單：**
- 匯入 `必選推薦-欄位調整-topic-summary-v6-final.xlsx`
- 確認欄位 mapping 出現 eligibility_label、recommendation_source、award_notes
- 確認匯入後：
  ```sql
  SELECT eligibility_label, recommendation_source, policy_topic, summary, award_notes
  FROM vendor_books ORDER BY id DESC LIMIT 5;
  ```
  有值不為空

**E. 選書與 snapshot：**
- 選一本書
- 確認 selection_items snapshot 包含上述欄位

**F. 選書頁確認：**
- selection.html 書卡顯示 summary / policy_topic
- 書卡 override modal 可編輯 eligibility_label / recommendation_source / award_notes

**G. export-check.html：**
- 對 general_books 專案執行匯出前檢查
- 確認阻擋條件：缺 eligible_label、H 欄空或非法、H 欄需備註但無 award_notes

**H. 匯出 Excel：**
- 匯出一般圖書書單
- 開啟輸出 Excel，確認：
  - A 欄值為 必選/推薦/自選
  - H 欄值在允許清單內
  - I 欄有 policy_topic
  - L 欄有 award_notes（若有）
- 以 openpyxl 驗證 data validation 仍在 H 欄（範本 copy 後應保留）

**I. 回歸測試：**
- 以 local_culture 專案執行匯出前檢查和匯出，確認不受影響

---

## 成果報告

- result_report_mode: none
- 適用情境：純功能新增，以手動目視確認為主
