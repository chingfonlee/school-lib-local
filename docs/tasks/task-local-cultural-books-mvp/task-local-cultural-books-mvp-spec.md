# Spec: task-local-cultural-books-mvp

## 目標

建立一個本地端、可開源的圖書採購 MVP，適合小學校在本地 Windows 電腦安裝與使用。**第一階段實作本土文化圖書採購**，以 ISBN 為主鍵比對學校館藏與本土推薦書單，協助學校排除已館藏圖書、進行選書，最後匯出教育局指定的本土文化採購書單 Excel 表格。

系統目標是開源給各地小學使用，因此前端流程、資料模型與匯出架構須預留第二階段的「必選/推薦/自選」一般圖書採購專案，兩種採購類型共用同一套介面與核心服務。

## 需求範圍

### 系統定位

- **小學校本地安裝**：執行 start.bat 啟動，不依賴雲端服務或網路連線
- **採購專案導向**：系統以「採購專案（procurement project）」為頂層單元，V1 預建立一個 `local_culture` 類型的預設專案，前端介面可切換專案
- **開源可擴充**：欄位對應以設定方式實作，不將特定書商欄名或教育局格式寫死為唯一路徑

### 欄位對齊總原則

1. **教育局範本欄位是最終輸出標準模型**。系統內部欄位名稱依教育局匯出格式定義，前端主要呈現系統標準欄位名稱。
2. **書商書單欄名不得寫死於程式碼**。不同書商格式以欄位對應設定（import_profile）橋接；自動偵測的 HINTS 字典為預設值，使用者可手動覆蓋。
3. **自動偵測為輔助，使用者必須確認**。系統依關鍵字猜測欄位對應，但必須在精靈步驟讓使用者檢視並確認，確認後才寫入資料庫。
4. **欄位對應確認前不寫入 vendor_books**。匯入精靈預覽步驟僅回傳欄位猜測結果，不執行正式寫入；使用者點選「確認匯入」後才正式寫入。
5. **未對應的書商欄位保留為 extra_fields**。不因欄位無法對應至標準欄位而阻擋匯入；使用者選定要保留的額外欄位後，其值存入 `vendor_books.extra_fields` JSON。
6. **欄位對齊設定可儲存為 import_profile**。儲存後可供下次相同書商格式直接套用，省略手動對應步驟；profile 包含書商名稱、標題列號、欄位對應與額外欄位設定。
7. **學校館藏匯入同樣套用自動偵測與 profile 機制**。館藏欄位固定（教育局格式），僅需偵測欄名異動；館藏無需 extra_fields 保留。

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

### 獲獎項目規則（V1 local_culture）

#### award_item 在 local_culture 的處理原則

V1 `local_culture` 採購專案：**直接保留書商書單「獲獎項目」欄的原始文字**，不進行任何自動拆分或轉換。

- 匯入時：將書商來源欄「獲獎項目」的值原文寫入 `award_item`，不因含 SDGs / SEL 等標籤而自動改寫
- 不自動填入「其他國內外具公信力單位辦理之獎項」
- 不自動設 `award_notes` 待確認標記
- `award_item` 缺少時屬 `required_review`（匯出前提醒，但不阻擋匯出）
- 使用者可透過 user_overrides 手動修正 `award_item`

#### policy_topic / award_notes（V2 reserved）

`policy_topic` 與 `award_notes` 欄位保留於 schema，供 V2 `general_books` 採購專案使用：

- V2 general_books 的獲獎項目欄需符合教育局下拉選單（如喜閱網、金鼎獎、好書大家讀等），並需與 SDGs / SEL 等政策議題標籤分離
- V1 local_culture **不使用** `policy_topic` 與 `award_notes` 進行強制判斷，這兩個欄位在 V1 保持空白

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
| `needs_review` | 無 required_blocking 缺失，但有 required_review 欄位缺失（author、publisher、award_item 任一為空） |
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

### 書商書單欄位對齊精靈（5 步驟流程）

匯入書商書單採用精靈式流程，分為兩個 API 呼叫（預覽 + 確認），共 5 個前端步驟：

| 步驟 | 代號 | 說明 |
|------|------|------|
| A | upload | 上傳 Excel，選擇採購專案 |
| B | sheet_header | 選擇工作表與標題列（系統自動猜測，使用者可修改） |
| C | field_mapping | 確認欄位對應（系統猜測 + 使用者修正；下拉選單選取） |
| D | extra_fields | 選擇要保留並在選書頁顯示的額外欄位 |
| E | confirm_import | 確認並正式匯入 |

