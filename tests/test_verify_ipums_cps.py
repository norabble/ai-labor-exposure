"""Tests for verify_ipums_cps.py's pure helpers — the IPUMS calls themselves are manual."""

import pandas as pd
import pytest
import requests

from verify_ipums_cps import displaced_reason_codes, household_cluster_decision, submit_and_download_or_none, summarise_basic_probe


def _person_rows(year, month, count, occ1990=100, cpsid=1, compwt=1000.0, empstat=10, age=30, classwkr=21):
    return pd.DataFrame(
        {
            "YEAR": [year] * count,
            "MONTH": [month] * count,
            "WTFINL": [1000.0] * count,
            "COMPWT": [compwt] * count,
            "CPSID": [cpsid] * count,
            "EMPSTAT": [empstat] * count,
            "AGE": [age] * count,
            "OCC1990": [occ1990] * count,
            "CLASSWKR": [classwkr] * count,
        }
    )


class TestSummariseBasicProbe:
    def test_employment_counts_only_civilian_employed_adults(self):
        person_df = pd.concat(
            [_person_rows(2020, 1, 3), _person_rows(2020, 1, 2, empstat=21), _person_rows(2020, 1, 1, age=15)],
            ignore_index=True,
        )
        summary_df = summarise_basic_probe(person_df)
        assert summary_df.loc[0, "employed_thousands"] == pytest.approx(3.0)

    def test_occ1990_valid_share_is_weighted_over_the_employed(self):
        person_df = pd.concat([_person_rows(2020, 1, 3), _person_rows(2020, 1, 1, occ1990=999)], ignore_index=True)
        assert summarise_basic_probe(person_df).loc[0, "occ1990_valid_share"] == pytest.approx(0.75)

    def test_linkage_share_counts_zero_cpsid_as_unlinked(self):
        person_df = pd.concat([_person_rows(1983, 1, 1, cpsid=0), _person_rows(1983, 1, 1, cpsid=5)], ignore_index=True)
        assert summarise_basic_probe(person_df).loc[0, "cpsid_linked_share"] == pytest.approx(0.5)


class TestHouseholdClusterDecision:
    def test_cpsid_when_every_probe_month_links(self):
        summary_df = pd.DataFrame({"cpsid_linked_share": [1.0, 0.995]})
        assert household_cluster_decision(summary_df) == "CPSID"

    def test_household_month_when_any_probe_month_does_not(self):
        summary_df = pd.DataFrame({"cpsid_linked_share": [0.0, 1.0]})
        assert household_cluster_decision(summary_df) == "household_month"


class TestSubmitAndDownloadOrNone:
    def test_returns_none_instead_of_raising_when_ipums_rejects_the_extract(self, monkeypatch):
        """A resolved sample can exist yet lack the requested supplement entirely (confirmed live
        2026-09-24 for the 2026 DWS survey, not yet conducted/published) — IPUMS answers with a
        400 for every requested variable, not an empty extract."""
        import verify_ipums_cps

        def _raise_bad_request(client, samples, variables, description, extract_dir):
            raise requests.exceptions.HTTPError("400 Client Error: Bad Request for url: ...")

        monkeypatch.setattr(verify_ipums_cps.download_ipums_cps, "_submit_and_download", _raise_bad_request)
        result = submit_and_download_or_none(
            client=None, samples=["cps2026_01s"], variables=["DWREAS"], description="probe", extract_dir="unused"
        )
        assert result is None

    def test_returns_the_extract_dir_on_success(self, monkeypatch):
        import verify_ipums_cps

        monkeypatch.setattr(verify_ipums_cps.download_ipums_cps, "_submit_and_download", lambda *args: args[-1])
        result = submit_and_download_or_none(
            client=None, samples=["cps1984_01s"], variables=["DWREAS"], description="probe", extract_dir="a_dir"
        )
        assert result == "a_dir"


class TestDisplacedReasonCodes:
    def test_matches_the_three_bls_displacement_reasons_only(self):
        reason_labels = {
            "Plant or company closed down or moved": 1,
            "Insufficient work": 2,
            "Position or shift abolished": 3,
            "Seasonal job completed": 4,
            "Self-operated business failed": 5,
            "Other": 6,
        }
        fragments = ("closed", "insufficient work", "abolished")
        assert displaced_reason_codes(reason_labels, fragments) == (1, 2, 3)
