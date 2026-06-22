# Spec: task-test-import-service-fixtures

## 目前問題

`import_service.py` 的匯入流程（欄位對應、空白列過濾、completeness 計算、DB 寫入）目前全靠手動驗證。已完成的 `task-test-foundation-core-services` 覆蓋了 `compute()` 與 `_resolve_project_type()`，但 import_service 的 helper 與最終寫入路徑尚未有自動化測試，容易回歸。

## 測試目標

- 補充 import_service 純函式 helper 的測試覆蓋
- 以最小成本驗證 `confirm_import()` 的欄位對應與 project_type completeness 行為
- 保持「小而穩」原則，不引入複雜 fixture 系統

## 測試範圍

### Tier 1：純函式測試（必做）

以下 helper 無 DB 相依，可直接 import 測試：

**`_match_columns()` — VENDOR_COLUMN_HINTS 欄位對應**

重點覆蓋一般圖書採購新增欄位（同時是容易被遺漏或拼錯的欄位）：

| 欄位 | 測試用欄名（Excel header 範例） |
|------|------|
| `eligibility_label` | `"eligible_label"`（hints 第一位）、`"必選推薦"` |
| `recommendation_source` | `"award_template"`（hints 第一位）、`"推薦來源"` |
| `award_notes` | `"award_notes"`（完全一致）、`"備註"` |
| `policy_topic` | `"topic"`、`"議題"` |
| `summary` | `"summary_80_120"`（hints 第一位）、`"摘要"` |

額外情境：
- 欄名大小寫與空白應被正規化（如 `" Summary_80_120 "` 仍能對應到 `summary`）
- 無任何已知欄名 → mapping 為空，全部欄位列於 unmapped

**`_is_blank_or_total_row()` — 空白列與合計列過濾**

| 情境 | 輸入 | 預期 |
|------|------|------|
| 全空值 | `[None, "", None]` | `True` |
| 含「合計」 | `["合計", "100"]` | `True` |
| 含「總計」 | `["總計"]` | `True` |
| 正常書目列 | `["某書", "作者甲", "出版社乙"]` | `False` |

### Tier 2：confirm_import 最小路徑（條件做）

若 monkeypatch + in-memory SQLite 方案成本可控，補測 `confirm_import()` 的端到端寫入行為：

- 使用 `openpyxl` 在測試中動態產生最小 xlsx bytes（2 欄位資料列）
- 使用 `monkeypatch.setattr("app.services.import_service.get_connection", ...)` 替換為 in-memory SQLite
- 使用 `monkeypatch.setattr("app.services.import_service.run_match", ...)` 讓 `run_match` 回傳 `{}`（避免複雜比對邏輯）
- 建立最小 schema（`procurement_projects`、`import_batches`、`vendor_books`、`book_matches`）

**驗證項目：**

| 情境 | 驗證 |
|------|------|
| general_books 專案匯入含 eligibility_label / recommendation_source | vendor_books 對應欄位寫入正確值 |
| general_books 專案匯入含 award_notes / policy_topic / summary | vendor_books 對應欄位寫入正確值 |
| general_books 專案，eligibility_label 與 recommendation_source 均有值 | completeness_status = `"needs_review"`（缺 author/publisher）或 `"export_ready"` |
| general_books 專案，缺 eligibility_label | completeness_status = `"missing_required"` |

若 Tier 2 的 monkeypatch 與 schema 設置超過 60 行 fixture 準備，或需要 mock 多於 2 個相依，則降級為「延後」，不強行實作。

## 附帶 Bug 修正

分析 `confirm_import()` 與 `import_vendor_books()` 時，發現兩處傳給 `compute_completeness()` 的 `book` dict 均缺少 `eligibility_label` 與 `recommendation_source`，導致 general_books 專案匯入後 completeness 永遠落入 `missing_required`，與實際規則不符。

本 task 採 **Option A**：在新增測試的同一 task 內修正此 bug。理由：修正範圍極小（兩處各補 2 行），且 Tier 2 測試可直接作為回歸保護。修正目標：`confirm_import()` L276–283 與 `import_vendor_books()` L496–503 的 `book` dict 各補入 `eligibility_label` 與 `recommendation_source`。

## 不做的事

- 不做 FastAPI TestClient router 測試
- 不做 Playwright / 瀏覽器 E2E
- 不使用大型真實 Excel 檔案
- 不測完整匯出 Excel
- 不建立大型 fixture 系統
- 不引入 coverage / tox / CI
- 不重構 import_service 架構
- 不測試 `import_library_holdings()`（成本較高，留待後續）

## 驗收條件

1. `python -m pytest -v` 執行通過，0 failures
2. Tier 1 測試全部完成：`_match_columns()` 覆蓋 5 個 general_books 欄位、大小寫正規化、無對應情境；`_is_blank_or_total_row()` 覆蓋 4 個情境
3. `confirm_import()` 與 `import_vendor_books()` 的 `book` dict 已補入 `eligibility_label` 與 `recommendation_source`
4. 若 Tier 2 實作：`confirm_import()` 驗證 general_books completeness 使用正確規則；fixture 設置不超過 60 行
5. 若 Tier 2 延後：spec/plan 明確記錄延後理由，不影響 Tier 1 與 bug 修正驗收
6. `python -m compileall app` 執行通過
7. git status 僅包含本 task 預期變更（tests/ 下新增檔案、import_service.py bug 修正）
