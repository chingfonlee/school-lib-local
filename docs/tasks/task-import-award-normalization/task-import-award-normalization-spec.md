# Spec: task-import-award-normalization

## 目標

書商提供的書單中，獲獎項目欄位（`award_item`，對應書商 Excel A 欄）是書商自訂文字，種類多且不一致；教育局規定採購書單只能使用固定 9 種官方獲獎名稱（`vendor_books.recommendation_source`，對應 `app/static/selection.html` 的 `H_ALLOWED` 清單）。目前匯入流程沒有任何機制協助老師把書商原始文字整理成官方名稱，老師只能在選書頁（`selection.html`）逐本手動修改。

本 task 在匯入頁面（`app/static/import.html`）的書商書單精靈中新增「整理書單」步驟，讓老師在欄位對應完成、正式匯入前，先依原始獲獎項目文字分組檢視系統建議的官方名稱、信心等級與是否需人工確認，並可批次修改後再匯入。

## 需求範圍

### 使用者故事

身為老師，在匯入書商書單時，我希望系統能先幫我把「獲獎項目」欄位的原始文字（例如「2025年好書大家讀」「SEL情緒」）整理成教育局規定的官方獲獎名稱，並清楚標示哪些是系統有把握的、哪些需要我自己確認，這樣我就不用匯入後再一本一本去選書頁修改。

### 功能範圍（V1）

1. **後端整理服務 `app/services/award_normalization_service.py`**
   - 提供 `normalize_award(raw_award: str) -> dict`：輸入書商原始獲獎文字，回傳建議的 `recommendation_source`、`eligibility_label`、`award_notes`、`confidence`（0~1）、`needs_review`（bool）、`matched_rule`。
   - 提供 `group_normalize(rows: list[dict]) -> list[dict]`：輸入本次匯入解析出的列（至少含 `award_item` 原始文字、書名），依原始文字分組（去除前後空白後精確比對），回傳每組的原始文字、筆數、範例書名（最多 3 筆）、建議結果、狀態（`auto` / `needs_review` / `unrecognized`）。
   - 比對規則優先順序：
     1. `自選`（去空白後完全等於「自選」）→ `學校自選(請備註原因)` / `自選`，高信心。
     2. 依 `docs/reports/award-normalization-import-feature-evaluation.md` 的「A 欄與 R 欄的關聯」表格，做 `contains` 比對（金鼎獎、好書大家讀、喜閱網、文化部第…屆中小學生優良讀物、國教署/國民中小學新生/新生閱讀入選）。
     3. 命中報告中列出的已知衝突值（例如 `SEL情緒`、`SDGS/...` 系列）→ 依報告中該值的多數對應做建議，但 `confidence` 降低、`needs_review = true`。
     4. 完全無法辨識 → 建議「其他國內外具公信力單位辦理之獎項(請備註獎項名稱)」、`eligibility_label = 推薦`、`needs_review = true`、`confidence` 低。
   - 內建規則（含上述四層）以資料表 `award_normalization_rules` 儲存（見下方資料模型），服務啟動時讀取啟用中的規則做比對；規則資料由 migration 於建表時一併寫入初始資料（seed），不在執行期動態寫入。

2. **後端 API**
   - 新增 `POST /api/imports/vendor-books/normalize-awards`：輸入與 `vendor-books/preview` 相同的檔案 + `sheet_name` + `header_row` + `mappings`（欄位對應），額外需要 `mappings.award_item` 與 `mappings.title` 已對應。輸出分組整理結果（見上）。此 API 純預覽，不寫入資料庫。
   - `POST /api/imports/vendor-books/confirm`（`app/routers/imports.py` 既有 endpoint）新增可選參數 `award_overrides`（JSON 字串，`{原始獲獎文字: {recommendation_source, eligibility_label, award_notes}}`）。`app/services/import_service.py` 的 `confirm_import()` 在組成每筆 `book` dict 時，若該筆 `award_item`（去空白後）存在於 `award_overrides`，以覆寫值取代原本從 `mappings.recommendation_source` / `mappings.eligibility_label` / `mappings.award_notes` 欄位讀到的值；未命中的列維持原欄位對應行為（不受影響）。

