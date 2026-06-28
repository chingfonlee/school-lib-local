# Plan: task-user-guide-with-screenshots

## 概覽

| 屬性 | 值 |
|------|-----|
| task-id | task-user-guide-with-screenshots |
| 類型 | chore |
| base branch | main |
| 分支 | chore/task-user-guide-with-screenshots |
| result_report_mode | none |

---

## Phase 1：合成館藏與環境確認

### 步驟 1：建立 sample-data/holdings/ 目錄

```powershell
New-Item -ItemType Directory -Force sample-data\holdings
```

### 步驟 2：建立 sample-data/holdings/README.md

內容：說明用途（合成虛構資料，僅供測試流程，不含真實學校館藏）、與 sample-data/vendor-lists/README.md 同保守措辭。

### 步驟 3：從 local-culture vendor list 取得 5 個真實 ISBN

執行 openpyxl 腳本（不要截圖、不要修改任何檔案，僅讀取並回報）：

```python
import openpyxl
wb = openpyxl.load_workbook("sample-data/vendor-lists/local-culture-vendor-list-2026.xlsx", data_only=True, read_only=True)
ws = wb.active
# 找 ISBN 欄，取前 5 個非空值
# 回報欄位名稱與 5 個 ISBN 值
```

將取得的 5 個 ISBN 記錄，供步驟 4 使用。

### 步驟 4：建立 sample-data/holdings/sample-holdings.xlsx

用 openpyxl 程式建立（確保可重複產生）：

- 欄位：`書名`、`作者`、`ISBN`、`出版社`、`索書號`
- 15 列資料：
  - **前 5 列**：ISBN 取自步驟 3（製造比對命中，示範「已館藏」狀態）；書名/作者使用對應的公開書目資訊（從 vendor list 同列讀取）
  - **後 10 列**：虛構書目，書名使用「示範書目一」到「示範書目十」，作者「示範作者」，出版社「示範出版社」，ISBN 使用格式 `9780000000010`～`9780000000100`（虛構格式，不命中任何書商書單）

> **隱私確認**：前 5 列的書名/作者資料為公開書目資訊，與 vendor list 同一來源，無個資風險。後 10 列為全虛構，無風險。

### 步驟 5：Commit 合成館藏資料

```
chore(task-user-guide-with-screenshots): add synthetic sample holdings
```

包含：
- `sample-data/holdings/README.md`
- `sample-data/holdings/sample-holdings.xlsx`

---

## Phase 2：截圖環境確認

> **已確認決策（2026-06-28）**
> 1. **截圖方式**：優先 Playwright 自動化。`playwright` 不加入正式 `requirements.txt`；使用臨時安裝或 `requirements-dev.txt`。若 Playwright 卡在檔案上傳或流程操作，fallback 手動截圖。
> 2. **00_source/ 範本**：僅作本機截圖用途，不 commit。本機已有則直接用；若無，建立臨時 dummy 範本於 `00_source/`（gitignored），截圖完可保留或刪除。
> 3. **DB 還原**：備份/還原 `data/school_lib.db`。截圖中不得出現真實學校名稱、真實本機路徑、真實密碼或 session secret。

### 步驟 6：確認 config.yaml

- 若 `config.yaml` 不存在，依 `config.example.yaml` 建立
- 確認以下欄位使用安全的示範值（非真實資訊）：
  - `auth.default_admin_password`：任何非空值（示範用，例如 `admin-demo`）
  - `auth.session_secret_key`：任何非空值（示範用）
- **不要** 修改 `database.path`（保持 `./data/school_lib.db` 以避免影響現有資料）

### 步驟 7：確認 00_source/ 匯出範本

```powershell
Get-ChildItem 00_source/ -Filter "*.xlsx" 2>$null
```

**已確認策略**：僅供本機截圖，不 commit `00_source/` 任何檔案。

- **若本機已有範本**：直接使用，繼續 Phase 3。
- **若無範本**：在 `00_source/` 建立最小結構 dummy xlsx（欄位符合 config.yaml column_mappings，內容空白），供截圖用。dummy 不 commit（`00_source/` 已列於 `.gitignore`）。

