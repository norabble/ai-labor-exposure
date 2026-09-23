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


class TestReadYearPersons:
    def test_a_pre_1998_extract_missing_compwt_reads_as_nan_not_keyerror(self, tmp_path, monkeypatch):
        """A pre-1998 extract, requested without COMPWT (Ruling 11), must reindex rather than
        raise KeyError when that column is absent from the downloaded CSV."""
        extract_dir = tmp_path / "basic" / "1990"
        extract_dir.mkdir(parents=True)
        columns_without_compwt = [name for name in ipums_variables.BASIC_MONTHLY_VARIABLES if name != "COMPWT"]
        chunk_df = person_records([{}]).reindex(columns=columns_without_compwt)
        monkeypatch.setattr(cps_detailed_panel.download_ipums_cps, "extract_is_downloaded", lambda directory: True)
        monkeypatch.setattr(cps_detailed_panel.download_ipums_cps, "read_extract", lambda directory: iter([chunk_df]))
        result_df = cps_detailed_panel.read_year_persons(1990, raw_dir=str(tmp_path))
        assert "COMPWT" in result_df.columns
        assert result_df["COMPWT"].isna().all()


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


class TestHouseholdClusterIds:
    def test_unlinked_cpsid_zero_records_fall_back_to_household_month(self):
        person_df = person_records(
            [
                {"CPSID": 0, "YEAR": 2010, "MONTH": 1, "SERIAL": 5},
                {"CPSID": 0, "YEAR": 2010, "MONTH": 1, "SERIAL": 6},
                {"CPSID": 1, "YEAR": 2010, "MONTH": 1, "SERIAL": 7},
            ]
        )
        cluster_ids = cps_detailed_panel.household_cluster_ids(person_df)
        # The two CPSID==0 records are in different households and must not collapse into one cluster.
        assert cluster_ids.iloc[0] != cluster_ids.iloc[1]
        # A real linked CPSID must never collide with a household-month fallback id.
        assert cluster_ids.iloc[2] not in {cluster_ids.iloc[0], cluster_ids.iloc[1]}

    def test_linked_cpsid_still_clusters_across_months(self):
        person_df = person_records(
            [
                {"CPSID": 42, "YEAR": 2010, "MONTH": 1, "SERIAL": 1},
                {"CPSID": 42, "YEAR": 2010, "MONTH": 2, "SERIAL": 9},
            ]
        )
        cluster_ids = cps_detailed_panel.household_cluster_ids(person_df)
        assert cluster_ids.iloc[0] == cluster_ids.iloc[1]


class TestClusterBootstrapVariance:
    def test_one_row_per_unit_and_universe(self):
        person_df = person_records(
            [{"occ1990dd": 4, "CPSID": household} for household in range(30)]
            + [{"occ1990dd": 8, "CPSID": 100 + household, "CLASSWKR": 13} for household in range(30)]
        )
        variance_df = cluster_bootstrap_variance(person_df, replicates=50)
        assert set(zip(variance_df["occ1990dd"], variance_df["universe"])) == {(4, "all_employed"), (8, "all_employed"), (4, "wage_salary")}
        assert (variance_df["sampling_variance"] > 0).all()


from cps_detailed_panel import (  # noqa: E402
    GateFailureError,
    all_gates_pass,
    build_rebuilt_tables,
    gate_g1,
    gate_g2,
    gate_g5,
    gate_g6,
    promote_rebuilt,
)

SALES = "sales and related occupations"


def _published(rows):
    return pd.DataFrame(rows, columns=["year", "cps_group", "employed_thousands", "months_observed"])


