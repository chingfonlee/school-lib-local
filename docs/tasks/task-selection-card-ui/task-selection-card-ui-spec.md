# Spec: task-selection-card-ui

## 目標

將 `app/static/selection.html` 的書目呈現方式從表格（table）改為卡片 grid，並將選書行為改為點擊按鈕直接新增一本（quantity: 1），不要求使用者手動輸入數量。

## 需求範圍

- `app/static/selection.html`：將書目渲染邏輯從 table row 改為 card 元素；移除數量 input；加入「＋ 加入選書」按鈕（送出 quantity: 1）；已選書顯示「已加入」disabled 按鈕；保留查館藏連結；保留 override 編輯區（inline edit，改為卡片內展開）
- `app/static/css/style.css`：補充 `.books-grid`、`.book-card`、`.book-card-body`、`.book-card-footer`、`.book-cta` 等樣式，參考 `school-lib/web/style.css` 的卡片設計語言
- budget bar 與統計（已選書目、定價小計、採購單價小計）維持原有更新邏輯
- 篩選功能（完整度篩選、文字搜尋）維持原有邏輯，僅渲染輸出改為卡片

## 不做的事

- 不修改後端 API（`/api/selections/`、`/api/books/`、`/api/projects/` 等）
- 不修改 migrations 或資料庫 schema
- 不修改 `app/routes/` 或任何 Python 檔案
- 不引入外部前端框架或 CDN
- 不加入分頁功能（維持現有一次全載）
- 不修改其他 HTML 頁面（import.html、match.html 等）

## 驗收條件

1. `/selection.html` 書目以卡片 grid 呈現（預設 3 欄，響應式縮至 2 欄或 1 欄）
2. 每張卡片顯示：書名、作者、ISBN、定價、採購價、得獎項目、完整度狀態
3. 未選書卡片顯示「＋ 加入選書」按鈕，點擊後送出 `quantity: 1`
4. 已選書卡片按鈕顯示「已加入」並 disabled
5. 點擊後 budget bar 的已選書目數量與金額統計正確更新
6. 查館藏連結仍可開啟（新分頁）
7. 「修正資料」override 編輯功能仍可使用（改為卡片內展開區）
8. 「清空選書」後所有卡片恢復可加入狀態
9. `python -m compileall app` 無錯誤
