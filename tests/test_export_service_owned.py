"""Tests for export_service _is_force_owned helper and Python-side exportable filter."""

import json

from app.services.export_service import _is_force_owned


def _make_book(match_status: str, force_owned=None) -> dict:
    overrides = {}
    if force_owned is not None:
        overrides["force_owned"] = force_owned
    return {
        "match_status": match_status,
        "user_overrides": json.dumps(overrides) if overrides else None,
    }


def _apply_filter(books: list[dict]) -> list[dict]:
    return [
        b for b in books
        if b["match_status"] in ("available", "missing_isbn", "invalid_isbn")
        or (b["match_status"] == "already_owned" and _is_force_owned(b))
    ]


def test_is_force_owned_true():
    book = {"user_overrides": '{"force_owned": true}'}
    assert _is_force_owned(book) is True


def test_is_force_owned_false_no_key():
    book = {"user_overrides": None}
    assert _is_force_owned(book) is False


def test_is_force_owned_false_empty():
    book = {"user_overrides": "{}"}
    assert _is_force_owned(book) is False


def test_is_force_owned_false_explicit_false():
    book = {"user_overrides": '{"force_owned": false}'}
    assert _is_force_owned(book) is False


def test_exportable_filter_includes_available():
    books = [_make_book("available")]
    assert len(_apply_filter(books)) == 1


def test_exportable_filter_includes_missing_isbn():
    books = [_make_book("missing_isbn"), _make_book("invalid_isbn")]
    assert len(_apply_filter(books)) == 2


def test_exportable_filter_includes_force_owned_already_owned():
    books = [_make_book("already_owned", force_owned=True)]
    result = _apply_filter(books)
    assert len(result) == 1
    assert result[0]["match_status"] == "already_owned"


def test_exportable_filter_excludes_unconfirmed_already_owned():
    books = [_make_book("already_owned", force_owned=None)]
    assert len(_apply_filter(books)) == 0


def test_exportable_filter_excludes_already_owned_force_false():
    books = [_make_book("already_owned", force_owned=False)]
    assert len(_apply_filter(books)) == 0


def test_exportable_filter_mixed():
    books = [
        _make_book("available"),
        _make_book("already_owned", force_owned=True),
        _make_book("already_owned", force_owned=None),
        _make_book("missing_isbn"),
    ]
    result = _apply_filter(books)
    assert len(result) == 3
    statuses = [b["match_status"] for b in result]
    assert statuses.count("available") == 1
    assert statuses.count("already_owned") == 1
    assert statuses.count("missing_isbn") == 1
