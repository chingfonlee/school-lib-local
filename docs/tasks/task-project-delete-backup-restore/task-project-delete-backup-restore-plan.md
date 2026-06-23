# Plan：task-project-delete-backup-restore

- task-id: task-project-delete-backup-restore
- type: feat
- base branch: main
- status: planning

---

## 實作步驟總覽

| 步驟 | 說明 | 影響檔案 |
|------|------|---------|
| Step 1 | 新增 delete-preview 與 DELETE API | `app/routers/projects.py` |
| Step 2 | 新增 backup router（備份 + 還原）| `app/routers/backup.py`（新增） |
| Step 3 | 在 main.py 註冊 backup router | `app/main.py` |
| Step 4 | projects.html：刪除按鈕 + 確認 Modal | `app/static/projects.html` |
| Step 5 | projects.html：備份 + 還原 UI | `app/static/projects.html` |
| Step 6 | 新增 tests（delete API、backup API）| `tests/test_project_delete.py`（新增） |

---

## Step 1：`app/routers/projects.py`

### 1-A：delete-preview API

```python
@router.get("/{project_id}/delete-preview")
async def delete_preview(project_id: int, user_id: int = Depends(require_auth)):
    conn = get_connection()
    project = conn.execute(
        "SELECT id, name FROM procurement_projects WHERE id = ?", (project_id,)
    ).fetchone()
    if project is None:
        conn.close()
        raise HTTPException(status_code=404, detail="找不到專案")

    selection_count = conn.execute(
        "SELECT COUNT(*) FROM selection_items WHERE project_id = ?", (project_id,)
    ).fetchone()[0]

    export_job_count = conn.execute(
        "SELECT COUNT(*) FROM export_jobs WHERE project_id = ?", (project_id,)
    ).fetchone()[0]

    import_batch_count = conn.execute(
        "SELECT COUNT(*) FROM import_batches WHERE project_id = ?", (project_id,)
    ).fetchone()[0]

    # 透過 import_batches 計算 vendor_books 與 library_holdings 數量
    batch_ids = [
        r[0] for r in conn.execute(
            "SELECT id FROM import_batches WHERE project_id = ?", (project_id,)
        ).fetchall()
    ]
    vendor_book_count = 0
    holding_count = 0
    if batch_ids:
        placeholders = ",".join("?" * len(batch_ids))
        vendor_book_count = conn.execute(
            f"SELECT COUNT(*) FROM vendor_books WHERE batch_id IN ({placeholders})",
            batch_ids,
        ).fetchone()[0]
        holding_count = conn.execute(
            f"SELECT COUNT(*) FROM library_holdings WHERE batch_id IN ({placeholders})",
            batch_ids,
        ).fetchone()[0]

    conn.close()
    return {
        "project_id": project_id,
        "project_name": project["name"],
        "selection_count": selection_count,
        "export_job_count": export_job_count,
        "import_batch_count": import_batch_count,
        "vendor_book_count": vendor_book_count,
        "holding_count": holding_count,
    }
```

### 1-B：DELETE API

