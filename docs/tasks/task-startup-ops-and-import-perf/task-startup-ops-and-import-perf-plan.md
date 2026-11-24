# Plan: task-startup-ops-and-import-perf

## 實作步驟

1. **強化 `app/config.py`、`app/auth.py` 與 `app/main.py`**
   - `app/config.py`：
     - 定義 `BASE_DIR = Path(__file__).resolve().parent.parent` 與 `_resolve_path(raw: str) -> str`（保留 `:memory:` 與絕對路徑，其餘基於 `BASE_DIR` 解析）。
     - `Config.__init__` 預設讀取 `BASE_DIR / "config.yaml"`，捕捉 `FileNotFoundError`、`yaml.YAMLError`、`KeyError`/`TypeError` 並拋出含中文指引的 `RuntimeError`。
     - 將 `database_path`、`export_output_dir`、`local_culture_export_template` 經 `_resolve_path()` 解析。
   - `app/auth.py`：移除重複的 `if not user_id` / fallback 死碼。
   - `app/main.py`：
     - 新增 `_validate_session_secret(secret: str)`，若為空或 `<generate-a-random-secret>` 直接拋出中文 `RuntimeError`（並同步確認 CI 測試 `config.example.yaml` 處理方式：在 CI 產生 config 時填入測試用 secret 或由測試設定）。
     - `SessionMiddleware` 加上 `max_age=8 * 3600, same_site="lax"`。
     - `StaticFiles(directory=str(BASE_DIR / "app" / "static"), html=True)`。

2. **補強 `setup_first_run.py`**
   - `CONFIG_PATH`、`EXAMPLE_PATH` 改基於 `Path(__file__).resolve().parent`。
   - `needs_setup()` 改用 `yaml.safe_load()` 檢查 `auth.default_admin_password` 與 `auth.session_secret_key` 是否為預設佔位符或缺失。
   - 寫入密碼時使用 `json.dumps(password, ensure_ascii=False)` 產生合法 YAML 雙引號字串，並更新既有 `config.yaml`（僅在檔案不存在時從 `config.example.yaml` 複製）。

3. **新增 `run_server.py` 與更新 `start.bat` / `start-portable.bat`**
   - `run_server.py`：
     - 讀取 `get_config()` 的 `server_host`、`server_port`；計算瀏覽器開啟位址（`0.0.0.0` 時改開 `127.0.0.1`）。
     - 實作 `check_health(url, timeout=1.0) -> bool` 與 `is_port_in_use(host, port) -> bool`。
     - 若 port 已被佔用：若 `check_health` 為 True，開瀏覽器並印「系統已在執行中，已為您開啟瀏覽器」後 `return 0`；否則印中文 Port 衝突指引並 `return 1`。
     - 啟動背景 daemon 執行緒等待 `check_health` 成功（最多 60 秒）後開啟瀏覽器，主執行緒呼叫 `uvicorn.run("app.main:app", host=host, port=port)`。
   - `start.bat`：以 `.venv\.req_hash`（或套件檢查）判斷是否需要跑 `pip install -r requirements.txt --quiet`，失敗時印中文提示並 `exit /b 1`；改以 `python run_server.py` 啟動。
   - `start-portable.bat`：改以 `python\python.exe run_server.py` 啟動，移除寫死的 `127.0.0.1:8765` 與 PowerShell 單行指令。
   - 同步檢查 `.github/workflows/ci.yml`：確保 `cp config.example.yaml config.yaml` 後會填入非佔位符的 `session_secret_key`，避免被新的啟動安全檢查阻擋。

4. **優化 `app/services/import_service.py` 效能與收斂重複程式碼**
   - `preview_excel()` 讀取欄位名時傳入 `nrows=1`。
   - `_parse_formula_multiplier()` 擴充支援 `*0.75` 等小數倍率（正則同時涵蓋 `\*\s*(\d+(?:\.\d+)?)\s*%` 與 `\*\s*(0?\.\d+)`）。
   - 抽取 `_insert_vendor_books_core(conn, df, project_id, proj_type, filename, mappings, extra_field_settings, user_id, profile_id, header_row, pp_formula_map, record_row_numbers)`，收集 `rows_to_insert` 後以 `conn.executemany(...)` 批次寫入，供 `confirm_import()` 與 `import_vendor_books()` 共用；`import_vendor_books()` 依副檔名選擇 `xlrd` / `openpyxl`。
   - `_insert_library_holding_rows()` 改為收集參數 list 後以 `conn.executemany(...)` 批次寫入。

