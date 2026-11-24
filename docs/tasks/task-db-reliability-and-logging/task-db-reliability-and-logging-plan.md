# Plan: task-db-reliability-and-logging

## 實作步驟

1. **新增標準庫日誌模組 `app/logging_config.py`**
   - 定義 `setup_logging(log_dir: Path | None = None) -> logging.Logger`，建立 `RotatingFileHandler`（`data/app.log`，`maxBytes=2 * 1024 * 1024`，`backupCount=3`，`encoding="utf-8"`）與 `StreamHandler`，避免重複掛載 handler。
   - 匯出模組預設 logger 取得方式，讓 `database.py`、`backup.py`、`main.py`、`projects.py` 共用。

2. **強化 `app/database.py` 連線管理與 migration 安全性**
   - 定義 `BASE_DIR = Path(__file__).resolve().parent.parent`（供解析 `migrations/` 目錄）。
   - 更新 `get_connection()`：設 `timeout=10.0`，執行 `PRAGMA foreign_keys = ON` 與 `PRAGMA busy_timeout = 10000`。
   - 新增 `@contextmanager def db_session(conn_factory=None)`：開啟連線，例外時 `conn.rollback()`，finally 必執行 `conn.close()`。
   - 更新 `run_migrations()`：
     - 使用 `db_session(get_connection)` 確保連線關閉。
     - 啟用 `PRAGMA journal_mode = WAL` 與 `PRAGMA synchronous = NORMAL`（若為 `:memory:` 或回傳非 wal 仍安全通過）。
     - 透過 `BASE_DIR / "migrations"` 尋找待執行 SQL 檔；若目錄不存在記錄錯誤並拋出 `FileNotFoundError`。
     - 若存在尚未套用的 migration 且 `Path(db_path).is_file()`，以 `sqlite3.backup()` 建立 `pre_migration_{ts}.db` 並保留最新 5 份。
     - 逐一執行待套用 migration 並記錄 log；發生例外時記錄 `logger.exception` 後拋出。
   - 更新 `ensure_initial_data()` 改用 `with db_session(get_connection) as conn:`。

3. **新增索引 migration `migrations/008_add_indexes.sql`**
   - 建立 `CREATE INDEX IF NOT EXISTS` 涵蓋：`import_batches(project_id)`、`vendor_books(batch_id)`、`vendor_books(isbn_normalized)`、`library_holdings(batch_id)`、`library_holdings(isbn_normalized)`、`book_matches(vendor_book_id)`、`book_matches(holding_id)`、`selection_items(project_id)`、`export_jobs(project_id)`。

4. **加固 `app/routers/backup.py`**
   - 加入模組級 `_backup_lock = threading.Lock()` 保護備份與還原關鍵區段。
   - `_validate_sqlite(path)`：改用 `try/finally` 關閉連線（`timeout=10.0`），新增 `PRAGMA quick_check` 檢查（結果非 `ok` 則回 400）。
   - `backup_database()`：暫存檔名加入 `uuid.uuid4().hex[:8]`；`src`/`dst` 連線用 `try/finally` 關閉；`cleanup()` 失敗時以 `logger.warning` 記錄。
   - `restore_database()`：暫存檔名加入短隨機碼；安全備份與還原連線全部包在 `try/finally` 中關閉，確保 Windows 不鎖檔；還原成功後呼叫 `run_migrations()`；清理超過最新 5 份的 `restore_safety_backup_*.db`；記錄成功／失敗日誌。

5. **清理 router 連線洩漏與大書單刪除子查詢**
   - `app/routers/projects.py`：各端點改用 `with db_session(get_connection) as conn:`；刪除專案中刪除 `book_matches` 改用子查詢（`WHERE vendor_book_id IN (SELECT id FROM vendor_books WHERE batch_id IN (...))` 與 `holding_id` 同理），避免超過 SQLite 參數上限。
   - `app/routers/auth.py`、`app/routers/admin.py`、`app/routers/books.py`、`app/routers/exports.py`、`app/routers/holdings.py`、`app/routers/imports.py`、`app/routers/selections.py`：將裸露的 `get_connection()` 改為 `with db_session(get_connection) as conn:`（或 `try/finally: conn.close()`），確保例外時不洩漏連線。

6. **整合日誌與全域例外處理至 `app/main.py`**
   - 在 `lifespan`（或模組初始化）呼叫 `setup_logging()` 並記錄啟動／migration 完成訊息。
   - 新增 `@app.exception_handler(Exception)`，記錄 `logger.exception`，回傳 `JSONResponse(status_code=500, content={"detail": f"系統發生未預期錯誤（{ts}），請查看 data/app.log 或聯絡管理員。"})`。

