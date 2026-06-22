# Plan: task-user-docs-foundation

## 實作步驟

### 步驟 0：盤點現有狀態

執行確認：
- `README.md` 不存在（根目錄）
- `docs/user-guide/` 目錄不存在
- 可用素材：`start.bat`（Python 需求、啟動流程）、app/static/*.html（頁面名稱）、`docs/STATUS.md`、既有 task spec/plan

整理 7 個主要頁面對應（供步驟 4 使用）：

| 操作 | 頁面 |
|------|------|
| 選擇 / 建立採購專案 | projects.html |
| 匯入館藏 / 書商書單 | import.html |
| 比對結果 | match.html |
| 選書 | selection.html |
| 匯出前檢查 | export-check.html |
| 匯出 Excel | export.html |
| 館藏查詢 | holdings.html |

### 步驟 1：建立 docs/user-guide/ 目錄

```
docs/user-guide/
```

目錄不存在時建立。

### 步驟 2：撰寫 README.md

路徑：`README.md`（專案根目錄）

內容結構（依序）：

1. 專案名稱與一句話說明
2. **用途**：本地端圖書採購輔助工具，協助國小教師完成書商書單比對、選書與匯出
3. **支援範圍**：本土文化採購（主要功能）、一般圖書採購（目前支援）
4. **本地資料安全**：所有資料存於本機 `data/school_lib.db`，不上傳雲端
5. **系統需求**：Windows 10/11、Python 3.10–3.13（不支援 3.14）、現代瀏覽器（Chrome / Edge）
6. **快速啟動**：執行 `start.bat` → 等待安裝完成 → 瀏覽器開啟 http://127.0.0.1:8765
7. **目前開發狀態**：活躍開發中，功能持續更新
8. **文件**：連結至 `docs/user-guide/install-windows.md`、`docs/user-guide/local-culture-quickstart.md`

寫作原則：面向教師 / 學校行政人員，避免技術術語；對尚未穩定的功能使用「目前支援」等保守措辭。

### 步驟 3：撰寫 docs/user-guide/install-windows.md

內容結構（依序）：

1. **系統需求**：Windows 10/11、Python 3.10–3.13（`start.bat` 會自動偵測；不支援 3.14）
2. **取得專案**：一般描述（下載 ZIP 或 git clone），不要求特定發布包
3. **首次啟動**：
   - 雙擊 `start.bat`
   - 首次執行：自動建立 `.venv` 虛擬環境，安裝套件（需等待數分鐘）
   - 啟動完成後瀏覽器自動開啟 http://127.0.0.1:8765
4. **安全提醒**：首次使用請修改 `config.yaml` 的 `session_secret_key`（預設值不安全）
5. **預設帳號**：說明預設登入資訊請查看 `config.yaml` 的 `auth` 區塊；首次使用後請立即修改預設密碼與 `session_secret_key`；文件不直接列出預設密碼
6. **資料位置**：`data/school_lib.db`（資料庫）、`exports/`（匯出 Excel 檔案）
7. **常見問題**：
   - Python 找不到：說明安裝路徑與版本確認方式
   - Port 8765 被占用：說明關閉其他程式或更改 port
   - 依賴安裝慢：說明首次需下載，後續啟動快速
   - 瀏覽器未自動開啟：手動輸入 http://127.0.0.1:8765

### 步驟 4：撰寫 docs/user-guide/local-culture-quickstart.md

內容結構（9 個主要步驟，對應實際頁面操作）：

1. **建立或選擇採購專案**（projects.html）：選擇本土文化類型
2. **匯入館藏**（import.html）：上傳館藏 Excel，說明自動欄位比對
3. **匯入書商書單**（import.html）：上傳書商書單 Excel，確認欄位對應
4. **查看比對結果**（match.html）：確認可採購 / 已館藏書目
5. **選書**（selection.html）：加入書目、修正缺漏欄位（獲獎項目、定價等）
6. **匯出前檢查**（export-check.html）：確認缺必填欄位的書目，修正或移除
7. **匯出 Excel**（export.html）：填入學校名稱，產生正式採購書單
8. **檢查匯出檔**：開啟 `exports/` 內的 Excel 確認格式與內容
9. **常見問題**：書目不出現於比對結果、欄位留空的處理、重新匯入書單

寫作原則：每個步驟說明「在哪個頁面」「做什麼」「預期結果」，文字清楚；不寫開發者技術細節。

### 步驟 5：驗證

**連結驗證**

確認 `README.md` 內的文件連結指向實際存在的檔案：
- `docs/user-guide/install-windows.md` → 存在
- `docs/user-guide/local-culture-quickstart.md` → 存在

使用 PowerShell 或 bash 確認檔案存在：
```
Test-Path docs/user-guide/install-windows.md
Test-Path docs/user-guide/local-culture-quickstart.md
```

**編碼與換行驗證**

確認三份文件符合：UTF-8 without BOM、LF 換行、final newline。

使用 PowerShell 抽查：
```powershell
# 確認無 BOM（UTF-8 with BOM 起頭為 0xEF 0xBB 0xBF）
$bytes = [System.IO.File]::ReadAllBytes("README.md")
$bytes[0..2]  # 應為 35（#）開頭，非 0xEF
```

或以 git diff --check 確認換行一致性。

**內容完整性確認**

- 確認三份文件不含密碼明文或 token
- 確認頁面名稱與 app/static/*.html 現況一致（step 0 盤點已確認）

**不執行**：程式碼語法測試（本 task 不改程式碼）

### 步驟 6：Commit

```
chore(task-user-docs-foundation): add user documentation foundation
```

涵蓋三份文件（README.md + 兩份 user-guide）。

## 風險與注意事項

**預設帳密的敏感性**

`start.bat` 與 `config.yaml` 中有預設帳號資訊。文件應描述性說明（如「首次啟動請修改管理員密碼與 session_secret_key」），不得將具體預設值寫入開放文件。

**config.yaml 的 session_secret_key**

`start.bat` L54 已有提醒。`install-windows.md` 需對應說明此步驟的重要性，但不展示預設值。

**功能範圍保守措辭**

一般圖書採購功能已實作但指南未涵蓋；README 說明「目前支援」即可，不承諾完整教學或後續規劃。

**Python 版本限制**

`start.bat` 明確排除 Python 3.14。文件說明支援範圍為 3.10–3.13。

**dir 與連結路徑**

`docs/user-guide/` 目錄目前不存在，步驟 1 需先建立再寫入文件；README.md 的連結使用相對路徑 `docs/user-guide/...`，步驟 5 驗證連結指向存在的檔案。

## 預計影響範圍

| 路徑 | 說明 |
|------|------|
| `README.md` | 新增（根目錄） |
| `docs/user-guide/install-windows.md` | 新增 |
| `docs/user-guide/local-culture-quickstart.md` | 新增 |

不影響：app/、migrations/、任何程式碼。

## 驗證指令

- lint：不適用（無程式碼變更）
- format：不適用
- typecheck：不適用
- test：不適用
- build：不適用
- 文件驗證：連結存在性確認（PowerShell `Test-Path`）、編碼抽查

## 成果報告

- result_report_mode: none
- 適用情境：無需成果報告
- 報告路徑（若 mode 非 none）：`docs/reports/task-user-docs-foundation/`