```python
@router.delete("/{project_id}")
async def delete_project(project_id: int, user_id: int = Depends(require_auth)):
    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM procurement_projects WHERE id = ?", (project_id,)
    ).fetchone()
    if existing is None:
        conn.close()
        raise HTTPException(status_code=404, detail="找不到專案")

    try:
        # 取得相關 batch_ids
        batch_rows = conn.execute(
            "SELECT id FROM import_batches WHERE project_id = ?", (project_id,)
        ).fetchall()
        batch_ids = [r[0] for r in batch_rows]

        placeholders = lambda n: ",".join("?" * n)

        # 1. selection_items（project FK）
        conn.execute(
            "DELETE FROM selection_items WHERE project_id = ?", (project_id,)
        )
        # 2. export_jobs（project FK）
        conn.execute(
            "DELETE FROM export_jobs WHERE project_id = ?", (project_id,)
        )
        if batch_ids:
            ph = placeholders(len(batch_ids))
            # 3. 取得 vendor_book_ids
            vb_rows = conn.execute(
                f"SELECT id FROM vendor_books WHERE batch_id IN ({ph})", batch_ids
            ).fetchall()
            vb_ids = [r[0] for r in vb_rows]

            if vb_ids:
                vb_ph = placeholders(len(vb_ids))
                # 4. book_matches（vendor FK）
                conn.execute(
                    f"DELETE FROM book_matches WHERE vendor_book_id IN ({vb_ph})",
                    vb_ids,
                )
            # 5. vendor_books
            conn.execute(
                f"DELETE FROM vendor_books WHERE batch_id IN ({ph})", batch_ids
            )
            # 6. 取得 holding_ids
            h_rows = conn.execute(
                f"SELECT id FROM library_holdings WHERE batch_id IN ({ph})", batch_ids
            ).fetchall()
            h_ids = [r[0] for r in h_rows]

            if h_ids:
                h_ph = placeholders(len(h_ids))
                # 7. nullify cross-project book_matches.holding_id
                conn.execute(
                    f"UPDATE book_matches SET holding_id = NULL WHERE holding_id IN ({h_ph})",
                    h_ids,
                )
                # 8. library_holdings
                conn.execute(
                    f"DELETE FROM library_holdings WHERE batch_id IN ({ph})", batch_ids
                )
            # 9. import_batches
            conn.execute(
                "DELETE FROM import_batches WHERE project_id = ?", (project_id,)
            )
        # 10. procurement_projects
        conn.execute(
            "DELETE FROM procurement_projects WHERE id = ?", (project_id,)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail=f"刪除失敗：{e}")

    conn.close()
    return {"ok": True}
```

---

## Step 2：新增 `app/routers/backup.py`

```python
import io
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.auth import require_auth
from app.config import get_config

router = APIRouter(prefix="/api/backup", tags=["backup"])

SQLITE_MAGIC = b"SQLite format 3\x00"
REQUIRED_TABLES = {"procurement_projects", "users", "schema_migrations"}


def _get_db_path() -> str:
    return get_config().database_path


def _validate_sqlite(path: str) -> None:
    """Raises HTTPException if file is not valid SQLite with required tables."""
    with open(path, "rb") as f:
        header = f.read(16)
    if header != SQLITE_MAGIC:
        raise HTTPException(status_code=400, detail="無效的 SQLite 檔案（magic bytes 不符）")
    try:
        conn = sqlite3.connect(path)
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"無法開啟 SQLite 檔案：{e}")
    missing = REQUIRED_TABLES - tables
    if missing:
        raise HTTPException(
            status_code=400, detail=f"備份檔缺少必要資料表：{', '.join(missing)}"
        )


@router.get("/database")
async def backup_database(user_id: int = Depends(require_auth)):
    db_path = _get_db_path()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_filename = f"school_lib_backup_{ts}.db"

    # 寫入暫時目錄
    tmp_dir = Path(db_path).parent
    tmp_path = str(tmp_dir / f"backup_temp_{ts}.db")

    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(tmp_path)
    src.backup(dst)
    src.close()
    dst.close()

    def cleanup():
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass

    return FileResponse(
        tmp_path,
        filename=backup_filename,
        media_type="application/octet-stream",
        background=BackgroundTask(cleanup),
    )


@router.post("/restore")
async def restore_database(
    file: UploadFile = File(...),
    user_id: int = Depends(require_auth),
):
    db_path = _get_db_path()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    data_dir = Path(db_path).parent
    data_dir.mkdir(parents=True, exist_ok=True)

    pending_path = str(data_dir / f"restore_pending_{ts}.db")
    safety_path = str(data_dir / f"restore_safety_backup_{ts}.db")

    # 1. 儲存上傳檔至暫時路徑
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="上傳檔案為空")
    with open(pending_path, "wb") as f:
        f.write(content)

    # 2. 驗證上傳的 SQLite 檔案
    try:
        _validate_sqlite(pending_path)
    except HTTPException:
        Path(pending_path).unlink(missing_ok=True)
        raise

    # 3. 建立現有 DB 的安全備份
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(safety_path)
    src.backup(dst)
    src.close()
    dst.close()

    # 4. 將 pending DB 內容還原至現有 DB 路徑
    try:
        pending_conn = sqlite3.connect(pending_path)
        current_conn = sqlite3.connect(db_path)
        pending_conn.backup(current_conn)
        pending_conn.close()
        current_conn.close()
    except Exception as e:
        Path(pending_path).unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"還原失敗：{e}")
    finally:
        Path(pending_path).unlink(missing_ok=True)

    return {
        "ok": True,
        "safety_backup_path": safety_path,
        "message": "還原成功。已自動建立安全備份。建議重新整理頁面後再繼續操作。",
    }
```

