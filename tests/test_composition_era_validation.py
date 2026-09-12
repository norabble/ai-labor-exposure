"""
test_composition_era_validation.py
──────────────────────────────────
Regression tests for composition_era_validation.py — the era comparison and the
cycle decomposition that together answer whether the demand-type signal is
era-invariant.

The statistics are tested against synthetic series with known answers rather
than against the pipeline's own numbers, so a change in the data cannot quietly
make a broken statistic look right.

Two behaviours are load-bearing:

  • Correlations are averaged and tested in Fisher-z space, not in r space. r is
    bounded and its sampling distribution is skewed, so averaging raw r values
    understates strong correlations.
  • COVID periods are excluded from both the era comparison and the cycle
    decomposition. 2019→20 and 2020→21 are shutdown and rehiring, and they
    dominate the unemployment-change term if left in.
"""

import numpy as np
import pandas as pd
import pytest

from composition_era_validation import (
    COMPOSITION_SCORE_COLUMN,
    CYCLE_OUTPUT_COLUMNS,
    OUTPUT_COLUMNS,
    build_period_correlations,
    decompose_fit_strength,
    discover_period_columns,
    is_ai_era,
    period_key,
    sector_correlation,
    summarise_eras,
)


def _correlation_frame(period_r_pairs, score=COMPOSITION_SCORE_COLUMN, covid_periods=("19_20", "20_21")):
    """Build a period-correlation frame from (period, r) pairs."""
    return pd.DataFrame(
        [
            {
                "period": period,
                "score": score,
                "sector_r": correlation,
                "sector_p": 0.01 if abs(correlation) > 0.42 else 0.30,
                "n_sectors": 22,
                "era": "ai" if is_ai_era(f"emp_growth_{period}") else "pre_ai",
                "is_covid": period in covid_periods,
            }
            for period, correlation in period_r_pairs
        ]
    )


class TestPeriodHelpers:
    def test_period_key_strips_either_prefix(self):
        assert period_key("hist_emp_growth_07_08") == "07_08"
        assert period_key("emp_growth_23_24") == "23_24"

    @pytest.mark.parametrize(
        "growth_column,expected",
        [
            ("hist_emp_growth_21_22", False),
            ("emp_growth_22_23", True),
            ("emp_growth_24_25", True),
            ("hist_emp_growth_05_06", False),
        ],
    )
    def test_ai_era_boundary_is_2022_23(self, growth_column, expected):
        assert is_ai_era(growth_column) is expected

    def test_discover_period_columns_is_chronological_and_excludes_aggregates(self):
        trends_df = pd.DataFrame(
            columns=[
                "emp_growth_composite",
                "hist_emp_growth_21_22",
                "hist_emp_growth_05_06",
                "hist_emp_growth_pre_ai",
                "emp_growth_23_24",
                "emp_growth_22_23",
                "wage_growth_22_23",
            ]
        )

        period_columns = discover_period_columns(trends_df)

        assert period_columns == [
            "hist_emp_growth_05_06",
            "hist_emp_growth_21_22",
            "emp_growth_22_23",
            "emp_growth_23_24",
        ]

    def test_wage_growth_columns_are_not_treated_as_periods(self):
        trends_df = pd.DataFrame(columns=["wage_growth_22_23", "hist_wage_growth_05_06"])

        assert discover_period_columns(trends_df) == []


