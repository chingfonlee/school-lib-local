# Spec: task-local-cultural-books-mvp

## 目標

建立一個本地端、可開源的圖書採購 MVP，適合小學校在本地 Windows 電腦安裝與使用。**第一階段實作本土文化圖書採購**，以 ISBN 為主鍵比對學校館藏與本土推薦書單，協助學校排除已館藏圖書、進行選書，最後匯出教育局指定的本土文化採購書單 Excel 表格。

系統目標是開源給各地小學使用，因此前端流程、資料模型與匯出架構須預留第二階段的「必選/推薦/自選」一般圖書採購專案，兩種採購類型共用同一套介面與核心服務。

## 需求範圍

### 系統定位

- **小學校本地安裝**：執行 start.bat 啟動，不依賴雲端服務或網路連線
- **採購專案導向**：系統以「採購專案（procurement project）」為頂層單元，V1 預建立一個 `local_culture` 類型的預設專案，前端介面可切換專案
- **開源可擴充**：欄位對應以設定方式實作，不將特定書商欄名或教育局格式寫死為唯一路徑

### 欄位對齊原則

1. **教育局範本欄位是最終標準模型**。系統內部欄位名稱依教育局匯出格式定義。
2. **書商書單與學校館藏都是匯入來源**。匯入流程負責將來源欄位轉換為系統標準欄位，前端主要呈現系統標準欄位。
3. 前端不直接綁定特定書商欄名；書商更換欄名時，只需更新欄位對應設定。

### 欄位完整度分級

每個匯出欄位依重要性分為三級：

| 等級 | 名稱 | 定義 |
|------|------|------|
| blocking | `required_blocking` | 缺少時不可匯出；系統阻擋 |
| review | `required_review` | 可選書可匯入，但匯出前需提醒使用者確認 |
| optional | `optional` | 可留空，不影響匯出 |

**本土文化採購表欄位分級：**

| 匯出欄位 | 等級 | 說明 |
|---------|------|------|
| 排序 | — | 系統產生 |
| 書名 | `required_blocking` | 缺少則不可匯出 |
| 作者 | `required_review` | 缺少需提醒 |
| 出版社 | `required_review` | 缺少需提醒 |
| ISBN | `required_blocking` | 須為有效 ISBN；已由 isbn_status 確保 |
| 採購數量 | `required_blocking` | 須大於 0 |
| 定價 | `required_blocking` | list_price 或 purchase_price 至少一欄有值 |
| 小計 | — | 系統計算 |
| 獲獎項目 | `required_review` | 缺少需提醒 |
| 備註 | `optional` | 可留空 |

### 缺欄位處理原則

**匯入寬鬆，選書清楚，匯出嚴格檢查。**

- 書商書單缺少任何欄位，不因此拒絕整批匯入
- 每本書匯入後計算 `completeness_status`，並在比對結果頁清楚顯示
- 選書階段顯示每本書的完整度警示
- 匯出前執行前置檢查，區分「可匯出」、「需補資料」、「不可匯出」三類

### 獲獎項目與政策議題分類規則

#### award_item 定義

`award_item` 欄位僅填入教育局採購書單下拉選單可接受的獎項或推薦來源，例如：

- 喜閱網
- 文化部中小學生優良課外讀物選介
- 好書大家讀
- 金鼎獎
- 文化部 Books from Taiwan
- 國民中小學新生閱讀推動活動入選書單
- 圖書分級推薦書目、臺灣歷史文化分級推薦書目
- 其他國內外具公信力單位辦理之獎項

#### policy_topic（政策議題）定義

下列標籤為教育政策議題分類，**不應填入 `award_item`**，應獨立儲存於 `policy_topic` 欄位：

- SDGs（聯合國永續發展目標）
- SEL（社會情緒學習）
- 性別平等
- 人權教育
- 環境教育
- 海洋教育
- 生命教育
- 閱讀素養
- 其他教育部或教育局公告的政策議題標籤

#### 分類規則

1. 書商書單獲獎項目欄若含 policy_topic 關鍵字，系統應：
   - 將原始值儲存至 `policy_topic` 欄位
   - 清空 `award_item`（不填入政策議題標籤）
