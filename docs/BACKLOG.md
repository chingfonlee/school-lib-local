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

- status: done
- priority: medium
- type: UX
- task-id: task-selection-advanced-filters
- description:
  增加比對狀態、資料完整度、書本類型、適讀年齡、分類/議題、價格區間、關鍵字與排序。
- decision:
  已轉成正式 task 並完成。

### 內網部署與使用補強

- status: idea
- priority: low
- type: deployment/ops
- source: 使用者詢問系統若要在內網使用需要具備什麼
- description:
  規劃讓本系統可在學校或單位內網穩定使用。目標是讓一台固定內網 IP 的電腦或小型主機提供服務，其他老師與館員可用瀏覽器連線操作。
- possible scope:
  - 支援用 config.yaml 設定 host / port，內網啟動時可綁定 0.0.0.0。
  - 補 Windows 防火牆與固定 IP 設定說明。
  - 補 Windows 工作排程器或 NSSM service 啟動腳本。
  - 補一鍵備份 data/、exports/、config.yaml 的方式。
  - 補預設帳密與 session_secret_key 初始化/變更說明。
  - 評估 SQLite 在多人內網使用下的限制與注意事項。
- notes:
  最小可行內網版是固定 IP 主機、開放 port、用 uvicorn 綁定 0.0.0.0。正式化前不急著做 HTTPS 或 reverse proxy；若未來跨校外或 VPN 使用，再評估 HTTPS。
- decision:
  可做可不做，暫不排入 Active Tasks。

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
