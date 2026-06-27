# Plan: task-add-sample-vendor-lists

## 實作步驟

### Phase 1：資料安全掃描（必須先完成，掃描結果需使用者確認後才能繼續）

1. 對兩份來源 Excel 執行 openpyxl 結構檢查（在專案根目錄執行）：

   ```powershell
   .venv\Scripts\python.exe -c @"
   import openpyxl

   files = [
       (r'00_source/一般圖書採購-必選推薦-2026.xlsx', 'general-books'),
       (r'00_source/本土書單採購 -2026.xlsx', 'local-culture'),
   ]
   for path, label in files:
       wb = openpyxl.load_workbook(path, data_only=True)
       for sn in wb.sheetnames:
           ws = wb[sn]
           state = ws.sheet_state if hasattr(ws, 'sheet_state') else 'visible'
           print(f'{label} | sheet={sn!r} | state={state} | rows={ws.max_row} | cols={ws.max_column}')
       ext = getattr(wb, '_external_links', [])
       print(f'{label} | external_links={len(ext)}')
   "@
   ```

2. 對兩份 Excel 執行 cell value 關鍵字掃描：

   ```powershell
   .venv\Scripts\python.exe -c @"
   import re, openpyxl

   PATTERNS = {
       'email':    re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'),
       'phone':    re.compile(r'0\d{1,3}[\-\s]?\d{3,4}[\-\s]?\d{4}'),
       'address':  re.compile(r'[路街巷弄號縣市]'),
       'school':   re.compile(r'國小|國中|學校|圖書館'),
       'internal': re.compile(r'預算|備註|核准|採購金額|內部'),
   }
   files = [
       (r'00_source/一般圖書採購-必選推薦-2026.xlsx', 'general-books'),
       (r'00_source/本土書單採購 -2026.xlsx', 'local-culture'),
   ]
   for path, label in files:
       wb = openpyxl.load_workbook(path, data_only=True)
       for sn in wb.sheetnames:
           ws = wb[sn]
           for row in ws.iter_rows():
               for cell in row:
                   v = str(cell.value) if cell.value is not None else ''
                   for key, pat in PATTERNS.items():
                       if pat.search(v):
                           print(f'[{label}][{sn}]{cell.coordinate} [{key}] {v[:120]}')
   "@
   ```

   注意：
   - `address` pattern 因書名常含「路」「街」「弄」等字，命中量預計較多，須人工逐筆確認是否為書名欄位或超連結 URL
   - `=HYPERLINK(...)` 公式在 `data_only=True` 下讀取的是計算結果（通常為書名文字），若公式計算結果為 `None`，不視為問題
   - 若 `data_only=True` 讀取到大量 `None`，改以 `data_only=False` 補充確認公式內容

3. 向使用者回報掃描結果：
   - 結構摘要（sheet names、hidden state、row/col count、external links 數量）
   - 關鍵字命中清單（全部列出，不過濾）

4. **向使用者回報掃描結果，等待使用者明確確認「可公開」後，才繼續 Phase 2。**
   即使掃描結果看起來全部正常，也必須先回報再等確認，不得自行判斷「看起來沒問題」後直接進入 Phase 2。
   若有未解決的命中項目，停止並說明，不得繼續。

### Phase 2：建立 sample-data 目錄與 Excel 檔案

5. 建立目錄：
   ```powershell
   New-Item -ItemType Directory -Force sample-data/vendor-lists | Out-Null
   ```

6. 複製兩份 Excel，重新命名為英文公開檔名（來源檔名含中文與空白，必須使用 `-LiteralPath`）：
   ```powershell
   Copy-Item -LiteralPath "00_source\一般圖書採購-必選推薦-2026.xlsx" `
             -Destination "sample-data\vendor-lists\general-books-required-recommended-2026.xlsx"
   Copy-Item -LiteralPath "00_source\本土書單採購 -2026.xlsx" `
             -Destination "sample-data\vendor-lists\local-culture-vendor-list-2026.xlsx"
   ```

7. 確認檔案存在：
   ```powershell
   Test-Path sample-data/vendor-lists/general-books-required-recommended-2026.xlsx
   Test-Path sample-data/vendor-lists/local-culture-vendor-list-2026.xlsx
   ```

8. 建立 `sample-data/vendor-lists/README.md`（依 Phase 1 掃描確認結果選擇授權措辭）：

   **若確認可以 MIT License 發布：**
   ```markdown
   # 範例書商書單 / Sample Vendor Lists

   本目錄包含兩份範例書商書單（推薦書目清單），供使用者 clone 本專案後直接測試匯入、比對、選書、匯出流程。

   ## 檔案說明

   | 檔案 | 說明 | 列數 |
   |------|------|------|
   | `general-books-required-recommended-2026.xlsx` | 一般圖書採購推薦書目（必選/推薦類） | 約 6751 列 |
   | `local-culture-vendor-list-2026.xlsx` | 本土文化圖書採購推薦書目 | 約 697 列 |

   ## 注意事項

   - 這兩份 Excel 是**範例推薦書目清單**，不是學校館藏資料，不含採購記錄或學校識別資訊
   - 範例書單僅供測試匯入流程使用；實際採購請使用書商提供的最新書單
   - 本目錄內容隨本專案以 MIT License 發布
   ```

   **若版權屬書商，需更保守措辭：**
   ```markdown
   # 範例書商書單 / Sample Vendor Lists

   本目錄包含兩份範例書商書單（推薦書目清單），供使用者 clone 本專案後直接測試匯入、比對、選書、匯出流程。

   ## 注意事項

   - 這兩份 Excel 是**範例推薦書目清單**，不是學校館藏資料
   - 範例書單僅供測試匯入流程使用；實際採購請使用書商提供的最新書單
   - 書目資訊版權歸原著作權人所有
   ```

