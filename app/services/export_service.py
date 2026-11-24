from copy import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import uuid

import openpyxl
from openpyxl.cell.cell import MergedCell
from openpyxl.utils import column_index_from_string

from app.database import db_session, get_connection

LOCAL_CULTURE_REQUIRED_COLS = (
    "sort_order",
    "title",
    "author",
    "publisher",
    "isbn",
    "quantity",
    "price",
    "subtotal",
    "award_item",
    "notes",
)
GENERAL_BOOKS_REQUIRED_COLS = (
    "eligibility_label",
    "sort_order",
    "title",
    "author",
    "publisher",
    "isbn",
    "quantity",
    "price",
    "subtotal",
)

# H欄合法值（來源：範本 N5:N13）— 與 validation_service.py 中的常數保持同步
GENERAL_BOOKS_H_ALLOWED = {
    "喜閱網",
    "文化部中小學生優良課外讀物選介",
    "好書大家讀",
    "金鼎獎",
    "文化部Books from Taiwan等具高公信力推薦價值之圖書",
    "國民中小學新生閱讀推動活動入選書單",
    "圖書分級推薦書目、臺灣歷史文化分級推薦書目",
    "其他國內外具公信力單位辦理之獎項(請備註獎項名稱)",
    "學校自選(請備註原因)",
}

GENERAL_BOOKS_H_REQUIRES_NOTES = {
    "其他國內外具公信力單位辦理之獎項(請備註獎項名稱)",
    "學校自選(請備註原因)",
}


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
        "SELECT project_type, export_template_type FROM procurement_projects WHERE id = ?",
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
            f"找不到匯出範本（project_type={project['export_template_type']}），請至導覽列「範本管理」確認範本已設定。"
        )
    result = dict(tmpl)
    result["_project_type"] = project["project_type"]
    return result


def _resolve_field(book: dict, field: str) -> str:
    overrides = json.loads(book.get("user_overrides") or "{}")
    if field in overrides and overrides[field] not in (None, ""):
        return str(overrides[field])
    v = book.get(field)
    if v not in (None, ""):
        return str(v)
    return ""


def _validate_export_template(tmpl: dict, col_map: dict, required_keys: tuple[str, ...]) -> None:
    template_path = tmpl.get("template_file_path") or ""
    if not template_path or not Path(template_path).is_file():
        raise ValueError(f"找不到匯出範本檔案：{template_path}，請至「範本管理」重新上傳。")
    missing = [k for k in required_keys if k not in col_map]
    if missing:
        raise ValueError(f"匯出範本缺少必要欄位設定：{', '.join(missing)}，請至「範本管理」重新設定。")


def _get_price(book: dict, price_field: str) -> float:
    overrides = json.loads(book.get("user_overrides") or "{}")
    override_val = overrides.get(price_field)
    val = override_val if override_val not in (None, "") else book.get(price_field)
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _resolve_eligibility_for_export(book: dict, project_type: str) -> str:
    value = _resolve_field(book, "eligibility_label")
    if project_type == "general_books_jh" and value == "推薦":
        return "必選"
    return value


def _is_force_owned(book: dict) -> bool:
    ov = json.loads(book.get("user_overrides") or "{}")
    return ov.get("force_owned") is True


def _format_policy_topic_for_export(value: str | None) -> str | None:
    if not value:
        return None
    parts = [p.strip() for p in re.split(r"[;；]", value)]
    parts = [p for p in parts if p]
    return "、".join(parts) if parts else None


def _extend_data_rows(ws, template_row: int, insert_at: int, extra_rows: int) -> None:
    if extra_rows <= 0:
        return

    # openpyxl insert_rows does not shift row_dimensions; save footer heights manually.
    footer_heights = {
        row: dim.height for row, dim in ws.row_dimensions.items() if row >= insert_at and dim.height is not None
    }
    saved_footer = _pop_footer_merged_ranges(ws, insert_at)
    ws.insert_rows(insert_at, extra_rows)
    last_inserted_row = insert_at + extra_rows - 1
    _unmerge_ranges_overlapping_rows(ws, insert_at, last_inserted_row)
    _copy_row_style(ws, template_row, insert_at, last_inserted_row)
    _push_footer_merged_ranges(ws, saved_footer, extra_rows)
    for row, height in footer_heights.items():
        ws.row_dimensions[row + extra_rows].height = height