步驟 A–D 由前端呼叫 `POST /api/imports/vendor-books/preview` 完成；步驟 E 呼叫 `POST /api/imports/vendor-books/confirm` 正式寫入 vendor_books。

**必要欄位對應（至少完成才可進行步驟 E）：**
- `title`（書名）— required_blocking
- `isbn`（ISBN / 條碼）— required_blocking
- `author`（作者）— required_review，允許留空但按鈕顯示警告
- `publisher`（出版社）— required_review，允許留空但按鈕顯示警告
- `list_price` 或 `purchase_price`（定價或採購單價，至少一欄）— required_blocking

### 教育局範本欄位作為標準模型

系統以教育局匯出欄位定義為內部標準欄位，不同版本採購專案對應不同欄位集合：

#### V1 local_culture 標準欄位

| 系統欄位 | 說明 | 完整度等級 |
|---------|------|------------|
| title | 書名 | required_blocking |
| author | 作者 | required_review |
| publisher | 出版社 | required_review |
| isbn | ISBN（正規化後） | required_blocking（isbn_status 確保） |
| quantity | 採購數量 | required_blocking（selection_items.selected_quantity） |
| list_price | 定價 | required_blocking（至少一種價格有值） |
| purchase_price | 採購單價 | required_blocking（至少一種價格有值） |
| award_item | 獲獎項目 | required_review |
| notes | 備註 | optional |

#### V2 general_books 預留欄位（V1 保持空白）

| 系統欄位 | 說明 |
|---------|------|
| selection_type | 必選 / 推薦 / 自選（V2 採購類型分類） |
| policy_topic | 政策議題標籤（SDGs / SEL 等，從獲獎項目分離） |

### 書商額外欄位保留

書商書單中未對應至標準欄位的來源欄，統一保留於 JSON 欄位：

- **raw_row**（已有）：每列完整原始值（所有來源欄），始終完整保留，不對外暴露。
- **extra_fields**（新增）：使用者在精靈步驟 D 勾選的額外欄位名稱與值，供選書頁顯示與篩選。

常見書商額外欄位範例：`分類`、`適合年齡`、`CIP`、`主題`、`內容簡介`、`購書連結`、自訂標籤。

**規則：**
1. 精靈步驟 D 列出所有未對應至標準欄位的書商來源欄，使用者勾選要保留的欄位。
2. 勾選欄位的欄名與值存入 `vendor_books.extra_fields`（JSON object）。
3. 選書頁可顯示 extra_fields 欄位（可展開），並可依 extra_fields 欄位值篩選書目。
4. extra_fields **不影響匯出**；匯出欄位固定為教育局格式標準欄位。
5. 未被勾選的額外欄位值仍保留於 raw_row，不會遺失。

### ISBN 比對規則

- 移除所有空白（含全形 `　`）、連字號（`-`）、不可見字元（不間斷空格、零寬空格等 Unicode 控制字元）
- Excel 數值格式（如 `9789861371580.0`）先轉整數字串再處理
- 僅接受 10 碼或 13 碼純數字；其他長度標記為 `invalid_isbn`
- ISBN 正規化後完全相同 → `already_owned`
- 書單 ISBN 不在館藏 → `available`
- ISBN 欄位缺失或空白 → `missing_isbn`
- ISBN 長度非 10/13 碼 → `invalid_isbn`
- 同書名但不同 ISBN → 額外標記 `same_title_different_isbn`（不覆蓋 `available`）

#### 館藏 ISBN 比對範圍

- **僅 `isbn_status = 'valid'` 的館藏加入比對索引**。缺 ISBN 或 ISBN 無效的館藏仍可匯入（供參考），但不加入 `{isbn_normalized: holding_id}` 索引。
- 館藏缺 ISBN 或 ISBN 無效時，**不在比對結果頁顯示**，也**不計入「ISBN 異常」統計**；這是館藏本身的資料品質問題，與書商書單 match_status 無關。
- 書商書單缺 ISBN（`missing_isbn`）或 ISBN 無效（`invalid_isbn`）的書目，**不作為比對對象**，也**不加入「可採購」清單**。比對結果頁以「已忽略缺 ISBN N 本」顯示其筆數，不以錯誤呈現。

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

