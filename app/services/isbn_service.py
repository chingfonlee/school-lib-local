import unicodedata
from typing import Literal


def normalize_isbn(raw) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, float):
        raw = str(int(raw))
    elif not isinstance(raw, str):
        raw = str(raw)
    raw = raw.strip()
    if not raw:
        return None
    # Handle Excel float-as-string (e.g. "9789864431991.0")
    if raw.endswith(".0") and raw[:-2].isdigit():
        raw = raw[:-2]

    cleaned = []
    for ch in raw:
        cat = unicodedata.category(ch)
        if ch in (" ", "\t", "　", " ", "​", "-", "－"):
            continue
        if cat == "Cc":
            continue
        cleaned.append(ch)
    result = "".join(cleaned)

    if len(result) not in (10, 13):
        return None
    if not result.isdigit():
        return None
    return result


def get_isbn_status(raw) -> Literal["valid", "missing", "invalid"]:
    if raw is None:
        return "missing"
    if isinstance(raw, float):
        check = str(int(raw))
    elif not isinstance(raw, str):
        check = str(raw)
    else:
        check = raw
    if not check.strip():
        return "missing"
    normalized = normalize_isbn(raw)
    if normalized is None:
        return "invalid"
    return "valid"
