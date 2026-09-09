"""
tests/test_pipeline.py
──────────────────────
Unit tests for the core economic logic of phase 2 — the parts of the pipeline
that turn a task classification into an exposure number.

Covers:
  • compute_task_exposure       — rebound adjustment per demand type
  • rollup_to_occupation        — importance-weighted mean across an occupation's tasks
  • derive_exposure_tier        — tier boundaries
  • compute_dynamic_equilibrium — signed net employment change, and the
    employment-weighted-sum-is-zero invariant it is built on

These are pure-function tests over synthetic frames; they need no downloaded data.
"""

import pandas as pd
import pytest
from scipy import stats

from analyze_bls import attach_growth_columns, select_detailed_rows, select_major_group_rows
from synthesize_dynamic import compute_dynamic_equilibrium, compute_equilibration_sensitivity, compute_sector_jackknife
from synthesize_impacts import (
    ADVERSARIAL_REBOUND,
    BOUNDED_REBOUND,
    UNBOUNDED_REBOUND,
    attach_dominant_demand,
    build_penetration_lookup,
    compute_task_exposure,
    derive_exposure_tier,
    rollup_to_occupation,
)


def _task_df(rows):
    return pd.DataFrame(rows, columns=["penetration", "Demand Type", "task_importance"])


class TestComputeTaskExposure:
    def test_bounded_has_high_exposure(self):
        result = compute_task_exposure(_task_df([(0.5, "Bounded", 1.0)]))
        assert result["task_exposure"].iloc[0] == pytest.approx(0.5 * (1 - BOUNDED_REBOUND))

    def test_unbounded_is_mostly_absorbed(self):
        result = compute_task_exposure(_task_df([(0.5, "Unbounded", 1.0)]))
        assert result["task_exposure"].iloc[0] == pytest.approx(0.5 * (1 - UNBOUNDED_REBOUND))

    def test_adversarial_is_nearly_fully_absorbed(self):
        result = compute_task_exposure(_task_df([(0.5, "Adversarial", 1.0)]))
        assert result["task_exposure"].iloc[0] == pytest.approx(0.5 * (1 - ADVERSARIAL_REBOUND))

    def test_zero_penetration_contributes_nothing(self):
        result = compute_task_exposure(_task_df([(0.0, "Bounded", 1.0)]))
        assert result["task_exposure"].iloc[0] == 0.0

    def test_error_rows_contribute_nothing(self):
        result = compute_task_exposure(_task_df([(0.8, "ERROR", 1.0)]))
        assert result["task_exposure"].iloc[0] == 0.0

    def test_importance_scales_exposure(self):
        result = compute_task_exposure(_task_df([(0.5, "Bounded", 3.0)]))
        assert result["task_exposure"].iloc[0] == pytest.approx(0.5 * (1 - BOUNDED_REBOUND) * 3.0)

    def test_bounded_exposure_exceeds_unbounded_exceeds_adversarial(self):
        """Ordering invariant: catches transposed rebound constants that the individual value tests above would miss."""
        result = compute_task_exposure(
            _task_df(
                [
                    (0.5, "Bounded", 1.0),
                    (0.5, "Unbounded", 1.0),
                    (0.5, "Adversarial", 1.0),
                ]
            )
        )
        bounded = result.loc[result["Demand Type"] == "Bounded", "task_exposure"].iloc[0]
        unbounded = result.loc[result["Demand Type"] == "Unbounded", "task_exposure"].iloc[0]
        adversarial = result.loc[result["Demand Type"] == "Adversarial", "task_exposure"].iloc[0]
        assert bounded > unbounded > adversarial