---

## Step 3：`app/main.py` 註冊 backup router

```python
from app.routers import auth, projects, imports, books, selections, exports, holdings, backup

# ...
app.include_router(backup.router)
```

---

## Step 4：`app/static/projects.html` — 刪除 UI

### 4-A：新增 CSS class（`app/static/css/style.css`）

`style.css` 已有 `.btn-danger`（實心紅色），刪除按鈕使用低調紅框樣式以避免誤操作感過強，新增 `.btn-danger-outline`，不修改既有 `.btn-danger`：

```css
.btn-danger-outline {
  background: transparent;
  color: #c0392b;
  border: 1px solid #e74c3c;
}
.btn-danger-outline:hover {
  background: #fff0f0;
}
```

卡片刪除按鈕使用 `btn-danger-outline`；confirm modal「確認刪除」按鈕使用既有 `btn-danger`（強調最後確認動作）。

### 4-B：卡片加入刪除按鈕

在 `project-actions` 中加入刪除按鈕（使用 `btn-danger-outline` class）：

```html
<button class="btn btn-danger-outline btn-sm" onclick="confirmDelete(${p.id},'${p.name.replace(/'/g,"\\'")}')">刪除</button>
```

刪除按鈕顯示邏輯：無條件顯示，點擊時才在 JS 中判斷是否為 current project。

### 4-C：`confirmDelete()` 函式

```js
async function confirmDelete(id, name) {
  const cur = getProjectId();   // 使用共用函式（依序查 sessionStorage / localStorage 的 current_project_id）
  if (cur == id) {
    showToast('請先選擇其他專案後再刪除此專案');
    return;
  }
  // 呼叫 delete-preview
  let preview;
  try {
    preview = await api(`/api/projects/${id}/delete-preview`);
  } catch (e) {
    showToast('無法取得刪除預覽：' + e.message);
    return;
  }
  // 填入 modal
  document.getElementById('delete-project-name').textContent = preview.project_name;
  document.getElementById('delete-stats').innerHTML = `
    <ul style="margin:8px 0;padding-left:20px;color:#555">
      <li>選書項目：${preview.selection_count} 筆</li>
      <li>匯出記錄：${preview.export_job_count} 筆</li>
      <li>匯入批次：${preview.import_batch_count} 批</li>
      <li>書商書目：${preview.vendor_book_count} 筆</li>
      <li>館藏紀錄：${preview.holding_count} 筆</li>
    </ul>`;
  document.getElementById('delete-confirm-btn').onclick = () => doDelete(id);
  document.getElementById('delete-modal').style.display = 'flex';
}

async function doDelete(id) {
  document.getElementById('delete-modal').style.display = 'none';
  try {
    await api(`/api/projects/${id}`, { method: 'DELETE' });
    // 若刪除的是 current project，清除
    if (getProjectId() == id) clearProject();
    showToast('專案已刪除');
    loadProjects();
  } catch (e) {
    showToast('刪除失敗：' + e.message);
  }
}

function closeDeleteModal() {
  document.getElementById('delete-modal').style.display = 'none';
}
```

### 4-D：刪除確認 Modal HTML

加在現有 edit-modal 之後（同 `<div class="page container">` 內）：

```html
<div id="delete-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.3);z-index:200;align-items:center;justify-content:center">
  <div class="card" style="width:460px;margin:0">
    <h2 style="color:#c0392b">確認刪除專案</h2>
    <p>即將刪除專案：<strong id="delete-project-name"></strong></p>
    <div id="delete-stats"></div>
    <p style="color:#c0392b;font-size:13px">⚠ 刪除後無法復原，建議先備份資料庫。與此專案相關的所有資料（書目、選書、匯出紀錄）將永久刪除。</p>
    <div style="display:flex;gap:8px;margin-top:12px">
      <button id="delete-confirm-btn" class="btn btn-danger">確認刪除</button>
      <button class="btn btn-secondary" onclick="closeDeleteModal()">取消</button>
    </div>
  </div>
</div>
```

