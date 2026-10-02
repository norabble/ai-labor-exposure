"""
test_btos_adoption.py
─────────────────────
Tests for btos_adoption.py — the Census BTOS AI-use series that supplies the
forecast's adoption driver A_t, and its spliced growth fits.

Parsing is tested against small synthetic workbooks written with the same sheet
and column layout as census.gov's National.xlsx, so no network is needed.
"""

import numpy as np
import pandas as pd
import pytest

import btos_adoption
from btos_adoption import (
    SERIES_COLUMNS,
    WORDING_ANY_FUNCTION,
    WORDING_PRODUCTION,
    merge_with_seed,
    parse_btos_workbook,
    parse_percent,
    wording_of,
)

OLD_QUESTION = "In the last two weeks, did this business use Artificial Intelligence (AI) in producing goods or services?"
NEW_QUESTION = "In the last two weeks, did this business use Artificial Intelligence (AI) in any of its business functions?"


def write_workbook(path, question_text, values_by_smpdt, errors_by_smpdt, ref_end_by_smpdt):
    """Write a minimal BTOS-shaped workbook: three sheets, smpdt as column headers."""
    smpdt_columns = list(values_by_smpdt)
    estimates_df = pd.DataFrame(
        [
            {"Question ID": "6", "Question": "Hours?", "Answer ID": "1", "Answer": "Yes", **{c: "50.0%" for c in smpdt_columns}},
            {"Question ID": "7", "Question": question_text, "Answer ID": "1", "Answer": "Yes", **values_by_smpdt},
            {"Question ID": "7", "Question": question_text, "Answer ID": "2", "Answer": "No", **{c: "80.0%" for c in smpdt_columns}},
        ]
    )
    errors_df = estimates_df.copy()
    for column in smpdt_columns:
        errors_df.loc[1, column] = errors_by_smpdt[column]
    dates_df = pd.DataFrame({"Smpdt": list(ref_end_by_smpdt), "Ref End": list(ref_end_by_smpdt.values())})
    with pd.ExcelWriter(path) as writer:
        estimates_df.to_excel(writer, sheet_name="Response Estimates", index=False)
        errors_df.to_excel(writer, sheet_name="Response Standard Errors", index=False)
        dates_df.to_excel(writer, sheet_name="Collection and Reference Dates", index=False)


class TestParsing:
    def test_parse_percent_converts_and_blanks(self):
        assert parse_percent("9.7%") == pytest.approx(0.097)
        assert np.isnan(parse_percent("."))
        assert np.isnan(parse_percent(np.nan))

    def test_wording_of_labels_both_wordings(self):
        assert wording_of(OLD_QUESTION) == WORDING_PRODUCTION
        assert wording_of(NEW_QUESTION) == WORDING_ANY_FUNCTION

    def test_wording_of_raises_on_unknown(self):
        with pytest.raises(ValueError, match="Unrecognised BTOS AI-use wording"):
            wording_of("Did this business use robots?")

    def test_parse_workbook_reads_yes_row_with_dates(self, tmp_path):
        workbook_path = tmp_path / "btos.xlsx"
        write_workbook(
            workbook_path,
            NEW_QUESTION,
            {"202602": "18.2%", "202601": "17.7%", "202526": "."},
            {"202602": "0.30%", "202601": "0.25%", "202526": "."},
            {"202526": "12/14/2025", "202601": "12/28/2025", "202602": "01/11/2026"},
        )
        series_df = parse_btos_workbook(workbook_path)
        assert list(series_df.columns) == SERIES_COLUMNS
        assert list(series_df["smpdt"]) == ["202601", "202602"]  # "." dropped, sorted by date
        assert series_df["ai_use"].tolist() == pytest.approx([0.177, 0.182])
        assert series_df["std_error"].tolist() == pytest.approx([0.0025, 0.0030])
        assert (series_df["wording"] == WORDING_ANY_FUNCTION).all()
        assert series_df["ref_end"].iloc[0] == pd.Timestamp("2025-12-28")

    def test_parse_workbook_raises_when_a_date_is_missing(self, tmp_path):
        workbook_path = tmp_path / "btos.xlsx"
        write_workbook(workbook_path, NEW_QUESTION, {"202602": "18.2%"}, {"202602": "0.30%"}, {"202601": "12/28/2025"})
        with pytest.raises(ValueError, match="no reference date"):
            parse_btos_workbook(workbook_path)


class TestMerge:
    def test_fetched_rows_replace_seed_rows_and_new_rows_append(self):
        seed_df = pd.DataFrame(
            {
                "smpdt": ["202517", "202601"],
                "ref_end": pd.to_datetime(["2025-08-17", "2025-12-28"]),
                "wording": [WORDING_PRODUCTION, WORDING_ANY_FUNCTION],
                "ai_use": [0.097, 0.170],
                "std_error": [0.0016, 0.0025],
            }
        )
        fetched_df = pd.DataFrame(
            {
                "smpdt": ["202601", "202602"],
                "ref_end": pd.to_datetime(["2025-12-28", "2026-01-11"]),
                "wording": [WORDING_ANY_FUNCTION, WORDING_ANY_FUNCTION],
                "ai_use": [0.177, 0.182],
                "std_error": [0.0025, 0.0030],
            }
        )
        merged_df = merge_with_seed(seed_df, fetched_df)
        assert list(merged_df["smpdt"]) == ["202517", "202601", "202602"]
        assert merged_df.loc[merged_df["smpdt"] == "202601", "ai_use"].item() == pytest.approx(0.177)

    def test_committed_seed_has_both_wordings(self):
        seed_df = pd.read_csv(btos_adoption.SEED_PATH, dtype={"smpdt": str})
        assert set(seed_df["wording"]) == {WORDING_PRODUCTION, WORDING_ANY_FUNCTION}
        assert seed_df["ai_use"].between(0, 1).all()
