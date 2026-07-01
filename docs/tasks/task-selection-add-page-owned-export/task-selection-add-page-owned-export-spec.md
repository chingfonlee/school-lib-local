# Spec: task-selection-add-page-owned-export

## 目標

在選書頁新增「加入本頁」功能，讓教師能一次將當前頁面所有未選書目加入採購清單。當本頁含有 `already_owned`（已館藏）書目時，系統需提醒教師並取得確認；教師明確確認後，這些已館藏書目以「已館藏仍採購」狀態加入選購清單，後續匯出前檢查與 Excel 匯出均可辨識並允許匯出。未經教師確認的 `already_owned` 書目，匯出行為維持現狀（不可匯出）。

---

## 需求範圍

### 1. 前端 UX（`app/static/selection.html`）

**PAGE_SIZE 調整**
- `PAGE_SIZE` 由 100 改為 50。

**「加入本頁」按鈕**
- 位置：篩選列（`.filter-bar`）右側，緊鄰現有「重設篩選」按鈕後方，與分頁控制區上方同排。
- 按鈕文字：「加入本頁」。
- 初始狀態：可點擊；若 `filteredBooks` 為空（頁面無書目）則 disabled。
- 按下後：立即 disabled 並顯示「處理中…」，防止重複點擊。

**已館藏確認 dialog**
- 觸發條件：本頁（`currentPage` 對應的 `filteredBooks` 切片）含有 `match_status === 'already_owned'` 且尚未加入選購清單（`selMap[b.id]` 不存在）的書目。
- 確認文案：`「本頁有 {N} 本已館藏書目，確認仍要採購並加入選書清單嗎？」`
- 使用者確認 → 本頁所有未選書目（含已館藏）送出加入請求。
- 使用者取消 → 整批加入動作中止，不做任何加入；按鈕恢復可點擊。

**略過邏輯**
- 已在選購清單中的書目（`selMap[b.id]` 有值）跳過，不重複加入、不覆蓋既有數量。

**完成後行為**
- 顯示 toast：`「已加入 {added} 本，略過 {skipped} 本（已在清單）」`。
- 刷新預算列（`refreshBudget()`）與卡片狀態（重新 render 當頁）。

**已館藏仍採購的視覺提示**
- 「已館藏仍採購」的 selection_items 在選書頁卡片上以「已加入（含館藏）」或原本「已加入」顯示即可，不新增額外 badge；UI 簡潔優先。

### 2. API 設計

**新增批次加入 endpoint**
- `POST /api/selections/bulk`
- Request body：
  ```json
  {
    "project_id": 1,
    "items": [
      { "vendor_book_id": 42, "force_owned": false },
      { "vendor_book_id": 57, "force_owned": true }
    ]
  }
  ```
  - `force_owned: true`：教師已確認「已館藏仍採購」。
  - `force_owned: false`（預設）：一般可採購書目。
- 已在清單中的書目（`UNIQUE(project_id, vendor_book_id)` 衝突）自動略過，不報錯。
- Response：
  ```json
  { "added": 3, "skipped": 2 }
  ```
- 錯誤處理：單本 `vendor_book_id` 不存在時略過該筆，不中止整批；無任何成功加入時回傳 `{ "added": 0, "skipped": N }`。

**後端 `upsert_selection` 擴充（`selection_service.py`）**
- 新增 `force_owned: bool = False` 參數。
- 若 `force_owned=True`，在寫入 `selection_items` 時同步將 `user_overrides` 設定（或 merge）`{"force_owned": true}`。
- 若 `vendor_book_id` 已在清單中（`existing` 為 True），略過（不更新數量、不覆蓋 overrides），直接回傳略過訊號。

### 3. 資料模型

**不新增 schema migration**

利用 `selection_items.user_overrides`（TEXT/JSON）欄位儲存 `{"force_owned": true}`，識別「已館藏仍採購」的選書記錄。

- `user_overrides` 中有 `force_owned: true` → 已確認已館藏仍採購。
- `user_overrides` 中無此鍵或值為 `false` → 一般 available 書目（或未確認的 already_owned，不可匯出）。

### 4. 匯出前檢查（`app/services/validation_service.py`）

`check_export_readiness` 邏輯調整：

```
can_export = (
    len(missing_blocking) == 0
    and (
        match_status != "already_owned"
        or _is_force_owned(overrides)
    )
)
```

