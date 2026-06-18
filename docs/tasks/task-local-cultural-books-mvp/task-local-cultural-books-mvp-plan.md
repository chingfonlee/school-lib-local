# Plan: task-local-cultural-books-mvp

## 實作步驟

### Step 1：專案結構建立

建立以下目錄結構與基礎空白檔案：

```
school-lib-local/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # 讀取 config.yaml
│   ├── database.py          # SQLite 連線、migration runner
│   ├── auth.py              # require_auth 依賴注入
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── project.py
│   │   ├── import_batch.py
│   │   ├── library_holding.py
│   │   ├── vendor_book.py
│   │   ├── book_match.py
│   │   ├── selection_item.py
│   │   └── export_job.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── isbn_service.py
│   │   ├── import_service.py
│   │   ├── match_service.py
│   │   ├── completeness_service.py  # 欄位完整度計算
│   │   ├── validation_service.py    # 匯出前置檢查
│   │   ├── selection_service.py
│   │   └── export_service.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── projects.py
│   │   ├── imports.py
│   │   ├── books.py
│   │   ├── selections.py
│   │   └── exports.py
│   └── static/
│       ├── index.html
│       ├── login.html
│       ├── projects.html
│       ├── import.html
│       ├── match.html
│       ├── selection.html
│       ├── export-check.html
│       ├── export.html
│       └── css/
│           └── style.css
├── migrations/
│   └── 001_initial_schema.sql
├── data/                    # SQLite DB，加入 .gitignore
├── exports/                 # 匯出 Excel，加入 .gitignore
├── .gitignore
├── config.yaml
├── requirements.txt
└── start.bat
```

### Step 2：SQLite Schema（migrations/001_initial_schema.sql）

```sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- V1 啟動時自動建立一筆預設 local_culture 專案
CREATE TABLE IF NOT EXISTS procurement_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    project_type TEXT NOT NULL CHECK(project_type IN ('local_culture', 'general_books')),
    budget_amount REAL,
    export_template_type TEXT NOT NULL DEFAULT 'local_culture',
    price_field TEXT NOT NULL DEFAULT 'purchase_price'
        CHECK(price_field IN ('list_price', 'purchase_price')),
    subtotal_mode TEXT NOT NULL DEFAULT 'quantity_times_purchase_price'
        CHECK(subtotal_mode IN ('quantity_times_list_price', 'quantity_times_purchase_price')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS import_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    file_type TEXT NOT NULL CHECK(file_type IN ('library_holdings', 'vendor_books')),
    column_mappings TEXT NOT NULL,   -- JSON: {"來源欄名": "系統欄名"}
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- project_id 對 library_holdings 批次為 NULL
CREATE TABLE IF NOT EXISTS import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES procurement_projects(id),
    batch_type TEXT NOT NULL CHECK(batch_type IN ('library_holdings', 'vendor_books')),
    original_filename TEXT NOT NULL,
    profile_id INTEGER REFERENCES import_profiles(id),
    record_count INTEGER,
    imported_by INTEGER REFERENCES users(id),
    imported_at TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS library_holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES import_batches(id),
    isbn TEXT,
    isbn_normalized TEXT,
    title TEXT,
    author TEXT,
    publisher TEXT,
    publish_year TEXT,
    price REAL,
    library_record_id TEXT,
    isbn_status TEXT NOT NULL CHECK(isbn_status IN ('valid', 'missing', 'invalid')),
    raw_row TEXT                     -- JSON: 原始列資料
);

-- V1 欄位對應 local_culture；award_item / vendor_seq 為 local_culture 專用，V2 可擴充
CREATE TABLE IF NOT EXISTS vendor_books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES import_batches(id),
    award_item TEXT,
    vendor_seq TEXT,
    title TEXT,
    author TEXT,
    isbn TEXT,
    isbn_normalized TEXT,
    publish_date TEXT,
    list_price REAL,
    purchase_price REAL,
    publisher TEXT,
    age_range TEXT,
    isbn_status TEXT NOT NULL CHECK(isbn_status IN ('valid', 'missing', 'invalid')),
    completeness_status TEXT NOT NULL DEFAULT 'unknown'
        CHECK(completeness_status IN ('export_ready', 'needs_review', 'missing_required', 'unknown')),
    policy_topic TEXT,               -- SDGs / SEL 等政策議題（從獲獎項目欄分離），不填入 award_item
    award_notes TEXT,                -- 待確認標記；非空時 completeness_status 強制為 needs_review
    user_overrides TEXT,             -- JSON: {"欄位名": "修正值"}
    raw_row TEXT                     -- JSON: 原始列資料
);

CREATE TABLE IF NOT EXISTS book_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor_book_id INTEGER NOT NULL REFERENCES vendor_books(id),
    holding_id INTEGER REFERENCES library_holdings(id),
    match_status TEXT NOT NULL CHECK(match_status IN (
        'available', 'already_owned', 'missing_isbn', 'invalid_isbn', 'same_title_different_isbn'
    )),
    matched_at TEXT NOT NULL,
    batch_run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS selection_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES procurement_projects(id),
    vendor_book_id INTEGER NOT NULL REFERENCES vendor_books(id),
    selected_quantity INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(project_id, vendor_book_id)
);

CREATE TABLE IF NOT EXISTS export_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES procurement_projects(id),
    school_name TEXT,
    approved_budget REAL,
    price_field TEXT NOT NULL CHECK(price_field IN ('list_price', 'purchase_price')),
    subtotal_mode TEXT NOT NULL CHECK(subtotal_mode IN (
        'quantity_times_list_price', 'quantity_times_purchase_price'
    )),
    template_path TEXT,              -- 匯出時使用的範本完整路徑
    output_filename TEXT,
    output_path TEXT,
    exported_by INTEGER REFERENCES users(id),
    exported_at TEXT NOT NULL,
    record_count INTEGER,
    total_amount REAL
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);
```

