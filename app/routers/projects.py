from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from app.auth import require_auth
from app.database import db_session, get_connection
from app.logging_config import get_logger

router = APIRouter(prefix="/api/projects", tags=["projects"])
logger = get_logger("projects")

VALID_PROJECT_TYPES = (
    "local_culture",
    "general_books",
    "local_culture_jh",
    "general_books_jh",
    "custom",
)
VALID_EXPORT_TEMPLATE_TYPES = (
    "generic_builtin",
    "local_culture",
    "general_books",
    "local_culture_jh",
    "general_books_jh",
)


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned if cleaned else None


class ProjectCreate(BaseModel):
    name: str
    project_type: str = "local_culture"
    budget_amount: float | None = None
    export_template_type: str | None = None
    price_field: str = "purchase_price"
    subtotal_mode: str = "quantity_times_purchase_price"
    academic_year: str | None = None
    funding_source: str | None = None
    project_notes: str | None = None
    is_archived: bool = False

    @field_validator("budget_amount")
    @classmethod
    def budget_non_negative(cls, v: float | None) -> float | None:
        if v is not None and v < 0:
            raise ValueError("budget_amount 不可為負數")
        return v


class ProjectUpdate(BaseModel):
    name: str | None = None
    budget_amount: float | None = None
    export_template_type: str | None = None
    price_field: str | None = None
    subtotal_mode: str | None = None
    academic_year: str | None = None
    funding_source: str | None = None
    project_notes: str | None = None
    is_archived: bool | None = None

    @field_validator("budget_amount")
    @classmethod
    def budget_non_negative(cls, v: float | None) -> float | None:
        if v is not None and v < 0:
            raise ValueError("budget_amount 不可為負數")
        return v


@router.get("/")
async def list_projects(user_id: int = Depends(require_auth)):
    with db_session(get_connection) as conn:
        rows = conn.execute(
            "SELECT p.*, "
            "(SELECT COUNT(*) FROM selection_items si WHERE si.project_id = p.id) as selection_count, "
            "(SELECT exported_at FROM export_jobs ej WHERE ej.project_id = p.id "
            " ORDER BY ej.exported_at DESC LIMIT 1) as last_export, "
            "(SELECT imported_at FROM import_batches ib2 "
            " WHERE ib2.batch_type = 'vendor_books' "
            " ORDER BY ib2.imported_at DESC LIMIT 1) as last_import, "
            "(SELECT COUNT(*) FROM vendor_books vb "
            " JOIN import_batches ib ON ib.id = vb.batch_id "
            " WHERE ib.batch_type = 'vendor_books') as vendor_book_count, "
            "(SELECT COUNT(*) FROM vendor_books vb2 "
            " JOIN import_batches ib3 ON ib3.id = vb2.batch_id "
            " WHERE ib3.batch_type = 'vendor_books' "
            " AND (SELECT bm.match_status FROM book_matches bm "
            "      WHERE bm.vendor_book_id = vb2.id "
            "        AND bm.match_status != 'same_title_different_isbn' "
            "      ORDER BY bm.id DESC LIMIT 1) = 'already_owned'"
            ") as already_owned_count, "
            "COALESCE("
            "  (SELECT CASE p.subtotal_mode "
            "     WHEN 'quantity_times_list_price' "
            "       THEN SUM(si2.selected_quantity * si2.list_price) "
            "     ELSE SUM(si2.selected_quantity * si2.purchase_price) "
            "   END "
            "   FROM selection_items si2 "
            "   WHERE si2.project_id = p.id AND si2.selected_quantity > 0), "
            "  0"
            ") as selection_amount "
            "FROM procurement_projects p ORDER BY p.is_archived ASC, p.created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/")
async def create_project(body: ProjectCreate, user_id: int = Depends(require_auth)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="專案名稱不可為空")
    if body.project_type not in VALID_PROJECT_TYPES:
        raise HTTPException(status_code=400, detail="無效的 project_type")

    resolved_template_type = _clean_optional_text(body.export_template_type)
    if resolved_template_type is None:
        resolved_template_type = "generic_builtin" if body.project_type == "custom" else body.project_type
    if resolved_template_type not in VALID_EXPORT_TEMPLATE_TYPES:
        raise HTTPException(status_code=400, detail="無效的 export_template_type")

    academic_year = _clean_optional_text(body.academic_year)
    funding_source = _clean_optional_text(body.funding_source)
    project_notes = _clean_optional_text(body.project_notes)
    is_archived = 1 if body.is_archived else 0

    now = datetime.now(timezone.utc).isoformat()
    with db_session(get_connection) as conn:
        row = conn.execute(
            "INSERT INTO procurement_projects"
            "(name, project_type, budget_amount, export_template_type, price_field, subtotal_mode, "
            "academic_year, funding_source, project_notes, is_archived, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                name,
                body.project_type,
                body.budget_amount,
                resolved_template_type,
                body.price_field,
                body.subtotal_mode,
                academic_year,
                funding_source,
                project_notes,
                is_archived,
                now,
                now,
            ),
        )
        project_id = row.lastrowid
        conn.commit()
    return {"id": project_id, "name": name}


