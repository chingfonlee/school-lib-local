# Plan: task-import-profiles-project-type

## 實作步驟

### 步驟 1：修改 app/routers/imports.py 的 save_profile 區塊

目標位置：`confirm_vendor_books()` 函式，L70–86 的 `if save_profile and profile_name:` 區塊。

**1-1. 在 `conn = get_connection()` 之後、INSERT 之前，加入 project_type 查詢：**

```python
proj_row = conn.execute(
    "SELECT project_type FROM procurement_projects WHERE id = ?", (project_id,)
).fetchone()
proj_type = proj_row["project_type"] if proj_row else "local_culture"
```

**1-2. 將 INSERT 的 `'local_culture'` 改為佔位符 `?`，並在 VALUES tuple 加入 `proj_type`：**

舊：
```python
"VALUES (?, 'vendor_books', ?, 'local_culture', 'excel', ?, ?, ?, ?, ?)",
(
    profile_name,
    json.dumps(mappings_dict, ensure_ascii=False),
    header_row,
    json.dumps(mappings_dict, ensure_ascii=False),
    json.dumps(extra_list, ensure_ascii=False),
    now,
    now,
),
```

新：
```python
"VALUES (?, 'vendor_books', ?, ?, 'excel', ?, ?, ?, ?, ?)",
(
    profile_name,
    json.dumps(mappings_dict, ensure_ascii=False),
    proj_type,
    header_row,
    json.dumps(mappings_dict, ensure_ascii=False),
    json.dumps(extra_list, ensure_ascii=False),
    now,
    now,
),
```

佔位符數量由 7 個增加為 8 個；tuple 同步增加為 8 個值，在 column_mappings 後插入 proj_type。

### 步驟 2：驗證與 commit

執行 `python -m compileall app`，確認無語法錯誤。

Commit 訊息：`fix(task-import-profiles-project-type): use actual project_type when saving import profile`

## 風險與注意事項

**INSERT OR IGNORE 語意**

現有記錄（name 欄位為 UNIQUE）不會被更新，INSERT 被忽略。舊的錯誤 profile 記錄不受本修正影響，使用者需刪除後重存才能修正既有錯誤記錄。這是預期行為，spec 已說明不做 backfill。

**project_type 查詢失敗的降級**

`proj_row` 為 None（project_id 查無記錄）時，`proj_type` 設為 `'local_culture'`，INSERT 照常執行，不中斷匯入流程。符合驗收條件 3。

**conn 生命週期**

project_type 查詢複用 save_profile 區塊已開啟的 `conn`（L70），不額外開關連線。`finally: conn.close()` 仍負責關閉，不受影響。

## 預計影響範圍

| 檔案 | 變更 |
|------|------|
| `app/routers/imports.py` | L70–88：新增 4 行查詢，修改 INSERT SQL 字串與 VALUES tuple |

不影響：import_service.py、profile 載入邏輯、其他 router。

## 驗證指令

- lint：無既有設定，跳過
- format：無既有設定，跳過
- typecheck：無既有設定，跳過
- test：無既有測試，跳過
- build：`python -m compileall app`

## 成果報告

- result_report_mode: none
- 適用情境：無需成果報告
- 報告路徑（若 mode 非 none）：`docs/reports/task-import-profiles-project-type/`
