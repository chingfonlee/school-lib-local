# 115年高雄市國小圖書館採購輔助系統

本地端圖書採購輔助工具，協助國小教師與行政人員完成書商書單比對、選書與採購書單匯出。

## 用途

本系統幫助學校完成以下工作：

- 匯入書商書單，與現有館藏比對，快速確認哪些書目尚未館藏
- 線上選書、填寫必要欄位（資格標記、推薦來源、獲獎記錄等）
- 匯出前逐筆確認，確保書單欄位完整
- 匯出符合規格的採購書單（Excel）

所有資料儲存於本機，不會上傳至任何雲端服務。

## 適用對象

- 國民小學圖書館管理員、行政人員或負責採購業務的教師
- 需處理書商書單、進行選書並匯出正式採購書單的使用者
- 目前以 Windows 本機安裝為主要使用方式

## 支援範圍

- **本土文化採購**：主要功能，包含館藏比對、選書、A 欄資格標記、H 欄推薦來源、匯出採購書單
- **一般圖書採購**：目前支援，詳細操作流程請見 [一般圖書採購快速上手](docs/user-guide/general-books-quickstart.md)

## 系統需求

| 項目 | 需求 |
|------|------|
| 作業系統 | Windows 10 / Windows 11 |
| Python | 3.10 至 3.13（不支援 3.14）—— 攜帶版不需要 |
| 瀏覽器 | Chrome 或 Edge（建議） |

## 快速開始

### 攜帶版（推薦，不需安裝 Python）

1. 至 [Releases 頁面](https://github.com/chingfonlee/school-lib-local/releases/latest) 下載 **`school-lib-portable.zip`**
2. 解壓縮至任意資料夾
3. 雙擊 `start.bat`，首次啟動輸入登入密碼
4. 瀏覽器自動開啟，以 `admin` 帳號登入

### 自行安裝版（已有 Python）

1. 安裝 [Python 3.12](https://www.python.org/downloads/)，勾選「**Add Python to PATH**」
2. 下載 ZIP 或 `git clone` 本 repo
3. 雙擊 `start.bat`，首次啟動輸入登入密碼

詳細說明請見 [Windows 安裝指南](docs/user-guide/install-windows.md)。

## 範例書單 / Sample Data

`sample-data/vendor-lists/` 目錄包含兩份範例書商書單，clone 後可直接用於測試：

| 檔案 | 說明 |
|------|------|
| `general-books-required-recommended-2026.xlsx` | 一般圖書採購推薦書目（約 6,750 筆） |
| `local-culture-vendor-list-2026.xlsx` | 本土文化圖書採購推薦書目（約 679 筆） |

這兩份 Excel 是**範例書商書單（推薦書目清單）**，不是學校館藏資料。clone 後可在「匯入書商書單」步驟直接選用，無需自備書單即可體驗完整採購流程。

> 實際採購請使用書商提供的最新書單。範例書單的書目資訊之權利歸各原權利人或資料來源所有，詳見 [`sample-data/vendor-lists/README.md`](sample-data/vendor-lists/README.md)。

## 本地資料安全

- 所有採購資料、館藏記錄、書商書單均儲存於本機 `data/school_lib.db`
- 匯出的 Excel 採購書單存放於 `exports/` 資料夾
- 本系統不傳送任何資料至外部伺服器

以下路徑已加入 `.gitignore`，不會被 git 追蹤或提交：

| 路徑 | 說明 |
|------|------|
| `data/` | 資料庫與館藏記錄 |
| `exports/` | 匯出的採購書單 |
| `00_source/` | 書商 Excel 原始書單 |
| `tmp/` | 暫存檔案 |
| `config.yaml` | 本機設定（含密碼） |

## 開發者安裝

適用於開發人員或希望手動安裝的使用者：

```bash
git clone <repo-url>
cd school-lib-local

# 建議使用 Python 3.11 或 3.12
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

copy config.example.yaml config.yaml
# 編輯 config.yaml，設定 default_admin_password 與 session_secret_key
```

執行測試：

```bash
.venv\Scripts\python.exe -m pytest -q
```

## 目前開發狀態

活躍開發中，功能持續更新。建議定期確認是否有新版本。

## 授權

本專案採用 [MIT License](LICENSE)。

## 開發流程文件

本 repo 包含 `AGENTS.md`、`CLAUDE.md`、`docs/tasks/`、`docs/logs/` 等目錄，為本專案的開發協作流程記錄（AI agent 工作日誌與任務規劃文件）。一般使用者不需閱讀這些文件即可正常使用系統。

## 文件

- [完整操作導覽（含截圖）](docs/user-guide/complete-walkthrough.md)
- [Windows 安裝指南](docs/user-guide/install-windows.md)
- [本土文化採購快速上手](docs/user-guide/local-culture-quickstart.md)
- [一般圖書採購快速上手](docs/user-guide/general-books-quickstart.md)
