from html.parser import HTMLParser
import io
import json
import math
import re
from datetime import datetime, timezone

import pandas as pd

from app.database import db_session, get_connection
from app.services.award_normalization_service import group_normalize
from app.services.completeness_service import compute as compute_completeness
from app.services.isbn_service import get_isbn_status, normalize_isbn
from app.services.match_service import normalize_title_for_match, run_match

DEFAULT_VENDOR_NAME = "未指定書商"
VALID_IMPORT_MODES = {"upsert", "replace_vendor"}
VALID_HOLDINGS_IMPORT_MODES = {"replace", "append"}

_ZIP_MAGIC = b"PK\x03\x04"
_OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_HTML_MARKERS = (b"<html", b"<!doctype", b"<table")
_HTML_ENCODINGS = ("utf-8-sig", "cp950", "big5", "gb18030")
_CURRENCY_CLEAN_RE = re.compile(
    r"(?:nt\$|ntd|tw\$|新台幣|新臺幣|[\$＄,，\s\u3000元整])+",
    re.IGNORECASE,
)


class _HtmlTableParser(HTMLParser):
    """Lightweight stdlib HTML table parser for HTML-disguised .xls exports."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table_stack: list[list[list[str]]] = []
        self._current_row: list[str] | None = None
        self._in_cell = False
        self._cell_buf: list[str] = []
        self._cell_colspan = 1

    def _finish_cell(self) -> None:
        if not self._in_cell:
            return
        text = "".join(self._cell_buf).replace("\xa0", " ").strip()
        if self._current_row is not None:
            self._current_row.append(text)
            if self._cell_colspan > 1:
                self._current_row.extend([""] * (self._cell_colspan - 1))
        self._in_cell = False
        self._cell_buf = []
        self._cell_colspan = 1

    def _finish_row(self) -> None:
        self._finish_cell()
        if self._current_row is not None and self._table_stack:
            if self._current_row:
                self._table_stack[-1].append(self._current_row)
        self._current_row = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t == "table":
            self._finish_cell()
            self._table_stack.append([])
        elif t == "tr" and self._table_stack:
            self._finish_row()
            self._current_row = []
        elif t in ("td", "th") and self._table_stack:
            if self._current_row is None:
                self._current_row = []
            self._finish_cell()
            self._in_cell = True
            self._cell_buf = []
            colspan = 1
            for k, v in attrs:
                if k.lower() == "colspan" and v:
                    try:
                        colspan = max(1, min(int(str(v).strip()), 100))
                    except ValueError:
                        colspan = 1
            self._cell_colspan = colspan
        elif t == "br" and self._in_cell:
            self._cell_buf.append(" ")

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in ("td", "th"):
            self._finish_cell()
        elif t == "tr":
            self._finish_row()
        elif t == "table" and self._table_stack:
            self._finish_row()
            table = self._table_stack.pop()
            if table:
                self.tables.append(table)

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_buf.append(data)

    def close(self) -> None:
        super().close()
        self._finish_row()
        while self._table_stack:
            table = self._table_stack.pop()
            if table:
                self.tables.append(table)


def _is_html_table_bytes(file_bytes: bytes) -> bool:
    if not file_bytes:
        return False
    if file_bytes.startswith(_ZIP_MAGIC) or file_bytes.startswith(_OLE2_MAGIC):
        return False
    head = file_bytes[:4096].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    return any(marker in head for marker in _HTML_MARKERS)


def _decode_html_bytes(file_bytes: bytes) -> str:
    for enc in _HTML_ENCODINGS:
        try:
            return file_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return file_bytes.decode("utf-8", errors="replace")


def _parse_html_tables(file_bytes: bytes) -> list[list[list[str]]]:
    html_text = _decode_html_bytes(file_bytes)
    parser = _HtmlTableParser()
    parser.feed(html_text)
    parser.close()
    return parser.tables


def _detect_file_engine(file_bytes: bytes, filename: str) -> str:
    if file_bytes.startswith(_ZIP_MAGIC):
        return "openpyxl"
    if file_bytes.startswith(_OLE2_MAGIC):
        return "xlrd"
    if _is_html_table_bytes(file_bytes):
        return "html"
    return "xlrd" if (filename or "").lower().endswith(".xls") else "openpyxl"


def normalize_vendor_name(vendor_name: str | None) -> str:
    cleaned = (vendor_name or "").strip()
    return cleaned if cleaned else DEFAULT_VENDOR_NAME


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
    "isbn": ["條碼", "isbn", "isbn碼", "isbn號", "條形碼"],
    "publish_date": ["出版日期", "出版年", "publish_date"],
    "list_price": ["定價", "list_price"],
    "purchase_price": ["單價", "採購價", "purchase_price"],
    "publisher": ["出版社", "publisher"],
    "age_range": ["適合年齡", "年齡", "age_range"],
    "category": ["分類", "category"],
    "book_type": ["類型", "書本類型", "book_type"],
    "summary": ["summary_80_120", "摘要", "summary"],
    "source_url": ["連結", "url", "link", "source_url"],
    "recommendation_source": ["award_template", "推薦來源", "recommendation_source"],
    "eligibility_label": ["eligible_label", "資格標籤", "必選推薦", "eligibility_label"],
    "policy_topic": ["topic", "議題", "policy_topic"],
    "classification_number": ["CIP", "分類號", "圖書分類號", "類號"],
    "award_notes": ["award_notes", "備註", "notes"],
}


def _normalize_header(value: str) -> str:
    return "".join(str(value).strip().lower().split())


def _match_columns(df_columns: list[str], hints: dict) -> tuple[dict, list[str]]:
    """Returns (mapping {src_col: sys_field}, unmapped_sys_fields)."""
    mapping = {}
    lower_cols = {_normalize_header(c): c for c in df_columns}
    for field, candidates in hints.items():
        for cand in candidates:
            key = _normalize_header(cand)
            if key in lower_cols:
                mapping[lower_cols[key]] = field
                break
    mapped_targets = set(mapping.values())
    unmapped = [field for field in hints if field not in mapped_targets]
    return mapping, unmapped


def _list_excel_sheets(file_bytes: bytes, engine: str) -> list[str]:
    """Return sheet names from an xls/xlsx/html-xls workbook."""
    if engine == "html":
        tables = _parse_html_tables(file_bytes)
        if not tables:
            raise ValueError("檔案中未找到任何表格資料")
        return [f"Table {i + 1}" for i in range(len(tables))]
    if engine == "openpyxl":
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
        sheets = list(wb.sheetnames)
        wb.close()
    else:
        import xlrd

        wb = xlrd.open_workbook(file_contents=file_bytes)
        sheets = wb.sheet_names()
    return sheets


def _read_raw_sheet(
    file_bytes: bytes,
    engine: str,
    sheet_name=0,
    header=None,
    nrows: int | None = None,
) -> pd.DataFrame:
    """Read a sheet into a DataFrame (dtype=str) for openpyxl, xlrd, or HTML-disguised .xls."""
    if engine == "html":
        tables = _parse_html_tables(file_bytes)
        if not tables:
            raise ValueError("檔案中未找到任何表格資料")
        if isinstance(sheet_name, int):
            idx = sheet_name
        elif isinstance(sheet_name, str):
            m = re.fullmatch(r"Table\s+(\d+)", sheet_name.strip(), re.IGNORECASE)
            if m:
                idx = int(m.group(1)) - 1
            elif sheet_name.strip().isdigit():
                idx = int(sheet_name.strip())
            else:
                raise ValueError(f"找不到工作表：{sheet_name}")
        else:
            idx = 0

        if idx < 0 or idx >= len(tables):
            raise ValueError(f"找不到工作表：{sheet_name}")

        raw_rows = tables[idx]
        max_cols = max((len(r) for r in raw_rows), default=0)
        if max_cols == 0:
            return pd.DataFrame()
        padded = [r + [""] * (max_cols - len(r)) for r in raw_rows]

        if header is None:
            selected = padded[:nrows] if nrows is not None else padded
            return pd.DataFrame(selected, dtype=str)

        header_idx = int(header)
        if header_idx < 0 or header_idx >= len(padded):
            return pd.DataFrame()

        raw_header = padded[header_idx]
        columns = [cell if cell else f"Unnamed: {i}" for i, cell in enumerate(raw_header)]
        data_rows = padded[header_idx + 1 :]
        if nrows is not None:
            data_rows = data_rows[:nrows]
        normalized_rows = [[cell if cell != "" else None for cell in r] for r in data_rows]
        return pd.DataFrame(normalized_rows, columns=columns, dtype=str)

    return pd.read_excel(
        io.BytesIO(file_bytes),
        engine=engine,
        sheet_name=sheet_name,
        header=header,
        nrows=nrows,
        dtype=str,
    )


def _detect_header_row(file_bytes: bytes, engine: str, hints: dict, sheet_name=0) -> int:
    """Score first 20 rows and return the best 0-based header row index."""
    preview = _read_raw_sheet(
        file_bytes,
        engine,
        sheet_name=sheet_name,
        header=None,
        nrows=20,
    )
    hint_tokens = {str(token).strip().lower() for candidates in hints.values() for token in candidates}
    best_row = 0
    best_score = -1
    for idx, row in preview.iterrows():
        values = [str(v).strip().lower() for v in row.tolist() if pd.notna(v)]
        score = sum(1 for value in values if value in hint_tokens)
        if score > best_score:
            best_score = score
            best_row = int(idx)
    return best_row


def _read_excel_with_detected_header(
    file_bytes: bytes,
    engine: str,
    hints: dict,
    sheet_name=0,
) -> pd.DataFrame:
    best_row = _detect_header_row(file_bytes, engine, hints, sheet_name=sheet_name)
    return _read_raw_sheet(
        file_bytes,
        engine,
        sheet_name=sheet_name,
        header=best_row,
    )


def _is_blank_or_total_row(values: list) -> bool:
    cleaned = [str(v).strip() for v in values if v not in (None, "") and not pd.isna(v)]
    if not cleaned:
        return True
    return any(value in {"合計", "總計"} for value in cleaned)


def _recommend_import_profile(source_columns: list[str]) -> dict | None:
    """Find the best matching vendor_books import profile by normalized header overlap."""
    if not source_columns:
        return None
    source_norm = {_normalize_header(c) for c in source_columns if _normalize_header(c)}
    if not source_norm:
        return None

    try:
        with db_session(get_connection) as conn:
            rows = conn.execute(
                "SELECT id, name, header_row, mappings, column_mappings, extra_field_settings "
                "FROM import_profiles "
                "WHERE file_type = 'vendor_books' "
                "ORDER BY id DESC"
            ).fetchall()
    except Exception:
        return None

    best_match: dict | None = None
    best_key: tuple[float, int, int] = (0.0, 0, 0)

    for row in rows:
        raw_mappings = row["mappings"] or row["column_mappings"]
        if not raw_mappings:
            continue
        try:
            mappings_dict = json.loads(raw_mappings)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(mappings_dict, dict):
            continue

        profile_norm = {
            _normalize_header(str(src_col))
            for src_col in mappings_dict.values()
            if src_col and _normalize_header(str(src_col))
        }
        if not profile_norm:
            continue

        matched = len(profile_norm & source_norm)
        total = len(profile_norm)
        overlap_ratio = matched / total
        if matched < 2 or overlap_ratio < 0.5:
            continue

        extra_settings: list[str] = []
        raw_extra = row["extra_field_settings"]
        if raw_extra:
            try:
                parsed_extra = json.loads(raw_extra)
                if isinstance(parsed_extra, list):
                    extra_settings = [str(item) for item in parsed_extra if item]
            except (TypeError, json.JSONDecodeError):
                extra_settings = []

        rank_key = (overlap_ratio, matched, int(row["id"]))
        if rank_key > best_key:
            best_key = rank_key
            best_match = {
                "id": row["id"],
                "name": row["name"],
                "header_row": row["header_row"] if row["header_row"] is not None else 0,
                "mappings": mappings_dict,
                "extra_field_settings": extra_settings,
                "matched_columns": matched,
                "total_profile_columns": total,
                "overlap_ratio": round(overlap_ratio, 4),
            }

    return best_match


def preview_excel(
    file_bytes: bytes,
    filename: str,
    sheet_name: str | None = None,
    header_row: int | None = None,
) -> dict:
    """
    Preview Excel without writing to DB.
    Returns sheet list, guessed header row (0-based), source columns, and suggested field mappings.
    header_row input is 0-based (pandas convention).
    """
    engine = _detect_file_engine(file_bytes, filename)
    sheets = _list_excel_sheets(file_bytes, engine)

    active_sheet = sheet_name if sheet_name else (sheets[0] if sheets else 0)

    if header_row is None:
        guessed_header_row = _detect_header_row(file_bytes, engine, VENDOR_COLUMN_HINTS, sheet_name=active_sheet)
    else:
        guessed_header_row = header_row

    df = _read_raw_sheet(
        file_bytes,
        engine,
        sheet_name=active_sheet,
        header=guessed_header_row,
        nrows=1,
    )

    source_columns = []
    for c in df.columns:
        cs = str(c).strip()
        if cs and not cs.lower().startswith("unnamed:"):
            source_columns.append(cs)

    src_to_sys, unmapped_sys = _match_columns(source_columns, VENDOR_COLUMN_HINTS)
    suggested_mappings = {v: k for k, v in src_to_sys.items()}

    mapped_source = set(src_to_sys.keys())
    extra_source_columns = [c for c in source_columns if c not in mapped_source]
    recommended_profile = _recommend_import_profile(source_columns)

    return {
        "sheets": sheets,
        "active_sheet": str(active_sheet),
        "guessed_header_row": guessed_header_row,
        "source_columns": source_columns,
        "suggested_mappings": suggested_mappings,
        "unmapped_system_fields": unmapped_sys,
        "extra_source_columns": extra_source_columns,
        "recommended_profile": recommended_profile,
    }


def preview_award_groups(
    file_bytes: bytes,
    filename: str,
    sheet_name: str | None,
    header_row: int,
    mappings: dict,
    project_type: str = "general_books",
) -> list[dict]:
    """
    Parse vendor Excel file and return grouped award normalization suggestions without writing to DB.
    """
    award_col = mappings.get("award_item")
    if not award_col:
        raise ValueError("尚未對應獲獎項目欄位")

    engine = _detect_file_engine(file_bytes, filename)
    sheet = sheet_name if sheet_name else 0
    df = _read_raw_sheet(
        file_bytes,
        engine,
        sheet_name=sheet,
        header=header_row,
    )
    df.columns = [str(c).strip() for c in df.columns]

    rows: list[dict] = []
    for _, row in df.iterrows():
        raw = {col: (None if pd.isna(row[col]) else str(row[col]).strip()) for col in df.columns}

        def get_field(sys_field: str):
            src_col = mappings.get(sys_field)
            if src_col:
                v = raw.get(src_col)
                return v if v else None
            return None

        isbn_raw = get_field("isbn")
        title = get_field("title")
        if _is_blank_or_total_row([isbn_raw, title, get_field("author"), get_field("publisher")]):
            continue

        rows.append(
            {
                "award_item": get_field("award_item"),
                "title": title,
            }
        )

    return group_normalize(rows, project_type=project_type)


_VENDOR_BOOKS_INSERT_SQL = (
    "INSERT INTO vendor_books"
    "(batch_id, award_item, vendor_seq, title, author, isbn, isbn_normalized, "
    "publish_date, list_price, purchase_price, publisher, age_range, "
    "isbn_status, completeness_status, extra_fields, source_row_number, raw_row, "
    "category, book_type, policy_topic, summary, source_url, recommendation_source, "
    "eligibility_label, classification_number, award_notes) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

_VENDOR_BOOKS_UPDATE_SQL = (
    "UPDATE vendor_books SET "
    "batch_id = ?, award_item = ?, vendor_seq = ?, title = ?, author = ?, isbn = ?, isbn_normalized = ?, "
    "publish_date = ?, list_price = ?, purchase_price = ?, publisher = ?, age_range = ?, "
    "isbn_status = ?, completeness_status = ?, extra_fields = ?, source_row_number = ?, raw_row = ?, "
    "category = ?, book_type = ?, policy_topic = ?, summary = ?, source_url = ?, recommendation_source = ?, "
    "eligibility_label = ?, classification_number = ?, award_notes = ? "
    "WHERE id = ?"
)


def _insert_vendor_books_core(
    conn,
    df: pd.DataFrame,
    project_id: int | None,
    proj_type: str | None,
    filename: str,
    mappings: dict,
    extra_field_settings: list | None,
    user_id: int,
    profile_id: int | None,
    header_row: int | None,
    pp_formula_map: dict,
    record_row_numbers: bool,
    award_overrides: dict | None = None,
    vendor_name: str | None = None,
    import_mode: str = "upsert",
) -> dict:
    """
    Shared core logic for inserting/upserting vendor_books rows into the shared catalog pool.
    mappings is {sys_field: src_col}.
    Returns summary dict. Does NOT commit.
    """
    _ = project_id
    if import_mode not in VALID_IMPORT_MODES:
        raise ValueError(f"不支援的匯入模式：{import_mode}（僅支援 upsert 或 replace_vendor）")

    normalized_vendor = normalize_vendor_name(vendor_name)
    now = datetime.now(timezone.utc).isoformat()

    parsed_rows: list[dict] = []
    skipped_count = 0

    for enum_idx, (_, row) in enumerate(df.iterrows()):
        raw = {col: (None if pd.isna(row[col]) else str(row[col]).strip()) for col in df.columns}
        source_row_number = (header_row + 2 + enum_idx) if (record_row_numbers and header_row is not None) else None

        def get_field(sys_field: str):
            src_col = mappings.get(sys_field)
            if src_col:
                v = raw.get(src_col)
                return v if v else None
            return None

        isbn_raw = get_field("isbn")
        title = get_field("title")
        if _is_blank_or_total_row([isbn_raw, title, get_field("author"), get_field("publisher")]):
            skipped_count += 1
            continue

        isbn_norm = normalize_isbn(isbn_raw)
        isbn_status = get_isbn_status(isbn_raw)

        extra_fields = {}
        for col_name in extra_field_settings or []:
            val = raw.get(col_name)
            if val:
                extra_fields[col_name] = val

        list_price = _to_float(get_field("list_price"))
        purchase_price = _to_float(get_field("purchase_price"))
        if purchase_price is None and list_price is not None:
            formula = pp_formula_map.get(enum_idx)
            if formula:
                purchase_price = _resolve_formula_purchase_price(formula, list_price)

        award_item = get_field("award_item")
        raw_award = (award_item or "").strip()
        override = award_overrides.get(raw_award) if award_overrides else None
        has_award_override = isinstance(override, dict)
        if has_award_override:
            recommendation_source = override.get("recommendation_source") or None
            eligibility_label = override.get("eligibility_label") or None
            award_notes = override.get("award_notes") or None
        else:
            recommendation_source = get_field("recommendation_source")
            eligibility_label = get_field("eligibility_label")
            award_notes = get_field("award_notes")

        parsed_rows.append(
            {
                "award_item": award_item,
                "vendor_seq": get_field("vendor_seq"),
                "title": title,
                "author": get_field("author"),
                "isbn": isbn_raw,
                "isbn_normalized": isbn_norm,
                "publish_date": get_field("publish_date"),
                "list_price": list_price,
                "purchase_price": purchase_price,
                "publisher": get_field("publisher"),
                "age_range": get_field("age_range"),
                "isbn_status": isbn_status,
                "extra_fields": json.dumps(extra_fields, ensure_ascii=False) if extra_fields else None,
                "source_row_number": source_row_number,
                "raw_row": json.dumps(raw, ensure_ascii=False),
                "category": get_field("category"),
                "book_type": get_field("book_type"),
                "policy_topic": get_field("policy_topic"),
                "summary": get_field("summary"),
                "source_url": get_field("source_url"),
                "recommendation_source": recommendation_source,
                "eligibility_label": eligibility_label,
                "classification_number": get_field("classification_number"),
                "award_notes": award_notes,
                "has_award_override": has_award_override,
            }
        )

    if not parsed_rows:
        raise ValueError("未解析到任何有效書目資料，已保留原有書單")

    if import_mode == "replace_vendor":
        _clear_vendor_books_by_vendor(conn, normalized_vendor)

    batch_row = conn.execute(
        "INSERT INTO import_batches(project_id, batch_type, original_filename, profile_id, "
        "vendor_name, imported_by, imported_at) VALUES (NULL, 'vendor_books', ?, ?, ?, ?, ?)",
        (filename, profile_id, normalized_vendor, user_id, now),
    )
    batch_id = batch_row.lastrowid

    inserted_count = 0
    updated_count = 0
    preserved_override_count = 0

    if import_mode == "replace_vendor":
        rows_to_insert: list[tuple] = []
        for item in parsed_rows:
            completeness = compute_completeness(item, project_type=proj_type)
            rows_to_insert.append(
                (
                    batch_id,
                    item["award_item"],
                    item["vendor_seq"],
                    item["title"],
                    item["author"],
                    item["isbn"],
                    item["isbn_normalized"],
                    item["publish_date"],
                    item["list_price"],
                    item["purchase_price"],
                    item["publisher"],
                    item["age_range"],
                    item["isbn_status"],
                    completeness,
                    item["extra_fields"],
                    item["source_row_number"],
                    item["raw_row"],
                    item["category"],
                    item["book_type"],
                    item["policy_topic"],
                    item["summary"],
                    item["source_url"],
                    item["recommendation_source"],
                    item["eligibility_label"],
                    item["classification_number"],
                    item["award_notes"],
                )
            )
        conn.executemany(_VENDOR_BOOKS_INSERT_SQL, rows_to_insert)
        inserted_count = len(rows_to_insert)
    else:
        existing_rows = conn.execute(
            "SELECT vb.id, vb.isbn_normalized, vb.user_overrides, "
            "vb.recommendation_source, vb.eligibility_label, vb.award_notes "
            "FROM vendor_books vb "
            "JOIN import_batches ib ON ib.id = vb.batch_id "
            "WHERE ib.batch_type = 'vendor_books' "
            "  AND COALESCE(NULLIF(TRIM(ib.vendor_name), ''), ?) = ? "
            "  AND vb.isbn_status = 'valid' "
            "  AND vb.isbn_normalized IS NOT NULL "
            "ORDER BY vb.id ASC",
            (DEFAULT_VENDOR_NAME, normalized_vendor),
        ).fetchall()
        existing_by_isbn: dict[str, dict] = {r["isbn_normalized"]: dict(r) for r in existing_rows}

        update_rows_by_id: dict[int, tuple] = {}
        insert_rows: list[tuple] = []
        insert_index_by_isbn: dict[str, int] = {}
        preserved_ids: set[int] = set()

        for item in parsed_rows:
            isbn_norm = item["isbn_normalized"]
            existing = existing_by_isbn.get(isbn_norm) if (item["isbn_status"] == "valid" and isbn_norm) else None

            if existing is not None:
                existing_id = int(existing["id"])
                existing_overrides_raw = existing.get("user_overrides")
                try:
                    existing_overrides = json.loads(existing_overrides_raw) if existing_overrides_raw else {}
                except (TypeError, json.JSONDecodeError):
                    existing_overrides = {}
                if not isinstance(existing_overrides, dict):
                    existing_overrides = {}

                if existing_overrides and existing_id not in preserved_ids:
                    preserved_ids.add(existing_id)
                    preserved_override_count += 1

                if not item["has_award_override"]:
                    rec_source = existing.get("recommendation_source") or item["recommendation_source"]
                    elig_label = existing.get("eligibility_label") or item["eligibility_label"]
                    award_notes = existing.get("award_notes") or item["award_notes"]
                else:
                    rec_source = item["recommendation_source"]
                    elig_label = item["eligibility_label"]
                    award_notes = item["award_notes"]

                merged_book = {
                    "title": item["title"],
                    "list_price": item["list_price"],
                    "purchase_price": item["purchase_price"],
                    "author": item["author"],
                    "publisher": item["publisher"],
                    "award_item": item["award_item"],
                    "eligibility_label": elig_label,
                    "recommendation_source": rec_source,
                }
                completeness = compute_completeness(merged_book, overrides=existing_overrides, project_type=proj_type)

                update_rows_by_id[existing_id] = (
                    batch_id,
                    item["award_item"],
                    item["vendor_seq"],
                    item["title"],
                    item["author"],
                    item["isbn"],
                    item["isbn_normalized"],
                    item["publish_date"],
                    item["list_price"],
                    item["purchase_price"],
                    item["publisher"],
                    item["age_range"],
                    item["isbn_status"],
                    completeness,
                    item["extra_fields"],
                    item["source_row_number"],
                    item["raw_row"],
                    item["category"],
                    item["book_type"],
                    item["policy_topic"],
                    item["summary"],
                    item["source_url"],
                    rec_source,
                    elig_label,
                    item["classification_number"],
                    award_notes,
                    existing_id,
                )
                existing["recommendation_source"] = rec_source
                existing["eligibility_label"] = elig_label
                existing["award_notes"] = award_notes
            else:
                completeness = compute_completeness(item, project_type=proj_type)
                insert_tuple = (
                    batch_id,
                    item["award_item"],
                    item["vendor_seq"],
                    item["title"],
                    item["author"],
                    item["isbn"],
                    item["isbn_normalized"],
                    item["publish_date"],
                    item["list_price"],
                    item["purchase_price"],
                    item["publisher"],
                    item["age_range"],
                    item["isbn_status"],
                    completeness,
                    item["extra_fields"],
                    item["source_row_number"],
                    item["raw_row"],
                    item["category"],
                    item["book_type"],
                    item["policy_topic"],
                    item["summary"],
                    item["source_url"],
                    item["recommendation_source"],
                    item["eligibility_label"],
                    item["classification_number"],
                    item["award_notes"],
                )
                if item["isbn_status"] == "valid" and isbn_norm and isbn_norm in insert_index_by_isbn:
                    insert_rows[insert_index_by_isbn[isbn_norm]] = insert_tuple
                else:
                    if item["isbn_status"] == "valid" and isbn_norm:
                        insert_index_by_isbn[isbn_norm] = len(insert_rows)
                    insert_rows.append(insert_tuple)

        if update_rows_by_id:
            conn.executemany(_VENDOR_BOOKS_UPDATE_SQL, list(update_rows_by_id.values()))
        if insert_rows:
            conn.executemany(_VENDOR_BOOKS_INSERT_SQL, insert_rows)
        updated_count = len(update_rows_by_id)
        inserted_count = len(insert_rows)

    record_count = inserted_count + updated_count
    conn.execute(
        "UPDATE import_batches SET record_count = ? WHERE id = ?",
        (record_count, batch_id),
    )
    return {
        "batch_id": batch_id,
        "vendor_name": normalized_vendor,
        "import_mode": import_mode,
        "record_count": record_count,
        "inserted_count": inserted_count,
        "updated_count": updated_count,
        "preserved_override_count": preserved_override_count,
        "skipped_count": skipped_count,
    }


def confirm_import(
    file_bytes: bytes,
    filename: str,
    project_id: int | None = None,
    sheet_name: str | None = None,
    header_row: int = 0,
    mappings: dict | None = None,
    extra_field_settings: list | None = None,
    user_id: int = 0,
    profile_id: int | None = None,
    award_overrides: dict | None = None,
    vendor_name: str | None = None,
    import_mode: str = "upsert",
) -> dict:
    """
    Formally import vendor books into the shared catalog pool using user-confirmed mappings (sys_field → src_col).
    header_row is 0-based.
    """
    if import_mode not in VALID_IMPORT_MODES:
        raise ValueError(f"不支援的匯入模式：{import_mode}（僅支援 upsert 或 replace_vendor）")

    mappings = mappings or {}
    extra_field_settings = extra_field_settings or []
    engine = _detect_file_engine(file_bytes, filename)
    sheet = sheet_name if sheet_name else 0

    pp_formula_map: dict = {}
    if engine == "openpyxl":
        pp_src_col = mappings.get("purchase_price")
        if pp_src_col:
            pp_formula_map = _build_formula_fallback(file_bytes, sheet, header_row, pp_src_col)

    df = _read_raw_sheet(
        file_bytes,
        engine,
        sheet_name=sheet,
        header=header_row,
    )
    df.columns = [str(c).strip() for c in df.columns]

    with db_session(get_connection) as conn:
        proj_type = None
        if project_id is not None:
            proj_row = conn.execute(
                "SELECT project_type FROM procurement_projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            proj_type = proj_row["project_type"] if proj_row else None
        result = _insert_vendor_books_core(
            conn=conn,
            df=df,
            project_id=project_id,
            proj_type=proj_type,
            filename=filename,
            mappings=mappings,
            extra_field_settings=extra_field_settings,
            user_id=user_id,
            profile_id=profile_id,
            header_row=header_row,
            pp_formula_map=pp_formula_map,
            record_row_numbers=True,
            award_overrides=award_overrides,
            vendor_name=vendor_name,
            import_mode=import_mode,
        )
        conn.commit()

    try:
        result["match_stats"] = run_match(project_id)
    except Exception as e:
        result["match_rerun_error"] = str(e)
    return result


def _holding_dedup_key(
    isbn_normalized: str | None,
    library_record_id: str | None,
    title: str | None,
) -> tuple[str, str, str]:
    rec_id = (library_record_id or "").strip()
    if rec_id:
        return ("rid", isbn_normalized or "", rec_id)
    title_key = normalize_title_for_match(title) or (title or "").strip().lower()
    return ("title", isbn_normalized or "", title_key)


def _rerun_match_after_holdings_change(result: dict) -> None:
    try:
        with db_session(get_connection) as conn2:
            vendor_book_exists = (
                conn2.execute(
                    "SELECT 1 FROM vendor_books vb "
                    "JOIN import_batches ib ON ib.id = vb.batch_id "
                    "WHERE ib.batch_type = 'vendor_books' LIMIT 1"
                ).fetchone()
                is not None
            )
            legacy_project_ids = [
                r[0]
                for r in conn2.execute(
                    "SELECT DISTINCT project_id FROM import_batches "
                    "WHERE batch_type='vendor_books' AND project_id IS NOT NULL"
                ).fetchall()
            ]
        if vendor_book_exists:
            stats = run_match()
            result["match_stats"] = stats
            result["match_rerun"] = True
            if "affected_projects" in result and "match_stats_by_project" in result:
                for pid in legacy_project_ids:
                    result["affected_projects"].append(pid)
                    result["match_stats_by_project"][str(pid)] = stats
    except Exception as e:
        result["match_rerun_error"] = str(e)


def import_library_holdings(
    file_bytes: bytes,
    filename: str,
    user_id: int,
    profile_id: int | None = None,
    column_overrides: dict | None = None,
    import_mode: str = "replace",
) -> dict:
    if import_mode not in VALID_HOLDINGS_IMPORT_MODES:
        raise ValueError(f"不支援的館藏匯入模式：{import_mode}（僅支援 replace 或 append）")

    now = datetime.now(timezone.utc).isoformat()
    engine = _detect_file_engine(file_bytes, filename)
    sheets = _list_excel_sheets(file_bytes, engine)

    with db_session(get_connection) as conn:
        seen_keys: set[tuple[str, str, str]] | None = None
        if import_mode == "replace":
            _clear_library_holdings(conn)
        else:
            existing_rows = conn.execute(
                "SELECT isbn_normalized, library_record_id, title FROM library_holdings"
            ).fetchall()
            seen_keys = {
                _holding_dedup_key(r["isbn_normalized"], r["library_record_id"], r["title"]) for r in existing_rows
            }

        all_rows_to_insert: list[tuple] = []
        skipped_duplicate_count = 0
        sheet_summaries = []
        skipped_sheets = []
        last_mapping: dict = {}
        last_unmapped: list = []

        for sheet_name in sheets:
            sheet_res = _read_library_sheet(file_bytes, engine, sheet_name)
            if sheet_res is None:
                skipped_sheets.append({"sheet_name": str(sheet_name), "reason": "無 isbn 或 title 欄位"})
                continue
            df, mapping, unmapped = sheet_res
            if column_overrides:
                mapping.update(column_overrides)
            sheet_rows, sheet_skipped = _collect_library_holding_rows(df, mapping, seen_keys=seen_keys)
            all_rows_to_insert.extend(sheet_rows)
            skipped_duplicate_count += sheet_skipped
            sheet_summaries.append(
                {
                    "sheet_name": str(sheet_name),
                    "record_count": len(sheet_rows),
                    "skipped_duplicate_count": sheet_skipped,
                }
            )
            last_mapping, last_unmapped = mapping, unmapped

        records_inserted = len(all_rows_to_insert)
        if records_inserted == 0 and skipped_duplicate_count == 0:
            raise ValueError("館藏檔案未匯入任何有效資料，請確認 Excel 格式與欄位名稱")

        batch_id: int | None = None
        if records_inserted > 0:
            batch_row = conn.execute(
                "INSERT INTO import_batches(project_id, batch_type, original_filename, profile_id, "
                "record_count, imported_by, imported_at) VALUES (NULL, 'library_holdings', ?, ?, ?, ?, ?)",
                (filename, profile_id, records_inserted, user_id, now),
            )
            batch_id = batch_row.lastrowid
            conn.executemany(
                "INSERT INTO library_holdings"
                "(batch_id, isbn, isbn_normalized, title, author, publisher, publish_year, "
                "price, library_record_id, isbn_status, raw_row) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(batch_id, *row) for row in all_rows_to_insert],
            )
            conn.commit()

    result: dict = {
        "batch_id": batch_id,
        "import_mode": import_mode,
        "replaced": import_mode == "replace",
        "record_count": records_inserted,
        "skipped_duplicate_count": skipped_duplicate_count,
        "sheet_summaries": sheet_summaries,
        "skipped_sheets": skipped_sheets,
        "unmapped_fields": last_unmapped,
        "column_mapping": last_mapping,
        "match_rerun": False,
        "affected_projects": [],
        "match_stats_by_project": {},
    }
    if records_inserted > 0:
        _rerun_match_after_holdings_change(result)
    return result


def commit_project_selections_to_holdings(project_id: int, user_id: int) -> dict:
    """Commit a project's selected books (selected_quantity > 0) into library_holdings idempotently."""
    now = datetime.now(timezone.utc).isoformat()
    with db_session(get_connection) as conn:
        project = conn.execute(
            "SELECT id, name FROM procurement_projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        if project is None:
            raise LookupError("採購專案不存在")
        project_name = str(project["name"])

        items = conn.execute(
            "SELECT id, title, author, publisher, isbn, isbn_normalized, isbn_status, "
            "publish_date, list_price, purchase_price, user_overrides "
            "FROM selection_items "
            "WHERE project_id = ? AND selected_quantity > 0 "
            "ORDER BY id ASC",
            (project_id,),
        ).fetchall()
        if not items:
            raise ValueError("本專案尚無已選購書目，無法記入館藏")

        existing_rows = conn.execute(
            "SELECT isbn_normalized, library_record_id FROM library_holdings "
            "WHERE library_record_id IS NOT NULL AND TRIM(library_record_id) != ''"
        ).fetchall()
        existing_record_ids: set[str] = set()
        existing_isbn_rid: set[tuple[str, str]] = set()
        for r in existing_rows:
            rid = str(r["library_record_id"]).strip()
            existing_record_ids.add(rid)
            existing_isbn_rid.add((r["isbn_normalized"] or "", rid))

        rows_to_insert: list[tuple] = []
        skipped_count = 0

        for si in items:
            raw_ov = si["user_overrides"]
            try:
                overrides = json.loads(raw_ov) if raw_ov else {}
            except (TypeError, json.JSONDecodeError):
                overrides = {}
            if not isinstance(overrides, dict):
                overrides = {}

            def _pick(field: str, _si=si, _ov=overrides):
                val = _ov.get(field)
                if val not in (None, ""):
                    return val
                return _si[field]

            title_val = _pick("title")
            author_val = _pick("author")
            publisher_val = _pick("publisher")
            isbn_val = _pick("isbn")
            pub_date_val = _pick("publish_date")

            title = str(title_val).strip() if title_val not in (None, "") else None
            author = str(author_val).strip() if author_val not in (None, "") else None
            publisher = str(publisher_val).strip() if publisher_val not in (None, "") else None
            isbn_raw = str(isbn_val).strip() if isbn_val not in (None, "") else None
            isbn_norm = normalize_isbn(isbn_raw)
            isbn_status = get_isbn_status(isbn_raw)
            publish_year = str(pub_date_val).strip() if pub_date_val not in (None, "") else None

            price = _to_float(_pick("purchase_price"))
            if price is None:
                price = _to_float(_pick("list_price"))

            library_record_id = f"PO-{project_id}-{si['id']}"
            if library_record_id in existing_record_ids or (isbn_norm or "", library_record_id) in existing_isbn_rid:
                skipped_count += 1
                continue

            existing_record_ids.add(library_record_id)
            existing_isbn_rid.add((isbn_norm or "", library_record_id))

            raw_row = json.dumps(
                {
                    "source": "procurement_commit",
                    "project_id": project_id,
                    "project_name": project_name,
                    "selection_item_id": si["id"],
                    "title": title,
                    "author": author,
                    "publisher": publisher,
                    "isbn": isbn_raw,
                    "publish_year": publish_year,
                    "price": price,
                },
                ensure_ascii=False,
            )
            rows_to_insert.append(
                (
                    isbn_raw,
                    isbn_norm,
                    title,
                    author,
                    publisher,
                    publish_year,
                    price,
                    library_record_id,
                    isbn_status,
                    raw_row,
                )
            )

        inserted_count = len(rows_to_insert)
        batch_id: int | None = None
        if inserted_count > 0:
            batch_row = conn.execute(
                "INSERT INTO import_batches(project_id, batch_type, original_filename, record_count, "
                "imported_by, imported_at) VALUES (NULL, 'library_holdings', ?, ?, ?, ?)",
                (f"採購回流：{project_name}", inserted_count, user_id, now),
            )
            batch_id = batch_row.lastrowid
            conn.executemany(
                "INSERT INTO library_holdings"
                "(batch_id, isbn, isbn_normalized, title, author, publisher, publish_year, "
                "price, library_record_id, isbn_status, raw_row) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(batch_id, *row) for row in rows_to_insert],
            )
            conn.commit()

    result: dict = {
        "project_id": project_id,
        "project_name": project_name,
        "batch_id": batch_id,
        "inserted_count": inserted_count,
        "skipped_count": skipped_count,
        "match_rerun": False,
        "match_stats": None,
    }
    if inserted_count > 0:
        _rerun_match_after_holdings_change(result)
    return result


def import_vendor_books(
    file_bytes: bytes,
    filename: str,
    project_id: int | None = None,
    user_id: int = 0,
    profile_id: int | None = None,
    column_overrides: dict | None = None,
    vendor_name: str | None = None,
    import_mode: str = "upsert",
) -> dict:
    """Legacy single-step import with auto-detected column mapping."""
    if import_mode not in VALID_IMPORT_MODES:
        raise ValueError(f"不支援的匯入模式：{import_mode}（僅支援 upsert 或 replace_vendor）")

    engine = _detect_file_engine(file_bytes, filename)
    header_row = _detect_header_row(file_bytes, engine, VENDOR_COLUMN_HINTS)
    df = _read_raw_sheet(
        file_bytes,
        engine,
        sheet_name=0,
        header=header_row,
    )
    df.columns = [str(c).strip() for c in df.columns]
    mapping, unmapped = _match_columns(list(df.columns), VENDOR_COLUMN_HINTS)
    if column_overrides:
        mapping.update(column_overrides)

    reverse_map = {v: k for k, v in mapping.items()}
    pp_formula_map: dict = {}
    if engine == "openpyxl":
        pp_src_col = reverse_map.get("purchase_price")
        if pp_src_col:
            pp_formula_map = _build_formula_fallback(file_bytes, 0, header_row, pp_src_col)

    with db_session(get_connection) as conn:
        proj_type = None
        if project_id is not None:
            proj_row = conn.execute(
                "SELECT project_type FROM procurement_projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            proj_type = proj_row["project_type"] if proj_row else None
        result = _insert_vendor_books_core(
            conn=conn,
            df=df,
            project_id=project_id,
            proj_type=proj_type,
            filename=filename,
            mappings=reverse_map,
            extra_field_settings=None,
            user_id=user_id,
            profile_id=profile_id,
            header_row=header_row,
            pp_formula_map=pp_formula_map,
            record_row_numbers=False,
            vendor_name=vendor_name,
            import_mode=import_mode,
        )
        conn.commit()

    result["unmapped_fields"] = unmapped
    result["column_mapping"] = mapping
    try:
        result["match_stats"] = run_match(project_id)
    except Exception as e:
        result["match_rerun_error"] = str(e)
    return result


def _to_float(v) -> float | None:
    if v is None:
        return None
    try:
        cleaned = _CURRENCY_CLEAN_RE.sub("", str(v))
        if not cleaned:
            return None
        val = float(cleaned)
        return val if math.isfinite(val) else None
    except (ValueError, TypeError):
        return None


def _parse_formula_multiplier(formula: str) -> float | None:
    """Extract multiplier from patterns like *75% or *0.75 → 0.75."""
    m = re.search(r"\*\s*(\d+(?:\.\d+)?)\s*%", formula)
    if m:
        return float(m.group(1)) / 100
    m = re.search(r"\*\s*(0?\.\d+)", formula)
    if m:
        return float(m.group(1))
    return None


def _resolve_formula_purchase_price(formula: str, list_price: float | None) -> float | None:
    """
    Compute purchase_price from a formula string and list_price.
    Supports =ROUND(ref*N%,0) and =ref*N%. Returns None if pattern unrecognised.
    """
    if list_price is None:
        return None
    multiplier = _parse_formula_multiplier(formula)
    if multiplier is None:
        return None
    if re.search(r"ROUND\s*\(", formula, re.IGNORECASE):
        return float(math.floor(list_price * multiplier + 0.5))
    return list_price * multiplier


def _build_formula_fallback(file_bytes: bytes, sheet, header_row: int, pp_src_col: str) -> dict:
    """
    Return {data_row_0based: formula_string} for the purchase_price column.
    data_row_0based=0 is the first data row (DataFrame index 0).
    Reads openpyxl with data_only=False to capture formula strings.
    Silently returns {} on any error.
    """
    try:
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(file_bytes), data_only=False, read_only=True)
        ws = wb[sheet] if isinstance(sheet, str) else list(wb.worksheets)[int(sheet) if sheet else 0]

        # Locate the purchase_price column by header name (Excel rows are 1-based)
        excel_header_row = header_row + 1
        pp_col_idx = None
        for header_cells in ws.iter_rows(min_row=excel_header_row, max_row=excel_header_row):
            for cell in header_cells:
                if cell.value and str(cell.value).strip() == pp_src_col:
                    pp_col_idx = cell.column
                    break

        if pp_col_idx is None:
            wb.close()
            return {}

        # Data rows start at header_row + 2 (Excel 1-based)
        # data_row_0based = cell.row - (header_row + 2), aligns with DataFrame enum_idx
        excel_data_start = header_row + 2
        formula_map: dict = {}
        for row in ws.iter_rows(min_row=excel_data_start, min_col=pp_col_idx, max_col=pp_col_idx):
            for cell in row:
                val = cell.value
                if val and isinstance(val, str) and val.startswith("="):
                    formula_map[cell.row - excel_data_start] = val

        wb.close()
        return formula_map
    except Exception:
        return {}


def _clear_library_holdings(conn) -> None:
    """
    Remove all library_holdings source data.
    Deletion order: book_matches (holding refs) → library_holdings → import_batches.
    Does NOT commit — caller owns the transaction.
    """
    conn.execute("DELETE FROM book_matches WHERE holding_id IS NOT NULL")
    conn.execute("DELETE FROM library_holdings")
    batch_ids = [
        r[0] for r in conn.execute("SELECT id FROM import_batches WHERE batch_type='library_holdings'").fetchall()
    ]
    if batch_ids:
        ph = ",".join("?" * len(batch_ids))
        conn.execute(f"DELETE FROM import_batches WHERE id IN ({ph})", batch_ids)


def _clear_vendor_books_for_project(conn, project_id: int) -> tuple[int, int, int]:
    """
    Remove legacy vendor_books-related source data bound to a specific project_id.
    Deletion order: book_matches → vendor_books → import_batches.
    selection_items are NOT deleted — they carry self-contained snapshots.
    Does NOT commit — caller owns the transaction.
    """
    vendor_books_count = conn.execute(
        "SELECT COUNT(*) FROM vendor_books vb "
        "JOIN import_batches ib ON ib.id = vb.batch_id "
        "WHERE ib.project_id = ? AND ib.batch_type = 'vendor_books'",
        (project_id,),
    ).fetchone()[0]
    matches_count = conn.execute(
        "SELECT COUNT(*) FROM book_matches bm "
        "JOIN vendor_books vb ON vb.id = bm.vendor_book_id "
        "JOIN import_batches ib ON ib.id = vb.batch_id "
        "WHERE ib.project_id = ? AND ib.batch_type = 'vendor_books'",
        (project_id,),
    ).fetchone()[0]
    batches_count = conn.execute(
        "SELECT COUNT(*) FROM import_batches WHERE project_id = ? AND batch_type = 'vendor_books'",
        (project_id,),
    ).fetchone()[0]

    if batches_count == 0:
        return 0, 0, 0

    conn.execute(
        "DELETE FROM book_matches WHERE vendor_book_id IN ("
        "  SELECT vb.id FROM vendor_books vb "
        "  JOIN import_batches ib ON ib.id = vb.batch_id "
        "  WHERE ib.project_id = ? AND ib.batch_type = 'vendor_books'"
        ")",
        (project_id,),
    )
    conn.execute(
        "DELETE FROM vendor_books WHERE batch_id IN ("
        "  SELECT id FROM import_batches WHERE project_id = ? AND batch_type = 'vendor_books'"
        ")",
        (project_id,),
    )
    conn.execute(
        "DELETE FROM import_batches WHERE project_id = ? AND batch_type = 'vendor_books'",
        (project_id,),
    )
    return vendor_books_count, matches_count, batches_count


def _clear_vendor_books_by_vendor(conn, vendor_name: str) -> tuple[int, int, int]:
    """
    Remove vendor_books-related source data for a specific normalized vendor_name.
    Deletion order: book_matches → vendor_books → import_batches.
    selection_items are NOT deleted. Does NOT commit.
    """
    normalized_vendor = normalize_vendor_name(vendor_name)
    vendor_books_count = conn.execute(
        "SELECT COUNT(*) FROM vendor_books vb "
        "JOIN import_batches ib ON ib.id = vb.batch_id "
        "WHERE ib.batch_type = 'vendor_books' "
        "  AND COALESCE(NULLIF(TRIM(ib.vendor_name), ''), ?) = ?",
        (DEFAULT_VENDOR_NAME, normalized_vendor),
    ).fetchone()[0]
    matches_count = conn.execute(
        "SELECT COUNT(*) FROM book_matches bm "
        "JOIN vendor_books vb ON vb.id = bm.vendor_book_id "
        "JOIN import_batches ib ON ib.id = vb.batch_id "
        "WHERE ib.batch_type = 'vendor_books' "
        "  AND COALESCE(NULLIF(TRIM(ib.vendor_name), ''), ?) = ?",
        (DEFAULT_VENDOR_NAME, normalized_vendor),
    ).fetchone()[0]
    batches_count = conn.execute(
        "SELECT COUNT(*) FROM import_batches "
        "WHERE batch_type = 'vendor_books' "
        "  AND COALESCE(NULLIF(TRIM(vendor_name), ''), ?) = ?",
        (DEFAULT_VENDOR_NAME, normalized_vendor),
    ).fetchone()[0]

    if batches_count == 0:
        return 0, 0, 0

    conn.execute(
        "DELETE FROM book_matches WHERE vendor_book_id IN ("
        "  SELECT vb.id FROM vendor_books vb "
        "  JOIN import_batches ib ON ib.id = vb.batch_id "
        "  WHERE ib.batch_type = 'vendor_books' "
        "    AND COALESCE(NULLIF(TRIM(ib.vendor_name), ''), ?) = ?"
        ")",
        (DEFAULT_VENDOR_NAME, normalized_vendor),
    )
    conn.execute(
        "DELETE FROM vendor_books WHERE batch_id IN ("
        "  SELECT id FROM import_batches "
        "  WHERE batch_type = 'vendor_books' "
        "    AND COALESCE(NULLIF(TRIM(vendor_name), ''), ?) = ?"
        ")",
        (DEFAULT_VENDOR_NAME, normalized_vendor),
    )
    conn.execute(
        "DELETE FROM import_batches "
        "WHERE batch_type = 'vendor_books' "
        "  AND COALESCE(NULLIF(TRIM(vendor_name), ''), ?) = ?",
        (DEFAULT_VENDOR_NAME, normalized_vendor),
    )
    return vendor_books_count, matches_count, batches_count


def _clear_all_vendor_books(conn) -> tuple[int, int, int]:
    """
    Remove all vendor_books source data across the shared catalog pool.
    selection_items are NOT deleted. Does NOT commit.
    """
    vendor_books_count = conn.execute(
        "SELECT COUNT(*) FROM vendor_books vb "
        "JOIN import_batches ib ON ib.id = vb.batch_id "
        "WHERE ib.batch_type = 'vendor_books'"
    ).fetchone()[0]
    matches_count = conn.execute(
        "SELECT COUNT(*) FROM book_matches bm "
        "JOIN vendor_books vb ON vb.id = bm.vendor_book_id "
        "JOIN import_batches ib ON ib.id = vb.batch_id "
        "WHERE ib.batch_type = 'vendor_books'"
    ).fetchone()[0]
    batches_count = conn.execute("SELECT COUNT(*) FROM import_batches WHERE batch_type = 'vendor_books'").fetchone()[0]

    if batches_count == 0:
        return 0, 0, 0

    conn.execute(
        "DELETE FROM book_matches WHERE vendor_book_id IN ("
        "  SELECT vb.id FROM vendor_books vb "
        "  JOIN import_batches ib ON ib.id = vb.batch_id "
        "  WHERE ib.batch_type = 'vendor_books'"
        ")"
    )
    conn.execute(
        "DELETE FROM vendor_books WHERE batch_id IN (SELECT id FROM import_batches WHERE batch_type = 'vendor_books')"
    )
    conn.execute("DELETE FROM import_batches WHERE batch_type = 'vendor_books'")
    return vendor_books_count, matches_count, batches_count


def list_vendors() -> list[dict]:
    """Return summary of vendors present in the shared vendor catalog pool."""
    with db_session(get_connection) as conn:
        rows = conn.execute(
            "SELECT "
            "  COALESCE(NULLIF(TRIM(ib.vendor_name), ''), ?) AS vendor_name, "
            "  COUNT(vb.id) AS book_count, "
            "  COUNT(DISTINCT ib.id) AS batch_count, "
            "  MAX(ib.imported_at) AS last_imported_at "
            "FROM import_batches ib "
            "LEFT JOIN vendor_books vb ON vb.batch_id = ib.id "
            "WHERE ib.batch_type = 'vendor_books' "
            "GROUP BY COALESCE(NULLIF(TRIM(ib.vendor_name), ''), ?) "
            "ORDER BY last_imported_at DESC, vendor_name ASC",
            (DEFAULT_VENDOR_NAME, DEFAULT_VENDOR_NAME),
        ).fetchall()
    return [dict(r) for r in rows]


def clear_library_holdings(user_id: int) -> dict:
    _ = user_id
    with db_session(get_connection) as conn:
        holdings_count = conn.execute("SELECT COUNT(*) FROM library_holdings").fetchone()[0]
        matches_count = conn.execute("SELECT COUNT(*) FROM book_matches WHERE holding_id IS NOT NULL").fetchone()[0]
        batches_count = conn.execute(
            "SELECT COUNT(*) FROM import_batches WHERE batch_type='library_holdings'"
        ).fetchone()[0]
        _clear_library_holdings(conn)
        conn.commit()
    return {
        "deleted_holdings": holdings_count,
        "deleted_matches": matches_count,
        "deleted_batches": batches_count,
    }


def clear_vendor_books(
    project_id: int | None = None,
    user_id: int = 0,
    vendor_name: str | None = None,
    clear_all: bool = False,
) -> dict:
    _ = user_id
    with db_session(get_connection) as conn:
        if clear_all:
            vendor_books_count, matches_count, batches_count = _clear_all_vendor_books(conn)
            preserved_count = conn.execute("SELECT COUNT(*) FROM selection_items").fetchone()[0]
            conn.commit()
            return {
                "clear_all": True,
                "vendor_name": None,
                "project_id": project_id,
                "deleted_vendor_books": vendor_books_count,
                "deleted_matches": matches_count,
                "deleted_batches": batches_count,
                "preserved_selection_items": preserved_count,
            }

        if vendor_name is not None and vendor_name.strip():
            normalized_vendor = normalize_vendor_name(vendor_name)
            vendor_books_count, matches_count, batches_count = _clear_vendor_books_by_vendor(conn, normalized_vendor)
            preserved_count = conn.execute("SELECT COUNT(*) FROM selection_items").fetchone()[0]
            conn.commit()
            return {
                "clear_all": False,
                "vendor_name": normalized_vendor,
                "project_id": project_id,
                "deleted_vendor_books": vendor_books_count,
                "deleted_matches": matches_count,
                "deleted_batches": batches_count,
                "preserved_selection_items": preserved_count,
            }

        if project_id is not None:
            project = conn.execute("SELECT id FROM procurement_projects WHERE id=?", (project_id,)).fetchone()
            if project is None:
                raise ValueError(f"project_id {project_id} 不存在")
            vendor_books_count, matches_count, batches_count = _clear_vendor_books_for_project(conn, project_id)
            preserved_count = conn.execute(
                "SELECT COUNT(*) FROM selection_items WHERE project_id=?", (project_id,)
            ).fetchone()[0]
            conn.commit()
            return {
                "clear_all": False,
                "vendor_name": None,
                "project_id": project_id,
                "deleted_vendor_books": vendor_books_count,
                "deleted_matches": matches_count,
                "deleted_batches": batches_count,
                "preserved_selection_items": preserved_count,
            }

        raise ValueError("請指定 vendor_name、clear_all=true 或 project_id")


def _read_library_sheet(file_bytes: bytes, engine: str, sheet_name) -> tuple | None:
    """
    Detect header and match columns for one sheet.
    Returns (df, mapping, unmapped) if the sheet has isbn or title mapping, else None.
    """
    df = _read_excel_with_detected_header(file_bytes, engine, LIBRARY_COLUMN_HINTS, sheet_name=sheet_name)
    df.columns = [str(c).strip() for c in df.columns]
    mapping, unmapped = _match_columns(list(df.columns), LIBRARY_COLUMN_HINTS)
    if "isbn" not in mapping.values() and "title" not in mapping.values():
        return None
    return df, mapping, unmapped


def _collect_library_holding_rows(
    df,
    mapping: dict,
    seen_keys: set[tuple[str, str, str]] | None = None,
) -> tuple[list[tuple], int]:
    """Parse rows from one sheet for library_holdings insertion (without batch_id).

    When ``seen_keys`` is provided (append mode), deduplicates against existing keys
    and updates ``seen_keys`` in place to prevent within-file duplicates as well.
    Returns ``(rows_to_insert, skipped_duplicate_count)``.
    """
    reverse_map = {v: k for k, v in mapping.items()}
    rows_to_insert: list[tuple] = []
    skipped_duplicates = 0

    for _, row in df.iterrows():
        raw = {col: (None if pd.isna(row[col]) else str(row[col]).strip()) for col in df.columns}

        def get_field(field: str, _raw=raw):
            src = reverse_map.get(field)
            if src:
                v = _raw.get(src)
                return v if v else None
            return None

        isbn_raw = get_field("isbn")
        title = get_field("title")
        if _is_blank_or_total_row([isbn_raw, title, get_field("author"), get_field("publisher")]):
            continue
        isbn_norm = normalize_isbn(isbn_raw)
        isbn_status = get_isbn_status(isbn_raw)
        rec_id = get_field("library_record_id")

        if seen_keys is not None:
            key = _holding_dedup_key(isbn_norm, rec_id, title)
            if key in seen_keys:
                skipped_duplicates += 1
                continue
            seen_keys.add(key)

        rows_to_insert.append(
            (
                isbn_raw,
                isbn_norm,
                title,
                get_field("author"),
                get_field("publisher"),
                get_field("publish_year"),
                _to_float(get_field("price")),
                rec_id,
                isbn_status,
                json.dumps(raw, ensure_ascii=False),
            )
        )

    return rows_to_insert, skipped_duplicates


def _insert_library_holding_rows(
    conn,
    batch_id: int,
    df,
    mapping: dict,
    seen_keys: set[tuple[str, str, str]] | None = None,
) -> int:
    """Insert rows from one sheet into library_holdings using executemany. Returns count inserted."""
    rows_to_insert, _ = _collect_library_holding_rows(df, mapping, seen_keys=seen_keys)

    if rows_to_insert:
        conn.executemany(
            "INSERT INTO library_holdings"
            "(batch_id, isbn, isbn_normalized, title, author, publisher, publish_year, "
            "price, library_record_id, isbn_status, raw_row) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(batch_id, *row) for row in rows_to_insert],
        )

    return len(rows_to_insert)
