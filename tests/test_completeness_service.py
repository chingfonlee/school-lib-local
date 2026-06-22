import pytest
from app.services.completeness_service import compute


def book(**kwargs):
    return {
        "title": "",
        "list_price": "",
        "purchase_price": "",
        "author": "",
        "publisher": "",
        "award_item": "",
        "eligibility_label": "",
        "recommendation_source": "",
        **kwargs,
    }


# --- local_culture branch (project_type=None or unspecified) ---

class TestLocalCulture:
    def test_missing_title_returns_missing_required(self):
        b = book(title="", list_price="100")
        assert compute(b) == "missing_required"

    def test_missing_price_returns_missing_required(self):
        b = book(title="某書", list_price="", purchase_price="")
        assert compute(b) == "missing_required"

    def test_purchase_price_satisfies_price_requirement(self):
        b = book(title="某書", purchase_price="80", author="A", publisher="P", award_item="金鼎獎")
        assert compute(b) == "export_ready"

    def test_missing_award_item_returns_needs_review(self):
        b = book(title="某書", list_price="100", author="A", publisher="P", award_item="")
        assert compute(b) == "needs_review"

    def test_missing_author_returns_needs_review(self):
        b = book(title="某書", list_price="100", author="", publisher="P", award_item="金鼎獎")
        assert compute(b) == "needs_review"

    def test_missing_publisher_returns_needs_review(self):
        b = book(title="某書", list_price="100", author="A", publisher="", award_item="金鼎獎")
        assert compute(b) == "needs_review"

    def test_all_fields_returns_export_ready(self):
        b = book(title="某書", list_price="100", author="A", publisher="P", award_item="金鼎獎")
        assert compute(b) == "export_ready"


# --- general_books branch ---

class TestGeneralBooks:
    PT = "general_books"

    def test_missing_eligibility_label_returns_missing_required(self):
        b = book(title="某書", list_price="100", eligibility_label="", recommendation_source="教育部")
        assert compute(b, project_type=self.PT) == "missing_required"

    def test_missing_recommendation_source_returns_missing_required(self):
        b = book(title="某書", list_price="100", eligibility_label="必選", recommendation_source="")
        assert compute(b, project_type=self.PT) == "missing_required"

    def test_missing_author_returns_needs_review(self):
        b = book(title="某書", list_price="100", eligibility_label="必選",
                 recommendation_source="教育部", author="", publisher="P")
        assert compute(b, project_type=self.PT) == "needs_review"

    def test_missing_publisher_returns_needs_review(self):
        b = book(title="某書", list_price="100", eligibility_label="必選",
                 recommendation_source="教育部", author="A", publisher="")
        assert compute(b, project_type=self.PT) == "needs_review"

    def test_all_fields_returns_export_ready(self):
        b = book(title="某書", list_price="100", eligibility_label="必選",
                 recommendation_source="教育部", author="A", publisher="P")
        assert compute(b, project_type=self.PT) == "export_ready"

    def test_award_item_not_required_for_general_books(self):
        b = book(title="某書", list_price="100", eligibility_label="必選",
                 recommendation_source="教育部", author="A", publisher="P", award_item="")
        assert compute(b, project_type=self.PT) == "export_ready"


# --- overrides ---

class TestOverrides:
    def test_override_fills_missing_award_item(self):
        b = book(title="某書", list_price="100", author="A", publisher="P", award_item="")
        overrides = {"award_item": "金鼎獎"}
        assert compute(b, overrides=overrides) == "export_ready"

    def test_override_empty_string_does_not_count(self):
        b = book(title="某書", list_price="100", author="A", publisher="P", award_item="")
        overrides = {"award_item": ""}
        assert compute(b, overrides=overrides) == "needs_review"

    def test_override_fills_missing_price(self):
        b = book(title="某書", list_price="", purchase_price="", author="A",
                 publisher="P", award_item="金鼎獎")
        overrides = {"list_price": "150"}
        assert compute(b, overrides=overrides) == "export_ready"

    def test_override_fills_general_books_field(self):
        b = book(title="某書", list_price="100", eligibility_label="",
                 recommendation_source="教育部", author="A", publisher="P")
        overrides = {"eligibility_label": "推薦"}
        assert compute(b, overrides=overrides, project_type="general_books") == "export_ready"
