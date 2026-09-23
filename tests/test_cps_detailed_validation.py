"""Tests for cps_detailed_validation.py — the detailed-level and 22-major-rollup era tests, on synthetic panels."""

import os

import numpy as np
import pandas as pd
import pytest

import composition_era_validation
from cps_detailed_measurement import build_detailed_trends
from cps_detailed_validation import (
    MINIMUM_ROLLUP_MAJORS,
    build_rollup_trends,
    corrected_correlation,
    detailed_period_correlations,
    labeled_units,
    major_period_correlations,
    major_scores,
    oews_major_agreement,
    published_ten_group_agreement,
    rollup_to_majors,
    run_views,
)


def panel_rows(cells):
    return pd.DataFrame(
        [
            {
                "year": year,
                "occ1990dd": code,
                "universe": "all_employed",
                "employed_thousands": employed,
                "person_months": 100,
                "distinct_households": 40.0,
                "months_observed": 12,
                "sampling_variance": variance,
            }
            for year, code, employed, variance in cells
        ]
    )


def synthetic_inputs(years=(2021, 2022, 2023), unit_count=30, slope=0.05, variance=0.01, unlabeled_units=()):
    """Growth rises with the score, plus a small deterministic wobble, so r is positive but below 1."""
    cells, score_rows = [], []
    for unit in range(1, unit_count + 1):
        score = unit / unit_count
        level = 1000.0
        for year in years:
            cells.append((year, unit, level, variance))
            level *= 1 + slope * score + 0.002 * ((unit * 7) % 5)
        score_rows.append({"occ1990dd": unit, "composition_net_change": score, "labeled_share": 0.5 if unit in unlabeled_units else 1.0})
    return panel_rows(cells), pd.DataFrame(score_rows)


class TestCorrectedCorrelation:
    @pytest.mark.parametrize(
        ("raw_r", "reliability", "expected"),
        [(0.3, 0.25, 0.6), (0.3, 0.0, np.nan), (0.3, np.nan, np.nan), (0.9, 0.5, np.nan)],  # last: |corrected| >= 1 is undefined
    )
    def test_rule(self, raw_r, reliability, expected):
        result = corrected_correlation(raw_r, reliability)
        assert (np.isnan(result) and np.isnan(expected)) or result == pytest.approx(expected)


class TestDetailedPeriodCorrelations:
    def test_one_row_per_period_and_score_with_a_positive_fit(self):
        panel_df, unit_scores_df = synthetic_inputs()
        period_df = detailed_period_correlations(
            unit_scores_df, build_detailed_trends(panel_df), panel_df, ["composition_net_change"], labeled_units(unit_scores_df)
        )
        assert set(period_df["period"]) == {"2021_2022", "2022_2023"}
        assert (period_df["fit_r"] > 0.5).all()
        assert period_df.set_index("period").loc["2022_2023", "era"] == "ai"

    def test_units_below_the_labeled_share_floor_are_excluded(self):
        panel_df, unit_scores_df = synthetic_inputs(unlabeled_units=range(1, 6))
        period_df = detailed_period_correlations(
            unit_scores_df, build_detailed_trends(panel_df), panel_df, ["composition_net_change"], labeled_units(unit_scores_df)
        )
        assert (period_df["n_units"] == 25).all()

    def test_seam_periods_are_flagged(self):
        panel_df, unit_scores_df = synthetic_inputs(years=(2010, 2011, 2022))
        period_df = detailed_period_correlations(
            unit_scores_df, build_detailed_trends(panel_df), panel_df, ["composition_net_change"], labeled_units(unit_scores_df)
        )
        assert period_df.set_index("period")["is_seam"].to_dict() == {"2010_2011": True, "2011_2022": False}


class TestRunViews:
    def test_headline_drops_seams_and_corrected_swaps_in_corrected_r(self):
        period_df = pd.DataFrame(
            {
                "period": ["2010_2011", "2012_2013"],
                "score": ["composition_net_change"] * 2,
                "fit_r": [0.1, 0.2],
                "fit_p": [0.5, 0.4],
                "n_units": [100, 100],
                "era": ["pre_ai"] * 2,
                "is_covid": [False, False],
                "is_seam": [True, False],
                "reliability": [0.25, 0.25],
                "fit_r_corrected": [0.2, 0.4],
            }
        )
        views = run_views(period_df, period_df, None)
        assert views["headline"]["period"].tolist() == ["2012_2013"]
        assert views["noise_corrected"]["fit_r"].tolist() == [0.4]
        assert views["seams_included"]["period"].tolist() == ["2010_2011", "2012_2013"]
        assert "direct_scores_diagnostic" not in views


