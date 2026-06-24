# Plan：task-general-books-user-guide

- task-id: task-general-books-user-guide
- base branch: main
- 實作分支: chore/task-general-books-user-guide

---

## 實作步驟

### Step 1：修正 `local-culture-quickstart.md`

**檔案**：`docs/user-guide/local-culture-quickstart.md`

找到步驟一中「點選『進入』即可」，改為「點選『選擇』即可」。

### Step 2：新增 `general-books-quickstart.md`

**檔案**：`docs/user-guide/general-books-quickstart.md`（新建）

依以下結構撰寫：

1. 事前準備
2. 步驟一：建立或選擇採購專案（強調選「一般圖書採購」）
3. 步驟二：匯入館藏
4. 步驟三：匯入書商書單
5. 步驟四：查看比對結果
6. 步驟五：選書（說明一般圖書無 A/H 欄）
7. 步驟六：匯出前檢查
8. 步驟七：匯出 Excel
9. 步驟八：確認匯出檔
10. 常見問題（可沿用 local-culture 版本，去除本土文化專屬問題）

與本土文化版的差異說明置於文件開頭「適用範圍」區塊。

### Step 3：驗證

人工確認：
- 兩份文件 Markdown 格式正確（標題層級、清單縮排）
- `general-books-quickstart.md` 流程完整，無遺漏步驟
- `local-culture-quickstart.md` 步驟一按鈕名稱已更正
- 繁體中文，無簡體字或錯別字

---

## 風險與注意事項

- `general-books-quickstart.md` 描述的 UI 操作應與目前實際頁面一致（參考 `local-culture-quickstart.md` 的語氣與格式）
- 一般圖書採購無 A 欄（資格標記）與 H 欄（推薦來源）欄位，不得在文件中提及

---

## 預計影響範圍

- `docs/user-guide/local-culture-quickstart.md`（一字修改）
- `docs/user-guide/general-books-quickstart.md`（新建）
- 不影響任何程式碼

---

## 驗證指令

- lint：不適用
- format：不適用
- typecheck：不適用
- test：不適用
- build：不適用

人工 Markdown 格式確認即可。

---

## 成果報告

- result_report_mode: none
