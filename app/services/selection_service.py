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
        snap = conn.execute(
            "SELECT vb.*, ib.id AS source_batch_id, ib.original_filename, "
            "(SELECT bm.match_status FROM book_matches bm "
            "  WHERE bm.vendor_book_id = vb.id "
            "    AND bm.match_status != 'same_title_different_isbn' "
            "  ORDER BY bm.id DESC LIMIT 1) AS match_status, "
            "(SELECT bm.holding_id FROM book_matches bm "
            "  WHERE bm.vendor_book_id = vb.id "
            "    AND bm.match_status != 'same_title_different_isbn' "
            "  ORDER BY bm.id DESC LIMIT 1) AS holding_id "
            "FROM vendor_books vb "
            "JOIN import_batches ib ON ib.id = vb.batch_id "
            "WHERE vb.id = ?",
            (vendor_book_id,),
        ).fetchone()

        if snap is None:
            conn.close()
            raise ValueError(f"vendor_book_id={vendor_book_id} 不存在，無法建立選書快照")

        snap = dict(snap)
        completeness = snap.get("completeness_status") or "unknown"

        conn.execute(
            "INSERT INTO selection_items("
            "project_id, vendor_book_id, "
            "source_batch_id, source_original_filename, source_row_number, "
            "selected_quantity, notes, "
            "title, author, publisher, isbn, isbn_normalized, isbn_status, "
            "publish_date, list_price, purchase_price, "
            "award_item, vendor_seq, age_range, "
            "category, book_type, policy_topic, summary, "
            "source_url, recommendation_source, eligibility_label, award_notes, "
            "classification_number, "
            "completeness_status, "
            "match_status_at_selection, holding_id_at_selection, "
            "user_overrides, extra_fields, raw_row, "
            "created_by, created_at, updated_at"
            ") VALUES ("
            "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?"
            ")",
            (
                project_id,
                vendor_book_id,
                snap.get("source_batch_id"),
                snap.get("original_filename"),
                snap.get("source_row_number"),
                quantity,
                notes,
                snap.get("title"),
                snap.get("author"),
                snap.get("publisher"),
                snap.get("isbn"),
                snap.get("isbn_normalized"),
                snap.get("isbn_status"),
                snap.get("publish_date"),
                snap.get("list_price"),
                snap.get("purchase_price"),
                snap.get("award_item"),
                snap.get("vendor_seq"),
                snap.get("age_range"),
                snap.get("category"),
                snap.get("book_type"),
                snap.get("policy_topic"),
                snap.get("summary"),
                snap.get("source_url"),
                snap.get("recommendation_source"),
                snap.get("eligibility_label"),
                snap.get("award_notes"),
                snap.get("classification_number"),
                completeness,
                snap.get("match_status"),
                snap.get("holding_id"),
                None,
                snap.get("extra_fields"),
                snap.get("raw_row"),
                user_id,
                now,
                now,
            ),
        )

    conn.commit()
    conn.close()
    return {"vendor_book_id": vendor_book_id, "quantity": quantity}


def get_selection_summary(project_id: int) -> dict:
    conn = get_connection()
    rows = conn.execute(
        "SELECT si.selected_quantity, si.list_price, si.purchase_price, si.user_overrides "
        "FROM selection_items si "
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
        "SELECT si.*, "
        "(SELECT bm.match_status FROM book_matches bm "
        "  WHERE bm.vendor_book_id = si.vendor_book_id "
        "    AND bm.match_status != 'same_title_different_isbn' "
        "  ORDER BY bm.id DESC LIMIT 1) AS current_match_status, "
        "(vb.id IS NOT NULL) AS vendor_book_still_exists "
        "FROM selection_items si "
        "LEFT JOIN vendor_books vb ON vb.id = si.vendor_book_id "
        "WHERE si.project_id = ? ORDER BY si.id",
        (project_id,),
    ).fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        d["sel_id"] = d["id"]              # selection_items.id as sel_id
        d["id"] = d.get("vendor_book_id")  # vendor_book_id as id for frontend compat
        d["sel_notes"] = d.get("notes")    # notes alias for backward compat
        result.append(d)
    return result


def update_selection_quantity(
    selection_id: int,
    quantity: int,
    user_id: int,
) -> dict:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()

    row = conn.execute(
        "SELECT id FROM selection_items WHERE id = ?",
        (selection_id,),
    ).fetchone()
    if row is None:
        conn.close()
        raise ValueError(f"selection_items.id={selection_id} 不存在")

    conn.execute(
        "UPDATE selection_items SET selected_quantity = ?, updated_at = ? WHERE id = ?",
        (quantity, now, selection_id),
    )
    conn.commit()
    conn.close()
    return {"selection_id": selection_id, "selected_quantity": quantity}


def remove_selection(selection_id: int) -> dict:
    conn = get_connection()
    result = conn.execute(
        "DELETE FROM selection_items WHERE id = ?", (selection_id,)
    )
    count = result.rowcount
    conn.commit()
    conn.close()
    if count == 0:
        raise ValueError(f"selection_items.id={selection_id} 不存在")
    return {"deleted": True, "selection_id": selection_id}


def clear_all_selections(project_id: int) -> dict:
    conn = get_connection()
    result = conn.execute(
        "DELETE FROM selection_items WHERE project_id = ?", (project_id,)
    )
    count = result.rowcount
    conn.commit()
    conn.close()
    return {"deleted_count": count}


def update_selection_overrides(
    selection_id: int,
    overrides_patch: dict,
    user_id: int,
) -> dict:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()

    row = conn.execute(
        "SELECT user_overrides FROM selection_items WHERE id = ?",
        (selection_id,),
    ).fetchone()
    if row is None:
        conn.close()
        raise ValueError(f"selection_items.id={selection_id} 不存在")

    existing = json.loads(row["user_overrides"] or "{}")
    existing.update(overrides_patch)
    merged = {k: v for k, v in existing.items() if v not in (None, "")}

    conn.execute(
        "UPDATE selection_items SET user_overrides = ?, updated_at = ? WHERE id = ?",
        (json.dumps(merged, ensure_ascii=False) if merged else None, now, selection_id),
    )
    conn.commit()
    conn.close()
    return {"selection_id": selection_id, "user_overrides": merged}


def _resolve_price(db_val, override_val) -> float | None:
    if override_val not in (None, ""):
        try:
            return float(override_val)
        except (ValueError, TypeError):
            pass
    return db_val
