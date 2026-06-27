# Spec: task-add-sample-vendor-lists

## 背景

本專案完成開源準備（task-open-source-readiness）後，使用者 clone 後無法直接測試完整的書商書單匯入、比對、選書、匯出流程，因為書商書單位於 `00_source/`（已 git-ignored），不包含在 repo 中。

以下兩份範例書商書單為可公開的推薦書目清單，不含學校館藏資料或個人識別資訊，適合作為 sample data 隨 repo 發布：

- `一般圖書採購-必選推薦-2026.xlsx`：約 6751 列、20 欄，含獲獎項目、書名、作者、ISBN、出版日期、定價、出版社、搜尋連結等書目資訊
- `本土書單採購 -2026.xlsx`：約 697 列、17 欄，含 Excel 公式欄位（`=ROUND(G2*75%,0)` 計算單價、`=HYPERLINK(...)` 書店連結）

這兩份 Excel 的定位是「範例書商書單 / 推薦書目清單」，不是學校館藏資料。

## 目標

將上述兩份範例書商書單以適當的公開路徑納入 repo，讓使用者 clone 後可直接使用 sample data 測試匯入、比對、選書、匯出流程，無需自備書商書單。

## 需求範圍

### 1. sample-data 目錄結構

建立 `sample-data/vendor-lists/` 目錄，包含：
- `general-books-required-recommended-2026.xlsx`（來源：`一般圖書採購-必選推薦-2026.xlsx`）
- `local-culture-vendor-list-2026.xlsx`（來源：`本土書單採購 -2026.xlsx`）
- `README.md`：說明這兩份 Excel 是範例推薦書單（非館藏）、用途、授權與注意事項

### 2. 文件更新

- `README.md`：新增「範例書單 / Sample Data」段落，說明 `sample-data/vendor-lists/` 路徑、用途、與實際採購書單的區別
- `docs/user-guide/local-culture-quickstart.md`：在書商書單匯入步驟補充可使用 `sample-data/vendor-lists/local-culture-vendor-list-2026.xlsx`
- `docs/user-guide/general-books-quickstart.md`：在書商書單匯入步驟補充可使用 `sample-data/vendor-lists/general-books-required-recommended-2026.xlsx`

### 3. 資料安全與公開確認

使用 openpyxl 對來源 Excel 執行結構檢查與 cell value 掃描，確認不含敏感資訊後，才允許複製並加入 git 追蹤：
- 結構檢查：sheet names、hidden sheets、row/column count、external links / external workbook references
- 關鍵字掃描：email 格式、電話格式、地址關鍵字（路/街/巷/弄/號/縣/市）、學校名稱關鍵字（國小/國中/學校/圖書館）、預算/備註/內部備註關鍵字
- 若發現疑似敏感內容：停止，向使用者回報，不自行清理或提交

### 4. 授權說明

- 若使用者確認兩份 Excel 可公開：`sample-data/vendor-lists/README.md` 中標註「範例書單隨本專案以 MIT License 發布」
- 若書目資料版權屬書商：改為「僅供測試，書目資訊版權歸原著作權人」

## 不做的事

- 不修改應用程式核心功能（import service、selection logic 等）
- 不將任何檔案放入 `00_source/`（已 git-ignored，保持不追蹤）
- 不追蹤 `data/`、`exports/`、`tmp/`、`config.yaml`
- 不刪除或搬移現有 `docs/tasks/`、`docs/logs/`
- 不建立服務層整合測試或新增測試用例
- 不執行 `git filter-repo` 或重寫 history

## 資料公開風險與檢查項目

| 檢查項目 | 方法 | 允許 | 禁止/停止條件 |
|---------|------|------|--------------|
| Hidden sheets | openpyxl `wb[sn].sheet_state` | hidden sheet 但無敏感資料 | hidden sheet 含敏感資訊 |
| External links | `wb._external_links` 或 `wb.defined_names` | 無 external workbook reference | 任何 external workbook reference |
| Email | regex `[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}` | 無 | 任何 email 地址 |
| 電話 | 台灣電話格式 regex | 無 | 電話號碼 |
| 地址 | 含「路」「街」「巷」「弄」「號」「縣」「市」的 cell value | 書名或 URL 含上述字（需人工確認） | 實際地址（非書名、非 URL） |
| 學校名稱 | 含「國小」「國中」「學校」「圖書館」的 cell value | 無 | 學校識別資訊 |
| 預算/內部 | 含「預算」「備註」「核准」「採購金額」「內部」的 cell value | 無 | 採購預算或內部備註 |

掃描以 `data_only=True` 讀取（取公式計算結果）。公式字串本身（`=ROUND(...)`、`=HYPERLINK(...)`）不視為敏感資料。`address` pattern 因書名常含相關字元，命中結果須人工確認是否為書名欄位或連結 URL。

## 驗收條件

- `git ls-files sample-data/vendor-lists/` 輸出 3 個檔案（2 個 xlsx + 1 個 README.md）
- openpyxl 掃描：兩份 workbook 無 external workbook references、無 hidden sheets 含敏感資料、cell value 掃描無未確認的敏感關鍵字命中
- `README.md` 新增 Sample Data / 範例書單段落
- `docs/user-guide/local-culture-quickstart.md` 在書商書單匯入步驟補充 sample file 路徑
- `docs/user-guide/general-books-quickstart.md` 在書商書單匯入步驟補充 sample file 路徑
- `sample-data/vendor-lists/README.md` 存在，說明用途、定位與授權
- `git ls-files 00_source/` 無輸出（來源目錄仍不追蹤）
- `.venv\Scripts\python.exe -m pytest -q` 全部通過
