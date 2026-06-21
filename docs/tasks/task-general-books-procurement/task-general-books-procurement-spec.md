# Spec: task-general-books-procurement

## 目標

支援一般圖書採購（`project_type = general_books`）完整流程：建立專案 → 匯入書單 → 選書 → 匯出前檢查 → 匯出符合高雄市 115 年度圖書採購書單格式的 Excel。

將使用者整理過的必選推薦書單（`必選推薦-欄位調整-topic-summary-v6-final.xlsx`）作為預設一般圖書來源書單，其他書商書單若缺少強化欄位則降級運作並提示需人工補充。

---

## Excel 調查結果

### 來源書單（必選推薦-欄位調整-topic-summary-v6-final.xlsx）

- Sheet: `Sheet`（單一工作表）
- 欄位（第 1 列）：獲獎項目、排序、書名、作者、條碼、出版日期、定價、單價、數量、總價、出版社、連結、適合年齡、分類、類型、topic、summary_80_120、award_template、eligible_label、award_notes
- 總計約 6750 筆書目
- 關鍵欄位語意：
  - `award_template`：已符合 H 欄下拉合法值（例如：喜閱網）
  - `eligible_label`：已符合 A 欄值（必選/推薦/自選）
  - `award_notes`：樣本為空（僅在 H 欄需備註時填入）
  - `topic`：議題，對應 `policy_topic`
  - `summary_80_120`：摘要，對應 `summary`

### 匯出範本（高雄市115年度○○區○○國小圖書館（室）圖書採購書單(空白).xlsx）

- Sheet：`正式書單`
- 第 4 列：欄位標題
- 第 5 列：範例列（匯出前清除）
- 第 6 列起：可填資料

| 欄位 | Excel 欄 | 說明 |
|------|---------|------|
| 必選/推薦/自選 | A | 下拉，允許值：必選,推薦,自選 |
| 排序 | B | 序號 |
| 書名 | C | |
| 作者 | D | |
| 出版社 | E | |
| ISBN | F | |
| 採購數量 | G | |
| 獲獎項目 | H | 下拉，允許值來自 N5:N13（9 個值） |
| 重要政策/議題 | I | |
| 定價(新臺幣) | J | |
| 小計 | K | |
| 備註 | L | H 欄某些值時必填 |

**H 欄 9 個允許值（N5:N13）：**

1. 喜閱網
2. 文化部中小學生優良課外讀物選介
3. 好書大家讀
4. 金鼎獎
5. 文化部Books from Taiwan等具高公信力推薦價值之圖書
6. 國民中小學新生閱讀推動活動入選書單
7. 圖書分級推薦書目、臺灣歷史文化分級推薦書目
8. 其他國內外具公信力單位辦理之獎項(請備註獎項名稱) ← L 欄備註必填
9. 學校自選(請備註原因) ← L 欄備註必填

---

## 欄位語意釐清：award_template / recommendation_source / award_item

這三個名稱在歷史上容易混淆，本 task 統一定義如下：

| 層次 | 欄位名稱 | 語意 |
|------|---------|------|
| 來源 Excel | `award_template` | 教育局 H 欄合法下拉值（如「喜閱網」）。已符合 N5:N13 允許清單 |
| DB（暫定） | `recommendation_source` | 儲存 award_template 值。VENDOR_COLUMN_HINTS 已有 `["award_template", ...]`→`recommendation_source` 對應 |
| 匯出 H 欄 | H 欄 ← `recommendation_source` | 讀 `recommendation_source`（含 user_overrides 覆蓋優先） |
| 來源 Excel | `獲獎項目` | 原始多行文字推薦說明（如「112學年度高雄喜閱網\n臺南布可星球…」），用途為閱讀參考或填入 award_notes |
| DB | `award_item` | 儲存「獲獎項目」原始文字，**不輸出至 H 欄**，僅作原始推薦來源追溯 |
| 來源 Excel | `award_notes` | L 欄備註內容，當 H 欄為「其他...」或「學校自選...」時必填 |
| DB | `award_notes` | 直接對應，匯出至 L 欄 |

**關鍵規則：**
- H 欄必須使用 `recommendation_source`，不得使用 `award_item`（後者為自由文字，不在合法清單內）
- 當 H 欄需要備註（值在 `GENERAL_BOOKS_H_REQUIRES_NOTES` 內），`award_notes` 不可空
- 若書商書單缺少 `award_template` 欄，`recommendation_source` 為空，匯出前檢查阻擋

---

## 欄位語意對照