`confirmDelete()` JS 中直接設定 onclick：`document.getElementById('delete-confirm-btn').onclick = () => doDelete(id);`。不使用 hidden button 轉接。

---

## Step 5：`app/static/projects.html` — 備份 / 還原 UI

### 5-A：頁面頂部操作區

在 `.section-header` 的 `.right` 中，或在下方加入管理區 card：

```html
<div class="card" style="margin-bottom:16px">
  <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
    <span style="font-size:14px;color:#555;font-weight:600">資料庫管理</span>
    <a href="/api/backup/database" class="btn btn-secondary btn-sm" id="backup-btn" onclick="handleBackupClick(event)">備份資料庫</a>
    <button class="btn btn-secondary btn-sm" onclick="showRestoreModal()">還原資料庫</button>
  </div>
</div>
```

備份按鈕使用 `<a href="...">` 觸發下載，並在 click 時顯示 toast。

### 5-B：還原 Modal HTML

```html
<div id="restore-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.3);z-index:200;align-items:center;justify-content:center">
  <div class="card" style="width:480px;margin:0">
    <h2>還原資料庫</h2>
    <p style="color:#e67e22;font-size:13px">⚠ 還原將覆蓋目前所有資料。系統將在還原前自動建立安全備份。</p>
    <div class="form-group" style="margin-top:12px">
      <label>選擇備份檔（.db）</label>
      <input type="file" id="restore-file" accept=".db">
    </div>
    <div style="display:flex;gap:8px;margin-top:12px">
      <button class="btn btn-primary" onclick="doRestore()" style="background:#e67e22">確認還原</button>
      <button class="btn btn-secondary" onclick="closeRestoreModal()">取消</button>
    </div>
    <p id="restore-status" style="margin-top:8px;font-size:13px"></p>
  </div>
</div>
```

### 5-C：還原 JS 函式

```js
function showRestoreModal() {
  document.getElementById('restore-file').value = '';
  document.getElementById('restore-status').textContent = '';
  document.getElementById('restore-modal').style.display = 'flex';
}
function closeRestoreModal() {
  document.getElementById('restore-modal').style.display = 'none';
}

async function doRestore() {
  const fileInput = document.getElementById('restore-file');
  if (!fileInput.files.length) return showToast('請選擇備份檔');
  const formData = new FormData();
  formData.append('file', fileInput.files[0]);
  document.getElementById('restore-status').textContent = '還原中，請稍候...';
  try {
    const res = await fetch('/api/backup/restore', {
      method: 'POST',
      body: formData,
      credentials: 'include',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '未知錯誤' }));
      throw new Error(err.detail);
    }
    const data = await res.json();
    document.getElementById('restore-status').textContent = data.message;
    showToast('還原成功！請重新整理頁面', 5000);
    setTimeout(() => location.reload(), 3000);
  } catch (e) {
    document.getElementById('restore-status').textContent = '';
    showToast('還原失敗：' + e.message, 5000);
  }
}

function handleBackupClick(e) {
  showToast('備份下載中...');
}
```

---

## Step 6：新增 `tests/test_project_delete.py`

測試項目：

```python
# 測試 delete-preview API 回傳正確結構
def test_delete_preview_returns_stats():
    ...

# 測試 DELETE 不存在的 project 回傳 404
def test_delete_nonexistent_project_returns_404():
    ...

# 測試 DELETE 現有 project 成功
def test_delete_project_success():
    ...

# 測試刪除後 project 不再出現在 list
def test_deleted_project_not_in_list():
    ...

# 測試 backup GET 回傳 200 及正確 Content-Disposition
def test_backup_database_returns_file():
    ...

# 測試 restore 上傳非 SQLite 檔案回傳 400
def test_restore_invalid_file_returns_400():
    ...
```

> 這些測試需要 DB 測試 fixture（類似 `tests/test_confirm_import.py` 的模式）。計劃建立 `conftest.py` 提供 test DB + test client。

---

## 可能影響的檔案

