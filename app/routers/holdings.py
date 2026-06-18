from fastapi import APIRouter, Depends, Query

from app.auth import require_auth
from app.database import get_connection
from app.services.isbn_service import normalize_isbn

router = APIRouter(prefix="/api/holdings", tags=["holdings"])


@router.get("/search")
async def search_holdings(
    q: str | None = Query(None),
    isbn: str | None = Query(None),
    title: str | None = Query(None),
    author: str | None = Query(None),
    publisher: str | None = Query(None),
    library_record_id: str | None = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
    user_id: int = Depends(require_auth),
):
    limit = min(limit, 200)
    offset = max(offset, 0)

    if not any([q, isbn, title, author, publisher, library_record_id]):
        return {"total": 0, "limit": limit, "offset": 0, "items": []}

    where_clauses = []
    params = []

    if isbn:
        normalized = normalize_isbn(isbn)
        if normalized:
            where_clauses.append("isbn_normalized = ?")
            params.append(normalized)
        else:
            where_clauses.append("isbn LIKE ?")
            params.append(f"%{isbn}%")

    if title:
        where_clauses.append("title LIKE ?")
        params.append(f"%{title}%")

    if author:
        where_clauses.append("author LIKE ?")
        params.append(f"%{author}%")

    if publisher:
        where_clauses.append("publisher LIKE ?")
        params.append(f"%{publisher}%")

    if library_record_id:
        where_clauses.append("library_record_id LIKE ?")
        params.append(f"%{library_record_id}%")

    if q:
        q_conditions = []
        q_params = []
        normalized_q = normalize_isbn(q)
        if normalized_q:
            q_conditions.append("isbn_normalized = ?")
            q_params.append(normalized_q)
        q_conditions.extend([
            "isbn LIKE ?", "title LIKE ?", "author LIKE ?",
            "publisher LIKE ?", "library_record_id LIKE ?",
        ])
        q_params.extend([f"%{q}%"] * 5)
        where_clauses.append(f"({' OR '.join(q_conditions)})")
        params.extend(q_params)

    where = " AND ".join(where_clauses)
    conn = get_connection()
    total = conn.execute(
        f"SELECT COUNT(*) FROM library_holdings WHERE {where}", params
    ).fetchone()[0]
    rows = conn.execute(
        f"SELECT id, title, author, publisher, publish_year, isbn, library_record_id, price "
        f"FROM library_holdings WHERE {where} "
        f"ORDER BY title ASC, library_record_id ASC "
        f"LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    conn.close()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [dict(r) for r in rows],
    }