> 建立 dummy 的最小結構：openpyxl 新建 xlsx，加一列 header（A/B/C/D/E 等），存至 `00_source/` 對應路徑即可。

### 步驟 8：安裝 Playwright（確認使用自動化截圖）

**已確認**：優先 Playwright，不加入正式 `requirements.txt`。

```powershell
# 臨時安裝（.venv 範圍內，不修改 requirements.txt）
.venv\Scripts\pip.exe install playwright
.venv\Scripts\playwright.exe install chromium
```

若需要以 `requirements-dev.txt` 記錄（供未來重建截圖環境）：

```
# requirements-dev.txt
playwright>=1.44
```

建立 `scripts/take-screenshots.py`（可重複執行的截圖腳本）。

**Fallback 條件**：若 Playwright 在 Windows 上無法處理 `<input type="file">` 上傳（`page.set_input_files` 失敗），改用方式 B（手動截圖）：
- 啟動服務後，按截圖清單手動操作瀏覽器
- Windows Snipping Tool（Win+Shift+S）或 DevTools 截圖（F12 → Ctrl+Shift+P → screenshot）
- 視窗固定 1280px 寬，截圖後手動命名存入 `docs/user-guide/images/`

---

## Phase 3：截圖執行

### 步驟 9：備份現有 DB

```powershell
if (Test-Path data\school_lib.db) {
    Copy-Item data\school_lib.db data\school_lib.db.screenshot_bak
}
```

若備份失敗（無 DB），繼續執行（截圖後還原步驟將跳過 rename）。

### 步驟 10：啟動乾淨測試 DB 並開始服務

移除現有 DB，讓服務啟動時建立乾淨 DB：

```powershell
Remove-Item data\school_lib.db -ErrorAction SilentlyContinue
```

若使用 Playwright：腳本內以 `subprocess` 啟動服務進程，等待 `127.0.0.1:8765` 回應後再開始操作。

若手動：另開終端機執行服務，確認瀏覽器可開啟後開始截圖。

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

### 步驟 11：依截圖清單逐一截圖

**截圖隱私硬性規則（每張截圖前確認）**：
- 學校名稱：只允許「○○國小」、「測試學校」、「示範學校」，**禁止任何真實學校名稱**
- 本機路徑：禁止 `C:\Users\[真實用戶名]\...`；允許 `127.0.0.1:8765`、`./exports/`
- 密碼/session key：禁止出現於畫面（Web UI 通常不顯示 config 內容，仍需確認）
- 個資：禁止（合成館藏無個資，vendor list 為公開書目）

若方式 A（Playwright）：執行 `scripts/take-screenshots.py`，自動輸出截圖至 `docs/user-guide/images/`。腳本應在截圖前填入合規的示範值（學校名稱使用「○○國小（示範）」）。

若方式 B（手動）：依截圖清單逐步操作並截圖，截圖前逐項確認隱私規則。

### 步驟 12：停止服務並還原 DB

```powershell
# 停止服務（若 Playwright 啟動，腳本結束時自動終止）
# 還原 DB
Remove-Item data\school_lib.db -ErrorAction SilentlyContinue
if (Test-Path data\school_lib.db.screenshot_bak) {
    Rename-Item data\school_lib.db.screenshot_bak data\school_lib.db
}
```

**確認還原成功**：`Test-Path data\school_lib.db` 輸出 `True`（若原本存在的話）。

### 步驟 13：截圖隱私掃描

逐張目視確認並記錄：
- 無真實學校名稱
- 無本機真實路徑
- 無個資（人名、電話、地址）
- 無 config secret（密碼明文、session key）

如任一張截圖有問題，需重新截圖後再繼續。

如發現問題，重新截圖或裁切後再確認。

---

## Phase 4：撰寫 complete-walkthrough.md

### 步驟 14：建立 docs/user-guide/images/ 目錄並存入截圖

```powershell
New-Item -ItemType Directory -Force docs\user-guide\images
```

截圖已存入此目錄（步驟 11）。

### 步驟 15：建立 docs/user-guide/complete-walkthrough.md

每個步驟章節格式：