9. Commit：
   ```powershell
   git add sample-data/vendor-lists/
   git commit -m "chore(task-add-sample-vendor-lists): add sample vendor list excel files"
   ```

### Phase 3：文件更新

10. 更新 `README.md`：在適當位置新增「範例書單 / Sample Data」段落，內容包含：
    - `sample-data/vendor-lists/` 路徑說明
    - 兩個檔案的簡短說明
    - 說明這是推薦書目清單（非學校館藏）
    - 說明 clone 後可直接測試，實際採購請使用最新書商書單

11. 更新 `docs/user-guide/local-culture-quickstart.md`：
    - 找到書商書單匯入步驟（上傳 / 選擇書商書單 Excel 的段落）
    - 補充說明：可使用 `sample-data/vendor-lists/local-culture-vendor-list-2026.xlsx` 作為測試用書單
    - 加入提示：此為範例，實際操作請使用書商最新書單

12. 更新 `docs/user-guide/general-books-quickstart.md`：
    - 找到書商書單匯入步驟
    - 補充說明：可使用 `sample-data/vendor-lists/general-books-required-recommended-2026.xlsx` 作為測試用書單
    - 加入提示：此為範例，實際操作請使用書商最新書單

13. Commit：
    ```powershell
    git add README.md docs/user-guide/local-culture-quickstart.md docs/user-guide/general-books-quickstart.md
    git commit -m "docs(task-add-sample-vendor-lists): add sample data section and quickstart references"
    ```

### Phase 4：最終驗證

14. 確認追蹤清單：
    ```powershell
    git ls-files sample-data/vendor-lists/
    ```
    預期輸出（3 個檔案）：
    ```
    sample-data/vendor-lists/README.md
    sample-data/vendor-lists/general-books-required-recommended-2026.xlsx
    sample-data/vendor-lists/local-culture-vendor-list-2026.xlsx
    ```

15. 確認 `00_source/` 仍未追蹤：
    ```powershell
    git ls-files 00_source/
    ```
    應無輸出。

16. 執行測試：
    ```powershell
    .venv\Scripts\python.exe -m pytest -q
    ```

17. 確認 working tree 乾淨：
    ```powershell
    git status --short
    ```

18. 回報完成情況，等待使用者確認後進入 task-close 流程

## 風險與注意事項

1. **Phase 1 掃描為強制前置條件**：掃描未完成或使用者未明確確認「可公開」，Phase 2 以後的步驟必須停止。不自行判斷「看起來沒問題」。

2. **`address` pattern 誤判風險高**：書名（例如「公路的盡頭」「問路集」）以及超連結 URL 會觸發 address pattern。Phase 1 步驟 2 命中結果量可能偏多，需要人工確認哪些屬於書名或連結、哪些是真實地址。執行時可先聚焦確認非書名欄位（排除 title/書名欄後再看其餘欄位）。

3. **Excel 公式欄位**：`=ROUND(G2*75%,0)` 與 `=HYPERLINK(...)` 為計算單價與書店連結，屬公開書目資訊，不視為敏感資料。`data_only=True` 讀取公式計算結果；若結果為 `None`（Excel 尚未計算），改以 `data_only=False` 補確認公式本身。

4. **Excel 檔案大小**：`general-books-required-recommended-2026.xlsx` 約 2 MB，加入 git 後 repo 稍微增大；此為可接受範圍。

5. **openpyxl external_links 屬性**：不同版本 openpyxl 的 `_external_links` 屬性名稱可能不同。若屬性不存在，改以 `workbook.defined_names` 確認是否有跨 workbook reference，並記錄實際使用的確認方式。

6. **回滾策略**：
   - Phase 2 commit 後發現問題：`git revert {commit-hash}`；`00_source/` 本機檔案不受影響
   - Phase 3 commit 後發現文件問題：同樣 `git revert`
   - 任何 commit 不得使用 `git reset --hard`

## 預計影響範圍

新增檔案：
- `sample-data/vendor-lists/general-books-required-recommended-2026.xlsx`（約 2 MB）
- `sample-data/vendor-lists/local-culture-vendor-list-2026.xlsx`（約 139 KB）
- `sample-data/vendor-lists/README.md`

修改檔案：
- `README.md`（新增 Sample Data / 範例書單段落）
- `docs/user-guide/local-culture-quickstart.md`（補充 sample file 路徑說明）
- `docs/user-guide/general-books-quickstart.md`（補充 sample file 路徑說明）

明確不修改：
- 所有 `app/` 原始碼
- `00_source/`（保持未追蹤）
- `docs/tasks/`、`docs/logs/`（歷史記錄，保留）
- `config.yaml`、`config.example.yaml`、`.gitignore`

## 驗證指令

- test: `.venv\Scripts\python.exe -m pytest -q`
- lint: 無（本專案未設定）
- format: 無（本專案未設定）
- typecheck: 無（本專案未設定）
- build: 不適用
- 追蹤清單驗證: `git ls-files sample-data/vendor-lists/`
- 未追蹤確認: `git ls-files 00_source/`（應無輸出）
- git 狀態: `git status --short`

## 成果報告

- result_report_mode: none
- 適用情境：此為靜態資產與文件補充，無需額外成果報告
