# Spec: task-user-guide-with-screenshots

## 背景

本專案已完成開源準備（README、Windows 安裝指南、本土文化 quickstart、一般圖書 quickstart、sample-data/、CI、LICENSE 等），但缺乏一份「有截圖的完整使用者導覽」。目前的 quickstart 文件沒有畫面圖，第一次接觸的非工程使用者難以直接按圖操作。

## 目標

新增 `docs/user-guide/complete-walkthrough.md`，搭配 10 張實際操作截圖，讓使用者從安裝到匯出採購書單都能看圖照做。截圖使用合成測試資料，不含真實學校資料或個資。

## 使用者對象

- 國民小學圖書館管理員、行政人員、負責採購業務的教師
- 非工程背景，首次接觸本系統
- 已完成 Windows 安裝，需要完整操作示範

## 文件範圍

### 新增文件

- `docs/user-guide/complete-walkthrough.md`：完整操作導覽，含截圖、每步驟目的、操作說明、預期畫面、常見問題
- `docs/user-guide/images/`：存放 10 張截圖（PNG，寬度建議 1280px）

### 更新文件

- `README.md`：新增連結至 complete-walkthrough.md

### 測試資料

- `sample-data/holdings/sample-holdings.xlsx`：合成館藏 Excel（虛構書目資料，約 15 列）
- `sample-data/holdings/README.md`：說明合成館藏的用途與資料來源

### 文件章節

| 章節 | 說明 |
|------|------|
| 系統用途簡介 | 這個系統能做什麼 |
| 取得專案與安裝 | clone / 解壓、建立 config.yaml、啟動 |
| 登入系統 | 帳號密碼位置、首次登入 |
| 首頁與專案列表 | 版面說明 |
| 建立採購專案 | 類型選擇、命名 |
| 匯入館藏 | 上傳館藏 Excel、欄位對應 |
| 匯入書商書單 | 上傳範例書單 Excel、欄位對應 |
| 使用 sample-data 範例書單 | 告知可直接用 sample-data/ 測試 |
| 查看比對結果 | 已館藏 vs 未館藏篩選 |
| 選書 | 加入採購清單、填寫欄位 |
| 匯出前檢查 | 資料完整度確認、補填或移除 |
| 匯出 Excel | 選範本、填學校名稱、下載 |
| 查看匯出檔案 | exports/ 位置 |
| 資料位置與備份 | data/、exports/ 說明 |
| 常見問題 | 整合既有 quickstart 的常見問題 |

## 截圖範圍

共 10 張，詳細清單見 plan 的截圖清單。截圖使用合成測試資料，以乾淨測試 DB 操作，不含真實館藏或學校資訊。

## 測試資料策略

### 合成館藏（sample-data/holdings/sample-holdings.xlsx）

- 約 15 列，欄位：書名、作者、ISBN、出版社、索書號
- 5 個 ISBN 取自 `sample-data/vendor-lists/local-culture-vendor-list-2026.xlsx`（產生比對命中，示範「已館藏」狀態）
- 10 個 ISBN 為公開格式虛構值（978-0-000-xxxxx-x 格式），不命中任何書目（示範「未館藏」書目）
- 書名使用虛構或明顯示範性質的名稱（例如「示範書目一」），不得使用真實學校名稱、個人資訊
- 作者、出版社使用虛構值（例如「示範出版社」）
- 此檔案以 openpyxl 程式建立，確保可重複產生

### 書商書單

直接使用 `sample-data/vendor-lists/local-culture-vendor-list-2026.xlsx`（已在 repo 中）

### 測試資料庫

截圖前備份 `data/school_lib.db`（若存在），使用乾淨 DB 操作，截圖後還原。`data/` 已在 `.gitignore`，不影響 repo 內容。

## 隱私與公開風險

| 風險項目 | 說明 | 處理方式 |
|---------|------|---------|
| 截圖含真實學校名稱 | 匯出步驟需填學校名稱 | 使用「測試學校」等中性名稱 |
| 截圖含本機路徑 | 檔案上傳時瀏覽器可能顯示路徑 | 截圖前確認，必要時裁切或替換 |
| 截圖含 config.yaml 內容 | Web UI 不顯示 config，風險低 | 確認無設定頁面洩漏 |
| 合成館藏含真實個資 | 自行建立，全部虛構 | 使用明顯示範性質的書名與作者 |
| committed 文件含真實路徑 | walkthrough.md 中的範例路徑 | 只使用相對路徑或佔位路徑（`./data/`），不含 `C:\Users\真實名稱\...` |

## 非目標

- 不修改核心 app 功能或 UI
- 不重做或調整 sample vendor list 內容
- 不使用真實學校館藏資料或個資
- 不部署網站或建立 GitHub Pages
- 不製作影片教學
- 不修改 quickstart 文件（complete-walkthrough 為獨立文件，與 quickstart 並列）
- 不新增 pytest 測試用例

## 驗收條件

- `docs/user-guide/complete-walkthrough.md` 存在，含全部章節
- `docs/user-guide/images/` 存在，含 10 張截圖（01-login.png ～ 10-dashboard-after-export.png）
- `sample-data/holdings/sample-holdings.xlsx` 存在，為虛構合成資料
- `sample-data/holdings/README.md` 存在，說明用途
- `README.md` 新增連結指向 complete-walkthrough.md
- `git ls-files docs/user-guide/images/` 輸出 10 個檔案
- `git ls-files sample-data/holdings/` 輸出 2 個檔案
- `pytest -q` 全部通過
- 人工確認：截圖無真實學校名稱、無個資、無 config secret、無本機真實路徑
- 人工確認：walkthrough.md 所有圖片連結有效（`![...](...)`）
