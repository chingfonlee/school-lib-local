# Spec: task-startup-ops-and-import-perf

## 目標

目前系統在本機與他校安裝啟動體驗上仍有數個維運痛點：`start.bat` 與 `start-portable.bat` 寫死 `127.0.0.1:8765` 而忽略 `config.yaml` 設定、Port 衝突或重複啟動缺乏中文引導、`start.bat` 每次啟動皆重跑 `pip install` 影響離線／校網速度、多處相對路徑依賴啟動當下工作目錄（CWD）、`app/main.py` 未阻擋未修改的預設 `session_secret_key`，且 `setup_first_run.py` 直接字串替換密碼在含 `"` 或 `\` 時會寫壞 YAML。此外，大檔 Excel 匯入仍會把整張表讀入預覽並逐筆 `INSERT`，且 `confirm_import()` 與 `import_vendor_books()` 存在大量重複程式碼。

本 task 補強啟動腳本、設定與路徑基準、Session 安全，並優化大檔匯入效能與收斂重複寫入邏輯。

## 需求範圍

1. **統一啟動入口與啟動腳本優化（`run_server.py`、`start.bat`、`start-portable.bat`）**
   - 新增 `run_server.py`，由 `start.bat` 與 `start-portable.bat` 呼叫：
     - 讀取 `config.yaml` 的 `server.host` 與 `server.port`。
     - 啟動前檢查 Port 是否已被佔用：
       - 若目標位址已回應本系統 `GET /api/health`（`{"status": "ok"}`），直接開啟瀏覽器並印出中文提示「系統已在執行中，已為您開啟瀏覽器」，以退出碼 `0` 結束。
       - 若被其他程式佔用，印出明確中文錯誤與修改 `config.yaml` `server.port` 的步驟，以非零退出碼結束。
     - 啟動 Uvicorn 時以背景執行緒輪詢 `/api/health` 就緒後再自動開啟瀏覽器（不再無條件 60 秒後硬開）。
   - 更新 `start.bat`：僅在新建 `.venv`、缺少核心套件（如 `uvicorn`）或 `requirements.txt` 內容變更時才執行 `pip install`，並檢查錯誤碼輸出中文錯誤提示。

2. **設定防呆、Session 安全與 `BASE_DIR` 路徑統一（`app/config.py`、`app/main.py`、`app/auth.py`、`setup_first_run.py`）**
   - `app/config.py`：
     - 定義 `BASE_DIR = Path(__file__).resolve().parent.parent`，將相對路徑（預設 `config.yaml`、`database_path`、`export_output_dir`、`local_culture_export_template`）統一基於 `BASE_DIR` 解析（保留絕對路徑與 `:memory:` 原樣）。
     - 捕捉 `FileNotFoundError`、`yaml.YAMLError`、`KeyError`，拋出含清楚中文指引的錯誤。
   - `app/main.py`：
     - 啟動驗證 `session_secret_key` 不得為空或預設佔位符 `<generate-a-random-secret>`（否則拒絕啟動並提示執行 `setup_first_run.py` 或修改 `config.yaml`）。
     - `SessionMiddleware` 明確設定 `max_age=8 * 3600` 與 `same_site="lax"`。
     - 靜態目錄改用 `BASE_DIR / "app" / "static"`。
   - `app/auth.py`：移除第 8–10 行重複死碼。
   - `setup_first_run.py`：
     - `needs_setup()` 改用 `yaml.safe_load()` 檢查實際 `auth.default_admin_password` 與 `auth.session_secret_key` 欄位值。
     - 寫入密碼時正確轉義 `\` 與 `"`（使用 JSON 雙引號字串格式），避免特殊字元密碼破壞 YAML 語法。
     - 僅在缺少 `config.yaml` 時複製 `config.example.yaml`，不無故覆蓋既有設定。

3. **大檔匯入效能優化與重複邏輯收斂（`app/services/import_service.py`）**
   - `preview_excel()` 讀取欄位名時補上 `nrows=1`，不將數千列資料全部載入記憶體。
   - 將 `vendor_books` 與 `library_holdings` 的逐筆 `conn.execute("INSERT ...")` 改為收集參數 tuple list 後以 `conn.executemany()` 批次寫入。
   - 抽取共用內部函式 `_insert_vendor_books_core(...)`，收斂 `confirm_import()` 與 `import_vendor_books()` 重複的逐列解析與寫入邏輯，並讓 `import_vendor_books()` 依副檔名支援 `.xls` / `.xlsx`。
   - `_parse_formula_multiplier()` 補齊小數倍率支援（例如 `*0.75`），維持既有 `*75%` 支援。

4. **本地遺留清理與測試**
   - 移除本地未入版控的 0-byte `app/school_lib.db`（若存在）。
   - 新增 `tests/test_startup_ops_and_import_perf.py` 驗證上述全部項目。

## 不做的事

- 不新增資料庫 migration 或變更既有 schema。
- 不修改前端 HTML/JS 頁面。
- 不實作管理員修改密碼 UI（留待後續需求評估）。
- 不修改 `.github/workflows/build-portable.yml` 打包流程結構（僅由 `start-portable.bat` 呼叫 `run_server.py`）。

## 驗收條件

1. `run_server.py` 正確讀取 `config.yaml` 的 host/port；Port 已被本系統佔用時偵測 `/api/health` 並回傳「已在執行中」；Port 被非本系統程式佔用時輸出明確中文指引並回傳非零狀態。
2. `app/config.py` 在任何工作目錄下都能正確以 `BASE_DIR` 解析相對路徑，缺檔或 YAML 格式錯誤時拋出清楚中文訊息。
3. `app/main.py` 拒絕空白或 `<generate-a-random-secret>` 的 `session_secret_key`，且 `SessionMiddleware` 套用 `max_age=28800` 與 `same_site="lax"`。
4. `setup_first_run.py` 可安全寫入含 `"`、`\`、`#` 等特殊字元的密碼且產出的 `config.yaml` 可被 `yaml.safe_load()` 正確解析。
5. `import_service.py` 的 `preview_excel()` 只讀必要列、`confirm_import()` 與 `import_vendor_books()` 共用 `_insert_vendor_books_core()` 並使用 `executemany()` 批次寫入，`_parse_formula_multiplier()` 同時支援 `*75%` 與 `*0.75`。
6. 全套驗證指令（`compileall`、`ruff check`、`ruff format --check`、`mypy`、`pytest -q`）全數通過。
