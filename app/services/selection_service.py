from datetime import datetime, timezone
import json
from typing import Any

from app.database import db_session, get_connection
from app.services.completeness_service import compute as compute_completeness


def upsert_selection(
    project_id: int,
    vendor_book_id: int,
    quantity: int,
    notes: str | None,
    user_id: int,
    force_owned: bool = False,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()

    with db_session(get_connection) as conn:
        if quantity == 0:
            conn.execute(
                "DELETE FROM selection_items WHERE project_id = ? AND vendor_book_id = ?",
                (project_id, vendor_book_id),
            )
            conn.commit()
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
            snap_row = conn.execute(
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

            if snap_row is None:
                raise ValueError(f"vendor_book_id={vendor_book_id} 不存在，無法建立選書快照")

            snap = dict(snap_row)
            completeness = snap.get("completeness_status") or "unknown"

            inherited_overrides = json.loads(snap.get("user_overrides") or "{}")
            if force_owned:
                inherited_overrides["force_owned"] = True
            overrides_json = json.dumps(inherited_overrides, ensure_ascii=False) if inherited_overrides else None

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
                    overrides_json,
                    snap.get("extra_fields"),
                    snap.get("raw_row"),
                    user_id,
                    now,
                    now,
                ),
            )

        conn.commit()
    return {"vendor_book_id": vendor_book_id, "quantity": quantity}


def get_selection_summary(project_id: int) -> dict[str, Any]:
    with db_session(get_connection) as conn:
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

    return {
        "count": count,
        "total_list_price": total_list,
        "total_purchase_price": total_purchase,
    }


def get_selected_books(project_id: int) -> list[dict[str, Any]]:
    with db_session(get_connection) as conn:
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

    result: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["sel_id"] = d["id"]  # selection_items.id as sel_id
        d["id"] = d.get("vendor_book_id")  # vendor_book_id as id for frontend compat
        d["sel_notes"] = d.get("notes")  # notes alias for backward compat
        result.append(d)
    return result


def update_selection_quantity(
    selection_id: int,
    quantity: int,
    user_id: int,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    with db_session(get_connection) as conn:
        row = conn.execute(
            "SELECT id FROM selection_items WHERE id = ?",
            (selection_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"selection_items.id={selection_id} 不存在")

        conn.execute(
            "UPDATE selection_items SET selected_quantity = ?, updated_at = ? WHERE id = ?",
            (quantity, now, selection_id),
        )
        conn.commit()
    return {"selection_id": selection_id, "selected_quantity": quantity}


def remove_selection(selection_id: int) -> dict[str, Any]:
    with db_session(get_connection) as conn:
        result = conn.execute("DELETE FROM selection_items WHERE id = ?", (selection_id,))
        count = result.rowcount
        conn.commit()
    if count == 0:
        raise ValueError(f"selection_items.id={selection_id} 不存在")
    return {"deleted": True, "selection_id": selection_id}


def clear_all_selections(project_id: int) -> dict[str, Any]:
    with db_session(get_connection) as conn:
        result = conn.execute("DELETE FROM selection_items WHERE project_id = ?", (project_id,))
        count = result.rowcount
        conn.commit()
    return {"deleted_count": count}


def update_selection_overrides(
    selection_id: int,
    overrides_patch: dict[str, Any],
    user_id: int,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    with db_session(get_connection) as conn:
        row = conn.execute(
            "SELECT si.*, pp.project_type "
            "FROM selection_items si "
            "LEFT JOIN procurement_projects pp ON pp.id = si.project_id "
            "WHERE si.id = ?",
            (selection_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"selection_items.id={selection_id} 不存在")

        book = dict(row)
        project_type = book.pop("project_type", None)
        existing = json.loads(book.get("user_overrides") or "{}")
        existing.update(overrides_patch)
        merged = {k: v for k, v in existing.items() if v not in (None, "")}
        new_completeness = compute_completeness(book, merged, project_type=project_type)

        conn.execute(
            "UPDATE selection_items SET user_overrides = ?, completeness_status = ?, updated_at = ? WHERE id = ?",
            (
                json.dumps(merged, ensure_ascii=False) if merged else None,
                new_completeness,
                now,
                selection_id,
            ),
        )
        conn.commit()
    return {
        "selection_id": selection_id,
        "user_overrides": merged,
        "completeness_status": new_completeness,
    }


def bulk_add_selections(
    project_id: int,
    items: list[dict[str, Any]],
    user_id: int,
) -> dict[str, int]:
    with db_session(get_connection) as conn:
        existing_ids = {
            row["vendor_book_id"]
            for row in conn.execute(
                "SELECT vendor_book_id FROM selection_items WHERE project_id = ?",
                (project_id,),
            ).fetchall()
        }

    added = 0
    skipped = 0
    for item in items:
        vbid = item["vendor_book_id"]
        if vbid in existing_ids:
            skipped += 1
            continue
        try:
            upsert_selection(
                project_id,
                vbid,
                1,
                None,
                user_id,
                force_owned=item.get("force_owned", False),
            )
            existing_ids.add(vbid)
            added += 1
        except ValueError:
            skipped += 1

    return {"added": added, "skipped": skipped}


def _resolve_price(db_val: Any, override_val: Any) -> float | None:
    if override_val not in (None, ""):
        try:
            return float(override_val)
        except (ValueError, TypeError):
            pass
    return db_val