def _unmerge_ranges_overlapping_rows(ws, first_row: int, last_row: int) -> None:
    ranges_to_unmerge = [
        copy(merged_range)
        for merged_range in ws.merged_cells.ranges
        if merged_range.min_row <= last_row and merged_range.max_row >= first_row
    ]
    for merged_range in ranges_to_unmerge:
        ws.merged_cells.remove(merged_range)
        for row, col in list(merged_range.cells)[1:]:
            cell = ws._cells.get((row, col))
            if isinstance(cell, MergedCell):
                del ws._cells[(row, col)]


def _pop_footer_merged_ranges(ws, insert_at: int) -> list[tuple[int, int, int, int]]:
    """Save and remove merged ranges whose min_row >= insert_at (footer area).

    Ranges that straddle insert_at (min_row < insert_at <= max_row) are left in
    place and handled by _unmerge_ranges_overlapping_rows (conservative removal).
    Returns list of (min_row, min_col, max_row, max_col) tuples.
    """
    to_save = [copy(r) for r in ws.merged_cells.ranges if r.min_row >= insert_at]
    saved = []
    for r in to_save:
        saved.append((r.min_row, r.min_col, r.max_row, r.max_col))
        ws.merged_cells.remove(r)
        for row, col in list(r.cells)[1:]:
            cell = ws._cells.get((row, col))
            if isinstance(cell, MergedCell):
                del ws._cells[(row, col)]
    return saved


def _push_footer_merged_ranges(ws, saved_ranges: list[tuple[int, int, int, int]], extra_rows: int) -> None:
    """Rebuild footer merged ranges shifted down by extra_rows."""
    for min_row, min_col, max_row, max_col in saved_ranges:
        ws.merge_cells(
            start_row=min_row + extra_rows,
            start_column=min_col,
            end_row=max_row + extra_rows,
            end_column=max_col,
        )


def _copy_row_style(ws, source_row: int, first_target_row: int, last_target_row: int) -> None:
    source_dim = ws.row_dimensions[source_row]
    for row in range(first_target_row, last_target_row + 1):
        target_dim = ws.row_dimensions[row]
        target_dim.height = source_dim.height
        target_dim.hidden = source_dim.hidden
        target_dim.outlineLevel = source_dim.outlineLevel
        target_dim.collapsed = source_dim.collapsed

        for col_idx in range(1, ws.max_column + 1):
            source_cell = ws.cell(source_row, col_idx)
            target_cell = ws.cell(row, col_idx)
            if source_cell.has_style:
                target_cell._style = copy(source_cell._style)
            if source_cell.number_format:
                target_cell.number_format = source_cell.number_format
            if source_cell.alignment:
                target_cell.alignment = copy(source_cell.alignment)
            if source_cell.font:
                target_cell.font = copy(source_cell.font)
            if source_cell.fill:
                target_cell.fill = copy(source_cell.fill)
            if source_cell.border:
                target_cell.border = copy(source_cell.border)
            if source_cell.protection:
                target_cell.protection = copy(source_cell.protection)


def _fetch_selection_items_for_export(conn, project_id: int) -> list:
    has_holdings = (
        conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='library_holdings'").fetchone()
        is not None
    )
    holdings_fallback_sql = (
        "  CASE "
        "    WHEN si.isbn_normalized IS NOT NULL AND si.isbn_normalized != '' "
        "      AND EXISTS ("
        "        SELECT 1 FROM library_holdings lh "
        "        WHERE lh.isbn_normalized = si.isbn_normalized"
        "      ) "
        "    THEN 'already_owned' "
        "  END, "
        if has_holdings
        else ""
    )
    return conn.execute(
        "SELECT si.*, "
        "COALESCE("
        "  (SELECT bm.match_status FROM book_matches bm "
        "   WHERE bm.vendor_book_id = si.vendor_book_id "
        "     AND bm.match_status != 'same_title_different_isbn' "
        "   ORDER BY bm.id DESC LIMIT 1), "
        f"{holdings_fallback_sql}"
        "  si.match_status_at_selection, 'available'"
        ") AS match_status "
        "FROM selection_items si "
        "WHERE si.project_id = ? AND si.selected_quantity > 0 "
        "ORDER BY si.vendor_seq, si.id",
        (project_id,),
    ).fetchall()