| 來源書單欄位 | DB 欄位 | 匯出對應 | 說明 |
|------------|--------|---------|------|
| `eligible_label` | `eligibility_label` | A 欄 | 必選/推薦/自選 |
| `award_template` | `recommendation_source` | H 欄 | H 欄下拉合法值（見上方語意釐清） |
| `topic` | `policy_topic` | I 欄 | 重要政策/議題 |
| `定價` | `list_price` | J 欄 | |
| `award_notes` | `award_notes` | L 欄 | H 欄需備註時使用 |
| `獲獎項目` | `award_item` | **不匯出**（原始多行文字，參考用） | 不可輸出至 H 欄 |
| `summary_80_120` | `summary` | 不匯出（選書判斷用） | |

---

## 現況調查結論

| 項目 | 現況 | 需做的事 |
|------|------|---------|
| `project_type = general_books` 後端允許 | ✅ projects.py 已有 | 無 |
| projects.html 建立 general_books | ❌ `disabled` | 移除 `disabled` |
| export_templates schema 支援 general_books | ✅ migration 002 已有 CHECK | 無 |
| general_books export template（config + seed） | ❌ config.yaml 無 | 新增 |
| `recommendation_source` HINTS | ✅ 已有 | 無 |
| `eligibility_label` HINTS | ✅ 已有 | 無 |
| `award_notes` HINTS | ❌ 缺漏 | 新增 |
| `eligibility_label` SYSTEM_FIELDS | ❌ 缺漏 | 新增 |
| `recommendation_source` SYSTEM_FIELDS | ❌ 缺漏 | 新增 |
| `award_notes` SYSTEM_FIELDS | ❌ 缺漏 | 新增 |
| export_general_books() 函式 | ❌ 不存在 | 新增 |
| exports.py 依 project_type 分流 | ❌ 硬編碼 local_culture | 新增分流 |
| validation_service general_books 規則 | ❌ 現有規則為通用/local_culture 語意 | 新增分流 |
| selection.html 顯示 summary / policy_topic | ❌ 僅搜尋可用，卡片不顯示 | 新增顯示 |
| selection.html 可編輯 eligibility_label / recommendation_source / award_notes | ❌ 無 | 新增覆寫欄位 |
| Migration | 不需要 — 所有欄位已存在 | 無 |

---

## 需求範圍

### 1. projects.html：啟用一般圖書採購選項

移除 `<option value="general_books" disabled>` 的 `disabled` 屬性。

### 2. import.html：補齊 SYSTEM_FIELDS

新增三個欄位至 `SYSTEM_FIELDS`：

```js
{key:'eligibility_label',     label:'必選/推薦（A欄）', required:false},
{key:'recommendation_source', label:'H欄獲獎代碼',      required:false},
{key:'award_notes',           label:'備註（L欄）',      required:false},
```

### 3. import_service.py：補齊 VENDOR_COLUMN_HINTS

新增 `award_notes` 對應：

```python
"award_notes": ["award_notes", "備註", "notes"],
```

### 4. config.yaml：新增 general_books 匯出範本