- `_is_force_owned(overrides)` → `overrides.get("force_owned") is True`。
- 未確認的 `already_owned`（無 `force_owned: true`）維持不可匯出；`already_owned_count` 計數器保留，供前端顯示。
- `details` 回傳的每筆資料不新增 `force_owned` 欄位（可從 `can_export` 與 `match_status` 推導，避免 schema 擴散）。

### 5. 匯出服務（`app/services/export_service.py`）

`export_local_culture` 與 `export_general_books` 的查詢 SQL 調整 `IN` 條件：

```sql
COALESCE(...) IN ('available', 'missing_isbn', 'invalid_isbn')
  OR (
    COALESCE(...) = 'already_owned'
    AND json_extract(si.user_overrides, '$.force_owned') = 1
  )
```

- 僅 `force_owned = true` 的 `already_owned` 書目被納入匯出；一般 `already_owned` 仍排除。
- `selection_items` 的快照欄位（`match_status_at_selection`、`user_overrides`）在來源書單清除後仍可作為匯出判斷依據。

### 6. 測試

**後端（`tests/test_selection_add_page.py`）**

- 批次加入全部為 `available` 書目 → 全數加入，`added = N`。
- 批次加入含 `already_owned`，`force_owned=True` → 加入成功，`user_overrides` 含 `{"force_owned": true}`。
- 批次加入含 `already_owned`，`force_owned=False` → 加入成功，但 `user_overrides` 不含 `force_owned`。
- 批次加入時，已在清單中的書目被略過（`skipped` 計數正確）。

**後端（`tests/test_validation_service_owned.py`）**

- `force_owned=true` 的 `already_owned` selection_item，`check_export_readiness` 中 `can_export=True`。
- 未帶 `force_owned` 的 `already_owned` selection_item，`can_export=False`。
- 一般 `available` selection_item 不受影響（`can_export` 依欄位完整度決定）。

**後端（`tests/test_export_service_owned.py`）**

- `export_local_culture` 的 SQL 條件：帶 `force_owned=true` 的 `already_owned` 書目出現在 `exportable` 清單；不帶的 `already_owned` 不出現。
- `export_general_books` 同上。

**前端手測流程**

1. 建立含 available 與 already_owned 書目的一般圖書專案。
2. 確認選書頁每頁顯示 50 本（`PAGE_SIZE = 50`）。
3. 點「加入本頁」，本頁只有 available 書目 → 直接加入，toast 顯示正確數字。
4. 切換頁面到含 already_owned 的頁 → 點「加入本頁」→ 看到確認 dialog，顯示已館藏數量。
5. 取消 → 無任何書目加入。
6. 再點「加入本頁」→ 確認 → 加入成功，toast 顯示加入數與略過數。
7. 前往「匯出前檢查」，確認已確認仍採購的已館藏書可通過（`can_export=true`）。
8. 匯出 Excel，確認該書出現在輸出檔案中。

---

## 不做的事

- 不新增資料庫 migration（利用既有 `user_overrides` JSON 欄位）。
- 不讓所有 `already_owned` 自動可匯出；只有帶 `force_owned: true` 的才允許。
- 不重構整個選書頁；不動篩選、排序、覆蓋資料等現有邏輯。
- 不修改匯入、範本管理、專案列表功能。
- 不在 `details` response 新增 `force_owned` 欄位。
- 不新增「已館藏仍採購」專屬 badge 或視覺樣式。

---

## 驗收條件

1. 選書頁 `PAGE_SIZE = 50`，分頁正常運作。
2. 「加入本頁」按鈕顯示；`filteredBooks` 為空時 disabled。
3. 本頁含未選的 `already_owned` → 點「加入本頁」出現確認 dialog，文案含已館藏數量。
4. 取消 dialog → 無任何書目加入。
5. 確認 dialog → 本頁未選書目（含已館藏）加入；已在清單者被略過；toast 顯示正確數字。
6. 加入後 `selection_items` 中 already_owned 書目的 `user_overrides` 包含 `{"force_owned": true}`。
7. `check_export_readiness`：帶 `force_owned=true` 的 already_owned 書目 `can_export=true`；不帶的 `can_export=false`。
8. `export_local_culture` / `export_general_books`：帶 `force_owned=true` 的 already_owned 書目出現在匯出 Excel；不帶的不出現。
9. 既有 available 書目的匯出行為不受影響。
10. `pytest` 全部通過（含新增測試）。
