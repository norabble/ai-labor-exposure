"""Tests for cps_historical_panel.py — the ten-group CPS employment panel, 1983 onward."""

import pandas as pd
import pytest

import cps_historical_panel
from cps_historical_panel import CPS_GROUP_SERIES, fetch_cps_group_employment, merge_into_seed


class TestSeriesMapping:
    def test_exactly_ten_leaf_groups(self):
        assert len(CPS_GROUP_SERIES) == 10

    def test_group_names_match_the_dws_soc_mapping(self):
        from dws_panel import DWS_TO_SOC_MAJOR

        assert set(CPS_GROUP_SERIES) == set(DWS_TO_SOC_MAJOR)

    def test_no_aggregate_series_included(self):
        """Aggregates would double-count against their own leaves."""
        aggregates = {"LNU02032201", "LNU02032205", "LNU02032208", "LNU02032212"}
        assert not (set(CPS_GROUP_SERIES.values()) & aggregates)


class TestFetch:
    def test_annual_means_are_assembled_into_long_form(self, monkeypatch):
        def fake_fetch(series_id, start_year, end_year):
            return pd.Series({1983: 100.0, 1984: 110.0}, name=series_id)

        monkeypatch.setattr(cps_historical_panel, "fetch_annual_means", fake_fetch)
        panel_df = fetch_cps_group_employment(1983, 1984)
        assert set(panel_df.columns) == {"year", "cps_group", "employed_thousands"}
        assert len(panel_df) == 20  # 10 groups x 2 years
        assert panel_df["employed_thousands"].iloc[0] == pytest.approx(100.0)

    def test_a_failed_series_is_skipped_not_fatal(self, monkeypatch):
        def fake_fetch(series_id, start_year, end_year):
            if series_id == CPS_GROUP_SERIES["service occupations"]:
                return None
            return pd.Series({1983: 100.0}, name=series_id)

        monkeypatch.setattr(cps_historical_panel, "fetch_annual_means", fake_fetch)
        with pytest.warns(UserWarning):
            panel_df = fetch_cps_group_employment(1983, 1983)
        assert "service occupations" not in set(panel_df["cps_group"])
        assert len(panel_df) == 9


class TestSeedMerge:
    def test_fetched_rows_override_seed_rows_for_the_same_year_and_group(self, tmp_path):
        seed_path = tmp_path / "seed.csv"
        pd.DataFrame([{"year": 1983, "cps_group": "service occupations", "employed_thousands": 1.0}]).to_csv(seed_path, index=False)
        fetched_df = pd.DataFrame([{"year": 1983, "cps_group": "service occupations", "employed_thousands": 2.0}])
        merged_df = merge_into_seed(fetched_df, str(seed_path))
        assert len(merged_df) == 1
        assert merged_df["employed_thousands"].iloc[0] == pytest.approx(2.0)

    def test_seed_rows_absent_from_the_fetch_survive(self, tmp_path):
        seed_path = tmp_path / "seed.csv"
        pd.DataFrame([{"year": 1975, "cps_group": "service occupations", "employed_thousands": 5.0}]).to_csv(seed_path, index=False)
        fetched_df = pd.DataFrame([{"year": 1983, "cps_group": "service occupations", "employed_thousands": 2.0}])
        merged_df = merge_into_seed(fetched_df, str(seed_path))
        assert set(merged_df["year"]) == {1975, 1983}

    def test_missing_seed_returns_the_fetch_unchanged(self, tmp_path):
        fetched_df = pd.DataFrame([{"year": 1983, "cps_group": "service occupations", "employed_thousands": 2.0}])
        merged_df = merge_into_seed(fetched_df, str(tmp_path / "absent.csv"))
        assert len(merged_df) == 1


class TestTrendTable:
    @staticmethod
    def _panel(years, groups=("service occupations", "production occupations")):
        return pd.DataFrame(
            [
                {"year": year, "cps_group": group, "employed_thousands": 100.0 + index * 10}
                for index, year in enumerate(years)
                for group in groups
            ]
        )

    def test_one_row_per_group(self):
        from cps_historical_panel import build_cps_group_trends

        trends_df = build_cps_group_trends(self._panel([2021, 2022, 2023]))
        assert len(trends_df) == 2
        assert "cps_group" in trends_df.columns

    def test_employment_columns_are_four_digit_year_keyed(self):
        from cps_historical_panel import build_cps_group_trends

        trends_df = build_cps_group_trends(self._panel([2021, 2022, 2023]))
        assert "TOT_EMP_1983" not in trends_df.columns
        assert "TOT_EMP_2022" in trends_df.columns

    def test_growth_columns_use_the_shared_naming(self):
        from cps_historical_panel import build_cps_group_trends

        trends_df = build_cps_group_trends(self._panel([2021, 2022, 2023]))
        assert "hist_emp_growth_2021_2022" in trends_df.columns
        assert "emp_growth_2022_2023" in trends_df.columns

    def test_growth_values_are_correct(self):
        from cps_historical_panel import build_cps_group_trends

        panel_df = pd.DataFrame(
            [
                {"year": 2022, "cps_group": "service occupations", "employed_thousands": 100.0},
                {"year": 2023, "cps_group": "service occupations", "employed_thousands": 110.0},
            ]
        )
        trends_df = build_cps_group_trends(panel_df)
        assert trends_df["emp_growth_2022_2023"].iloc[0] == pytest.approx(0.10)


