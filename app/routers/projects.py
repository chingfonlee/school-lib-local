from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from app.auth import require_auth
from app.database import get_connection

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    project_type: str = "local_culture"
    budget_amount: float | None = None
    price_field: str = "purchase_price"
    subtotal_mode: str = "quantity_times_purchase_price"

    @field_validator("budget_amount")
    @classmethod
    def budget_non_negative(cls, v):
        if v is not None and v < 0:
            raise ValueError("budget_amount 不可為負數")
        return v


class ProjectUpdate(BaseModel):
    name: str | None = None
    budget_amount: float | None = None
    price_field: str | None = None
    subtotal_mode: str | None = None

    @field_validator("budget_amount")
    @classmethod
    def budget_non_negative(cls, v):
        if v is not None and v < 0:
            raise ValueError("budget_amount 不可為負數")
        return v


@router.get("/")
async def list_projects(user_id: int = Depends(require_auth)):
    conn = get_connection()
    rows = conn.execute(
        "SELECT p.*, "
        "(SELECT COUNT(*) FROM selection_items si WHERE si.project_id = p.id) as selection_count, "
        "(SELECT exported_at FROM export_jobs ej WHERE ej.project_id = p.id "
        " ORDER BY ej.exported_at DESC LIMIT 1) as last_export, "
        "(SELECT imported_at FROM import_batches ib2 "
        " WHERE ib2.project_id = p.id AND ib2.batch_type = 'vendor_books' "
        " ORDER BY ib2.imported_at DESC LIMIT 1) as last_import, "
        "(SELECT COUNT(*) FROM vendor_books vb "
        " JOIN import_batches ib ON ib.id = vb.batch_id "
        " WHERE ib.project_id = p.id) as vendor_book_count, "
        "(SELECT COUNT(*) FROM vendor_books vb2 "
        " JOIN import_batches ib3 ON ib3.id = vb2.batch_id "
        " WHERE ib3.project_id = p.id "
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
        "FROM procurement_projects p ORDER BY p.created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("/")
async def create_project(body: ProjectCreate, user_id: int = Depends(require_auth)):
    if body.project_type not in ("local_culture", "general_books", "local_culture_jh", "general_books_jh"):
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

    batch_ids = [
        r[0]
        for r in conn.execute(
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
        batch_ids = [
            r[0]
            for r in conn.execute(
                "SELECT id FROM import_batches WHERE project_id = ?", (project_id,)
            ).fetchall()
        ]

        def _ph(n):
            return ",".join("?" * n)

        conn.execute("DELETE FROM selection_items WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM export_jobs WHERE project_id = ?", (project_id,))

        if batch_ids:
            bph = _ph(len(batch_ids))
            vb_ids = [
                r[0]
                for r in conn.execute(
                    f"SELECT id FROM vendor_books WHERE batch_id IN ({bph})", batch_ids
                ).fetchall()
            ]
            if vb_ids:
                conn.execute(
                    f"DELETE FROM book_matches WHERE vendor_book_id IN ({_ph(len(vb_ids))})",
                    vb_ids,
                )
            conn.execute(f"DELETE FROM vendor_books WHERE batch_id IN ({bph})", batch_ids)

            h_ids = [
                r[0]
                for r in conn.execute(
                    f"SELECT id FROM library_holdings WHERE batch_id IN ({bph})", batch_ids
                ).fetchall()
            ]
            if h_ids:
                conn.execute(
                    f"UPDATE book_matches SET holding_id = NULL WHERE holding_id IN ({_ph(len(h_ids))})",
                    h_ids,
                )
                conn.execute(
                    f"DELETE FROM library_holdings WHERE batch_id IN ({bph})", batch_ids
                )
            conn.execute("DELETE FROM import_batches WHERE project_id = ?", (project_id,))

        conn.execute("DELETE FROM procurement_projects WHERE id = ?", (project_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail=f"刪除失敗：{e}")

    conn.close()
    return {"ok": True}


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
    if "budget_amount" in body.model_fields_set:
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
