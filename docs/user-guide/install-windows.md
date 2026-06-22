# Windows 安裝與啟動說明

本文件說明如何在 Windows 電腦上安裝並啟動圖書採購輔助系統。

## 系統需求

| 項目 | 需求 |
|------|------|
| 作業系統 | Windows 10 / Windows 11 |
| Python | 3.10 至 3.13（**不支援 3.14**） |
| 瀏覽器 | Chrome 或 Edge（建議） |

> **Python 安裝說明**
> 若尚未安裝 Python，請至 [python.org](https://www.python.org/downloads/) 下載 3.12 版本。
> 安裝時請勾選「Add Python to PATH」選項。

## 取得專案

選擇以下任一方式取得專案資料夾：

- **下載 ZIP**：在 GitHub 頁面點選「Code」→「Download ZIP」，解壓縮至任意資料夾
- **git clone**：若已安裝 Git，在終端機執行 `git clone <專案網址>`

## 首次啟動

1. 開啟專案資料夾
2. 雙擊 `start.bat`
3. 首次執行時，系統會顯示以下訊息並自動處理：

   ```
   首次啟動：正在建立虛擬環境...
   安裝或更新依賴套件...
   ```

   此步驟需等待數分鐘，視網路速度而定。

4. 安裝完成後，系統自動開啟瀏覽器並導向 `http://127.0.0.1:8765`
5. 依下方「登入帳號」說明完成首次登入

> 第二次之後啟動速度較快，僅需幾秒。

## 登入帳號

預設登入資訊請查看 `config.yaml` 的 `auth` 區塊（`default_admin_username`、`default_admin_password`）。

**首次使用後請立即修改：**

- 開啟專案資料夾內的 `config.yaml`，修改 `default_admin_password` 為自訂密碼
- 同時將 `session_secret_key` 改為隨機字串（例如鍵盤隨機輸入的長字串）

> 若未修改預設密碼與 `session_secret_key`，系統安全性較低，不建議在多人共用網路環境下使用。

## 資料與匯出位置

| 路徑 | 說明 |
|------|------|
| `data/school_lib.db` | 系統資料庫（館藏、書商書單、採購記錄） |
| `exports/` | 匯出的 Excel 採購書單 |

建議定期備份 `data/` 與 `exports/` 資料夾。

## 常見問題

### Python 找不到

`start.bat` 執行後出現「找不到 Python」錯誤：

- 確認已安裝 Python 3.10 至 3.13
- 開啟「命令提示字元」輸入 `python --version` 或 `py --version`，確認版本
- 若顯示 3.14，請改安裝 3.12 版本
- 重新安裝 Python 時，請確認勾選「Add Python to PATH」

### Port 8765 被占用

瀏覽器無法連線，或終端機顯示「port already in use」：

- 關閉其他可能占用 8765 的程式後重新啟動
- 或修改 `config.yaml` 的 `server.port` 為其他值（如 `8766`），並重新執行 `start.bat`

### 依賴安裝時間較長

首次啟動需下載並安裝 Python 套件，視網路速度可能需要 3 至 10 分鐘。
若長時間無回應，可嘗試關閉後重新執行 `start.bat`。

### 瀏覽器未自動開啟

若安裝完成後瀏覽器未自動開啟：

1. 手動開啟 Chrome 或 Edge
2. 在網址列輸入 `http://127.0.0.1:8765`
3. 確認 `start.bat` 的視窗仍在執行中（關閉視窗會停止伺服器）
