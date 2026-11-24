# Spec: task-db-reliability-and-logging

## 目標

本專案為本機端執行於 Windows 環境的 SQLite Web 應用。目前資料庫連線缺乏 WAL 模式、`busy_timeout` 與統一的連線關閉／交易回滾機制，在併發存取、匯入寫入、備份還原或 migration 中途失敗時容易出現 `database is locked`、Windows 鎖檔殘留與 schema 半套用風險；資料庫亦缺少常用外鍵與比對欄位索引；且全系統沒有任何檔案日誌與全域例外記錄，學校端發生錯誤時難以定位原因。

本 task 加固資料庫連線與交易可靠性、補齊關鍵二級索引、改善備份還原與 migration 安全性，並建立零外部依賴的標準庫檔案日誌與全域例外處理機制。

## 需求範圍

1. **SQLite 連線設定與統一 context manager（`app/database.py`）**
   - `get_connection()` 連線逾時設為 `timeout=10.0`，並於每次連線設定 `PRAGMA foreign_keys = ON` 與 `PRAGMA busy_timeout = 10000`。
   - 於 `run_migrations()` 啟動初始化時設定 `PRAGMA journal_mode = WAL` 與 `PRAGMA synchronous = NORMAL`（`:memory:` 資料庫不因 WAL 設定出錯）。
   - 新增輕量 `@contextmanager` 函式 `db_session(conn_factory=None)`，於區塊離開時確保 `conn.close()`，發生例外時自動 `conn.rollback()` 後再拋出。
   - 將 `app/database.py`、`app/routers/auth.py`、`app/routers/projects.py`、`app/routers/admin.py`、`app/routers/backup.py` 及其他 router 中未受 `try/finally` 保護的連線使用改為 `db_session` 或 `try/finally` 關閉（維持與既有測試 `monkeypatch` 相容）。

2. **Migration 安全性與二級索引（`app/database.py`、`migrations/008_add_indexes.sql`）**
   - `run_migrations()` 使用相對於專案根目錄（`BASE_DIR`）的 `migrations` 路徑，避免因工作目錄不同而靜默跳過 migration。
   - 若偵測到有尚未套用的 migration 且資料庫檔案已存在，先以 `sqlite3.backup()` 建立前置備份 `data/pre_migration_{timestamp}.db`（於資料庫所在目錄），保留最近 5 份避免無限累積。
   - 新增 `migrations/008_add_indexes.sql`（全部使用 `CREATE INDEX IF NOT EXISTS`），針對常用外鍵與查詢欄位建立索引：
     - `import_batches(project_id)`
     - `vendor_books(batch_id)`、`vendor_books(isbn_normalized)`
     - `library_holdings(batch_id)`、`library_holdings(isbn_normalized)`
     - `book_matches(vendor_book_id)`、`book_matches(holding_id)`
     - `selection_items(project_id)`
     - `export_jobs(project_id)`

3. **備份與還原穩定性（`app/routers/backup.py`）**
   - `_validate_sqlite()`、`backup_database()`、`restore_database()` 的所有 `sqlite3.connect()` 均設 `timeout=10.0` 並以 `try/finally` 確保關閉，避免 Windows 刪檔時出現 `WinError 32` 鎖檔錯誤。
   - 新增模組級 `threading.Lock`，序列化 `backup` 與 `restore` 操作，避免同時還原或備份衝突。
   - 暫存檔名加入短隨機碼（`uuid.uuid4().hex[:8]`）防止同秒並發檔名碰撞。
   - `_validate_sqlite()` 增加 `PRAGMA quick_check` 檢查，拒絕損毀的 SQLite 檔案。
   - `restore_database()` 還原完成後立即執行 `run_migrations()`，確保還原舊版備份時 schema 自動補齊。
   - 自動清理 `restore_safety_backup_*.db`，保留最新 5 份。

4. **刪除專案大書單安全性（`app/routers/projects.py`）**
   - 刪除專案時避免將大量 `vendor_book_id` / `holding_id` 展開為 `IN (?, ?, ...)` 超過 SQLite 變數上限，改用子查詢刪除相關 `book_matches`。

5. **檔案日誌與全域例外處理（`app/logging_config.py`、`app/main.py`）**
   - 新增 `app/logging_config.py`，僅使用 Python 標準庫 `logging` 與 `RotatingFileHandler`（寫入 `data/app.log`，單檔上限 2 MB、保留 3 份，UTF-8 編碼），同時輸出至 console。
   - 在 `app/main.py` 啟動時初始化日誌，並新增全域 `@app.exception_handler(Exception)`：記錄完整 stack trace（`logger.exception`），回傳友善中文 500 JSON 回應（附時間戳記以便對照 log）。
   - 於啟動／migration、備份／還原失敗、清理暫存檔失敗與刪除專案加上關鍵日誌，不再靜默吞掉例外。

## 不做的事

- 不修改業務邏輯（匯出公式、備註覆寫、ISBN 正規化、匯入零筆防清空、選書快照繼承等，已拆至後續 Task 1B）。
- 不修改前端 HTML/JS 頁面。
- 不修改啟動腳本（`start.bat`、`start-portable.bat`）與 `config.yaml` 結構。
- 不引入任何新的第三方套件（如 loguru、SQLAlchemy）。
- 不修改既有的 `migrations/001` 至 `007` SQL 檔案內容（避免影響已套用環境的一致性）。

## 驗收條件

1. `get_connection()` 連線具備 `timeout=10.0`、`foreign_keys = ON`、`busy_timeout = 10000`；`run_migrations()` 後檔案型 SQLite 處於 `WAL` 模式。
2. `db_session()` 在正常結束時關閉連線，在例外時自動 rollback 並關閉連線，且不破壞既有測試的 `monkeypatch`。
3. `migrations/008_add_indexes.sql` 套用成功且具冪等性，所有指定索引存在於 `sqlite_master`。
4. `run_migrations()` 在有待套用 migration 時會自動建立 `pre_migration_*.db` 備份；若無待套用 migration 則不重複建立備份。
5. `backup.py` 在驗證損毀 DB、還原舊版 schema DB、連續備份與清理安全備份時皆正常運作，且不殘留未關閉連線或暫存檔。
6. 未捕捉例外會寫入 `data/app.log` 並回傳含中文說明與時間戳的 500 JSON 回應。
7. `python -m compileall app` 與 `python -m pytest tests -q` 全數通過，並包含本次新增的單元／整合測試。
