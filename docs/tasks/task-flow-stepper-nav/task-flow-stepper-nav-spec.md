# Spec: task-flow-stepper-nav

## 目標

將導覽列的平列連結改為六步驟式流程 stepper，讓使用者能清楚辨識圖書採購
的操作順序及目前所在步驟。「館藏查詢」定位為輔助工具，視覺上與主流程明確
區隔，不被視為第七步。

## 使用者目標

- 進入任一頁面，立即知道自己在第幾步
- 能看見完整六步流程，理解前後步驟
- 「館藏查詢」不被誤解為主流程步驟

## 需求範圍

### 主流程六步驟

| 序號 | 步驟名稱 | 對應頁面 |
|------|----------|---------|
| 1 | 採購專案 | projects.html |
| 2 | 匯入 | import.html |
| 3 | 比對結果 | match.html |
| 4 | 選書 | selection.html |
| 5 | 匯出前檢查 | export-check.html |
| 6 | 匯出 | export.html |

### 館藏查詢（輔助工具）

- 保留導覽中，視覺權重低於主流程
- 不附序號
- 放置於 `.nav-steps` 之外、`.nav-right` 之前（使用 `.nav-tool` class）
- 支援 `.nav-tool.active`，在 holdings.html 上顯示 active 狀態
- 在其他頁面不顯示 active

### 視覺規格

- 每個主流程步驟顯示 1–6 序號（圓形徽章，`.step-num` class）
- 步驟間有連接感（細箭頭 `›`，以 CSS `::after` 實作）
- active 步驟序號：`#0071e3`（與現有主按鈕藍一致），白字
- 非 active 步驟：低對比度（灰底灰字），不搶主內容視線
- 整體延續現有設計語言：玻璃態半透明 nav、系統字體、白色卡片

### 響應式

- 桌面（≥ 768px）：六步驟完整橫向排列，序號與連接符可見
- 窄螢幕（< 768px）：`.nav-steps` 水平捲動（`overflow-x: auto`），不換行
- `.nav-title`、`.nav-right` 設 `flex-shrink: 0`，確保右側使用者/登出不被擠壓
- `.nav-steps` 設 `min-width: 0`，讓捲動能正確收縮
- 任何寬度下不得出現文字重疊、導覽破版

## 不做的事

- 不做後端 API 修改
- 不實作步驟完成/未完成狀態判斷（無 JS 狀態邏輯）
- 不引入前端框架或 build pipeline
- 不處理登入/權限邏輯
- 不動 login.html（無 nav）
- 不建立共用 template 元件（維持靜態 HTML 架構，各頁各自維護 nav）

## 驗收條件

1. projects.html → 步驟 1 active（序號藍色），館藏查詢無序號且非 active
2. import.html → 步驟 2 active
3. match.html → 步驟 3 active
4. selection.html → 步驟 4 active
5. export-check.html → 步驟 5 active
6. export.html → 步驟 6 active
7. holdings.html → 六個主步驟均非 active，館藏查詢 active
8. index.html → 六個主步驟均非 active，館藏查詢非 active
9. 背景圖存在時（`library-procurement-bg.webp`），nav 文字仍清楚可讀
   （依賴現有 `backdrop-filter: blur` + `rgba` 背景）
10. 桌面寬度下六步驟序號與連接符號清楚可見
11. 375px 寬度時 `.nav-steps` 水平捲動，nav 不破版、不文字重疊

## 風險與限制

- nav HTML 在 8 個頁面中各自重複，無共用元件；修改量略多，需逐一更新
- `app/static/css/style.css` 目前有未 commit 的背景圖設定（已確認保留），
  實作時在現有內容上追加 nav/stepper 樣式，不覆蓋背景設定
- 讀寫 HTML 檔案時須避免終端亂碼誤判編碼，不得重編碼整個檔案；
  若終端顯示異常，先確認 bytes 層級，瀏覽器顯示正常即為正確
- `匯出前檢查` 字數多，需確認桌面版 nav 不超寬或序號標籤不擠壓
