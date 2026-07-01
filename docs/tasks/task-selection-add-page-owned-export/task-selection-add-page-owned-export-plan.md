# Plan: task-selection-add-page-owned-export

## 實作步驟

### 步驟 1：確認 SQLite JSON1 可用性（決策點）

在開始修改 `export_service.py` 前，先執行以下 Python 片段驗證目前部署環境的 SQLite 是否支援 `json_extract`：

```python
import sqlite3
conn = sqlite3.connect(":memory:")
result = conn.execute("SELECT json_extract('{\"a\":1}', '$.a')").fetchone()
print(result)  # (1,) 表示 JSON1 可用
conn.close()
```

**決策規則**：
- 若 JSON1 可用 → 可在 SQL WHERE 子句使用 `json_extract`，但仍建議在 Python 端做後置過濾（與 `validation_service.py` 一致，更易測試）。
- 若 JSON1 不可用 → 強制使用 Python 端過濾（Plan 預設路徑，見步驟 4）。

**本 Plan 預設路徑**：使用 Python 端過濾，不在 SQL WHERE 加入 `json_extract` 條件。原因：`validation_service.py` 本就在 Python 端解析 `user_overrides`，export 端保持一致，避免 JSON1 版本依賴，且測試更容易 mock。

---

### 步驟 2：`app/services/selection_service.py`

**2-A：擴充 `upsert_selection`**

- 新增 `force_owned: bool = False` 參數（在函式簽章最後、`user_id` 之前）。
- 僅在 `force_owned=True` 且新建記錄（非 existing）時，將 `{"force_owned": True}` merge 進 `user_overrides` 後再 INSERT。
- 若已有既有記錄（`existing` 為 True）：跳過，不更新數量、不覆蓋 overrides，回傳 `{"skipped": True, "vendor_book_id": vendor_book_id}`。

**2-B：新增 `bulk_add_selections`**

```python
def bulk_add_selections(
    project_id: int,
    items: list[dict],   # [{"vendor_book_id": int, "force_owned": bool}, ...]
    user_id: int,
) -> dict:              # {"added": int, "skipped": int}
```

- 對 `items` 逐筆呼叫 `upsert_selection`（quantity=1, notes=None, force_owned 依各 item）。
- 回傳 `added` / `skipped` 計數。
- `vendor_book_id` 不存在（`upsert_selection` 拋 `ValueError`）時，該筆計入 `skipped`，不中止整批。

---

### 步驟 3：`app/routers/selections.py`

新增 endpoint：

```python
class BulkSelectionItem(BaseModel):
    vendor_book_id: int
    force_owned: bool = False

class BulkSelectionRequest(BaseModel):
    project_id: int
    items: list[BulkSelectionItem]

@router.post("/bulk")
async def bulk_update_selection(
    body: BulkSelectionRequest,
    user_id: int = Depends(require_auth),
):
    result = bulk_add_selections(
        body.project_id,
        [i.model_dump() for i in body.items],
        user_id,
    )
    return result
```

- Router import 補上 `bulk_add_selections`。
- 不需要新增錯誤處理（`bulk_add_selections` 內部已吸收個別失敗）。

---

### 步驟 4：`app/services/export_service.py`

**適用函式**：`export_local_culture` 與 `export_general_books`（兩者 SQL 結構相同）。

**變更方式（Python 端過濾）**：

1. 移除現有 SQL WHERE 中的 `IN ('available', 'missing_isbn', 'invalid_isbn')` 條件，改為只過濾 `selected_quantity > 0`（保留 COALESCE match_status 子查詢）。
2. 在 `conn.close()` 後，以 Python list comprehension 過濾：

```python
def _is_force_owned(book: dict) -> bool:
    ov = json.loads(book.get("user_overrides") or "{}")
    return ov.get("force_owned") is True

exportable = [
    dict(b) for b in books
    if b["match_status"] in ("available", "missing_isbn", "invalid_isbn")
    or (b["match_status"] == "already_owned" and _is_force_owned(dict(b)))
]
```

3. 此後 `exportable` 的使用與現行邏輯完全相同，不需其他改動。

**注意**：`_is_force_owned` 是模組層級 helper，與 `_resolve_field`、`_get_price` 同排。

---

### 步驟 5：`app/services/validation_service.py`

**新增 helper**（模組層級，置於 `_resolve` 之後）：

