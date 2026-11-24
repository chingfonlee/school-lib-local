from collections import defaultdict
from datetime import datetime, timezone
import re
from typing import Any
import unicodedata
import uuid

from app.database import db_session, get_connection

_EDITION_BRACKET_RE = re.compile(
    r"[(\[【〔]\s*"
    r"(?:"
    r"(?:精裝|平裝)(?:版|本)?"
    r"|(?:全新|最新)?(?:修訂|增訂|修訂二|修訂三|新|初|二|三|四|五|2|3|4|5|繪本|典藏|紀念|普及)版"
    r")"
    r"\s*[)\]】〕]"
)
_NON_WORD_RE = re.compile(r"[\W_]+")


def normalize_title_for_match(title: str | None) -> str:
    """Normalize a book title for duplicate-title matching across editions/ISBNs."""
    if not title:
        return ""
    text = unicodedata.normalize("NFKC", title).lower()
    text = _EDITION_BRACKET_RE.sub("", text)
    text = _NON_WORD_RE.sub("", text)
    if len(text) < 2:
        return ""
    return text


def run_match(project_id: int | None = None) -> dict[str, int]:
    """Match all valid-ISBN books in the shared vendor catalog pool against library holdings.

    ``project_id`` is accepted for backward compatibility and ignored because matching
    always operates on the school-wide shared vendor catalog.
    """
    _ = project_id
    batch_run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with db_session(get_connection) as conn:
        holdings = conn.execute(
            "SELECT id, isbn_normalized, title FROM library_holdings WHERE isbn_normalized IS NOT NULL"
        ).fetchall()

        isbn_index: dict[str, int] = {}
        title_index: dict[str, list[str]] = defaultdict(list)
        for h in holdings:
            isbn_index[h["isbn_normalized"]] = h["id"]
            title_key = normalize_title_for_match(h["title"])
            if title_key:
                title_index[title_key].append(h["isbn_normalized"])

        vbooks = conn.execute(
            "SELECT vb.id, vb.isbn_normalized, vb.isbn_status, vb.title "
            "FROM vendor_books vb "
            "JOIN import_batches ib ON ib.id = vb.batch_id "
            "WHERE ib.batch_type = 'vendor_books' AND vb.isbn_status = 'valid'"
        ).fetchall()

        conn.execute(
            "DELETE FROM book_matches WHERE vendor_book_id IN ("
            "SELECT vb.id FROM vendor_books vb "
            "JOIN import_batches ib ON ib.id = vb.batch_id "
            "WHERE ib.batch_type = 'vendor_books')"
        )

        stats: dict[str, int] = {
            "available": 0,
            "already_owned": 0,
            "missing_isbn": 0,
            "invalid_isbn": 0,
            "same_title_different_isbn": 0,
        }

        rows_to_insert: list[tuple[Any, ...]] = []
        for vb in vbooks:
            if vb["isbn_normalized"] in isbn_index:
                status = "already_owned"
            else:
                status = "available"

            holding_id = None
            if status == "already_owned":
                holding_id = isbn_index.get(vb["isbn_normalized"])

            rows_to_insert.append((vb["id"], holding_id, status, now, batch_run_id))
            stats[status] = stats.get(status, 0) + 1

            if status == "available" and vb["title"]:
                title_key = normalize_title_for_match(vb["title"])
                matched_isbns = title_index.get(title_key, []) if title_key else []
                for h_isbn in matched_isbns:
                    if h_isbn != vb["isbn_normalized"]:
                        rows_to_insert.append(
                            (vb["id"], isbn_index[h_isbn], "same_title_different_isbn", now, batch_run_id)
                        )
                        stats["same_title_different_isbn"] += 1
                        break

        conn.executemany(
            "INSERT INTO book_matches(vendor_book_id, holding_id, match_status, matched_at, batch_run_id) "
            "VALUES (?, ?, ?, ?, ?)",
            rows_to_insert,
        )
        conn.commit()
    return stats
