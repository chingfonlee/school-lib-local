import math
from typing import Any, Literal
import unicodedata


def _isbn10_to_isbn13(isbn10: str) -> str:
    core = "978" + isbn10[:9]
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(core))
    check = (10 - (total % 10)) % 10
    return core + str(check)


def normalize_isbn(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, float):
        if math.isnan(raw) or math.isinf(raw):
            return None
        raw = str(int(raw))
    elif not isinstance(raw, str):
        raw = str(raw)

    raw = unicodedata.normalize("NFKC", raw).strip()
    if not raw:
        return None

    # Handle Excel float-as-string (e.g. "9789864431991.0")
    if raw.endswith(".0") and raw[:-2].isascii() and raw[:-2].isdigit():
        raw = raw[:-2]

    cleaned: list[str] = []
    for ch in raw:
        cat = unicodedata.category(ch)
        if ch in (" ", "\t", "\u3000", "\u00a0", "\u200b", "-", "－"):
            continue
        if cat == "Cc":
            continue
        cleaned.append(ch)
    result = "".join(cleaned).upper()

    if len(result) == 13:
        if result.isascii() and result.isdigit():
            return result
        return None

    if len(result) == 10:
        head = result[:9]
        tail = result[9]
        if head.isascii() and head.isdigit() and ((tail.isascii() and tail.isdigit()) or tail == "X"):
            return _isbn10_to_isbn13(result)
        return None

    return None


def get_isbn_status(raw: Any) -> Literal["valid", "missing", "invalid"]:
    if raw is None:
        return "missing"
    if isinstance(raw, float):
        if math.isnan(raw) or math.isinf(raw):
            return "missing"
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