`app/database.py` 實作簡易 migration runner：啟動時掃描 `migrations/` 目錄，依序執行未記錄於 `schema_migrations` 的 SQL 檔。

`app/database.py` 另實作 `ensure_initial_data()`：若 `procurement_projects` 為空，自動建立一筆預設 `local_culture` 專案，從 config.yaml 讀取 price_field / subtotal_mode 預設值。

### Step 3：ISBN Normalization（app/services/isbn_service.py）

實作 `normalize_isbn(raw) -> str | None`：

1. 輸入為 `None` 或空字串 → 回傳 `None`（missing）
2. 輸入為數值（如 Excel float `9789861371580.0`）→ 轉整數字串
3. 移除下列字元：
   - ASCII 空格 ` `、Tab `\t`
   - 全形空格（U+3000）
   - 不間斷空格（U+00A0）
   - 零寬空格（U+200B）
   - 連字號 `-`（U+002D）、全形連字號 `－`（U+FF0D）
   - `unicodedata.category(c) == 'Cc'` 的控制字元
4. 結果非 10 或 13 碼純數字 → 回傳 `None`（invalid）
5. 回傳純數字字串

實作 `get_isbn_status(raw) -> Literal["valid", "missing", "invalid"]`：
- raw 為 None / 空 → `"missing"`
- normalize_isbn 回傳 None 且 raw 非空 → `"invalid"`
- 否則 → `"valid"`

### Step 4：Excel Import Pipeline（app/services/import_service.py）

#### 4.1 學校館藏匯入（.xls）

- `pandas.read_excel(engine='xlrd')` 讀取 .xls
- 依 `LIBRARY_COLUMN_HINTS` 字典比對 header row（不分大小寫、去除前後空白）
- 自動偵測不完整時，回傳未對應欄位清單，供前端顯示讓使用者補齊並儲存為新 profile
- 每筆：呼叫 `isbn_service` 取得 `isbn_normalized` 與 `isbn_status`
- 批次寫入 `library_holdings`；建立 `import_batches`（project_id = NULL）

#### 4.2 書商書單匯入（.xlsx）