class TestSectorCorrelation:
    def _scored_frame(self, n_sectors=22):
        rows = []
        for sector_index in range(n_sectors):
            soc_major = f"{11 + 2 * sector_index:02d}"
            rows.append(
                {
                    "OCC_CODE": f"{soc_major}-0001",
                    "soc_major": soc_major,
                    COMPOSITION_SCORE_COLUMN: sector_index / n_sectors,
                    "emp_growth_22_23": sector_index / n_sectors,
                    "TOT_EMP_25": 100_000.0,
                }
            )
        return pd.DataFrame(rows)

    def test_perfectly_aligned_score_and_growth_give_r_of_one(self):
        result = sector_correlation(self._scored_frame(), COMPOSITION_SCORE_COLUMN, "emp_growth_22_23", "TOT_EMP_25", None)

        assert result is not None
        correlation, _, n_sectors = result
        assert correlation == pytest.approx(1.0)
        assert n_sectors == 22

    def test_returns_none_when_too_few_occupations(self):
        thin_df = self._scored_frame(n_sectors=4)

        assert sector_correlation(thin_df, COMPOSITION_SCORE_COLUMN, "emp_growth_22_23", "TOT_EMP_25", None) is None

    def test_build_period_correlations_covers_every_period_and_score(self):
        scored_df = self._scored_frame()
        scored_df["hist_emp_growth_20_21"] = scored_df["emp_growth_22_23"]

        correlation_df = build_period_correlations(scored_df, "TOT_EMP_25", None, [COMPOSITION_SCORE_COLUMN])

        assert set(correlation_df["period"]) == {"20_21", "22_23"}
        assert set(correlation_df["era"]) == {"pre_ai", "ai"}
        assert correlation_df.loc[correlation_df["period"] == "20_21", "is_covid"].all()


class TestSummariseEras:
    def test_splits_periods_into_the_two_eras(self):
        correlation_df = _correlation_frame([("05_06", 0.1), ("18_19", 0.2), ("22_23", 0.5), ("23_24", 0.6)])

        era_summary_df = summarise_eras(correlation_df)

        assert list(era_summary_df.columns) == OUTPUT_COLUMNS
        assert set(era_summary_df["era"]) == {"pre_ai", "ai"}
        assert era_summary_df.loc[era_summary_df["era"] == "pre_ai", "n_periods"].iloc[0] == 2
        assert era_summary_df.loc[era_summary_df["era"] == "ai", "n_periods"].iloc[0] == 2

    def test_mean_is_taken_in_fisher_z_space(self):
        """Averaging raw r understates strong correlations; z-averaging does not."""
        correlation_df = _correlation_frame([("05_06", 0.2), ("06_07", 0.9), ("22_23", 0.1), ("23_24", 0.1)])

        era_summary_df = summarise_eras(correlation_df)
        pre_ai_mean = era_summary_df.loc[era_summary_df["era"] == "pre_ai", "mean_r"].iloc[0]

        assert pre_ai_mean == pytest.approx(np.tanh((np.arctanh(0.2) + np.arctanh(0.9)) / 2))
        assert pre_ai_mean > (0.2 + 0.9) / 2

    def test_covid_periods_are_excluded_by_default(self):
        correlation_df = _correlation_frame([("05_06", 0.1), ("19_20", 0.9), ("22_23", 0.3), ("23_24", 0.3)])

        excluded_summary_df = summarise_eras(correlation_df, exclude_covid=True)
        included_summary_df = summarise_eras(correlation_df, exclude_covid=False)

        assert excluded_summary_df.loc[excluded_summary_df["era"] == "pre_ai", "n_periods"].iloc[0] == 1
        assert included_summary_df.loc[included_summary_df["era"] == "pre_ai", "n_periods"].iloc[0] == 2

    def test_counts_individually_significant_periods(self):
        correlation_df = _correlation_frame([("05_06", 0.9), ("06_07", 0.1), ("22_23", 0.3), ("23_24", 0.3)])

        era_summary_df = summarise_eras(correlation_df)

        assert era_summary_df.loc[era_summary_df["era"] == "pre_ai", "n_significant"].iloc[0] == 1

    def test_era_difference_is_nan_when_one_era_is_too_short(self):
        correlation_df = _correlation_frame([("05_06", 0.1), ("06_07", 0.2), ("22_23", 0.5)])

        era_summary_df = summarise_eras(correlation_df)

        assert era_summary_df["welch_p"].isna().all()


