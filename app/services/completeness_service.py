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


def compute(book: dict, overrides: dict | None = None) -> Literal[
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
    award_item = _get(book, "award_item", overrides)

    if not author or not publisher or not award_item:
        return "needs_review"

    return "export_ready"


def recompute_for_book(vendor_book_id: int) -> str:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM vendor_books WHERE id = ?", (vendor_book_id,)
    ).fetchone()
    if row is None:
        conn.close()
        return "unknown"
    book = dict(row)
    overrides = json.loads(book.get("user_overrides") or "{}")
    status = compute(book, overrides)
    conn.execute(
        "UPDATE vendor_books SET completeness_status = ? WHERE id = ?",
        (status, vendor_book_id),
    )
    conn.commit()
    conn.close()
    return status
