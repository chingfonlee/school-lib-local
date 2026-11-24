from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import threading
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.auth import require_auth
from app.database import DB_TIMEOUT_SECONDS, get_db_path, prune_old_files, run_migrations
from app.logging_config import get_logger

router = APIRouter(prefix="/api/backup", tags=["backup"])

SQLITE_MAGIC = b"SQLite format 3\x00"
REQUIRED_TABLES = {"procurement_projects", "users", "schema_migrations"}
SAFETY_BACKUP_KEEP = 5

_backup_lock = threading.Lock()
logger = get_logger("backup")


def _sqlite_backup(src_path: str, dst_path: str) -> None:
    src: sqlite3.Connection | None = None
    dst: sqlite3.Connection | None = None
    try:
        src = sqlite3.connect(src_path, timeout=DB_TIMEOUT_SECONDS)
        dst = sqlite3.connect(dst_path, timeout=DB_TIMEOUT_SECONDS)
        src.backup(dst)
    finally:
        if dst is not None:
            dst.close()
        if src is not None:
            src.close()


def _validate_sqlite(path: str) -> None:
    with open(path, "rb") as f:
        header = f.read(16)
    if header != SQLITE_MAGIC:
        raise HTTPException(status_code=400, detail="無效的 SQLite 檔案（magic bytes 不符）")

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(path, timeout=DB_TIMEOUT_SECONDS)
        check_row = conn.execute("PRAGMA quick_check").fetchone()
        if not check_row or str(check_row[0]).lower() != "ok":
            raise HTTPException(status_code=400, detail="SQLite 檔案完整性檢查未通過")
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Failed to validate uploaded SQLite file: %s", e, exc_info=True)
        raise HTTPException(status_code=400, detail=f"無法開啟 SQLite 檔案：{e}")
    finally:
        if conn is not None:
            conn.close()

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
    suffix = uuid.uuid4().hex[:8]
    backup_filename = f"school_lib_backup_{ts}.db"
    data_dir = Path(db_path).parent
    data_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = str(data_dir / f"backup_temp_{ts}_{suffix}.db")

    try:
        with _backup_lock:
            _sqlite_backup(db_path, tmp_path)
    except Exception as e:
        Path(tmp_path).unlink(missing_ok=True)
        logger.exception("Database backup failed")
        raise HTTPException(status_code=500, detail=f"備份失敗：{e}")

    def cleanup() -> None:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            logger.warning("Failed to remove temporary backup file: %s", tmp_path, exc_info=True)

    logger.info("Database backup created by user_id=%s: %s", user_id, backup_filename)
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
    suffix = uuid.uuid4().hex[:8]
    data_dir = Path(db_path).parent
    data_dir.mkdir(parents=True, exist_ok=True)

    pending_path = str(data_dir / f"restore_pending_{ts}_{suffix}.db")
    safety_path = str(data_dir / f"restore_safety_backup_{ts}_{suffix}.db")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="上傳檔案為空")

    with open(pending_path, "wb") as f:
        f.write(content)

    try:
        _validate_sqlite(pending_path)
        with _backup_lock:
            _sqlite_backup(db_path, safety_path)
            _sqlite_backup(pending_path, db_path)
            run_migrations()
            prune_old_files(data_dir, "restore_safety_backup_*.db", SAFETY_BACKUP_KEEP)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Database restore failed")
        raise HTTPException(status_code=500, detail=f"還原失敗：{e}")
    finally:
        try:
            Path(pending_path).unlink(missing_ok=True)
        except Exception:
            logger.warning("Failed to remove pending restore file: %s", pending_path, exc_info=True)

    logger.info("Database restored by user_id=%s; safety backup: %s", user_id, safety_path)
    return {
        "ok": True,
        "safety_backup_path": safety_path,
        "message": "還原成功。已自動建立安全備份。頁面即將重新整理；若畫面異常，請重新啟動服務。",
    }