```markdown
## 步驟 N：[步驟標題]

[目的：一句話說明此步驟的目的]

**操作說明：**

1. ...
2. ...

![alt text 描述](images/NN-name.png)

**預期畫面：** [說明截圖中應看到什麼]

> **注意：** [常見問題或注意事項，若有]
```

文件章節（按順序）：

1. 前言（系統用途、本文件使用對象）
2. 快速索引（章節目錄）
3. 系統用途簡介
4. 取得專案與安裝（參照 README.md / install-windows.md）
5. 登入系統 → `01-login.png`
6. 首頁與採購專案列表（空白狀態）→ `02-projects-empty.png`
7. 建立採購專案 → `03-project-create.png`
8. 匯入館藏 → `04-import-holdings.png`
9. 使用 sample-data 範例書單（說明可直接使用 sample-data/holdings/ 和 sample-data/vendor-lists/）
10. 匯入書商書單 → `05-import-vendor-list.png`
11. 查看比對結果 → `06-match-results.png`
12. 選書 → `07-selection.png`
13. 匯出前檢查 → `08-export-check.png`
14. 匯出 Excel → `09-export.png`
15. 查看匯出結果 → `10-dashboard-after-export.png`
16. 資料位置與備份說明（data/、exports/）
17. 常見問題（整合 quickstart 問題，依 complete walkthrough 場景整理）

### 步驟 16：Commit walkthrough 文件與截圖

```
docs(task-user-guide-with-screenshots): add complete walkthrough with screenshots
```

包含：
- `docs/user-guide/complete-walkthrough.md`
- `docs/user-guide/images/*.png`（10 張）

---

## Phase 5：更新 README.md

### 步驟 17：README.md 新增連結

在現有「快速開始」段落後（或「範例書單」段落旁），新增一行或一段：

```markdown
完整操作流程（含截圖）請見 [完整使用者導覽](docs/user-guide/complete-walkthrough.md)。
```

### 步驟 18：Commit README 更新

```
docs(task-user-guide-with-screenshots): add walkthrough link to README
```

---

## Phase 6：最終驗證

### 步驟 19：git status --short

預期輸出：空（乾淨）。

### 步驟 20：驗證 git ls-files

```powershell
git ls-files docs/user-guide/images/     # 預期 10 個 .png 檔
git ls-files sample-data/holdings/       # 預期 2 個檔案
git ls-files docs/user-guide/complete-walkthrough.md  # 預期有輸出
```

### 步驟 21：執行 pytest

```powershell
Copy-Item config.example.yaml config.yaml -ErrorAction SilentlyContinue
.venv\Scripts\python.exe -m pytest -q
```

預期：全數通過（walkthrough 為 Markdown，不影響 pytest）。

### 步驟 22：瀏覽器確認

啟動服務，以瀏覽器開啟 `docs/user-guide/complete-walkthrough.md`（或在 GitHub 上預覽），確認：
- 所有 `![...](images/...)` 圖片正常顯示
- 所有章節連結有效
- 文字可讀，流程合理

### 步驟 23：文件隱私最終掃描

```powershell
# 掃描 committed 文件是否含敏感關鍵字
git grep -n "Users\\" docs/user-guide/complete-walkthrough.md
git grep -n "password" docs/user-guide/complete-walkthrough.md
```

確認：無本機路徑、無密碼明文、無真實學校名稱。

---

## 截圖清單