class TestDeriveExposureTier:
    def _row(self, score, penetration):
        return pd.Series({"occupation_exposure": score, "mean_penetration": penetration})

    def test_high_structural_exposure(self):
        assert derive_exposure_tier(self._row(0.06, 0.10)) == "High Structural Exposure"

    def test_moderate_structural_exposure(self):
        assert derive_exposure_tier(self._row(0.02, 0.05)) == "Moderate Structural Exposure"

    def test_low_structural_exposure(self):
        assert derive_exposure_tier(self._row(0.005, 0.01)) == "Low Structural Exposure"

    def test_minimal_ai_exposure_fallback(self):
        assert derive_exposure_tier(self._row(0.001, 0.001)) == "Minimal AI Exposure"

    def test_high_exposure_requires_sufficient_penetration(self):
        # Score qualifies but penetration is too low — should not be High Structural Exposure
        result = derive_exposure_tier(self._row(0.06, 0.01))
        assert result != "High Structural Exposure"


class TestRollupToOccupation:
    def _occ_df(self, rows):
        return pd.DataFrame(
            rows,
            columns=["O*NET-SOC Code", "Title", "Demand Type", "penetration", "task_importance", "task_exposure"],
        )

    def test_dominant_demand_reflects_majority(self):
        df = self._occ_df(
            [
                ("11-1011.00", "Chief Executives", "Bounded", 0.5, 2.0, 1.0),
                ("11-1011.00", "Chief Executives", "Bounded", 0.3, 1.0, 0.3),
                ("11-1011.00", "Chief Executives", "Unbounded", 0.2, 0.5, 0.05),
            ]
        )
        result = rollup_to_occupation(df)
        assert result.iloc[0]["dominant_demand"] == "Bounded"

    def test_pct_columns_sum_to_one(self):
        df = self._occ_df(
            [
                ("11-1011.00", "Chief Executives", "Bounded", 0.5, 1.0, 0.5),
                ("11-1011.00", "Chief Executives", "Unbounded", 0.3, 1.0, 0.15),
                ("11-1011.00", "Chief Executives", "Adversarial", 0.2, 1.0, 0.0),
            ]
        )
        result = rollup_to_occupation(df)
        total_pct = result.iloc[0]["pct_bounded"] + result.iloc[0]["pct_unbounded"] + result.iloc[0]["pct_adversarial"]
        assert total_pct == pytest.approx(1.0)

    def test_error_rows_excluded_from_count(self):
        df = self._occ_df(
            [
                ("11-1011.00", "Chief Executives", "Bounded", 0.5, 1.0, 0.5),
                ("11-1011.00", "Chief Executives", "ERROR", 0.8, 1.0, 0.0),
            ]
        )
        result = rollup_to_occupation(df)
        assert result.iloc[0]["total_tasks"] == 1

    def test_occupation_exposure_is_importance_weighted(self):
        # Bounded(penetration=0.5, importance=2): task_exposure = 0.5×(1-0.1)×2 = 0.9
        # Unbounded(penetration=0.3, importance=1): task_exposure = 0.3×(1-0.7)×1 = 0.09
        # occupation_exposure = (0.9 + 0.09) / (2.0 + 1.0) = 0.99 / 3.0
        df = self._occ_df(
            [
                ("11-1011.00", "Chief Executives", "Bounded", 0.5, 2.0, 0.9),
                ("11-1011.00", "Chief Executives", "Unbounded", 0.3, 1.0, 0.09),
            ]
        )
        result = rollup_to_occupation(df)
        assert result.iloc[0]["occupation_exposure"] == pytest.approx(0.99 / 3.0)

    def test_contribution_identity(self):
        """bounded + unbounded + adversarial contributions must equal occupation_exposure."""
        df = self._occ_df(
            [
                ("11-1011.00", "Chief Executives", "Bounded", 0.5, 2.0, 0.9),
                ("11-1011.00", "Chief Executives", "Unbounded", 0.3, 1.0, 0.09),
                ("11-1011.00", "Chief Executives", "Adversarial", 0.4, 1.0, 0.04),
            ]
        )
        result = rollup_to_occupation(df)
        row = result.iloc[0]
        contribution_sum = (
            row["bounded_exposure_contribution"] + row["unbounded_exposure_contribution"] + row["adversarial_exposure_contribution"]
        )
        assert contribution_sum == pytest.approx(row["occupation_exposure"])