| 檔案 | 變更類型 |
|------|---------|
| `app/routers/projects.py` | 新增 delete-preview 與 DELETE endpoints |
| `app/routers/backup.py` | **新增** |
| `app/main.py` | 新增 backup router 匯入與註冊 |
| `app/static/projects.html` | 刪除按鈕、confirm modal、備份/還原 UI |
| `app/static/css/style.css` | 新增 `.btn-danger-outline` 樣式（不改動既有 `.btn-danger`） |
| `tests/test_project_delete.py` | **新增** |

**不需異動：**
- migrations/（無新 migration 需求）
- `app/services/*.py`（刪除邏輯直接在 router 實作）
- 其他 HTML 頁面

---

## DB 關聯與刪除順序分析

（詳見 spec 「資料關聯分析」章節，此處列出 plan 執行觀點）

**已確認 FK 限制**（`PRAGMA foreign_keys = ON`）：

| 刪除目標 | 被哪些 FK 阻擋 | 解法 |
|---------|-------------|------|
| procurement_projects | selection_items, export_jobs, import_batches | 先刪子表 |
| import_batches | vendor_books, library_holdings | 先刪子表 |
| vendor_books | book_matches.vendor_book_id（NOT NULL） | 先刪 book_matches |
| library_holdings | book_matches.holding_id（NULLABLE） | 先 UPDATE SET NULL |

**不受 FK 阻擋的欄位**（migration 003 後）：

- `selection_items.vendor_book_id`：nullable，無 FK
- `selection_items.source_batch_id`：無 FK
- `selection_items.holding_id_at_selection`：無 FK

---

## 後端 API 設計

| Endpoint | Method | 說明 |
|---------|--------|------|
| `/api/projects/{id}/delete-preview` | GET | 刪除前影響統計 |
| `/api/projects/{id}` | DELETE | 刪除專案及關聯資料 |
| `/api/backup/database` | GET | 下載 DB 備份 |
| `/api/backup/restore` | POST | 上傳備份還原 DB |

所有 endpoint 均需 `require_auth`。

---

## 備份 API 策略

- 使用 `sqlite3.Connection.backup(target)` Python built-in 方法，支援線上備份。
- 備份寫至 `data/backup_temp_YYYYMMDD_HHMMSS.db`，透過 `FileResponse` 下載後由 `BackgroundTask` 清理暫時檔。
- **不直接 `shutil.copy` 正在使用中的 DB 檔案**。

---

## 還原 API 策略

1. 接收 multipart file 上傳（`UploadFile`），寫至 `data/restore_pending_YYYYMMDD_HHMMSS.db`。
2. 驗證 magic bytes + 必要資料表。
3. 使用 sqlite3 backup API 備份現有 DB 至 `data/restore_safety_backup_YYYYMMDD_HHMMSS.db`。
4. 使用 sqlite3 backup API 將 pending DB 內容寫入現有 DB 路徑（`pending.backup(current)`）。
5. 清理 pending 暫時檔。
6. **不需要重啟服務**：`get_connection()` 每次 request 建立新 connection，restore 完成後後續 request 即使用新 DB。前端還原成功後自動 `location.reload()`；若畫面異常，提示使用者重新啟動服務。
7. Windows 環境下避免 file rename（OS 可能 lock），使用 backup API in-place 覆寫。

---

## 前端 UI 調整策略

- `projects.html` 最小侵入：在現有 `.project-actions` 加入刪除按鈕，在頁面頂部加入「資料庫管理」card。
- 確認 Modal 複用現有 edit-modal 的設計模式（`position:fixed;inset:0`）。
- 還原使用 `fetch()` 而非 `api()`（因為需要 FormData，不是 JSON）。
- 備份使用 `<a href="/api/backup/database">` 觸發直接下載（最簡單，不需 JS 處理 blob）。

---

## 測試策略

**新增測試（`tests/test_project_delete.py`）：**

1. 需要 test DB fixture（在記憶體或暫時路徑建立 test DB）
2. 建立 `tests/conftest.py` 提供：
   - `test_client`：含登入 session 的 TestClient
   - `test_project_id`：已插入的測試專案 id