def export_local_culture(settings: ExportSettings) -> str:
    with db_session(get_connection) as conn:
        tmpl = _load_export_template_for_project(settings.project_id, conn)

    col_map = json.loads(tmpl["column_mappings"])
    _validate_export_template(tmpl, col_map, LOCAL_CULTURE_REQUIRED_COLS)

    def col(key: str) -> int:
        return column_index_from_string(col_map[key])

    template_path = tmpl["template_file_path"]
    header_row = tmpl.get("header_row") or 0
    data_start = tmpl["data_start_row"]
    max_rows = tmpl["max_rows"]
    example_row = data_start - 1
    template_end = data_start + max_rows - 1
    summary_row = data_start + max_rows

    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_filename = f"本土文化採購書單_{ts}_{uuid.uuid4().hex[:6]}.xlsx"
    out_path = str(Path(settings.output_dir) / out_filename)

    with db_session(get_connection) as conn:
        books = _fetch_selection_items_for_export(conn, settings.project_id)

    all_books = [dict(b) for b in books]
    exportable = [
        b
        for b in all_books
        if b["match_status"] in ("available", "missing_isbn", "invalid_isbn")
        or (b["match_status"] == "already_owned" and _is_force_owned(b))
    ]

    shutil.copy2(template_path, out_path)
    wb = None
    try:
        wb = openpyxl.load_workbook(out_path)
        ws = wb.active

        school_name_cell = tmpl.get("school_name_cell") or ""
        approved_budget_cell = tmpl.get("approved_budget_cell") or ""
        school_name_prefix = "校名："
        budget_prefix = "本案核定金額：新臺幣"
        budget_suffix = "元"

        if school_name_cell:
            ws[school_name_cell] = school_name_prefix + settings.school_name
        if approved_budget_cell and settings.approved_budget is not None:
            ws[approved_budget_cell] = budget_prefix + f"{settings.approved_budget:,.0f}" + budget_suffix

        if example_row > header_row:
            for key in col_map:
                ws.cell(row=example_row, column=col(key)).value = None

        extra_rows_needed = max(0, len(exportable) - (template_end - data_start + 1))
        if extra_rows_needed > 0:
            _extend_data_rows(ws, template_end, summary_row, extra_rows_needed)
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
            ws.cell(row=row, column=col("isbn")).value = _resolve_field(book, "isbn_normalized") or _resolve_field(
                book, "isbn"
            )
            ws.cell(row=row, column=col("quantity")).value = quantity
            ws.cell(row=row, column=col("price")).value = price if price else None
            ws.cell(row=row, column=col("subtotal")).value = subtotal if subtotal else None
            ws.cell(row=row, column=col("award_item")).value = _resolve_field(book, "award_item")
            ws.cell(row=row, column=col("notes")).value = _resolve_field(book, "notes") or None

            total_qty += quantity
            total_amount += subtotal

        ws.cell(row=summary_row, column=col("quantity")).value = total_qty
        ws.cell(row=summary_row, column=col("subtotal")).value = total_amount

        wb.save(out_path)
    except Exception:
        if wb is not None:
            wb.close()
        Path(out_path).unlink(missing_ok=True)
        raise
    else:
        wb.close()

    now = datetime.now(timezone.utc).isoformat()
    with db_session(get_connection) as conn:
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

    return str(job_id)