- `pandas.read_excel(engine='openpyxl')` 讀取 .xlsx
- 依 `VENDOR_COLUMN_HINTS` 自動偵測欄位（含 list_price / purchase_price）
- 書單原始數量與總價欄保留於 `raw_row` JSON，不作採購計算依據
- 每筆：呼叫 `isbn_service`；呼叫 `completeness_service.compute` 計算初始 `completeness_status`
- 批次寫入 `vendor_books`；建立 `import_batches`（project_id = 選定專案 id）

#### 4.3 欄位對應設定（import_profiles）

- 使用者手動調整的欄位對應可儲存為 `import_profile`，供下次匯入套用
- column_mappings 格式：`{"來源欄名": "系統欄名"}`，如 `{"條碼": "isbn", "定價": "list_price"}`

#### 4.4 獲獎項目處理（local_culture V1：直接保留原文）

V1 `local_culture` 匯入時，`award_item` 欄位**直接複製書商來源欄「獲獎項目」的原始文字**：

```python
book["award_item"] = raw_row.get("獲獎項目") or None
```

不執行任何關鍵字拆分，不自動填值，不設 award_notes。`policy_topic` 與 `award_notes` 保持 NULL。

> V2 general_books 預留：屆時可在此步驟加入 POLICY_TOPIC_KEYWORDS 關鍵字偵測與 split_award_and_policy 函式，將 SDGs / SEL 等政策議題標籤分離至 policy_topic，並在只有政策議題時設定 award_notes「待確認」標記。V1 不實作此邏輯。

### Step 5：Match Service（app/services/match_service.py）

實作 `run_match(project_id: int, batch_run_id: str) -> dict`：

1. 讀取所有 `library_holdings`，建立 `{isbn_normalized: holding_id}` 索引
2. 建立 `{title_stripped: [isbn_normalized]}` 索引（書名去除空白後比對），供 `same_title_different_isbn` 偵測
3. 讀取隸屬 project 的所有 `vendor_books`，逐筆判斷 `match_status`：
   - isbn_status = `missing` → `missing_isbn`
   - isbn_status = `invalid` → `invalid_isbn`
   - isbn_normalized 存在館藏索引 → `already_owned`
   - isbn_normalized 不在館藏索引 → `available`
4. 對 `available` 的書目：若書名（去除空白後）在館藏書名索引中找到不同 ISBN → 額外新增一筆 `same_title_different_isbn` 記錄（不覆蓋 `available`）
5. 批次寫入 `book_matches`
6. 回傳各 match_status 的統計筆數

### Step 6：Completeness Service（app/services/completeness_service.py）

實作 `compute(book: dict, overrides: dict = None) -> str`：

根據 spec 中本土文化表欄位分級，判斷 `completeness_status`：

**required_blocking 檢查（任一缺失 → `missing_required`）：**
- title：book['title'] 或 overrides.get('title') 非空
- 定價可用：list_price 或 purchase_price 至少一欄有值（含 overrides）

注意：ISBN 有效性已由 isbn_status 負責；completeness_status 不重複檢查 isbn。

**required_review 檢查（通過 blocking 後，任一缺失 → `needs_review`）：**
- author 非空
- publisher 非空
- award_item 非空（local_culture 專用；缺少時提醒，不阻擋匯出）

V1 local_culture 不使用 award_notes 進行強制 needs_review 判斷。

**全部通過 → `export_ready`**

另實作 `recompute_for_book(vendor_book_id: int)`：當使用者更新 user_overrides 後，重新計算並更新 `completeness_status`。

### Step 7：Validation Service（app/services/validation_service.py）

實作 `check_export_readiness(project_id: int, price_field: str) -> dict`：

讀取 project 的所有 selection_items，逐筆評估可匯出狀態：

```python
{
    "total_selected": int,       # 總選書筆數
    "export_ready": int,         # 可直接匯出
    "needs_review": int,         # 可匯出但有缺失提醒欄位
    "missing_required": int,     # 不可匯出，缺 required_blocking
    "already_owned": int,        # 異常：被選但 match_status 為 already_owned
    "details": [                 # 逐筆明細
        {
            "vendor_book_id": int,
            "title": str,
            "match_status": str,
            "completeness_status": str,
            "missing_blocking_fields": list,    # 缺少的 required_blocking 欄位名稱
            "missing_review_fields": list,      # 缺少的 required_review 欄位名稱
            "can_export": bool
        }
    ]
}
```

