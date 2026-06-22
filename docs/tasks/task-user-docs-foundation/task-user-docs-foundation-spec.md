# Spec: task-user-docs-foundation

## 目標

建立本專案開源與使用者操作所需的基礎文件，讓其他小學或教師可在 Windows 本機安裝、啟動，並完成基本採購流程。具體目標：

- 讓使用者理解這是本地端圖書採購輔助系統，資料保存在本機
- 讓 Windows 使用者可依文件完成安裝、啟動、登入與基本操作
- 讓本土文化採購流程有一份快速上手指南

## 需求範圍

### 1. README.md（專案根目錄）

- 專案用途簡介
- 支援範圍：本土文化採購（主要）、一般圖書採購（目前支援）
- 本地資料安全說明（資料保存在本機，無雲端上傳）
- 系統需求（Python 版本、Windows 版本、瀏覽器）
- 快速啟動摘要（執行 start.bat、開啟瀏覽器）
- 目前開發狀態（活躍開發中，功能持續更新）
- 文件導覽連結（指向 install-windows.md、local-culture-quickstart.md）

### 2. docs/user-guide/install-windows.md

- Windows 安裝需求（Python 版本、必要設定）
- 取得專案方式（一般描述，不要求特定發布包或 installer）
- 執行 start.bat 的步驟說明
- 首次啟動行為說明（自動建立 .venv、安裝 requirements，需等待）
- 開啟瀏覽器：http://127.0.0.1:8765
- 預設帳號密碼說明與修改提醒
- 常見問題：Python 找不到、port 8765 被占用、依賴安裝慢、瀏覽器未自動開啟
- 資料與匯出位置：data/school_lib.db、exports/

### 3. docs/user-guide/local-culture-quickstart.md

涵蓋本土文化採購主要流程，步驟對應實際頁面操作：

1. 建立或選擇採購專案
2. 匯入館藏
3. 匯入書商書單
4. 執行比對 / 查看比對結果
5. 選書（含加入選書、修正缺漏欄位）
6. 匯出前檢查（修正或移除缺必填書目）
7. 匯出 Excel
8. 檢查匯出檔
9. 常見問題

## 不做的事

- 不建立自動化測試
- 不修改任何程式碼（app/、migrations/ 等）
- 不新增截圖或圖片
- 不撰寫完整一般圖書採購專門指南（可在 README 提到支援，詳細教學留待後續 task）
- 不承諾正式 release / installer
- 不撰寫雲端部署或多人帳號權限文件
- 不引入文件產生器或靜態網站工具（如 MkDocs、Docusaurus）

## 驗收條件

1. `README.md`、`docs/user-guide/install-windows.md`、`docs/user-guide/local-culture-quickstart.md` 三份文件均存在
2. 三份文件均為繁體中文，使用 Markdown 格式
3. 三份文件符合專案文件格式：UTF-8 without BOM、LF 換行、final newline
4. `README.md` 包含專案用途、系統需求、快速啟動摘要、文件導覽連結，可讓新使用者理解入口
5. `install-windows.md` 包含 start.bat 啟動步驟、首次啟動說明、常見問題，可讓 Windows 使用者依步驟操作
6. `local-culture-quickstart.md` 覆蓋本土文化採購從匯入到匯出的完整主要流程
7. 文件不包含不存在的功能承諾（如截圖、installer、雲端功能）
8. 文件不包含密碼、token、內部 IP 等敏感資料（預設帳密可以描述性說明，不硬寫密碼字串）
9. 不修改 app/、migrations/ 或其他程式碼，git status 僅包含本 task 預期文件與 STATUS/log 變更