class TestDynamicEquilibrium:
    def _fixture_df(self):
        """Three occupations: pure Bounded loser, mixed, pure Unbounded gainer."""
        return pd.DataFrame(
            {
                "OCC_CODE": ["11-0000", "13-0000", "15-0000"],
                "Title": ["Managers", "Business Ops", "Computer"],
                "dominant_demand": ["Bounded", "Bounded", "Unbounded"],
                "dominant_strength": [1.0, 0.5, 1.0],
                "employment": [1000.0, 2000.0, 500.0],
                "occupation_exposure": [0.3, 0.15, 0.05],
                "pct_bounded": [1.0, 0.5, 0.0],
                "pct_unbounded": [0.0, 0.5, 1.0],
                "pct_adversarial": [0.0, 0.0, 0.0],
                "bounded_exposure_contribution": [0.3, 0.1, 0.0],
                "unbounded_exposure_contribution": [0.0, 0.05, 0.05],
                "adversarial_exposure_contribution": [0.0, 0.0, 0.0],
            }
        )

    def test_conservation_sums_to_zero(self):
        result = compute_dynamic_equilibrium(self._fixture_df(), "employment")
        assert result["net_employment_change_workers"].sum() == pytest.approx(0.0, abs=1e-6)

    def test_pure_unbounded_gains_workers(self):
        result = compute_dynamic_equilibrium(self._fixture_df(), "employment")
        unbounded_row = result[result["OCC_CODE"] == "15-0000"].iloc[0]
        assert unbounded_row["net_employment_change"] > 0

    def test_pure_bounded_loses_workers(self):
        result = compute_dynamic_equilibrium(self._fixture_df(), "employment")
        bounded_row = result[result["OCC_CODE"] == "11-0000"].iloc[0]
        assert bounded_row["net_employment_change"] < 0

    def test_zero_absorption_capacity_raises(self):
        no_capacity_df = self._fixture_df().copy()
        no_capacity_df["pct_unbounded"] = 0.0
        no_capacity_df["pct_adversarial"] = 0.0
        with pytest.raises(ValueError, match="No absorption capacity"):
            compute_dynamic_equilibrium(no_capacity_df, "employment")

    def test_absorption_is_one_scalar_times_absorption_capacity(self):
        """
        Absorption carries no per-occupation information beyond absorption_capacity
        — the redistribution step is a single economy-wide constant. The
        equilibration sweep depends on this holding exactly.
        """
        result = compute_dynamic_equilibrium(self._fixture_df(), "employment")
        with_capacity_df = result[result["absorption_capacity"] > 0]
        implied_scalars = with_capacity_df["absorption"] / with_capacity_df["absorption_capacity"]
        assert implied_scalars.max() - implied_scalars.min() == pytest.approx(0.0, abs=1e-12)

    def test_absorption_capacity_is_unbounded_plus_adversarial(self):
        """
        Adversarial is a carve-out from Unbounded in the framework: productivity
        feeds back into demand for both, so both can receive displaced labor.
        """
        result = compute_dynamic_equilibrium(self._adversarial_fixture_df(), "employment")
        expected = result["pct_unbounded"] + result["pct_adversarial"]
        pd.testing.assert_series_equal(result["absorption_capacity"], expected, check_names=False)

    def test_pure_adversarial_occupation_absorbs(self):
        """
        A pure Adversarial occupation with no measured penetration displaces nothing
        and must gain workers, not be scored as a net loser with zero capacity.
        """
        result = compute_dynamic_equilibrium(self._adversarial_fixture_df(), "employment")
        adversarial_row = result[result["OCC_CODE"] == "23-0000"].iloc[0]
        assert adversarial_row["absorption"] > 0
        assert adversarial_row["net_employment_change"] > 0

    def _adversarial_fixture_df(self):
        """The base fixture plus a pure Adversarial occupation with zero penetration."""
        fixture_df = self._fixture_df()
        adversarial_row = pd.DataFrame(
            {
                "OCC_CODE": ["23-0000"],
                "Title": ["Lawyers"],
                "dominant_demand": ["Adversarial"],
                "dominant_strength": [1.0],
                "employment": [800.0],
                "occupation_exposure": [0.0],
                "pct_bounded": [0.0],
                "pct_unbounded": [0.0],
                "pct_adversarial": [1.0],
                "bounded_exposure_contribution": [0.0],
                "unbounded_exposure_contribution": [0.0],
                "adversarial_exposure_contribution": [0.0],
            }
        )
        return pd.concat([fixture_df, adversarial_row], ignore_index=True)


