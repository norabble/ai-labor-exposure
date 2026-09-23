"""Tests for dws_detailed_panel.py — the detailed Displaced Worker Supplement build, on synthetic records."""

import pandas as pd
import pytest

import dws_detailed_panel
import ipums_cps_variables as ipums_variables
from dws_detailed_panel import (
    attach_lost_job_occ1990dd,
    gate_g3,
    gate_g6d,
    is_long_tenured,
    lost_job_edges,
    lost_job_raw_vintage,
    select_displaced,
    tabulate_survey,
)


@pytest.fixture(autouse=True)
def pinned_dws_variables(monkeypatch):
    monkeypatch.setattr(ipums_variables, "DWS_DISPLACED_REASON_CODES", (1, 2, 3))
    monkeypatch.setattr(ipums_variables, "DWS_LOST_JOB_OCC1990_VARIABLE", None)


def displaced_records(rows):
    defaults = {
        "YEAR": 2024,
        "SERIAL": 1,
        "AGE": 45,
        ipums_variables.DWS_WEIGHT_VARIABLE: 2000.0,
        ipums_variables.DWS_REASON_VARIABLE: 1,
        ipums_variables.DWS_TENURE_VARIABLE: 5.0,
        ipums_variables.DWS_LOST_JOB_OCC_VARIABLE: 4700,
    }
    return pd.DataFrame([{**defaults, **row} for row in rows])


class TestVintages:
    @pytest.mark.parametrize(
        ("survey_year", "vintage"),
        [(1984, "1980"), (1992, "1980"), (1994, "1990"), (2002, "1990"), (2004, "2002"), (2012, "2010"), (2020, "2018")],
    )
    def test_survey_year_to_raw_code_vintage(self, survey_year, vintage):
        assert lost_job_raw_vintage(survey_year) == vintage

    @pytest.mark.parametrize("survey_year", [1986, 1996, 2006, 2014, 2024])
    def test_shares_never_exceed_one_per_raw_code(self, survey_year):
        edges_df = lost_job_edges(survey_year)
        assert (edges_df.groupby("raw_code")["share"].sum() <= 1.0 + 1e-9).all()
        assert not edges_df.empty


class TestSelection:
    def test_keeps_adults_displaced_for_a_bls_reason_with_positive_weight(self):
        person_df = displaced_records(
            [{}, {"AGE": 19}, {ipums_variables.DWS_REASON_VARIABLE: 5}, {ipums_variables.DWS_WEIGHT_VARIABLE: 0.0}]
        )
        assert len(select_displaced(person_df)) == 1

    def test_long_tenure_is_three_or_more_valid_years(self):
        tenure = ipums_variables.DWS_TENURE_VARIABLE
        person_df = displaced_records([{tenure: 2.9}, {tenure: 3.0}, {tenure: 99.0}])
        assert is_long_tenured(person_df).tolist() == [False, True, False]


class TestMapping:
    def test_a_split_raw_code_divides_its_weight(self, monkeypatch):
        monkeypatch.setattr(
            dws_detailed_panel,
            "lost_job_edges",
            lambda survey_year: pd.DataFrame({"raw_code": [4700, 4700], "occ1990dd": [243, 274], "share": [0.5, 0.5]}),
        )
        mapped_df, unmapped_share = attach_lost_job_occ1990dd(displaced_records([{}]), 2024)
        assert mapped_df["allocated_weight"].tolist() == [1000.0, 1000.0]
        assert unmapped_share == pytest.approx(0.0)

    def test_an_unmapped_raw_code_is_reported_for_g6d(self, monkeypatch):
        monkeypatch.setattr(
            dws_detailed_panel, "lost_job_edges", lambda survey_year: pd.DataFrame({"raw_code": [4700], "occ1990dd": [274], "share": [1.0]})
        )
        _, unmapped_share = attach_lost_job_occ1990dd(displaced_records([{}, {ipums_variables.DWS_LOST_JOB_OCC_VARIABLE: 1}]), 2024)
        assert unmapped_share == pytest.approx(0.5)


class TestTabulateSurvey:
    def test_counts_per_group_and_tenure_class(self):
        mapped_df = pd.DataFrame(
            {
                "occ1990dd": [274, 274, 4],
                "allocated_weight": [2000.0, 2000.0, 1000.0],
                "SERIAL": [1, 2, 3],
                ipums_variables.DWS_TENURE_VARIABLE: [5.0, 1.0, 10.0],
            }
        )
        groups_df = pd.DataFrame({"occ1990dd": [274, 4], "dorn_group": ["retsales", "exec"]})
        panel_df = tabulate_survey(mapped_df, 2024, groups_df).set_index(["dorn_group", "tenure_class"])
        assert panel_df.loc[("retsales", "all_tenures"), "displaced_thousands"] == pytest.approx(4.0)
        assert panel_df.loc[("retsales", "long_tenured"), "displaced_thousands"] == pytest.approx(2.0)
        assert panel_df.loc[("retsales", "all_tenures"), "unweighted_count"] == 2


