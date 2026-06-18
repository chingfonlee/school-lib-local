import json
import io
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.database import get_connection
from app.services.isbn_service import normalize_isbn, get_isbn_status
from app.services.completeness_service import compute as compute_completeness

LIBRARY_COLUMN_HINTS = {
    "isbn": ["b02", "isbn", "條碼", "isbn碼", "isbn號"],
    "title": ["b03", "書名", "title"],
    "author": ["b07", "作者", "author"],
    "publisher": ["b10", "出版社", "publisher"],
    "publish_year": ["b12", "出版年", "出版年份", "publish_year"],
    "price": ["b16", "價格", "定價", "price"],
    "library_record_id": ["b04", "書目識別號", "書目編號"],
}

VENDOR_COLUMN_HINTS = {
    "award_item": ["獲獎項目", "獎項", "award"],
    "vendor_seq": ["序號", "編號", "no", "no."],
    "title": ["書名", "title"],
    "author": ["作者", "author"],
    "isbn": ["條碼", "isbn", "isbn碼", "isbn號"],
    "publish_date": ["出版日期", "出版年", "publish_date"],
    "list_price": ["定價", "list_price"],
    "purchase_price": ["單價", "採購價", "purchase_price"],
    "publisher": ["出版社", "publisher"],
    "age_range": ["適合年齡", "年齡", "age_range"],
}


def _match_columns(df_columns: list[str], hints: dict) -> tuple[dict, list[str]]:
    mapping = {}
    unmapped_sources = []
    lower_cols = {c.strip().lower(): c for c in df_columns}
    for field, candidates in hints.items():
        for cand in candidates:
            if cand.lower() in lower_cols:
                mapping[lower_cols[cand.lower()]] = field
                break
    mapped_targets = set(mapping.values())
    for field in hints:
        if field not in mapped_targets:
            unmapped_sources.append(field)
    return mapping, unmapped_sources


def import_library_holdings(
    file_bytes: bytes,
    filename: str,
    user_id: int,
    profile_id: int | None = None,
    column_overrides: dict | None = None,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()

    if filename.lower().endswith(".xls"):
        df = pd.read_excel(io.BytesIO(file_bytes), engine="xlrd", dtype=str)
    else:
        df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl", dtype=str)

    df.columns = [str(c).strip() for c in df.columns]
    mapping, unmapped = _match_columns(list(df.columns), LIBRARY_COLUMN_HINTS)
    if column_overrides:
        mapping.update(column_overrides)

    batch_row = conn.execute(
        "INSERT INTO import_batches(project_id, batch_type, original_filename, profile_id, "
        "imported_by, imported_at) VALUES (NULL, 'library_holdings', ?, ?, ?, ?)",
        (filename, profile_id, user_id, now),
    )
    batch_id = batch_row.lastrowid

    records_inserted = 0
    reverse_map = {v: k for k, v in mapping.items()}

    for _, row in df.iterrows():
        raw = {col: (None if pd.isna(row[col]) else str(row[col]).strip()) for col in df.columns}

        def get_field(field: str):
            src = reverse_map.get(field)
            if src:
                v = raw.get(src)
                return v if v else None
            return None

        isbn_raw = get_field("isbn")
        isbn_norm = normalize_isbn(isbn_raw)
        isbn_status = get_isbn_status(isbn_raw)

        conn.execute(
            "INSERT INTO library_holdings"
            "(batch_id, isbn, isbn_normalized, title, author, publisher, publish_year, "
            "price, library_record_id, isbn_status, raw_row) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                batch_id,
                isbn_raw,
                isbn_norm,
                get_field("title"),
                get_field("author"),
                get_field("publisher"),
                get_field("publish_year"),
                _to_float(get_field("price")),
                get_field("library_record_id"),
                isbn_status,
                json.dumps(raw, ensure_ascii=False),
            ),
        )
        records_inserted += 1

    conn.execute(
        "UPDATE import_batches SET record_count = ? WHERE id = ?",
        (records_inserted, batch_id),
    )
    conn.commit()
    conn.close()

    return {
        "batch_id": batch_id,
        "record_count": records_inserted,
        "unmapped_fields": unmapped,
        "column_mapping": mapping,
    }


def import_vendor_books(
    file_bytes: bytes,
    filename: str,
    project_id: int,
    user_id: int,
    profile_id: int | None = None,
    column_overrides: dict | None = None,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()

    df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl", dtype=str)
    df.columns = [str(c).strip() for c in df.columns]
    mapping, unmapped = _match_columns(list(df.columns), VENDOR_COLUMN_HINTS)
    if column_overrides:
        mapping.update(column_overrides)

    batch_row = conn.execute(
        "INSERT INTO import_batches(project_id, batch_type, original_filename, profile_id, "
        "imported_by, imported_at) VALUES (?, 'vendor_books', ?, ?, ?, ?)",
        (project_id, filename, profile_id, user_id, now),
    )
    batch_id = batch_row.lastrowid

    records_inserted = 0
    reverse_map = {v: k for k, v in mapping.items()}

    for _, row in df.iterrows():
        raw = {col: (None if pd.isna(row[col]) else str(row[col]).strip()) for col in df.columns}

        def get_field(field: str):
            src = reverse_map.get(field)
            if src:
                v = raw.get(src)
                return v if v else None
            return None

        isbn_raw = get_field("isbn")
        isbn_norm = normalize_isbn(isbn_raw)
        isbn_status = get_isbn_status(isbn_raw)

        award_item = get_field("award_item")

        book = {
            "title": get_field("title"),
            "list_price": _to_float(get_field("list_price")),
            "purchase_price": _to_float(get_field("purchase_price")),
            "author": get_field("author"),
            "publisher": get_field("publisher"),
            "award_item": award_item,
        }
        completeness = compute_completeness(book)

        conn.execute(
            "INSERT INTO vendor_books"
            "(batch_id, award_item, vendor_seq, title, author, isbn, isbn_normalized, "
            "publish_date, list_price, purchase_price, publisher, age_range, "
            "isbn_status, completeness_status, raw_row) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                batch_id,
                award_item,
                get_field("vendor_seq"),
                book["title"],
                book["author"],
                isbn_raw,
                isbn_norm,
                get_field("publish_date"),
                book["list_price"],
                book["purchase_price"],
                book["publisher"],
                get_field("age_range"),
                isbn_status,
                completeness,
                json.dumps(raw, ensure_ascii=False),
            ),
        )
        records_inserted += 1

    conn.execute(
        "UPDATE import_batches SET record_count = ? WHERE id = ?",
        (records_inserted, batch_id),
    )
    conn.commit()
    conn.close()

    return {
        "batch_id": batch_id,
        "record_count": records_inserted,
        "unmapped_fields": unmapped,
        "column_mapping": mapping,
    }


def _to_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", ""))
    except (ValueError, TypeError):
        return None
