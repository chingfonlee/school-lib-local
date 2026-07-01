from app.services.export_service import _resolve_eligibility_for_export


def test_junior_high_recommended_exports_as_required():
    book = {"eligibility_label": "推薦", "user_overrides": None}

    assert _resolve_eligibility_for_export(book, "general_books_jh") == "必選"


def test_elementary_recommended_exports_unchanged():
    book = {"eligibility_label": "推薦", "user_overrides": None}

    assert _resolve_eligibility_for_export(book, "general_books") == "推薦"


def test_junior_high_override_recommended_exports_as_required():
    book = {"eligibility_label": "必選", "user_overrides": '{"eligibility_label": "推薦"}'}

    assert _resolve_eligibility_for_export(book, "general_books_jh") == "必選"