class TestComparabilityBreaks:
    def test_break_periods_are_flagged(self):
        from cps_historical_panel import measure_comparability_breaks

        trends_df = pd.DataFrame(
            [
                {
                    "cps_group": "service occupations",
                    "hist_emp_growth_1999_2000": 0.20,
                    "hist_emp_growth_2001_2002": 0.01,
                }
            ]
        )
        break_df = measure_comparability_breaks(trends_df, ("1999_2000",))
        flagged = break_df[break_df["is_break_period"]]
        assert set(flagged["period"]) == {"1999_2000"}
        assert flagged["emp_growth"].iloc[0] == pytest.approx(0.20)

    def test_non_break_periods_are_retained_for_comparison(self):
        from cps_historical_panel import measure_comparability_breaks

        trends_df = pd.DataFrame(
            [
                {
                    "cps_group": "service occupations",
                    "hist_emp_growth_1999_2000": 0.20,
                    "hist_emp_growth_2001_2002": 0.01,
                }
            ]
        )
        break_df = measure_comparability_breaks(trends_df, ("1999_2000",))
        assert set(break_df["period"]) == {"1999_2000", "2001_2002"}


class TestInstrumentAgreement:
    def test_matching_periods_are_paired_by_group(self):
        from cps_historical_panel import compare_with_oews

        cps_trends_df = pd.DataFrame([{"cps_group": "production occupations", "emp_growth_2022_2023": 0.05}])
        oews_trends_df = pd.DataFrame([{"soc_major": "51", "TOT_EMP_2022": 100.0, "TOT_EMP_2023": 103.0}])
        comparison_df = compare_with_oews(cps_trends_df, oews_trends_df, {"51": "production occupations"})
        assert len(comparison_df) == 1
        assert comparison_df["oews_growth"].iloc[0] == pytest.approx(0.03)
        assert comparison_df["difference"].iloc[0] == pytest.approx(0.02)

    def test_periods_absent_from_oews_are_dropped(self):
        from cps_historical_panel import compare_with_oews

        cps_trends_df = pd.DataFrame(
            [{"cps_group": "production occupations", "hist_emp_growth_1983_1984": 0.05, "emp_growth_2022_2023": 0.05}]
        )
        oews_trends_df = pd.DataFrame([{"soc_major": "51", "TOT_EMP_2022": 100.0, "TOT_EMP_2023": 103.0}])
        comparison_df = compare_with_oews(cps_trends_df, oews_trends_df, {"51": "production occupations"})
        assert set(comparison_df["period"]) == {"2022_2023"}

    def test_oews_growth_is_level_weighted_not_rate_averaged(self):
        """A group's OEWS growth must come from summed levels, not a mean of member rates.

        SOC 51 is large and shrinking (1000 -> 900, -10%); SOC 99 is small and
        growing fast (10 -> 15, +50%). An unweighted mean of rates gives +20%.
        The faithful, level-summed answer is (900+15)/(1000+10) - 1 ≈ -9.4% —
        clearly on the opposite side of zero from the mean-of-rates answer, so
        this test would fail against the old unweighted-mean implementation.
        """
        from cps_historical_panel import compare_with_oews

        cps_trends_df = pd.DataFrame([{"cps_group": "production occupations", "emp_growth_2022_2023": 0.05}])
        oews_trends_df = pd.DataFrame(
            [
                {"soc_major": "51", "TOT_EMP_2022": 1000.0, "TOT_EMP_2023": 900.0},
                {"soc_major": "99", "TOT_EMP_2022": 10.0, "TOT_EMP_2023": 15.0},
            ]
        )
        comparison_df = compare_with_oews(cps_trends_df, oews_trends_df, {"51": "production occupations", "99": "production occupations"})
        assert comparison_df["oews_growth"].iloc[0] == pytest.approx(-0.09406, abs=1e-4)

    def test_period_dropped_when_start_level_is_zero(self):
        from cps_historical_panel import compare_with_oews

        cps_trends_df = pd.DataFrame([{"cps_group": "production occupations", "emp_growth_2022_2023": 0.05}])
        oews_trends_df = pd.DataFrame([{"soc_major": "51", "TOT_EMP_2022": 0.0, "TOT_EMP_2023": 103.0}])
        comparison_df = compare_with_oews(cps_trends_df, oews_trends_df, {"51": "production occupations"})
        assert len(comparison_df) == 0
