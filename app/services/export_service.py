import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import openpyxl
from openpyxl.utils import column_index_from_string

from app.database import get_connection
from app.services.validation_service import check_export_readiness


@dataclass
class ExportSettings:
    project_id: int
    school_name: str
    approved_budget: float | None
    price_field: str
    subtotal_mode: str
    output_dir: str
    exported_by: int


def _load_export_template_for_project(project_id: int, conn) -> dict:
    """Look up the export template for a project by its export_template_type."""
    project = conn.execute(
        "SELECT export_template_type FROM procurement_projects WHERE id = ?",
        (project_id,),
    ).fetchone()
    if project is None:
        raise ValueError("採購專案不存在")
    tmpl = conn.execute(
        "SELECT * FROM export_templates WHERE project_type = ? ORDER BY id LIMIT 1",
        (project["export_template_type"],),
    ).fetchone()
    if tmpl is None:
        raise ValueError(
            f"找不到匯出範本（project_type={project['export_template_type']}）"
            "，請確認 config.yaml export_templates 已設定並重新啟動服務。"
        )
    return dict(tmpl)


def _resolve_field(book: dict, field: str) -> str:
    overrides = json.loads(book.get("user_overrides") or "{}")
    if field in overrides and overrides[field] not in (None, ""):
        return str(overrides[field])
    v = book.get(field)
    if v not in (None, ""):
        return str(v)
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

    conn = get_connection()
    tmpl = _load_export_template_for_project(settings.project_id, conn)
    conn.close()

    col_map = json.loads(tmpl["column_mappings"])

    def col(key: str) -> int:
        return column_index_from_string(col_map[key])

    template_path = tmpl["template_file_path"]
    data_start = tmpl["data_start_row"]
    max_rows = tmpl["max_rows"]
    example_row = data_start - 1
    template_end = data_start + max_rows - 1
    summary_row = data_start + max_rows

    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_filename = f"本土文化採購書單_{ts}.xlsx"
    out_path = str(Path(settings.output_dir) / out_filename)

    shutil.copy2(template_path, out_path)

    wb = openpyxl.load_workbook(out_path)
    ws = wb.active

    school_name_prefix = "校名："
    budget_prefix = "本案核定金額：新臺幣"
    budget_suffix = "元"

    ws[tmpl["school_name_cell"]] = school_name_prefix + settings.school_name
    if settings.approved_budget is not None:
        ws[tmpl["approved_budget_cell"]] = (
            budget_prefix + f"{settings.approved_budget:,.0f}" + budget_suffix
        )

    if example_row >= 1:
        for key in col_map:
            ws.cell(row=example_row, column=col(key)).value = None

    conn = get_connection()
    books = conn.execute(
        "SELECT si.*, "
        "COALESCE("
        "  (SELECT bm.match_status FROM book_matches bm "
        "   WHERE bm.vendor_book_id = si.vendor_book_id "
        "     AND bm.match_status != 'same_title_different_isbn' "
        "   ORDER BY bm.id DESC LIMIT 1), "
        "  si.match_status_at_selection, 'available'"
        ") AS match_status "
        "FROM selection_items si "
        "WHERE si.project_id = ? AND si.selected_quantity > 0 "
        "  AND COALESCE("
        "    (SELECT bm.match_status FROM book_matches bm "
        "     WHERE bm.vendor_book_id = si.vendor_book_id "
        "       AND bm.match_status != 'same_title_different_isbn' "
        "     ORDER BY bm.id DESC LIMIT 1), "
        "    si.match_status_at_selection, 'available'"
        "  ) IN ('available', 'missing_isbn', 'invalid_isbn') "
        "ORDER BY si.vendor_seq, si.id",
        (settings.project_id,),
    ).fetchall()
    conn.close()

    exportable = [dict(b) for b in books]

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

        ws.cell(row=row, column=col("sort_order")).value = i + 1
        ws.cell(row=row, column=col("title")).value = _resolve_field(book, "title")
        ws.cell(row=row, column=col("author")).value = _resolve_field(book, "author")
        ws.cell(row=row, column=col("publisher")).value = _resolve_field(book, "publisher")
        ws.cell(row=row, column=col("isbn")).value = (
            _resolve_field(book, "isbn_normalized") or _resolve_field(book, "isbn")
        )
        ws.cell(row=row, column=col("quantity")).value = quantity
        ws.cell(row=row, column=col("price")).value = price if price else None
        ws.cell(row=row, column=col("subtotal")).value = subtotal if subtotal else None
        ws.cell(row=row, column=col("award_item")).value = _resolve_field(book, "award_item")
        ws.cell(row=row, column=col("notes")).value = book.get("notes") or None

        total_qty += quantity
        total_amount += subtotal

    ws.cell(row=summary_row, column=col("quantity")).value = total_qty
    ws.cell(row=summary_row, column=col("subtotal")).value = total_amount

    wb.save(out_path)

    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    row = conn.execute(
        "INSERT INTO export_jobs"
        "(project_id, school_name, approved_budget, price_field, subtotal_mode, "
        "template_path, output_filename, output_path, exported_by, exported_at, "
        "record_count, total_amount, export_template_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            settings.project_id,
            settings.school_name,
            settings.approved_budget,
            settings.price_field,
            settings.subtotal_mode,
            template_path,
            out_filename,
            out_path,
            settings.exported_by,
            now,
            len(exportable),
            total_amount,
            tmpl["id"],
        ),
    )
    job_id = row.lastrowid
    conn.commit()
    conn.close()

    return str(job_id)
