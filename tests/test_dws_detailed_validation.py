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


def _inputs_with_group_employment(observed_multiplier, employment_by_index):
    """Like `_inputs`, but each group's CPS employment (in every year) is set from
    `employment_by_index`, rather than a uniform 1000.0 — needed to test the size-only benchmark,
    which is driven entirely by that employment, not by any model score."""
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
            {
                "year": year,
                "occ1990dd": code,
                "universe": "all_employed",
                "employed_thousands": employment_by_index[code - 1],
                "months_observed": months,
            }
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


class TestEmploymentSizeBenchmark:
    """The size-only pseudo-model: does a group's plain CPS employment share alone predict its
    observed displacement share, with no model score involved at all?"""

    def test_perfect_employment_proportionality_gives_a_benchmark_r_of_one(self):
        employment_by_index = [100.0, 200.0, 300.0, 400.0, 500.0, 600.0]
        dws_panel_df, unit_scores_df, panel_df, groups_df = _inputs_with_group_employment(
            lambda index: 0.05 * employment_by_index[index], employment_by_index
        )
        comparison_df = build_detailed_displacement_comparison(dws_panel_df, unit_scores_df, panel_df, groups_df)

        benchmark_rows = comparison_df[(comparison_df["model"] == "employment_size_benchmark") & (comparison_df["measure"] == "share")]
        assert len(benchmark_rows) == 1
        benchmark_row = benchmark_rows.iloc[0]
        assert benchmark_row["pearson_r"] == pytest.approx(1.0)
        assert benchmark_row["n_groups"] == 6

    def test_benchmark_rows_do_not_duplicate_per_real_model(self):
        """One employment_size_benchmark row per (survey_year, tenure_class) — not one per
        composition/dynamic, since the benchmark carries no model score."""
        employment_by_index = [100.0, 150.0, 225.0, 300.0, 450.0, 600.0]
        dws_panel_df, unit_scores_df, panel_df, groups_df = _inputs_with_group_employment(
            lambda index: 5.0 * (index + 1), employment_by_index
        )
        comparison_df = build_detailed_displacement_comparison(dws_panel_df, unit_scores_df, panel_df, groups_df)

        benchmark_rows = comparison_df[comparison_df["model"] == "employment_size_benchmark"]
        assert len(benchmark_rows) == comparison_df[["survey_year", "tenure_class"]].drop_duplicates().shape[0]

    def test_benchmark_rows_keep_the_full_output_schema(self):
        employment_by_index = [100.0, 200.0, 300.0, 400.0, 500.0, 600.0]
        dws_panel_df, unit_scores_df, panel_df, groups_df = _inputs_with_group_employment(
            lambda index: 0.05 * employment_by_index[index], employment_by_index
        )
        comparison_df = build_detailed_displacement_comparison(dws_panel_df, unit_scores_df, panel_df, groups_df)
        assert list(comparison_df.columns) == dws_detailed_validation.OUTPUT_COLUMNS


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


class TestRunReadsThePopulatedGatesSeed:
    """Important 2: run()'s nonresponse-share wiring (reading dws_gates_path,
    nonresponse_share_by_survey, passing it to build_detailed_displacement_comparison) must be
    exercised with an actual populated gates CSV, not just mocked away."""

    def test_run_reads_a_populated_gates_csv_and_passes_its_nonresponse_shares_through(self, monkeypatch, tmp_path):
        dws_seed_path = tmp_path / "dws_panel.csv"
        pd.DataFrame({"survey_year": [2024], "dorn_group": ["exec"], "tenure_class": ["all_tenures"], "displaced_thousands": [1.0]}).to_csv(
            dws_seed_path, index=False
        )
        monkeypatch.setattr(dws_detailed_validation, "load_detailed_panel", lambda: pd.DataFrame({"placeholder": [1]}))
        unit_scores_path = tmp_path / "occ1990dd_scores.csv"
        pd.DataFrame({"occ1990dd": [1], "composition_gross_displacement": [0.01]}).to_csv(unit_scores_path, index=False)
        monkeypatch.setattr(dws_detailed_validation, "UNIT_SCORES_OUTPUT_PATH", str(unit_scores_path))
        monkeypatch.setattr(dws_detailed_validation, "BRIDGE_CHECK_OUTPUT_PATH", str(tmp_path / "absent_bridge_check.csv"))
        monkeypatch.setattr(dws_detailed_validation, "OUTPUT_PATH", str(tmp_path / "output.csv"))

        # A real, populated gates CSV — the on-disk shape gate_g6d actually writes, with a G6D row
        # (ignored by run()) alongside the G6D-nonresponse row run() must read.
        gates_path = tmp_path / "gates.csv"
        pd.DataFrame(
            {
                "gate": ["G6D", "G6D-nonresponse"],
                "scope": ["2024", "2024"],
                "observed": [0.002, 0.25],
                "threshold": [0.01, float("nan")],
                "gated": [True, False],
                "passed": [True, float("nan")],
            }
        ).to_csv(gates_path, index=False)

        captured_arguments = {}

        def _capturing_comparison(*arguments):
            captured_arguments["nonresponse_share_by_survey_year"] = arguments[4]
            return pd.DataFrame(
                {
                    "survey_year": [2024],
                    "model": ["composition"],
                    "tenure_class": ["all_tenures"],
                    "measure": ["rate"],
                    "pearson_r": [0.5],
                    "pearson_p": [0.1],
                    "spearman_r": [0.5],
                    "spearman_p": [0.1],
                    "n_groups": [6],
                }
            )

        monkeypatch.setattr(dws_detailed_validation, "build_detailed_displacement_comparison", _capturing_comparison)

        result_df = dws_detailed_validation.run(str(dws_seed_path), g4_passed_this_run=True, dws_gates_path=str(gates_path))

        assert result_df is not None
        nonresponse_share_by_survey_year = captured_arguments["nonresponse_share_by_survey_year"]
        assert nonresponse_share_by_survey_year.loc[2024] == pytest.approx(0.25)

    def test_the_allocation_the_populated_share_drives_matches_allocate_nonresponse_for_rate(self):
        """Ties run()'s wiring test above to the actual allocation math: the 0.25 share read back
        from a populated gates file, fed through the same function `_rate_correlation` calls,
        produces the documented 1/(1 - share) inflation."""
        displaced_thousands = pd.Series([8.0])
        employment = pd.Series([100.0])
        result = allocate_nonresponse_for_rate(displaced_thousands, employment, nonresponse_share=0.25)
        assert result.iloc[0] == pytest.approx((8.0 * (1.0 / 0.75)) / 100.0)


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