| 截圖 | 對應頁面 | 畫面狀態 | 測試資料需求 | 敏感資料風險 | 截圖前注意事項 |
|------|---------|---------|------------|------------|--------------|
| 01-login.png | 登入頁 | 空白表單（帳密欄位空白） | 無（不需 DB 資料） | 低 | URL bar 顯示 127.0.0.1:8765；帳密欄位保持空白 |
| 02-projects-empty.png | 採購專案列表 | 已登入，無任何專案 | 乾淨 DB | 低 | 確認登入帳號不顯示個人名稱 |
| 03-project-create.png | 新增採購專案 | 對話框已填「115年度本土文化採購（示範）」，類型已選 | 空白 DB | 低 | 確認專案名稱不含真實學校名 |
| 04-import-holdings.png | 匯入頁面（館藏） | 館藏匯入完成，顯示「匯入成功，共 15 筆」 | sample-data/holdings/sample-holdings.xlsx | 低（書名為公開書目或虛構資料） | 確認成功訊息顯示；確認無真實路徑於畫面中 |
| 05-import-vendor-list.png | 匯入頁面（書商書單） | 書商書單匯入完成，顯示成功筆數（~679筆） | sample-data/vendor-lists/local-culture-vendor-list-2026.xlsx | 低（公開書目） | 確認顯示成功訊息 |
| 06-match-results.png | 比對結果 | 顯示已館藏/未館藏統計；可見篩選按鈕 | 館藏 + 書商書單均已匯入 | 低 | 確認統計數字合理（5 已館藏，~674 未館藏） |
| 07-selection.png | 選書 | 已選 3-5 本書，顯示選書清單與完整度狀態 | 比對結果就緒 | 低 | 確認顯示的書名為公開書目 |
| 08-export-check.png | 匯出前檢查 | 顯示選書清單，部分「可匯出」部分「需補充」 | 選書完成，欄位部分填寫 | 低 | 確認完整度標示清晰 |
| 09-export.png | 匯出頁面 | 學校名稱填「○○國小（示範）」，範本已選，尚未點產生 | 選書完成；00_source/ 需有範本或 dummy | **高** | **嚴格確認學校名稱為示範值；確認無真實學校名稱** |
| 10-dashboard-after-export.png | 採購專案列表/首頁 | 匯出完成後，專案卡片顯示完成/匯出狀態 | 匯出完成 | 中（匯出檔名可能含學校名） | 確認匯出記錄顯示的檔名含示範學校名稱 |

---

## 預計新增／修改檔案

| 路徑 | 類型 | 說明 |
|------|------|------|
| `sample-data/holdings/README.md` | 新增 | 合成館藏說明 |
| `sample-data/holdings/sample-holdings.xlsx` | 新增 | 合成館藏 Excel（openpyxl 產生） |
| `docs/user-guide/images/*.png` | 新增 × 10 | 截圖（截圖後 commit） |
| `docs/user-guide/complete-walkthrough.md` | 新增 | 完整操作導覽（繁體中文，含截圖） |
| `scripts/take-screenshots.py` | 新增（方式 A 才有） | Playwright 截圖腳本 |
| `requirements.txt` 或 `requirements-dev.txt` | 修改（方式 A 才有） | 新增 `playwright` 依賴 |
| `README.md` | 修改 | 新增 complete-walkthrough.md 連結 |

---

## 測試資料準備方式

### 合成館藏 xlsx 建立腳本邏輯

```python
import openpyxl

# Step 1: 從 local-culture vendor list 取得 5 個真實 ISBN
wb_vendor = openpyxl.load_workbook(
    "sample-data/vendor-lists/local-culture-vendor-list-2026.xlsx",
    data_only=True, read_only=True
)
ws_vendor = wb_vendor.active
# 找 ISBN 欄（掃描第一列欄位名稱）
# 取前 5 個非空 ISBN 及對應書名/作者

# Step 2: 建立合成館藏
wb_holdings = openpyxl.Workbook()
ws_holdings = wb_holdings.active
ws_holdings.title = "館藏"
ws_holdings.append(["書名", "作者", "ISBN", "出版社", "索書號"])

# 前 5 列：使用真實 ISBN + 對應書目（公開書目資訊）
for i, (isbn, title, author) in enumerate(real_books):
    ws_holdings.append([title, author, isbn, "示範出版社", f"R{i+1:03d}"])

# 後 10 列：全虛構
fictional_isbns = [f"978000000{i:04d}" for i in range(1, 11)]
for i, isbn in enumerate(fictional_isbns):
    ws_holdings.append([f"示範書目{i+1}", "示範作者", isbn, "示範出版社", f"F{i+1:03d}"])

wb_holdings.save("sample-data/holdings/sample-holdings.xlsx")
```

---

## 截圖執行方式（方式 A：Playwright）

### scripts/take-screenshots.py 架構

