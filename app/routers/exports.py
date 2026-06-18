from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.auth import require_auth
from app.config import get_config
from app.database import get_connection
from app.services.validation_service import check_export_readiness
from app.services.export_service import ExportSettings, export_local_culture

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
    school_name: str
    approved_budget: float | None = None
    price_field: str = "purchase_price"
    subtotal_mode: str = "quantity_times_purchase_price"


@router.post("/local-culture")
async def do_export(body: ExportRequest, user_id: int = Depends(require_auth)):
    cfg = get_config()
    settings = ExportSettings(
        project_id=body.project_id,
        school_name=body.school_name,
        approved_budget=body.approved_budget,
        price_field=body.price_field,
        subtotal_mode=body.subtotal_mode,
        template_path=cfg.local_culture_export_template,
        output_dir=cfg.export_output_dir,
        exported_by=user_id,
    )
    try:
        job_id = export_local_culture(settings)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"job_id": job_id}


@router.get("/jobs")
async def list_jobs(
    project_id: int = Query(...),
    user_id: int = Depends(require_auth),
):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM export_jobs WHERE project_id = ? ORDER BY exported_at DESC",
        (project_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/download/{job_id}")
async def download_export(job_id: int, user_id: int = Depends(require_auth)):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM export_jobs WHERE id = ?", (job_id,)
    ).fetchone()
    conn.close()
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
