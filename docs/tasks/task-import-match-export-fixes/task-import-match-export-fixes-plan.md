# Plan: task-import-match-export-fixes

## 實作步驟

1. **修復 `app/services/isbn_service.py`**
   - 處理 `float` 時先檢查 `math.isnan(raw) or math.isinf(raw)` 回傳 `None`（`get_isbn_status` 回傳 `"missing"`）。
   - 使用 `unicodedata.normalize("NFKC", raw)` 轉半形後去除空白、控制字元與連字號。
   - 支援 10 碼 ISBN（前 9 碼為 ASCII 數字，第 10 碼為數字或 `X`/`x`），新增 `_isbn10_to_isbn13()` 補 `978` 並計算 EAN-13 檢核碼回傳 13 碼；13 碼須全為 ASCII 數字。

2. **修復 `app/services/completeness_service.py` 與 `app/services/selection_service.py`**
   - `completeness_service.py`：第 30 行改為 `if project_type in ("general_books", "general_books_jh"):`；`recompute_for_book()` 改用 `db_session(get_connection)`。
   - `selection_service.py`：
     - 所有函式改用 `db_session(get_connection)`。
     - `upsert_selection()` 建立快照時解析 `snap.get("user_overrides")`，若 `force_owned=True` 則設定 `overrides["force_owned"] = True` 後存回 `selection_items.user_overrides`。
     - `update_selection_overrides()` 查詢該筆 `selection_items` 與專案 `project_type`，更新 `user_overrides` 同時重算並更新 `completeness_status`。
     - `bulk_add_selections()` 成功新增後執行 `existing_ids.add(vbid)`。

3. **加固 `app/services/import_service.py`**
   - `_to_float()` 加入 `math.isfinite(val)` 檢查。
   - `confirm_import()` 與 `import_vendor_books()` 改為先完成 Excel 讀取，再以 `with db_session(get_connection) as conn:` 執行清除與寫入；若 `records_inserted == 0` 拋出 `ValueError("未解析到任何有效書目資料，已保留原有書單")` 觸發 rollback。

4. **修復 `app/services/match_service.py` 與 `app/services/validation_service.py`**
   - `match_service.run_match()` 改用 `db_session(get_connection)`。
   - `validation_service.check_export_readiness()`：
     - 改用 `db_session(get_connection)`。
     - SQL 中當 `book_matches` 查無結果時，透過 `EXISTS (SELECT 1 FROM library_holdings lh WHERE lh.isbn_normalized = si.isbn_normalized)` 即時辨識脫鉤快照是否已入館藏（優先於舊的 `match_status_at_selection`）。
     - 價格檢核改用 `_resolve_positive_float()`，將 `0` 或非正數視為缺定價。
     - `missing_required_count` 改為只要 `len(missing_blocking) > 0` 即計入（不因同時 `already_owned` 而漏計）。

5. **修復 `app/services/export_service.py`**
   - 新增 `_validate_export_template(tmpl, col_map, required_keys)`：驗證範本檔案存在與必要欄位鍵值齊全，否則拋出清楚中文 `ValueError`。
   - 兩支匯出函式改用 `db_session(get_connection)`；輸出檔名加入 `uuid.uuid4().hex[:6]` 避免同秒碰撞；複製並寫入失敗時在 `except` 刪除半成品 `out_path`。
   - 清空範例列條件改為 `if example_row > tmpl["header_row"]:`（避免無範例列時清空標題列）；`school_name_cell` 非空才寫入。
   - 備註欄改用 `_resolve_field(book, "notes") or None`；`_get_price()` 改判斷 `overrides.get(price_field) not in (None, "")`；`export_general_books()` 依 `settings.subtotal_mode` 計算小計。
   - 查詢選書 SQL 比照 `validation_service` 補上脫鉤快照即時比對 `library_holdings`。

6. **新增回歸測試並執行完整驗證**
   - 新增 `tests/test_import_match_export_fixes.py`，逐項覆蓋 spec 的 6 項功能驗收條件。
   - 更新 `.github/workflows/ci.yml` 的 `mypy` 目標清單（可視相容性納入 `isbn_service.py`、`completeness_service.py`、`match_service.py`、`validation_service.py`）。
   - 執行下方完整驗證指令確保全數 pass。

## 風險與注意事項

- **ISBN-10 轉 ISBN-13 與既有測試相容性**：需確認現有 `tests/` 中是否有直接斷言 10 碼原樣回傳的測試；若有，依 spec 檢查預期行為並確認不破壞既有測試。
- **`validation_service` 與 `export_service` 脫鉤快照比對**：只針對 `si.isbn_normalized IS NOT NULL AND si.isbn_normalized != ''` 查詢 `library_holdings`，避免無 ISBN 書目誤判；且受惠於 Task 1A 已建立的 `idx_library_holdings_isbn_normalized` 索引，查詢成本極低。
- **`export_service` 必要欄位驗證**：需與 `app/routers/admin.py` 的 `REQUIRED_FIELDS` 保持一致，避免誤擋既有合法範本（特別是測試用的精簡範本）。

## 預計影響範圍

| 路徑 | 說明 |
|---|---|
| `app/services/isbn_service.py` | NFKC 半形化、NaN/inf 防護、ISBN-10 末碼 `X` 與轉 ISBN-13 |
| `app/services/completeness_service.py` | 補齊 `general_books_jh` 判斷與 `db_session` |
| `app/services/selection_service.py` | 繼承 `user_overrides`、覆寫重算完整度、批次去重與 `db_session` |
| `app/services/import_service.py` | 交易保護、零筆防清空、`_to_float` 拒絕 NaN/inf |
| `app/services/match_service.py` | 改用 `db_session` |
| `app/services/validation_service.py` | 脫鉤快照即時館藏比對、0 元價檢核、`missing_required` 計數與 `db_session` |
| `app/services/export_service.py` | 防清標題列、備註覆寫、0 元價與 `subtotal_mode`、範本防呆與清理半成品、脫鉤快照比對 |
| `tests/test_import_match_export_fixes.py`（新增） | 本次修復完整回歸測試 |

## 驗證指令

- lint: `.venv\Scripts\python.exe -m ruff check app tests`
- format: `.venv\Scripts\python.exe -m ruff format --check app/services/isbn_service.py app/services/completeness_service.py app/services/selection_service.py app/services/import_service.py app/services/match_service.py app/services/validation_service.py app/services/export_service.py tests/test_import_match_export_fixes.py`
- typecheck: `.venv\Scripts\python.exe -m mypy app/logging_config.py app/database.py app/main.py app/routers/backup.py app/routers/projects.py app/services/isbn_service.py app/services/completeness_service.py app/services/match_service.py app/services/validation_service.py`
- test: `.venv\Scripts\python.exe -m pytest -q`
- build: `.venv\Scripts\python.exe -m compileall -q app`

## 成果報告

- result_report_mode: none
- 適用情境：無（以 spec 驗收條件與測試結果為準）
- 報告路徑（若 mode 非 none）：`docs/reports/task-import-match-export-fixes/`
