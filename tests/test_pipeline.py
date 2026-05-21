import pandas as pd
import pytest

from synthesize_impacts import (
    ADVERSARIAL_REBOUND,
    BOUNDED_REBOUND,
    UNBOUNDED_REBOUND,
    compute_task_impact,
    derive_narrative,
    rollup_to_occupation,
)


def _task_df(rows):
    return pd.DataFrame(rows, columns=["penetration", "Demand Type", "task_importance"])


class TestComputeTaskImpact:
    def test_bounded_has_full_impact(self):
        result = compute_task_impact(_task_df([(0.5, "Bounded", 1.0)]))
        assert result["task_impact"].iloc[0] == pytest.approx(0.5 * (1 - BOUNDED_REBOUND))

    def test_unbounded_is_partially_absorbed(self):
        result = compute_task_impact(_task_df([(0.5, "Unbounded", 1.0)]))
        assert result["task_impact"].iloc[0] == pytest.approx(0.5 * (1 - UNBOUNDED_REBOUND))

    def test_adversarial_rebounds_fully(self):
        result = compute_task_impact(_task_df([(0.5, "Adversarial", 1.0)]))
        assert result["task_impact"].iloc[0] == pytest.approx(0.5 * (1 - ADVERSARIAL_REBOUND))

    def test_zero_penetration_contributes_nothing(self):
        result = compute_task_impact(_task_df([(0.0, "Bounded", 1.0)]))
        assert result["task_impact"].iloc[0] == 0.0

    def test_error_rows_contribute_nothing(self):
        result = compute_task_impact(_task_df([(0.8, "ERROR", 1.0)]))
        assert result["task_impact"].iloc[0] == 0.0

    def test_importance_scales_impact(self):
        result = compute_task_impact(_task_df([(0.5, "Bounded", 3.0)]))
        assert result["task_impact"].iloc[0] == pytest.approx(0.5 * (1 - BOUNDED_REBOUND) * 3.0)


class TestDeriveNarrative:
    def _row(self, score, penetration):
        return pd.Series({"occupation_impact": score, "mean_penetration": penetration})

    def test_high_displacement_risk(self):
        assert derive_narrative(self._row(0.06, 0.10)) == "High Displacement Risk"

    def test_moderate_displacement_risk(self):
        assert derive_narrative(self._row(0.02, 0.05)) == "Moderate Displacement Risk"

    def test_low_displacement_risk(self):
        assert derive_narrative(self._row(0.005, 0.01)) == "Low Displacement Risk"

    def test_minimal_ai_impact_fallback(self):
        assert derive_narrative(self._row(0.001, 0.001)) == "Minimal AI Impact"

    def test_high_risk_requires_sufficient_penetration(self):
        # Score qualifies but penetration is too low — should not be High Displacement Risk
        result = derive_narrative(self._row(0.06, 0.01))
        assert result != "High Displacement Risk"


class TestRollupToOccupation:
    def _occ_df(self, rows):
        return pd.DataFrame(
            rows,
            columns=["O*NET-SOC Code", "Title", "Demand Type", "penetration", "task_importance", "task_impact"],
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

    def test_occupation_impact_is_importance_weighted(self):
        # Bounded(penetration=0.5, importance=2): task_impact = 0.5×1.0×2 = 1.0
        # Unbounded(penetration=0.3, importance=1): task_impact = 0.3×0.5×1 = 0.15
        # occupation_impact = (1.0 + 0.15) / (2.0 + 1.0) = 1.15 / 3.0
        df = self._occ_df(
            [
                ("11-1011.00", "Chief Executives", "Bounded", 0.5, 2.0, 1.0),
                ("11-1011.00", "Chief Executives", "Unbounded", 0.3, 1.0, 0.15),
            ]
        )
        result = rollup_to_occupation(df)
        assert result.iloc[0]["occupation_impact"] == pytest.approx(1.15 / 3.0)
