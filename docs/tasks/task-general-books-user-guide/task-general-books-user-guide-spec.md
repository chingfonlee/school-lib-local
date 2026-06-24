# Spec：task-general-books-user-guide

- task-id: task-general-books-user-guide
- type: chore
- base branch: main
- status: planning

---

## 目標

補齊使用者文件的缺口：新增一般圖書採購操作指南，並修正本土文化採購快速上手中與現行 UI 不符的按鈕名稱。

---

## 需求範圍

### 需求一：新增一般圖書採購快速上手

建立 `docs/user-guide/general-books-quickstart.md`，說明使用一般圖書採購流程的操作步驟，對象為不熟悉系統的教師或行政人員。

內容涵蓋：
- 事前準備（館藏 Excel、書商書單 Excel）
- 建立或選擇採購專案（類型選「一般圖書採購」）
- 匯入館藏
- 匯入書商書單
- 查看比對結果
- 選書（填寫數量、定價等欄位；注意一般圖書採購無 A 欄資格標記、H 欄推薦來源等本土文化專屬欄位）
- 匯出前檢查
- 匯出 Excel
- 常見問題

與本土文化採購的主要差異：
- 專案類型選「一般圖書採購」
- 無 A 欄資格標記、H 欄推薦來源欄位
- 匯出範本不同（系統依專案類型自動選擇）

### 需求二：修正 `local-culture-quickstart.md` 按鈕名稱

步驟一中「點選『進入』即可」與現行 UI 不符（按鈕現為「選擇」），改為「點選『選擇』即可」。

---

## 不做的事

- 不修改任何程式碼或 HTML
- 不新增截圖（文字描述即可）
- 不重寫 `install-windows.md` 或 `README.md`
- 不說明系統內部實作細節

---

## 驗收條件

1. `docs/user-guide/general-books-quickstart.md` 存在，涵蓋完整操作流程（準備 → 建立專案 → 匯入 → 比對 → 選書 → 匯出前檢查 → 匯出 → 確認）。
2. 明確說明一般圖書採購與本土文化採購的差異。
3. `local-culture-quickstart.md` 步驟一的「進入」已改為「選擇」。
4. 兩份文件均為繁體中文、Markdown 格式正確。