class TestGateG1:
    def test_a_complete_year_within_one_percent_passes(self):
        rebuilt_df = pd.DataFrame({"year": [2010], "cps_group": [SALES], "employed_thousands": [100.5], "months_observed": [12]})
        published_df = _published([[2010, SALES, 100.0, None], [2011, SALES, 100.0, None]])
        gate_df = gate_g1(rebuilt_df, published_df)
        assert gate_df["gated"].tolist() == [True]
        assert gate_df["passed"].tolist() == [True]

    def test_a_two_percent_gap_fails(self):
        rebuilt_df = pd.DataFrame({"year": [2010], "cps_group": [SALES], "employed_thousands": [102.0], "months_observed": [12]})
        gate_df = gate_g1(rebuilt_df, _published([[2010, SALES, 100.0, None], [2011, SALES, 100.0, None]]))
        assert gate_df["passed"].tolist() == [False]

    def test_the_latest_published_year_without_a_month_count_is_not_gated(self):
        # A year with no month count is complete only if a later published year exists.
        rebuilt_df = pd.DataFrame({"year": [2011], "cps_group": [SALES], "employed_thousands": [150.0], "months_observed": [12]})
        gate_df = gate_g1(rebuilt_df, _published([[2010, SALES, 100.0, None], [2011, SALES, 100.0, None]]))
        assert gate_df["gated"].tolist() == [False]

    def test_partial_rebuilt_years_are_reported_not_gated(self):
        rebuilt_df = pd.DataFrame({"year": [2010], "cps_group": [SALES], "employed_thousands": [150.0], "months_observed": [8]})
        gate_df = gate_g1(rebuilt_df, _published([[2010, SALES, 100.0, None], [2011, SALES, 100.0, None]]))
        assert gate_df["gated"].tolist() == [False]


class TestGateG2:
    def test_years_from_1998_are_gated_and_earlier_years_reported(self):
        totals_df = pd.DataFrame({"year": [1997, 1998], "total_thousands": [130.0, 100.5], "months_observed": [12, 12]})
        gate_df = gate_g2(totals_df, pd.Series({1997: 100.0, 1998: 100.0}))
        assert gate_df["gated"].tolist() == [False, True]
        assert bool(gate_df["passed"].iloc[1])

    def test_an_unavailable_published_series_fails_rather_than_passing_vacuously(self):
        totals_df = pd.DataFrame({"year": [2010], "total_thousands": [100.0], "months_observed": [12]})
        gate_df = gate_g2(totals_df, None)
        assert gate_df["gated"].tolist() == [True]
        assert gate_df["passed"].tolist() == [False]


class TestGateG5AndG6:
    def test_g5_fails_when_an_employed_code_is_in_no_group(self):
        panel_df = pd.DataFrame({"occ1990dd": [4, 905], "employed_thousands": [10.0, 1.0]})
        groups_df = pd.DataFrame({"occ1990dd": [4], "dorn_group": ["exec"]})
        assert gate_g5(panel_df, groups_df)["passed"].tolist() == [False]

    def test_g6_gates_every_year_at_one_percent(self):
        gate_df = gate_g6(pd.Series({1983: 0.004, 1984: 0.02}))
        assert gate_df["passed"].tolist() == [True, False]


def _gate_row(gate, gated, passed):
    return {"gate": gate, "scope": "x", "observed": 0.0, "threshold": 0.01, "gated": gated, "passed": passed}


class TestAllGatesPass:
    def test_every_required_gate_must_have_a_gated_row(self):
        gates_df = pd.DataFrame([_gate_row("G1", True, True), _gate_row("G2", False, None)])
        assert not all_gates_pass(gates_df, ("G1", "G2"))

    def test_a_reported_row_never_blocks(self):
        gates_df = pd.DataFrame([_gate_row("G1", True, True), _gate_row("G1", False, None)])
        assert all_gates_pass(gates_df, ("G1",))


