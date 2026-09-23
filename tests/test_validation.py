"""
tests/test_validation.py
────────────────────────
Unit tests for the helpers validate_bls.py builds every correlation on.

validate_bls.py is the largest module in the project and held no tests, which
meant the sample selection, outlier trimming and sector-adjustment feeding every
published r were unverified. These are the pure functions in it; the plotting
and file IO around them are not covered here.

Covers:
  • _label                       — period key to axis label
  • _clean                       — NaN/inf handling and outlier trimming
  • _correlations                — the model and Eloundou correlations
  • _compute_shift_share_residuals — growth minus employment-weighted sector mean
"""

import numpy as np
import pandas as pd
import pytest
import scipy.stats as stats

from validate_bls import _clean, _compute_shift_share_residuals, _correlations, _label


class TestLabel:
    def test_year_over_year_period_expands_to_four_digit_years(self):
        assert _label("22_23") == "2022→2023"

    def test_historical_period_expands_the_same_way(self):
        assert _label("05_06") == "2005→2006"

    def test_composite_is_named_rather_than_expanded(self):
        assert _label("composite") == "Composite (2022→latest)"


class TestClean:
    """
    Note what this does: it trims on the *outcome* variable, and asymmetrically.
    That is a deliberate robustness choice, but it selects on the dependent
    variable, so the boundaries are pinned here to make any change to them visible.
    """

    @staticmethod
    def _frame(growth_values, score_values=None, growth_col="emp_growth_22_23"):
        return pd.DataFrame(
            {
                growth_col: growth_values,
                "occupation_exposure": score_values if score_values is not None else [0.05] * len(growth_values),
            }
        )

    def test_rows_missing_growth_are_dropped(self):
        cleaned = _clean(self._frame([0.1, None, 0.2]), "emp_growth_22_23", is_composite=False)
        assert len(cleaned) == 2

    def test_rows_missing_the_score_are_dropped(self):
        cleaned = _clean(self._frame([0.1, 0.2], [0.05, None]), "emp_growth_22_23", is_composite=False)
        assert len(cleaned) == 1

    def test_infinite_growth_is_dropped(self):
        """Growth divides by the earlier year, so a zero base yields inf rather than NaN."""
        cleaned = _clean(self._frame([0.1, np.inf, -np.inf]), "emp_growth_22_23", is_composite=False)
        assert len(cleaned) == 1

    def test_infinite_score_is_dropped(self):
        cleaned = _clean(self._frame([0.1, 0.2], [0.05, np.inf]), "emp_growth_22_23", is_composite=False)
        assert len(cleaned) == 1

    @pytest.mark.parametrize("growth", [1.0, 1.5, -0.5, -0.9])
    def test_year_over_year_employment_outliers_are_trimmed(self, growth):
        """The window is exclusive: exactly +1.0 and exactly -0.5 are removed."""
        cleaned = _clean(self._frame([growth]), "emp_growth_22_23", is_composite=False)
        assert len(cleaned) == 0

    @pytest.mark.parametrize("growth", [0.999, -0.499, 0.0])
    def test_year_over_year_employment_growth_inside_the_window_is_kept(self, growth):
        cleaned = _clean(self._frame([growth]), "emp_growth_22_23", is_composite=False)
        assert len(cleaned) == 1

    def test_the_composite_window_is_wider_than_the_year_over_year_one(self):
        """A composite spans three years, so growth that is an outlier for one year is not for three."""
        borderline = self._frame([1.5], growth_col="emp_growth_composite")
        assert len(_clean(borderline, "emp_growth_composite", is_composite=True)) == 1
        assert len(_clean(self._frame([1.5]), "emp_growth_22_23", is_composite=False)) == 0

    @pytest.mark.parametrize("growth", [2.0, -0.75, 3.0])
    def test_composite_employment_outliers_are_trimmed(self, growth):
        frame = self._frame([growth], growth_col="emp_growth_composite")
        assert len(_clean(frame, "emp_growth_composite", is_composite=True)) == 0

    def test_wage_growth_is_not_trimmed(self):
        """Trimming applies only to employment growth; wage outliers are kept."""
        frame = self._frame([5.0, -0.9], growth_col="wage_growth_22_23")
        cleaned = _clean(frame, "wage_growth_22_23", is_composite=False)
        assert len(cleaned) == 2

    def test_an_alternative_score_column_is_honoured(self):
        frame = pd.DataFrame({"emp_growth_22_23": [0.1, 0.2], "net_employment_change": [0.01, None]})
        cleaned = _clean(frame, "emp_growth_22_23", is_composite=False, score_col="net_employment_change")
        assert len(cleaned) == 1

    def test_the_input_frame_is_not_modified(self):
        frame = self._frame([0.1, np.inf])
        _clean(frame, "emp_growth_22_23", is_composite=False)
        assert len(frame) == 2
        assert np.isinf(frame["emp_growth_22_23"].iloc[1])


