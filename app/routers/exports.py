from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.auth import require_auth
from app.config import get_config
from app.database import db_session, get_connection
from app.services.export_service import ExportSettings, export_general_books, export_local_culture
from app.services.import_service import commit_project_selections_to_holdings
from app.services.validation_service import check_export_readiness

router = APIRouter(prefix="/api/exports", tags=["exports"])


@router.get("/check")
async def export_check(
    project_id: int = Query(...),
    price_field: str = Query("purchase_price"),
    subtotal_mode: str = Query("quantity_times_purchase_price"),
    user_id: int = Depends(require_auth),
):
    result = check_export_readiness(project_id, price_field)
    return result


class ExportRequest(BaseModel):
    project_id: int
    school_name: str = ""
    approved_budget: float | None = None
    price_field: str = "purchase_price"
    subtotal_mode: str = "quantity_times_purchase_price"


@router.post("/local-culture")
async def do_export(body: ExportRequest, user_id: int = Depends(require_auth)):
    cfg = get_config()
    with db_session(get_connection) as conn:
        project = conn.execute(
            "SELECT project_type FROM procurement_projects WHERE id = ?",
            (body.project_id,),
        ).fetchone()
    if project is None:
        raise HTTPException(status_code=404, detail="採購專案不存在")
    settings = ExportSettings(
        project_id=body.project_id,
        school_name=body.school_name,
        approved_budget=body.approved_budget,
        price_field=body.price_field,
        subtotal_mode=body.subtotal_mode,
        output_dir=cfg.export_output_dir,
        exported_by=user_id,
    )
    try:
        if project["project_type"] in ("general_books", "general_books_jh"):
            job_id = export_general_books(settings)
        else:
            job_id = export_local_culture(settings)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"job_id": job_id}


class CommitToHoldingsRequest(BaseModel):
    project_id: int


@router.post("/commit-to-holdings")
async def commit_to_holdings(body: CommitToHoldingsRequest, user_id: int = Depends(require_auth)):
    try:
        return commit_project_selections_to_holdings(body.project_id, user_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/jobs")
async def list_jobs(
    project_id: int = Query(...),
    user_id: int = Depends(require_auth),
):
    with db_session(get_connection) as conn:
        rows = conn.execute(
            "SELECT * FROM export_jobs WHERE project_id = ? ORDER BY exported_at DESC",
            (project_id,),
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/download/{job_id}")
async def download_export(job_id: int, user_id: int = Depends(require_auth)):
    with db_session(get_connection) as conn:
        row = conn.execute("SELECT * FROM export_jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="找不到匯出記錄")
    import os

    if not os.path.exists(row["output_path"]):
        raise HTTPException(status_code=404, detail="匯出檔案不存在")
    return FileResponse(
        row["output_path"],
        filename=row["output_filename"],
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
