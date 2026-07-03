# 書商獲獎欄位整理功能評估報告

日期：2026-07-03

## 背景

評估來源檔案：

`00_source/必選推薦-欄位調整-topic-summary-v6-final.xlsx`

本次評估聚焦於 Excel 中：

- A 欄 `獲獎項目`：通常是書商提供的原始獎項名稱、推薦來源或主題標籤。
- R 欄 `award_template`：教育局規定採購書單應使用的官方獲獎名稱。
- S 欄 `eligible_label`：必選、推薦、自選。
- T 欄 `award_notes`：當官方欄位需要備註時，放入原始獎項名稱或原因。

使用者希望評估是否能在採購系統內新增「整理書單」功能，讓老師在匯入書商書單時，可以把書商提供的 A 欄值整理成教育局要求的 R 欄官方值。

## 資料分析摘要

此 Excel 工作表共有 6,750 筆資料。

A 欄 `獲獎項目`：

- 唯一值數量：386 種
- 來源型態包含：
  - 直接獎項名稱，例如 `2025年好書大家讀`、`2024年金鼎獎`
  - 政策或主題標籤，例如 `SEL情緒`、`SDGS/優質教育品質`
  - 多行複合來源，例如 `文化部第47屆中小學生優良讀物` 加上 `2024年好書大家讀`
  - 自選標示，例如 `自選`

R 欄 `award_template`：

- 唯一值數量：8 種
- 代表教育局允許或要求使用的官方獲獎名稱

R 欄主要分布：

| 官方值 | 筆數 |
|---|---:|
| 學校自選(請備註原因) | 3278 |
| 圖書分級推薦書目、臺灣歷史文化分級推薦書目 | 1127 |
| 文化部中小學生優良課外讀物選介 | 993 |
| 其他國內外具公信力單位辦理之獎項(請備註獎項名稱) | 481 |
| 好書大家讀 | 353 |
| 國民中小學新生閱讀推動活動入選書單 | 321 |
| 喜閱網 | 168 |
| 金鼎獎 | 29 |

S 欄 `eligible_label` 分布：

| 值 | 筆數 |
|---|---:|
| 推薦 | 3296 |
| 自選 | 3286 |
| 必選 | 168 |

## A 欄與 R 欄的關聯

A 欄與 R 欄不是單純的一對一搬移，而是「多種書商文字收斂到少數官方分類」。

觀察到的穩定規則：

| A 欄特徵 | 建議 R 欄 |
|---|---|
| `自選` | 學校自選(請備註原因) |
| 包含 `金鼎獎` | 金鼎獎 |
| 包含 `好書大家讀` | 好書大家讀 |
| 包含 `喜閱網` | 喜閱網 |
| 包含 `文化部第...屆中小學生優良讀物` | 文化部中小學生優良課外讀物選介 |
| 包含 `國教署`、`國民中小學新生`、`新生閱讀入選` | 國民中小學新生閱讀推動活動入選書單 |
| 無法對應但具獎項性質 | 其他國內外具公信力單位辦理之獎項(請備註獎項名稱) |

但資料中也存在衝突：

- A 欄唯一值 386 種，其中 366 種穩定對到單一 R 欄。
- 有 20 種 A 欄文字在資料中對到不同 R 欄。
- 若只用「同一 A 欄文字的多數決」轉換，整體準確率約 97.61%，仍約有 161 筆會被錯誤轉換。

衝突集中在主題標籤，例如：

| A 欄值 | 主要對應 | 其他對應 |
|---|---:|---:|
| SEL情緒 | 圖書分級推薦書目、臺灣歷史文化分級推薦書目 349 筆 | 其他國內外具公信力單位辦理之獎項 29 筆 |
| SDGS/優質教育品質 | 圖書分級推薦書目、臺灣歷史文化分級推薦書目 314 筆 | 其他國內外具公信力單位辦理之獎項 62 筆 |
| SDGS/陸地生態 | 圖書分級推薦書目、臺灣歷史文化分級推薦書目 63 筆 | 其他國內外具公信力單位辦理之獎項 11 筆 |
| SDGS/就業與經濟成長 | 圖書分級推薦書目、臺灣歷史文化分級推薦書目 15 筆 | 其他國內外具公信力單位辦理之獎項 15 筆 |

因此，系統不應只做靜默自動轉換。較好的做法是：自動建議、標示信心、讓老師批次確認或覆寫。

## 現有系統狀態

目前系統已有可承接整理結果的欄位：

