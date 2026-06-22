# Spec: task-general-books-completeness

## 目標

修正一般圖書採購（project_type=general_books）的三類顯示與資料缺口：
1. 匯入時 `award_notes` 未寫入 `vendor_books`（資料 bug）
2. 選書頁完整度 badge 對 general_books 顯示錯誤（completeness_service 不知 project_type）
3. 選書頁修正表單欄位對所有類型一律相同（缺欄位差異化）

附帶修正 `export.html` 警告文字說「排除」而非「留空」。

## 問題現象

**問題 1 — award_notes 匯入缺漏（bug）**

`import_service.py` 的 `confirm_import()` 與 `import_vendor_books()` 的 SQL INSERT 均未包含 `award_notes` 欄位，儘管 `VENDOR_COLUMN_HINTS` 已定義 `"award_notes": ["award_notes", "備註", "notes"]`，`vendor_books` 資料表也有 `award_notes TEXT` 欄位（migration 001）。匯入後 `vendor_books.award_notes = NULL`；若 H欄選了需備註的值（例如「其他國內外具公信力單位辦理之獎項」），`validation_service` 將因備註空白而阻擋匯出。

**問題 2 — completeness badge 不符 general_books 驗證邏輯**

`completeness_service.compute()` 只以 `award_item` 判斷 `needs_review`，不檢查 `eligibility_label`（A欄）與 `recommendation_source`（H欄）。general_books 書目即使缺少 A/H 欄，選書頁仍可能顯示 `export_ready`，與 `validation_service.check_export_readiness()` 的實際驗證結果不一致，造成使用者誤判。

**問題 3 — 修正表單欄位無差異**

`selection.html` 的 `render()` 與 `renderClearedItems()` 無論 `projectType` 為何，皆同時顯示 `award_item`、`eligibility_label`、`recommendation_source`、`award_notes` 四個欄位。general_books 用不到 `award_item`；local_culture 用不到後三欄，造成介面混淆。

## 使用者期望行為

- 匯入含備註欄位的書單後，`vendor_books.award_notes` 有正確值，匯出 L欄不為空
- general_books 採購的書目，若缺少 A欄（eligibility_label）或 H欄（recommendation_source），選書頁顯示 `missing_required` badge
- general_books 採購的書目，若 A/H 欄均有值且 title/price/author/publisher 完整，選書頁顯示 `export_ready`
- general_books 修正表單顯示 eligibility_label（A欄）、recommendation_source（H欄）、award_notes（L欄），不顯示「獲獎項目」
- local_culture 修正表單顯示「獲獎項目」（award_item），不顯示 A/H/L 三欄
- export.html 警告文字改為「欄位將留空」，不再說「排除」

## 需求範圍

**後端 — import_service.py（bug 修正）**

`confirm_import()` 與 `import_vendor_books()` 的 INSERT SQL 各補上 `award_notes` 欄位名稱與 `get_field("award_notes")` 參數（最小修改：各補一個欄位、一個參數）。

**後端 — completeness_service.py**

`compute()` 加入 `project_type: str | None = None` 參數，新增 general_books 分支：

- 缺 `eligibility_label` 或 `recommendation_source` → `missing_required`
- 缺 `author` 或 `publisher` → `needs_review`
- 否則 → `export_ready`

local_culture 及其他類型維持現有邏輯不變。

**後端 — import_service.py（project_type 傳遞）**

`confirm_import()` 與 `import_vendor_books()` 呼叫 `compute_completeness` 前，先從 DB 查詢 `project` 的 `project_type`，並傳入 `compute_completeness(book, project_type=proj_type)`。`recompute_for_book()` 同步修正（從 vendor_books join import_batches join procurement_projects 取得 project_type）。

**前端 — selection.html**

`render()` 與 `renderClearedItems()` 依 `projectType` 條件顯示/隱藏欄位：
- general_books：隱藏 `award_item` 欄位列，顯示 eligibility_label / recommendation_source / award_notes
- local_culture（及其他）：顯示 `award_item`，隱藏 eligibility_label / recommendation_source / award_notes

**前端 — export.html（附帶修正）**

L147 警告文字「匯出時將自動排除這些書目。」改為「欄位將留空，請確認後再匯出。」

## 不做的事

- 不修改 `validation_service.py`（general_books 匯出驗證邏輯已正確）
- 不修改匯出流程（排除/留空邏輯不動）
- 不修改 `routers/imports.py` 的 `import_profiles` project_type 硬碼問題（低優先，獨立範圍）
- 不對已存在的 `vendor_books.completeness_status` 執行一次性 backfill SQL

## 驗收條件

1. 匯入含備註（L欄）欄位的書單後，`vendor_books.award_notes` 有正確值，匯出 L欄不為空
2. general_books 採購的書目，若缺少 `eligibility_label` 或 `recommendation_source`，選書頁顯示 `missing_required` badge
3. general_books 採購的書目，若 A/H 欄均有值且 title/price/author/publisher 完整，選書頁顯示 `export_ready`
4. general_books 修正表單不顯示「獲獎項目」欄位列，顯示 A/H/L 三欄（eligibility_label、recommendation_source、award_notes）
5. local_culture 修正表單顯示「獲獎項目」欄位列，不顯示 A/H/L 三欄
6. `renderClearedItems()` 快照區塊的修正表單與 `render()` 一致，同樣依 `projectType` 條件顯示欄位
7. 使用者儲存書目 overrides 後，`completeness_status` 依正確的 project_type 邏輯重算（recompute_for_book 修正）
8. `export.html` 警告文字為「欄位將留空，請確認後再匯出。」，不再說「排除」
9. `python -m compileall app` 執行無錯誤