class TestEquilibrationSensitivity:
    """
    The sweep varies the absorption scalar to show how much of the sector-level
    result depends on the conservation constraint holding exactly. Multiplier 0
    is the no-equilibrium model the dynamic model argues against.
    """

    def _validation_df(self):
        sweep_df = TestDynamicEquilibrium()._fixture_df()
        sweep_df["gross_displacement"] = sweep_df["bounded_exposure_contribution"] + sweep_df["adversarial_exposure_contribution"]
        sweep_df["soc_major"] = sweep_df["OCC_CODE"].str[:2]
        sweep_df["emp_growth_composite"] = [-0.05, 0.01, 0.08]
        return sweep_df

    def test_returns_one_row_per_multiplier(self):
        result = compute_equilibration_sensitivity(self._validation_df(), "employment", "emp_growth_composite", multipliers=(0.0, 1.0, 5.0))
        assert list(result["equilibration_multiplier"]) == [0.0, 1.0, 5.0]

    def test_zero_multiplier_is_pure_displacement(self):
        """At multiplier 0 nothing is reabsorbed, so the score is −gross_displacement."""
        validation_df = self._validation_df()
        result = compute_equilibration_sensitivity(validation_df, "employment", "emp_growth_composite", multipliers=(0.0,))
        expected_r = stats.pearsonr(-validation_df["gross_displacement"], validation_df["emp_growth_composite"])[0]
        assert result.iloc[0]["sector_r"] == pytest.approx(expected_r)

    def test_sweep_uses_sector_growth_table_when_given(self):
        validation_df = self._validation_df()
        sector_growth_df = pd.DataFrame({"emp_growth_composite": [0.08, 0.01, -0.05]}, index=pd.Index(["11", "13", "15"], name="soc_major"))
        result = compute_equilibration_sensitivity(
            validation_df, "employment", "emp_growth_composite", multipliers=(1.0,), sector_growth_df=sector_growth_df
        )
        assert result.iloc[0]["sector_r"] < 0

    def test_unit_multiplier_matches_the_fitted_model(self):
        """Multiplier 1 must reproduce the net_employment_change the model actually publishes."""
        validation_df = self._validation_df()
        fitted_df = compute_dynamic_equilibrium(validation_df, "employment")
        result = compute_equilibration_sensitivity(validation_df, "employment", "emp_growth_composite", multipliers=(1.0,))
        expected_r = stats.pearsonr(fitted_df["net_employment_change"], validation_df["emp_growth_composite"])[0]
        assert result.iloc[0]["sector_r"] == pytest.approx(expected_r)