2. 若一本書**只有政策議題標籤而沒有明確獎項或推薦來源**：
   - `award_item` 可暫填「其他國內外具公信力單位辦理之獎項」
   - `award_notes` 必須標記「待確認：{政策議題} 主題書單是否可列為推薦來源」
   - 此書的 `completeness_status` 強制設為 `needs_review`，即使其他欄位均完整
3. 若書商同一欄同時含政策議題與有效獎項名稱，僅保留有效獎項於 `award_item`，政策議題記入 `policy_topic`
4. 使用者仍可透過 user_overrides 手動修正 `award_item`，但 `award_notes` 待確認標記需使用者自行清除

### 核心功能

1. **採購專案管理**：建立、選擇採購專案，每個專案獨立匯入書單、選書與匯出
2. **匯入學校館藏**：支援 .xls 格式，自動偵測欄位或套用欄位對應設定；館藏為全域資料，不屬於特定專案
3. **匯入書商書單**：支援 .xlsx 格式，匯入後歸屬於選定的採購專案
4. **ISBN 正規化**：移除空白、連字號、不可見字元；Excel 數值格式轉文字；僅接受 10 碼或 13 碼
5. **ISBN 比對（match_status）**：以正規化 ISBN 為主鍵標記比對結果（詳見「書目資料狀態」）
6. **欄位完整度計算（completeness_status）**：依欄位分級評估每本書是否可匯出
7. **使用者資料修正**：可對任何欄位輸入修正值（user_override），修正值優先於匯入值用於匯出
8. **選書與採購管理**：填寫採購數量，即時試算預算（以 list_price 與 purchase_price 分別計算）
9. **匯出前置檢查**：顯示已選書的可匯出 / 需補資料 / 不可匯出統計
10. **匯出教育局格式**：套用空白範本，依 `price_field` 與 `subtotal_mode` 設定產生 Excel

### 書目資料狀態

書目狀態分為兩個獨立維度：

#### match_status（ISBN 比對結果）

| 值 | 說明 |
|----|------|
| `available` | ISBN 不在館藏，可採購 |
| `already_owned` | ISBN 完全相同，已館藏 |
| `missing_isbn` | ISBN 欄位缺失或空白 |
| `invalid_isbn` | ISBN 長度非 10/13 碼 |
| `same_title_different_isbn` | 同書名但不同 ISBN（僅標記，V1 不自動排除） |

#### completeness_status（欄位完整度）

僅對 `match_status = available` 的書目計算：

| 值 | 說明 |
|----|------|
| `export_ready` | 所有 required_blocking 欄位有值 |
| `needs_review` | 無 required_blocking 缺失，但有 required_review 欄位缺失；或 award_notes 含「待確認」標記（即使其他欄位完整） |
| `missing_required` | 有一個以上 required_blocking 欄位缺失 |

### 使用者修正資料（三層值）

每本書每個欄位在匯出時依以下優先順序解析：

```
user_override_value → normalized_value → raw_value → 空白
```

- **raw_value**：從 Excel 讀入的原始值，儲存於 `raw_row`（JSON）
- **normalized_value**：匯入時寫入的欄位值（已做基本清理）；ISBN 有獨立的 `isbn_normalized`
- **user_override_value**：使用者透過前端手動修正的值，儲存於 `user_overrides`（JSON）

`user_overrides` 的修改不影響 `completeness_status` 的顯示，但匯出時會採用修正後的值。若使用者填入了原本缺失的 required_blocking 欄位，完整度應重新計算。

### 欄位對齊規則

#### 學校館藏欄位（來源：00_source/學校館藏.xls）

| 來源欄位 | 系統欄位 |
|---------|---------|
| B02 ISBN | isbn |
| B03 書名 | title |
| B07 作者 | author |
| B10 出版社 | publisher |
| B12 出版年 | publish_year |
| B16 價格 | price |
| B04 書目識別號 | library_record_id |

#### 書商本土書單欄位（來源：00_source/更新-日苑-高雄 本土推薦書單-去除重複ISBN.xlsx）

