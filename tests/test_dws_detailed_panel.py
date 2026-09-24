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
        ipums_variables.DWS_LOST_JOB_CLASS_VARIABLE: 2,  # wage/salary, private for-profit — not self-employed
        ipums_variables.DWS_RECALL_VARIABLE: 1,  # No — recall not expected
        ipums_variables.DWS_LOST_WORK_VARIABLE: 1,  # last year — inside every survey's reference window
    }
    return pd.DataFrame([{**defaults, **row} for row in rows])


class TestVintages:
    @pytest.mark.parametrize(
        ("survey_year", "vintage"),
        [(1984, "1980"), (1990, "1980"), (1992, "1990"), (1994, "1990"), (2002, "1990"), (2004, "2002"), (2012, "2010"), (2020, "2018")],
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
        assert len(select_displaced(person_df, 2024)) == 1

    def test_long_tenure_is_three_or_more_valid_years(self):
        tenure = ipums_variables.DWS_TENURE_VARIABLE
        person_df = displaced_records([{tenure: 2.9}, {tenure: 3.0}, {tenure: 99.0}])
        assert is_long_tenured(person_df).tolist() == [False, True, False]

    def test_excludes_self_employed_lost_job(self):
        class_variable = ipums_variables.DWS_LOST_JOB_CLASS_VARIABLE
        person_df = displaced_records(
            [
                {class_variable: ipums_variables.DWS_SELF_EMPLOYED_CLASS_CODES[0]},
                {class_variable: 2},  # wage/salary, private for-profit
            ]
        )
        result_df = select_displaced(person_df, 2024)
        assert len(result_df) == 1
        assert result_df[class_variable].iloc[0] == 2

    def test_keeps_missing_or_niu_lost_job_class_rather_than_guessing(self):
        class_variable = ipums_variables.DWS_LOST_JOB_CLASS_VARIABLE
        person_df = displaced_records([{class_variable: code} for code in ipums_variables.DWS_MISSING_CLASS_CODES])
        assert len(select_displaced(person_df, 2024)) == len(ipums_variables.DWS_MISSING_CLASS_CODES)

    def test_missing_lost_job_class_count_counts_niu_and_nonresponse_codes(self):
        class_variable = ipums_variables.DWS_LOST_JOB_CLASS_VARIABLE
        displaced_df = displaced_records([{class_variable: 2}, {class_variable: 99}, {class_variable: 97}])
        assert dws_detailed_panel.missing_lost_job_class_count(displaced_df) == 2


class TestRecallAndWindowSelection:
    """g3-diagnosis2-report.md: BLS's published Table 5/8 population excludes layoffs expecting
    recall within six months and lost jobs outside the survey's reference window."""

    def test_recall_expected_is_excluded(self):
        recall_variable = ipums_variables.DWS_RECALL_VARIABLE
        person_df = displaced_records([{recall_variable: 1}, {recall_variable: 2}])
        result_df = select_displaced(person_df, 2024)
        assert len(result_df) == 1
        assert result_df[recall_variable].iloc[0] == 1

    @pytest.mark.parametrize("recall_code", [96, 97, 98, 99])
    def test_niu_and_nonresponse_recall_codes_are_kept(self, recall_code):
        recall_variable = ipums_variables.DWS_RECALL_VARIABLE
        person_df = displaced_records([{recall_variable: recall_code}])
        assert len(select_displaced(person_df, 2024)) == 1

    def test_out_of_window_lost_work_year_is_excluded(self):
        lost_work_variable = ipums_variables.DWS_LOST_WORK_VARIABLE
        # 2024 is a 1994+ survey: window is codes 1-3. 0 ("this year"), 4, 5, and 99 (NIU) all fall
        # outside it.
        person_df = displaced_records([{lost_work_variable: code} for code in (0, 1, 2, 3, 4, 5, 99)])
        result_df = select_displaced(person_df, 2024)
        assert sorted(result_df[lost_work_variable].tolist()) == [1, 2, 3]

    def test_pre_1994_window_is_five_years(self):
        lost_work_variable = ipums_variables.DWS_LOST_WORK_VARIABLE
        person_df = displaced_records([{lost_work_variable: code} for code in (0, 1, 2, 3, 4, 5, 99)])
        result_df = select_displaced(person_df, 1990)
        assert sorted(result_df[lost_work_variable].tolist()) == [1, 2, 3, 4, 5]

    def test_pre_1994_survey_with_no_dwrecall_column_applies_no_recall_filter_and_does_not_crash(self):
        person_df = displaced_records([{}]).drop(columns=[ipums_variables.DWS_RECALL_VARIABLE])
        result_df = select_displaced(person_df, 1990)
        assert len(result_df) == 1


class TestRecallRuleImpact:
    def test_measures_the_share_the_recall_rule_removes(self):
        recall_variable = ipums_variables.DWS_RECALL_VARIABLE
        person_df = displaced_records(
            [
                {recall_variable: 1, ipums_variables.DWS_WEIGHT_VARIABLE: 3000.0},
                {recall_variable: 2, ipums_variables.DWS_WEIGHT_VARIABLE: 1000.0},
            ]
        )
        # Recall-included total 4000, recall-excluded total 3000 -> 25% removed.
        assert dws_detailed_panel.measure_recall_rule_impact(person_df, 1994) == pytest.approx(0.25)

    def test_nan_when_the_recall_included_total_is_zero(self):
        person_df = displaced_records([{"AGE": 10}])  # excluded on age, so nothing in the denominator
        assert pd.isna(dws_detailed_panel.measure_recall_rule_impact(person_df, 1994))


class TestMapping:
    def test_a_split_raw_code_divides_its_weight(self, monkeypatch):
        monkeypatch.setattr(
            dws_detailed_panel,
            "lost_job_edges",
            lambda survey_year: pd.DataFrame({"raw_code": [4700, 4700], "occ1990dd": [243, 274], "share": [0.5, 0.5]}),
        )
        mapped_df, unmapped_share, nonresponse_share = attach_lost_job_occ1990dd(displaced_records([{}]), 2024)
        assert mapped_df["allocated_weight"].tolist() == [1000.0, 1000.0]
        assert unmapped_share == pytest.approx(0.0)
        assert nonresponse_share == pytest.approx(0.0)

    def test_an_unmapped_raw_code_is_reported_for_g6d(self, monkeypatch):
        monkeypatch.setattr(
            dws_detailed_panel, "lost_job_edges", lambda survey_year: pd.DataFrame({"raw_code": [4700], "occ1990dd": [274], "share": [1.0]})
        )
        _, unmapped_share, _ = attach_lost_job_occ1990dd(displaced_records([{}, {ipums_variables.DWS_LOST_JOB_OCC_VARIABLE: 1}]), 2024)
        assert unmapped_share == pytest.approx(0.5)

    def test_zero_total_weight_is_a_failure_not_a_vacuous_pass(self, monkeypatch):
        """A survey with no displaced weight at all (e.g. a wrong sample month) must fail G6D, not report 0.0 unmapped."""
        monkeypatch.setattr(
            dws_detailed_panel, "lost_job_edges", lambda survey_year: pd.DataFrame({"raw_code": [4700], "occ1990dd": [274], "share": [1.0]})
        )
        empty_df = displaced_records([{}]).iloc[0:0]
        _, unmapped_share, nonresponse_share = attach_lost_job_occ1990dd(empty_df, 2024)
        assert unmapped_share == pytest.approx(1.0)
        assert pd.isna(nonresponse_share)

    def test_nonresponse_weight_is_excluded_from_the_crosswalk_share_and_reported_separately(self, monkeypatch):
        """G6D redefinition: a record whose raw lost-job code is the raw route's own nonresponse
        sentinel (0, not 999 — see RAW_LOST_JOB_OCC_NONRESPONSE_CODE) must not count as crosswalk
        loss, and its weight share must come back as `nonresponse_share` instead."""
        monkeypatch.setattr(
            dws_detailed_panel, "lost_job_edges", lambda survey_year: pd.DataFrame({"raw_code": [4700], "occ1990dd": [274], "share": [1.0]})
        )
        records = displaced_records([{}, {ipums_variables.DWS_LOST_JOB_OCC_VARIABLE: dws_detailed_panel.RAW_LOST_JOB_OCC_NONRESPONSE_CODE}])
        mapped_df, unmapped_share, nonresponse_share = attach_lost_job_occ1990dd(records, 2024)
        assert len(mapped_df) == 1
        assert unmapped_share == pytest.approx(0.0)
        assert nonresponse_share == pytest.approx(0.5)

    def test_raw_route_999_is_not_treated_as_nonresponse(self, monkeypatch):
        """DWOCC's own range never reaches 999 (verified 0-905 in 1984), so unlike the harmonized
        route, a raw code of 999 must be treated as an ordinary (unmapped) code, not nonresponse."""
        monkeypatch.setattr(
            dws_detailed_panel, "lost_job_edges", lambda survey_year: pd.DataFrame({"raw_code": [4700], "occ1990dd": [274], "share": [1.0]})
        )
        records = displaced_records([{}, {ipums_variables.DWS_LOST_JOB_OCC_VARIABLE: 999}])
        mapped_df, unmapped_share, nonresponse_share = attach_lost_job_occ1990dd(records, 2024)
        assert len(mapped_df) == 1
        assert nonresponse_share == pytest.approx(0.0)
        assert unmapped_share == pytest.approx(0.5)  # the 999 record counts as crosswalk loss, not nonresponse

    def test_all_reported_weight_zero_fails_g6d_closed(self, monkeypatch):
        """Minor 1: every record nonresponding (nonzero total weight, zero reported weight) must
        fail G6D closed rather than reporting a vacuous 0.0 unmapped share."""
        monkeypatch.setattr(
            dws_detailed_panel, "lost_job_edges", lambda survey_year: pd.DataFrame({"raw_code": [4700], "occ1990dd": [274], "share": [1.0]})
        )
        records = displaced_records([{ipums_variables.DWS_LOST_JOB_OCC_VARIABLE: dws_detailed_panel.RAW_LOST_JOB_OCC_NONRESPONSE_CODE}])
        mapped_df, unmapped_share, nonresponse_share = attach_lost_job_occ1990dd(records, 2024)
        assert len(mapped_df) == 0
        assert unmapped_share == pytest.approx(1.0)
        assert nonresponse_share == pytest.approx(1.0)


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

    def test_g6d_gates_crosswalk_loss_at_one_percent_and_reports_nonresponse_ungated(self):
        gates_df = gate_g6d(pd.Series({2022: 0.002, 2024: 0.05}), pd.Series({2022: 0.03, 2024: 0.04}))
        crosswalk_df = gates_df[gates_df["gate"] == "G6D"]
        assert crosswalk_df["passed"].tolist() == [True, False]
        assert crosswalk_df["gated"].tolist() == [True, True]
        nonresponse_df = gates_df[gates_df["gate"] == "G6D-nonresponse"]
        assert nonresponse_df["observed"].tolist() == [0.03, 0.04]
        assert not nonresponse_df["gated"].any()
        assert nonresponse_df["passed"].isna().all()

    def test_all_gates_pass_ignores_the_ungated_nonresponse_rows(self):
        """A nonresponse share far above the 1% G6D threshold must never fail all_gates_pass —
        it is reported information, not a gated check."""
        gates_df = gate_g6d(pd.Series({2024: 0.002}), pd.Series({2024: 0.30}))
        assert dws_detailed_panel.all_gates_pass(gates_df, ("G6D",))


def test_nonresponse_share_by_survey_reads_back_the_gate_record():
    gates_df = gate_g6d(pd.Series({2022: 0.002, 2024: 0.05}), pd.Series({2022: 0.03, 2024: 0.04}))
    result = dws_detailed_panel.nonresponse_share_by_survey(gates_df)
    assert result.loc[2022] == pytest.approx(0.03)
    assert result.loc[2024] == pytest.approx(0.04)


class TestGateRecordRoundTrip:
    """Minor 2: the ungated "G6D-nonresponse" rows (gated=False, passed=NaN) must survive a CSV
    round trip without disturbing promote_rebuilt's own gated-row logic either way."""

    def _write_and_reread(self, gates_df: pd.DataFrame, tmp_path) -> pd.DataFrame:
        gates_path = tmp_path / "gates.csv"
        gates_df.to_csv(gates_path, index=False)
        return pd.read_csv(gates_path), str(gates_path)

    def test_round_tripped_nonresponse_rows_still_let_all_gates_pass_and_promote_succeed(self, tmp_path):
        gates_df = pd.concat(
            [
                gate_g3(
                    pd.DataFrame({"survey_year": [2024], "cps_group": ["exec"], "displaced_thousands": [100.0]}),
                    pd.DataFrame(
                        {
                            "survey_year": [2024],
                            "source_table": ["table_5_occupation"],
                            "measurement_basis": ["count_thousands"],
                            "group_name": ["Exec"],
                            "displaced_thousands": [100.0],
                        }
                    ),
                ),
                gate_g6d(pd.Series({2024: 0.002}), pd.Series({2024: 0.30})),
            ],
            ignore_index=True,
        )
        reread_df, gates_path = self._write_and_reread(gates_df, tmp_path)
        assert dws_detailed_panel.all_gates_pass(reread_df, ("G3", "G6D"))

        source_path = tmp_path / "source.csv"
        destination_path = tmp_path / "destination.csv"
        pd.DataFrame({"placeholder": [1]}).to_csv(source_path, index=False)
        dws_detailed_panel.promote_rebuilt({str(source_path): str(destination_path)}, gates_path, ("G3", "G6D"))
        assert destination_path.exists()

    def test_a_failing_gated_row_still_blocks_after_the_round_trip(self, tmp_path):
        gates_df = gate_g6d(pd.Series({2024: 0.05}), pd.Series({2024: 0.30}))
        reread_df, gates_path = self._write_and_reread(gates_df, tmp_path)
        assert not dws_detailed_panel.all_gates_pass(reread_df, ("G6D",))

        source_path = tmp_path / "source.csv"
        destination_path = tmp_path / "destination.csv"
        pd.DataFrame({"placeholder": [1]}).to_csv(source_path, index=False)
        with pytest.raises(Exception):
            dws_detailed_panel.promote_rebuilt({str(source_path): str(destination_path)}, gates_path, ("G6D",))
        assert not destination_path.exists()


def test_the_build_refuses_until_task_2_has_verified_ipums(monkeypatch):
    monkeypatch.setattr(ipums_variables, "VERIFICATION_STATUS", "unverified")
    with pytest.raises(RuntimeError, match="Task 2"):
        dws_detailed_panel.build_rebuilt_panel([2024])


def test_the_build_fails_g6d_when_a_downloaded_survey_has_zero_displaced_records(monkeypatch, tmp_path):
    """A survey that IS downloaded but yields no displaced records (e.g. the wrong sample month
    resolved) must fail closed through G6D rather than silently contributing nothing."""
    monkeypatch.setattr(ipums_variables, "VERIFICATION_STATUS", "verified")
    monkeypatch.setattr(dws_detailed_panel, "load_occ1990dd_groups", lambda: pd.DataFrame({"occ1990dd": [274], "dorn_group": ["retsales"]}))
    empty_df = displaced_records([{}]).iloc[0:0]
    monkeypatch.setattr(dws_detailed_panel, "read_survey_persons", lambda survey_year, raw_dir: empty_df)
    published_path = tmp_path / "published_dws_panel.csv"
    pd.DataFrame(columns=["survey_year", "source_table", "measurement_basis", "group_name", "displaced_thousands"]).to_csv(
        published_path, index=False
    )
    monkeypatch.setattr(dws_detailed_panel, "PUBLISHED_DWS_PANEL_PATH", str(published_path))

    gates_df = dws_detailed_panel.build_rebuilt_panel(
        [2024], raw_dir=str(tmp_path / "raw"), panel_path=str(tmp_path / "panel.csv"), gates_path=str(tmp_path / "gates.csv")
    )
    g6d_df = gates_df[gates_df["gate"] == "G6D"]
    assert not g6d_df.empty
    assert g6d_df["observed"].iloc[0] == pytest.approx(1.0)
    assert not g6d_df["passed"].iloc[0]
    assert not dws_detailed_panel.all_gates_pass(gates_df, dws_detailed_panel.REQUIRED_GATES)


def test_the_build_raises_a_clear_error_when_no_survey_is_downloaded(monkeypatch, tmp_path):
    monkeypatch.setattr(ipums_variables, "VERIFICATION_STATUS", "verified")
    monkeypatch.setattr(dws_detailed_panel, "read_survey_persons", lambda survey_year, raw_dir: None)
    with pytest.raises(RuntimeError, match="[Nn]o.*download"):
        dws_detailed_panel.build_rebuilt_panel([2024], raw_dir=str(tmp_path / "raw"))


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
        mapped_df, unmapped_share, nonresponse_share = attach_lost_job_occ1990dd(self.harmonized_records([{}]), 2024)
        assert len(mapped_df) == 1
        assert mapped_df["occ1990dd"].iloc[0] == 4
        assert mapped_df["allocated_weight"].iloc[0] == 2000.0  # Full weight, no splitting
        assert unmapped_share == pytest.approx(0.0)
        assert nonresponse_share == pytest.approx(0.0)

    def test_unknown_dwocc1990_code_is_reported_unmapped(self, harmonized_fixture):
        """A DWOCC1990 value absent from the spine is reported in unmapped share."""
        # Code 99999 is not in the spine
        mapped_df, unmapped_share, _ = attach_lost_job_occ1990dd(self.harmonized_records([{"DWOCC1990": 99999}]), 2024)
        assert len(mapped_df) == 0
        assert unmapped_share == pytest.approx(1.0)

    def test_raw_dwocc_column_is_ignored_in_harmonized_route(self, harmonized_fixture):
        """The raw DWOCC column value is ignored when DWOCC1990 is present."""
        # DWOCC1990=4 (valid), DWOCC=9999 (invalid if used)
        mapped_df, unmapped_share, _ = attach_lost_job_occ1990dd(self.harmonized_records([{}]), 2024)
        assert len(mapped_df) == 1
        assert mapped_df["occ1990dd"].iloc[0] == 4  # Proves it used DWOCC1990, not DWOCC
        assert unmapped_share == pytest.approx(0.0)

    def test_mixed_known_and_unknown_dwocc1990_codes_split_unmapped(self, harmonized_fixture):
        """Multiple records with a mix of known and unknown codes report split unmapped share."""
        records = self.harmonized_records([{"DWOCC1990": 4}, {"DWOCC1990": 99999}])  # 50% known, 50% unknown
        mapped_df, unmapped_share, _ = attach_lost_job_occ1990dd(records, 2024)
        assert len(mapped_df) == 1  # Only the known code is mapped
        assert unmapped_share == pytest.approx(0.5)  # Half the weight is unmapped

    def test_dwocc1990_nonresponse_is_excluded_from_unmapped_and_reported_separately(self, harmonized_fixture):
        """G6D redefinition on the harmonized route: DWOCC1990 == 999 is nonresponse, not crosswalk loss."""
        records = self.harmonized_records([{"DWOCC1990": 4}, {"DWOCC1990": 999}])
        mapped_df, unmapped_share, nonresponse_share = attach_lost_job_occ1990dd(records, 2024)
        assert len(mapped_df) == 1
        assert unmapped_share == pytest.approx(0.0)
        assert nonresponse_share == pytest.approx(0.5)