class TestBlsRowSelection:
    """
    Each OEWS file carries detailed-occupation rows and major-group summary rows.
    Detailed rows feed the occupation-level trends; major-group rows feed the
    sector-level trends, because major-group codes are stable across SOC
    revisions while detailed codes are not.
    """

    def _modern_frame(self):
        return pd.DataFrame(
            {
                "OCC_CODE": ["00-0000", "15-0000", "15-1100", "15-1252", "15-2011"],
                "OCC_TITLE": ["All", "Computer and Mathematical", "Computer", "Software Developers", "Actuaries"],
                "O_GROUP": ["total", "major", "minor", "detailed", "detailed"],
                "I_GROUP": ["cross-industry"] * 5,
                "TOT_EMP": [150000000, 5000000, 4800000, 1500000, 25000],
                "A_MEDIAN": [48000, 100000, 101000, 130000, 120000],
            }
        )

    def _legacy_frame(self):
        return pd.DataFrame(
            {
                "OCC_CODE": ["00-0000", "15-0000", "15-1131", "15-1132"],
                "OCC_TITLE": ["All", "Computer and Mathematical", "Programmers", "Software Developers, Applications"],
                "GROUP": ["total", "major", None, None],
                "TOT_EMP": ["130,000,000", "3,283,950", "333,620", "499,280"],
                "A_MEDIAN": ["33,000", "76,000", "71,000", "87,000"],
            }
        )

    def test_major_rows_keyed_by_two_digit_soc_major(self):
        result = select_major_group_rows(self._modern_frame())
        assert list(result["soc_major"]) == ["15"]
        assert result.iloc[0]["TOT_EMP"] == 5000000

    def test_major_rows_from_legacy_group_column_parse_numbers(self):
        result = select_major_group_rows(self._legacy_frame())
        assert list(result["soc_major"]) == ["15"]
        assert result.iloc[0]["TOT_EMP"] == 3283950
        assert result.iloc[0]["A_MEDIAN"] == 76000

    def test_i_group_column_does_not_shadow_o_group(self):
        """2019+ files carry I_GROUP before O_GROUP; the occupation grouping must win."""
        shadowed_df = self._modern_frame()[["OCC_CODE", "OCC_TITLE", "I_GROUP", "O_GROUP", "TOT_EMP", "A_MEDIAN"]]
        assert len(select_major_group_rows(shadowed_df)) == 1
        assert list(select_detailed_rows(shadowed_df)["OCC_CODE"]) == ["15-1252", "15-2011"]

    def test_detailed_rows_exclude_summary_rows_in_legacy_files(self):
        result = select_detailed_rows(self._legacy_frame())
        assert list(result["OCC_CODE"]) == ["15-1131", "15-1132"]


class TestAttachGrowthColumns:
    def _trend_frame(self):
        return pd.DataFrame(
            {
                "key": ["a"],
                "TOT_EMP_21": [100.0],
                "TOT_EMP_22": [110.0],
                "TOT_EMP_23": [121.0],
                "A_MEDIAN_22": [50.0],
                "A_MEDIAN_23": [55.0],
            }
        )

    def test_pre_anchor_periods_get_hist_prefix(self):
        result = attach_growth_columns(self._trend_frame(), ["21", "22", "23"])
        assert result.iloc[0]["hist_emp_growth_21_22"] == pytest.approx(0.10)
        assert result.iloc[0]["emp_growth_22_23"] == pytest.approx(0.10)
        assert "hist_emp_growth_22_23" not in result.columns

    def test_composite_and_pre_ai_anchored_at_2022(self):
        result = attach_growth_columns(self._trend_frame(), ["21", "22", "23"])
        assert result.iloc[0]["emp_growth_composite"] == pytest.approx(0.10)
        assert result.iloc[0]["wage_growth_composite"] == pytest.approx(0.10)
        assert result.iloc[0]["hist_emp_growth_pre_ai"] == pytest.approx(0.10)

    def test_wage_growth_skipped_when_a_year_lacks_wages(self):
        result = attach_growth_columns(self._trend_frame(), ["21", "22", "23"])
        assert "hist_wage_growth_21_22" not in result.columns
        assert "emp_growth_22_23" in result.columns


