import uuid
from datetime import datetime, timezone
from collections import defaultdict

from app.database import get_connection


def run_match(project_id: int) -> dict:
    conn = get_connection()
    batch_run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    holdings = conn.execute(
        "SELECT id, isbn_normalized, title FROM library_holdings "
        "WHERE isbn_normalized IS NOT NULL"
    ).fetchall()

    isbn_index: dict[str, int] = {}
    title_index: dict[str, list[str]] = defaultdict(list)
    for h in holdings:
        isbn_index[h["isbn_normalized"]] = h["id"]
        if h["title"]:
            key = "".join(h["title"].split())
            title_index[key].append(h["isbn_normalized"])

    vbooks = conn.execute(
        "SELECT vb.id, vb.isbn_normalized, vb.isbn_status, vb.title "
        "FROM vendor_books vb "
        "JOIN import_batches ib ON ib.id = vb.batch_id "
        "WHERE ib.project_id = ?",
        (project_id,),
    ).fetchall()

    conn.execute(
        "DELETE FROM book_matches WHERE vendor_book_id IN ("
        "SELECT vb.id FROM vendor_books vb "
        "JOIN import_batches ib ON ib.id = vb.batch_id WHERE ib.project_id = ?)",
        (project_id,),
    )

    stats = {
        "available": 0,
        "already_owned": 0,
        "missing_isbn": 0,
        "invalid_isbn": 0,
        "same_title_different_isbn": 0,
    }

    rows_to_insert = []
    for vb in vbooks:
        isbn_status = vb["isbn_status"]
        if isbn_status == "missing":
            status = "missing_isbn"
        elif isbn_status == "invalid":
            status = "invalid_isbn"
        elif vb["isbn_normalized"] in isbn_index:
            status = "already_owned"
        else:
            status = "available"

        holding_id = None
        if status == "already_owned":
            holding_id = isbn_index.get(vb["isbn_normalized"])

        rows_to_insert.append((vb["id"], holding_id, status, now, batch_run_id))
        stats[status] = stats.get(status, 0) + 1

        if status == "available" and vb["title"]:
            title_key = "".join(vb["title"].split())
            matched_isbns = title_index.get(title_key, [])
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
    conn.close()
    return stats