class TestPromote:
    def test_refuses_when_a_gate_failed_and_copies_nothing(self, tmp_path):
        gates_path = tmp_path / "gates.csv"
        pd.DataFrame([_gate_row("G1", True, False)]).to_csv(gates_path, index=False)
        source, destination = tmp_path / "rebuilt.csv", tmp_path / "seed.csv"
        source.write_text("a\n1\n")
        with pytest.raises(GateFailureError):
            promote_rebuilt({str(source): str(destination)}, str(gates_path), ("G1",))
        assert not destination.exists()

    def test_refusal_names_a_required_gate_that_has_no_gated_row(self, tmp_path):
        gates_path = tmp_path / "gates.csv"
        pd.DataFrame([_gate_row("G1", True, True)]).to_csv(gates_path, index=False)
        source, destination = tmp_path / "rebuilt.csv", tmp_path / "seed.csv"
        source.write_text("a\n1\n")
        with pytest.raises(GateFailureError, match="G2"):
            promote_rebuilt({str(source): str(destination)}, str(gates_path), ("G1", "G2"))
        assert not destination.exists()

    def test_copies_when_every_gate_passed(self, tmp_path):
        gates_path = tmp_path / "gates.csv"
        pd.DataFrame([_gate_row("G1", True, True)]).to_csv(gates_path, index=False)
        source, destination = tmp_path / "rebuilt.csv", tmp_path / "seed.csv"
        source.write_text("a\n1\n")
        promote_rebuilt({str(source): str(destination)}, str(gates_path), ("G1",))
        assert destination.read_text() == "a\n1\n"


class TestCacheManifest:
    def _spine_path(self, tmp_path, contents="source_code,occ1990dd\n1,1\n"):
        spine_path = tmp_path / "spine.csv"
        spine_path.write_text(contents)
        return str(spine_path)

    def test_manifest_changes_when_a_keyed_constant_changes(self, tmp_path, monkeypatch):
        spine_path = self._spine_path(tmp_path)
        before = cps_detailed_panel.compute_cache_manifest(spine_path)
        monkeypatch.setattr(ipums_variables, "HOUSEHOLD_CLUSTER", "household_month")
        after = cps_detailed_panel.compute_cache_manifest(spine_path)
        assert before != after

    def test_manifest_changes_when_the_spine_seed_contents_change(self, tmp_path):
        spine_path = self._spine_path(tmp_path)
        before = cps_detailed_panel.compute_cache_manifest(spine_path)
        with open(spine_path, "w") as spine_file:
            spine_file.write("source_code,occ1990dd\n1,2\n")
        after = cps_detailed_panel.compute_cache_manifest(spine_path)
        assert before != after

    def test_cache_is_invalid_when_no_manifest_has_been_written(self, tmp_path):
        spine_path = self._spine_path(tmp_path)
        assert not cps_detailed_panel.cache_is_valid(str(tmp_path / "tabulated"), spine_path)

    def test_cache_is_valid_after_writing_and_invalid_once_a_constant_changes(self, tmp_path, monkeypatch):
        spine_path = self._spine_path(tmp_path)
        tabulated_dir = str(tmp_path / "tabulated")
        cps_detailed_panel.write_cache_manifest(tabulated_dir, spine_path)
        assert cps_detailed_panel.cache_is_valid(tabulated_dir, spine_path)
        monkeypatch.setattr(ipums_variables, "EMPLOYED_EMPSTAT_CODES", (99,))
        assert not cps_detailed_panel.cache_is_valid(tabulated_dir, spine_path)


