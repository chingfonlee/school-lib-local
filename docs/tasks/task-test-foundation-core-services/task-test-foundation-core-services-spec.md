# Spec: task-test-foundation-core-services

## 目前問題

核心邏輯（completeness_service 分支判斷、import profile project_type 決策）目前全靠手動瀏覽器驗證，缺乏自動化安全網。任何修改都可能在不知情的情況下造成回歸。

## 測試目標

建立最小可維護的自動化測試基礎，優先覆蓋最容易回歸、不需要瀏覽器即可驗證的核心邏輯。

## 測試範圍

### 1. `app/services/completeness_service.py` — `compute()` 函式

`compute()` 是純函式（無 DB 相依），可直接測試：

**local_culture 分支（`project_type` 為 None 或非 general_books）：**
- 缺 title 或 price → `missing_required`
- 有 title、price，缺 author/publisher/award_item → `needs_review`
- 有 title、price、author、publisher、award_item → `export_ready`

**general_books 分支（`project_type == "general_books"`）：**
- 缺 eligibility_label 或 recommendation_source → `missing_required`
- 有 eligibility_label、recommendation_source，缺 author/publisher → `needs_review`
- 有全部必填欄位 → `export_ready`

**overrides 對狀態判斷的影響：**
- overrides 補足缺漏欄位，狀態由 `needs_review` 升至 `export_ready`
- overrides 中空字串不應被視為有效值

### 2. import profile `project_type` 決策邏輯

`app/routers/imports.py` 的 `confirm_vendor_books()` 中（L72–75）：

```python
proj_row = conn.execute(...).fetchone()
proj_type = proj_row["project_type"] if proj_row else "local_culture"
```

此決策邏輯嵌在 router 內，測試 router 需要 FastAPI TestClient + 完整 DB + 檔案上傳，成本較高。

**計畫**：將此 2 行邏輯抽成小 helper `_resolve_project_type(conn, project_id) -> str`，放置於同一 router 檔案內，不改動業務行為。Helper 可用 in-memory SQLite 測試：

- 傳入已知 general_books project_id → 回傳 `"general_books"`
- 傳入已知 local_culture project_id → 回傳 `"local_culture"`
- 傳入查無對應的 project_id → 降級回傳 `"local_culture"`

## 不做的事

- 不做 Playwright / 瀏覽器 E2E 測試
- 不測整個 Excel 匯入流程（import_service.py 的完整 IO 路徑）
- 不建立大型 fixture 系統
- 不引入 coverage、tox、nox、CI 等額外工具
- 不重構 app 業務架構
- 不修改業務行為

## 驗收條件

1. `python -m pytest` 執行通過，0 failures
2. 測試覆蓋 `compute()` 的 local_culture 分支（3 個狀態）、general_books 分支（3 個狀態）、overrides 影響（至少 2 個 case）
3. 測試覆蓋 `_resolve_project_type()` 的 3 個情境（general_books、local_culture、查無）
4. `python -m compileall app` 執行通過
5. 不修改 `compute()` 的業務邏輯，`_resolve_project_type()` 抽取後 `confirm_vendor_books()` 行為不變
6. 不引入 coverage、tox、nox 等額外工具
