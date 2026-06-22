# Plan: task-general-books-completeness

## 實作步驟

### 步驟 0：修正 import_service.py 的 award_notes 寫入缺漏

**confirm_import()（L282–317）**

- 將 `eligibility_label, classification_number)` 改為 `eligibility_label, classification_number, award_notes)`
- 對應 VALUES 結尾將 `get_field("classification_number"),` 後新增一行 `get_field("award_notes"),`
- VALUES 佔位符數量從 25 個增為 26 個

**import_vendor_books()（L497–531）**

- 同上：`eligibility_label, classification_number)` 改為 `eligibility_label, classification_number, award_notes)`
- VALUES 結尾加 `get_field("award_notes"),`，佔位符改為 26 個

驗證：匯入含「備註」欄位的書單，用 DB browser 確認 `vendor_books.award_notes` 有值。

---

### 步驟 1：更新 completeness_service.py 的 compute()

修改函式簽名：

```python
def compute(book: dict, overrides: dict | None = None, project_type: str | None = None) -> ...:
```

在現有 `author`、`publisher`、`award_item` 取值後，以 `project_type` 分支取代舊邏輯：

```python
if project_type == 'general_books':
    eligibility_label = _get(book, "eligibility_label", overrides)
    recommendation_source = _get(book, "recommendation_source", overrides)
    if not eligibility_label or not recommendation_source:
        return "missing_required"
    if not author or not publisher:
        return "needs_review"
    return "export_ready"

# local_culture 及其他（現有邏輯不動）
award_item = _get(book, "award_item", overrides)
if not author or not publisher or not award_item:
    return "needs_review"
return "export_ready"
```

`_get()` 呼叫 `eligibility_label` 與 `recommendation_source` 時，overrides 可能有使用者修正值，須透過 `_get()` 取得（不直接讀 book 欄位）。

---

### 步驟 2：更新 import_service.py 傳入 project_type

**confirm_import()**

`conn = get_connection()` 之後（約 L228），在 `_clear_vendor_books_for_project` 之前，加入一次 project_type 查詢：

```python
proj_row = conn.execute(
    "SELECT project_type FROM procurement_projects WHERE id = ?", (project_id,)
).fetchone()
proj_type = proj_row["project_type"] if proj_row else None
```

在 `book` dict 組好後，將呼叫改為：

```python
completeness = compute_completeness(book, project_type=proj_type)
```

**import_vendor_books()**

同上：`conn = get_connection()` 之後，加入 project_type 查詢（project_id 已是函式參數），修改 `compute_completeness(book)` 呼叫，傳入 `project_type=proj_type`。

---

### 步驟 3：修正 recompute_for_book()

`recompute_for_book()` 目前從 `vendor_books` 讀取單本書，無法得知 project_type。修正方式：透過 `vendor_books → import_batches → procurement_projects` join 取得 project_type：

```python
row = conn.execute(
    "SELECT vb.*, pp.project_type "
    "FROM vendor_books vb "
    "JOIN import_batches ib ON vb.batch_id = ib.id "
    "JOIN procurement_projects pp ON ib.project_id = pp.id "
    "WHERE vb.id = ?",
    (vendor_book_id,)
).fetchone()
```

`book = dict(row)` 之後，`project_type = book.pop("project_type", None)`，再傳入 `compute(book, overrides, project_type=project_type)`。

若 join 失敗（import_batches.project_id 為 NULL，即 library_holdings 類型），`project_type` 為 None，維持現有 local_culture 邏輯，安全降級。

---

### 步驟 4：修正 selection.html 的 render()

在 `render(books)` 函式的模板字串中，以 `projectType` 條件控制欄位列顯示：

```javascript
const isGeneral = projectType === 'general_books';
```

欄位列改為：

```javascript
${!isGeneral ? `<div class="field-row"><label>獲獎項目</label><input type="text" value="..." data-field="award_item" data-bookid="${b.id}"></div>` : ''}
${isGeneral ? `<div class="field-row"><label>必選/推薦（A欄）</label><select data-field="eligibility_label" data-bookid="${b.id}">${eligOptions}</select></div>` : ''}
${isGeneral ? `<div class="field-row"><label>H欄推薦來源</label><select data-field="recommendation_source" data-bookid="${b.id}">${recSrcOptions}</select></div>` : ''}
${isGeneral ? `<div class="field-row"><label>備註（L欄）</label><input type="text" value="..." data-field="award_notes" data-bookid="${b.id}"></div>` : ''}
```

