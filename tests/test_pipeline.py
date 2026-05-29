import pandas as pd
import pytest

from synthesize_dynamic import compute_dynamic_equilibrium
from synthesize_impacts import (
    ADVERSARIAL_REBOUND,
    BOUNDED_REBOUND,
    UNBOUNDED_REBOUND,
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

    def test_zero_unbounded_capacity_raises(self):
        no_unbounded_df = self._fixture_df().copy()
        no_unbounded_df["pct_unbounded"] = 0.0
        with pytest.raises(ValueError, match="No Unbounded capacity"):
            compute_dynamic_equilibrium(no_unbounded_df, "employment")
