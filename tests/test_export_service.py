from app.services.export_service import (
    _format_policy_topic_for_export,
    _resolve_eligibility_for_export,
)


def test_junior_high_recommended_exports_as_required():
    book = {"eligibility_label": "推薦", "user_overrides": None}

    assert _resolve_eligibility_for_export(book, "general_books_jh") == "必選"


def test_elementary_recommended_exports_unchanged():
    book = {"eligibility_label": "推薦", "user_overrides": None}

    assert _resolve_eligibility_for_export(book, "general_books") == "推薦"


def test_junior_high_override_recommended_exports_as_required():
    book = {"eligibility_label": "必選", "user_overrides": '{"eligibility_label": "推薦"}'}

    assert _resolve_eligibility_for_export(book, "general_books_jh") == "必選"


# ── _format_policy_topic_for_export ──


def test_policy_topic_semicolon_to_ideographic_comma():
    assert _format_policy_topic_for_export("SDGs;SEL") == "SDGs、SEL"


def test_policy_topic_fullwidth_semicolon_to_ideographic_comma():
    assert _format_policy_topic_for_export("SDGs；SEL") == "SDGs、SEL"


def test_policy_topic_semicolon_with_surrounding_spaces():
    assert _format_policy_topic_for_export("SDGs; SEL") == "SDGs、SEL"


def test_policy_topic_consecutive_semicolons_skip_empty_parts():
    assert _format_policy_topic_for_export("A;;B") == "A、B"


def test_policy_topic_three_values():
    assert _format_policy_topic_for_export("SDGs;SEL;品德") == "SDGs、SEL、品德"


def test_policy_topic_single_value_unchanged():
    assert _format_policy_topic_for_export("SDGs") == "SDGs"


def test_policy_topic_empty_string_returns_none():
    assert _format_policy_topic_for_export("") is None


def test_policy_topic_none_returns_none():
    assert _format_policy_topic_for_export(None) is None


def test_policy_topic_whitespace_only_segments_return_none():
    assert _format_policy_topic_for_export(" ; ；") is None