class TestSectorJackknife:
    """
    Leave-one-sector-out recomputation of the sector-level correlation. With
    n = 22 sectors a single sector can carry the headline result, and the
    jackknife is what shows whether one does.
    """

    def _validation_df(self):
        jackknife_df = TestDynamicEquilibrium()._fixture_df()
        jackknife_df = pd.concat(
            [
                jackknife_df,
                pd.DataFrame(
                    {
                        "OCC_CODE": ["29-0000"],
                        "Title": ["Nurses"],
                        "dominant_demand": ["Unbounded"],
                        "dominant_strength": [1.0],
                        "employment": [3000.0],
                        "occupation_exposure": [0.01],
                        "pct_bounded": [0.1],
                        "pct_unbounded": [0.9],
                        "pct_adversarial": [0.0],
                        "bounded_exposure_contribution": [0.01],
                        "unbounded_exposure_contribution": [0.0],
                        "adversarial_exposure_contribution": [0.0],
                    }
                ),
            ],
            ignore_index=True,
        )
        jackknife_df["net_employment_change"] = [-0.3, -0.05, 0.2, 0.15]
        jackknife_df["soc_major"] = jackknife_df["OCC_CODE"].str[:2]
        jackknife_df["emp_growth_composite"] = [-0.05, 0.01, 0.08, 0.06]
        return jackknife_df

    def test_one_row_per_sector(self):
        result = compute_sector_jackknife(self._validation_df(), "employment", "emp_growth_composite", "net_employment_change")
        assert sorted(result["dropped_sector"]) == ["11", "13", "15", "29"]
        assert (result["n_sectors"] == 3).all()

    def test_dropping_a_sector_matches_a_manual_recomputation(self):
        validation_df = self._validation_df()
        result = compute_sector_jackknife(validation_df, "employment", "emp_growth_composite", "net_employment_change")
        remaining_df = validation_df[validation_df["soc_major"] != "11"]
        expected_r = stats.pearsonr(remaining_df["net_employment_change"], remaining_df["emp_growth_composite"])[0]
        dropped_11 = result[result["dropped_sector"] == "11"].iloc[0]
        assert dropped_11["sector_r"] == pytest.approx(expected_r)

    def test_uses_sector_growth_table_when_given(self):
        """
        Sector growth comes from the major-group totals in bls_sector_trends.csv
        when available, not from the survivor-occupation mean. Here the table
        reverses the ordering, so the correlation must flip sign.
        """
        validation_df = self._validation_df()
        sector_growth_df = pd.DataFrame(
            {"emp_growth_composite": [0.08, 0.06, 0.01, -0.05]}, index=pd.Index(["11", "13", "15", "29"], name="soc_major")
        )
        result = compute_sector_jackknife(
            validation_df, "employment", "emp_growth_composite", "net_employment_change", sector_growth_df=sector_growth_df
        )
        assert result["full_sample_r"].iloc[0] < 0

    def test_carries_the_full_sample_correlation_for_reference(self):
        validation_df = self._validation_df()
        result = compute_sector_jackknife(validation_df, "employment", "emp_growth_composite", "net_employment_change")
        expected_r = stats.pearsonr(validation_df["net_employment_change"], validation_df["emp_growth_composite"])[0]
        assert result["full_sample_r"].nunique() == 1
        assert result["full_sample_r"].iloc[0] == pytest.approx(expected_r)