```python
def _is_force_owned(overrides: dict) -> bool:
    return overrides.get("force_owned") is True
```

**修改 `can_export` 判斷**（`check_export_readiness` 內）：

```python
# 修改前
can_export = len(missing_blocking) == 0 and match_status != "already_owned"

# 修改後
can_export = len(missing_blocking) == 0 and (
    match_status != "already_owned" or _is_force_owned(overrides)
)
```

`already_owned_count` 計數器與 `details` 的其他欄位保持不變。

---

### 步驟 6：`app/static/selection.html`

**6-A：PAGE_SIZE**

```js
const PAGE_SIZE = 50;  // 原為 100
```

**6-B：「加入本頁」按鈕**

在 `.filter-bar` 的 `重設篩選` 按鈕之後插入：

```html
<button class="btn btn-secondary btn-sm" id="btn-add-page" onclick="addCurrentPage()">加入本頁</button>
```

**6-C：`addCurrentPage()` 函式**

```js
async function addCurrentPage() {
  const start = (currentPage - 1) * PAGE_SIZE;
  const pageBooks = filteredBooks.slice(start, start + PAGE_SIZE);

  // 只取尚未選取的書目
  const toAdd = pageBooks.filter(b => !selMap[b.id]);
  if (!toAdd.length) { showToast('本頁書目已全部加入清單'); return; }

  // 計算本頁尚未選取的 already_owned 書目數量（需要確認的部分）
  const ownedCount = toAdd.filter(
    b => getEffectiveMatchStatus(b) === 'already_owned'
  ).length;

  if (ownedCount > 0) {
    const ok = confirm(
      `本頁有 ${ownedCount} 本已館藏書目，確認仍要採購並加入選書清單嗎？`
    );
    if (!ok) return;
  }

  const btn = document.getElementById('btn-add-page');
  btn.disabled = true;
  btn.textContent = '處理中…';

  try {
    const items = toAdd.map(b => ({
      vendor_book_id: b.id,
      force_owned: getEffectiveMatchStatus(b) === 'already_owned',
    }));
    const result = await api('/api/selections/bulk', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: pid, items }),
    });
    // 更新本地 selMap（後端加入的書）
    toAdd.forEach(b => { selMap[b.id] = 1; });
    await refreshBudget();
    renderCurrentPage();
    showToast(`已加入 ${result.added} 本，略過 ${result.skipped} 本（已在清單）`);
  } catch (e) {
    showToast('加入失敗：' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '加入本頁';
  }
}
```

**6-D：按鈕 disabled 控制**

在 `applyFilter()` 結尾（`renderCurrentPage()` 之後）加入：

```js
const btnAddPage = document.getElementById('btn-add-page');
if (btnAddPage) btnAddPage.disabled = filteredBooks.length === 0;
```

---

### 步驟 7：新增測試

**`tests/test_selection_add_page.py`**（新建）

使用 in-memory SQLite，直接測試 `bulk_add_selections` service function：

- `test_bulk_add_available_books`：全 available → `added=N, skipped=0`，`user_overrides` 為 None。
- `test_bulk_add_force_owned`：含 already_owned，`force_owned=True` → 加入成功，`user_overrides` 含 `{"force_owned": true}`。
- `test_bulk_add_already_in_list`：已在清單中的書 → `skipped` 計數，不覆蓋既有記錄。
- `test_bulk_add_mixed`：混合 available + already_owned（force_owned=True）+ 已選書 → 各計數正確。
- `test_bulk_add_nonexistent_book`：`vendor_book_id` 不存在 → 計入 skipped，不拋例外。

Fixture 需補欄位：`selection_items` 需含 `user_overrides TEXT`、`match_status_at_selection TEXT`，`vendor_books` 需含 `batch_id`；`import_batches` 需存在（`upsert_selection` 做快照時需要 JOIN）。

**`tests/test_validation_service_owned.py`**（新建）

直接呼叫 `check_export_readiness`，以 in-memory SQLite 模擬：

- `test_force_owned_already_owned_can_export`：`match_status='already_owned'`，`user_overrides='{"force_owned": true}'`，無欄位缺漏 → `can_export=True`。
- `test_unconfirmed_already_owned_cannot_export`：`match_status='already_owned'`，`user_overrides=None` → `can_export=False`。
- `test_available_book_unaffected`：`match_status='available'`，無 force_owned → 依欄位完整度決定 `can_export`。

