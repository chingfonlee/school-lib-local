# Spec：task-project-delete-backup-restore

- task-id: task-project-delete-backup-restore
- type: feat
- base branch: main
- status: planning

---

## 背景與問題

目前系統缺少：

1. **專案刪除功能**：測試期間建立的假專案無法清理；匯入錯誤的專案無法移除。
2. **資料庫備份**：學校在執行重要操作前，無法對整個資料庫建立備份。
3. **資料庫還原**：機器重裝或資料損毀後，無法從備份檔還原。

---

## 使用者目標

1. 能從「採購專案」頁面刪除不需要的專案，並在刪除前確認影響範圍。
2. 能下載整個 SQLite 資料庫備份檔，在執行危險操作前留底。
3. 能上傳備份檔還原資料庫，系統不需要重新啟動即可使用新資料。

---

## 資料關聯分析（重要）

### 完整 FK 依賴圖（migration 001–004 後）

```
procurement_projects (id)
  ├── import_batches.project_id          REFERENCES procurement_projects(id)  [有 FK]
  ├── selection_items.project_id         REFERENCES procurement_projects(id)  [有 FK]
  └── export_jobs.project_id             REFERENCES procurement_projects(id)  [有 FK]

import_batches (id)
  ├── vendor_books.batch_id              REFERENCES import_batches(id)        [有 FK]
  └── library_holdings.batch_id         REFERENCES import_batches(id)        [有 FK]
  （注意：selection_items.source_batch_id 無 FK constraint，migration 003 rebuild 時移除）

vendor_books (id)
  └── book_matches.vendor_book_id        REFERENCES vendor_books(id)          [有 FK，NOT NULL]
  （注意：selection_items.vendor_book_id migration 003 後已無 FK constraint）

library_holdings (id)
  └── book_matches.holding_id            REFERENCES library_holdings(id)      [有 FK，NULLABLE]
```

### 跨專案 library_holdings 風險

`book_matches.holding_id` 指向 library_holdings，而 library_holdings 屬於某個 import_batch（某個專案）。
若專案 A 的 vendor_books 比對到屬於專案 B 的 library_holdings，刪除專案 B 時若直接刪除其 library_holdings，
`PRAGMA foreign_keys = ON` 會因 book_matches 仍有 holding_id 參照而報錯。

**處理方式**：刪除 library_holdings 前，先 `UPDATE book_matches SET holding_id = NULL WHERE holding_id IN (...)` 。

### 正確刪除順序

```
1. DELETE selection_items WHERE project_id = ?
2. DELETE export_jobs WHERE project_id = ?
3. 取得本專案所有 import batch_ids：
   SELECT id FROM import_batches WHERE project_id = ?
4. 取得這些 batch 中所有 vendor_book_ids：
   SELECT id FROM vendor_books WHERE batch_id IN (batch_ids)
5. DELETE book_matches WHERE vendor_book_id IN (vendor_book_ids)
6. DELETE vendor_books WHERE batch_id IN (batch_ids)
7. 取得這些 batch 中所有 holding_ids：
   SELECT id FROM library_holdings WHERE batch_id IN (batch_ids)
8. UPDATE book_matches SET holding_id = NULL WHERE holding_id IN (holding_ids)
9. DELETE library_holdings WHERE batch_id IN (batch_ids)
10. DELETE import_batches WHERE project_id = ?
11. DELETE procurement_projects WHERE id = ?
```

所有步驟在同一 transaction 中執行（`conn.execute("BEGIN")` ... `conn.commit()`）。

---

## 專案刪除需求

### 1. 刪除按鈕（projects.html）

- 每個專案卡片加入「刪除」按鈕。
- 視覺使用危險操作樣式（紅色外框，例如 `btn-danger`）。
- 與「選擇」、「設定」按鈕視覺上明確區隔（位置靠右或獨立一行）。

### 2. 目前使用中專案的處理策略

採用 **策略 A**：不允許刪除目前使用中的專案。

- 前端使用共用函式 `getProjectId()`（依序查 sessionStorage / localStorage 的 `current_project_id`）讀取 current project id。
- 若點擊刪除的是 current project，顯示提示：「請先在其他專案點選「選擇」後再刪除此專案」。
- 後端不追蹤 current project（session 無此資訊），由前端防呆。
- spec 限制記錄：後端無法得知 current project，無法在 API 層阻擋，為已知限制。

