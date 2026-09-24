"""Tests for dws_detailed_validation.py — per-survey displacement validation at Dorn-group level."""

import pandas as pd
import pytest

import dws_detailed_validation
from dws_detailed_validation import (
    allocate_nonresponse_for_rate,
    build_detailed_displacement_comparison,
    latest_complete_employment,
    predicted_by_group,
)

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


def test_share_rows_carry_the_leave_one_out_range_and_rate_rows_do_not():
    comparison_df = build_detailed_displacement_comparison(*_inputs(lambda index: 5.0 * (index + 1)))
    share_row = comparison_df[(comparison_df["model"] == "composition") & (comparison_df["measure"] == "share")].iloc[0]
    assert share_row["leave_one_out_min"] <= share_row["leave_one_out_max"]
    rate_row = comparison_df[(comparison_df["model"] == "composition") & (comparison_df["measure"] == "rate")].iloc[0]
    assert pd.isna(rate_row["leave_one_out_min"])
    assert pd.isna(rate_row["leave_one_out_max"])


def test_a_constant_prediction_gives_no_correlation_row():
    comparison_df = build_detailed_displacement_comparison(*_inputs(lambda index: 5.0 * (index + 1)))
    assert comparison_df[comparison_df["model"] == "dynamic"].empty


class TestNonresponseAllocation:
    """The rate measure's proportional, missing-at-random nonresponse allocation."""

    def test_scales_the_count_up_before_dividing_by_employment(self):
        displaced_thousands = pd.Series([10.0, 20.0])
        employment = pd.Series([100.0, 200.0])
        result = allocate_nonresponse_for_rate(displaced_thousands, employment, nonresponse_share=0.5)
        # 1 / (1 - 0.5) = 2x inflation, then divided by employment.
        assert result.tolist() == pytest.approx([0.2, 0.2])

    def test_a_missing_share_leaves_the_rate_unscaled(self):
        displaced_thousands = pd.Series([10.0])
        employment = pd.Series([100.0])
        result = allocate_nonresponse_for_rate(displaced_thousands, employment, nonresponse_share=float("nan"))
        assert result.tolist() == pytest.approx([0.1])

    def test_an_out_of_range_share_leaves_the_rate_unscaled_rather_than_dividing_oddly(self):
        displaced_thousands = pd.Series([10.0])
        employment = pd.Series([100.0])
        result = allocate_nonresponse_for_rate(displaced_thousands, employment, nonresponse_share=1.0)
        assert result.tolist() == pytest.approx([0.1])

    def test_zero_share_is_a_no_op(self):
        displaced_thousands = pd.Series([10.0])
        employment = pd.Series([100.0])
        result = allocate_nonresponse_for_rate(displaced_thousands, employment, nonresponse_share=0.0)
        assert result.tolist() == pytest.approx([0.1])

    def test_build_detailed_displacement_comparison_passes_the_survey_specific_share_through(self):
        """The rate measure's magnitude changes with the allocation, but the share measure does not."""
        dws_panel_df, unit_scores_df, panel_df, groups_df = _inputs(lambda index: 5.0 * (index + 1))
        unallocated_df = build_detailed_displacement_comparison(dws_panel_df, unit_scores_df, panel_df, groups_df)
        allocated_df = build_detailed_displacement_comparison(dws_panel_df, unit_scores_df, panel_df, groups_df, pd.Series({2024: 0.5}))
        # Pearson/Spearman r are invariant to a uniform rescaling, so the correlation columns should
        # be unchanged even though the underlying observed rate was scaled — the allocation must not
        # silently corrupt the correlation, only the (untested-here) intermediate rate values.
        share_columns = ["pearson_r", "spearman_r", "n_groups"]
        unallocated_rate_row = unallocated_df[(unallocated_df["model"] == "composition") & (unallocated_df["measure"] == "rate")]
        allocated_rate_row = allocated_df[(allocated_df["model"] == "composition") & (allocated_df["measure"] == "rate")]
        pd.testing.assert_frame_equal(
            unallocated_rate_row[share_columns].reset_index(drop=True), allocated_rate_row[share_columns].reset_index(drop=True)
        )


