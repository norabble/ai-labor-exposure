"""Tests for four-digit year keys — the century boundary that two-digit keys got wrong."""

import pandas as pd
import pytest

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

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "attach_growth_columns pairs available_years[i] with available_years[i+1] "
            "positionally (zip(available_years[:-1], available_years[1:])) and never sorts. "
            "Its only caller, analyze_bls_data, sorts year keys with sorted() before passing "
            "them in, so this is a real precondition on the function, not a defensive check "
            "inside it. Given out-of-order input it silently emits wrong pairings, e.g. "
            "hist_emp_growth_2022_1999 (years reversed) instead of hist_emp_growth_2000_2022, "
            "and emp_growth_2000_2023 (skips 2022) instead of emp_growth_2022_2023. This is a "
            "known gap flagged for review, not something fixed by this task."
        ),
    )
    def test_out_of_order_year_keys_still_pair_chronologically_adjacent_years(self):
        year_keys = ["2022", "1999", "2000", "2023"]
        trend_df = attach_growth_columns(_trend_frame(year_keys), year_keys)
        assert "hist_emp_growth_1999_2000" in trend_df.columns
        assert "hist_emp_growth_2000_2022" in trend_df.columns
        assert "emp_growth_2022_2023" in trend_df.columns


class TestPreAiComposite:
    """Replaces test_pre_ai_composite_spans_from_the_earliest_year in TestCenturyBoundary."""

    def test_pre_ai_composite_name_carries_its_span(self):
        year_keys = ["1999", "2000", "2022", "2023"]
        trend_df = attach_growth_columns(_trend_frame(year_keys), year_keys)
        assert "hist_emp_growth_pre_ai_1999_2022" in trend_df.columns
        assert "hist_wage_growth_pre_ai_1999_2022" in trend_df.columns

    def test_pre_ai_composite_is_not_discovered_as_a_period(self):
        from composition_era_validation import discover_period_columns

        year_keys = ["1999", "2000", "2022", "2023"]
        trend_df = attach_growth_columns(_trend_frame(year_keys), year_keys)
        discovered = discover_period_columns(trend_df)
        assert not any("pre_ai" in column for column in discovered)