```python
from playwright.sync_api import sync_playwright
import time, pathlib

SCREENSHOTS_DIR = pathlib.Path("docs/user-guide/images")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "http://127.0.0.1:8765"
ADMIN_USER = "admin"
ADMIN_PASS = "admin-demo"  # 讀取自 config.yaml 或作為參數傳入

def take_screenshots():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})

        # 01-login.png：登入前，空白表單
        page.goto(f"{BASE_URL}/login")
        page.screenshot(path=SCREENSHOTS_DIR / "01-login.png")

        # 登入
        page.fill("[name=username]", ADMIN_USER)
        page.fill("[name=password]", ADMIN_PASS)
        page.click("[type=submit]")
        page.wait_for_load_state("networkidle")

        # 02-projects-empty.png：首頁，無專案
        page.screenshot(path=SCREENSHOTS_DIR / "02-projects-empty.png")

        # 03-project-create.png：新增專案對話框
        # ...（依實際 UI 元素 selector 調整）

        # 依此類推...

        browser.close()

if __name__ == "__main__":
    take_screenshots()
```

> **注意**：scripts/take-screenshots.py 的實際 selector 需在啟動服務後，依實際 HTML 元素確認。Phase 3 執行前，先 `grep` 或 DevTools 確認各頁面的 form selector。

---

## 文件撰寫策略

- 繁體中文，面向非工程使用者
- 每章節固定格式：目的 → 操作說明（條列） → 截圖 → 預期畫面 → 注意事項
- 避免技術術語（「FastAPI」、「endpoint」、「schema」）；使用「系統」、「頁面」、「欄位」
- 路徑使用相對路徑（`./data/`、`./exports/`），不使用任何真實本機路徑
- 截圖 alt text 格式：`[步驟N：[頁面名稱] - [畫面狀態]]`
  - 範例：`![步驟5：比對結果頁 - 顯示已館藏與未館藏書目統計](images/06-match-results.png)`

---

## 風險與回滾策略

| 風險 | 機率 | 回滾策略 |
|------|------|---------|
| Playwright file upload 在 Windows 上失敗 | 中 | 改用手動截圖（方式 B） |
| 00_source/ 缺乏匯出範本，09/10 截圖異常 | 中 | 建立 dummy 範本或以說明文字替代截圖 |
| 截圖含敏感資訊（學校名稱） | 低 | 重新截圖；更換示範值後再截 |
| openpyxl 讀取 vendor list ISBN 欄失敗 | 低 | 手動指定 5 個已知 ISBN |
| sample-holdings.xlsx commit 後含個資 | 極低（全為虛構） | 若確認後仍有疑慮，以 `git filter-repo` 移除 |
| pytest 因截圖或 Markdown 異常失敗 | 極低（不影響 py 測試） | 確認 pytest 只掃描 app/tests/ |

---

## Commit 計劃

| Commit | 內容 |
|--------|------|
| 1 | `chore(task-user-guide-with-screenshots): add synthetic sample holdings` |
| 2 | `docs(task-user-guide-with-screenshots): add complete walkthrough with screenshots` |
| 3 | `docs(task-user-guide-with-screenshots): add walkthrough link to README` |
| （可選）4 | `chore(task-user-guide-with-screenshots): add playwright screenshot script` |

---

## 驗證指令

```powershell
# 1. 確認 working tree 乾淨
git status --short

# 2. 確認新增檔案已追蹤
git ls-files docs/user-guide/images/
git ls-files sample-data/holdings/
git ls-files docs/user-guide/complete-walkthrough.md

# 3. pytest
Copy-Item config.example.yaml config.yaml -ErrorAction SilentlyContinue
.venv\Scripts\python.exe -m pytest -q

# 4. 圖片連結掃描（確認 walkthrough 的所有 img 路徑有效）
$imgs = Select-String -Path docs\user-guide\complete-walkthrough.md -Pattern "!\[.*?\]\((images/.*?\.png)\)" -AllMatches |
    ForEach-Object { $_.Matches } | ForEach-Object { $_.Groups[1].Value }
$imgs | ForEach-Object {
    $p = "docs\user-guide\$_"
    if (Test-Path $p) { Write-Output "OK: $_" } else { Write-Output "MISSING: $_" }
}

# 5. 隱私掃描
git grep -rn "C:\\Users\\" -- docs/user-guide/
git grep -rn "password" -- docs/user-guide/complete-walkthrough.md
```
