import json
from datetime import datetime, timezone

from app.database import get_connection


def upsert_selection(
    project_id: int,
    vendor_book_id: int,
    quantity: int,
    notes: str | None,
    user_id: int,
) -> dict:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()

    if quantity == 0:
        conn.execute(
            "DELETE FROM selection_items WHERE project_id = ? AND vendor_book_id = ?",
            (project_id, vendor_book_id),
        )
        conn.commit()
        conn.close()
        return {"deleted": True}

    existing = conn.execute(
        "SELECT id FROM selection_items WHERE project_id = ? AND vendor_book_id = ?",
        (project_id, vendor_book_id),
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE selection_items SET selected_quantity = ?, notes = ?, updated_at = ? "
            "WHERE project_id = ? AND vendor_book_id = ?",
            (quantity, notes, now, project_id, vendor_book_id),
        )
    else:
        conn.execute(
            "INSERT INTO selection_items"
            "(project_id, vendor_book_id, selected_quantity, notes, created_by, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (project_id, vendor_book_id, quantity, notes, user_id, now, now),
        )

    conn.commit()
    conn.close()
    return {"vendor_book_id": vendor_book_id, "quantity": quantity}


def get_selection_summary(project_id: int) -> dict:
    conn = get_connection()
    rows = conn.execute(
        "SELECT si.selected_quantity, vb.list_price, vb.purchase_price, "
        "vb.user_overrides "
        "FROM selection_items si "
        "JOIN vendor_books vb ON vb.id = si.vendor_book_id "
        "WHERE si.project_id = ?",
        (project_id,),
    ).fetchall()

    count = 0
    total_list = 0.0
    total_purchase = 0.0
    for r in rows:
        count += 1
        overrides = json.loads(r["user_overrides"] or "{}")
        lp = _resolve_price(r["list_price"], overrides.get("list_price"))
        pp = _resolve_price(r["purchase_price"], overrides.get("purchase_price"))
        q = r["selected_quantity"]
        total_list += (lp or 0) * q
        total_purchase += (pp or 0) * q

    conn.close()
    return {
        "count": count,
        "total_list_price": total_list,
        "total_purchase_price": total_purchase,
    }


def get_selected_books(project_id: int) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT si.id as sel_id, si.selected_quantity, si.notes as sel_notes, "
        "vb.*, "
        "bm.match_status "
        "FROM selection_items si "
        "JOIN vendor_books vb ON vb.id = si.vendor_book_id "
        "LEFT JOIN book_matches bm ON bm.vendor_book_id = vb.id "
        "  AND bm.match_status != 'same_title_different_isbn' "
        "WHERE si.project_id = ? "
        "ORDER BY si.id",
        (project_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def clear_all_selections(project_id: int) -> dict:
    conn = get_connection()
    result = conn.execute(
        "DELETE FROM selection_items WHERE project_id = ?", (project_id,)
    )
    count = result.rowcount
    conn.commit()
    conn.close()
    return {"deleted_count": count}


def _resolve_price(db_val, override_val) -> float | None:
    if override_val not in (None, ""):
        try:
            return float(override_val)
        except (ValueError, TypeError):
            pass
    return db_val