class TestRunWithdrawsOnAStaleG4Verdict:
    """dws_detailed_validation.run() must never act on a possibly-stale
    occ1990dd_bridge_check.csv left over from an earlier, different run."""

    def _stub_common_inputs(self, monkeypatch, tmp_path):
        dws_seed_path = tmp_path / "dws_panel.csv"
        pd.DataFrame({"survey_year": [2024], "dorn_group": ["exec"], "tenure_class": ["all_tenures"], "displaced_thousands": [1.0]}).to_csv(
            dws_seed_path, index=False
        )
        monkeypatch.setattr(dws_detailed_validation, "load_detailed_panel", lambda: pd.DataFrame({"placeholder": [1]}))
        unit_scores_path = tmp_path / "occ1990dd_scores.csv"
        pd.DataFrame({"occ1990dd": [1], "composition_gross_displacement": [0.01]}).to_csv(unit_scores_path, index=False)
        monkeypatch.setattr(dws_detailed_validation, "UNIT_SCORES_OUTPUT_PATH", str(unit_scores_path))
        monkeypatch.setattr(
            dws_detailed_validation,
            "build_detailed_displacement_comparison",
            lambda *arguments: pd.DataFrame(
                {
                    "survey_year": [2024],
                    "model": ["composition"],
                    "tenure_class": ["all_tenures"],
                    "measure": ["share"],
                    "pearson_r": [0.5],
                    "pearson_p": [0.1],
                    "spearman_r": [0.5],
                    "spearman_p": [0.1],
                    "n_groups": [6],
                }
            ),
        )
        return dws_seed_path

    def test_an_explicit_false_verdict_withholds_even_if_the_file_says_passed(self, monkeypatch, tmp_path):
        dws_seed_path = self._stub_common_inputs(monkeypatch, tmp_path)
        bridge_check_path = tmp_path / "bridge_check.csv"
        pd.DataFrame({"coding_block": ["2003_2010"], "block_gate_passed": [True]}).to_csv(bridge_check_path, index=False)
        monkeypatch.setattr(dws_detailed_validation, "BRIDGE_CHECK_OUTPUT_PATH", str(bridge_check_path))
        monkeypatch.setattr(dws_detailed_validation, "g4_passed", lambda check_df: True)
        with pytest.warns(UserWarning, match="G4"):
            assert dws_detailed_validation.run(str(dws_seed_path), g4_passed_this_run=False) is None

    def test_an_explicit_true_verdict_proceeds_even_without_a_bridge_check_file(self, monkeypatch, tmp_path):
        dws_seed_path = self._stub_common_inputs(monkeypatch, tmp_path)
        monkeypatch.setattr(dws_detailed_validation, "BRIDGE_CHECK_OUTPUT_PATH", str(tmp_path / "absent_bridge_check.csv"))
        monkeypatch.setattr(dws_detailed_validation, "OUTPUT_PATH", str(tmp_path / "output.csv"))
        result_df = dws_detailed_validation.run(str(dws_seed_path), g4_passed_this_run=True)
        assert result_df is not None

    def test_the_standalone_default_falls_back_to_the_on_disk_bridge_check(self, monkeypatch, tmp_path):
        dws_seed_path = self._stub_common_inputs(monkeypatch, tmp_path)
        monkeypatch.setattr(dws_detailed_validation, "BRIDGE_CHECK_OUTPUT_PATH", str(tmp_path / "absent_bridge_check.csv"))
        with pytest.warns(UserWarning, match="G4"):
            assert dws_detailed_validation.run(str(dws_seed_path)) is None

    def test_explicit_false_verdict_overrides_a_stale_passing_file(self, monkeypatch, tmp_path):
        """When cps_detailed_validation.run() returns early with LAST_RUN_G4_PASSED=False,
        dws_detailed_validation should withhold even if an old bridge_check.csv says passed."""
        dws_seed_path = self._stub_common_inputs(monkeypatch, tmp_path)
        bridge_check_path = tmp_path / "bridge_check.csv"
        # Stale bridge check from a previous run that had passed
        pd.DataFrame({"coding_block": ["2003_2010"], "block_gate_passed": [True]}).to_csv(bridge_check_path, index=False)
        monkeypatch.setattr(dws_detailed_validation, "BRIDGE_CHECK_OUTPUT_PATH", str(bridge_check_path))
        monkeypatch.setattr(dws_detailed_validation, "g4_passed", lambda check_df: True)
        monkeypatch.setattr(dws_detailed_validation, "OUTPUT_PATH", str(tmp_path / "output.csv"))
        # Caller passes explicit False from cps_detailed_validation.LAST_RUN_G4_PASSED
        with pytest.warns(UserWarning, match="G4 did not pass in this run"):
            result = dws_detailed_validation.run(str(dws_seed_path), g4_passed_this_run=False)
        assert result is None
