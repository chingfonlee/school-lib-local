import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import openpyxl

from app.database import get_connection
from app.services.validation_service import check_export_readiness

TEMPLATE_CONFIG = {
    "school_name_cell": "A3",
    "school_name_prefix": "校名：",
    "budget_cell": "E3",
    "budget_prefix": "本案核定金額：新臺幣",
    "budget_suffix": "元",
    "example_row": 5,
    "data_start_row": 6,
    "data_template_end_row": 55,
    "summary_row": 56,
    "col_seq": 1,
    "col_title": 2,
    "col_author": 3,
    "col_publisher": 4,
    "col_isbn": 5,
    "col_quantity": 6,
    "col_price": 7,
    "col_subtotal": 8,
    "col_award_item": 9,
    "col_notes": 10,
}


@dataclass
class ExportSettings:
    project_id: int
    school_name: str
    approved_budget: float | None
    price_field: str
    subtotal_mode: str
    template_path: str
    output_dir: str
    exported_by: int


def _resolve_field(book: dict, field: str) -> str:
    overrides = json.loads(book.get("user_overrides") or "{}")
    if field in overrides and overrides[field] not in (None, ""):
        return str(overrides[field])
    v = book.get(field)
    if v not in (None, ""):
        return str(v)
    raw = json.loads(book.get("raw_row") or "{}")
    rv = raw.get(field)
    if rv not in (None, ""):
        return str(rv)
    return ""


def _get_price(book: dict, price_field: str) -> float:
    overrides = json.loads(book.get("user_overrides") or "{}")
    val = overrides.get(price_field) or book.get(price_field)
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def export_local_culture(settings: ExportSettings) -> str:
    readiness = check_export_readiness(settings.project_id, settings.price_field)
    blocking = [d for d in readiness["details"] if not d["can_export"] and d["match_status"] != "already_owned"]
    if blocking:
        titles = "; ".join(d["title"] for d in blocking[:5])
        raise ValueError(f"以下書目缺少必填欄位無法匯出：{titles}")

    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_filename = f"本土文化採購書單_{ts}.xlsx"
    out_path = str(Path(settings.output_dir) / out_filename)

    shutil.copy2(settings.template_path, out_path)

    wb = openpyxl.load_workbook(out_path)
    ws = wb.active
    tc = TEMPLATE_CONFIG

    ws[tc["school_name_cell"]] = tc["school_name_prefix"] + settings.school_name
    if settings.approved_budget is not None:
        ws[tc["budget_cell"]] = tc["budget_prefix"] + f"{settings.approved_budget:,.0f}" + tc["budget_suffix"]

    for col in range(tc["col_title"], tc["col_notes"] + 1):
        ws.cell(row=tc["example_row"], column=col).value = None

    conn = get_connection()
    books = conn.execute(
        "SELECT vb.*, si.selected_quantity, si.notes as sel_notes, bm.match_status "
        "FROM selection_items si "
        "JOIN vendor_books vb ON vb.id = si.vendor_book_id "
        "LEFT JOIN book_matches bm ON bm.vendor_book_id = vb.id "
        "  AND bm.match_status != 'same_title_different_isbn' "
        "WHERE si.project_id = ? AND (bm.match_status = 'available' OR bm.match_status IS NULL) "
        "ORDER BY vb.vendor_seq, vb.id",
        (settings.project_id,),
    ).fetchall()
    conn.close()

    exportable = [dict(b) for b in books if b["selected_quantity"] > 0]

    data_start = tc["data_start_row"]
    template_end = tc["data_template_end_row"]
    summary_row = tc["summary_row"]

    extra_rows_needed = max(0, len(exportable) - (template_end - data_start + 1))
    if extra_rows_needed > 0:
        ws.insert_rows(summary_row, extra_rows_needed)
        summary_row += extra_rows_needed

    total_qty = 0
    total_amount = 0.0

    for i, book in enumerate(exportable):
        row = data_start + i
        if row > template_end + extra_rows_needed:
            break

        quantity = book["selected_quantity"]
        price = _get_price(book, settings.price_field)

        if settings.subtotal_mode == "quantity_times_list_price":
            subtotal = quantity * _get_price(book, "list_price")
        else:
            subtotal = quantity * _get_price(book, "purchase_price")

        ws.cell(row=row, column=tc["col_seq"]).value = i + 1
        ws.cell(row=row, column=tc["col_title"]).value = _resolve_field(book, "title")
        ws.cell(row=row, column=tc["col_author"]).value = _resolve_field(book, "author")
        ws.cell(row=row, column=tc["col_publisher"]).value = _resolve_field(book, "publisher")
        ws.cell(row=row, column=tc["col_isbn"]).value = (
            _resolve_field(book, "isbn_normalized") or _resolve_field(book, "isbn")
        )
        ws.cell(row=row, column=tc["col_quantity"]).value = quantity
        ws.cell(row=row, column=tc["col_price"]).value = price if price else None
        ws.cell(row=row, column=tc["col_subtotal"]).value = subtotal if subtotal else None
        ws.cell(row=row, column=tc["col_award_item"]).value = _resolve_field(book, "award_item")
        ws.cell(row=row, column=tc["col_notes"]).value = book.get("sel_notes") or None

        total_qty += quantity
        total_amount += subtotal

    ws.cell(row=summary_row, column=tc["col_quantity"]).value = total_qty
    ws.cell(row=summary_row, column=tc["col_subtotal"]).value = total_amount

    wb.save(out_path)

    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    row = conn.execute(
        "INSERT INTO export_jobs"
        "(project_id, school_name, approved_budget, price_field, subtotal_mode, "
        "template_path, output_filename, output_path, exported_by, exported_at, "
        "record_count, total_amount) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            settings.project_id,
            settings.school_name,
            settings.approved_budget,
            settings.price_field,
            settings.subtotal_mode,
            settings.template_path,
            out_filename,
            out_path,
            settings.exported_by,
            now,
            len(exportable),
            total_amount,
        ),
    )
    job_id = row.lastrowid
    conn.commit()
    conn.close()

    return str(job_id)