3. **前端 UI（`app/static/import.html`）**
   - 在既有精靈步驟 D（`step-D`，選擇額外欄位）與步驟 E（`step-E`，確認並正式匯入）之間，新增步驟 `step-award`「整理獲獎項目」。
   - 進入此步驟時：
     - 若目前欄位對應未包含 `award_item`，顯示提示「本次匯入未對應獲獎項目欄位，略過整理」並可直接「下一步」跳到 E。
     - 若已對應，顯示「整理書單」按鈕，按下後呼叫 `normalize-awards` API，以分組表格呈現：原始獲獎項目、筆數、範例書名、建議官方名稱、建議必選/推薦/自選、建議備註、狀態（已自動整理／需確認／無法辨識）。
   - 每組可用下拉選單修改官方名稱（沿用 `selection.html` 現有 9 項 `H_ALLOWED` 清單）與必選/推薦/自選，文字輸入修改備註；修改後該組狀態改為「老師已覆寫」，修改立即套用到該組（不需逐筆操作）。
   - 「需確認」與「無法辨識」狀態需視覺區分（例如色塊或標籤），並在頁面上方顯示尚有幾組待確認，未全部處理完仍可前進到下一步（不強制擋關），但需在下一步摘要中提示尚有未確認組數。
   - 老師確認整理結果後按「下一步」進入步驟 E；步驟 E 的「確認匯入」動作將整理結果一併以 `award_overrides` 傳給 `confirm` API。

4. **資料模型變更**
   - 新增 migration（`migrations/008_...`，實際編號依合併時最新序號決定），建立資料表 `award_normalization_rules`：

     | 欄位 | 型別 | 說明 |
     |---|---|---|
     | `id` | INTEGER PK | 規則 ID |
     | `project_type` | TEXT | 適用專案類型，V1 固定 `general_books`（`general_books_jh` 沿用同一組規則） |
     | `match_type` | TEXT | `exact` / `contains` |
     | `raw_pattern` | TEXT | 比對樣式 |
     | `normalized_award` | TEXT | 對應官方獲獎名稱（`recommendation_source`） |
     | `eligibility_label` | TEXT | 必選、推薦、自選 |
     | `award_notes_mode` | TEXT | `empty` / `raw_award` |
     | `priority` | INTEGER | 數字越小優先度越高 |
     | `confidence` | REAL | 0~1 |
     | `enabled` | INTEGER | 0/1 |
     | `created_at` / `updated_at` | TEXT | ISO8601 |

   - V1 不提供規則管理 UI；規則只能透過 migration seed 資料建立，不開放老師或管理者在畫面上新增/修改規則列（畫面上的「修改」只作用於本次匯入的分組結果，不寫回此表）。
   - 不新增 `profile_id` 欄位（書商 profile 專屬規則留待 V2 評估是否需要）。

### 轉換規則策略

依 `docs/reports/award-normalization-import-feature-evaluation.md` 的分析：386 種原始值中 366 種穩定對應單一官方值，20 種存在衝突（以 `SEL`、`SDGS` 開頭的主題標籤為主）。V1 策略：

- 對「穩定對應」類型（`自選`、含金鼎獎/好書大家讀/喜閱網/文化部/新生閱讀關鍵字）給高信心自動建議。
- 對已知衝突類型給低信心建議並標示 `needs_review`，強制老師看過分組表格再決定，不做靜默自動轉換。
- 對完全未知的原始文字，建議「其他…(請備註獎項名稱)」並標示 `needs_review`，備註預設帶入原始文字（`award_notes_mode = raw_award`）方便老師確認。

### 衝突與低信心資料如何處理

- 不在後端自動寫入衝突值的最終判斷；`needs_review = true` 的分組必須經過前端渲染呈現給老師，即使老師不修改、直接按下一步，也視為老師已檢視並接受系統建議（不阻擋流程）。
- 若老師在此步驟未進入過（例如未對應 `award_item` 欄位），`award_overrides` 為空，`confirm_import()` 行為與現行完全一致。

### 驗證與測試標準

