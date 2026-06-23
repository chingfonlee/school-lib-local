import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.auth import require_auth
from app.database import get_db_path

router = APIRouter(prefix="/api/backup", tags=["backup"])

SQLITE_MAGIC = b"SQLite format 3\x00"
REQUIRED_TABLES = {"procurement_projects", "users", "schema_migrations"}


def _validate_sqlite(path: str) -> None:
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
            status_code=400,
            detail=f"備份檔缺少必要資料表：{', '.join(sorted(missing))}",
        )


@router.get("/database")
async def backup_database(user_id: int = Depends(require_auth)):
    db_path = get_db_path()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_filename = f"school_lib_backup_{ts}.db"
    data_dir = Path(db_path).parent
    tmp_path = str(data_dir / f"backup_temp_{ts}.db")

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
    db_path = get_db_path()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    data_dir = Path(db_path).parent
    data_dir.mkdir(parents=True, exist_ok=True)

    pending_path = str(data_dir / f"restore_pending_{ts}.db")
    safety_path = str(data_dir / f"restore_safety_backup_{ts}.db")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="上傳檔案為空")
    with open(pending_path, "wb") as f:
        f.write(content)

    try:
        _validate_sqlite(pending_path)
    except HTTPException:
        Path(pending_path).unlink(missing_ok=True)
        raise

    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(safety_path)
    src.backup(dst)
    src.close()
    dst.close()

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
        "message": "還原成功。已自動建立安全備份。頁面即將重新整理；若畫面異常，請重新啟動服務。",
    }