class TestBuildPenetrationLookup:
    """
    The Anthropic penetration file has no Task IDs, so the join is on task text —
    and that file repeats some texts. Left un-collapsed, those repeats fan the
    merge out and over-weight the repeated task in the occupation rollup.
    """

    def test_repeated_task_text_collapses_to_one_row(self):
        penetration_df = pd.DataFrame({"task": ["Write press releases."] * 8 + ["Draft a budget."], "penetration": [0.7263] * 8 + [0.1]})
        lookup_df = build_penetration_lookup(penetration_df)
        assert len(lookup_df) == 2
        assert lookup_df["task_lower"].is_unique

    def test_collapsing_preserves_the_penetration_value(self):
        penetration_df = pd.DataFrame({"task": ["Write press releases."] * 3, "penetration": [0.7263] * 3})
        lookup_df = build_penetration_lookup(penetration_df)
        assert lookup_df["penetration"].iloc[0] == pytest.approx(0.7263)

    def test_text_is_normalised_for_matching(self):
        penetration_df = pd.DataFrame({"task": ["  Write Press Releases.  "], "penetration": [0.5]})
        lookup_df = build_penetration_lookup(penetration_df)
        assert lookup_df["task_lower"].iloc[0] == "write press releases."

    def test_disagreeing_values_raise_rather_than_picking_one(self):
        """Collapsing is only safe while the repeated rows agree — so that is checked, not assumed."""
        penetration_df = pd.DataFrame({"task": ["Write press releases."] * 2, "penetration": [0.7263, 0.4]})
        with pytest.raises(ValueError, match="disagreeing penetration values"):
            build_penetration_lookup(penetration_df)

    def test_the_error_names_the_offending_text_and_its_range(self):
        penetration_df = pd.DataFrame({"task": ["Write press releases."] * 2, "penetration": [0.7263, 0.4]})
        with pytest.raises(ValueError) as raised:
            build_penetration_lookup(penetration_df)
        message = str(raised.value)
        assert "write press releases." in message
        assert "0.4" in message and "0.7263" in message
        assert "2 rows" in message

    def test_a_value_missing_from_only_some_rows_is_a_disagreement(self):
        """A missing value is not evidence that two rows describe the same measurement."""
        penetration_df = pd.DataFrame({"task": ["Write press releases."] * 2, "penetration": [0.7263, None]})
        with pytest.raises(ValueError, match="disagreeing penetration values"):
            build_penetration_lookup(penetration_df)

    def test_rows_missing_throughout_agree_with_each_other(self):
        penetration_df = pd.DataFrame({"task": ["Write press releases."] * 2, "penetration": [None, None]})
        assert len(build_penetration_lookup(penetration_df)) == 1

    def test_float_noise_is_not_treated_as_a_conflict(self):
        penetration_df = pd.DataFrame({"task": ["Write press releases."] * 2, "penetration": [0.7263, 0.7263 + 1e-12]})
        assert len(build_penetration_lookup(penetration_df)) == 1

    def test_a_real_difference_just_above_tolerance_is_a_conflict(self):
        penetration_df = pd.DataFrame({"task": ["Write press releases."] * 2, "penetration": [0.7263, 0.7263 + 1e-6]})
        with pytest.raises(ValueError, match="disagreeing penetration values"):
            build_penetration_lookup(penetration_df)

    def test_tolerance_is_adjustable_for_a_genuinely_negligible_spread(self):
        penetration_df = pd.DataFrame({"task": ["Write press releases."] * 2, "penetration": [0.7263, 0.7264]})
        assert len(build_penetration_lookup(penetration_df, tolerance=1e-3)) == 1

    def test_only_repeated_texts_are_checked(self):
        """Distinct tasks may hold any values; disagreement is only meaningful within one text."""
        penetration_df = pd.DataFrame({"task": ["Write press releases.", "Draft a budget."], "penetration": [0.7263, 0.4]})
        assert len(build_penetration_lookup(penetration_df)) == 2

    def test_collapsing_is_reported_on_stdout(self, capsys):
        penetration_df = pd.DataFrame({"task": ["Write press releases."] * 8, "penetration": [0.7263] * 8})
        build_penetration_lookup(penetration_df)
        assert "Collapsed 7 repeated row(s)" in capsys.readouterr().out

    def test_nothing_is_reported_when_there_is_nothing_to_collapse(self, capsys):
        penetration_df = pd.DataFrame({"task": ["Write press releases.", "Draft a budget."], "penetration": [0.7263, 0.4]})
        build_penetration_lookup(penetration_df)
        assert "Collapsed" not in capsys.readouterr().out

    def test_merge_against_the_lookup_does_not_add_rows(self):
        """The regression this fix exists for: 19,281 classified tasks became 19,295 rows."""
        classified_tasks_df = pd.DataFrame(
            {
                "Task ID": [1, 2, 3],
                "Task": ["Write press releases.", "Write press releases.", "Draft a budget."],
                "Demand Type": ["Bounded", "Unbounded", "Bounded"],
            }
        )
        classified_tasks_df["task_lower"] = classified_tasks_df["Task"].str.lower().str.strip()
        penetration_df = pd.DataFrame({"task": ["Write press releases."] * 8 + ["Draft a budget."], "penetration": [0.7263] * 8 + [0.1]})

        merged_df = classified_tasks_df.merge(build_penetration_lookup(penetration_df), on="task_lower", how="left", validate="many_to_one")
        assert len(merged_df) == len(classified_tasks_df)
        assert merged_df["penetration"].tolist() == pytest.approx([0.7263, 0.7263, 0.1])