- 使用 `00_source/必選推薦-欄位調整-topic-summary-v6-final.xlsx` 作為手動驗證資料（若檔案不在版控內，由使用者於驗證時提供路徑）。
- 新增 `award_normalization_service` 單元測試，至少覆蓋：
  - `自選` → `學校自選(請備註原因)` / `自選`，高信心。
  - 含「金鼎獎」「好書大家讀」「喜閱網」「文化部第…屆中小學生優良讀物」「新生閱讀」關鍵字的原始文字 → 對應官方值，高信心。
  - `SEL情緒`、`SDGS/優質教育品質` → `needs_review = true`。
  - 完全陌生文字 → 建議「其他…」、`needs_review = true`。
  - `group_normalize` 分組筆數、範例書名數量上限正確。
- 新增 `confirm_import()` 整合測試，驗證：
  - 未帶 `award_overrides` 時行為不變（既有測試需全數通過）。
  - 帶 `award_overrides` 時，命中的列 `recommendation_source` / `eligibility_label` / `award_notes` 依覆寫值寫入，未命中的列維持原欄位對應。
- 手動驗證：匯出一般圖書採購書單時，官方獲獎欄位只使用 `recommendation_source`（既有行為，`export_service.py`），確認本 task 不破壞此原則。
- 手動驗證：`selection.html` 單本覆寫 `recommendation_source` / `eligibility_label` / `award_notes` 功能不受影響。

## 不做的事

- 不做老師儲存對應為規則、供下次匯入自動套用（跨匯入持久學習規則），留待 V2 評估。
- 不做規則管理 UI（新增/修改/停用 `award_normalization_rules`），V1 規則只透過 migration seed 建立。
- 不新增書商 profile 專屬規則（`profile_id` 綁定），V1 所有 `general_books` / `general_books_jh` 專案共用同一組系統規則。
- 不修改 `local_culture` 專案類型的匯入流程；「整理書單」步驟只在對應到 `award_item` 欄位時出現，不特別限制 project_type，但實際規則只覆蓋 `general_books` 系列的 9 種官方值。
- 不修改 `import_vendor_books()`（`app/services/import_service.py` 中的單步驟舊版匯入函式）與 `POST /api/imports/vendor-books`（legacy 單步驟上傳 endpoint），本 task 只處理精靈式流程（`preview` → `confirm`）。
- 不強制「需確認」組別必須被老師修改才能繼續下一步；只要求呈現，不擋流程。
- 不在此 task 內處理 `award_item` 欄位本身的匯入偵測邏輯（`VENDOR_COLUMN_HINTS['award_item']`），沿用現有欄位對應機制。

## 驗收條件

1. 匯入頁面書商書單精靈中，欄位對應（步驟 C/D）已包含 `award_item` 對應時，步驟 D 與 E 之間出現「整理獲獎項目」步驟；未對應 `award_item` 時可直接略過，不影響現有匯入流程。
2. 按下「整理書單」後，系統依原始獲獎項目文字分組顯示：原始文字、筆數、範例書名、建議官方名稱、建議必選/推薦/自選、建議備註、信心/狀態標示。
3. `自選`、含「金鼎獎」「好書大家讀」「喜閱網」「文化部第…屆中小學生優良讀物」「新生閱讀」關鍵字的分組自動標示為「已自動整理」高信心建議。
4. `SEL情緒`、`SDGS/優質教育品質` 等已知衝突值標示為「需確認」，不被靜默自動套用。
5. 老師可在分組表格修改官方名稱、必選/推薦/自選、備註，並套用到同組所有書目；修改後狀態顯示「老師已覆寫」。
6. 正式匯入後，`vendor_books.award_item` 保留原始文字；`vendor_books.recommendation_source`、`eligibility_label`、`award_notes` 依整理結果（含老師覆寫）寫入。
7. 未進入「整理獲獎項目」步驟（例如未對應 `award_item`）時，匯入行為與本 task 實作前完全一致。
8. `selection.html` 單本覆寫 `recommendation_source` / `eligibility_label` / `award_notes` 功能不受影響。
9. 匯出一般圖書採購書單時，官方獲獎欄位仍只使用 `recommendation_source`，不直接使用 `award_item`。
10. 既有測試（`python -m pytest -q`）全數通過，新增 `award_normalization_service` 與 `confirm_import()` override 相關測試。