3. 測試項目：
   - DELETE 不存在 project → 404
   - DELETE 存在 project → 200，GET list 確認已刪除
   - delete-preview 回傳正確 key
   - backup GET → 200，Content-Disposition 包含 .db
   - restore 上傳非 SQLite → 400
   - restore 上傳有效 SQLite → 200（測試環境用暫時 DB）

**既有測試：** 執行 `.venv\Scripts\pytest.exe tests/ -v` 確認 45 tests 通過。

---

## 手動驗證方式

### 專案刪除

```bash
# 1. 取得 delete-preview
curl -s http://127.0.0.1:8000/api/projects/3/delete-preview -b "session=<tok>"

# 2. 刪除專案
curl -s -X DELETE http://127.0.0.1:8000/api/projects/3 -b "session=<tok>"

# 3. 確認已刪除
curl -s http://127.0.0.1:8000/api/projects/ -b "session=<tok>"
```

### 備份

```bash
# 下載備份
curl -O -J http://127.0.0.1:8000/api/backup/database -b "session=<tok>"

# 驗證備份可開啟
python -c "import sqlite3; c=sqlite3.connect('school_lib_backup_XXXXXX.db'); print([r[0] for r in c.execute('SELECT name FROM sqlite_master WHERE type=\"table\"')])"
```

### 還原

```bash
# 上傳還原
curl -X POST http://127.0.0.1:8000/api/backup/restore \
  -F "file=@school_lib_backup_XXXXXX.db" \
  -b "session=<tok>"

# 驗證還原後資料
curl -s http://127.0.0.1:8000/api/projects/ -b "session=<tok>"
```

### 截圖驗證

建議截圖確認：

- `projects.html`：刪除按鈕樣式（紅框）、confirm modal（含影響統計）。
- 「資料庫管理」區塊：備份 + 還原按鈕外觀。
- 還原 modal：上傳檔案 input + 確認按鈕。
- 刪除目前使用中專案的防呆 toast。

---

## Lint / Format / Typecheck / Test / Build 檢查

| 類型 | 指令 | 說明 |
|------|------|------|
| Python lint | 不適用（無 ruff/flake8 設定） | 手動確認縮排與語法 |
| Python typecheck | 不適用（無 mypy 設定） | 手動確認型別 |
| Python test（既有） | `.venv\Scripts\pytest.exe tests/ -v` | 確認 45 tests 通過 |
| Python test（新增） | `.venv\Scripts\pytest.exe tests/test_project_delete.py -v` | 新增測試通過 |
| JS lint | 不適用（無 ESLint 設定） | 手動確認 |
| Build | 不適用（FastAPI StaticFiles serve） | 啟動 uvicorn 後手動驗證 |
| 服務啟動 | `.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000` | 手動啟動後驗證 |

## 驗證結果（2026-06-23）

### pytest

```
58 passed（含 13 個新增測試，既有 45 個全部通過）
.venv\Scripts\pytest.exe tests/ -v
```

### API 驗證（本機 uvicorn 手動驗證）

| 項目 | 結果 |
|------|------|
| `GET /api/projects/{id}/delete-preview` 不存在 → 404 | pass |
| `GET /api/projects/{id}/delete-preview` 存在 → 6 個統計欄位 | pass |
| `DELETE /api/projects/{id}` 不存在 → 404 | pass |
| `DELETE /api/projects/{id}` 存在 → 200 `{"ok":true}`，列表確認已移除 | pass |
| `GET /api/backup/database` → 200，`Content-Disposition` 含日期檔名，SQLite magic bytes 正確 | pass |
| `POST /api/backup/restore` 非 SQLite → 400 `magic bytes 不符` | pass |
| `POST /api/backup/restore` 合法備份 → 200，`safety_backup` 已建立，還原後 DB 可存取 | pass |

### projects.html 結構驗證

| 元素 | 結果 |
|------|------|
| 「資料庫管理」card（備份 + 還原按鈕） | pass |
| 卡片 `.btn-danger-outline` 刪除按鈕 | pass |
| `delete-modal`：統計列表、`delete-confirm-btn` 直接 onclick binding | pass |
| `restore-modal`：file input、確認還原 | pass |
| `getProjectId()` 防呆、刪除 current project 顯示 toast | pass |
| 既有 `.btn-danger`、背景圖、stepper nav 未受影響 | pass |
