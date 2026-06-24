# 國小圖書館圖書採購輔助系統

本地端圖書採購輔助工具，協助國小教師與行政人員完成書商書單比對、選書與採購書單匯出。

## 用途

本系統幫助學校完成以下工作：

- 匯入書商書單，與現有館藏比對，快速確認哪些書目尚未館藏
- 線上選書、填寫必要欄位（資格標記、推薦來源、獲獎記錄等）
- 匯出前逐筆確認，確保書單欄位完整
- 匯出符合規格的採購書單（Excel）

所有資料儲存於本機，不會上傳至任何雲端服務。

## 支援範圍

- **本土文化採購**：主要功能，包含館藏比對、選書、A 欄資格標記、H 欄推薦來源、匯出採購書單
- **一般圖書採購**：目前支援，詳細操作流程請見 [一般圖書採購快速上手](docs/user-guide/general-books-quickstart.md)

## 本地資料安全

- 所有採購資料、館藏記錄、書商書單均儲存於本機 `data/school_lib.db`
- 匯出的 Excel 採購書單存放於 `exports/` 資料夾
- 本系統不傳送任何資料至外部伺服器

## 系統需求

| 項目 | 需求 |
|------|------|
| 作業系統 | Windows 10 / Windows 11 |
| Python | 3.10 至 3.13（不支援 3.14） |
| 瀏覽器 | Chrome 或 Edge（建議） |

## 快速啟動

1. 雙擊 `start.bat`
2. 首次執行時，系統會自動安裝必要套件（需等待數分鐘）
3. 安裝完成後，瀏覽器自動開啟 `http://127.0.0.1:8765`
4. 依 `config.yaml` 的 `auth` 區塊確認帳號後登入

詳細安裝說明請見 [Windows 安裝指南](docs/user-guide/install-windows.md)。

## 目前開發狀態

活躍開發中，功能持續更新。建議定期確認是否有新版本。

## 文件

- [Windows 安裝指南](docs/user-guide/install-windows.md)
- [本土文化採購快速上手](docs/user-guide/local-culture-quickstart.md)
- [一般圖書採購快速上手](docs/user-guide/general-books-quickstart.md)