class TestDecomposeFitStrength:
    def test_recovers_a_planted_cycle_coefficient(self):
        """Fit strength built as z = 0.2 + 0.15·dU must come back with those coefficients."""
        periods = ["05_06", "06_07", "07_08", "08_09", "18_19", "22_23", "23_24", "24_25"]
        unemployment_change = pd.Series(dict(zip(periods, [-1.0, 0.0, 1.0, 2.0, 3.0, -0.5, 0.2, 0.1])))
        planted_r = [np.tanh(0.2 + 0.15 * unemployment_change[period]) for period in periods]
        correlation_df = _correlation_frame(list(zip(periods, planted_r)))

        cycle_df = decompose_fit_strength(correlation_df, unemployment_change)

        assert list(cycle_df.columns) == CYCLE_OUTPUT_COLUMNS
        coefficients = cycle_df.set_index("term")["coefficient"]
        assert coefficients["intercept"] == pytest.approx(0.2, abs=1e-6)
        assert coefficients["unemployment_change"] == pytest.approx(0.15, abs=1e-6)

    def test_detects_an_ai_era_premium_over_and_above_the_cycle(self):
        periods = ["05_06", "06_07", "07_08", "08_09", "18_19", "22_23", "23_24", "24_25"]
        unemployment_change = pd.Series(dict(zip(periods, [-1.0, 0.0, 1.0, 3.0, 0.0, 0.0, 0.2, 0.1])))
        planted_r = [
            np.tanh(0.1 + 0.1 * unemployment_change[period] + (0.4 if is_ai_era(f"emp_growth_{period}") else 0.0)) for period in periods
        ]

        cycle_df = decompose_fit_strength(_correlation_frame(list(zip(periods, planted_r))), unemployment_change)
        coefficients = cycle_df.set_index("term")["coefficient"]

        assert coefficients["ai_era"] == pytest.approx(0.4, abs=1e-6)

    def test_reports_no_ai_premium_when_the_cycle_explains_everything(self):
        periods = ["05_06", "06_07", "07_08", "08_09", "18_19", "22_23", "23_24", "24_25"]
        unemployment_change = pd.Series(dict(zip(periods, [-1.0, 0.0, 1.0, 3.0, 0.0, 0.0, 0.2, 0.1])))
        planted_r = [np.tanh(0.2 + 0.15 * unemployment_change[period]) for period in periods]

        cycle_df = decompose_fit_strength(_correlation_frame(list(zip(periods, planted_r))), unemployment_change)
        coefficients = cycle_df.set_index("term")["coefficient"]

        assert coefficients["ai_era"] == pytest.approx(0.0, abs=1e-6)

    def test_covid_periods_are_excluded_from_the_regression(self):
        periods = ["05_06", "06_07", "07_08", "08_09", "19_20", "22_23", "23_24", "24_25"]
        unemployment_change = pd.Series(dict(zip(periods, [-1.0, 0.0, 1.0, 3.0, 4.4, 0.0, 0.2, 0.1])))
        correlation_df = _correlation_frame(list(zip(periods, [0.2, 0.3, 0.4, 0.5, 0.95, 0.3, 0.3, 0.3])))

        cycle_df = decompose_fit_strength(correlation_df, unemployment_change)

        assert cycle_df["n_periods"].iloc[0] == len(periods) - 1

    def test_skips_a_score_with_too_few_periods_to_fit(self):
        unemployment_change = pd.Series({"05_06": 0.0, "22_23": 1.0})
        correlation_df = _correlation_frame([("05_06", 0.2), ("22_23", 0.3)])

        assert decompose_fit_strength(correlation_df, unemployment_change).empty

    def test_periods_confined_to_one_era_warn_instead_of_raising(self):
        """Without both eras the AI-era effect is unidentified; the normal equations are singular."""
        periods = ["05_06", "06_07", "07_08", "08_09", "18_19"]
        unemployment_change = pd.Series(dict(zip(periods, [-1.0, 0.0, 1.0, 2.0, 3.0])))
        correlation_df = _correlation_frame(list(zip(periods, [0.2, 0.3, 0.4, 0.5, 0.1])))

        with pytest.warns(UserWarning, match="do not span both eras"):
            cycle_df = decompose_fit_strength(correlation_df, unemployment_change)

        assert cycle_df.empty
