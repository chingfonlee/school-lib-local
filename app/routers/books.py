from collections import defaultdict
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth import require_auth
from app.database import db_session, get_connection
from app.services.completeness_service import recompute_for_book
from app.services.match_service import run_match

router = APIRouter(prefix="/api/books", tags=["books"])

_AUXILIARY_MATCH_FILTERS = {"same_title_different_isbn", "other_project_selected"}


@router.get("/matches")
async def get_matches(
    project_id: int = Query(...),
    match_status: str | None = Query(None),
    completeness_status: str | None = Query(None),
    user_id: int = Depends(require_auth),
):
    where_clauses = ["ib.project_id = ?", "vb.isbn_status = 'valid'"]
    params: list[Any] = [project_id]

    if match_status and match_status not in _AUXILIARY_MATCH_FILTERS:
        where_clauses.append("bm.match_status = ?")
        params.append(match_status)
    if completeness_status:
        where_clauses.append("vb.completeness_status = ?")
        params.append(completeness_status)

    where = " AND ".join(where_clauses)
    with db_session(get_connection) as conn:
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

        if not rows:
            return []

        copy_rows = conn.execute(
            "SELECT lh.isbn_normalized, COUNT(*) AS cnt "
            "FROM library_holdings lh "
            "WHERE lh.isbn_normalized IN ("
            "  SELECT DISTINCT vb.isbn_normalized "
            "  FROM vendor_books vb "
            "  JOIN import_batches ib ON ib.id = vb.batch_id "
            "  WHERE ib.project_id = ? AND vb.isbn_status = 'valid' AND vb.isbn_normalized IS NOT NULL"
            ") "
            "GROUP BY lh.isbn_normalized",
            (project_id,),
        ).fetchall()
        holding_copies_map: dict[str, int] = {r["isbn_normalized"]: int(r["cnt"]) for r in copy_rows}

        similar_rows = conn.execute(
            "SELECT bm.vendor_book_id, lh.title, lh.author, lh.publisher, "
            "  COALESCE(lh.isbn_normalized, lh.isbn) AS isbn "
            "FROM book_matches bm "
            "JOIN vendor_books vb ON vb.id = bm.vendor_book_id "
            "JOIN import_batches ib ON ib.id = vb.batch_id "
            "JOIN library_holdings lh ON lh.id = bm.holding_id "
            "WHERE ib.project_id = ? AND bm.match_status = 'same_title_different_isbn' "
            "ORDER BY bm.id",
            (project_id,),
        ).fetchall()
        similar_map: dict[int, dict[str, Any]] = {}
        for r in similar_rows:
            similar_map.setdefault(
                r["vendor_book_id"],
                {
                    "title": r["title"],
                    "author": r["author"],
                    "publisher": r["publisher"],
                    "isbn": r["isbn"],
                },
            )

        other_sel_rows = conn.execute(
            "SELECT DISTINCT si.isbn_normalized, pp.id AS project_id, pp.name AS project_name "
            "FROM selection_items si "
            "JOIN procurement_projects pp ON pp.id = si.project_id "
            "WHERE si.project_id != ? "
            "  AND si.selected_quantity > 0 "
            "  AND si.isbn_normalized IS NOT NULL "
            "  AND si.isbn_normalized IN ("
            "    SELECT DISTINCT vb.isbn_normalized "
            "    FROM vendor_books vb "
            "    JOIN import_batches ib ON ib.id = vb.batch_id "
            "    WHERE ib.project_id = ? AND vb.isbn_status = 'valid' AND vb.isbn_normalized IS NOT NULL"
            "  ) "
            "ORDER BY pp.id",
            (project_id, project_id),
        ).fetchall()
        other_sel_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in other_sel_rows:
            other_sel_map[r["isbn_normalized"]].append(
                {"project_id": r["project_id"], "project_name": r["project_name"]}
            )

    results: list[dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        isbn_norm = item.get("isbn_normalized")
        item["holding_copies"] = holding_copies_map.get(isbn_norm, 0) if isbn_norm else 0
        item["similar_holding"] = similar_map.get(item["id"])
        item["other_project_selections"] = list(other_sel_map.get(isbn_norm, [])) if isbn_norm else []

        if match_status == "same_title_different_isbn" and item["similar_holding"] is None:
            continue
        if match_status == "other_project_selected" and not item["other_project_selections"]:
            continue
        results.append(item)

    return results


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
    with db_session(get_connection) as conn:
        match_rows = conn.execute(
            "SELECT bm.match_status, COUNT(*) as cnt "
            "FROM book_matches bm "
            "JOIN vendor_books vb ON vb.id = bm.vendor_book_id "
            "JOIN import_batches ib ON ib.id = vb.batch_id "
            "WHERE ib.project_id = ? AND vb.isbn_status = 'valid' "
            "AND bm.match_status != 'same_title_different_isbn' "
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

        holdings_count = conn.execute("SELECT COUNT(*) FROM library_holdings").fetchone()[0]

        same_title_different_isbn_count = conn.execute(
            "SELECT COUNT(DISTINCT bm.vendor_book_id) "
            "FROM book_matches bm "
            "JOIN vendor_books vb ON vb.id = bm.vendor_book_id "
            "JOIN import_batches ib ON ib.id = vb.batch_id "
            "WHERE ib.project_id = ? AND vb.isbn_status = 'valid' "
            "AND bm.match_status = 'same_title_different_isbn'",
            (project_id,),
        ).fetchone()[0]

        other_project_duplicate_count = conn.execute(
            "SELECT COUNT(*) "
            "FROM vendor_books vb "
            "JOIN import_batches ib ON ib.id = vb.batch_id "
            "WHERE ib.project_id = ? "
            "  AND vb.isbn_status = 'valid' "
            "  AND vb.isbn_normalized IS NOT NULL "
            "  AND EXISTS ("
            "    SELECT 1 FROM selection_items si "
            "    WHERE si.project_id != ? "
            "      AND si.selected_quantity > 0 "
            "      AND si.isbn_normalized = vb.isbn_normalized"
            "  )",
            (project_id, project_id),
        ).fetchone()[0]

    return {
        "total_vendor_books": total_vendor,
        "ignored_missing_isbn": ignored_missing_isbn,
        "ignored_invalid_isbn": ignored_invalid_isbn,
        "total_holdings": holdings_count,
        "match_status": {r["match_status"]: r["cnt"] for r in match_rows},
        "completeness_status": {r["completeness_status"]: r["cnt"] for r in comp_rows},
        "same_title_different_isbn_count": same_title_different_isbn_count,
        "other_project_duplicate_count": other_project_duplicate_count,
    }


class OverrideUpdate(BaseModel):
    overrides: dict


@router.patch("/{book_id}/overrides")
async def update_overrides(
    book_id: int,
    body: OverrideUpdate,
    user_id: int = Depends(require_auth),
):
    with db_session(get_connection) as conn:
        existing = conn.execute("SELECT user_overrides FROM vendor_books WHERE id = ?", (book_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="找不到書目")
        current = json.loads(existing["user_overrides"] or "{}")
        current.update(body.overrides)
        conn.execute(
            "UPDATE vendor_books SET user_overrides = ? WHERE id = ?",
            (json.dumps(current, ensure_ascii=False), book_id),
        )
        conn.commit()
    new_status = recompute_for_book(book_id)
    return {"ok": True, "completeness_status": new_status}
