"""
test_composition_model.py
─────────────────────────
Regression tests for synthesize_composition.py — the demand composition model,
which is the dynamic labor equilibrium model with all technology-exposure
information stripped out.

Two of these tests are load-bearing for the model's argument rather than just its
correctness:

  • test_score_is_scale_invariant_in_displacement_rate asserts that the score's
    cross-sectional shape does not depend on D. That property is what makes the
    validation non-circular: a single economy-wide scalar cannot manufacture a
    cross-sectional pattern, so D sets the amplitude and the taxonomy sets the
    shape. If someone later makes D carry cross-sectional information, this test
    is what catches it.

  • test_default_displacement_components_preserve_dynamic_model guards the one
    edit this work makes to existing model code — the defaulted
    displacement_components parameter on compute_dynamic_equilibrium.

synthesize_dynamic.py had no test coverage before this file, so these also serve
as the first tests of the equilibrium itself.
"""

import os

import numpy as np
import pandas as pd
import pytest

from synthesize_composition import (
    ADVERSARIAL_DISPLACEMENT_COLUMN,
    BOUNDED_DISPLACEMENT_COLUMN,
    COMPOSITION_DISPLACEMENT_COMPONENTS,
    build_composition_model,
    compute_composition_displacement,
)
from synthesize_dynamic import AI_DISPLACEMENT_COMPONENTS, compute_dynamic_equilibrium
from synthesize_impacts import ADVERSARIAL_REBOUND, BOUNDED_REBOUND

EMPLOYMENT_COLUMN = "TOT_EMP_25"

DYNAMIC_REPORT_PATH = "data/output/occupation_dynamic_model_report.csv"
DYNAMIC_REPORT_PRESENT = os.path.exists(DYNAMIC_REPORT_PATH)


def _occupation_frame():
    """Four occupations spanning the composition space, with unequal employment weights."""
    return pd.DataFrame(
        {
            "OCC_CODE": ["43-1011", "29-1215", "41-3091", "15-1252"],
            "Title": ["Clerical Supervisors", "Family Physicians", "Sales Representatives", "Software Developers"],
            "pct_bounded": [0.90, 0.10, 0.30, 0.40],
            "pct_unbounded": [0.05, 0.80, 0.20, 0.55],
            "pct_adversarial": [0.05, 0.10, 0.50, 0.05],
            EMPLOYMENT_COLUMN: [1_200_000.0, 120_000.0, 430_000.0, 1_650_000.0],
        }
    )


def _ai_frame():
    """The same occupations carrying AI-penetration contributions instead."""
    occupation_df = _occupation_frame()
    occupation_df["bounded_exposure_contribution"] = [0.42, 0.03, 0.11, 0.19]
    occupation_df["adversarial_exposure_contribution"] = [0.01, 0.01, 0.04, 0.00]
    return occupation_df


class TestComputeCompositionDisplacement:
    def test_components_are_rate_times_composition_times_net_rebound(self):
        composition_model_df = compute_composition_displacement(_occupation_frame(), 0.02)

        assert composition_model_df[BOUNDED_DISPLACEMENT_COLUMN].iloc[0] == pytest.approx(0.02 * (1 - BOUNDED_REBOUND) * 0.90)
        assert composition_model_df[ADVERSARIAL_DISPLACEMENT_COLUMN].iloc[2] == pytest.approx(0.02 * (1 - ADVERSARIAL_REBOUND) * 0.50)

    def test_bounded_displaces_far_more_than_adversarial_per_unit_share(self):
        """Bounded keeps 90% of the shock as displacement; Adversarial keeps 10%."""
        composition_model_df = compute_composition_displacement(_occupation_frame(), 0.02)

        bounded_per_share = composition_model_df[BOUNDED_DISPLACEMENT_COLUMN] / composition_model_df["pct_bounded"]
        adversarial_per_share = composition_model_df[ADVERSARIAL_DISPLACEMENT_COLUMN] / composition_model_df["pct_adversarial"]

        assert (bounded_per_share / adversarial_per_share).round(6).nunique() == 1
        assert bounded_per_share.iloc[0] / adversarial_per_share.iloc[0] == pytest.approx(9.0)

    def test_unbounded_share_contributes_no_displacement(self):
        """Unbounded work is absorption capacity only; it never enters gross_displacement."""
        all_unbounded_df = _occupation_frame()
        all_unbounded_df[["pct_bounded", "pct_unbounded", "pct_adversarial"]] = [0.0, 1.0, 0.0]

        composition_model_df = compute_composition_displacement(all_unbounded_df, 0.02)

        assert (composition_model_df[list(COMPOSITION_DISPLACEMENT_COMPONENTS)] == 0).all().all()

    def test_zero_rate_gives_zero_displacement(self):
        composition_model_df = compute_composition_displacement(_occupation_frame(), 0.0)

        assert (composition_model_df[list(COMPOSITION_DISPLACEMENT_COMPONENTS)] == 0).all().all()

    def test_negative_displacement_rate_is_rejected(self):
        """A negative rate inverts every prediction, so it must raise rather than compute."""
        with pytest.raises(ValueError, match="must be non-negative"):
            compute_composition_displacement(_occupation_frame(), -0.01)

    def test_missing_composition_columns_raise(self):
        incomplete_df = _occupation_frame().drop(columns=["pct_adversarial"])

        with pytest.raises(ValueError, match="missing demand composition columns"):
            compute_composition_displacement(incomplete_df, 0.02)