7. **建立驗證工具鏈（`requirements-dev.txt`、`pyproject.toml`、`.github/workflows/ci.yml`）**
   - 新增 `requirements-dev.txt`（包含 `ruff`、`mypy`，不影響 `requirements.txt` 與攜帶版打包）。
   - 新增 `pyproject.toml`，設定 `pytest`（`testpaths = ["tests"]`）、`ruff`（核心規則 `E, F`、`line-length = 120`）與 `mypy`（`ignore_missing_imports = true`）。
   - 更新 `.github/workflows/ci.yml`，安裝 `requirements-dev.txt` 並執行 compileall、ruff check、mypy 與 pytest。

8. **撰寫與執行測試**
   - 新增 `tests/test_db_reliability_and_logging.py`，覆蓋：
     - `get_connection()` 的 `busy_timeout` / `foreign_keys` 與 `db_session()` 正常關閉／例外 rollback。
     - `run_migrations()` 的 WAL 設定、前置備份建立與保留上限、`008_add_indexes.sql` 索引建立與冪等性。
     - `backup.py` 損毀 DB 拒絕（`quick_check`）、還原舊版 schema 自動跑 migration、安全備份自動清理至 5 份。
     - `setup_logging()` 寫入檔案且不重複掛載 handler、全域 500 例外回應格式與 `/api/health` 啟動冒煙測試。
   - 依下方「驗證指令」執行全部檢查並確保全數 pass。

## 風險與注意事項

- **測試 monkeypatch 相容性**：`tests/conftest.py` 與其他測試檔案透過 `monkeypatch.setattr("app.routers.projects.get_connection", ...)` 注入記憶體 DB。所有 router 使用 `db_session(get_connection)`（傳入該模組的 `get_connection`）即可完全保留既有測試相容性。
- **既有測試 `TestClient(app, raise_server_exceptions=True)`**：全域 `@app.exception_handler(Exception)` 在 `raise_server_exceptions=True` 時不會吞掉 FastAPI 測試中刻意驗證的未捕捉例外；驗證 500 回應的測試需使用 `raise_server_exceptions=False`。
- **Windows 檔案鎖定**：在測試與實務中，刪除暫存 `.db` 檔前必須確保所有指向該檔的 `sqlite3.Connection` 已完全 `close()`；若啟用 WAL，連線關閉後 `-wal`/`-shm` 會自動回收。

## 預計影響範圍

| 路徑 | 說明 |
|---|---|
| `app/logging_config.py`（新增） | 標準庫 RotatingFileHandler 日誌設定 |
| `migrations/008_add_indexes.sql`（新增） | 9 個常用外鍵與比對欄位索引 |
| `app/database.py` | WAL / `busy_timeout`、`db_session()`、migration 前自動備份與 `BASE_DIR` |
| `app/main.py` | 初始化日誌與全域例外處理器 |
| `app/routers/backup.py` | 連線關閉、互斥鎖、隨機暫存檔名、`quick_check`、還原後 migration、清理舊安全備份 |
| `app/routers/projects.py` | `db_session()` 與刪除專案子查詢 |
| `app/routers/auth.py`、`admin.py`、`books.py`、`exports.py`、`holdings.py`、`imports.py`、`selections.py` | 全面改用 `db_session(get_connection)` 消除連線洩漏 |
| `tests/test_db_reliability_and_logging.py`（新增） | 本次任務單元與整合測試 |
| `requirements-dev.txt`（新增） | 開發與 CI 驗證工具（`ruff`、`mypy`） |
| `pyproject.toml`（新增） | `pytest`、`ruff`、`mypy` 統一設定 |
| `.github/workflows/ci.yml` | 納入 lint / typecheck / compileall 驗證步驟 |

## 驗證指令

- lint: `.venv\Scripts\python.exe -m ruff check app tests`
- format: `.venv\Scripts\python.exe -m ruff format --check <本次修改檔案>`
- typecheck: `.venv\Scripts\python.exe -m mypy app/logging_config.py app/database.py app/main.py app/routers/backup.py app/routers/projects.py`
- test: `.venv\Scripts\python.exe -m pytest -q`
- build: `.venv\Scripts\python.exe -m compileall -q app`（搭配 FastAPI TestClient 啟動冒煙測試）

## 成果報告

- result_report_mode: none
- 適用情境：無（沿用專案慣例，以 spec 驗收條件與測試結果為準）
- 報告路徑（若 mode 非 none）：`docs/reports/task-db-reliability-and-logging/`