此服務供匯出前置檢查頁（export-check.html）與實際匯出呼叫前的驗證使用。

### Step 8：Selection Service（app/services/selection_service.py）

- `upsert_selection(project_id, vendor_book_id, quantity, notes, user_id)`：quantity=0 時刪除該筆
- `get_selection_summary(project_id) -> dict`：回傳 count、total_list_price、total_purchase_price、items 清單
- `get_selected_books(project_id) -> list`：回傳含 vendor_book 資料、match_status、completeness_status、兩種金額的完整清單
- `clear_all_selections(project_id, user_id)`：清空指定專案的選書（呼叫前需前端確認）

### Step 9：匯出前置準備（手動，實作 export_service 前執行）

**實作前必須先手動開啟空白範本，確認：**

- 校名填入的儲存格位置（例：B3）
- 核定金額的儲存格位置
- 書目資料起始列號（第幾列開始是資料行）
- 各匯出欄位對應的欄號（排序、書名、作者、出版社、ISBN、採購數量、定價、小計、獲獎項目、備註）
- 合計列格式與位置

將上述資訊記錄為 `app/services/export_service.py` 頂端的 `TEMPLATE_CONFIG` 常數字典（不寫死在函式內）。

### Step 10：Export Service（app/services/export_service.py）

#### 10.1 Value Resolution

實作 `resolve_field(book: dict, field: str) -> str`：

```
user_overrides[field] → book[field] (normalized) → raw_row[field] → ""
```

匯出時每個欄位都透過此函式取值。

#### 10.2 ExportSettings

```python
@dataclass
class ExportSettings:
    project_id: int
    school_name: str
    approved_budget: float | None
    price_field: str              # "list_price" or "purchase_price"
    subtotal_mode: str            # "quantity_times_list_price" or "quantity_times_purchase_price"
    template_path: str
    output_dir: str
    exported_by: int
```

#### 10.3 export_local_culture(settings) -> str

1. 呼叫 `validation_service.check_export_readiness`；若有 `missing_required` 書目，拋出例外並回報哪本書缺哪個欄位
2. 複製範本至 `exports/` 目錄，輸出檔名含日期時間（`本土文化採購書單_{YYYYMMDD}_{HHmmss}.xlsx`）
3. `openpyxl.load_workbook(copy_path)` 開啟複製檔
4. 填入校名、核定金額（若有）至 `TEMPLATE_CONFIG` 指定的儲存格
5. 讀取 selection_items join vendor_books，依 vendor_seq 或 id 排序
6. 逐列填入，每個欄位呼叫 `resolve_field`；定價欄依 `price_field`；小計依 `subtotal_mode`
7. 填入合計行（總冊數、依 subtotal_mode 計算的總金額）
8. 儲存輸出檔
9. 建立 `export_jobs` 紀錄（記錄 template_path）
10. 回傳輸出檔路徑

**重要**：`00_source/` 原始範本以 `openpyxl.load_workbook(..., read_only=True)` 僅讀取，每次匯出複製至 `exports/` 後操作，原始範本不被寫入。

### Step 11：FastAPI Routers（app/routers/）

**app/main.py**

```python
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=config.session_secret_key)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
# 掛載各 router
@app.on_event("startup")
async def startup():
    db.run_migrations()
    db.ensure_initial_data()  # 預設管理員帳號 + 預設採購專案
```

**projects router（/api/projects）**
- `GET /`：列出所有採購專案
- `POST /`：建立新專案
- `GET /{id}`：取得專案詳情
- `PUT /{id}`：更新專案設定（name、price_field、subtotal_mode 等）

**auth router（/api/auth）**
- `POST /login`：驗證帳密，設定 session cookie
- `POST /logout`：清除 session

