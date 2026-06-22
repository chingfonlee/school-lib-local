import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from app.auth import require_auth
from app.database import get_connection
from app.services.import_service import (
    import_library_holdings,
    import_vendor_books,
    preview_excel,
    confirm_import,
    clear_library_holdings,
    clear_vendor_books,
)

router = APIRouter(prefix="/api/imports", tags=["imports"])


def _resolve_project_type(conn, project_id: int) -> str:
    row = conn.execute(
        "SELECT project_type FROM procurement_projects WHERE id = ?", (project_id,)
    ).fetchone()
    return row["project_type"] if row else "local_culture"


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


@router.post("/vendor-books/preview")
async def preview_vendor_books(
    file: UploadFile = File(...),
    sheet_name: str | None = Form(None),
    header_row: int | None = Form(None),
    user_id: int = Depends(require_auth),
):
    content = await file.read()
    try:
        result = preview_excel(content, file.filename, sheet_name=sheet_name, header_row=header_row)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.post("/vendor-books/confirm")
async def confirm_vendor_books(
    file: UploadFile = File(...),
    project_id: int = Form(...),
    sheet_name: str | None = Form(None),
    header_row: int = Form(...),
    mappings: str = Form(...),
    extra_field_settings: str = Form("[]"),
    save_profile: bool = Form(False),
    profile_name: str | None = Form(None),
    user_id: int = Depends(require_auth),
):
    content = await file.read()
    try:
        mappings_dict = json.loads(mappings)
        extra_list = json.loads(extra_field_settings)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"mappings/extra_field_settings JSON 格式錯誤：{e}")

    profile_id = None
    if save_profile and profile_name:
        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        try:
            proj_type = _resolve_project_type(conn, project_id)
            row = conn.execute(
                "INSERT OR IGNORE INTO import_profiles"
                "(name, file_type, column_mappings, project_type, source_type, "
                "header_row, mappings, extra_field_settings, created_at, updated_at) "
                "VALUES (?, 'vendor_books', ?, ?, 'excel', ?, ?, ?, ?, ?)",
                (
                    profile_name,
                    json.dumps(mappings_dict, ensure_ascii=False),
                    proj_type,
                    header_row,
                    json.dumps(mappings_dict, ensure_ascii=False),
                    json.dumps(extra_list, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            conn.commit()
            profile_id = row.lastrowid or None
        finally:
            conn.close()

    try:
        result = confirm_import(
            content,
            file.filename,
            project_id,
            sheet_name=sheet_name,
            header_row=header_row,
            mappings=mappings_dict,
            extra_field_settings=extra_list,
            user_id=user_id,
            profile_id=profile_id,
        )
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


@router.delete("/holdings")
async def delete_holdings(user_id: int = Depends(require_auth)):
    try:
        result = clear_library_holdings(user_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.delete("/vendor-books")
async def delete_vendor_books(project_id: int, user_id: int = Depends(require_auth)):
    try:
        result = clear_vendor_books(project_id, user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
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