### 3. 刪除前二次確認 Modal

**第一步：點「刪除」** → 顯示確認 Modal：

Modal 內容：
- 標題：「確認刪除專案」
- 專案名稱（粗體顯示）
- 影響範圍（來自 delete-preview API）：
  - 選書項目：N 筆
  - 匯出記錄：N 筆
  - 匯入批次：N 批
  - 書商書目：N 筆
  - 館藏紀錄：N 筆
- 警告文字：「刪除後無法復原，建議先備份資料庫。與此專案相關的所有資料（書目、選書、匯出紀錄）將永久刪除。」
- 「確認刪除」按鈕（紅色）
- 「取消」按鈕

**第二步：點「確認刪除」** → 呼叫 DELETE API → 重新載入列表。

不要求使用者輸入專案名稱（已有兩個明確點擊步驟，MVP 不增加輸入負擔）。

### 4. 刪除影響預覽 API

**GET `/api/projects/{project_id}/delete-preview`**

```json
{
  "project_id": 1,
  "project_name": "115年度本土文化採購",
  "selection_count": 12,
  "export_job_count": 3,
  "import_batch_count": 2,
  "vendor_book_count": 120,
  "holding_count": 5000
}
```

回傳前確認專案存在（404 if not found）。需要登入。

### 5. 刪除 API

**DELETE `/api/projects/{project_id}`**

- 需要登入。
- 確認專案存在（404 if not found）。
- 依刪除順序在 transaction 中執行所有 DELETE / UPDATE。
- 成功回傳 `{"ok": true}`。
- 若發生 FK 違規或其他 DB 錯誤，rollback 並回傳 500。

---

## 備份需求

### 備份 API

**GET `/api/backup/database`**

- 需要登入。
- 使用 **sqlite3 Python backup API**（`src_conn.backup(dst_conn)`），不直接複製正在使用中的檔案。
- 備份至暫時路徑（`data/backup_temp_YYYYMMDD_HHMMSS.db`），再以 `FileResponse` 回傳。
- 回傳後刪除暫時檔（或交由 OS 清理）。
- 下載檔名：`school_lib_backup_YYYYMMDD_HHMMSS.db`（使用 `Content-Disposition` header）。
- 備份範圍：僅 `data/school_lib.db`，不包含 `exports/` 目錄。

### 前端（projects.html）

- 在頁面加入「備份資料庫」按鈕（與專案列表分開，放在頁面頂部操作區或底部管理區）。
- 點擊後直接呼叫 `GET /api/backup/database`（`window.location.href` 或隱藏 `<a>` 觸發下載）。
- 下載成功後顯示 toast：「備份已下載」。

---

## 還原需求

### 還原 API

**POST `/api/backup/restore`**（multipart form, field: `file`）

1. **驗證** 上傳檔案：
   - 檔案大小限制：合理上限（例如 100 MB）。
   - 驗證 SQLite magic bytes（前 16 bytes 應為 `SQLite format 3\x00`）。
   - 連線並驗證必要資料表存在：`procurement_projects`, `users`, `schema_migrations`。
   - 驗證失敗 → 400 錯誤，不接觸現有 DB。
2. **安全備份** 現有 DB：
   - 路徑：`data/restore_safety_backup_YYYYMMDD_HHMMSS.db`。
   - 使用 sqlite3 backup API。
3. **還原** 上傳檔案：
   - 將上傳內容寫入暫時路徑。
   - 使用 sqlite3 backup API 將暫時 DB 內容寫入 `data/school_lib.db`（`pending.backup(current)`）。
   - 清理暫時檔。
4. 回傳：

```json
{
  "ok": true,
  "safety_backup_path": "data/restore_safety_backup_20261231_120000.db",
  "message": "還原成功。已自動建立安全備份。建議重新整理頁面後再繼續操作。"
}
```

### 重啟服務的必要性

**不需要重啟服務**。`get_connection()` 每次 request 建立新的 sqlite3 connection，restore 完成後，後續所有 request 都會開新 connection 至已替換的 DB 檔案。

已知限制：若還原當下有其他 in-flight request 正在執行 DB 操作，可能出現 inconsistent read。對本地學校單一使用者環境，此風險可接受。

### 安全性

