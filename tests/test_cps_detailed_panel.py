"""Tests for cps_detailed_panel.py — the local build of the detailed CPS panel, on synthetic microdata."""

import pandas as pd
import pytest

import cps_detailed_panel
import ipums_cps_variables as ipums_variables
from cps_detailed_panel import (
    attach_occ1990dd,
    census_code_ten_group_lookup,
    coding_block_for_year,
    collapse_crosstab,
    select_civilian_employed,
    tabulate_crosstab,
    tabulate_ten_groups_direct,
    tabulate_total,
    tabulate_year,
)


def person_records(rows):
    """rows: dicts overriding a default employed, wage-and-salary adult in January 2010."""
    defaults = {
        "YEAR": 2010,
        "MONTH": 1,
        "SERIAL": 1,
        "CPSID": 1,
        "PERNUM": 1,
        "WTFINL": 1000.0,
        "COMPWT": 1000.0,
        "AGE": 40,
        "EMPSTAT": 10,
        "OCC": 10,
        "OCC1990": 4,
        "CLASSWKR": 21,
    }
    return pd.DataFrame([{**defaults, **row} for row in rows])


@pytest.fixture(autouse=True)
def linked_households(monkeypatch):
    monkeypatch.setattr(ipums_variables, "HOUSEHOLD_CLUSTER", "CPSID")


class TestCodingBlocks:
    @pytest.mark.parametrize(
        ("year", "block"), [(2002, None), (2003, "2003_2010"), (2011, "2011_2019"), (2020, "2020_2026"), (2026, "2020_2026")]
    )
    def test_year_to_block(self, year, block):
        assert coding_block_for_year(year) == block


class TestSelectCivilianEmployed:
    def test_keeps_only_employed_adults(self):
        person_df = person_records([{}, {"EMPSTAT": 21}, {"AGE": 15}, {"EMPSTAT": 12}, {"EMPSTAT": 1}])
        assert len(select_civilian_employed(person_df)) == 2


class TestAttachOcc1990dd:
    def test_maps_through_the_spine_and_reports_the_unmapped_weighted_share(self):
        person_df = person_records([{"OCC1990": 4}, {"OCC1990": 4}, {"OCC1990": 777, "WTFINL": 2000.0}])
        spine_df, unmapped_share = attach_occ1990dd(person_df, {4: 4})
        assert len(spine_df) == 2
        assert unmapped_share == pytest.approx(0.5)


class TestTabulateYear:
    def test_annual_employment_is_the_mean_of_monthly_weighted_totals(self):
        person_df = person_records([{"MONTH": 1, "occ1990dd": 4}, {"MONTH": 1, "occ1990dd": 4, "CPSID": 2}, {"MONTH": 2, "occ1990dd": 4}])
        panel_df = tabulate_year(person_df, 2010)
        all_employed = panel_df[panel_df["universe"] == "all_employed"].iloc[0]
        assert all_employed["employed_thousands"] == pytest.approx(1.5)  # (2000 + 1000) / 2 months / 1000
        assert all_employed["person_months"] == 3
        assert all_employed["distinct_households"] == 2
        assert all_employed["months_observed"] == 2

    def test_wage_salary_excludes_the_self_employed(self):
        person_df = person_records([{"occ1990dd": 4}, {"occ1990dd": 4, "CLASSWKR": 13, "CPSID": 2}])
        panel_df = tabulate_year(person_df, 2010).set_index("universe")
        assert panel_df.loc["all_employed", "employed_thousands"] == pytest.approx(2.0)
        assert panel_df.loc["wage_salary", "employed_thousands"] == pytest.approx(1.0)

    def test_distinct_households_is_nan_when_households_do_not_link(self, monkeypatch):
        monkeypatch.setattr(ipums_variables, "HOUSEHOLD_CLUSTER", "household_month")
        panel_df = tabulate_year(person_records([{"occ1990dd": 4}]), 2010)
        assert panel_df["distinct_households"].isna().all()


