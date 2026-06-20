# Spec: task-selection-advanced-filters

## 目標

在選書頁（selection.html）提供進階篩選與排序功能，讓老師面對大量書商書單時能快速縮小範圍，找到「可採購、適合年級、符合主題、資料完整、預算合理」的書。

## 問題說明

目前 selection.html 的篩選條件不足：

- filter-bar 僅有「完整度篩選」（completeness_status select）與「書名搜尋」（title text）
- `loadData()` 硬編碼 `match_status=available`，頁面只顯示「可採購」書，老師無法看見已館藏、ISBN 缺失或 ISBN 無效的書
- `/api/books/matches` 後端硬編碼 `vb.isbn_status = 'valid'`，ISBN 有問題的書無法進入 allBooks
- 無法依書本類型、年齡、分類、價格區間快速篩選
- 無排序功能

## 需求範圍

### 1. 顯示範圍

`/api/books/matches` 維持 `vb.isbn_status = 'valid'` 過濾，`loadData()` 移除 `match_status=available` 硬編碼，預設載入全部 valid-ISBN 書（available + already_owned）。

**第一階段不顯示 missing_isbn / invalid_isbn**：無有效 ISBN 的書無法採購；在選書頁顯示意義不大，排除後 filter-bar 不需要這兩個比對狀態選項。

### 2. 篩選條件

#### 比對狀態（match_status）
| 選項 | 對應值 |
|------|--------|
| 全部（預設） | — |
| 可採購 | available |
| 已館藏 | already_owned |

比對狀態篩選使用 effective status：`b.match_status || b.current_match_status || 'unknown'`。
API 可能回傳 `match_status`（來自 JOIN book_matches）或 `current_match_status`（來自子查詢快照），以第一個有值的欄位為準。

#### 資料完整度（completeness_status）
| 選項 | 對應值 |
|------|--------|
| 全部（預設） | — |
| 可匯出 | export_ready |
| 需補資料 | needs_review |
| 缺必要欄位 | missing_required |

#### 書本類型（book_type）
- 下拉選單，選項從 allBooks 動態產生（去重、排序、移除空值）
- 預設「全部」
- **若 allBooks 中 book_type 均為空（目前現況），隱藏 label + select**；重新匯入且有值後自動恢復顯示
- 未來要使用此篩選，需在匯入時正確 mapping「書本類型」欄位並重新匯入

#### 適讀年齡（age_range）
- 下拉選單，選項從 allBooks 動態產生（去重、排序、移除空值）
- 預設「全部」

#### 分類 / 議題（category + policy_topic 文字包含搜尋）
- 單一 text input，搜尋涵蓋 `category` 與 `policy_topic` 欄位
- **若 allBooks 中 category 與 policy_topic 均為空（目前現況），隱藏此 input**；重新匯入且有值後自動恢復顯示
- `policy_topic` 欄位目前在匯入流程未填入（vendor_books schema 有此欄位但 import 不寫入）；未來要使用需在匯入時正確 mapping 並重新匯入

#### 價格區間（purchase_price fallback list_price）
- min_price 與 max_price 兩個數字 input
- 價格來源邏輯（`getEffectivePrice`）：優先 `purchase_price`，若為 null / 0 則 fallback `list_price`；兩者均無則視為無價格（不參與區間比較時排除）
- 僅一端填寫時：只套用單邊邊界

#### 關鍵字搜尋
- 單一 text input，搜尋涵蓋以下欄位（任一符合即可）：
  `title`、`author`、`isbn`、`isbn_normalized`、`publisher`、`summary`、`category`、`book_type`、`policy_topic`
- 大小寫不敏感，使用簡單 includes（不做斷詞）

#### 排序
| 選項 | 邏輯 |
|------|------|
| 匯入順序（預設） | `id` asc |
| 可採購優先 | available 在前，其餘依 id |
| 資料完整度優先 | export_ready → needs_review → missing_required → unknown |
| 價格低到高 | getEffectivePrice asc，無價格排最後 |
| 價格高到低 | getEffectivePrice desc，無價格排最後 |
| 書名 A→Z | title asc（字串比較） |

### 3. 重設篩選

「重設篩選」按鈕：清空所有篩選欄位，恢復顯示全部。

### 4. 計數顯示

filter-bar 旁顯示「共 N 筆」，反映篩選後書本數量（不含 cleared-section）。

## 行為定義

- 篩選只作用於 allBooks（vendor_books 候選清單），不影響 `#cleared-section`（已清除來源的 snapshot）
- `#cleared-section` 維持獨立顯示，不納入主篩選
- budget bar（已選書目、定價小計、採購單價小計）資料來自 `/api/selections/`，由 `refreshBudget()` / `loadData()` 更新，不受前端篩選影響
- 篩選結果為空時，`#book-grid` 顯示「無符合條件的書目」
- 篩選條件改變時即時更新（onchange / oninput）

## 不做的事

- 不改 DB schema
- 不改匯入流程（含 policy_topic、book_type 欄位的匯入邏輯）
- 不改 selection_items snapshot 邏輯
- 不改 export 流程
- 不做大型 UI redesign
- 不儲存篩選條件偏好
- 不做後端全文搜尋或分頁
- 不改 budget bar 計算邏輯
- 不調整 `/api/books/stats` 統計語意（match.html stats 不在本 task 範圍）；books.py 改動僅限 `/api/books/matches` 候選清單查詢

## 驗收條件

- [ ] selection.html 可依 match_status 篩選（available / already_owned / 全部）；不顯示 missing_isbn / invalid_isbn
- [ ] 可依 completeness_status 篩選
- [ ] book_type 有資料時顯示動態 select；無資料時隱藏（目前預期隱藏）
- [ ] 可依 age_range 篩選（select 選項從 allBooks 動態產生，目前有 670 筆資料）
- [ ] category / policy_topic 有資料時顯示 input；無資料時隱藏（目前預期隱藏）
- [ ] 可依 min_price / max_price 價格區間篩選（price fallback 已處理）
- [ ] 關鍵字搜尋涵蓋 title、author、isbn / isbn_normalized、publisher、summary、category、book_type、policy_topic
- [ ] 排序功能六種選項可正常切換
- [ ] 重設篩選後恢復全部顯示
- [ ] 已選書數量與金額統計不受篩選影響
- [ ] `#cleared-section` 顯示不被破壞
- [ ] `python -m compileall app` 通過
