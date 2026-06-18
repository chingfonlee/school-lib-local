from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import require_auth
from app.database import get_connection

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    project_type: str = "local_culture"
    budget_amount: float | None = None
    price_field: str = "purchase_price"
    subtotal_mode: str = "quantity_times_purchase_price"


class ProjectUpdate(BaseModel):
    name: str | None = None
    budget_amount: float | None = None
    price_field: str | None = None
    subtotal_mode: str | None = None


@router.get("/")
async def list_projects(user_id: int = Depends(require_auth)):
    conn = get_connection()
    rows = conn.execute(
        "SELECT p.*, "
        "(SELECT COUNT(*) FROM selection_items si WHERE si.project_id = p.id) as selection_count, "
        "(SELECT exported_at FROM export_jobs ej WHERE ej.project_id = p.id "
        " ORDER BY ej.exported_at DESC LIMIT 1) as last_export "
        "FROM procurement_projects p ORDER BY p.created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("/")
async def create_project(body: ProjectCreate, user_id: int = Depends(require_auth)):
    if body.project_type not in ("local_culture", "general_books"):
        raise HTTPException(status_code=400, detail="無效的 project_type")
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    row = conn.execute(
        "INSERT INTO procurement_projects"
        "(name, project_type, budget_amount, export_template_type, price_field, subtotal_mode, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            body.name,
            body.project_type,
            body.budget_amount,
            body.project_type,
            body.price_field,
            body.subtotal_mode,
            now,
            now,
        ),
    )
    project_id = row.lastrowid
    conn.commit()
    conn.close()
    return {"id": project_id}


@router.get("/{project_id}")
async def get_project(project_id: int, user_id: int = Depends(require_auth)):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM procurement_projects WHERE id = ?", (project_id,)
    ).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="找不到專案")
    return dict(row)


@router.put("/{project_id}")
async def update_project(
    project_id: int, body: ProjectUpdate, user_id: int = Depends(require_auth)
):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    existing = conn.execute(
        "SELECT * FROM procurement_projects WHERE id = ?", (project_id,)
    ).fetchone()
    if existing is None:
        conn.close()
        raise HTTPException(status_code=404, detail="找不到專案")

    updates = dict(existing)
    if body.name is not None:
        updates["name"] = body.name
    if body.budget_amount is not None:
        updates["budget_amount"] = body.budget_amount
    if body.price_field is not None:
        updates["price_field"] = body.price_field
    if body.subtotal_mode is not None:
        updates["subtotal_mode"] = body.subtotal_mode

    conn.execute(
        "UPDATE procurement_projects SET name=?, budget_amount=?, price_field=?, "
        "subtotal_mode=?, updated_at=? WHERE id=?",
        (
            updates["name"],
            updates["budget_amount"],
            updates["price_field"],
            updates["subtotal_mode"],
            now,
            project_id,
        ),
    )
    conn.commit()
    conn.close()
    return {"ok": True}