@router.get("/{project_id}")
async def get_project(project_id: int, user_id: int = Depends(require_auth)):
    with db_session(get_connection) as conn:
        row = conn.execute("SELECT * FROM procurement_projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="找不到專案")
    return dict(row)


@router.get("/{project_id}/delete-preview")
async def delete_preview(project_id: int, user_id: int = Depends(require_auth)):
    with db_session(get_connection) as conn:
        project = conn.execute("SELECT id, name FROM procurement_projects WHERE id = ?", (project_id,)).fetchone()
        if project is None:
            raise HTTPException(status_code=404, detail="找不到專案")

        selection_count = conn.execute(
            "SELECT COUNT(*) FROM selection_items WHERE project_id = ?", (project_id,)
        ).fetchone()[0]
        export_job_count = conn.execute(
            "SELECT COUNT(*) FROM export_jobs WHERE project_id = ?", (project_id,)
        ).fetchone()[0]
        import_batch_count = conn.execute(
            "SELECT COUNT(*) FROM import_batches WHERE project_id = ? AND batch_type != 'vendor_books'",
            (project_id,),
        ).fetchone()[0]
        holding_count = conn.execute(
            "SELECT COUNT(*) FROM library_holdings lh "
            "JOIN import_batches ib ON ib.id = lh.batch_id "
            "WHERE ib.project_id = ? AND ib.batch_type != 'vendor_books'",
            (project_id,),
        ).fetchone()[0]

    return {
        "project_id": project_id,
        "project_name": project["name"],
        "selection_count": selection_count,
        "export_job_count": export_job_count,
        "import_batch_count": import_batch_count,
        "vendor_book_count": 0,
        "holding_count": holding_count,
        "shared_catalog_preserved": True,
    }


@router.delete("/{project_id}")
async def delete_project(project_id: int, user_id: int = Depends(require_auth)):
    try:
        with db_session(get_connection) as conn:
            existing = conn.execute("SELECT id FROM procurement_projects WHERE id = ?", (project_id,)).fetchone()
            if existing is None:
                raise HTTPException(status_code=404, detail="找不到專案")

            # Migrate any legacy project-bound vendor_books batches into the shared pool before deleting the project.
            conn.execute(
                "UPDATE import_batches SET project_id = NULL WHERE project_id = ? AND batch_type = 'vendor_books'",
                (project_id,),
            )

            conn.execute("DELETE FROM selection_items WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM export_jobs WHERE project_id = ?", (project_id,))

            non_vendor_batches = conn.execute(
                "SELECT COUNT(*) FROM import_batches WHERE project_id = ? AND batch_type != 'vendor_books'",
                (project_id,),
            ).fetchone()[0]
            if non_vendor_batches > 0:
                conn.execute(
                    "UPDATE book_matches SET holding_id = NULL WHERE holding_id IN ("
                    "  SELECT lh.id FROM library_holdings lh "
                    "  JOIN import_batches ib ON ib.id = lh.batch_id "
                    "  WHERE ib.project_id = ? AND ib.batch_type != 'vendor_books'"
                    ")",
                    (project_id,),
                )
                conn.execute(
                    "DELETE FROM library_holdings WHERE batch_id IN ("
                    "  SELECT id FROM import_batches WHERE project_id = ? AND batch_type != 'vendor_books'"
                    ")",
                    (project_id,),
                )
                conn.execute(
                    "DELETE FROM import_batches WHERE project_id = ? AND batch_type != 'vendor_books'",
                    (project_id,),
                )

            conn.execute("DELETE FROM procurement_projects WHERE id = ?", (project_id,))
            conn.commit()
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to delete project_id=%s", project_id)
        raise HTTPException(status_code=500, detail=f"刪除失敗：{e}")

    logger.info("Deleted project_id=%s by user_id=%s", project_id, user_id)
    return {"ok": True}


@router.put("/{project_id}")
async def update_project(project_id: int, body: ProjectUpdate, user_id: int = Depends(require_auth)):
    now = datetime.now(timezone.utc).isoformat()
    with db_session(get_connection) as conn:
        existing = conn.execute("SELECT * FROM procurement_projects WHERE id = ?", (project_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="找不到專案")

        updates = dict(existing)
        if body.name is not None:
            cleaned_name = body.name.strip()
            if not cleaned_name:
                raise HTTPException(status_code=400, detail="專案名稱不可為空")
            updates["name"] = cleaned_name
        if "budget_amount" in body.model_fields_set:
            updates["budget_amount"] = body.budget_amount
        if body.export_template_type is not None:
            cleaned_tmpl = _clean_optional_text(body.export_template_type)
            if cleaned_tmpl not in VALID_EXPORT_TEMPLATE_TYPES:
                raise HTTPException(status_code=400, detail="無效的 export_template_type")
            updates["export_template_type"] = cleaned_tmpl
        if body.price_field is not None:
            updates["price_field"] = body.price_field
        if body.subtotal_mode is not None:
            updates["subtotal_mode"] = body.subtotal_mode
        if "academic_year" in body.model_fields_set:
            updates["academic_year"] = _clean_optional_text(body.academic_year)
        if "funding_source" in body.model_fields_set:
            updates["funding_source"] = _clean_optional_text(body.funding_source)
        if "project_notes" in body.model_fields_set:
            updates["project_notes"] = _clean_optional_text(body.project_notes)
        if body.is_archived is not None:
            updates["is_archived"] = 1 if body.is_archived else 0

        conn.execute(
            "UPDATE procurement_projects SET name=?, budget_amount=?, export_template_type=?, "
            "price_field=?, subtotal_mode=?, academic_year=?, funding_source=?, project_notes=?, "
            "is_archived=?, updated_at=? WHERE id=?",
            (
                updates["name"],
                updates["budget_amount"],
                updates["export_template_type"],
                updates["price_field"],
                updates["subtotal_mode"],
                updates.get("academic_year"),
                updates.get("funding_source"),
                updates.get("project_notes"),
                updates.get("is_archived", 0),
                now,
                project_id,
            ),
        )
        conn.commit()
    return {"ok": True}
