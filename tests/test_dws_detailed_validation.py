"""Tests for dws_detailed_validation.py — per-survey displacement validation at Dorn-group level."""

import pandas as pd
import pytest

from dws_detailed_validation import build_detailed_displacement_comparison, latest_complete_employment, predicted_by_group

GROUPS = ["exec", "prof", "cleric", "retsales", "product", "operator"]


def _inputs(observed_multiplier):
    groups_df = pd.DataFrame({"occ1990dd": range(1, 7), "dorn_group": GROUPS})
    unit_scores_df = pd.DataFrame(
        {
            "occ1990dd": range(1, 7),
            "composition_gross_displacement": [0.01, 0.02, 0.03, 0.04, 0.05, 0.06],
            "dynamic_gross_displacement": 0.02,
        }
    )
    panel_df = pd.DataFrame(
        [
            {"year": year, "occ1990dd": code, "universe": "all_employed", "employed_thousands": 1000.0, "months_observed": months}
            for year, months in ((2022, 12), (2023, 12), (2024, 12), (2025, 12), (2026, 8))
            for code in range(1, 7)
        ]
    )
    dws_panel_df = pd.DataFrame(
        [
            {"survey_year": 2024, "dorn_group": group, "tenure_class": "all_tenures", "displaced_thousands": observed_multiplier(index)}
            for index, group in enumerate(GROUPS)
        ]
    )
    return dws_panel_df, unit_scores_df, panel_df, groups_df


def test_latest_complete_year_ignores_a_partial_year():
    _, _, panel_df, _ = _inputs(lambda index: 1.0)
    assert latest_complete_employment(panel_df).index.name == "occ1990dd"
    assert len(latest_complete_employment(panel_df)) == 6


def test_predicted_displacement_is_rate_times_employment_summed_per_group():
    _, unit_scores_df, panel_df, groups_df = _inputs(lambda index: 1.0)
    predicted_df = predicted_by_group(
        unit_scores_df, latest_complete_employment(panel_df), groups_df, "composition_gross_displacement"
    ).set_index("dorn_group")
    assert predicted_df.loc["cleric", "predicted_displaced"] == pytest.approx(30.0)
    assert predicted_df.loc["cleric", "predicted_rate"] == pytest.approx(0.03)


def test_observed_proportional_to_predicted_gives_a_perfect_share_correlation():
    comparison_df = build_detailed_displacement_comparison(*_inputs(lambda index: 5.0 * (index + 1)))
    headline = comparison_df[(comparison_df["model"] == "composition") & (comparison_df["measure"] == "share")]
    assert headline["pearson_r"].iloc[0] == pytest.approx(1.0)
    assert headline["n_groups"].iloc[0] == 6


def test_a_constant_prediction_gives_no_correlation_row():
    comparison_df = build_detailed_displacement_comparison(*_inputs(lambda index: 5.0 * (index + 1)))
    assert comparison_df[comparison_df["model"] == "dynamic"].empty