class TestScaleInvariance:
    def test_score_is_scale_invariant_in_displacement_rate(self):
        """The non-circularity guarantee: D sets amplitude, the taxonomy sets shape.

        If this fails, D has begun carrying cross-sectional information and the
        model's validation is no longer independent of its input.
        """
        low_rate_df = build_composition_model(_occupation_frame(), EMPLOYMENT_COLUMN, 0.005)
        high_rate_df = build_composition_model(_occupation_frame(), EMPLOYMENT_COLUMN, 0.42)

        shape_correlation = np.corrcoef(low_rate_df["net_employment_change"], high_rate_df["net_employment_change"])[0, 1]

        assert shape_correlation == pytest.approx(1.0, abs=1e-12)

    def test_scores_are_exactly_proportional_across_rates(self):
        low_rate_df = build_composition_model(_occupation_frame(), EMPLOYMENT_COLUMN, 0.005)
        high_rate_df = build_composition_model(_occupation_frame(), EMPLOYMENT_COLUMN, 0.42)

        ratio = high_rate_df["net_employment_change"] / low_rate_df["net_employment_change"]

        assert ratio.std() == pytest.approx(0.0, abs=1e-9)
        assert ratio.mean() == pytest.approx(0.42 / 0.005, rel=1e-9)

    def test_occupation_ranking_is_identical_across_rates(self):
        low_rate_df = build_composition_model(_occupation_frame(), EMPLOYMENT_COLUMN, 0.005)
        high_rate_df = build_composition_model(_occupation_frame(), EMPLOYMENT_COLUMN, 0.42)

        assert list(low_rate_df.sort_values("net_employment_change")["OCC_CODE"]) == list(
            high_rate_df.sort_values("net_employment_change")["OCC_CODE"]
        )


class TestConservation:
    @pytest.mark.parametrize("displacement_rate", [0.001, 0.007, 0.02, 0.1, 0.42])
    def test_conservation_holds_at_any_displacement_rate(self, displacement_rate):
        composition_model_df = build_composition_model(_occupation_frame(), EMPLOYMENT_COLUMN, displacement_rate)

        employment_weighted_sum = (composition_model_df["net_employment_change"] * composition_model_df[EMPLOYMENT_COLUMN]).sum()

        assert employment_weighted_sum == pytest.approx(0.0, abs=1.0)

    def test_bounded_heavy_occupation_loses_and_unbounded_heavy_gains(self):
        composition_model_df = build_composition_model(_occupation_frame(), EMPLOYMENT_COLUMN, 0.02).set_index("OCC_CODE")

        assert composition_model_df.loc["43-1011", "net_employment_change"] < 0
        assert composition_model_df.loc["29-1215", "net_employment_change"] > 0

    def test_absorption_capacity_is_unbounded_plus_adversarial(self):
        composition_model_df = build_composition_model(_occupation_frame(), EMPLOYMENT_COLUMN, 0.02)

        assert composition_model_df["absorption_capacity"].to_numpy() == pytest.approx(
            (composition_model_df["pct_unbounded"] + composition_model_df["pct_adversarial"]).to_numpy()
        )


