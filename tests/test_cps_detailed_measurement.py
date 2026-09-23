"""Tests for cps_detailed_measurement.py — trends, eligibility, reliability and seams on a synthetic panel."""

import numpy as np
import pandas as pd
import pytest

from cps_detailed_measurement import (
    build_detailed_trends,
    eligible_for_period,
    fixed_set_units,
    growth_frame,
    measure_vintage_seams,
    period_reliability,
    relative_standard_errors,
    reliability_for_units,
)


def panel_rows(cells):
    """cells: (year, occ1990dd, employed_thousands, sampling_variance) in the all_employed universe."""
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


class TestTrends:
    def test_growth_columns_follow_the_shared_naming(self):
        trends_df = build_detailed_trends(panel_rows([(2021, 4, 100.0, 1.0), (2022, 4, 110.0, 1.0), (2023, 4, 121.0, 1.0)]))
        assert trends_df.loc[0, "hist_emp_growth_2021_2022"] == pytest.approx(0.10)
        assert trends_df.loc[0, "emp_growth_2022_2023"] == pytest.approx(0.10)


class TestRelativeStandardErrors:
    def test_rse_is_the_standard_error_over_the_level(self):
        rse_df = relative_standard_errors(panel_rows([(2010, 4, 100.0, 400.0)]))
        assert rse_df.loc[4, 2010] == pytest.approx(0.20)


class TestGrowthVariance:
    def test_delta_method_growth_variance(self):
        # g = E1/E0 - 1 = 0.1; Var(g) = (E1/E0)^2 * (V1/E1^2 + V0/E0^2) = 1.21 * (1/121 + 1/100)
        growth_df = growth_frame(panel_rows([(2010, 4, 100.0, 1.0), (2011, 4, 110.0, 1.0)]), 2010, 2011)
        assert growth_df.loc[4, "growth"] == pytest.approx(0.1)
        assert growth_df.loc[4, "growth_variance"] == pytest.approx(1.21 * (1 / 12100 + 1 / 10000))


class TestEligibility:
    """The headline rule keeps a shrinking occupation until it is genuinely unmeasurable.

    Mutation-proof: occupation 8 shrinks from precise to imprecise. Per-period
    eligibility must keep it in 2010->2011 (both ends precise) and drop it in
    2011->2012 (end imprecise); the fixed-set sensitivity must drop it everywhere.
    Inverting either rule fails at least one assertion.
    """

    @pytest.fixture
    def shrinking_panel(self):
        return panel_rows(
            [
                (2010, 4, 100.0, 4.0),
                (2011, 4, 100.0, 4.0),
                (2012, 4, 100.0, 4.0),
                (2010, 8, 100.0, 4.0),  # RSE 0.02
                (2011, 8, 50.0, 25.0),  # RSE 0.10
                (2012, 8, 5.0, 4.0),  # RSE 0.40 — shrank below measurability
            ]
        )

    def test_per_period_eligibility_keeps_the_occupation_while_both_ends_are_measurable(self, shrinking_panel):
        rse_df = relative_standard_errors(shrinking_panel)
        assert set(eligible_for_period(rse_df, 2010, 2011, 0.20)) == {4, 8}
        assert set(eligible_for_period(rse_df, 2011, 2012, 0.20)) == {4}

    def test_fixed_set_drops_the_occupation_from_every_period(self, shrinking_panel):
        assert set(fixed_set_units(relative_standard_errors(shrinking_panel), 0.20)) == {4}

    def test_no_cutoff_keeps_every_unit_with_both_endpoints(self, shrinking_panel):
        assert set(eligible_for_period(relative_standard_errors(shrinking_panel), 2011, 2012, None)) == {4, 8}


class TestReliability:
    def test_reliability_is_one_minus_noise_share(self):
        # Growth 0.0, 0.2, 0.4, 0.6: observed variance 0.0666...; each unit's sampling variance is chosen to be 0.02.
        levels = [100.0, 100.0, 100.0, 100.0]
        endings = [100.0, 120.0, 140.0, 160.0]
        cells = []
        for code, (start, end) in enumerate(zip(levels, endings), start=1):
            ratio = end / start
            # Var(g) = ratio^2 * (V1/E1^2 + V0/E0^2) with V1 = V0 = V: solve for V giving 0.02.
            variance = 0.02 / (ratio**2 * (1 / end**2 + 1 / start**2))
            cells += [(2010, code, start, variance), (2011, code, end, variance)]
        panel_df = panel_rows(cells)
        observed_variance = np.var([0.0, 0.2, 0.4, 0.6], ddof=1)
        expected = 1 - 0.02 / observed_variance
        assert reliability_for_units(panel_df, 2010, 2011, pd.Index([1, 2, 3, 4])) == pytest.approx(expected)

    def test_period_table_reports_coverage(self):
        # Years span 2022 because attach_growth_columns anchors its pre-AI composite there, as the real panel does.
        panel_df = panel_rows([(2021, 4, 90.0, 4.0), (2022, 4, 100.0, 4.0), (2021, 8, 10.0, 25.0), (2022, 8, 10.0, 25.0)])
        reliability_df = period_reliability(panel_df, build_detailed_trends(panel_df), cutoff=0.20)
        row = reliability_df.iloc[0]
        assert row["n_eligible"] == 1  # occupation 8 has RSE 0.5
        assert row["employment_share_covered"] == pytest.approx(100.0 / 110.0)


class TestSeams:
    def test_seam_periods_are_flagged_and_ordinary_periods_kept(self):
        trends_df = build_detailed_trends(
            panel_rows([(2001, 4, 100.0, 1.0), (2002, 4, 100.0, 1.0), (2003, 4, 150.0, 1.0), (2022, 4, 150.0, 1.0)])
        )
        seam_df = measure_vintage_seams(trends_df).set_index("period")
        assert bool(seam_df.loc["2002_2003", "is_seam_period"])
        assert not bool(seam_df.loc["2001_2002", "is_seam_period"])
