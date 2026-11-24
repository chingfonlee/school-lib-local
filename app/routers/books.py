from collections import Counter, defaultdict
import json
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from app.auth import require_auth
from app.database import db_session, get_connection
from app.services.completeness_service import compute as compute_completeness, recompute_for_book
from app.services.import_service import DEFAULT_VENDOR_NAME, normalize_vendor_name
from app.services.match_service import run_match

router = APIRouter(prefix="/api/books", tags=["books"])

_AUXILIARY_MATCH_FILTERS = {"same_title_different_isbn", "other_project_selected"}

_VENDOR_BOOK_MATCH_COLUMNS = (
    "vb.id, vb.batch_id, vb.award_item, vb.vendor_seq, vb.title, vb.author, "
    "vb.isbn, vb.isbn_normalized, vb.publish_date, vb.list_price, vb.purchase_price, "
    "vb.publisher, vb.age_range, vb.isbn_status, vb.completeness_status, "
    "vb.policy_topic, vb.award_notes, vb.user_overrides, vb.source_row_number, "
    "vb.category, vb.book_type, vb.summary, vb.source_url, "
    "vb.recommendation_source, vb.eligibility_label, vb.classification_number"
)


def _json_response(payload: Any) -> Response:
    return Response(
        content=json.dumps(payload, ensure_ascii=False),
        media_type="application/json",
    )