| 來源欄位 | 系統欄位 |
|---------|---------|
| 獲獎項目 | award_item |
| 序號 | vendor_seq |
| 書名 | title |
| 作者 | author |
| 條碼 | isbn |
| 出版日期 | publish_date |
| 定價 | list_price |
| 單價 | purchase_price |
| 數量 | （保留於 raw_row，不作採購計算） |
| 總價 | （保留於 raw_row，不作採購計算） |
| 出版社 | publisher |
| 適合年齡 | age_range |

#### 教育局本土文化採購書單匯出欄位（範本：00_source/高雄市115年度...充實本土文化相關圖書採購書單(空白).xlsx）

| 匯出欄位 | 來源（value resolution 後） |
|---------|--------------------------|
| 排序 | 系統重新編號 |
| 書名 | title |
| 作者 | author |
| 出版社 | publisher |
| ISBN | isbn（正規化後） |
| 採購數量 | selection_items.selected_quantity |
| 定價 | 依 price_field 設定（list_price 或 purchase_price） |
| 小計 | 依 subtotal_mode 設定計算 |
| 獲獎項目 | award_item |
| 備註 | 可留空或使用者填入 |

### ISBN 比對規則

- 移除所有空白（含全形 `　`）、連字號（`-`）、不可見字元（不間斷空格、零寬空格等 Unicode 控制字元）
- Excel 數值格式（如 `9789861371580.0`）先轉整數字串再處理
- 僅接受 10 碼或 13 碼純數字；其他長度標記為 `invalid_isbn`
- ISBN 正規化後完全相同 → `already_owned`
- 書單 ISBN 不在館藏 → `available`
- ISBN 欄位缺失或空白 → `missing_isbn`
- ISBN 長度非 10/13 碼 → `invalid_isbn`
- 同書名但不同 ISBN → 額外標記 `same_title_different_isbn`（不覆蓋 `available`）

### 採購專案（procurement_projects）

每個採購案為一個獨立專案，包含：

- **name**：使用者命名（如「115年度本土文化採購」）
- **project_type**：`local_culture`（本土文化）/ `general_books`（必選/推薦/自選，V2）
- **budget_amount**：核定金額（選填）
- **export_template_type**：決定匯出用哪種教育局範本
- **price_field**：`list_price` / `purchase_price`
- **subtotal_mode**：`quantity_times_list_price` / `quantity_times_purchase_price`

V1 系統啟動時自動建立一個預設 `local_culture` 專案。前端所有操作（匯入書單、選書、匯出）均在選定的專案下進行。

### 匯出設定

| 設定項目 | 選項 | 說明 |
|---------|------|------|
| price_field | `list_price` / `purchase_price` | 定價欄顯示哪個價格 |
| subtotal_mode | `quantity_times_list_price` / `quantity_times_purchase_price` | 小計計算方式 |
| school_name | 使用者輸入 | 填入範本的校名欄 |
| approved_budget | 使用者輸入（選填） | 填入範本的核定金額欄 |

price_field 與 subtotal_mode 可獨立設定（定價欄顯示定價，小計卻用採購單價計算，是合理的使用情境）。

匯出設定儲存於 `procurement_projects`，每次匯出時可覆蓋為一次性設定。

### 資料模型（SQLite）

**users**
- id, username, password_hash, display_name, created_at, updated_at

**procurement_projects**（採購專案）
- id, name, project_type (`local_culture` / `general_books`), budget_amount, export_template_type, price_field, subtotal_mode, created_at, updated_at

**import_profiles**（欄位對應設定）
- id, name, file_type (`library_holdings` / `vendor_books`), column_mappings (JSON), created_at, updated_at

**import_batches**（每次匯入紀錄）
- id, project_id (NULL for library_holdings), batch_type (`library_holdings` / `vendor_books`), original_filename, profile_id, record_count, imported_by, imported_at, notes

**library_holdings**（學校館藏，全域共用）
- id, batch_id, isbn, isbn_normalized, title, author, publisher, publish_year, price, library_record_id, isbn_status, raw_row (JSON)