- `award_item`：可保存書商原始獲獎項目。
- `recommendation_source`：可保存教育局官方獲獎名稱，匯出一般圖書書單時使用。
- `eligibility_label`：可保存必選、推薦、自選。
- `award_notes`：可保存備註。

相關位置：

- `app/services/import_service.py`
- `app/static/import.html`
- `app/static/selection.html`
- `app/services/export_service.py`
- `app/services/validation_service.py`

目前缺口不是資料欄位，而是「匯入時將書商原始欄位整理成官方欄位」的流程與規則。

## 建議功能設計

功能名稱建議：

`整理書單`

入口位置：

- 放在 `匯入` 頁面的「書商書單」流程中。
- 建議在「確認欄位對應」之後、「正式匯入」之前新增按鈕或步驟。
- 老師選好 A 欄來源欄位後，按下「整理書單」，系統產生整理建議。

建議流程：

1. 老師上傳書商 Excel。
2. 系統偵測標題列與欄位。
3. 老師確認欄位對應，至少對應書名、ISBN 或書名，以及原始獲獎項目欄位。
4. 老師按「整理書單」。
5. 系統依原始 A 欄分組，不逐筆顯示全部 6,750 筆。
6. 每一組顯示：
   - 書商原始獲獎文字
   - 筆數
   - 系統建議的官方獲獎名稱
   - 建議的必選/推薦/自選
   - 建議備註
   - 信心等級
   - 是否需要老師確認
   - 範例書名
7. 老師可批次修改某一組的官方獲獎名稱與備註。
8. 老師確認後正式匯入。
9. 系統寫入：
   - 原始 A 欄到 `award_item`
   - 整理後官方值到 `recommendation_source`
   - 必選/推薦/自選到 `eligibility_label`
   - 備註到 `award_notes`

## 規則設計建議

建議新增一個規則服務，而不是把規則全部寫死在匯入頁面。

服務名稱可為：

`award_normalization_service.py`

核心函式概念：

```python
normalize_award(raw_award, project_type, profile_id=None)
```

回傳資料建議包含：

```json
{
  "raw_award": "2025年好書大家讀",
  "recommendation_source": "好書大家讀",
  "eligibility_label": "推薦",
  "award_notes": null,
  "confidence": 0.95,
  "needs_review": false,
  "matched_rule": "contains:好書大家讀"
}
```

建議新增資料表：

`award_normalization_rules`

欄位建議：

| 欄位 | 用途 |
|---|---|
| `id` | 規則 ID |
| `project_type` | 適用專案類型，例如 `general_books` |
| `profile_id` | 可選，綁定特定書商或匯入設定 |
| `raw_pattern` | 原始文字或比對樣式 |
| `match_type` | `exact`、`contains`、`regex` |
| `normalized_award` | 對應官方獲獎名稱 |
| `eligibility_label` | 必選、推薦、自選 |
| `award_notes_mode` | `empty`、`raw_award`、`custom` |
| `custom_award_notes` | 自訂備註文字 |
| `priority` | 規則優先順序 |
| `confidence` | 信心分數 |
| `enabled` | 是否啟用 |
| `created_at` / `updated_at` | 維護時間 |

規則優先順序建議：

1. 老師或管理者自訂規則
2. 特定書商或匯入 profile 規則
3. 系統內建 exact 規則
4. 系統內建 contains / regex 規則
5. 多數決建議
6. 無法辨識時歸入「其他國內外具公信力單位辦理之獎項」

## UI 建議

匯入頁面可新增一個按鈕：

`整理書單`

建議出現時機：

- 書商書單已上傳
- 欄位對應已確認
- 至少能取得原始獲獎項目欄位

按鈕動作：

- 呼叫後端整理預覽 API。
- 顯示「整理結果」區塊或 modal。

整理結果畫面建議以分組表格呈現：

| 原始獲獎項目 | 筆數 | 建議官方名稱 | 必選/推薦/自選 | 備註 | 狀態 |
|---|---:|---|---|---|---|
| 2025年好書大家讀 | 175 | 好書大家讀 | 推薦 |  | 已自動整理 |
| SEL情緒 | 378 | 圖書分級推薦書目、臺灣歷史文化分級推薦書目 | 推薦 |  | 需確認 |
| 自選 | 3278 | 學校自選(請備註原因) | 自選 |  | 已自動整理 |

狀態建議：

- 已自動整理
- 需確認
- 無法辨識
- 老師已覆寫

老師可對每組操作：

- 修改官方獲獎名稱
- 修改必選/推薦/自選
- 修改備註
- 套用到同原始值的所有書
- 將此對應儲存為規則，供下次匯入使用

## 驗證重點

實作後至少應驗證：