```yaml
export_templates:
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

`school_name_cell` 與 `approved_budget_cell` 設為空字串，export function 跳過寫入。

### 5. export_service.py：新增 export_general_books()

- 從 export_templates 載入 general_books 範本
- 根據 column_mappings 寫入各欄
- A 欄 ← `eligibility_label`
- H 欄 ← `recommendation_source`（值必須在允許清單內）
- I 欄 ← `policy_topic`
- L 欄 ← `award_notes`
- K 欄 ← 小計（quantity × price）

**H 欄合法值常數（hardcode，來源：範本 N5:N13）**

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

### 6. exports.py router：依 project_type 分流

讀取 project 的 `project_type`，決定呼叫 `export_local_culture()` 或 `export_general_books()`。

### 7. validation_service.py：依 project_type 套用規則

`check_export_readiness(project_id, price_field)` 內部查詢 `project_type` 後分流。

**general_books 阻擋條件（missing_required / can_export=False）：**
- 書名空
- 定價空（依 price_field）
- 採購數量 ≤ 0
- `eligibility_label` 空（A 欄缺漏）
- `recommendation_source` 不在 `GENERAL_BOOKS_H_ALLOWED` 內（H 欄非法或空）
- H 欄需要備註（`recommendation_source` 在 `GENERAL_BOOKS_H_REQUIRES_NOTES`）但 `award_notes` 空

**general_books 提示條件（needs_review）：**
- 作者空
- 出版社空
- ISBN 無效/缺失

### 8. selection.html：書卡顯示 summary 與 policy_topic

書卡（卡片 render 函式）加入：
- summary：若有值，顯示為縮排文字段落（限制顯示行數或折疊）
- policy_topic：若有值，以 tag/badge 形式顯示

適用所有 project_type（local_culture 書目若有 summary 亦可受益）。

### 9. selection.html：書卡可覆寫 eligibility_label / recommendation_source / award_notes

**後端 endpoint 已存在**：`PATCH /api/selections/{selection_id}/overrides` 接受任意 `overrides` dict，自動 merge 至 `user_overrides`。`_resolve_field()` 在匯出時優先讀取 overrides，支援任何欄位名稱。無需新增後端程式碼。

在書卡 override 編輯介面加入三個欄位（純前端修改）：
- `eligibility_label`：`<select>`（必選/推薦/自選）
- `recommendation_source`：`<select>`（9 個 H 欄允許值，與 `GENERAL_BOOKS_H_ALLOWED` 常數一致）
- `award_notes`：`<input type="text">`

覆寫值透過 PATCH endpoint 存入 `user_overrides`，保存後重新整理書卡狀態。

**注意**：此 override UI 對所有 project_type 可見。local_culture 使用者填入無害（export_local_culture 不讀這幾個欄位）。

### 11. selection.html：採購類別篩選（general_books 專用）

在篩選列新增「採購類別」下拉選單（全部 / 必選 / 推薦 / 自選），只在 `project_type === 'general_books'` 時顯示。

**`getPurchaseCategory(book)` 邏輯（優先順序）：**

1. 優先使用 `eligibility_label`（來自匯入書單，已整理為今年規則）
2. 若 `eligibility_label` 空白，才 fallback 依 `recommendation_source` 推導：
   - `喜閱網` → 必選
   - `學校自選(請備註原因)` → 自選
   - 其他有值 → 推薦
   - 空白 → ''

**設計原則：**
- 優先 `eligibility_label` 保持規則靈活性：明年教育局若調整哪個 H 欄值對應哪個類別，只需更新書單的 `eligible_label` 欄位，不需改程式中的推導規則
- `recommendation_source` 推導僅作為沒有 `eligibility_label` 資料的 fallback

### 10. export.html：依 project_type 隱藏不適用輸入欄

目前 export.html 無條件顯示「學校名稱」與「核定金額」兩個輸入欄。general_books 範本無對應儲存格，export_general_books() 跳過寫入，但 UI 仍顯示這兩個欄位造成誤解。

調整：
- 頁面載入時讀取 `proj.project_type`
- 若 `project_type === 'general_books'`：隱藏學校名稱 / 核定金額輸入欄（含 label）
- 若 `project_type === 'local_culture'`：維持現有顯示不變
- 不影響其他欄位（定價欄/小計計算方式/匯出按鈕）

---

## 降級策略

| 缺漏狀況 | 行為 |
|---------|------|
| 無 `topic` / `policy_topic` | I 欄空白，選書仍可進行，匯出不阻擋 |
| 無 `summary` | 卡片不顯示摘要段落，不阻擋 |
| 無 `award_template` / `recommendation_source` | 匯出前檢查阻擋（缺 H 欄值） |
| `recommendation_source` 不在允許清單內 | 匯出前檢查阻擋（H 欄非法值） |
| 無 `eligibility_label` | 匯出前檢查阻擋（缺 A 欄值） |
| H 欄需備註但無 `award_notes` | 匯出前檢查阻擋 |

---

## 不做的事

- 不大幅重構 export_service（export_local_culture 不動）
- 不做多選 eligibility_label 或 H 欄
- 不自動生成 summary 或 policy_topic
- 不強制所有書商書單有 award_template
- 不刪除或破壞 local_culture 採購流程
- 不處理多校雲端帳號/權限
- 不改清除來源資料行為
- 不修改 migration（現有欄位已足夠）
- 不大幅改動 export.html（僅依 project_type 隱藏學校名稱/核定金額，其餘不動）
- 不引入新的 Python 依賴

---

## 驗收條件

1. `python -m compileall app` pass
2. 可建立 `project_type = general_books` 專案
3. 匯入預設一般圖書書單後：
   - `eligibility_label` / `recommendation_source` / `policy_topic` / `summary` / `award_notes` 正確寫入 `vendor_books`
   - selection_items snapshot 也包含上述欄位
4. 選書頁書卡顯示 summary 與 policy_topic（有值才顯示）
5. 書卡可覆寫 `eligibility_label` / `recommendation_source` / `award_notes`
6. export-check.html 顯示 general_books 特有的阻擋條件（缺 A/H 欄、H 欄非法、備註必填）
7. 可匯出一般圖書 Excel，A/H/I/J/K/L 欄正確
8. 匯出的 H 欄值在範本 N5:N13 允許清單內
9. 不符合 H 欄合法值的書目不會靜默輸出，匯出前被阻擋
10. local_culture 既有流程不受影響