**`tests/test_export_service_owned.py`**（新建）

測試 `_is_force_owned` helper（import 自 `export_service`）與 Python 端過濾邏輯：

- `test_is_force_owned_true`：`user_overrides='{"force_owned": true}'` → `True`。
- `test_is_force_owned_false`：`user_overrides=None` 或 `'{}'` → `False`。
- `test_exportable_filter_includes_force_owned`：模擬一組 books（available + already_owned with force_owned + already_owned without）→ 只有 available 與 force_owned already_owned 進入 exportable。
- `test_exportable_filter_excludes_unconfirmed_owned`：確認不帶 force_owned 的 already_owned 不出現。

---

## 風險與注意事項

1. **JSON1 / Python 端過濾一致性**：`validation_service.py` 與 `export_service.py` 均在 Python 端解析 `user_overrides`，兩者邏輯須一致。若未來有人在 SQL 層加入 `json_extract`，需同步確認 SQLite 版本（3.38.0+ 預設內建 JSON1）。

2. **前端確認邏輯邊界**：只有「本頁尚未選取且 `match_status === 'already_owned'`」的書需要確認；已選書目（`selMap[b.id]` 有值）在 `toAdd` 過濾時已排除，不會再次觸發確認 dialog。確認一次即涵蓋本頁所有待加入的已館藏書，不需逐本確認。

3. **`upsert_selection` existing 略過**：現行邏輯在 existing 時仍執行 `UPDATE`；本任務改為略過並回傳 skipped 訊號。需確認這不影響既有的單本 `POST /api/selections/` 端點（該端點應維持原本的 upsert 語意，existing 時仍更新數量）。因此 **`upsert_selection` 不應改動 existing 時的行為**；略過邏輯應由 `bulk_add_selections` 在呼叫 `upsert_selection` 前先做 `SELECT` 判斷，而非修改 `upsert_selection` 本身。

4. **`user_overrides` merge 時機**：`upsert_selection` 現行在 INSERT 時傳入 `None` 作為 `user_overrides`（snapshot 的 `user_overrides` 也一起傳，但目前是 `None`）。`force_owned=True` 時，需在呼叫 INSERT 前先將 `{"force_owned": True}` 序列化傳入，不得覆蓋既有 snapshot 中的 `user_overrides`（若 snapshot 本就有值，需 merge）。

5. **來源書單清除後的匯出**：`selection_items` 快照在來源書單清除後仍存在，`user_overrides` 欄位不受影響，Python 端過濾依舊可讀取 `force_owned`，無需額外處理。

6. **測試 fixture 缺欄位**：`conftest.py` 的 `_TEST_SCHEMA` 中 `selection_items` 欄位較少，新測試應各自建立完整 in-memory schema，不依賴 `conftest.py` 的 fixture，以避免 schema 版本耦合。

---

## 預計影響範圍

| 檔案 | 變更性質 |
|---|---|
| `app/static/selection.html` | 修改：PAGE_SIZE、新增按鈕與函式 |
| `app/services/selection_service.py` | 修改：新增 `bulk_add_selections`；`upsert_selection` 加 `force_owned` 參數 |
| `app/routers/selections.py` | 修改：新增 `/bulk` endpoint |
| `app/services/validation_service.py` | 修改：`can_export` 條件、新增 `_is_force_owned` helper |
| `app/services/export_service.py` | 修改：SQL 改為 Python 端過濾、新增 `_is_force_owned` helper |
| `tests/test_selection_add_page.py` | 新建 |
| `tests/test_validation_service_owned.py` | 新建 |
| `tests/test_export_service_owned.py` | 新建 |

**不影響**：匯入流程、範本管理、專案列表、比對流程、館藏查詢、`export-check.html` 前端。

---

## 驗證指令

- lint: 無既有設定，跳過
- format: 無既有設定，跳過
- typecheck: 無既有設定，跳過
- test: `pytest tests/test_selection_add_page.py tests/test_validation_service_owned.py tests/test_export_service_owned.py tests/test_export_service.py -v`
- build: 無需 build（靜態 HTML + FastAPI dev server）

完整回歸：`pytest -v`

---

## 成果報告

- result_report_mode: none
- 適用情境：無需產出成果報告，驗收依 pytest 結果與手測流程確認。
