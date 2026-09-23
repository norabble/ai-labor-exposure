"""
tests/test_wages.py
───────────────────
Tests for how BLS wage suppression is handled in analyze_bls.py.

BLS suppresses wages two different ways and neither is a missing value: "#" is a
wage censored at a published floor, "*" is an estimate withheld. Coercing both to
NaN dropped every physician from the wage panel and discarded five hourly-only
occupations whose wage was sitting in the adjacent column.

Covers the censoring floor derivation and the annual/hourly growth fallback.
"""

import pandas as pd
import pytest

from analyze_bls import compute_wage_growth, derive_censoring_floor


class TestDeriveCensoringFloor:
    """
    Censoring is applied on the value, so every censored wage exceeds every
    published one — which makes the highest published wage a valid floor without
    knowing the ceiling BLS actually used. BLS stopped documenting it after 2018.
    """

    def test_floor_is_the_highest_published_wage(self):
        wages_df = pd.DataFrame({"A_MEDIAN": [50_000.0, 226_880.0, float("nan")], "A_MEDIAN_censored": [False, False, True]})
        assert derive_censoring_floor(wages_df) == pytest.approx(226_880.0)

    def test_censored_rows_do_not_raise_the_floor(self):
        """A censored row has no numeric wage, so it cannot contribute to its own bound."""
        wages_df = pd.DataFrame({"A_MEDIAN": [50_000.0, float("nan"), float("nan")], "A_MEDIAN_censored": [False, True, True]})
        assert derive_censoring_floor(wages_df) == pytest.approx(50_000.0)

    def test_no_censoring_yields_no_floor(self):
        """2025 is the first year BLS censors nothing."""
        wages_df = pd.DataFrame({"A_MEDIAN": [50_000.0, 559_030.0], "A_MEDIAN_censored": [False, False]})
        assert derive_censoring_floor(wages_df) is None

    def test_missing_flag_column_yields_no_floor(self):
        assert derive_censoring_floor(pd.DataFrame({"A_MEDIAN": [50_000.0]})) is None


class TestComputeWageGrowth:
    """
    Growth is a ratio, so hourly and annual growth are comparable and can share a
    column. The fallback recovers the occupations BLS publishes hourly-only.
    """

    @staticmethod
    def _wages(annual_22, annual_25, hourly_22, hourly_25):
        return pd.DataFrame(
            {
                "A_MEDIAN_22": annual_22,
                "A_MEDIAN_25": annual_25,
                "H_MEDIAN_22": hourly_22,
                "H_MEDIAN_25": hourly_25,
            }
        )

    def test_annual_is_used_when_available(self):
        growth, source = compute_wage_growth(self._wages([100.0], [110.0], [1.0], [5.0]), "22", "25")
        assert growth.iloc[0] == pytest.approx(0.10)
        assert source.iloc[0] == "annual"

    def test_hourly_is_used_when_annual_is_unavailable(self):
        """The Actors case: A_MEDIAN withheld, H_MEDIAN published."""
        growth, source = compute_wage_growth(self._wages([None], [None], [17.94], [29.05]), "22", "25")
        assert growth.iloc[0] == pytest.approx(29.05 / 17.94 - 1)
        assert source.iloc[0] == "hourly"

    def test_one_annual_endpoint_alone_is_not_enough(self):
        """Growth needs both endpoints in the same series; a lone endpoint falls back."""
        growth, source = compute_wage_growth(self._wages([100.0], [None], [10.0], [12.0]), "22", "25")
        assert growth.iloc[0] == pytest.approx(0.20)
        assert source.iloc[0] == "hourly"

    def test_neither_series_available_yields_no_growth_and_no_source(self):
        """The physician case: censored in both A_MEDIAN and H_MEDIAN."""
        growth, source = compute_wage_growth(self._wages([None], [None], [None], [None]), "22", "25")
        assert pd.isna(growth.iloc[0])
        assert pd.isna(source.iloc[0])

    def test_hourly_growth_is_not_rescaled_to_an_annual_wage(self):
        """
        Reconstructing annual as hourly x 2080 would fabricate the exact quantity BLS
        withheld, for the occupations where it is least meaningful. Growth is a ratio,
        so no rescaling is needed or wanted.
        """
        growth, _ = compute_wage_growth(self._wages([None], [None], [20.0], [30.0]), "22", "25")
        assert growth.iloc[0] == pytest.approx(0.5)

    def test_missing_hourly_columns_are_tolerated(self):
        """Historical files predate H_MEDIAN; the annual path must still work."""
        wages_df = pd.DataFrame({"A_MEDIAN_22": [100.0], "A_MEDIAN_25": [110.0]})
        growth, source = compute_wage_growth(wages_df, "22", "25")
        assert growth.iloc[0] == pytest.approx(0.10)
        assert source.iloc[0] == "annual"

    def test_each_occupation_picks_its_own_series(self):
        wages_df = self._wages([100.0, None, None], [110.0, None, None], [1.0, 20.0, None], [9.0, 25.0, None])
        growth, source = compute_wage_growth(wages_df, "22", "25")
        assert source.tolist()[:2] == ["annual", "hourly"]
        assert pd.isna(source.iloc[2])
        assert growth.iloc[0] == pytest.approx(0.10)
        assert growth.iloc[1] == pytest.approx(0.25)
