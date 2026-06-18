import json
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth import require_auth
from app.database import get_connection
from app.services.match_service import run_match
from app.services.completeness_service import recompute_for_book

router = APIRouter(prefix="/api/books", tags=["books"])


@router.get("/matches")
async def get_matches(
    project_id: int = Query(...),
    match_status: str | None = Query(None),
    completeness_status: str | None = Query(None),
    user_id: int = Depends(require_auth),
):
    conn = get_connection()
    where_clauses = ["ib.project_id = ?", "vb.isbn_status = 'valid'"]
    params = [project_id]

    if match_status:
        where_clauses.append("bm.match_status = ?")
        params.append(match_status)
    if completeness_status:
        where_clauses.append("vb.completeness_status = ?")
        params.append(completeness_status)

    where = " AND ".join(where_clauses)
    rows = conn.execute(
        f"SELECT vb.*, bm.match_status "
        f"FROM vendor_books vb "
        f"JOIN import_batches ib ON ib.id = vb.batch_id "
        f"LEFT JOIN book_matches bm ON bm.vendor_book_id = vb.id "
        f"  AND bm.match_status != 'same_title_different_isbn' "
        f"WHERE {where} "
        f"ORDER BY vb.id",
        params,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("/run-match")
async def run_match_endpoint(body: dict, user_id: int = Depends(require_auth)):
    project_id = body.get("project_id")
    if project_id is None:
        raise HTTPException(status_code=400, detail="缺少 project_id")
    stats = run_match(project_id)
    return stats


@router.get("/stats")
async def get_stats(
    project_id: int = Query(...),
    user_id: int = Depends(require_auth),
):
    conn = get_connection()
    match_rows = conn.execute(
        "SELECT bm.match_status, COUNT(*) as cnt "
        "FROM book_matches bm "
        "JOIN vendor_books vb ON vb.id = bm.vendor_book_id "
        "JOIN import_batches ib ON ib.id = vb.batch_id "
        "WHERE ib.project_id = ? AND bm.match_status != 'same_title_different_isbn' "
        "GROUP BY bm.match_status",
        (project_id,),
    ).fetchall()

    comp_rows = conn.execute(
        "SELECT vb.completeness_status, COUNT(*) as cnt "
        "FROM vendor_books vb "
        "JOIN import_batches ib ON ib.id = vb.batch_id "
        "WHERE ib.project_id = ? AND vb.isbn_status = 'valid' "
        "GROUP BY vb.completeness_status",
        (project_id,),
    ).fetchall()

    total_vendor = conn.execute(
        "SELECT COUNT(*) FROM vendor_books vb "
        "JOIN import_batches ib ON ib.id = vb.batch_id "
        "WHERE ib.project_id = ? AND vb.isbn_status = 'valid'",
        (project_id,),
    ).fetchone()[0]

    ignored_missing_isbn = conn.execute(
        "SELECT COUNT(*) FROM vendor_books vb "
        "JOIN import_batches ib ON ib.id = vb.batch_id "
        "WHERE ib.project_id = ? AND vb.isbn_status = 'missing'",
        (project_id,),
    ).fetchone()[0]

    ignored_invalid_isbn = conn.execute(
        "SELECT COUNT(*) FROM vendor_books vb "
        "JOIN import_batches ib ON ib.id = vb.batch_id "
        "WHERE ib.project_id = ? AND vb.isbn_status = 'invalid'",
        (project_id,),
    ).fetchone()[0]

    holdings_count = conn.execute(
        "SELECT COUNT(*) FROM library_holdings"
    ).fetchone()[0]

    conn.close()

    return {
        "total_vendor_books": total_vendor,
        "ignored_missing_isbn": ignored_missing_isbn,
        "ignored_invalid_isbn": ignored_invalid_isbn,
        "total_holdings": holdings_count,
        "match_status": {r["match_status"]: r["cnt"] for r in match_rows},
        "completeness_status": {r["completeness_status"]: r["cnt"] for r in comp_rows},
    }


class OverrideUpdate(BaseModel):
    overrides: dict


@router.patch("/{book_id}/overrides")
async def update_overrides(
    book_id: int,
    body: OverrideUpdate,
    user_id: int = Depends(require_auth),
):
    conn = get_connection()
    existing = conn.execute(
        "SELECT user_overrides FROM vendor_books WHERE id = ?", (book_id,)
    ).fetchone()
    if existing is None:
        conn.close()
        raise HTTPException(status_code=404, detail="找不到書目")
    current = json.loads(existing["user_overrides"] or "{}")
    current.update(body.overrides)
    conn.execute(
        "UPDATE vendor_books SET user_overrides = ? WHERE id = ?",
        (json.dumps(current, ensure_ascii=False), book_id),
    )
    conn.commit()
    conn.close()
    new_status = recompute_for_book(book_id)
    return {"ok": True, "completeness_status": new_status}
