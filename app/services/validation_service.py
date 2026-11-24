import json
import math
from typing import Any

from app.database import db_session, get_connection

# H欄合法值（來源：範本 N5:N13）— 與 export_service.py 中的常數保持同步
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


def check_export_readiness(project_id: int, price_field: str) -> dict[str, Any]:
    with db_session(get_connection) as conn:
        project = conn.execute(
            "SELECT project_type FROM procurement_projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        project_type = project["project_type"] if project else "local_culture"

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
        rows = conn.execute(
            "SELECT si.*, "
            "COALESCE("
            "  (SELECT bm.match_status FROM book_matches bm "
            "   WHERE bm.vendor_book_id = si.vendor_book_id "
            "     AND bm.match_status != 'same_title_different_isbn' "
            "   ORDER BY bm.id DESC LIMIT 1), "
            f"{holdings_fallback_sql}"
            "  si.match_status_at_selection"
            ") AS resolved_match_status "
            "FROM selection_items si "
            "WHERE si.project_id = ?",
            (project_id,),
        ).fetchall()

    total_selected = 0
    ready_count = 0
    needs_review_count = 0
    missing_required_count = 0
    already_owned_count = 0
    details: list[dict[str, Any]] = []

    for r in rows:
        total_selected += 1
        overrides = json.loads(r["user_overrides"] or "{}")
        match_status = r["resolved_match_status"] or "unknown"
        comp_status = r["completeness_status"]

        if match_status == "already_owned":
            already_owned_count += 1

        missing_blocking: list[str] = []
        missing_review: list[str] = []

        title = _resolve(r, "title", overrides)
        if not title:
            missing_blocking.append("書名")

        lp = _resolve_positive_float(r, "list_price", overrides)
        pp = _resolve_positive_float(r, "purchase_price", overrides)
        if price_field == "list_price" and lp is None:
            missing_blocking.append("定價(定價)")
        elif price_field == "purchase_price" and pp is None:
            missing_blocking.append("定價(單價)")
        if lp is None and pp is None:
            if "定價(定價)" not in missing_blocking and "定價(單價)" not in missing_blocking:
                missing_blocking.append("定價")

        if r["selected_quantity"] <= 0:
            missing_blocking.append("採購數量")

        if project_type == "custom":
            if not _resolve(r, "author", overrides):
                missing_review.append("作者")
            if not _resolve(r, "publisher", overrides):
                missing_review.append("出版社")
            if r["isbn_status"] != "valid":
                missing_review.append("ISBN")
        elif project_type in ("general_books", "general_books_jh"):
            eligibility_col = "B" if project_type == "general_books_jh" else "A"
            recommendation_col = "K" if project_type == "general_books_jh" else "H"
            eligibility = _resolve(r, "eligibility_label", overrides)
            if not eligibility:
                missing_blocking.append(f"必選/推薦（{eligibility_col}欄）")

            rec_src = _resolve(r, "recommendation_source", overrides)
            if not rec_src or rec_src not in GENERAL_BOOKS_H_ALLOWED:
                missing_blocking.append(f"{recommendation_col}欄獲獎項目（非法或空白）")
            elif rec_src in GENERAL_BOOKS_H_REQUIRES_NOTES:
                notes_field = "notes" if project_type == "general_books_jh" else "award_notes"
                notes = _resolve(r, notes_field, overrides)
                if not notes:
                    missing_blocking.append(f"備註（L欄，{recommendation_col}欄需備註）")

            if not _resolve(r, "author", overrides):
                missing_review.append("作者")
            if not _resolve(r, "publisher", overrides):
                missing_review.append("出版社")
            if r["isbn_status"] != "valid":
                missing_review.append("ISBN")
        else:
            isbn = _resolve(r, "isbn_normalized", overrides)
            if r["isbn_status"] != "valid" and not isbn:
                missing_blocking.append("ISBN")

            if not _resolve(r, "author", overrides):
                missing_review.append("作者")
            if not _resolve(r, "publisher", overrides):
                missing_review.append("出版社")
            if not _resolve(r, "award_item", overrides):
                missing_review.append("獲獎項目")

        can_export = len(missing_blocking) == 0 and (match_status != "already_owned" or _is_force_owned(overrides))

        if not can_export:
            if len(missing_blocking) > 0:
                missing_required_count += 1
        elif missing_review:
            needs_review_count += 1
        else:
            ready_count += 1

        details.append(
            {
                "sel_id": r["id"],
                "vendor_book_id": r["vendor_book_id"],
                "title": title or r["title"] or "",
                "match_status": match_status,
                "completeness_status": comp_status,
                "missing_blocking_fields": missing_blocking,
                "missing_review_fields": missing_review,
                "can_export": can_export,
            }
        )

    return {
        "total_selected": total_selected,
        "export_ready": ready_count,
        "needs_review": needs_review_count,
        "missing_required": missing_required_count,
        "already_owned": already_owned_count,
        "details": details,
    }


def _is_force_owned(overrides: dict[str, Any]) -> bool:
    return overrides.get("force_owned") is True


def _resolve(row: Any, field: str, overrides: dict[str, Any]) -> str:
    if field in overrides and overrides[field] not in (None, ""):
        return str(overrides[field])
    v = row[field] if field in row.keys() else None
    if v not in (None, ""):
        return str(v)
    return ""


def _resolve_positive_float(row: Any, field: str, overrides: dict[str, Any]) -> float | None:
    raw = _resolve(row, field, overrides)
    if not raw:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(val) or val <= 0:
        return None
    return val