5. **清理遺留檔、撰寫測試並執行全套驗證**
   - 刪除未入版控的 0-byte `app/school_lib.db`（若存在）。
   - 新增 `tests/test_startup_ops_and_import_perf.py`，覆蓋 `BASE_DIR` 解析、`Config` 錯誤處理、`setup_first_run` 特殊字元密碼、`run_server` 健檢與 Port 佔用分支、`session_secret_key` 阻擋、`preview_excel`、`executemany` 批次匯入與 `*0.75` 公式解析。
   - 更新 `.github/workflows/ci.yml` 的 `mypy` 與 `ruff` 目標加入 `app/config.py`、`app/auth.py`、`run_server.py`、`setup_first_run.py`。
   - 執行全套驗證指令確保全數 pass。

## 風險與注意事項

- **CI 與測試使用 `config.example.yaml`**：`config.example.yaml` 的 `session_secret_key` 是 `<generate-a-random-secret>`；CI（`.github/workflows/ci.yml`）直接複製 `config.example.yaml` 跑 pytest，因此必須在 CI 步驟中將該佔位符替換為測試密鑰（或在 `app/main.py` 僅於非 pytest 執行或明確替換 CI config；建議直接於 CI 替換測試密鑰，最乾淨一致）。
- **`import_vendor_books()` 去重相容性**：保留既有回傳鍵值（`batch_id`、`record_count`、`unmapped_fields`、`column_mapping`、`match_stats`），確保既有測試不中斷。

## 預計影響範圍

| 路徑 | 說明 |
|---|---|
| `run_server.py`（新增） | 讀取 `config.yaml`、Port 衝突偵測、健康檢查後自動開瀏覽器 |
| `start.bat`、`start-portable.bat` | 改呼叫 `run_server.py`；`start.bat` 避免每次重複 `pip install` |
| `setup_first_run.py` | `yaml.safe_load` 檢查、安全密碼轉義、避免覆蓋既有設定 |
| `app/config.py` | `BASE_DIR` 統一相對路徑解析與中文設定錯誤提示 |
| `app/main.py` | 阻擋預設 `session_secret_key`、Session `max_age`/`same_site`、`BASE_DIR` 靜態路徑 |
| `app/auth.py` | 移除重複死碼 |
| `app/services/import_service.py` | `preview_excel` `nrows=1`、`executemany` 批次寫入、收斂重複邏輯、支援 `*0.75` 公式 |
| `.github/workflows/ci.yml` | 產生測試用 `session_secret_key` 並擴大 `ruff`/`mypy` 檢查目標 |
| `tests/test_startup_ops_and_import_perf.py`（新增） | 啟動、設定、安全與匯入效能回歸測試 |

## 驗證指令

- lint: `.venv\Scripts\python.exe -m ruff check app tests run_server.py setup_first_run.py`
- format: `.venv\Scripts\python.exe -m ruff format --check run_server.py setup_first_run.py app/config.py app/auth.py app/main.py app/services/import_service.py tests/test_startup_ops_and_import_perf.py`
- typecheck: `.venv\Scripts\python.exe -m mypy app/logging_config.py app/database.py app/main.py app/config.py app/auth.py app/routers/backup.py app/routers/projects.py app/services/isbn_service.py app/services/completeness_service.py app/services/match_service.py app/services/validation_service.py run_server.py`
- test: `.venv\Scripts\python.exe -m pytest -q`
- build: `.venv\Scripts\python.exe -m compileall -q app run_server.py setup_first_run.py`

## 成果報告

- result_report_mode: none
- 適用情境：無
- 報告路徑（若 mode 非 none）：`docs/reports/task-startup-ops-and-import-perf/`