def test_a_stale_cache_manifest_forces_the_year_to_be_recomputed(monkeypatch, tmp_path):
    """A cached year built under different keyed constants (e.g. EMPLOYED_EMPSTAT_CODES) must be
    recomputed, not silently reused — the whole point of Ruling on cache keying."""
    monkeypatch.setattr(ipums_variables, "VERIFICATION_STATUS", "verified")
    tabulated_dir = tmp_path / "tabulated"
    raw_dir = tmp_path / "raw"
    spine_path = tmp_path / "spine.csv"
    spine_path.write_text("source_code,occ1990dd\n1,1\n")
    monkeypatch.setattr(cps_detailed_panel, "SPINE_SEED_PATH", str(spine_path))

    def fake_year_tables(year):
        panel_df = pd.DataFrame(
            [
                {
                    "year": year,
                    "occ1990dd": 1,
                    "universe": "all_employed",
                    "employed_thousands": 1.0,
                    "person_months": 1,
                    "distinct_households": 1.0,
                    "months_observed": 12,
                    "sampling_variance": 0.0,
                }
            ]
        )
        return cps_detailed_panel.YearTables(
            panel_df,
            pd.DataFrame(columns=["year", "coding_block", "occ1990dd", "census_code", "employed_thousands"]),
            pd.DataFrame(columns=["year", "cps_group", "employed_thousands", "months_observed"]),
            {"year": year, "total_thousands": 1.0, "months_observed": 12, "unmapped_share": 0.0},
        )

    # Seed a cached year 2020 under different (stale) constants.
    monkeypatch.setattr(ipums_variables, "EMPLOYED_EMPSTAT_CODES", (99,))
    cps_detailed_panel.write_year_cache(2020, fake_year_tables(2020), str(tabulated_dir))
    cps_detailed_panel.write_cache_manifest(str(tabulated_dir), str(spine_path))
    monkeypatch.setattr(ipums_variables, "EMPLOYED_EMPSTAT_CODES", (10, 12))  # restore the real value

    build_calls = []

    def fake_build_year_tables(year, person_df, spine, lookups_by_block):
        build_calls.append(year)
        return fake_year_tables(year)

    monkeypatch.setattr(cps_detailed_panel, "spine_lookup", lambda: {1: 1})
    monkeypatch.setattr(cps_detailed_panel, "ten_group_lookups", lambda: {})
    monkeypatch.setattr(cps_detailed_panel, "read_year_persons", lambda year, raw_dir: pd.DataFrame({"placeholder": [1]}))
    monkeypatch.setattr(cps_detailed_panel, "build_year_tables", fake_build_year_tables)
    monkeypatch.setattr(cps_detailed_panel, "load_occ1990dd_groups", lambda: pd.DataFrame({"occ1990dd": [1], "dorn_group": ["exec"]}))
    published_path = tmp_path / "published.csv"
    pd.DataFrame(columns=["year", "cps_group", "employed_thousands", "months_observed"]).to_csv(published_path, index=False)
    monkeypatch.setattr(cps_detailed_panel, "PUBLISHED_TEN_GROUP_PANEL_PATH", str(published_path))

    import historical_displacement

    monkeypatch.setattr(historical_displacement, "fetch_annual_means", lambda series_id, first_year, last_year: None)

    cps_detailed_panel.build_rebuilt_tables(
        2020,
        2020,
        raw_dir=str(raw_dir),
        tabulated_dir=str(tabulated_dir),
        panel_path=str(tmp_path / "panel.csv"),
        crosstab_path=str(tmp_path / "crosstab.csv"),
        gates_path=str(tmp_path / "gates.csv"),
    )
    assert build_calls == [2020]  # recomputed despite an on-disk cache file for 2020


def test_the_build_refuses_until_task_2_has_verified_ipums(monkeypatch):
    monkeypatch.setattr(ipums_variables, "VERIFICATION_STATUS", "unverified")
    with pytest.raises(RuntimeError, match="Task 2"):
        build_rebuilt_tables(1983, 1983)


def test_the_build_raises_a_clear_error_when_no_year_is_downloaded(monkeypatch, tmp_path):
    monkeypatch.setattr(ipums_variables, "VERIFICATION_STATUS", "verified")
    monkeypatch.setattr(cps_detailed_panel, "read_year_cache", lambda year, tabulated_dir: None)
    monkeypatch.setattr(cps_detailed_panel, "read_year_persons", lambda year, raw_dir: None)
    with pytest.raises(RuntimeError, match="[Nn]o.*download"):
        build_rebuilt_tables(1983, 1984, raw_dir=str(tmp_path / "raw"), tabulated_dir=str(tmp_path / "tabulated"))