class TestChartLevels:
    @pytest.mark.parametrize(
        ("level", "chart_name"),
        [
            ("cps_detailed", composition_era_validation.CPS_DETAILED_CHART_NAME),
            ("cps_major", composition_era_validation.CPS_MAJOR_CHART_NAME),
        ],
    )
    def test_new_levels_write_their_own_chart(self, tmp_path, level, chart_name):
        period_df = pd.DataFrame(
            {
                "period": ["2020_2021", "2021_2022", "2022_2023"],
                "score": ["composition_net_change"] * 3,
                "fit_r": [0.1, 0.2, 0.15],
                "fit_p": [0.3, 0.01, 0.2],
                "n_units": [250, 260, 255],
                "era": ["pre_ai", "pre_ai", "ai"],
                "is_covid": [True, False, False],
            }
        )
        composition_era_validation.plot_signal_over_time(period_df, str(tmp_path), level=level)
        assert os.path.exists(tmp_path / chart_name)


class TestRollupToMajors:
    def test_detailed_employment_is_split_by_bridge_weight(self):
        panel_df = panel_rows([(2010, 4, 100.0, 1.0)])
        bridge_weights_df = pd.DataFrame(
            {"occ1990dd": [4, 4, 4], "soc_2018_code": ["11-1011", "11-1021", "13-1011"], "weight": [0.5, 0.25, 0.25]}
        )
        rollup_df = rollup_to_majors(panel_df, bridge_weights_df).set_index("soc_major")
        assert rollup_df.loc["11", "employed_thousands"] == pytest.approx(75.0)
        assert rollup_df.loc["13", "employed_thousands"] == pytest.approx(25.0)

    def test_the_trend_table_carries_the_shared_growth_columns(self):
        rollup_df = pd.DataFrame({"year": [2021, 2022, 2023], "soc_major": ["11"] * 3, "employed_thousands": [100.0, 110.0, 121.0]})
        trends_df = build_rollup_trends(rollup_df)
        assert trends_df.loc[0, "emp_growth_2022_2023"] == pytest.approx(0.10)


def _major_inputs(slope):
    majors = [f"{code:02d}" for code in range(11, 55, 2)]  # 22 two-digit majors
    scored_df = pd.DataFrame(
        {"OCC_CODE": [f"{major}-1011" for major in majors], "composition_net_change": np.linspace(0, 1, 22), "TOT_EMP_2025": 1000.0}
    )
    rollup_df = pd.DataFrame(
        [
            {"year": year, "soc_major": major, "employed_thousands": 100.0 * (1 + slope * score + 0.003 * (index % 3)) ** (year - 2021)}
            for index, (major, score) in enumerate(zip(majors, np.linspace(0, 1, 22)))
            for year in (2021, 2022, 2023)
        ]
    )
    return scored_df, build_rollup_trends(rollup_df)


class TestMajorPeriodCorrelations:
    def test_positive_fit_at_n_22(self):
        scored_df, trends_df = _major_inputs(slope=0.05)
        period_df = major_period_correlations(
            major_scores(scored_df, "TOT_EMP_2025", ["composition_net_change"]), trends_df, ["composition_net_change"]
        )
        assert (period_df["n_units"] == 22).all()
        assert (period_df["fit_r"] > 0.5).all()

    def test_fewer_than_twenty_majors_gives_no_row(self):
        scored_df, trends_df = _major_inputs(slope=0.05)
        thin_scores_df = major_scores(scored_df.head(MINIMUM_ROLLUP_MAJORS - 1), "TOT_EMP_2025", ["composition_net_change"])
        assert major_period_correlations(thin_scores_df, trends_df, ["composition_net_change"]).empty


class TestAgreementReports:
    def test_oews_agreement_pairs_each_major_with_itself(self):
        wage_salary_trends_df = build_rollup_trends(
            pd.DataFrame({"year": [2021, 2022], "soc_major": ["11", "11"], "employed_thousands": [100.0, 110.0]})
        )
        sector_trends_df = pd.DataFrame({"soc_major": ["11"], "TOT_EMP_2021": [200.0], "TOT_EMP_2022": [210.0]})
        agreement_df = oews_major_agreement(wage_salary_trends_df, sector_trends_df)
        assert agreement_df.loc[0, "soc_major"] == "11"
        assert agreement_df.loc[0, "oews_growth"] == pytest.approx(0.05)
        assert agreement_df.loc[0, "cps_growth"] == pytest.approx(0.10)

    def test_published_agreement_labels_the_reconstruction_segments(self):
        rollup_df = pd.DataFrame({"year": [1990, 2001, 2010], "soc_major": ["41"] * 3, "employed_thousands": [110.0, 100.0, 99.0]})
        published_df = pd.DataFrame(
            {"year": [1990, 2001, 2010], "cps_group": ["sales and related occupations"] * 3, "employed_thousands": [100.0, 100.0, 100.0]}
        )
        agreement_df = published_ten_group_agreement(rollup_df, published_df).set_index("year")
        assert agreement_df.loc[1990, "segment"] == "reconstruction_1983_1999"
        assert agreement_df.loc[2001, "segment"] == "bridge_2000_2002"
        assert agreement_df.loc[2010, "segment"] == "published_2003_on"
        assert agreement_df.loc[1990, "relative_difference"] == pytest.approx(0.10)