### 匯出範本設計原則

教育局採購書單範本可能每年改版，也因縣市不同而有所差異。系統採可替換設計，不將任何範本結構資訊寫死於程式碼。

**系統資料流：**

```
書商書單 → import_profile → 系統標準欄位 → selection_items → export_template → 教育局 Excel
```

**import mapping 與 export mapping 的區別：**

| Mapping 種類 | 方向 | 儲存位置 |
|------------|------|--------|
| import_profile.mappings | 來源欄位 → 系統標準欄位 | import_profiles.mappings JSON |
| export_template.column_mappings | 系統標準欄位 → 教育局 Excel 欄位字母 | export_templates.column_mappings JSON |

**設計原則：**
1. 匯出 Excel 的所有結構資訊（範本路徑、sheet 名稱、校名儲存格、核定金額儲存格、資料起始列、各欄位位置）均由 `export_templates` 資料模型提供，**不寫死於 `export_service.py`**。
2. **V1**：由 config.yaml 定義範本設定，系統啟動時透過 `ensure_initial_data()` seed 至 SQLite `export_templates` 表；export_service 從 DB 讀取設定。
3. **V2**：可加入前端「匯出範本管理」頁，讓使用者上傳新範本、選 sheet、設定儲存格與欄位對應；seed 機制不衝突，DB 中可有多筆 template。
4. 每個 `procurement_project` 透過 `export_template_type` 關聯一個 `export_template`（name 欄位對應）。
5. `export_service.py` 只做業務邏輯（value resolution、儲存格填入、小計計算），範本結構從傳入的 template 設定讀取。

### 資料模型（SQLite）

**users**
- id, username, password_hash, display_name, created_at, updated_at

**procurement_projects**（採購專案）
- id, name, project_type (`local_culture` / `general_books`), budget_amount, export_template_type, price_field, subtotal_mode, created_at, updated_at

**import_profiles**（欄位對應設定）
- id, name, file_type (`library_holdings` / `vendor_books`), project_type (`local_culture` / `general_books`), source_type (TEXT，書商或機構名稱，選填), header_row (INTEGER，標題列號), mappings (JSON，格式 `{"title": "書名", "isbn": "條碼", ...}`，系統欄位名為 key、來源欄名為 value), extra_field_settings (JSON，格式 `["分類", "適合年齡"]`，使用者選定要保留的額外欄位清單), created_at, updated_at
- 備註：原 `column_mappings` 欄由 `mappings` 取代（格式方向相反：新格式 key=系統欄、value=來源欄；舊格式 key=來源欄、value=系統欄）

**import_batches**（每次匯入紀錄）
- id, project_id (NULL for library_holdings), batch_type (`library_holdings` / `vendor_books`), original_filename, profile_id, record_count, imported_by, imported_at, notes

**library_holdings**（學校館藏，全域共用）
- id, batch_id, isbn, isbn_normalized, title, author, publisher, publish_year, price, library_record_id, isbn_status, raw_row (JSON)

**vendor_books**（書商書單，歸屬採購專案）
- id, batch_id, award_item, vendor_seq, title, author, isbn, isbn_normalized, publish_date, list_price, purchase_price, publisher, age_range, isbn_status, completeness_status, policy_topic (TEXT), award_notes (TEXT), user_overrides (JSON), extra_fields (JSON), source_row_number (INTEGER), raw_row (JSON)
- `policy_topic`：V2 reserved，供 general_books 儲存 SDGs / SEL 等政策議題標籤；V1 local_culture 保持空白
- `award_notes`：V2 reserved，供 general_books 記錄待確認標記；V1 local_culture 保持空白，不用於 completeness_status 判斷
- `extra_fields`：使用者在精靈步驟 D 選定的額外書商欄位值（JSON object，如 `{"分類": "文學", "適合年齡": "6-10歲"}`）；選書頁可顯示與篩選；不影響匯出
- `source_row_number`：來源 Excel 中的列號（整數，從 1 起算），供除錯與溯源使用
- 備註：V1 欄位對應 local_culture 書單；V2 可視需要擴充

**book_matches**（比對結果）
- id, vendor_book_id, holding_id (NULL 若未匹配), match_status, matched_at, batch_run_id