注意：local_culture 原有的 eligibility_label / recommendation_source / award_notes 欄位列改為 general_books 專屬；若 local_culture 也需要備註欄，需另外討論（目前 spec 不做）。

---

### 步驟 5：修正 selection.html 的 renderClearedItems()

與步驟 4 相同邏輯，對 `renderClearedItems(items)` 中的模板字串套用相同的 `isGeneral` 條件。`data-selid` 屬性保持不變。

---

### 步驟 6：修正 export.html 警告文字（附帶）

L147：

```
`注意：有 ${check.missing_required} 本書缺少必填欄位，匯出時將自動排除這些書目。`
```

改為：

```
`注意：有 ${check.missing_required} 本書缺少必填欄位，匯出時欄位將留空，請確認後再匯出。`
```

---

### 步驟 7：驗證與 commit

執行 `python -m compileall app` 確認無語法錯誤。

手動驗證（需兩種 project_type）：

1. **general_books 匯入測試**：書單含備註欄 → 匯入後確認 `award_books.award_notes` 有值、匯出 L欄不為空
2. **general_books badge 測試**：書目缺 eligibility_label → 選書頁顯示 `missing_required`；補上 A/H 欄後重算 → 顯示 `export_ready`
3. **general_books 修正表單**：開啟修正表單 → 不顯示「獲獎項目」，顯示 A/H/L 三欄
4. **local_culture 修正表單**：開啟修正表單 → 顯示「獲獎項目」，不顯示 A/H/L 三欄
5. **快照區塊**：清除書單後查看快照修正表單 → 欄位顯示與活書單一致
6. **export.html**：有缺欄位書目時確認警告文字說「留空」

Commit 訊息格式：`fix(task-general-books-completeness): {short-description}`

## 風險與注意事項

**recompute_for_book() 的處理方式**

已在步驟 3 修正，透過 join 取得 project_type。若 `import_batches.project_id = NULL`（library_holdings 路徑），join 會 fail，此時 `project_type = None` 安全降級為 local_culture 邏輯。這個 edge case 不影響正常使用流程，可接受。

**已存在的 vendor_books.completeness_status backfill**

不進行一次性 backfill，理由：

1. `validation_service.check_export_readiness()` 對 general_books 的驗證已正確，不會因舊的 `completeness_status` 讓不合格書目通過匯出
2. 使用者重新匯入即可刷新所有 `completeness_status`
3. 儲存任何書目 overrides 會觸發 `recompute_for_book()`（步驟 3 修正後會帶入正確 project_type）
4. backfill 需要批次 UPDATE，風險高於效益

如日後有大量舊資料需求，可另建 chore task 處理。

**selection.html 欄位隱藏的影響**

`saveOverrides()` 使用 `querySelectorAll('[data-bookid]')` 收集所有欄位，若欄位列不存在（`${!isGeneral ? ... : ''}`），對應 field 不會出現在 overrides，不會寫入 null 或空字串，安全。`saveSelectionOverrides()` 同理。

**general_books 的 award_notes 欄位顯示**

依 spec，general_books 顯示 award_notes（L欄）。local_culture 原本也有 award_notes 欄位列，修正後改為隱藏。若日後 local_culture 也需要備註，需另外評估。

## 預計影響範圍

| 檔案 | 變更 |
|------|------|
| `app/services/import_service.py` | 步驟 0、2：award_notes INSERT、project_type 查詢與傳遞 |
| `app/services/completeness_service.py` | 步驟 1、3：compute() 簽名與邏輯、recompute_for_book() join |
| `app/static/selection.html` | 步驟 4、5：render() 與 renderClearedItems() 欄位條件顯示 |
| `app/static/export.html` | 步驟 6：警告文字 |

不影響：`validation_service.py`、`export_service.py`、DB schema、API routes。

## 驗證指令

- lint：無既有設定，跳過
- format：無既有設定，跳過
- typecheck：無既有設定，跳過
- test：無既有測試，跳過
- build：`python -m compileall app`

## 成果報告

- result_report_mode: none
- 適用情境：無需成果報告
- 報告路徑（若 mode 非 none）：`docs/reports/task-general-books-completeness/`