def export_general_books(settings: ExportSettings) -> str:
    with db_session(get_connection) as conn:
        tmpl = _load_export_template_for_project(settings.project_id, conn)

    col_map = json.loads(tmpl["column_mappings"])
    _validate_export_template(tmpl, col_map, GENERAL_BOOKS_REQUIRED_COLS)

    def col(key: str) -> int:
        return column_index_from_string(col_map[key])

    template_path = tmpl["template_file_path"]
    project_type = tmpl.get("_project_type") or ""
    sheet_name = tmpl.get("sheet_name") or ""
    header_row = tmpl.get("header_row") or 0
    data_start = tmpl["data_start_row"]
    max_rows = tmpl["max_rows"]
    example_row = data_start - 1
    template_end = data_start + max_rows - 1
    summary_row = data_start + max_rows

    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_filename = f"一般圖書採購書單_{ts}_{uuid.uuid4().hex[:6]}.xlsx"
    out_path = str(Path(settings.output_dir) / out_filename)

    with db_session(get_connection) as conn:
        books = _fetch_selection_items_for_export(conn, settings.project_id)

    all_books = [dict(b) for b in books]
    exportable = [
        b
        for b in all_books
        if b["match_status"] in ("available", "missing_isbn", "invalid_isbn")
        or (b["match_status"] == "already_owned" and _is_force_owned(b))
    ]

    shutil.copy2(template_path, out_path)
    wb = None
    try:
        wb = openpyxl.load_workbook(out_path)
        ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active

        school_name_cell = tmpl.get("school_name_cell") or ""
        approved_budget_cell = tmpl.get("approved_budget_cell") or ""
        school_name_prefix = "校名："
        budget_prefix = "本案核定金額：新臺幣"
        budget_suffix = "元"

        if school_name_cell:
            ws[school_name_cell] = school_name_prefix + settings.school_name
        if approved_budget_cell and settings.approved_budget is not None:
            ws[approved_budget_cell] = budget_prefix + f"{settings.approved_budget:,.0f}" + budget_suffix

        if example_row > header_row:
            for key in col_map:
                ws.cell(row=example_row, column=col(key)).value = None

        extra_rows_needed = max(0, len(exportable) - (template_end - data_start + 1))
        if extra_rows_needed > 0:
            _extend_data_rows(ws, template_end, summary_row, extra_rows_needed)
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

            ws.cell(row=row, column=col("eligibility_label")).value = (
                _resolve_eligibility_for_export(book, project_type) or None
            )
            ws.cell(row=row, column=col("sort_order")).value = i + 1
            ws.cell(row=row, column=col("title")).value = _resolve_field(book, "title")
            ws.cell(row=row, column=col("author")).value = _resolve_field(book, "author") or None
            ws.cell(row=row, column=col("publisher")).value = _resolve_field(book, "publisher") or None
            ws.cell(row=row, column=col("isbn")).value = (
                _resolve_field(book, "isbn_normalized") or _resolve_field(book, "isbn") or None
            )
            ws.cell(row=row, column=col("quantity")).value = quantity
            if "recommendation_source" in col_map:
                ws.cell(row=row, column=col("recommendation_source")).value = (
                    _resolve_field(book, "recommendation_source") or None
                )
            if "policy_topic" in col_map:
                ws.cell(row=row, column=col("policy_topic")).value = _format_policy_topic_for_export(
                    _resolve_field(book, "policy_topic")
                )
            ws.cell(row=row, column=col("price")).value = price if price else None
            ws.cell(row=row, column=col("subtotal")).value = subtotal if subtotal else None
            if "award_notes" in col_map:
                ws.cell(row=row, column=col("award_notes")).value = _resolve_field(book, "award_notes") or None
            if "notes" in col_map:
                ws.cell(row=row, column=col("notes")).value = _resolve_field(book, "notes") or None

            total_qty += quantity
            total_amount += subtotal

        ws.cell(row=summary_row, column=col("quantity")).value = total_qty
        ws.cell(row=summary_row, column=col("subtotal")).value = total_amount

        wb.save(out_path)
    except Exception:
        if wb is not None:
            wb.close()
        Path(out_path).unlink(missing_ok=True)
        raise
    else:
        wb.close()

    now = datetime.now(timezone.utc).isoformat()
    with db_session(get_connection) as conn:
        row_result = conn.execute(
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
        job_id = row_result.lastrowid
        conn.commit()

    return str(job_id)
