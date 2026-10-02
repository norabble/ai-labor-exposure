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

import forecast_composition
from btos_adoption import AdoptionFit
from forecast_composition import (
    align_sectors,
    attach_drivers,
    coefficients_from,
    decompose_slopes,
    estimate_instrument,
    estimate_period_slopes,
    fit_coefficients,
    report_employment_column,
    sector_code,
    sector_employment_panel,
    sector_scores,
    stage2_input,
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


def synthetic_period_slopes(structural=0.02, cycle=0.01, ai=0.08, noise=0.0, ai_periods=4, seed=0):
    """Periods 2000→2025 whose slopes follow the decomposition exactly (plus optional noise)."""
    rng = np.random.default_rng(seed)
    end_years = np.arange(2001, 2026)
    unemployment = rng.normal(0, 1, len(end_years))
    adoption = np.where(end_years > 2025 - ai_periods, np.linspace(0.05, 0.25, len(end_years)), 0.0)
    slopes = structural + cycle * unemployment + ai * adoption + rng.normal(0, noise, len(end_years))
    periods = [f"{year - 1}_{year}" for year in end_years]
    return pd.DataFrame(
        {
            "instrument": "oews",
            "period": periods,
            "start_year": end_years - 1,
            "end_year": end_years,
            "slope": slopes,
            "std_error": 0.01,
            "residual_sd": 0.02,
            "n_sectors": 22,
            "is_covid": False,
            "excluded_reason": "",
            "unemployment_change": unemployment,
            "adoption": adoption,
        }
    )


class TestStageTwo:
    def test_attach_drivers_zeroes_adoption_through_2022(self):
        slopes_df = pd.DataFrame({"period": ["2021_2022", "2022_2023"], "end_year": [2022, 2023]})
        driven_df = attach_drivers(slopes_df, pd.Series({"2021_2022": -1.0, "2022_2023": -0.3}), pd.Series({2023: 0.12}))
        assert driven_df["adoption"].tolist() == [0.0, 0.12]
        assert driven_df["unemployment_change"].tolist() == [-1.0, -0.3]

    def test_stage2_input_drops_covid_excluded_and_undriven(self):
        driven_df = synthetic_period_slopes()
        driven_df.loc[0, "is_covid"] = True
        driven_df.loc[1, "excluded_reason"] = "SOC revision level break"
        driven_df.loc[2, "unemployment_change"] = np.nan
        assert len(stage2_input(driven_df)) == len(driven_df) - 3
        assert len(stage2_input(driven_df, include_excluded=True)) == len(driven_df) - 2

    def test_recovers_known_coefficients(self):
        coefficients = coefficients_from(decompose_slopes(synthetic_period_slopes(noise=0.0)))
        assert coefficients["structural"] == pytest.approx(0.02, abs=1e-9)
        assert coefficients["cycle"] == pytest.approx(0.01, abs=1e-9)
        assert coefficients["ai"] == pytest.approx(0.08, abs=1e-9)

    def test_without_ai_periods_warns_and_omits_ai(self):
        pre_ai_df = synthetic_period_slopes(ai_periods=0)
        with pytest.warns(UserWarning, match="AI term is not identified"):
            decomposition_df = decompose_slopes(pre_ai_df)
        assert "ai" not in set(decomposition_df["term"])
        assert coefficients_from(decomposition_df)["ai"] == 0.0

    def test_fit_coefficients_returns_none_when_rank_deficient(self):
        assert fit_coefficients(synthetic_period_slopes(ai_periods=0)) is None


class TestEstimationEntryPoint:
    def test_estimate_instrument_writes_main_and_sensitivity_rows(self, scores):
        # Noise keeps every Stage 1 standard error positive; WLS weights are 1/se².
        panel_df = synthetic_panel({year: 0.01 for year in range(2001, 2026)}, scores, years=range(2000, 2026), noise=0.002)
        period_keys = [f"{year}_{year + 1}" for year in range(2000, 2025)]
        unemployment_change = pd.Series(np.random.default_rng(1).normal(0, 1, len(period_keys)), index=period_keys)
        adoption_fits = {
            "logistic": AdoptionFit("logistic", (0.6, 0.6, 5.0), 0.55, True),
            "linear": AdoptionFit("linear", (0.0, 0.04), 0.55, True),
        }
        estimate, decomposition_rows = estimate_instrument(
            "oews", panel_df, scores, {"2009_2010": "SOC 2010 revision level break"}, unemployment_change, adoption_fits
        )
        assert set(decomposition_rows["specification"]) == {"main", "with_excluded_periods", "backcast_linear"}
        assert (decomposition_rows["instrument"] == "oews").all()
        assert "2009_2010" not in set(estimate.stage2_df["period"])

    def test_decompose_rejects_zero_standard_error(self):
        zero_error_df = synthetic_period_slopes()
        zero_error_df.loc[0, "std_error"] = 0.0
        with pytest.raises(ValueError, match="non-positive standard error"):
            decompose_slopes(zero_error_df)

    def test_run_stage_skips_without_unemployment(self, monkeypatch, capsys):
        monkeypatch.setattr(forecast_composition, "unemployment_change_by_period", lambda period_keys: None)
        monkeypatch.setattr(forecast_composition, "_load_inputs", lambda: (pd.DataFrame(), {"oews": pd.DataFrame()}))
        monkeypatch.setattr(forecast_composition, "run_adoption", lambda: (pd.DataFrame(), {}))
        assert forecast_composition.run_estimation() is None
        assert "No unemployment series available" in capsys.readouterr().out
