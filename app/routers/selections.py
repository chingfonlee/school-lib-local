from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth import require_auth
from app.services.selection_service import (
    upsert_selection,
    get_selection_summary,
    get_selected_books,
    remove_selection,
    clear_all_selections,
    update_selection_overrides,
)

router = APIRouter(prefix="/api/selections", tags=["selections"])


class SelectionUpsert(BaseModel):
    project_id: int
    vendor_book_id: int
    quantity: int
    notes: str | None = None


class OverridesPatch(BaseModel):
    overrides: dict


@router.get("/")
async def list_selections(
    project_id: int = Query(...),
    user_id: int = Depends(require_auth),
):
    books = get_selected_books(project_id)
    summary = get_selection_summary(project_id)
    return {"summary": summary, "items": books}


@router.post("/")
async def update_selection(body: SelectionUpsert, user_id: int = Depends(require_auth)):
    result = upsert_selection(
        body.project_id,
        body.vendor_book_id,
        body.quantity,
        body.notes,
        user_id,
    )
    return result


@router.delete("/")
async def delete_all_selections(
    project_id: int = Query(...),
    user_id: int = Depends(require_auth),
):
    result = clear_all_selections(project_id)
    return result


@router.delete("/{selection_id}")
async def delete_selection(
    selection_id: int,
    user_id: int = Depends(require_auth),
):
    try:
        result = remove_selection(selection_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result


@router.patch("/{selection_id}/overrides")
async def patch_selection_overrides(
    selection_id: int,
    body: OverridesPatch,
    user_id: int = Depends(require_auth),
):
    try:
        result = update_selection_overrides(selection_id, body.overrides, user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result