def _parse_overrides(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _offer_sort_key(offer: dict[str, Any]) -> tuple[bool, float, str, int]:
    effective_price = offer.get("purchase_price")
    if effective_price is None:
        effective_price = offer.get("list_price")
    return (
        effective_price is None,
        float(effective_price) if effective_price is not None else float("inf"),
        str(offer.get("vendor_name") or ""),
        int(offer.get("vendor_book_id") or 0),
    )


@router.get("/matches")
async def get_matches(
    project_id: int = Query(...),
    match_status: str | None = Query(None),
    completeness_status: str | None = Query(None),
    vendor_name: str | None = Query(None),
    include_missing_isbn: bool = Query(False),
    page: int | None = Query(None, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    include_offers: bool = Query(True),
    user_id: int = Depends(require_auth),
):
    _ = user_id
    show_non_valid_isbn = include_missing_isbn or match_status in ("missing_isbn", "invalid_isbn")
    where_clauses = ["ib.batch_type = 'vendor_books'"]
    if not show_non_valid_isbn:
        where_clauses.append("vb.isbn_status = 'valid'")
    params: list[Any] = [DEFAULT_VENDOR_NAME]

    if vendor_name is not None and vendor_name.strip():
        norm_vendor = normalize_vendor_name(vendor_name)
        where_clauses.append("COALESCE(NULLIF(TRIM(ib.vendor_name), ''), ?) = ?")
        params.extend([DEFAULT_VENDOR_NAME, norm_vendor])

    if match_status and match_status not in _AUXILIARY_MATCH_FILTERS:
        where_clauses.append("bm.match_status = ?")
        params.append(match_status)

    where = " AND ".join(where_clauses)
    with db_session(get_connection) as conn:
        proj_row = conn.execute(
            "SELECT project_type FROM procurement_projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        project_type = proj_row["project_type"] if proj_row else None

        rows = conn.execute(
            f"SELECT {_VENDOR_BOOK_MATCH_COLUMNS}, "
            f"  COALESCE(NULLIF(TRIM(ib.vendor_name), ''), ?) AS vendor_name, bm.match_status "
            f"FROM vendor_books vb "
            f"JOIN import_batches ib ON ib.id = vb.batch_id "
            f"LEFT JOIN book_matches bm ON bm.vendor_book_id = vb.id "
            f"  AND bm.match_status != 'same_title_different_isbn' "
            f"WHERE {where} "
            f"ORDER BY vb.id",
            params,
        ).fetchall()

        if not rows:
            if page is not None:
                return _json_response(
                    {
                        "items": [],
                        "total": 0,
                        "page": page,
                        "page_size": page_size,
                        "total_pages": 0,
                    }
                )
            return _json_response([])

        copy_rows = conn.execute(
            "SELECT lh.isbn_normalized, COUNT(*) AS cnt "
            "FROM library_holdings lh "
            "WHERE lh.isbn_normalized IN ("
            "  SELECT DISTINCT vb.isbn_normalized "
            "  FROM vendor_books vb "
            "  JOIN import_batches ib ON ib.id = vb.batch_id "
            "  WHERE ib.batch_type = 'vendor_books' AND vb.isbn_status = 'valid' AND vb.isbn_normalized IS NOT NULL"
            ") "
            "GROUP BY lh.isbn_normalized"
        ).fetchall()
        holding_copies_map: dict[str, int] = {r["isbn_normalized"]: int(r["cnt"]) for r in copy_rows}

        similar_rows = conn.execute(
            "SELECT bm.vendor_book_id, lh.title, lh.author, lh.publisher, "
            "  COALESCE(lh.isbn_normalized, lh.isbn) AS isbn "
            "FROM book_matches bm "
            "JOIN vendor_books vb ON vb.id = bm.vendor_book_id "
            "JOIN import_batches ib ON ib.id = vb.batch_id "
            "JOIN library_holdings lh ON lh.id = bm.holding_id "
            "WHERE ib.batch_type = 'vendor_books' AND bm.match_status = 'same_title_different_isbn' "
            "ORDER BY bm.id"
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
            "SELECT DISTINCT si.isbn_normalized, pp.id AS project_id, pp.name AS project_name, "
            "  EXISTS (SELECT 1 FROM export_jobs ej WHERE ej.project_id = pp.id) AS has_exported "
            "FROM selection_items si "
            "JOIN procurement_projects pp ON pp.id = si.project_id "
            "WHERE si.project_id != ? "
            "  AND si.selected_quantity > 0 "
            "  AND si.isbn_normalized IS NOT NULL "
            "  AND si.isbn_normalized IN ("
            "    SELECT DISTINCT vb.isbn_normalized "
            "    FROM vendor_books vb "
            "    JOIN import_batches ib ON ib.id = vb.batch_id "
            "    WHERE ib.batch_type = 'vendor_books' AND vb.isbn_status = 'valid' AND vb.isbn_normalized IS NOT NULL"
            "  ) "
            "ORDER BY pp.id",
            (project_id,),
        ).fetchall()
        other_sel_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in other_sel_rows:
            other_sel_map[r["isbn_normalized"]].append(
                {
                    "project_id": r["project_id"],
                    "project_name": r["project_name"],
                    "has_exported": bool(r["has_exported"]),
                }
            )

        offers_by_isbn: dict[str, list[dict[str, Any]]] = defaultdict(list)
        if include_offers:
            offer_rows = conn.execute(
                "SELECT vb.id AS vendor_book_id, vb.isbn_normalized, "
                "  COALESCE(NULLIF(TRIM(ib.vendor_name), ''), ?) AS vendor_name, "
                "  vb.purchase_price, vb.list_price "
                "FROM vendor_books vb "
                "JOIN import_batches ib ON ib.id = vb.batch_id "
                "WHERE ib.batch_type = 'vendor_books' "
                "  AND vb.isbn_status = 'valid' "
                "  AND vb.isbn_normalized IS NOT NULL",
                (DEFAULT_VENDOR_NAME,),
            ).fetchall()
            for r in offer_rows:
                offers_by_isbn[r["isbn_normalized"]].append(
                    {
                        "vendor_book_id": r["vendor_book_id"],
                        "vendor_name": r["vendor_name"],
                        "purchase_price": r["purchase_price"],
                        "list_price": r["list_price"],
                    }
                )

    results: list[dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        overrides = _parse_overrides(item.get("user_overrides"))
        item["completeness_status"] = compute_completeness(item, overrides=overrides, project_type=project_type)

        if completeness_status and item["completeness_status"] != completeness_status:
            continue

        isbn_norm = item.get("isbn_normalized")
        item["holding_copies"] = holding_copies_map.get(isbn_norm, 0) if isbn_norm else 0
        item["similar_holding"] = similar_map.get(item["id"])
        item["other_project_selections"] = list(other_sel_map.get(isbn_norm, [])) if isbn_norm else []

        if include_offers and isbn_norm and isbn_norm in offers_by_isbn:
            other_offers = [
                offer
                for offer in offers_by_isbn[isbn_norm]
                if offer["vendor_book_id"] != item["id"] and offer["vendor_name"] != item["vendor_name"]
            ]
            other_offers.sort(key=_offer_sort_key)
            item["other_vendor_offers"] = other_offers
        else:
            item["other_vendor_offers"] = []

        if match_status == "same_title_different_isbn" and item["similar_holding"] is None:
            continue
        if match_status == "other_project_selected" and not item["other_project_selections"]:
            continue
        results.append(item)

    if page is not None:
        total = len(results)
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        start = (page - 1) * page_size
        page_items = results[start : start + page_size]
        return _json_response(
            {
                "items": page_items,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
            }
        )

    return _json_response(results)


@router.post("/run-match")
async def run_match_endpoint(
    body: dict | None = Body(default=None),
    user_id: int = Depends(require_auth),
):
    _ = user_id
    project_id = body.get("project_id") if isinstance(body, dict) else None
    stats = run_match(project_id)
    return stats


@router.get("/stats")
async def get_stats(
    project_id: int = Query(...),
    vendor_name: str | None = Query(None),
    user_id: int = Depends(require_auth),
):
    _ = user_id
    vendor_filter_sql = ""
    vendor_params: list[Any] = []
    if vendor_name is not None and vendor_name.strip():
        norm_vendor = normalize_vendor_name(vendor_name)
        vendor_filter_sql = " AND COALESCE(NULLIF(TRIM(ib.vendor_name), ''), ?) = ?"
        vendor_params = [DEFAULT_VENDOR_NAME, norm_vendor]

    with db_session(get_connection) as conn:
        proj_row = conn.execute(
            "SELECT project_type FROM procurement_projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        project_type = proj_row["project_type"] if proj_row else None

        match_rows = conn.execute(
            "SELECT bm.match_status, COUNT(*) as cnt "
            "FROM book_matches bm "
            "JOIN vendor_books vb ON vb.id = bm.vendor_book_id "
            "JOIN import_batches ib ON ib.id = vb.batch_id "
            f"WHERE ib.batch_type = 'vendor_books' AND vb.isbn_status = 'valid'{vendor_filter_sql} "
            "AND bm.match_status != 'same_title_different_isbn' "
            "GROUP BY bm.match_status",
            vendor_params,
        ).fetchall()

        valid_books = conn.execute(
            "SELECT vb.title, vb.author, vb.publisher, vb.list_price, vb.purchase_price, "
            "  vb.award_item, vb.eligibility_label, vb.recommendation_source, vb.user_overrides "
            "FROM vendor_books vb "
            "JOIN import_batches ib ON ib.id = vb.batch_id "
            f"WHERE ib.batch_type = 'vendor_books' AND vb.isbn_status = 'valid'{vendor_filter_sql}",
            vendor_params,
        ).fetchall()

        comp_counter: Counter[str] = Counter()
        for b in valid_books:
            book_dict = dict(b)
            overrides = _parse_overrides(book_dict.get("user_overrides"))
            comp_counter[compute_completeness(book_dict, overrides=overrides, project_type=project_type)] += 1

        total_vendor = len(valid_books)

        ignored_missing_isbn = conn.execute(
            "SELECT COUNT(*) FROM vendor_books vb "
            "JOIN import_batches ib ON ib.id = vb.batch_id "
            f"WHERE ib.batch_type = 'vendor_books' AND vb.isbn_status = 'missing'{vendor_filter_sql}",
            vendor_params,
        ).fetchone()[0]

        ignored_invalid_isbn = conn.execute(
            "SELECT COUNT(*) FROM vendor_books vb "
            "JOIN import_batches ib ON ib.id = vb.batch_id "
            f"WHERE ib.batch_type = 'vendor_books' AND vb.isbn_status = 'invalid'{vendor_filter_sql}",
            vendor_params,
        ).fetchone()[0]

        holdings_count = conn.execute("SELECT COUNT(*) FROM library_holdings").fetchone()[0]

        same_title_different_isbn_count = conn.execute(
            "SELECT COUNT(DISTINCT bm.vendor_book_id) "
            "FROM book_matches bm "
            "JOIN vendor_books vb ON vb.id = bm.vendor_book_id "
            "JOIN import_batches ib ON ib.id = vb.batch_id "
            f"WHERE ib.batch_type = 'vendor_books' AND vb.isbn_status = 'valid'{vendor_filter_sql} "
            "AND bm.match_status = 'same_title_different_isbn'",
            vendor_params,
        ).fetchone()[0]

        missing_isbn_similar_count = conn.execute(
            "SELECT COUNT(DISTINCT bm.vendor_book_id) "
            "FROM book_matches bm "
            "JOIN vendor_books vb ON vb.id = bm.vendor_book_id "
            "JOIN import_batches ib ON ib.id = vb.batch_id "
            f"WHERE ib.batch_type = 'vendor_books' AND vb.isbn_status IN ('missing', 'invalid'){vendor_filter_sql} "
            "AND bm.match_status = 'same_title_different_isbn'",
            vendor_params,
        ).fetchone()[0]

        other_project_duplicate_count = conn.execute(
            "SELECT COUNT(*) "
            "FROM vendor_books vb "
            "JOIN import_batches ib ON ib.id = vb.batch_id "
            f"WHERE ib.batch_type = 'vendor_books'{vendor_filter_sql} "
            "  AND vb.isbn_status = 'valid' "
            "  AND vb.isbn_normalized IS NOT NULL "
            "  AND vb.isbn_normalized IN ("
            "    SELECT DISTINCT si.isbn_normalized "
            "    FROM selection_items si "
            "    WHERE si.project_id != ? "
            "      AND si.selected_quantity > 0 "
            "      AND si.isbn_normalized IS NOT NULL "
            "      AND si.isbn_normalized != ''"
            "  )",
            [*vendor_params, project_id],
        ).fetchone()[0]

    return {
        "total_vendor_books": total_vendor,
        "ignored_missing_isbn": ignored_missing_isbn,
        "ignored_invalid_isbn": ignored_invalid_isbn,
        "total_holdings": holdings_count,
        "match_status": {r["match_status"]: r["cnt"] for r in match_rows},
        "completeness_status": dict(comp_counter),
        "same_title_different_isbn_count": same_title_different_isbn_count,
        "missing_isbn_similar_count": missing_isbn_similar_count,
        "other_project_duplicate_count": other_project_duplicate_count,
    }


class OverrideUpdate(BaseModel):
    overrides: dict
    project_id: int | None = None


@router.patch("/{book_id}/overrides")
async def update_overrides(
    book_id: int,
    body: OverrideUpdate,
    project_id: int | None = Query(None),
    user_id: int = Depends(require_auth),
):
    _ = user_id
    effective_project_id = project_id if project_id is not None else body.project_id
    project_type = None
    with db_session(get_connection) as conn:
        existing = conn.execute("SELECT user_overrides FROM vendor_books WHERE id = ?", (book_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="找不到書目")
        if effective_project_id is not None:
            proj_row = conn.execute(
                "SELECT project_type FROM procurement_projects WHERE id = ?",
                (effective_project_id,),
            ).fetchone()
            project_type = proj_row["project_type"] if proj_row else None
        current = _parse_overrides(existing["user_overrides"])
        current.update(body.overrides)
        conn.execute(
            "UPDATE vendor_books SET user_overrides = ? WHERE id = ?",
            (json.dumps(current, ensure_ascii=False), book_id),
        )
        conn.commit()
    new_status = recompute_for_book(book_id, project_type=project_type)
    return {"ok": True, "completeness_status": new_status}