**imports router（/api/imports）**
- `POST /holdings`：上傳學校館藏 .xls，執行匯入
- `POST /vendor-books`：上傳書商書單 .xlsx，執行匯入（body 含 project_id）
- `GET /batches`：列出匯入批次（可依 project_id 篩選）
- `GET /profiles`：列出欄位對應設定
- `POST /profiles`：儲存欄位對應設定

**books router（/api/books）**
- `GET /matches`：取得比對結果（query params: project_id, match_status, completeness_status）
- `POST /run-match`：重新執行比對（body: project_id）
- `GET /stats`：取得 match_status + completeness_status 統計（query: project_id）
- `PATCH /{id}/overrides`：更新書目 user_overrides（呼叫後重新計算 completeness_status）

**selections router（/api/selections）**
- `GET /`：取得選書清單（query: project_id）
- `POST /`：更新選書數量（body: project_id, vendor_book_id, quantity, notes）
- `DELETE /`：清空選書（body: project_id）

**exports router（/api/exports）**
- `GET /check`：執行匯出前置檢查，回傳 validation_service 結果（query: project_id, price_field, subtotal_mode）
- `POST /local-culture`：執行匯出，body: ExportSettings；回傳 job_id
- `GET /jobs`：列出匯出記錄（query: project_id）
- `GET /download/{job_id}`：下載匯出 Excel（FileResponse）

所有 `/api/` 路由加 `Depends(require_auth)` 保護。

### Step 12：Account / Login 基礎設計（app/auth.py）

- 使用 `SessionMiddleware`（session 儲存於 signed cookie）
- 密碼以 `passlib[bcrypt]` 雜湊儲存
- `ensure_initial_data()` 中：若 users 表為空，從 config.yaml 讀取 `default_admin_username` / `default_admin_password` 建立預設帳號
- `require_auth`：讀取 session 中的 user_id；無效時回傳 401（JSON 請求）或導向 `/login.html`（HTML 請求）
- V1 不實作密碼修改頁面

### Step 13：前端頁面設計

八個靜態 HTML 頁面，Vanilla JS（Fetch API），共用 `css/style.css`。

**UI 規範**
- 背景：`#ffffff`；次要背景：`#f5f5f7`
- 圓角：`8px`
- 字型：`system-ui, -apple-system, "PingFang TC", "Noto Sans CJK TC", sans-serif`
- 表格 row hover：`#f0f0f0`
- match_status badge 色：available（綠）、already_owned（灰）、missing_isbn（黃）、invalid_isbn（紅）、same_title_different_isbn（橘）
- completeness_status badge 色：export_ready（綠）、needs_review（黃）、missing_required（紅）

**流程導覽（所有頁面頂部顯示）**

```
採購專案選擇 → 匯入 → 比對結果 → 選書 → 匯出前檢查 → 匯出
```

**login.html**
- 置中卡片，帳號密碼輸入

**projects.html（採購專案）**
- 列出所有專案（名稱、類型、選書筆數、上次匯出時間）
- 「選擇」按鈕設定目前工作專案（儲存於 sessionStorage）
- 「新增專案」按鈕（V1 只允許 local_culture 類型；general_books 顯示為灰色「即將推出」）
- 專案設定：可修改 price_field 與 subtotal_mode 預設值

**index.html（首頁）**
- 顯示目前選定專案名稱
- 狀態摘要：館藏筆數、書單筆數、選書筆數、上次匯出時間
- 快速跳轉連結至各功能頁

**import.html**
- 分頁籤：學校館藏 / 書商書單（上方顯示目前選定專案）
- 拖曳或點選上傳；上傳後顯示欄位對應結果
- 未對應欄位顯示下拉選單讓使用者補齊
- 「儲存欄位設定」按鈕；匯入紀錄表格

**match.html**
- 頂部統計：各 match_status 與 completeness_status 的筆數 badge
- 篩選器：match_status（全部 / 可採購 / 已館藏 / ISBN 異常）× completeness_status（全部 / 可匯出 / 需補資料 / 缺必填）
- 表格：書名、作者、出版社、ISBN、獲獎項目、match_status badge、completeness_status badge
- 「重新比對」按鈕