class TestDynamicEquilibriumParameter:
    def test_default_displacement_components_preserve_dynamic_model(self):
        """The one edit to existing model code must be a no-op when the default is used."""
        explicit_df = compute_dynamic_equilibrium(_ai_frame(), EMPLOYMENT_COLUMN, displacement_components=AI_DISPLACEMENT_COMPONENTS)
        defaulted_df = compute_dynamic_equilibrium(_ai_frame(), EMPLOYMENT_COLUMN)

        pd.testing.assert_frame_equal(defaulted_df, explicit_df)

    def test_gross_displacement_sums_the_named_components(self):
        equilibrium_df = compute_dynamic_equilibrium(_ai_frame(), EMPLOYMENT_COLUMN)

        assert equilibrium_df["gross_displacement"].iloc[0] == pytest.approx(0.42 + 0.01)

    def test_missing_components_raise_rather_than_reading_as_zero(self):
        with pytest.raises(ValueError, match="displacement components missing"):
            compute_dynamic_equilibrium(_occupation_frame(), EMPLOYMENT_COLUMN)

    def test_an_unscorable_occupation_is_dropped_with_a_warning(self):
        """A missing component used to break conservation instead of failing cleanly.

        compute_absorption_scalar sums with skipna, so leaving the row in pinned the
        scalar on a different row set than it was applied to, and the conservation
        assertion fired blaming conservation for what was missing input data.
        """
        frame_with_gap = _ai_frame()
        frame_with_gap.loc[0, "bounded_exposure_contribution"] = np.nan

        with pytest.warns(UserWarning, match="cannot be scored"):
            equilibrium_df = compute_dynamic_equilibrium(frame_with_gap, EMPLOYMENT_COLUMN)

        assert len(equilibrium_df) == len(frame_with_gap) - 1
        assert "43-1011" not in set(equilibrium_df["OCC_CODE"])
        assert not equilibrium_df["gross_displacement"].isna().any()

    def test_conservation_still_holds_after_dropping_an_unscorable_occupation(self):
        frame_with_gap = _ai_frame()
        frame_with_gap.loc[0, "bounded_exposure_contribution"] = np.nan

        with pytest.warns(UserWarning, match="cannot be scored"):
            equilibrium_df = compute_dynamic_equilibrium(frame_with_gap, EMPLOYMENT_COLUMN)

        employment_weighted_sum = (equilibrium_df["net_employment_change"] * equilibrium_df[EMPLOYMENT_COLUMN]).sum()
        assert employment_weighted_sum == pytest.approx(0.0, abs=1.0)

    def test_composition_components_appear_in_the_output(self):
        composition_model_df = build_composition_model(_occupation_frame(), EMPLOYMENT_COLUMN, 0.02)

        for column in COMPOSITION_DISPLACEMENT_COMPONENTS:
            assert column in composition_model_df.columns


@pytest.mark.skipif(not DYNAMIC_REPORT_PRESENT, reason="dynamic model report not generated")
class TestAgainstTheRealOccupationSet:
    def _real_frame(self):
        return pd.read_csv(DYNAMIC_REPORT_PATH)

    def test_runs_over_the_full_occupation_set_and_conserves(self):
        composition_model_df = build_composition_model(self._real_frame(), EMPLOYMENT_COLUMN, 0.0070)

        assert len(composition_model_df) == len(self._real_frame())
        employment_weighted_sum = (composition_model_df["net_employment_change"] * composition_model_df[EMPLOYMENT_COLUMN]).sum()
        assert employment_weighted_sum == pytest.approx(0.0, abs=1.0)

    def test_reorders_occupations_relative_to_the_ai_model(self):
        """Related but distinct: stripping penetration re-admits occupations AI has not reached."""
        real_frame = self._real_frame()
        composition_model_df = build_composition_model(real_frame, EMPLOYMENT_COLUMN, 0.0070)

        merged_df = composition_model_df[["OCC_CODE", "net_employment_change"]].merge(
            real_frame[["OCC_CODE", "net_employment_change"]], on="OCC_CODE", suffixes=("_composition", "_ai")
        )
        correlation = merged_df["net_employment_change_composition"].corr(merged_df["net_employment_change_ai"])

        # Strongly related, but far from a relabel.
        assert 0.5 < correlation < 0.95
