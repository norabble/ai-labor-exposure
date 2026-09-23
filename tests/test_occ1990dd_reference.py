"""Tests for occ1990dd_reference.py — the committed Dorn, Census and group reference seeds."""

import pandas as pd
import pytest

from occ1990dd_reference import (
    DORN_VINTAGES,
    OUTSIDE_GROUP_OCC1990DD,
    expand_soc_reference,
    known_occ1990dd_codes,
    load_census_2002_to_2010,
    load_census_2018_to_2010,
    load_census_code_list,
    load_dorn_crosswalk,
    load_occ1990dd_groups,
    soc_reference_prefix,
    uncovered_codes,
)


class TestSocReferencePrefix:
    @pytest.mark.parametrize(
        ("reference", "expected_prefix"),
        [
            ("11-1011", "11-1011"),  # detailed: itself
            ("11-2020", "11-202"),  # broad group: trailing zero dropped
            ("11-2000", "11-2"),  # minor group
            ("15-113X", "15-113"),  # wildcard
            ("25-90XX", "25-90"),  # wildcard whose kept digits end in zero — the zero is real
            ("none", None),
            (" 13-11xx ", "13-11"),  # whitespace and lower-case x tolerated
        ],
    )
    def test_prefix_rules(self, reference, expected_prefix):
        assert soc_reference_prefix(reference) == expected_prefix


class TestExpandSocReference:
    vocabulary = {"11-1011", "11-2021", "11-2022", "11-2031", "25-9021", "25-9031", "25-1011"}

    def test_detailed_code_expands_to_itself(self):
        assert expand_soc_reference("11-1011", self.vocabulary) == {"11-1011"}

    def test_broad_group_expands_to_its_detailed_members(self):
        assert expand_soc_reference("11-2020", self.vocabulary) == {"11-2021", "11-2022"}

    def test_wildcard_keeps_a_zero_before_the_x(self):
        assert expand_soc_reference("25-90XX", self.vocabulary) == {"25-9021", "25-9031"}

    def test_none_expands_to_nothing(self):
        assert expand_soc_reference("none", self.vocabulary) == set()


class TestDornCrosswalks:
    @pytest.mark.parametrize(("vintage", "expected_rows"), [("1980", 504), ("1990", 502), ("2000", 471), ("2005", 471), ("2010", 489)])
    def test_row_counts_match_the_published_files(self, vintage, expected_rows):
        assert len(load_dorn_crosswalk(vintage)) == expected_rows

    @pytest.mark.parametrize("vintage", DORN_VINTAGES)
    def test_every_source_code_maps_to_exactly_one_occ1990dd(self, vintage):
        crosswalk_df = load_dorn_crosswalk(vintage)
        assert not crosswalk_df["source_code"].duplicated().any()

    def test_known_code_universe_is_333_excluding_unclassified(self):
        codes = known_occ1990dd_codes()
        assert len(codes) == 333
        assert 999 not in codes


class TestCensusCodeLists:
    @pytest.mark.parametrize(("vintage", "expected_codes"), [("2002", 510), ("2010", 540), ("2018", 570)])
    def test_code_counts(self, vintage, expected_codes):
        code_list_df = load_census_code_list(vintage)
        assert len(code_list_df) == expected_codes
        assert not code_list_df["census_code"].duplicated().any()

    def test_chief_executives_is_code_10_in_every_vintage(self):
        for vintage in ("2002", "2010", "2018"):
            code_list_df = load_census_code_list(vintage)
            assert code_list_df.loc[code_list_df["census_code"] == 10, "soc_reference"].iloc[0] == "11-1011"

    def test_2018_to_2010_covers_every_2018_code_once(self):
        crosswalk_df = load_census_2018_to_2010()
        codes_2018 = set(load_census_code_list("2018")["census_code"])
        assert set(crosswalk_df["census_2018"]) == codes_2018
        assert not crosswalk_df["census_2018"].duplicated().any()


class TestGroups:
    def test_twenty_five_groups(self):
        assert load_occ1990dd_groups()["dorn_group"].nunique() == 25

    def test_every_known_code_but_905_and_991_is_in_exactly_one_group(self):
        groups_df = load_occ1990dd_groups()
        assert not groups_df["occ1990dd"].duplicated().any()
        assert set(uncovered_codes(known_occ1990dd_codes(), groups_df)) == set(OUTSIDE_GROUP_OCC1990DD)

    def test_uncovered_codes_reports_codes_outside_every_group(self):
        groups_df = pd.DataFrame({"occ1990dd": [4, 22], "dorn_group": ["exec", "exec"]})
        assert uncovered_codes({4, 22, 905}, groups_df) == [905]


def test_2002_to_2010_covers_nearly_every_2002_code():
    crosswalk_df = load_census_2002_to_2010()
    codes_2002 = set(load_census_code_list("2002")["census_code"])
    # Five 2002 codes (0210, 3130, 4550, 8230, 8240) have no 2010 successor in the Census sheet.
    assert len(codes_2002 - set(crosswalk_df["census_2002"])) == 5
