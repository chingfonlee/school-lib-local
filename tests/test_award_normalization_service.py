from __future__ import annotations

import io
from pathlib import Path
import sqlite3

import openpyxl
import pytest

from app.services.award_normalization_service import (
    DEFAULT_UNRECOGNIZED_AWARD,
    group_normalize,
    normalize_award,
)
from app.services.import_service import preview_award_groups

MIGRATION_009 = Path(__file__).resolve().parent.parent / "migrations" / "009_award_normalization_rules.sql"


class _NoCloseConn:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def close(self) -> None:
        pass

    def __getattr__(self, name: str):
        return getattr(self._conn, name)


@pytest.fixture
def rules_db(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(MIGRATION_009.read_text(encoding="utf-8"))
    conn.commit()
    monkeypatch.setattr(
        "app.services.award_normalization_service.get_connection",
        lambda: _NoCloseConn(conn),
    )
    yield conn
    conn.close()


def _make_xlsx(headers: list[str], rows: list[list[str]]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestNormalizeAward:
    def test_self_selected_exact_match(self, rules_db):
        res = normalize_award("  自選  ")
        assert res["recommendation_source"] == "學校自選(請備註原因)"
        assert res["eligibility_label"] == "自選"
        assert res["award_notes"] is None
        assert res["confidence"] >= 0.9
        assert res["needs_review"] is False
        assert res["status"] == "auto"

    @pytest.mark.parametrize(
        "raw,expected_source",
        [
            ("2025年金鼎獎入圍", "金鼎獎"),
            ("2025年好書大家讀", "好書大家讀"),
            ("高雄市喜閱網推薦", "喜閱網"),
            ("文化部第46屆中小學生優良讀物", "文化部中小學生優良課外讀物選介"),
            ("國教署新生閱讀", "國民中小學新生閱讀推動活動入選書單"),
            ("國民中小學新生閱讀推動", "國民中小學新生閱讀推動活動入選書單"),
            ("113年新生閱讀入選", "國民中小學新生閱讀推動活動入選書單"),
            ("114年新生閱讀推薦書單", "國民中小學新生閱讀推動活動入選書單"),
        ],
    )
    def test_high_confidence_keywords(self, rules_db, raw: str, expected_source: str):
        res = normalize_award(raw)
        assert res["recommendation_source"] == expected_source
        assert res["eligibility_label"] == "推薦"
        assert res["award_notes"] is None
        assert res["confidence"] >= 0.8
        assert res["needs_review"] is False
        assert res["status"] == "auto"

    @pytest.mark.parametrize("raw", ["SEL情緒", "SDGS/優質教育品質", "SDGs/氣候行動"])
    def test_known_conflict_values_require_review(self, rules_db, raw: str):
        res = normalize_award(raw)
        assert res["recommendation_source"] == "圖書分級推薦書目、臺灣歷史文化分級推薦書目"
        assert res["eligibility_label"] == "推薦"
        assert res["award_notes"] == raw
        assert res["confidence"] < 0.8
        assert res["needs_review"] is True
        assert res["status"] == "needs_review"

    def test_unrecognized_award(self, rules_db):
        res = normalize_award("某民間協會年度嚴選")
        assert res["recommendation_source"] == DEFAULT_UNRECOGNIZED_AWARD
        assert res["eligibility_label"] == "推薦"
        assert res["award_notes"] == "某民間協會年度嚴選"
        assert res["confidence"] < 0.5
        assert res["needs_review"] is True
        assert res["status"] == "unrecognized"
        assert res["matched_rule"] is None

    def test_empty_award_returns_empty_status(self, rules_db):
        for raw in ("", "   ", None):
            res = normalize_award(raw)
            assert res["recommendation_source"] is None
            assert res["eligibility_label"] is None
            assert res["award_notes"] is None
            assert res["needs_review"] is False
            assert res["status"] == "empty"

    def test_general_books_jh_shares_general_books_rules(self, rules_db):
        res = normalize_award("2025年金鼎獎", project_type="general_books_jh")
        assert res["recommendation_source"] == "金鼎獎"
        assert res["status"] == "auto"


class TestGroupNormalize:
    def test_group_counts_and_sample_titles_cap(self, rules_db):
        rows = [
            {"award_item": "2025年好書大家讀", "title": "書一"},
            {"award_item": " 2025年好書大家讀 ", "title": "書二"},
            {"award_item": "2025年好書大家讀", "title": "書三"},
            {"award_item": "2025年好書大家讀", "title": "書四"},
            {"award_item": "SEL情緒", "title": "情緒書"},
            {"award_item": "", "title": "無獎書一"},
            {"award_item": None, "title": "無獎書二"},
        ]
        groups = group_normalize(rows)
        by_raw = {g["raw_award"]: g for g in groups}

        assert len(by_raw) == 3
        assert by_raw["2025年好書大家讀"]["count"] == 4
        assert by_raw["2025年好書大家讀"]["sample_titles"] == ["書一", "書二", "書三"]
        assert by_raw["2025年好書大家讀"]["status"] == "auto"

        assert by_raw["SEL情緒"]["count"] == 1
        assert by_raw["SEL情緒"]["sample_titles"] == ["情緒書"]
        assert by_raw["SEL情緒"]["needs_review"] is True
        assert by_raw["SEL情緒"]["status"] == "needs_review"

        assert by_raw[""]["count"] == 2
        assert by_raw[""]["sample_titles"] == ["無獎書一", "無獎書二"]
        assert by_raw[""]["status"] == "empty"


class TestPreviewAwardGroups:
    def test_raises_when_award_item_not_mapped(self, rules_db):
        xlsx = _make_xlsx(["書名", "ISBN"], [["書一", "9789570000001"]])
        with pytest.raises(ValueError, match="尚未對應獲獎項目欄位"):
            preview_award_groups(
                xlsx,
                "vendor.xlsx",
                sheet_name=None,
                header_row=0,
                mappings={"title": "書名", "isbn": "ISBN"},
            )

    def test_skips_blank_and_total_rows(self, rules_db):
        xlsx = _make_xlsx(
            ["獲獎項目", "書名", "ISBN"],
            [
                ["2025年金鼎獎", "好書A", "9789570000001"],
                ["", "", ""],
                ["", "合計", ""],
                ["SEL情緒", "好書B", "9789570000002"],
            ],
        )
        groups = preview_award_groups(
            xlsx,
            "vendor.xlsx",
            sheet_name=None,
            header_row=0,
            mappings={"award_item": "獲獎項目", "title": "書名", "isbn": "ISBN"},
        )
        by_raw = {g["raw_award"]: g for g in groups}
        assert set(by_raw.keys()) == {"2025年金鼎獎", "SEL情緒"}
        assert by_raw["2025年金鼎獎"]["count"] == 1
        assert by_raw["SEL情緒"]["count"] == 1
