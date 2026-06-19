# Spec: task-reimport-replace-vendor-books

## 目標

同一 project 重新匯入採購書單（vendor_books）時，以最新一批資料取代舊資料，避免多批次累積。
匯入後 DB 中該 project 的 vendor_books 只剩最新批次，舊的 selection_items、book_matches 一併清除。

## 重要行為說明

**重新匯入採購書單會清空該 project 既有的選書紀錄（selection_items）。**
這是設計上可接受的行為，但必須在文件與回報中明確說明，讓使用者知道重新匯入後需重新進行比對與選書。

## 需求範圍

- `app/services/import_service.py`：
  - 新增 `_clear_vendor_books_for_project(conn, project_id)` helper — 在新批次插入前清除舊資料
  - 修改 `confirm_import`：取得 `conn` 後、INSERT import_batches 前，呼叫 helper
  - 修改 `import_vendor_books`：同上
- 清除順序（避免 FK 問題）：
  1. 查出舊 batch_ids（`import_batches WHERE project_id=? AND batch_type='vendor_books'`）
  2. 若無舊 batch，提前 return（不影響後續流程）
  3. DELETE `selection_items` WHERE project_id=? AND vendor_book_id 屬於舊 vendor_books
  4. DELETE `book_matches` WHERE vendor_book_id 屬於舊 vendor_books
  5. DELETE `vendor_books` WHERE batch_id 屬於舊 batch_ids
  6. DELETE `import_batches` WHERE id 屬於舊 batch_ids

## 不做的事

- 不清除 `library_holdings`（Holdings 不屬於採購書單匯入）
- 不修改 DB schema
- 不修改 API endpoint 或 request/response 格式
- 不修改前端（`selection.html` 已透過 `/api/selections/` 反映 DB 狀態）
- 不提供「保留選書」的 undo 或備份機制（不在本次 MVP 範圍）

## 驗收條件

1. `python -m compileall app` 無錯誤
2. 重新匯入 `00_source/本土書單.xlsx` 後，DB 中該 project 的 vendor_books 只剩最新一批 670 筆
3. `purchase_price IS NOT NULL` = 670 / 670
4. 舊批次的 import_batches、vendor_books、book_matches、selection_items 均已清除
5. 沒有 FK constraint 錯誤或未預期例外
6. 重跑比對後，`/selection.html` 顯示採購價（第一筆 525、第二筆 263 左右）