class TestCrosstab:
    def test_crosstab_is_keyed_by_block_unit_and_raw_code(self):
        person_df = person_records([{"occ1990dd": 4, "OCC": 10}, {"occ1990dd": 4, "OCC": 20}])
        crosstab_df = tabulate_crosstab(person_df, 2010)
        assert set(crosstab_df["census_code"]) == {10, 20}
        assert set(crosstab_df["coding_block"]) == {"2003_2010"}

    def test_years_before_2003_contribute_nothing(self):
        assert tabulate_crosstab(person_records([{"YEAR": 1995, "occ1990dd": 4}]), 1995).empty

    def test_collapse_sums_years_within_a_block(self):
        yearly_df = pd.DataFrame(
            {
                "year": [2003, 2004],
                "coding_block": ["2003_2010"] * 2,
                "occ1990dd": [4, 4],
                "census_code": [10, 10],
                "employed_thousands": [1.0, 2.0],
            }
        )
        assert collapse_crosstab(yearly_df)["employed_thousands"].tolist() == [3.0]


class TestTenGroupsDirect:
    def test_raw_codes_map_to_groups_through_the_soc_major(self):
        code_list_df = pd.DataFrame(
            {"census_code": [10, 4700], "census_title": ["Chief executives", "Retail supervisors"], "soc_reference": ["11-1011", "41-1011"]}
        )
        lookup = census_code_ten_group_lookup(code_list_df)
        assert lookup == {
            10: "management, business, and financial operations occupations",
            4700: "sales and related occupations",
        }
        employed_df = person_records([{"OCC": 10}, {"OCC": 4700}, {"OCC": 9999}])
        groups_df = tabulate_ten_groups_direct(employed_df, 2010, lookup, "COMPWT").set_index("cps_group")
        assert groups_df.loc["sales and related occupations", "employed_thousands"] == pytest.approx(1.0)
        assert len(groups_df) == 2


class TestTotal:
    def test_total_is_the_monthly_mean_in_thousands(self):
        employed_df = person_records([{"MONTH": 1}, {"MONTH": 2}, {"MONTH": 2}])
        assert tabulate_total(employed_df, 2010, "WTFINL")["total_thousands"] == pytest.approx(1.5)


def test_module_does_not_import_ipumspy_at_top_level():
    assert "ipumspy" not in cps_detailed_panel.__dict__


import numpy as np  # noqa: E402

from cps_detailed_panel import bootstrap_group_variance, cluster_bootstrap_variance  # noqa: E402


class TestBootstrapGroupVariance:
    def test_matches_the_analytic_poisson_variance(self):
        # 400 single-record clusters of weight 1000, scaled to thousands: total = sum(w_i), Var = 400.
        cluster_count = 400
        variance = bootstrap_group_variance(
            np.full(cluster_count, 7), np.full(cluster_count, 1000.0), np.arange(cluster_count), scale=1 / 1000.0, replicates=4000
        )
        assert variance.loc[7] == pytest.approx(400.0, rel=0.10)

    def test_records_in_one_household_move_together(self):
        # 200 clusters of two records each: each cluster total is 2, so Var = 200 * 2**2 = 800, not 400.
        cluster_ids = np.repeat(np.arange(200), 2)
        variance = bootstrap_group_variance(np.full(400, 7), np.full(400, 1000.0), cluster_ids, scale=1 / 1000.0, replicates=4000)
        assert variance.loc[7] == pytest.approx(800.0, rel=0.10)

    def test_is_deterministic_under_a_fixed_seed(self):
        arguments = (np.array([1, 1, 2]), np.array([1.0, 2.0, 3.0]), np.array([0, 1, 2]), 1.0)
        first = bootstrap_group_variance(*arguments, replicates=60, seed=5)
        second = bootstrap_group_variance(*arguments, replicates=60, seed=5)
        pd.testing.assert_series_equal(first, second)


class TestClusterBootstrapVariance:
    def test_one_row_per_unit_and_universe(self):
        person_df = person_records(
            [{"occ1990dd": 4, "CPSID": household} for household in range(30)]
            + [{"occ1990dd": 8, "CPSID": 100 + household, "CLASSWKR": 13} for household in range(30)]
        )
        variance_df = cluster_bootstrap_variance(person_df, replicates=50)
        assert set(zip(variance_df["occ1990dd"], variance_df["universe"])) == {(4, "all_employed"), (8, "all_employed"), (4, "wage_salary")}
        assert (variance_df["sampling_variance"] > 0).all()
