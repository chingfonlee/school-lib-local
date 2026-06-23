# Plan: task-flow-stepper-nav

## 實作步驟

1. **修改 `app/static/css/style.css`：追加 stepper 樣式**

   在現有 `/* Nav */` 區塊內，於保留背景圖設定的前提下，追加或調整以下規則：

   ```css
   /* 防止窄螢幕擠壓右側 */
   .nav-title { flex-shrink: 0; }
   .nav-steps { min-width: 0; flex-wrap: nowrap; overflow-x: auto; }
   .nav-right { flex-shrink: 0; }

   /* Stepper 連結 */
   .nav-steps a {
     display: flex; align-items: center; gap: 5px;
     padding: 5px 10px; border-radius: 6px;
     font-size: 13px; color: #555; white-space: nowrap;
   }
   .nav-steps a:not(:last-child)::after {
     content: "›"; color: #c8c8cd; margin-left: 2px; font-size: 14px;
   }

   /* 序號徽章 */
   .step-num {
     display: inline-flex; align-items: center; justify-content: center;
     width: 18px; height: 18px; border-radius: 50%;
     font-size: 11px; font-weight: 600;
     background: #d2d2d7; color: #555; flex-shrink: 0;
   }
   .nav-steps a.active .step-num { background: #0071e3; color: #fff; }
   .nav-steps a.active { color: #1d1d1f; font-weight: 600; }

   /* 輔助工具連結 */
   .nav-tool {
     padding: 5px 10px; font-size: 13px; color: #888;
     border-left: 1px solid #d2d2d7; margin-left: 4px;
     white-space: nowrap;
   }
   .nav-tool:hover { color: #444; text-decoration: none; }
   .nav-tool.active { color: #0071e3; font-weight: 600; }
   ```

   注意：不刪除、不覆蓋 body 背景圖相關設定（`linear-gradient` 與 `url("/img/library-procurement-bg.webp")`）。

2. **更新 8 個 HTML 檔案的 nav 結構**

   對每個有 nav 的頁面，將 `.nav-steps` 內的連結改為含序號結構，
   並將館藏查詢移出 `.nav-steps`、改為 `.nav-tool`，置於 `.nav-steps` 之後、`.nav-right` 之前。

   注意：讀寫 HTML 時避免因終端顯示亂碼就誤判編碼問題；
   這些檔案為 UTF-8 without BOM，終端亂碼不代表檔案編碼錯誤，
   瀏覽器顯示正常即以現有編碼為準，不得重編碼整個檔案。

   **統一 nav 範本（各頁僅改 active 位置）：**

   ```html
   <nav>
     <div class="nav-inner">
       <span class="nav-title">圖書採購系統</span>
       <div class="nav-steps">
         <a href="/projects.html">
           <span class="step-num">1</span>採購專案
         </a>
         <a href="/import.html">
           <span class="step-num">2</span>匯入
         </a>
         <a href="/match.html">
           <span class="step-num">3</span>比對結果
         </a>
         <a href="/selection.html">
           <span class="step-num">4</span>選書
         </a>
         <a href="/export-check.html">
           <span class="step-num">5</span>匯出前檢查
         </a>
         <a href="/export.html">
           <span class="step-num">6</span>匯出
         </a>
       </div>
       <a href="/holdings.html" class="nav-tool">館藏查詢</a>
       <div class="nav-right"><span id="user-name"></span> <a href="#" onclick="logout()">登出</a></div>
     </div>
   </nav>
   ```

   各頁面的 active 對應：

   | 頁面 | active 位置 |
   |------|------------|
   | projects.html | 步驟 1 `<a>` 加 `class="active"` |
   | import.html | 步驟 2 `<a>` 加 `class="active"` |
   | match.html | 步驟 3 `<a>` 加 `class="active"` |
   | selection.html | 步驟 4 `<a>` 加 `class="active"` |
   | export-check.html | 步驟 5 `<a>` 加 `class="active"` |
   | export.html | 步驟 6 `<a>` 加 `class="active"` |
   | holdings.html | 主步驟無 active；`.nav-tool` 加 `class="nav-tool active"` |
   | index.html | 主步驟無 active；`.nav-tool` 無 active |

3. **本機驗證**

   啟動服務（`uvicorn` / FastAPI StaticFiles）後，逐頁確認：

   - 各頁面 active 步驟序號顯示藍色（`#0071e3`）
   - holdings.html：館藏查詢 active，主步驟序號均灰色
   - index.html：所有步驟均灰色，館藏查詢無 active
   - 桌面 1280px：六步驟序號與連接符 `›` 完整可見
   - DevTools 375px：`.nav-steps` 水平捲動，`.nav-right`（使用者/登出）不被擠壓
   - 背景圖存在時 nav 文字清楚可讀（半透明白色 nav 不受影響）

## 風險與注意事項

- **編碼安全**：HTML 檔為 UTF-8 without BOM；若終端顯示中文亂碼，
  先用 bytes 層確認（有無 BOM、換行符），不得因亂碼就重編碼整個檔案
- **背景圖保留**：`style.css` 修改只追加 nav/stepper 樣式，
  不刪除或覆蓋 body 背景圖設定與 `library-procurement-bg.webp` 引用
- **`tmp/` 不 commit**：`tmp/` 為本機服務啟動產生的 log，不納入 commit
- **`匯出前檢查` 寬度**：五字步驟名稱較長，確認桌面版 nav 不超出容器

## 預計影響範圍

| 檔案 | 異動類型 |
|------|---------|
| `app/static/css/style.css` | 追加 `.step-num`、`.nav-tool`、`.nav-tool.active`；調整 `.nav-steps`、`.nav-title`、`.nav-right` |
| `app/static/projects.html` | 修改 nav HTML（步驟 1 active） |
| `app/static/import.html` | 修改 nav HTML（步驟 2 active） |
| `app/static/match.html` | 修改 nav HTML（步驟 3 active） |
| `app/static/selection.html` | 修改 nav HTML（步驟 4 active） |
| `app/static/export-check.html` | 修改 nav HTML（步驟 5 active） |
| `app/static/export.html` | 修改 nav HTML（步驟 6 active） |
| `app/static/holdings.html` | 修改 nav HTML（館藏查詢 active） |
| `app/static/index.html` | 修改 nav HTML（無 active） |
| `app/static/login.html` | 不動（無 nav） |

## 驗證指令

- lint：不適用（純 HTML/CSS，專案無 linter 設定）
- format：手動檢查縮排一致性（2 空格）
- typecheck：不適用
- test：手動瀏覽器驗證（啟動 FastAPI StaticFiles 後逐頁確認，見上方步驟 3）
- build：不適用（靜態檔案，由 FastAPI StaticFiles 直接 serve）

## 是否需要截圖

建議在桌面寬度（1280px）與窄螢幕（375px）各截圖 projects.html 一張確認視覺，
不強制所有頁面截圖。

## 成果報告

- result_report_mode: none
- 適用情境：純 UI 調整，驗收以目視確認為主，不需結構化報告