**selection.html**
- 顯示 match_status = `available` 的書目
- 每筆右側：採購數量輸入框 + completeness_status badge + 「修正資料」連結（展開 inline 編輯 overrides）
- 底部即時預算試算：以 list_price 與 purchase_price 分別顯示總計
- 「清空選書」按鈕（需確認）

**export-check.html（匯出前置檢查）**
- 顯示選定 price_field + subtotal_mode
- 四格統計卡：已選 N 本 / 可匯出 N 本 / 需補資料 N 本 / 不可匯出 N 本
- 明細表格：各本書的 completeness_status 與缺少欄位清單
- 「繼續匯出」按鈕（若有不可匯出書目，按鈕顯示警告；needs_review 書目可繼續）

**export.html（匯出設定）**
- 表單：校名、核定金額（選填）、price_field（radio）、subtotal_mode（radio）
- 選書預覽表格（僅顯示 export_ready + needs_review 的書目）
- 「產生 Excel」按鈕 → 執行匯出 → 顯示下載連結
- 歷史匯出紀錄（時間、檔名、price_field 設定、subtotal_mode、總金額）

### Step 14：start.bat

```bat
@echo off
chcp 65001 >nul
echo 圖書採購系統啟動中...
cd /d %~dp0

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [錯誤] 找不到 Python，請先安裝 Python 3.10 或以上版本。
    pause
    exit /b 1
)

if not exist .venv\ (
    echo 首次啟動：正在建立虛擬環境...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [錯誤] 虛擬環境建立失敗。
        pause
        exit /b 1
    )
)

call .venv\Scripts\activate.bat
echo 安裝或更新依賴套件...
pip install -r requirements.txt --quiet

echo 啟動伺服器，請稍候...
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8765
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765

pause
```

### Step 15：config.yaml 初始範本

```yaml
server:
  host: "127.0.0.1"
  port: 8765

database:
  path: "./data/school_lib.db"

auth:
  default_admin_username: "admin"
  default_admin_password: "changeme"
  session_secret_key: "please-change-this-to-a-random-string"

source:
  local_culture_export_template: "./00_source/高雄市115年度○○區○○國小圖書館（室）充實本土文化相關圖書採購書單(空白).xlsx"

export:
  output_dir: "./exports"
  default_price_field: "purchase_price"
  default_subtotal_mode: "quantity_times_purchase_price"

default_project:
  name: "115年度本土文化採購"
  project_type: "local_culture"
```

### Step 16：requirements.txt

```
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
starlette>=0.37.0
itsdangerous>=2.1.0
passlib[bcrypt]>=1.7.4
pandas>=2.1.0
openpyxl>=3.1.2
xlrd>=2.0.1
pyyaml>=6.0.1
python-multipart>=0.0.9
```

### Step 17：.gitignore

```
data/
exports/
.venv/
__pycache__/
*.pyc
*.db
*.sqlite3
```

### Step 18：端對端驗收流程

1. 執行 `start.bat`，確認自動建立 `.venv`、安裝 dependencies 並啟動
2. 開啟 `http://127.0.0.1:8765`，確認導向 login 頁
3. 以預設帳號登入，確認進入首頁並顯示預設採購專案
4. 到 projects.html，確認預設 local_culture 專案已存在，可修改 price_field / subtotal_mode
5. 匯入 `00_source/學校館藏.xls`，確認欄位對應正確，記錄匯入筆數
6. 選擇採購專案後，匯入 `00_source/更新-日苑-高雄 本土推薦書單-去除重複ISBN.xlsx`，確認欄位對應
7. 到 match.html 確認各 match_status 統計正確；確認 completeness_status badge 顯示
8. 對一本 `missing_required` 書目輸入 user_override（補填書名或定價），確認 completeness_status 更新
9. 在 selection.html 選書並填入數量，確認 list_price 與 purchase_price 兩種預算試算顯示
10. 到 export-check.html，確認四格統計（已選 / 可匯出 / 需補資料 / 不可匯出）數字正確
11. 到 export.html 填入校名，設定 price_field / subtotal_mode，執行匯出
12. 開啟匯出 Excel，確認格式與原始範本一致；確認定價欄與小計欄依設定計算
13. 確認 `00_source/` 原始檔案的修改時間未變動

