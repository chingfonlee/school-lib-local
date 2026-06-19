# Plan: task-reimport-replace-vendor-books

## 實作步驟

### 1. 新增 `_clear_vendor_books_for_project(conn, project_id)` helper

位置：`app/services/import_service.py`，緊接在 `_build_formula_fallback` 之後。

```python
def _clear_vendor_books_for_project(conn, project_id: int) -> None:
    """
    Delete all vendor_books-related data for a project before re-import.
    Order: selection_items → book_matches → vendor_books → import_batches
    """
    old_batch_ids = [
        r[0] for r in conn.execute(
            "SELECT id FROM import_batches WHERE project_id=? AND batch_type='vendor_books'",
            (project_id,),
        ).fetchall()
    ]
    if not old_batch_ids:
        return

    ph = ",".join("?" * len(old_batch_ids))

    conn.execute(
        f"DELETE FROM selection_items WHERE project_id=? AND vendor_book_id IN "
        f"(SELECT id FROM vendor_books WHERE batch_id IN ({ph}))",
        [project_id] + old_batch_ids,
    )
    conn.execute(
        f"DELETE FROM book_matches WHERE vendor_book_id IN "
        f"(SELECT id FROM vendor_books WHERE batch_id IN ({ph}))",
        old_batch_ids,
    )
    conn.execute(
        f"DELETE FROM vendor_books WHERE batch_id IN ({ph})",
        old_batch_ids,
    )
    conn.execute(
        f"DELETE FROM import_batches WHERE id IN ({ph})",
        old_batch_ids,
    )
```

### 2. 修改 `confirm_import`

在 `conn = get_connection()` 之後、INSERT import_batches 之前，插入：

```python
_clear_vendor_books_for_project(conn, project_id)
```

### 3. 修改 `import_vendor_books`

同樣在 `conn = get_connection()` 之後、INSERT import_batches 之前，插入：

```python
_clear_vendor_books_for_project(conn, project_id)
```

## 風險與注意事項

- **選書清空為不可逆操作**：helper 在 `conn.commit()` 前執行，但若後續 INSERT 失敗，SQLite 會 rollback，選書資料得以保留；正常成功路徑下選書會被清除，不可恢復
- **大量刪除效能**：本土書單約 670 筆，SELECT / DELETE 均走 batch_id / vendor_book_id index，效能可接受
- **FK 順序**：SQLite 預設不強制 FK，但仍依照邏輯順序刪除（selection_items → book_matches → vendor_books → import_batches）避免語義錯誤
- **subquery IN**：使用 `DELETE ... WHERE ... IN (SELECT ...)` 取代二次 Python fetch，SQL 層面完成，原子性更佳
- **`batch_type='vendor_books'` 過濾**：確保不誤刪 library_holdings 相關批次（若未來新增其他 batch_type 亦安全）

## 預計影響範圍

- `app/services/import_service.py`：新增 1 個 helper，修改 `confirm_import` 與 `import_vendor_books` 各 1 行
- 不影響其他 Python 檔案、DB schema、API 規格或前端

## 驗證指令

- lint: 無
- format: 無
- typecheck: 無
- test: 無
- build: `python -m compileall app`

## 成果報告

- result_report_mode: none
- 適用情境：不需
- 報告路徑（若 mode 非 none）：無
