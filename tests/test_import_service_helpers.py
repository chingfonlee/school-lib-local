from app.services.import_service import (
    _match_columns,
    _is_blank_or_total_row,
    VENDOR_COLUMN_HINTS,
)


# --- _match_columns: general_books specific fields ---

class TestMatchColumnsGeneralBooksFields:
    def test_eligible_label_maps_to_eligibility_label(self):
        mapping, _ = _match_columns(["eligible_label"], VENDOR_COLUMN_HINTS)
        assert mapping.get("eligible_label") == "eligibility_label"

    def test_chinese_alias_maps_to_eligibility_label(self):
        mapping, _ = _match_columns(["必選推薦"], VENDOR_COLUMN_HINTS)
        assert mapping.get("必選推薦") == "eligibility_label"

    def test_award_template_maps_to_recommendation_source(self):
        mapping, _ = _match_columns(["award_template"], VENDOR_COLUMN_HINTS)
        assert mapping.get("award_template") == "recommendation_source"

    def test_chinese_alias_maps_to_recommendation_source(self):
        mapping, _ = _match_columns(["推薦來源"], VENDOR_COLUMN_HINTS)
        assert mapping.get("推薦來源") == "recommendation_source"

    def test_award_notes_exact_match(self):
        mapping, _ = _match_columns(["award_notes"], VENDOR_COLUMN_HINTS)
        assert mapping.get("award_notes") == "award_notes"

    def test_chinese_alias_maps_to_award_notes(self):
        mapping, _ = _match_columns(["備註"], VENDOR_COLUMN_HINTS)
        assert mapping.get("備註") == "award_notes"

    def test_topic_maps_to_policy_topic(self):
        mapping, _ = _match_columns(["topic"], VENDOR_COLUMN_HINTS)
        assert mapping.get("topic") == "policy_topic"

    def test_chinese_alias_maps_to_policy_topic(self):
        mapping, _ = _match_columns(["議題"], VENDOR_COLUMN_HINTS)
        assert mapping.get("議題") == "policy_topic"

    def test_summary_80_120_maps_to_summary(self):
        mapping, _ = _match_columns(["summary_80_120"], VENDOR_COLUMN_HINTS)
        assert mapping.get("summary_80_120") == "summary"

    def test_chinese_alias_maps_to_summary(self):
        mapping, _ = _match_columns(["摘要"], VENDOR_COLUMN_HINTS)
        assert mapping.get("摘要") == "summary"


class TestMatchColumnsNormalization:
    def test_leading_trailing_spaces_normalized(self):
        mapping, _ = _match_columns([" summary_80_120 "], VENDOR_COLUMN_HINTS)
        assert " summary_80_120 " in mapping
        assert mapping[" summary_80_120 "] == "summary"

    def test_mixed_case_normalized(self):
        mapping, _ = _match_columns(["Summary_80_120"], VENDOR_COLUMN_HINTS)
        assert mapping.get("Summary_80_120") == "summary"

    def test_unknown_columns_produce_empty_mapping(self):
        mapping, unmapped = _match_columns(["unknown_col", "另一個未知欄"], VENDOR_COLUMN_HINTS)
        assert mapping == {}
        assert len(unmapped) == len(VENDOR_COLUMN_HINTS)


# --- _is_blank_or_total_row ---

class TestIsBlankOrTotalRow:
    def test_all_none_is_blank(self):
        assert _is_blank_or_total_row([None, None, None]) is True

    def test_all_empty_string_is_blank(self):
        assert _is_blank_or_total_row(["", "", ""]) is True

    def test_mixed_none_and_empty_is_blank(self):
        assert _is_blank_or_total_row([None, "", None]) is True

    def test_contains_subtotal_label(self):
        assert _is_blank_or_total_row(["合計", "100"]) is True

    def test_contains_grand_total_label(self):
        assert _is_blank_or_total_row(["總計"]) is True

    def test_normal_row_is_not_blank(self):
        assert _is_blank_or_total_row(["某書", "作者甲", "出版社乙"]) is False

    def test_row_with_one_real_value_is_not_blank(self):
        assert _is_blank_or_total_row([None, "某書", None]) is False
