# Spec: task-import-profiles-project-type

## 目標

修正 `app/routers/imports.py` 的 `confirm_vendor_books()` 在儲存匯入設定檔（import_profiles）時，`project_type` 欄位硬碼為 `'local_culture'`，導致 general_books 專案儲存的 profile 紀錄 project_type 錯誤。

## 問題現象

`confirm_vendor_books()` 的 save_profile 區塊（L70–80 附近）執行以下 INSERT：

```sql
INSERT OR IGNORE INTO import_profiles
(name, file_type, column_mappings, project_type, source_type, ...)
VALUES (?, 'vendor_books', ?, 'local_culture', 'excel', ...)
```

`project_type` 位置硬碼為字串 `'local_culture'`。使用 general_books 專案儲存 profile 時，DB 中該筆記錄的 `project_type` 會被存為 `'local_culture'`，與實際專案類型不符。

## 使用者期望行為

general_books 專案儲存的 import profile，`project_type` 欄位應為 `'general_books'`；local_culture 專案儲存的則為 `'local_culture'`。

## 需求範圍

`app/routers/imports.py`：

在 save_profile 區塊執行 INSERT 之前，以 `project_id` 查詢 `procurement_projects` 取得實際 `project_type`，取代硬碼值。若查無對應 project，沿用 `'local_culture'` 作為安全降級（不中斷匯入流程）。

## 不做的事

- 不修改 import_profiles 的其他欄位或邏輯
- 不對已存在的錯誤 profile 記錄進行 backfill（`INSERT OR IGNORE` 不更新既有記錄；使用者刪除後重存即可修正）
- 不修改 profile 載入或套用邏輯

## 驗收條件

1. general_books 專案儲存 import profile 後，`import_profiles.project_type` 欄位值為 `'general_books'`
2. local_culture 專案儲存 import profile 後，`import_profiles.project_type` 欄位值為 `'local_culture'`
3. `project_id` 查無對應 `procurement_projects` 時，儲存 profile 不中斷，`import_profiles.project_type` 使用 `'local_culture'`
4. `python -m compileall app` 執行無錯誤
