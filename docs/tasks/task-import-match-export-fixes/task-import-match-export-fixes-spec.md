# Spec: task-import-match-export-fixes

## 目標

在專案核心業務服務（匯入、ISBN 正規化、館藏比對、選書快照、匯出檢核與 Excel 匯出）中存在多處會直接導致資料遺失、匯出格式損壞或比對錯漏的缺陷，包含：無範例列時匯出清空標題列、備註覆寫未寫入 Excel、國中一般圖書（`general_books_jh`）完整度誤用本土文化規則、ISBN-10 末碼 `X` 被拒且 10/13 碼無法互通、匯入零筆資料仍清空舊書單、以及重匯廠商書單後脫鉤選書快照不隨館藏更新同步比對狀態。

本 task 系統性修復上述核心業務邏輯缺陷，並補齊相關服務的交易安全與自動化回歸測試。

## 需求範圍

1. **ISBN 正規化與 10/13 碼互通（`app/services/isbn_service.py`）**
   - 先使用 `unicodedata.normalize("NFKC", ...)` 將全形數字與全形符號轉為半形，避免全形數字誤過驗證但比對失敗。
   - 安全處理 `float("nan")` 與 `float("inf")`（回傳 `None`／`missing`，不拋 `ValueError`）。
   - 支援合法 ISBN-10（允許末碼 `X` / `x`），並統一轉換為 13 碼 ISBN-13（補前綴 `978` 並重算第 13 位 EAN 檢核碼），使館藏 10 碼與書商 13 碼可直接比對。

2. **完整度計算與選書快照同步（`app/services/completeness_service.py`、`app/services/selection_service.py`）**
   - `completeness_service.compute()` 將一般圖書判斷由 `project_type == "general_books"` 擴充為 `project_type in ("general_books", "general_books_jh")`。
   - `selection_service.upsert_selection()` 建立選書快照時繼承 `vendor_books.user_overrides`；若 `force_owned=True` 則與既有覆寫合併（不丟失先前在比對頁修正的欄位）。
   - `selection_service.update_selection_overrides()` 更新 `selection_items.user_overrides` 後，同步依專案 `project_type` 重算並寫回 `selection_items.completeness_status`。
   - `selection_service.bulk_add_selections()` 新增成功後即時將 `vendor_book_id` 加入 `existing_ids`，避免同一請求內重複 ID 重複寫入。
   - `completeness_service.py` 與 `selection_service.py` 改用 `db_session(get_connection)` 確保連線釋放。

3. **匯入交易安全與零筆防清空（`app/services/import_service.py`）**
   - `confirm_import()` 與 `import_vendor_books()` 改用 `db_session(get_connection)`，並於讀取、解析完 Excel 後再開啟 DB 交易；發生例外時自動 rollback 保留既有資料。
   - 若 `records_inserted == 0`，主動 `raise ValueError("未解析到任何有效書目資料，已保留原有書單")`，觸發 rollback，不再清空既有廠商書單。
   - `_to_float()` 檢查 `math.isfinite()`，拒絕 `NaN` / `inf` 寫入資料庫。

4. **館藏比對與脫鉤選書快照狀態同步（`app/services/match_service.py`、`app/services/validation_service.py`、`app/services/export_service.py`）**
   - `match_service.run_match()` 改用 `db_session(get_connection)`。
   - `validation_service.check_export_readiness()` 與 `export_service`（本土文化與一般圖書）在解析每筆選書的比對狀態時：若該筆 `vendor_book_id` 在 `book_matches` 查無紀錄（例如重匯書商書單後已脫鉤的快照），且 `si.isbn_normalized` 存在於目前 `library_holdings.isbn_normalized`，則即時判定為 `already_owned`，避免誤購已入館藏書目。

5. **匯出檢核與 Excel 匯出一致性及防呆（`app/services/export_service.py`、`app/services/validation_service.py`）**
   - **不誤清標題列**：`export_local_culture()` 與 `export_general_books()` 僅在 `example_row > tmpl["header_row"]` 時才清空範例列。
   - **備註覆寫一致**：兩支匯出函式的備註欄改用 `_resolve_field(book, "notes") or None`，確保 `user_overrides["notes"]` 正確寫入 Excel。
   - **價格與小計一致**：`_get_price()` 改以 `not in (None, "")` 判斷覆寫值（避免覆寫 `0` 誤退回原價）；`export_general_books()` 依 `settings.subtotal_mode` 計算小計；`validation_service` 檢核價格須為 `> 0` 的有效數值（`0` 不視為有效價格），且同時為 `already_owned` 又缺必填欄位時亦正確計入 `missing_required`。
   - **範本與檔案防呆**：匯出前檢查範本檔案存在與必要 `column_mappings` 鍵值齊全（缺漏時拋出清楚中文 `ValueError` 回 400）；`school_name_cell` 非空才寫入；寫入過程發生例外時清理半成品 `out_path`；輸出檔名加入短隨機碼避免同秒碰撞；DB 呼叫改用 `db_session(get_connection)`。

## 不做的事

- 不修改前端 HTML/JS 頁面（排入第 2 批）。
- 不重構合併 `confirm_import()` 與 `import_vendor_books()` 的整體結構，亦不重寫 `iterrows()` 為 `executemany`（排入第 3 批）。
- 不新增資料庫 migration 或變更既有 schema。
- 不變更既有合法 13 碼 ISBN 的正規化結果。

## 驗收條件

1. `normalize_isbn()` 正確處理全形數字、`float('nan')`、ISBN-10 末碼 `X`/`x`，並將合法 ISBN-10 轉為正確的 ISBN-13。
2. `completeness_service.compute(..., project_type="general_books_jh")` 依一般圖書規則檢查 `eligibility_label` 與 `recommendation_source`。
3. `upsert_selection()` 繼承 `vendor_books.user_overrides`（並與 `force_owned` 正確合併）；`update_selection_overrides()` 同步更新 `selection_items.completeness_status`；`bulk_add_selections()` 去重同一請求內的重複 ID。
4. `confirm_import()` 遇到零筆有效列時拋出 `ValueError` 並保留原本已匯入的廠商書單；`_to_float("nan")` 回傳 `None`。
5. 脫鉤的選書快照（`vendor_book_id` 不在 `book_matches`）在 `library_holdings` 新增相同 ISBN 後，`check_export_readiness()` 與匯出均能即時辨識為 `already_owned`。
6. 無範例列的範本匯出時標題列完整保留；`user_overrides["notes"]` 正確寫入 Excel；範本缺檔或缺欄時回傳 `ValueError` 且不留半成品檔案；`0` 元書在檢核被標記缺定價。
7. 驗證指令（`compileall`、`ruff check`、`ruff format --check`、`mypy`、`pytest -q`）全數通過。
