# Spec: task-selection-performance-pagination

## 目標

改善一般圖書採購「選書」頁（`selection.html`）在大量書目下的前端 render 效能。  
目前一般圖書採購測試專案約有 6750 筆 vendor_books，頁面一次 render 全部書卡導致畫面明顯卡頓；本土文化採購約 670 筆，體感尚可。  
透過前端分頁，限制每次 render 的書卡數量，讓 6750 筆資料下的選書頁仍可流暢使用。

## 問題現象

- 以一般圖書採購專案開啟 selection.html，等待 API 回應後，頁面 render 時間明顯較長，畫面短暫凍結。
- 後端 `/api/books/matches` 查詢約 166ms，後端不是主要瓶頸。
- 前端 `render()` 函式一次對 `allBooks`（最多 6750 筆）執行 `Array.map` 產生 HTML 字串並一次寫入 `innerHTML`，造成大量 DOM 節點同時建立，觸發瀏覽器 layout 與 paint 成本過高。
- 一般圖書書卡包含 summary、policy_topic、A/H/L 欄位下拉等較多 DOM 元素，單卡成本高於本土文化書卡。

## 效能瓶頸假設

主因：`render()` 一次建立數千張書卡 DOM。  
次因：一般圖書書卡 HTML 樣板較複雜（多 select、多欄位），每張卡節點數多。  
後端 SQL 查詢（166ms）不是主要瓶頸，本 task 不改 API。

## 使用者期望行為

1. 開啟選書頁後，首屏應快速出現（不因書目筆數多而凍結）。
2. 篩選、排序、關鍵字搜尋仍對全部書目有效，不因分頁而遺漏。
3. 可透過分頁控制瀏覽所有書目。
4. 篩選條件改變時，自動回到第 1 頁。
5. 顯示目前頁面範圍與符合篩選的總筆數，例如「1–100 / 共 6750 筆」。
6. 加入選書、修正資料、預算統計、已清除來源快照等既有功能行為不改變。

## 需求範圍

### 分頁機制

- 新增分頁狀態變數：`currentPage`（從 1 開始）、`PAGE_SIZE`（固定值，建議 100）。
- `applyFilter()` 執行篩選排序後，將完整 filtered 結果儲存為 `filteredBooks`，並重設 `currentPage = 1`。
- `render()` 只 render `filteredBooks.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)` 的書卡。
- 篩選條件任一改變時，`applyFilter()` 重設 `currentPage = 1`。

### 分頁控制 UI

- 在書卡網格上方或下方加入分頁列：
  - 上一頁按鈕（第 1 頁時 disabled）
  - 頁碼資訊，例如「第 N 頁 / 共 M 頁」
  - 下一頁按鈕（最後一頁時 disabled）
- 分頁列在總筆數 ≤ PAGE_SIZE 時可隱藏（避免空間浪費）。

### result-count 更新

- 顯示「第 1–100 筆 / 共 6750 筆」格式，而非僅顯示「共 N 筆」。
- 篩選後總筆數為 0 時，顯示「無符合條件的書目」（現有行為保持）。

## 不做的事

- 不修改後端 API，不改 `/api/books/matches` 的 server-side pagination。
- 不引入 React、Vue 或任何前端框架。
- 不引入 virtual scroll 或 IntersectionObserver 等複雜機制（列為 V2 選項）。
- 不重構 selection.html 的整體架構或 JS 模組化。
- 不改變加入選書、清空選書、修正資料儲存、已清除來源快照等既有功能。
- 不加 DB index（目前後端查詢 166ms，不是主要瓶頸；若未來有必要，另開 task）。
- 不改 CSS 樣式（書卡視覺外觀維持不變）。
- 不加「無限滾動」（可延後 V2）。
- 不修改本土文化採購的書卡樣板或任何 local_culture 相關邏輯。

## 驗收條件

1. 以一般圖書採購專案（6750 筆）開啟 selection.html，首次 render 不超過 PAGE_SIZE 張書卡（首屏無凍結感）。
2. 篩選、排序、重設篩選均對全部 allBooks 有效，結果正確。
3. 篩選條件改變時，頁面自動回到第 1 頁。
4. result-count 顯示目前頁碼範圍與總筆數（例如「第 1–100 筆 / 共 6750 筆」）。
5. 分頁控制可正確切換頁面，上一頁 / 下一頁按鈕在邊界時 disabled。
6. 加入選書後，預算統計（已選書目、定價小計、採購單價小計）更新正常。
7. 修正資料 override 儲存後，書卡顯示更新正常。
8. 清空選書功能正常。
9. 以本土文化採購專案開啟 selection.html，功能回歸正常；若總筆數 > PAGE_SIZE，分頁列正常顯示並可翻頁；若總筆數 ≤ PAGE_SIZE，分頁列隱藏。
10. `python -m compileall app` 通過。