## 風險與注意事項

1. **學校館藏 .xls 加密**：xlrd 2.x 僅支援未加密的 .xls；若有密碼保護，需在匯入錯誤訊息中說明，告知使用者先在 Excel 移除保護。

2. **教育局範本儲存格位置（高風險）**：匯出服務依賴 `TEMPLATE_CONFIG` 常數記錄的儲存格位置。實作 Step 9 前必須先手動讀取範本確認，記錄為常數。若教育局日後改版範本，常數需同步更新。

3. **Excel 欄位自動偵測脆弱**：書商若更改欄名（如「條碼」改為「ISBN碼」），自動偵測會失準。手動欄位對應介面是必要的後備路徑，不可省略。

4. **ISBN 資料品質**：館藏資料中 ISBN 可能大量缺失或格式不一；`missing_isbn` 與 `invalid_isbn` 筆數需清楚顯示於 match.html，不得靜默忽略。

5. **completeness_status 未即時更新**：user_overrides 修改後需呼叫 `completeness_service.recompute_for_book` 更新資料庫；若前端修改後未觸發重算，匯出前檢查結果會過時。

6. **price_field 與 subtotal_mode 獨立設定的 UX**：兩者可獨立設定，但組合如「定價欄顯示原定價，小計用採購單價計算」在介面上需清楚標示，避免使用者誤解小計算法。

7. **same_title_different_isbn 書名比對**：書名完全比對對含異體字或簡繁混用的中文書名可能漏標。V1 接受此限制，不引入模糊比對。

8. **Session secret key 安全性**：config.yaml 預設值不安全；start.bat 首次啟動後應在終端機顯示提醒，告知使用者修改。

9. **Windows 路徑含中文**：00_source 內的檔名含中文；Python `pathlib.Path` 在 Windows UTF-8 locale 下通常可用，但需在實際 Windows 環境測試。

10. **瀏覽器開啟時序**：start.bat 的 `timeout /t 2` 延遲不足以保證 uvicorn 完全就緒；可在 login 頁面 JavaScript 加入重試邏輯（每秒 ping `/api/health`，就緒後顯示登入表單）。

11. **匯出檔名衝突**：若同一秒執行兩次匯出，時間戳記相同；可在輸出檔名後附加 export_jobs.id 的後綴（如 `_1`）避免覆蓋。

12. **procurement_projects 擴充邊界**：general_books 在 V2 實作時，import_service 與 match_service 需依 project_type 分支處理；V1 的 vendor_books 欄位（award_item、vendor_seq）對 general_books 為選填，不應在 V2 加 NOT NULL constraint。

## 預計影響範圍

**新增**：
- `app/`（後端程式碼）
- `migrations/`（資料庫 schema）
- `app/static/`（前端頁面）
- `requirements.txt`、`start.bat`、`config.yaml`、`.gitignore`

**不修改**：
- `00_source/`（所有原始 Excel 檔案）
- `docs/`（規則與文件）
- `CLAUDE.md`、`AGENTS.md`

**執行時產生（gitignore）**：
- `data/school_lib.db`
- `exports/*.xlsx`
- `.venv/`

## 驗證指令

本專案目前無既有工具設定，以下為建議指令，**需使用者確認後安裝**：

- lint: `ruff check app/`（替代方案：`flake8 app/`）
- format: `ruff format --check app/`（替代方案：`black --check app/`）
- typecheck: 待確認（`mypy app/` 可選，V1 不強制）
- test: `pytest tests/ -v`（tests/ 目錄將於實作時建立）
- build/啟動驗證: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8765`

若使用者不引入新工具，以手動執行 Step 18 端對端驗收流程取代。

## 成果報告

- result_report_mode: none
- 適用情境：本任務以功能正確執行為驗收標準，Step 18 端對端驗收流程涵蓋所有驗收條件，無需額外成果報告。
