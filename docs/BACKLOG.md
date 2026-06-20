# Backlog

本文件記錄可能想做、但尚未排入 Active Tasks 的候選任務。

這些項目不是承諾，不代表一定要實作。Agent 只能在使用者明確指定時，才將其中項目轉成 task-planning。

## 使用規則

- `docs/BACKLOG.md` 是候選任務清單，不等於 Active Tasks。
- Agent 可以讀取並整理 backlog，但不得自行將 backlog 項目轉為正式 task。
- 只有使用者明確要求「建立 task」或「進入 task-planning」時，才能從 backlog 轉成正式 task。
- Backlog 項目若已轉成 task，請在該項目補上對應 task-id。
- Backlog 項目若已完成，請更新 status 與 decision，不要直接刪除，保留追溯脈絡。

## 候選任務

### 階段提示按鈕光暈效果

- status: idea
- priority: low
- type: UI/UX
- source: 使用者希望在不同流程階段提示目前可以前往的頁面或可以使用的按鈕
- description:
  在不同工作流程階段，用按鈕邊框光暈提示下一步可以做什麼。
  例如匯入完成後提示「前往比對結果」，比對完成後提示「前往選書」，匯出檢查通過後提示「產生 Excel」。
- notes:
  可參考 Jakubantalik/border-beam 的視覺概念，但目前專案是 FastAPI + 靜態 HTML/JS，不建議導入 React 套件。
  若未來實作，優先用純 CSS 製作按鈕外框光暈或呼吸式提示效果。
- decision:
  可做可不做，暫不排入 Active Tasks。

### 選書頁進階篩選

- status: active
- priority: medium
- type: UX
- task-id: task-selection-advanced-filters
- description:
  增加比對狀態、資料完整度、書本類型、適讀年齡、分類/議題、價格區間、關鍵字與排序。
- decision:
  已轉成正式 task，目前在 Active Tasks 中執行。

## 查詢提示詞範例

```text
請讀取 docs/BACKLOG.md，整理目前我曾經提過但尚未排入 Active Tasks 的候選任務。

請分類回報：
1. 可以近期做
2. 可做可不做
3. 需要更多需求釐清
4. 已經轉成 task 或已完成

請不要開始實作，也不要更新 STATUS.md。
```

## 新增候選任務提示詞範例

```text
請更新 docs/BACKLOG.md，新增一個候選任務。

請只更新 docs/BACKLOG.md，不要進入 task-planning，不要修改 STATUS.md。
```