class TestCorrelations:
    def test_both_correlations_match_scipy_on_the_same_columns(self):
        frame = pd.DataFrame(
            {
                "occupation_exposure": [0.01, 0.02, 0.03, 0.04, 0.05],
                "eloundou_exposure_mid": [0.5, 0.3, 0.4, 0.2, 0.1],
                "emp_growth_22_23": [0.02, 0.01, 0.00, -0.01, -0.02],
            }
        )
        r_impact, p_impact, r_eloundou, p_eloundou = _correlations(frame, "emp_growth_22_23")

        expected_impact = stats.pearsonr(frame["occupation_exposure"], frame["emp_growth_22_23"])
        expected_eloundou = stats.pearsonr(frame["eloundou_exposure_mid"], frame["emp_growth_22_23"])
        assert (r_impact, p_impact) == pytest.approx(tuple(expected_impact))
        assert (r_eloundou, p_eloundou) == pytest.approx(tuple(expected_eloundou))

    def test_a_perfect_inverse_relationship_returns_minus_one(self):
        frame = pd.DataFrame(
            {
                "occupation_exposure": [0.01, 0.02, 0.03],
                "eloundou_exposure_mid": [0.01, 0.02, 0.03],
                "emp_growth_22_23": [0.03, 0.02, 0.01],
            }
        )
        r_impact, _, _, _ = _correlations(frame, "emp_growth_22_23")
        assert r_impact == pytest.approx(-1.0)


class TestComputeShiftShareResiduals:
    """
    The residual strips the national trend and the sector cycle, leaving the
    occupation-specific deviation. The sector mean is employment-weighted, so a
    large occupation pulls its sector's baseline toward its own growth.
    """

    @staticmethod
    def _frame(growth, employment, soc_major, index=None):
        return pd.DataFrame(
            {"emp_growth_22_23": growth, "TOT_EMP_25": employment, "soc_major": soc_major},
            index=index,
        )

    def _residuals(self, frame):
        return _compute_shift_share_residuals(frame, "emp_growth_22_23", "TOT_EMP_25", "soc_major")

    def test_the_sector_mean_is_employment_weighted_not_a_plain_mean(self):
        """One occupation of 900 workers at 10% and one of 100 at 0% average to 9%, not 5%."""
        residuals = self._residuals(self._frame([0.10, 0.00], [900.0, 100.0], ["11", "11"]))
        assert residuals.iloc[0] == pytest.approx(0.01)
        assert residuals.iloc[1] == pytest.approx(-0.09)

    def test_residuals_are_computed_within_each_sector_independently(self):
        residuals = self._residuals(self._frame([0.10, 0.20, 0.50, 0.50], [100.0] * 4, ["11", "11", "29", "29"]))
        assert residuals.iloc[0] == pytest.approx(-0.05)
        assert residuals.iloc[1] == pytest.approx(0.05)
        assert residuals.iloc[2] == pytest.approx(0.0)
        assert residuals.iloc[3] == pytest.approx(0.0)

    def test_a_lone_occupation_in_its_sector_has_no_deviation(self):
        residuals = self._residuals(self._frame([0.10], [100.0], ["11"]))
        assert residuals.iloc[0] == pytest.approx(0.0)

    def test_an_occupation_missing_growth_gets_no_residual(self):
        residuals = self._residuals(self._frame([0.10, None], [100.0, 100.0], ["11", "11"]))
        assert pd.isna(residuals.iloc[1])

    def test_a_row_missing_growth_does_not_shift_its_sector_baseline(self):
        """It is excluded from the mean, so the surviving occupation is still the whole sector."""
        residuals = self._residuals(self._frame([0.10, None], [100.0, 5000.0], ["11", "11"]))
        assert residuals.iloc[0] == pytest.approx(0.0)

    def test_a_sector_with_no_usable_rows_yields_no_residuals(self):
        residuals = self._residuals(self._frame([None, 0.20], [100.0, 100.0], ["11", "29"]))
        assert pd.isna(residuals.iloc[0])
        assert residuals.iloc[1] == pytest.approx(0.0)

    def test_results_align_on_the_index_rather_than_by_position(self):
        """
        The frame reaching this has been merged and filtered upstream, so its index
        is not a clean range. Aligning positionally would silently pair an
        occupation with another sector's baseline.
        """
        frame = self._frame([0.10, 0.20, 0.50], [100.0] * 3, ["11", "11", "29"], index=[70, 3, 41])
        residuals = self._residuals(frame)
        assert list(residuals.index) == [70, 3, 41]
        assert residuals.loc[70] == pytest.approx(-0.05)
        assert residuals.loc[3] == pytest.approx(0.05)
        assert residuals.loc[41] == pytest.approx(0.0)

    def test_the_employment_weighted_residuals_sum_to_zero_within_a_sector(self):
        """The defining property: the sector's own weighted deviation is nothing."""
        frame = self._frame([0.10, -0.02, 0.04], [900.0, 100.0, 500.0], ["11", "11", "11"])
        residuals = self._residuals(frame)
        assert float((residuals * frame["TOT_EMP_25"]).sum()) == pytest.approx(0.0, abs=1e-9)
