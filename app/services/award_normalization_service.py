from __future__ import annotations

import sqlite3
from typing import Any

from app.database import db_session, get_connection

DEFAULT_UNRECOGNIZED_AWARD = "其他國內外具公信力單位辦理之獎項(請備註獎項名稱)"
AUTO_CONFIDENCE_THRESHOLD = 0.8
MAX_SAMPLE_TITLES = 3

_STATUS_SORT_ORDER = {
    "unrecognized": 0,
    "needs_review": 1,
    "auto": 2,
    "empty": 3,
}


def _resolve_rule_project_type(project_type: str) -> str:
    if project_type == "general_books_jh":
        return "general_books"
    return project_type


def _load_rules(conn: sqlite3.Connection, project_type: str) -> list[dict[str, Any]]:
    resolved_type = _resolve_rule_project_type(project_type)
    rows = conn.execute(
        "SELECT * FROM award_normalization_rules WHERE project_type = ? AND enabled = 1 ORDER BY priority ASC, id ASC",
        (resolved_type,),
    ).fetchall()
    return [dict(r) for r in rows]


def _match_with_rules(raw_award: str | None, rules: list[dict[str, Any]]) -> dict[str, Any]:
    text = (raw_award or "").strip()
    if not text:
        return {
            "recommendation_source": None,
            "eligibility_label": None,
            "award_notes": None,
            "confidence": 1.0,
            "needs_review": False,
            "status": "empty",
            "matched_rule": None,
        }

    text_lower = text.lower()
    for rule in rules:
        pattern = str(rule["raw_pattern"])
        pattern_lower = pattern.lower()
        match_type = rule["match_type"]
        if match_type == "exact":
            matched = text_lower == pattern_lower
        elif match_type == "contains":
            matched = pattern_lower in text_lower
        else:
            matched = False

        if matched:
            confidence = float(rule["confidence"])
            needs_review = confidence < AUTO_CONFIDENCE_THRESHOLD
            award_notes = text if rule["award_notes_mode"] == "raw_award" else None
            return {
                "recommendation_source": str(rule["normalized_award"]),
                "eligibility_label": str(rule["eligibility_label"]),
                "award_notes": award_notes,
                "confidence": confidence,
                "needs_review": needs_review,
                "status": "needs_review" if needs_review else "auto",
                "matched_rule": pattern,
            }

    return {
        "recommendation_source": DEFAULT_UNRECOGNIZED_AWARD,
        "eligibility_label": "推薦",
        "award_notes": text,
        "confidence": 0.3,
        "needs_review": True,
        "status": "unrecognized",
        "matched_rule": None,
    }


def normalize_award(
    raw_award: str | None,
    project_type: str = "general_books",
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Normalize a single vendor raw award string using enabled DB rules."""
    if not (raw_award or "").strip():
        return _match_with_rules(raw_award, [])

    if conn is not None:
        rules = _load_rules(conn, project_type)
    else:
        with db_session(get_connection) as session_conn:
            rules = _load_rules(session_conn, project_type)

    return _match_with_rules(raw_award, rules)


def group_normalize(
    rows: list[dict[str, Any]],
    project_type: str = "general_books",
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """Group parsed vendor rows by stripped award_item and return normalization suggestions."""
    if not rows:
        return []

    if conn is not None:
        rules = _load_rules(conn, project_type)
    else:
        with db_session(get_connection) as session_conn:
            rules = _load_rules(session_conn, project_type)

    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        raw_key = str(row.get("award_item") or "").strip()
        title = str(row.get("title") or "").strip()
        entry = grouped.get(raw_key)
        if entry is None:
            entry = {"count": 0, "sample_titles": []}
            grouped[raw_key] = entry
        entry["count"] += 1
        if title and len(entry["sample_titles"]) < MAX_SAMPLE_TITLES:
            entry["sample_titles"].append(title)

    results: list[dict[str, Any]] = []
    for raw_key, info in grouped.items():
        norm = _match_with_rules(raw_key, rules)
        results.append(
            {
                "raw_award": raw_key,
                "count": info["count"],
                "sample_titles": info["sample_titles"],
                "recommendation_source": norm["recommendation_source"],
                "eligibility_label": norm["eligibility_label"],
                "award_notes": norm["award_notes"],
                "confidence": norm["confidence"],
                "needs_review": norm["needs_review"],
                "status": norm["status"],
                "matched_rule": norm["matched_rule"],
            }
        )

    results.sort(key=lambda g: (_STATUS_SORT_ORDER.get(str(g["status"]), 99), -int(g["count"]), str(g["raw_award"])))
    return results