class TestGates:
    def test_g3_allows_published_rounding_on_small_groups(self):
        direct_df = pd.DataFrame(
            {
                "survey_year": [2024, 2024],
                "cps_group": ["sales and related occupations", "farming, fishing, and forestry occupations"],
                "displaced_thousands": [1010.0, 4.4],
            }
        )
        published_df = pd.DataFrame(
            {
                "survey_year": [2024, 2024],
                "source_table": ["table_5_occupation"] * 2,
                "measurement_basis": ["count_thousands"] * 2,
                "group_name": ["Sales and related occupations", "Farming, fishing, and forestry occupations"],
                "displaced_thousands": [1000.0, 4.0],
            }
        )
        gate_df = gate_g3(direct_df, published_df)
        # 1% off on the large group passes; 10% off on the 4k group passes only because 0.4k < 0.5k rounding.
        assert gate_df["passed"].tolist() == [True, True]

    def test_g3_fails_a_real_gap(self):
        direct_df = pd.DataFrame({"survey_year": [2024], "cps_group": ["sales and related occupations"], "displaced_thousands": [1100.0]})
        published_df = pd.DataFrame(
            {
                "survey_year": [2024],
                "source_table": ["table_5_occupation"],
                "measurement_basis": ["count_thousands"],
                "group_name": ["Sales and related occupations"],
                "displaced_thousands": [1000.0],
            }
        )
        assert gate_g3(direct_df, published_df)["passed"].tolist() == [False]

    def test_g6d_gates_every_survey_at_one_percent(self):
        assert gate_g6d(pd.Series({2022: 0.002, 2024: 0.05}))["passed"].tolist() == [True, False]


def test_the_build_refuses_until_task_2_has_verified_ipums(monkeypatch):
    monkeypatch.setattr(ipums_variables, "VERIFICATION_STATUS", "unverified")
    with pytest.raises(RuntimeError, match="Task 2"):
        dws_detailed_panel.build_rebuilt_panel([2024])


class TestHarmonizedRoute:
    """Tests for the harmonized DWOCC1990 route (when DWS_LOST_JOB_OCC1990_VARIABLE is set)."""

    @pytest.fixture
    def harmonized_fixture(self, monkeypatch):
        """Override the autouse fixture to enable the harmonized route."""
        monkeypatch.setattr(ipums_variables, "DWS_DISPLACED_REASON_CODES", (1, 2, 3))
        monkeypatch.setattr(ipums_variables, "DWS_LOST_JOB_OCC1990_VARIABLE", "DWOCC1990")

    def harmonized_records(self, rows):
        defaults = {
            "YEAR": 2024,
            "SERIAL": 1,
            "AGE": 45,
            ipums_variables.DWS_WEIGHT_VARIABLE: 2000.0,
            ipums_variables.DWS_REASON_VARIABLE: 1,
            ipums_variables.DWS_TENURE_VARIABLE: 5.0,
            "DWOCC1990": 4,  # Known code from spine
            ipums_variables.DWS_LOST_JOB_OCC_VARIABLE: 9999,  # Ignored in harmonized route
        }
        return pd.DataFrame([{**defaults, **row} for row in rows])

    def test_known_dwocc1990_code_maps_through_spine_with_full_weight(self, harmonized_fixture):
        """A record with a known 1990-basis code maps to its spine target with share 1 and unmapped share 0."""
        # Code 4 maps to occ1990dd 4 in the spine
        mapped_df, unmapped_share = attach_lost_job_occ1990dd(self.harmonized_records([{}]), 2024)
        assert len(mapped_df) == 1
        assert mapped_df["occ1990dd"].iloc[0] == 4
        assert mapped_df["allocated_weight"].iloc[0] == 2000.0  # Full weight, no splitting
        assert unmapped_share == pytest.approx(0.0)

    def test_unknown_dwocc1990_code_is_reported_unmapped(self, harmonized_fixture):
        """A DWOCC1990 value absent from the spine is reported in unmapped share."""
        # Code 99999 is not in the spine
        mapped_df, unmapped_share = attach_lost_job_occ1990dd(self.harmonized_records([{"DWOCC1990": 99999}]), 2024)
        assert len(mapped_df) == 0
        assert unmapped_share == pytest.approx(1.0)

    def test_raw_dwocc_column_is_ignored_in_harmonized_route(self, harmonized_fixture):
        """The raw DWOCC column value is ignored when DWOCC1990 is present."""
        # DWOCC1990=4 (valid), DWOCC=9999 (invalid if used)
        mapped_df, unmapped_share = attach_lost_job_occ1990dd(self.harmonized_records([{}]), 2024)
        assert len(mapped_df) == 1
        assert mapped_df["occ1990dd"].iloc[0] == 4  # Proves it used DWOCC1990, not DWOCC
        assert unmapped_share == pytest.approx(0.0)

    def test_mixed_known_and_unknown_dwocc1990_codes_split_unmapped(self, harmonized_fixture):
        """Multiple records with a mix of known and unknown codes report split unmapped share."""
        records = self.harmonized_records([{"DWOCC1990": 4}, {"DWOCC1990": 99999}])  # 50% known, 50% unknown
        mapped_df, unmapped_share = attach_lost_job_occ1990dd(records, 2024)
        assert len(mapped_df) == 1  # Only the known code is mapped
        assert unmapped_share == pytest.approx(0.5)  # Half the weight is unmapped