**vendor_books**（書商書單，歸屬採購專案）
- id, batch_id, award_item, vendor_seq, title, author, isbn, isbn_normalized, publish_date, list_price, purchase_price, publisher, age_range, isbn_status, completeness_status, policy_topic (TEXT), award_notes (TEXT), user_overrides (JSON), raw_row (JSON)
- `policy_topic`：儲存 SDGs / SEL 等政策議題標籤（從獲獎項目欄分離出的政策議題值）
- `award_notes`：待確認標記，如「待確認：SDGs 主題書單是否可列為推薦來源」；含此標記時 completeness_status 強制為 needs_review
- 備註：V1 欄位對應 local_culture 書單；award_item / vendor_seq / policy_topic / award_notes 為 local_culture 專用選填欄位；V2 可視需要擴充

**book_matches**（比對結果）
- id, vendor_book_id, holding_id (NULL 若未匹配), match_status, matched_at, batch_run_id

**selection_items**（選書，歸屬採購專案）
- id, project_id, vendor_book_id (UNIQUE per project), selected_quantity, notes, created_by, created_at, updated_at

**export_jobs**（匯出紀錄）
- id, project_id, school_name, approved_budget, price_field, subtotal_mode, template_path, output_filename, output_path, exported_by, exported_at, record_count, total_amount

**schema_migrations**
- version, applied_at

### 技術規格

| 項目 | 選型 |
|------|------|
| 後端 | Python + FastAPI |
| 資料庫 | SQLite（本地端，隨 app 目錄存放） |
| Excel 讀取 | pandas + xlrd（.xls）、openpyxl（.xlsx） |
| Excel 匯出 | openpyxl，套用教育局空白範本格式 |
| 前端 | 靜態 HTML/CSS/Vanilla JS |
| 本地啟動 | start.bat（Windows） |
| 設定 | config.yaml |
| 部署環境 | 本地 Windows 電腦，無雲端服務 |

## 不做的事

- 不做雲端部署或遠端服務
- 不做多人即時協作
- 不做正式上架編目（OPAC）
- 不做書名模糊比對自動排除（same_title_different_isbn 第一版僅標記）
- 不做 ISBN-13 checksum 驗證（第一版以長度作為驗證依據）
- 不在 V1 實作 general_books 採購專案的完整流程（預留架構，不實作）
- 不修改 `00_source/` 下任何原始 Excel 檔案
- 不預設固定折扣率
- 不使用雲端服務或外部 API

## 驗收條件

**匯入與比對**
1. 可匯入 `00_source/學校館藏.xls`，欄位正確對應至 library_holdings
2. 可匯入 `00_source/更新-日苑-高雄 本土推薦書單-去除重複ISBN.xlsx`，欄位正確對應至 vendor_books
3. 書商書單缺少非阻擋欄位（如作者、出版社）時，仍可完成匯入，不拒絕整批
4. 執行比對後，match_status 各值（already_owned、available、missing_isbn、invalid_isbn）均正確標記

**完整度與選書**
5. 每本書顯示 completeness_status（export_ready / needs_review / missing_required）
6. 可在選書頁面填入採購數量，即時顯示兩種預算試算（list_price 小計與 purchase_price 小計）
7. 使用者可對任意欄位輸入 user_override，修正值在前端即時反映
8. 書商書單獲獎項目欄含 SDGs / SEL 等政策議題關鍵字時，系統自動分離至 policy_topic，award_item 清空並設 award_notes 待確認標記，該書進入 needs_review

**匯出**
8. 匯出前檢查頁顯示：已選幾本 / 可匯出幾本 / 需補資料幾本 / 不可匯出幾本
9. 已選書若缺 required_blocking 欄位，系統阻擋匯出並指出哪本書缺哪個欄位
10. 已選書若缺 required_review 欄位，系統提醒但允許繼續匯出
11. 依匯出設定（price_field + subtotal_mode）正確產生教育局本土文化 Excel，定價欄與小計計算各自獨立
12. 匯出檔套用原始空白範本格式，校名與資料填入位置正確

**系統基礎**
13. `00_source/` 下所有原始檔案在所有操作後未被修改
14. `start.bat` 可在 Windows 電腦首次啟動（自動建立虛擬環境、安裝 dependencies）
15. 未登入狀態無法執行任何匯入、選書、匯出操作
