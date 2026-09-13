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
