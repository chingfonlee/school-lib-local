import json
import sqlite3
from typing import Literal

from app.database import get_connection


def _get(book: dict, field: str, overrides: dict | None) -> str:
    if overrides and field in overrides and overrides[field] not in (None, ""):
        return str(overrides[field])
    v = book.get(field)
    if v not in (None, ""):
        return str(v)
    return ""


def compute(book: dict, overrides: dict | None = None, project_type: str | None = None) -> Literal[
    "export_ready", "needs_review", "missing_required", "unknown"
]:
    title = _get(book, "title", overrides)
    list_price = _get(book, "list_price", overrides)
    purchase_price = _get(book, "purchase_price", overrides)
    has_price = bool(list_price or purchase_price)

    if not title or not has_price:
        return "missing_required"

    author = _get(book, "author", overrides)
    publisher = _get(book, "publisher", overrides)

    if project_type == "general_books":
        eligibility_label = _get(book, "eligibility_label", overrides)
        recommendation_source = _get(book, "recommendation_source", overrides)
        if not eligibility_label or not recommendation_source:
            return "missing_required"
        if not author or not publisher:
            return "needs_review"
        return "export_ready"

    award_item = _get(book, "award_item", overrides)
    if not author or not publisher or not award_item:
        return "needs_review"

    return "export_ready"


def recompute_for_book(vendor_book_id: int) -> str:
    conn = get_connection()
    row = conn.execute(
        "SELECT vb.*, pp.project_type "
        "FROM vendor_books vb "
        "JOIN import_batches ib ON vb.batch_id = ib.id "
        "JOIN procurement_projects pp ON ib.project_id = pp.id "
        "WHERE vb.id = ?",
        (vendor_book_id,),
    ).fetchone()
    if row is None:
        conn.close()
        return "unknown"
    book = dict(row)
    project_type = book.pop("project_type", None)
    overrides = json.loads(book.get("user_overrides") or "{}")
    status = compute(book, overrides, project_type=project_type)
    conn.execute(
        "UPDATE vendor_books SET completeness_status = ? WHERE id = ?",
        (status, vendor_book_id),
    )
    conn.commit()
    conn.close()
    return status
