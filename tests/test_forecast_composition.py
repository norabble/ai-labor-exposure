"""
test_forecast_composition.py
────────────────────────────
Tests for forecast_composition.py — the decomposed-slope composition forecast.

Every statistic is tested against synthetic sectors with a known answer, so a
change in the real data cannot make a broken estimator look right.
"""

import numpy as np
import pandas as pd
import pytest

from forecast_composition import (
    align_sectors,
    estimate_period_slopes,
    report_employment_column,
    sector_code,
    sector_employment_panel,
    sector_scores,
)

SECTORS = [f"{code:02d}" for code in range(11, 55, 2)]  # 22 two-digit codes


def synthetic_panel(slope_by_period: dict[int, float], scores: pd.Series, years=range(2000, 2006), noise=0.0, seed=0) -> pd.DataFrame:
    """Sector employment whose relative growth is slope × (score − weighted mean score) each year, plus optional noise.

    Relative growth subtracts total growth, which removes the common 2% and the
    weighted-mean score term, so the Stage 1 OLS slope equals `slope` exactly when noise is 0.
    """
    rng = np.random.default_rng(seed)
    employment = pd.Series(1000.0, index=scores.index)
    columns = {}
    for year in years:
        columns[year] = employment.copy()
        slope = slope_by_period.get(year + 1, 0.0)
        employment = employment * (1.0 + 0.02 + slope * scores + rng.normal(0.0, noise, len(scores)))
    return pd.DataFrame(columns)


@pytest.fixture
def scores():
    return pd.Series(np.linspace(-0.2, 0.2, len(SECTORS)), index=SECTORS, name="score")


class TestStageOneInputs:
    def test_sector_code_normalises_ints_and_strings(self):
        assert sector_code(11) == "11"
        assert sector_code("11") == "11"
        assert sector_code(11.0) == "11"

    def test_report_employment_column_detects_year(self):
        assert report_employment_column(pd.DataFrame(columns=["OCC_CODE", "TOT_EMP_2026"])) == "TOT_EMP_2026"
        with pytest.raises(ValueError, match="exactly one"):
            report_employment_column(pd.DataFrame(columns=["TOT_EMP_2025", "TOT_EMP_2026"]))

    def test_sector_scores_are_employment_weighted(self):
        report_df = pd.DataFrame(
            {
                "OCC_CODE": ["43-1011", "43-9061", "15-1252"],
                "TOT_EMP_2025": [100.0, 300.0, 50.0],
                "net_employment_change": [-0.4, 0.0, 0.16],
            }
        )
        scores = sector_scores(report_df)
        assert scores["43"] == pytest.approx(-0.1)
        assert scores["15"] == pytest.approx(0.16)

    def test_sector_employment_panel_reads_year_columns(self):
        trends_df = pd.DataFrame(
            {"soc_major": [11, 13], "TOT_EMP_2023": [10, 20], "TOT_EMP_2022": [9, 19], "emp_growth_2022_2023": [0.1, 0.05]}
        )
        panel_df = sector_employment_panel(trends_df)
        assert list(panel_df.index) == ["11", "13"]
        assert list(panel_df.columns) == [2022, 2023]

    def test_align_sectors_raises_on_missing_score(self, scores):
        panel_df = pd.DataFrame({2024: 1.0, 2025: 1.0}, index=[*SECTORS, "55"])
        with pytest.raises(ValueError, match="No dynamic-model score"):
            align_sectors(panel_df, scores)


class TestPeriodSlopes:
    def test_recovers_known_slopes(self, scores):
        panel_df = synthetic_panel({2002: 0.05, 2004: -0.03}, scores)
        slopes_df = estimate_period_slopes(panel_df, scores, "oews", {})
        by_period = slopes_df.set_index("period")["slope"]
        assert by_period["2001_2002"] == pytest.approx(0.05, abs=1e-9)
        assert by_period["2003_2004"] == pytest.approx(-0.03, abs=1e-9)
        assert by_period["2000_2001"] == pytest.approx(0.0, abs=1e-9)

    def test_excluded_and_covid_periods_are_flagged_not_dropped(self, scores):
        panel_df = synthetic_panel({}, scores, years=range(2018, 2022))
        slopes_df = estimate_period_slopes(panel_df, scores, "oews", {"2018_2019": "SOC revision level break"})
        flags = slopes_df.set_index("period")
        assert flags.loc["2018_2019", "excluded_reason"] == "SOC revision level break"
        assert bool(flags.loc["2019_2020", "is_covid"])
        assert len(slopes_df) == 3

    def test_skips_non_consecutive_years(self, scores):
        panel_df = synthetic_panel({}, scores, years=range(2000, 2003)).drop(columns=[2001])
        assert estimate_period_slopes(panel_df, scores, "oews", {}).empty
