from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import require_auth
from app.services.selection_service import (
    bulk_add_selections,
    clear_all_selections,
    get_selected_books,
    get_selection_summary,
    import_selections_from_projects,
    remove_selection,
    update_selection_overrides,
    update_selection_quantity,
    upsert_selection,
)

router = APIRouter(prefix="/api/selections", tags=["selections"])


class SelectionUpsert(BaseModel):
    project_id: int
    vendor_book_id: int
    quantity: int
    notes: str | None = None


class OverridesPatch(BaseModel):
    overrides: dict


class QuantityPatch(BaseModel):
    quantity: int = Field(..., ge=1)


class BulkSelectionItem(BaseModel):
    vendor_book_id: int
    force_owned: bool = False


class BulkSelectionRequest(BaseModel):
    project_id: int
    items: list[BulkSelectionItem]


class ImportFromProjectsRequest(BaseModel):
    target_project_id: int
    source_project_ids: list[int] = Field(..., min_length=1)
    skip_already_owned: bool = True


@router.post("/import-from-projects")
async def import_from_projects(
    body: ImportFromProjectsRequest,
    user_id: int = Depends(require_auth),
):
    try:
        result = import_selections_from_projects(
            body.target_project_id,
            body.source_project_ids,
            user_id,
            skip_already_owned=body.skip_already_owned,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result


@router.post("/bulk")
async def bulk_update_selection(
    body: BulkSelectionRequest,
    user_id: int = Depends(require_auth),
):
    result = bulk_add_selections(
        body.project_id,
        [i.model_dump() for i in body.items],
        user_id,
    )
    return result


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


@router.patch("/{selection_id}/quantity")
async def patch_selection_quantity(
    selection_id: int,
    body: QuantityPatch,
    user_id: int = Depends(require_auth),
):
    try:
        result = update_selection_quantity(selection_id, body.quantity, user_id)
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
