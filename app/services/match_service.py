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


def normalize_author_for_match(author: str | None) -> str:
    """Normalize an author name for weak matching on books without valid ISBN."""
    if not author:
        return ""
    text = unicodedata.normalize("NFKC", author).lower()
    text = _NON_WORD_RE.sub("", text)
    return text


def _authors_compatible(a: str, b: str) -> bool:
    """Return True if either author is missing or the normalized authors match/contain each other."""
    if not a or not b:
        return True
    return a == b or a in b or b in a


def run_match(project_id: int | None = None) -> dict[str, int]:
    """Match books in the shared vendor catalog pool against library holdings.

    ``project_id`` is accepted for backward compatibility and ignored because matching
    always operates on the school-wide shared vendor catalog.
    """
    _ = project_id
    batch_run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with db_session(get_connection) as conn:
        holdings = conn.execute("SELECT id, isbn_normalized, title, author FROM library_holdings").fetchall()

        isbn_index: dict[str, int] = {}
        title_index: dict[str, list[tuple[int, str | None, str]]] = defaultdict(list)
        for h in holdings:
            h_id = int(h["id"])
            h_isbn: str | None = h["isbn_normalized"]
            if h_isbn:
                isbn_index[h_isbn] = h_id
            title_key = normalize_title_for_match(h["title"])
            if title_key:
                title_index[title_key].append((h_id, h_isbn, normalize_author_for_match(h["author"])))

        vbooks = conn.execute(
            "SELECT vb.id, vb.isbn_normalized, vb.isbn_status, vb.title, vb.author "
            "FROM vendor_books vb "
            "JOIN import_batches ib ON ib.id = vb.batch_id "
            "WHERE ib.batch_type = 'vendor_books' AND vb.isbn_status IN ('valid', 'missing', 'invalid')"
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
            isbn_status = vb["isbn_status"]
            if isbn_status == "valid":
                if vb["isbn_normalized"] in isbn_index:
                    status = "already_owned"
                    holding_id: int | None = isbn_index.get(vb["isbn_normalized"])
                else:
                    status = "available"
                    holding_id = None

                rows_to_insert.append((vb["id"], holding_id, status, now, batch_run_id))
                stats[status] = stats.get(status, 0) + 1

                if status == "available" and vb["title"]:
                    title_key = normalize_title_for_match(vb["title"])
                    candidates = title_index.get(title_key, []) if title_key else []
                    for h_id, h_isbn, _h_author in candidates:
                        if h_isbn != vb["isbn_normalized"]:
                            rows_to_insert.append((vb["id"], h_id, "same_title_different_isbn", now, batch_run_id))
                            stats["same_title_different_isbn"] += 1
                            break
            else:
                status = "missing_isbn" if isbn_status == "missing" else "invalid_isbn"
                rows_to_insert.append((vb["id"], None, status, now, batch_run_id))
                stats[status] = stats.get(status, 0) + 1

                if vb["title"]:
                    title_key = normalize_title_for_match(vb["title"])
                    vb_author = normalize_author_for_match(vb["author"])
                    candidates = title_index.get(title_key, []) if title_key else []
                    for h_id, _h_isbn, h_author in candidates:
                        if _authors_compatible(vb_author, h_author):
                            rows_to_insert.append((vb["id"], h_id, "same_title_different_isbn", now, batch_run_id))
                            stats["same_title_different_isbn"] += 1
                            break

        conn.executemany(
            "INSERT INTO book_matches(vendor_book_id, holding_id, match_status, matched_at, batch_run_id) "
            "VALUES (?, ?, ?, ?, ?)",
            rows_to_insert,
        )
        conn.commit()
    return stats
