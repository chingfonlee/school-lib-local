import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from app.auth import require_auth
from app.database import get_connection
from app.services.import_service import import_library_holdings, import_vendor_books

router = APIRouter(prefix="/api/imports", tags=["imports"])


@router.post("/holdings")
async def upload_holdings(
    file: UploadFile = File(...),
    user_id: int = Depends(require_auth),
):
    content = await file.read()
    try:
        result = import_library_holdings(content, file.filename, user_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.post("/vendor-books")
async def upload_vendor_books(
    file: UploadFile = File(...),
    project_id: int = Form(...),
    user_id: int = Depends(require_auth),
):
    content = await file.read()
    try:
        result = import_vendor_books(content, file.filename, project_id, user_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.get("/batches")
async def list_batches(
    project_id: int | None = None,
    user_id: int = Depends(require_auth),
):
    conn = get_connection()
    if project_id is not None:
        rows = conn.execute(
            "SELECT * FROM import_batches WHERE project_id = ? ORDER BY imported_at DESC",
            (project_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM import_batches ORDER BY imported_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/profiles")
async def list_profiles(user_id: int = Depends(require_auth)):
    conn = get_connection()
    rows = conn.execute("SELECT * FROM import_profiles ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


class ProfileCreate(BaseModel):
    name: str
    file_type: str
    column_mappings: dict


@router.post("/profiles")
async def create_profile(body: ProfileCreate, user_id: int = Depends(require_auth)):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    row = conn.execute(
        "INSERT INTO import_profiles(name, file_type, column_mappings, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (body.name, body.file_type, json.dumps(body.column_mappings, ensure_ascii=False), now, now),
    )
    profile_id = row.lastrowid
    conn.commit()
    conn.close()
    return {"id": profile_id}