class TestAttachDominantDemand:
    """
    The label must always be re-derived from the composition it summarises. Copying
    it through an aggregation is what left 8 SOC codes — Chief Executives among
    them — labelled with a demand type their own pct_* columns contradicted.
    """

    @staticmethod
    def _composition(bounded, unbounded, adversarial):
        return pd.DataFrame({"pct_bounded": [bounded], "pct_unbounded": [unbounded], "pct_adversarial": [adversarial]})

    def test_picks_the_largest_share(self):
        labelled = attach_dominant_demand(self._composition(0.281, 0.419, 0.301))
        assert labelled["dominant_demand"].iloc[0] == "Unbounded"

    def test_strength_is_the_dominant_share(self):
        labelled = attach_dominant_demand(self._composition(0.281, 0.419, 0.301))
        assert labelled["dominant_strength"].iloc[0] == pytest.approx(0.419)

    def test_ties_resolve_to_the_first_listed_type(self):
        labelled = attach_dominant_demand(self._composition(0.5, 0.5, 0.0))
        assert labelled["dominant_demand"].iloc[0] == "Bounded"

    def test_an_occupation_with_no_task_importance_still_gets_a_label(self):
        labelled = attach_dominant_demand(self._composition(float("nan"), float("nan"), float("nan")))
        assert labelled["dominant_demand"].iloc[0] == "Bounded"
        assert pd.isna(labelled["dominant_strength"].iloc[0])

    def test_relabelling_after_aggregation_overrides_a_stale_label(self):
        """The Chief Executives case: two O*NET rows averaging to a different winner."""
        onet_rows_df = pd.DataFrame(
            {
                "OCC_CODE": ["11-1011", "11-1011"],
                "pct_bounded": [0.30, 0.262],
                "pct_unbounded": [0.20, 0.638],
                "pct_adversarial": [0.50, 0.100],
                "dominant_demand": ["Adversarial", "Unbounded"],
            }
        )
        # "first" would carry Adversarial through, but the averaged composition is
        # 0.281 / 0.419 / 0.300 — Unbounded.
        aggregated_df = (
            onet_rows_df.groupby("OCC_CODE").agg({"pct_bounded": "mean", "pct_unbounded": "mean", "pct_adversarial": "mean"}).reset_index()
        )
        relabelled_df = attach_dominant_demand(aggregated_df)

        assert onet_rows_df["dominant_demand"].iloc[0] == "Adversarial"
        assert relabelled_df["dominant_demand"].iloc[0] == "Unbounded"

    def test_label_always_agrees_with_the_composition_it_summarises(self):
        occupation_df = pd.DataFrame(
            {
                "pct_bounded": [0.589, 0.450, 0.197, 0.508, 0.0],
                "pct_unbounded": [0.000, 0.462, 0.407, 0.492, 1.0],
                "pct_adversarial": [0.411, 0.087, 0.397, 0.000, 0.0],
            }
        )
        labelled = attach_dominant_demand(occupation_df)
        for _, row in labelled.iterrows():
            expected = max(
                ("Bounded", row["pct_bounded"]),
                ("Unbounded", row["pct_unbounded"]),
                ("Adversarial", row["pct_adversarial"]),
                key=lambda pair: pair[1],
            )[0]
            assert row["dominant_demand"] == expected
            assert row["dominant_strength"] == pytest.approx(row[f"pct_{expected.lower()}"])
