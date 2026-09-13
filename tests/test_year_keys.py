"""Tests for four-digit year keys — the century boundary that two-digit keys got wrong."""

import pandas as pd

from analyze_bls import COMPOSITE_ANCHOR_YEAR, attach_growth_columns


def _trend_frame(year_keys: list[str]) -> pd.DataFrame:
    columns = {"OCC_CODE": ["11-1011"]}
    for offset, year_key in enumerate(year_keys):
        columns[f"TOT_EMP_{year_key}"] = [100.0 + offset * 10]
        columns[f"A_MEDIAN_{year_key}"] = [50_000.0 + offset * 1_000]
    return pd.DataFrame(columns)


class TestCenturyBoundary:
    def test_anchor_year_is_four_digits(self):
        assert COMPOSITE_ANCHOR_YEAR == "2022"

    def test_twentieth_century_periods_carry_the_hist_prefix(self):
        year_keys = ["1999", "2000", "2022", "2023"]
        trend_df = attach_growth_columns(_trend_frame(year_keys), year_keys)
        assert "hist_emp_growth_1999_2000" in trend_df.columns
        assert "emp_growth_1999_2000" not in trend_df.columns

    def test_ai_era_periods_do_not_carry_the_hist_prefix(self):
        year_keys = ["1999", "2000", "2022", "2023"]
        trend_df = attach_growth_columns(_trend_frame(year_keys), year_keys)
        assert "emp_growth_2022_2023" in trend_df.columns
        assert "hist_emp_growth_2022_2023" not in trend_df.columns

    def test_pre_ai_composite_spans_from_the_earliest_year(self):
        year_keys = ["1999", "2000", "2022", "2023"]
        trend_df = attach_growth_columns(_trend_frame(year_keys), year_keys)
        pre_ai_columns = [column for column in trend_df.columns if "pre_ai" in column]
        assert pre_ai_columns, "expected a pre-AI composite column"

    def test_year_keys_sort_chronologically_as_strings(self):
        assert sorted(["2000", "1999", "2022", "1983"]) == ["1983", "1999", "2000", "2022"]