1. 匯入 `必選推薦-欄位調整-topic-summary-v6-final.xlsx`。
2. 原始 A 欄值保留在 `vendor_books.award_item`。
3. 整理後 R 欄官方值寫入 `vendor_books.recommendation_source`。
4. S 欄或推論結果寫入 `vendor_books.eligibility_label`。
5. 需要備註的官方值正確寫入 `vendor_books.award_notes`。
6. `SEL情緒`、`SDGS/...` 等衝突值會標示 `needs_review`，不應完全靜默套用。
7. 選書頁仍可單本覆寫 `recommendation_source`、`eligibility_label`、`award_notes`。
8. 匯出一般圖書採購書單時，官方欄位只使用 `recommendation_source`，不可誤用原始 `award_item`。
9. 現有 tests 通過，並新增獎項整理服務測試。

## 建議交給 Agent 產出 Spec / Plan 的提示詞

```text
請依本專案規則先讀 docs/PROJECT_RULES.md、docs/STATUS.md，並依 current_action 執行對應流程。

目標：
規劃一個「整理書單」功能，放在匯入頁面的書商書單流程中，讓老師可以按一個按鈕，將書商提供的原始獲獎項目欄位整理成教育局規定的官方獲獎名稱。

背景：
請閱讀 docs/reports/award-normalization-import-feature-evaluation.md。
來源 Excel 為 00_source/必選推薦-欄位調整-topic-summary-v6-final.xlsx。
其中 A 欄通常是書商提供的原始獲獎項目，R 欄 award_template 是教育局規定使用的官方獲獎名稱。
A 欄值可能因不同書商而不同，因此功能不能只靠固定欄位搬移，必須支援自動建議、信心標示、人工覆核與規則累積。

任務：
請準備新的 task spec 與 task plan markdown，不要直接實作程式碼。

建議 task-id：
task-import-award-normalization

規劃範圍：
1. 在匯入頁面 app/static/import.html 的書商書單流程中加入「整理書單」按鈕或步驟。
2. 整理功能應在欄位對應後、正式匯入前執行。
3. 後端需提供整理預覽 API，根據原始獲獎項目欄位產生分組整理結果。
4. 整理結果以原始獲獎項目分組，不逐筆顯示全部書目。
5. 每組需顯示原始獲獎項目、筆數、範例書名、建議官方獲獎名稱、建議 eligibility_label、建議 award_notes、confidence、needs_review。
6. 老師可修改每組的官方獲獎名稱、必選/推薦/自選與備註，並套用到同組書目。
7. 正式匯入時，原始值保留到 award_item，整理後官方值寫入 recommendation_source，必選/推薦/自選寫入 eligibility_label，備註寫入 award_notes。
8. 規劃是否新增 award_normalization_service.py。
9. 規劃是否新增 award_normalization_rules migration，以支援系統內建規則、書商 profile 規則與老師儲存規則。
10. 不破壞現有 selection.html 單本覆寫功能。
11. 不改變 export_general_books 的原則：匯出官方獲獎欄位時只使用 recommendation_source，不直接使用原始 award_item。

需要分析的現有檔案：
- app/services/import_service.py
- app/routers/imports.py
- app/static/import.html
- app/static/selection.html
- app/services/export_service.py
- app/services/validation_service.py
- migrations/
- tests/

Spec 需說明：
- 使用者故事
- 功能範圍
- 非目標
- 資料模型變更
- API 行為
- UI 流程
- 轉換規則策略
- 衝突與低信心資料如何處理
- 驗證與測試標準

Plan 需說明：
- 實作步驟
- 影響檔案
- migration 設計
- 後端服務設計
- 前端流程設計
- 測試項目
- 風險與回復方式

驗證方式：
1. 使用 00_source/必選推薦-欄位調整-topic-summary-v6-final.xlsx 作為手動驗證資料。
2. 確認 A 欄原始值保留在 award_item。
3. 確認整理後官方值寫入 recommendation_source。
4. 確認自選資料轉為 eligibility_label=自選，recommendation_source=學校自選(請備註原因)。
5. 確認包含 金鼎獎、好書大家讀、喜閱網、文化部中小學生優良讀物、新生閱讀 等文字時可自動建議正確官方值。
6. 確認 SEL情緒、SDGS/優質教育品質 等衝突值會標示 needs_review。
7. 確認老師覆寫後，正式匯入採用覆寫值。
8. 確認匯出一般圖書書單時使用 recommendation_source。
9. 執行既有測試，並新增 award normalization 相關單元測試。

請只產出 spec / plan 文件與必要的 task 狀態更新；不要開始實作功能。
```