**selection_items**（選書，歸屬採購專案）
- id, project_id, vendor_book_id (UNIQUE per project), selected_quantity, notes, created_by, created_at, updated_at

**export_templates**（匯出範本設定）
- id, name (TEXT UNIQUE，如 `local_culture_kaohsiung_115`), project_type, template_file_path, sheet_name (TEXT，預設 NULL 表示第一個 sheet), header_row (INTEGER，範本欄位標題列號), data_start_row (INTEGER), max_rows (INTEGER，可用資料列數), school_name_cell (TEXT，如 `A3`), approved_budget_cell (TEXT，如 `E3`), total_quantity_cell (TEXT，如 `F56`), total_amount_cell (TEXT，如 `H56`), column_mappings (JSON), created_at, updated_at
- `column_mappings` 格式：`{"sort_order": "A", "title": "B", "author": "C", "publisher": "D", "isbn": "E", "quantity": "F", "price": "G", "subtotal": "H", "award_item": "I", "notes": "J"}`

**export_jobs**（匯出紀錄）
- id, project_id, export_template_id (INTEGER REFERENCES export_templates), school_name, approved_budget, price_field, subtotal_mode, template_path, output_filename, output_path, exported_by, exported_at, record_count, total_amount

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

**匯入精靈**
1. 可透過精靈匯入 `00_source/更新-日苑-高雄 本土推薦書單-去除重複ISBN.xlsx`，精靈 A→E 步驟全部正常完成
2. 精靈步驟 C 正確顯示自動猜測的欄位對應，使用者可修改下拉選單覆蓋猜測值
3. 精靈步驟 D 列出未對應的書商來源欄，使用者勾選後 extra_fields 正確寫入 vendor_books
4. 欄位對應確認前（步驟 E 點選前）不寫入 vendor_books；點選「確認匯入」後才正式寫入
5. 欄位對齊設定可儲存為 import_profile，下次匯入相同書商格式時可套用

**館藏匯入**
6. 可匯入 `00_source/學校館藏.xls`，欄位正確對應至 library_holdings
7. 缺 ISBN 或 ISBN 無效的館藏仍可匯入，但不加入比對索引，也不在比對結果頁顯示，不計入「ISBN 異常」統計

**書商書單匯入**
8. 書商書單缺少非阻擋欄位（如作者、出版社）時，仍可完成匯入，不拒絕整批
9. 書商書單缺 ISBN（missing_isbn）或 ISBN 無效（invalid_isbn）的書目，比對結果頁顯示為「已忽略缺 ISBN N 本」，不顯示為錯誤，不加入「可採購」清單

**ISBN 比對**
10. 執行比對後，有效 ISBN 書商書目的 match_status（already_owned、available）均正確標記
11. 比對索引僅使用 isbn_status = 'valid' 的館藏，缺 ISBN 館藏不影響書商書單的 match_status

**完整度與選書**
12. 每本書顯示 completeness_status（export_ready / needs_review / missing_required）
13. 可在選書頁面填入採購數量，即時顯示兩種預算試算（list_price 小計與 purchase_price 小計）
14. 使用者可對任意欄位輸入 user_override，修正值在前端即時反映
15. local_culture 書單的獲獎項目欄原文保留於 award_item，不做自動拆分；award_item 缺少時 completeness_status 為 needs_review
16. 選書頁可顯示 extra_fields 欄位（展開區塊）；可依 extra_fields 欄位值篩選書目

**匯出**
17. 匯出前檢查頁顯示：已選幾本 / 可匯出幾本 / 需補資料幾本 / 不可匯出幾本
18. 已選書若缺 required_blocking 欄位，系統阻擋匯出並指出哪本書缺哪個欄位
19. 已選書若缺 required_review 欄位，系統提醒但允許繼續匯出
20. 依匯出設定（price_field + subtotal_mode）正確產生教育局本土文化 Excel，定價欄與小計計算各自獨立
21. 匯出檔套用原始空白範本格式，校名與資料填入位置正確；extra_fields 不出現在匯出欄位

**系統基礎**
22. `00_source/` 下所有原始檔案在所有操作後未被修改
23. `start.bat` 可在 Windows 電腦首次啟動（自動建立虛擬環境、安裝 dependencies）
24. 未登入狀態無法執行任何匯入、選書、匯出操作
