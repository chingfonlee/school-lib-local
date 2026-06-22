# Plan: task-test-foundation-core-services

## 實作步驟

### 步驟 0：盤點現有狀態（已確認）

- `requirements.txt`：無 pytest，需新增
- `tests/` 目錄：不存在
- `pytest.ini` / `pyproject.toml`：不存在
- `completeness_service.compute()`：純函式，無 DB，直接 import 即可測試
- import profile project_type 決策：嵌在 `app/routers/imports.py` L72–75，需先抽成 helper

---

### 步驟 1：新增 pytest dependency

> **⚠️ 需使用者確認後才執行**

**問題**：`pytest` 不在 `requirements.txt`，無法執行 `python -m pytest`。

**建議做法（二擇一，請使用者確認）：**

**選項 A：直接加入 requirements.txt**

```
pytest>=8.0
```

- 優點：所有環境一致，`start.bat` 啟動時自動安裝，不需管理多份 requirements
- 缺點：生產環境也會安裝測試框架（本專案為本地工具，影響有限）

**選項 B：建立 requirements-dev.txt**

```
pytest>=8.0
```

執行測試前需另外執行：`pip install -r requirements-dev.txt`

- 優點：明確區分 dev / prod 依賴
- 缺點：需要額外步驟，`start.bat` 不自動安裝

**建議：選項 A**（本專案為本地工具，不存在生產環境最小化問題；維護成本較低）。

**等待使用者確認後，才執行此步驟。**

---

### 步驟 2：建立 tests/ 目錄與 conftest

1. 建立 `tests/` 目錄
2. 建立 `tests/__init__.py`（空檔，讓 pytest 正確識別為 package）

---

### 步驟 3：抽取 `_resolve_project_type()` helper

**修改 `app/routers/imports.py`：**

在 `confirm_vendor_books()` 之前，新增：

```python
def _resolve_project_type(conn, project_id: int) -> str:
    row = conn.execute(
        "SELECT project_type FROM procurement_projects WHERE id = ?", (project_id,)
    ).fetchone()
    return row["project_type"] if row else "local_culture"
```

**更新 `confirm_vendor_books()` L72–75：**

原本：
```python
proj_row = conn.execute(
    "SELECT project_type FROM procurement_projects WHERE id = ?", (project_id,)
).fetchone()
proj_type = proj_row["project_type"] if proj_row else "local_culture"
```

改為：
```python
proj_type = _resolve_project_type(conn, project_id)
```

業務行為不變，僅封裝為可獨立測試的函式。

---

### 步驟 4：撰寫 `tests/test_completeness_service.py`

覆蓋 `compute()` 的所有分支：

**local_culture 分支（project_type=None 或未指定）**

| 情境 | 欄位 | 預期狀態 |
|------|------|---------|
| 缺 title | 無 title | `missing_required` |
| 缺 price（list 與 purchase 均無） | 無 list_price / purchase_price | `missing_required` |
| 缺 award_item | 有 title/price/author/publisher，無 award_item | `needs_review` |
| 缺 author | 有 title/price/award_item，無 author | `needs_review` |
| 全欄完整 | 全部有值 | `export_ready` |

**general_books 分支（project_type="general_books"）**

| 情境 | 欄位 | 預期狀態 |
|------|------|---------|
| 缺 eligibility_label | 無 eligibility_label | `missing_required` |
| 缺 recommendation_source | 無 recommendation_source | `missing_required` |
| 缺 author | 有 eligibility/recommendation，無 author | `needs_review` |
| 全欄完整 | 全部有值 | `export_ready` |

**overrides 影響**

| 情境 | 說明 | 預期狀態 |
|------|------|---------|
| override 補足 award_item | book 無 award_item，override 有 → local_culture 可 export_ready | `export_ready` |
| override 空字串不生效 | override award_item="" → 視為無值 | `needs_review` |

---

### 步驟 5：撰寫 `tests/test_import_profile_project_type.py`

使用 Python 標準庫 `sqlite3` 建立 in-memory DB，不依賴 `app.database`：

```python
import sqlite3
import pytest
from app.routers.imports import _resolve_project_type

@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute(
        "CREATE TABLE procurement_projects "
        "(id INTEGER PRIMARY KEY, project_type TEXT NOT NULL)"
    )
    c.execute("INSERT INTO procurement_projects VALUES (1, 'general_books')")
    c.execute("INSERT INTO procurement_projects VALUES (2, 'local_culture')")
    c.commit()
    yield c
    c.close()
```

**測試情境：**

| 情境 | project_id | 預期回傳 |
|------|-----------|---------|
| general_books | 1 | `"general_books"` |
| local_culture | 2 | `"local_culture"` |
| 查無 project | 999 | `"local_culture"` |

---

### 步驟 6：驗證

```
python -m compileall app
python -m pytest -v
```

- `compileall`：確認 helper 抽取後 app 仍可編譯
- `pytest -v`：確認所有測試通過，0 failures

---

### 步驟 7：Commit

```
chore(task-test-foundation-core-services): add core service tests
```

涵蓋：`app/routers/imports.py`（helper 抽取）、`tests/` 目錄、兩份測試檔案、`requirements.txt`（或 requirements-dev.txt，依確認結果）。

---

## 風險與注意事項

**pytest dependency 確認前不可執行步驟 1**

步驟 1 為 prerequisites，需等使用者確認選項 A 或 B 才能繼續。若使用者跳過確認，不得自行假設。

**`_resolve_project_type` 抽取範圍限制**

僅抽取 L72–75 的 project_type 決策，不動 INSERT 邏輯或其他 router 行為。抽取後 `confirm_vendor_books()` 行為完全不變。

**in-memory DB 不依賴 app.database**

測試直接使用 `sqlite3.connect(":memory:")`，不呼叫 `get_connection()`，不需要實際資料庫檔案，不干擾 `data/school_lib.db`。

**不引入 httpx / TestClient**

import router 的完整測試（包含 FastAPI TestClient）成本較高，本 task 不實作，留待後續 task。

---

## 預計影響範圍

| 路徑 | 說明 |
|------|------|
| `requirements.txt` 或 `requirements-dev.txt` | 新增 pytest（待確認） |
| `app/routers/imports.py` | 抽取 `_resolve_project_type()` helper（2 行邏輯封裝，業務行為不變） |
| `tests/__init__.py` | 新增（空檔） |
| `tests/test_completeness_service.py` | 新增 |
| `tests/test_import_profile_project_type.py` | 新增 |

不影響：`app/services/`（不修改）、`app/static/`、`migrations/`、其他 router。

---

## 驗證指令

```
python -m compileall app
python -m pytest -v
```

## 成果報告

- result_report_mode: none