- 上傳路徑固定寫入 `data/` 目錄（不跟隨 filename 路徑）。
- 不接受 `.db` 以外的副檔名（或不強制副檔名，但依 magic bytes 驗證）。
- 明確拒絕路徑穿越（不使用原始 filename 拼接路徑）。
- 需要登入。

### 前端（projects.html）

- 頁面加入「還原資料庫」按鈕，點擊後展開還原區或顯示 Modal。
- 還原 Modal 內容：
  - 警告：「還原將覆蓋目前所有資料，請確認備份檔正確。」
  - 「系統將在還原前自動建立目前資料庫的安全備份。」
  - 檔案選擇 input（`.db`）
  - 「確認還原」按鈕（橘色或紅色）
  - 「取消」按鈕
- 還原成功後頁面自動 `location.reload()`（3 秒後）。若畫面異常，提示：「若畫面仍有問題，請重新啟動服務」。

---

## 安全性與資料保護需求

| 需求 | 說明 |
|------|------|
| 所有 API 需要登入 | `require_auth` dependency |
| 備份檔路徑固定 | 不讓使用者控制備份存放路徑 |
| 還原前自動安全備份 | 避免一次操作遺失所有資料 |
| 上傳檔 magic bytes 驗證 | 防止上傳非 SQLite 檔案 |
| 上傳路徑不跟隨 filename | 防止路徑穿越 |
| 刪除在 transaction 中 | 失敗時完整 rollback |
| 刪除不可撤銷 | 前端警告，建議先備份 |

---

## 非目標

- 不做單一專案匯出/還原。
- 不做雲端備份。
- 不做排程自動備份。
- 不做使用者權限分級。
- 不處理 exports/ 目錄完整備份（後續任務）。
- 不改 stepper nav。
- 不清除現有測試專案（測試專案作為驗證刪除功能的測試素材保留）。
- 後端不追蹤 current project（此為已知限制，由前端防呆）。

---

## 驗收條件

### 專案刪除

1. 每個非目前使用中的專案卡片顯示刪除按鈕。
2. 點擊目前使用中的專案刪除按鈕 → 顯示防呆提示，不顯示確認 Modal。
3. 點擊非使用中的專案刪除按鈕 → 顯示確認 Modal，含專案名稱與影響數量。
4. 取消刪除 → 資料不變，專案仍在列表中。
5. 確認刪除後 → 專案不再出現在列表。
6. 刪除後 API 確認：對應 project_id 的 selection_items、export_jobs、import_batches、vendor_books、library_holdings、book_matches 均已清除（或 book_matches.holding_id 已 nullified）。
7. 既有其他專案資料不受影響。
8. DELETE `/api/projects/{project_id}` 不存在的 id → 404。

### 備份

9. 「備份資料庫」按鈕可觸發下載。
10. 下載的 .db 檔可用 sqlite3 開啟。
11. 備份檔包含 `procurement_projects`、`users`、`schema_migrations` 等必要資料表。
12. 備份檔名包含日期時間。

### 還原

13. 上傳有效備份檔 → 還原成功，系統在同一 session 內即可使用新資料（無需重啟）。
14. 還原前已自動建立安全備份在 `data/` 目錄下。
15. 上傳非 SQLite 檔案 → 400 錯誤，現有 DB 不受影響。
16. 還原後頁面重新整理，新資料可正常顯示。

### 既有測試

17. pytest 45 tests 通過。

---

## 風險與限制

| 風險 | 處理方式 |
|------|---------|
| 跨專案 book_matches.holding_id 參照 | 刪除 holdings 前 UPDATE book_matches SET holding_id = NULL |
| selection_items.source_batch_id 無 FK（migration 003 移除） | 無 FK 問題，但資料仍有語意關聯，刪除 import_batches 後 source_batch_id 成為無效 id，屬已知設計，不影響功能 |
| 還原時 in-flight requests | 本地單使用者風險可接受；spec 明確記錄此限制 |
| 後端無法識別 current project | 前端防呆；API 層不做此檢查；已知限制 |
| 備份暫時檔的清理 | 回傳 FileResponse 後刪除暫時檔，或使用 BackgroundTask 清理 |
| SQLite backup API 執行期間讀取 | sqlite3.backup() 支援線上備份，此風險可接受 |
| Windows 上 DB 檔案被 sqlite3 lock | restore 使用 backup API 寫入方式，不做 file rename，可避免 Windows 的 file-in-use 問題 |
