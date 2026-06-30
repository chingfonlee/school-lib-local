# Windows 安裝與啟動說明

本文件說明如何在 Windows 電腦上安裝並啟動 115年高雄市國中國小圖書館採購輔助系統。

## 選擇安裝方式

本系統提供兩種安裝方式：

| | 攜帶版（推薦） | 自行安裝版 |
|---|---|---|
| **下載大小** | 約 150 MB（內含 Python） | 約 5 MB（需另行安裝 Python） |
| **需要安裝 Python** | 否 | 是 |
| **解壓縮後直接使用** | 是 | 是 |
| **適合對象** | 不想額外安裝軟體的老師 | 電腦已有 Python 或開發者 |

---

## 方式一：攜帶版（推薦）

不需要安裝 Python，下載後解壓縮即可使用。

### 步驟

1. 前往 [GitHub Releases 頁面](https://github.com/chingfonlee/school-lib-local/releases/latest) 下載 **`school-lib-portable.zip`**

2. 解壓縮至任意資料夾（例如 `C:\圖書採購系統\`）

3. 開啟資料夾，雙擊 **`start.bat`**

4. 首次啟動時，畫面會出現：

   ```
   ==================================================
     首次啟動設定
   ==================================================

     請設定管理員登入密碼（至少 6 個字元）：
   ```

5. 輸入登入密碼，按 **Enter** 確認

6. 瀏覽器自動開啟 `http://127.0.0.1:8765`，完成！

> 第二次之後啟動速度較快，僅需幾秒，不需要再設定密碼。

---

## 方式二：自行安裝版

需要先安裝 Python，適合已有 Python 或希望日後自行更新的使用者。

### 步驟一：安裝 Python

若尚未安裝 Python：

1. 前往 [python.org](https://www.python.org/downloads/) 下載 Python **3.12**
2. 執行安裝程式，**務必勾選「Add Python to PATH」**
3. 安裝完成

### 步驟二：取得系統

選擇任一方式：

- **下載 ZIP**：在 [GitHub 頁面](https://github.com/chingfonlee/school-lib-local) 點選「Code」→「Download ZIP」，解壓縮至任意資料夾
- **git clone**：`git clone https://github.com/chingfonlee/school-lib-local.git`

### 步驟三：啟動

1. 開啟資料夾，雙擊 **`start.bat`**
2. 首次執行時，系統自動安裝必要套件（需等待 3–10 分鐘，視網路速度而定）
3. 安裝完成後，出現密碼設定提示，輸入密碼按 Enter
4. 瀏覽器自動開啟，完成！

---

## 登入帳號

兩種安裝方式的登入方式相同：

- **帳號**：`admin`
- **密碼**：首次啟動時自行設定的密碼

> 請記住您設定的密碼，日後每次登入都需要使用。若忘記密碼，請刪除 `config.yaml` 後重新執行 `start.bat` 重設。

---

## 資料與匯出位置

| 路徑 | 說明 |
|------|------|
| `data/school_lib.db` | 系統資料庫（館藏、書商書單、採購記錄） |
| `exports/` | 匯出的 Excel 採購書單 |

建議定期備份 `data/` 與 `exports/` 資料夾。

---

## 常見問題

### Python 找不到（方式二）

`start.bat` 執行後出現「找不到 Python」錯誤：

- 確認已安裝 Python 3.10 至 3.13
- 開啟「命令提示字元」輸入 `python --version` 或 `py --version`，確認版本
- 若顯示 3.14，請改安裝 3.12 版本
- 重新安裝 Python 時，請確認勾選「Add Python to PATH」

### Port 8765 被占用

瀏覽器無法連線，或終端機顯示「port already in use」：

- 關閉其他可能占用 8765 的程式後重新啟動
- 或修改 `config.yaml` 的 `server.port` 為其他值（如 `8766`），並重新執行 `start.bat`

### 套件安裝時間較長（方式二）

首次啟動需下載並安裝 Python 套件，視網路速度可能需要 3 至 10 分鐘。
若長時間無回應，可嘗試關閉後重新執行 `start.bat`。

### 瀏覽器未自動開啟

若安裝完成後瀏覽器未自動開啟：

1. 手動開啟 Chrome 或 Edge
2. 在網址列輸入 `http://127.0.0.1:8765`
3. 確認 `start.bat` 的視窗仍在執行中（關閉視窗會停止伺服器）
