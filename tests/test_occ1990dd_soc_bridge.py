"""Tests for occ1990dd_soc_bridge.py — the chain from occ1990dd to SOC 2018, its weights and its scores."""

import pandas as pd
import pytest

from occ1990dd_soc_bridge import (
    SocTables,
    build_bridge_weights,
    build_chain_edges,
    census_code_members,
    equal_division_weights,
    load_anchor_employment,
    load_soc_tables,
    to_soc_2018,
)

FAKE_TABLES = SocTables(
    vocabularies={
        "soc2000": {"11-2011", "15-1021"},
        "soc2010": {"11-2011", "11-2021", "11-2022", "15-1131"},
        "soc2018": {"11-2011", "11-2021", "11-2022", "15-1251"},
    },
    soc2000_to_soc2010={"11-2011": {"11-2011"}, "15-1021": {"15-1131"}},
    soc2010_to_soc2018={"11-2011": {"11-2011"}, "11-2021": {"11-2021"}, "11-2022": {"11-2022"}, "15-1131": {"15-1251"}},
)


class TestToSoc2018:
    def test_soc_2018_codes_pass_through(self):
        assert to_soc_2018({"11-2021"}, "soc2018", FAKE_TABLES) == {"11-2021"}

    def test_soc_2000_goes_through_2010(self):
        assert to_soc_2018({"15-1021"}, "soc2000", FAKE_TABLES) == {"15-1251"}

    def test_empty_input_gives_empty_output(self):
        assert to_soc_2018(set(), "soc2010", FAKE_TABLES) == set()

    def test_unknown_generation_raises(self):
        with pytest.raises(ValueError):
            to_soc_2018({"11-2011"}, "soc1990", FAKE_TABLES)


class TestCensusCodeMembers:
    def test_a_broad_reference_expands_then_maps_to_2018(self):
        code_list_df = pd.DataFrame({"census_code": [50], "census_title": ["Marketing and sales managers"], "soc_reference": ["11-2020"]})
        members_df = census_code_members(code_list_df, "2010", FAKE_TABLES)
        assert set(members_df["soc_2018_code"]) == {"11-2021", "11-2022"}

    def test_a_none_reference_contributes_no_rows(self):
        code_list_df = pd.DataFrame({"census_code": [9840], "census_title": ["Armed forces"], "soc_reference": ["none"]})
        assert census_code_members(code_list_df, "2010", FAKE_TABLES).empty


class TestBuildChainEdges:
    def test_joins_dorn_codes_to_census_members_and_drops_unclassified(self):
        dorn_2010_df = pd.DataFrame({"source_code": [50, 9999], "occ1990dd": [13, 999]})
        members_df = pd.DataFrame({"census_code": [50, 50, 9999], "soc_2018_code": ["11-2021", "11-2022", "55-1011"]})
        chain_df = build_chain_edges(dorn_2010_df, members_df)
        assert set(chain_df["occ1990dd"]) == {13}
        assert set(chain_df["soc_2018_code"]) == {"11-2021", "11-2022"}


class TestEqualDivisionWeights:
    def test_weights_sum_to_one_within_each_owner(self):
        edges_df = pd.DataFrame({"occ1990dd": [1, 1, 2], "soc_2018_code": ["A", "B", "C"]})
        weights_df = equal_division_weights(edges_df, "occ1990dd", pd.Series({"A": 30.0, "B": 10.0, "C": 5.0}))
        assert weights_df.groupby("occ1990dd")["weight"].sum().tolist() == pytest.approx([1.0, 1.0])
        assert weights_df.set_index("soc_2018_code").loc["A", "weight"] == pytest.approx(0.75)

    def test_a_code_shared_by_two_owners_gives_each_half_its_employment(self):
        # Unit 1 = {A (shared), B}; unit 2 = {A (shared)}. A's 40 splits 20/20, so unit 1 is A 20 : B 20.
        edges_df = pd.DataFrame({"occ1990dd": [1, 1, 2], "soc_2018_code": ["A", "B", "A"]})
        weights_df = equal_division_weights(edges_df, "occ1990dd", pd.Series({"A": 40.0, "B": 20.0}))
        unit_one = weights_df[weights_df["occ1990dd"] == 1].set_index("soc_2018_code")["weight"]
        assert unit_one["A"] == pytest.approx(0.5)
        assert unit_one["B"] == pytest.approx(0.5)

    def test_an_owner_with_no_oews_employment_weights_members_equally(self):
        edges_df = pd.DataFrame({"occ1990dd": [7, 7, 7], "soc_2018_code": ["X", "Y", "Z"]})
        weights_df = equal_division_weights(edges_df, "occ1990dd", pd.Series(dtype=float))
        assert weights_df["weight"].tolist() == pytest.approx([1 / 3, 1 / 3, 1 / 3])


class TestAnchorEmployment:
    def test_reads_2022_employment_keyed_by_soc_code_and_drops_non_numeric(self, tmp_path):
        trends_path = tmp_path / "bls_trends.csv"
        pd.DataFrame({"OCC_CODE": ["11-1011", "11-1021", "11-1031"], "TOT_EMP_2022": [100, "**", 50]}).to_csv(trends_path, index=False)
        anchor_employment = load_anchor_employment(str(trends_path))
        assert anchor_employment.to_dict() == {"11-1011": 100.0, "11-1031": 50.0}


@pytest.fixture(scope="module")
def bridge_weights_df():
    """The real chain from the committed seeds, with uniform employment so bls_trends.csv is not needed."""
    soc_tables = load_soc_tables()
    uniform_employment = pd.Series(1.0, index=sorted(soc_tables.vocabularies["soc2018"]))
    return build_bridge_weights(uniform_employment, soc_tables)


class TestRealChain:
    def test_every_unit_weight_sums_to_one(self, bridge_weights_df):
        assert bridge_weights_df.groupby("occ1990dd")["weight"].sum().to_numpy() == pytest.approx(1.0)

    def test_the_chain_reaches_nearly_every_occ1990dd_code(self, bridge_weights_df):
        # 328 of the 333 known codes on 2026-09-23; a few exist only in pre-2010 vintages.
        assert bridge_weights_df["occ1990dd"].nunique() >= 320

    def test_chief_executives_reach_soc_chief_executives(self, bridge_weights_df):
        # occ1990dd 4 is chief executives and general administrators (Dorn).
        assert "11-1011" in set(bridge_weights_df.loc[bridge_weights_df["occ1990dd"] == 4, "soc_2018_code"])
