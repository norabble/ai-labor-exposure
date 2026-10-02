"""
test_download_cps_history.py
────────────────────────────
Tests for download_cps_history.py and the A-19 series mapping in cps_panel.py.
Payloads are built inline, so nothing here reaches the BLS API.
"""

import pytest

from cps_panel import A19_SERIES_BY_SOC_MAJOR, CPS_TO_SOC_MAJOR, OCCUPATION_BY_SOC_MAJOR, PANEL_COLUMNS
from download_cps_history import parse_api_payload


def _payload(months_by_soc_major: dict[str, list[tuple[str, str, str]]], status: str = "REQUEST_SUCCEEDED") -> dict:
    """A BLS API response: per SOC major group, (year, period, value) observations."""
    return {
        "status": status,
        "message": [],
        "Results": {
            "series": [
                {"seriesID": A19_SERIES_BY_SOC_MAJOR[soc_major], "data": [{"year": y, "period": p, "value": v} for y, p, v in observations]}
                for soc_major, observations in months_by_soc_major.items()
            ]
        },
    }


def _every_group(observations: list[tuple[str, str, str]]) -> dict[str, list[tuple[str, str, str]]]:
    return {soc_major: observations for soc_major in A19_SERIES_BY_SOC_MAJOR}


class TestSeriesMapping:
    def test_covers_every_major_group_with_a_unique_series(self):
        assert set(A19_SERIES_BY_SOC_MAJOR) == set(CPS_TO_SOC_MAJOR.values())
        assert len(set(A19_SERIES_BY_SOC_MAJOR.values())) == 22

    def test_occupation_names_match_a19_wording(self):
        assert OCCUPATION_BY_SOC_MAJOR["19"] == "Life, physical, and social science occupations"
        assert OCCUPATION_BY_SOC_MAJOR["53"] == "Transportation and material moving occupations"


class TestParseApiPayload:
    def test_returns_panel_schema_with_integer_levels(self):
        history_df = parse_api_payload(_payload(_every_group([("2026", "M09", "21,631"), ("2026", "M08", "21318")])))
        assert list(history_df.columns) == PANEL_COLUMNS
        assert history_df["employed_thousands"].dtype == "int64"
        assert history_df.loc[history_df["month"] == "2026-09", "employed_thousands"].iloc[0] == 21631

    def test_drops_the_annual_average_period(self):
        history_df = parse_api_payload(_payload(_every_group([("2025", "M13", "999"), ("2025", "M12", "100")])))
        assert sorted(history_df["month"].unique()) == ["2025-12"]

    def test_leaves_a_month_bls_did_not_collect_absent_rather_than_zero(self):
        """October 2025 was never collected; the API reports it as '-'."""
        history_df = parse_api_payload(_payload(_every_group([("2025", "M11", "100"), ("2025", "M10", "-"), ("2025", "M09", "100")])))
        assert sorted(history_df["month"].unique()) == ["2025-09", "2025-11"]

    def test_stamps_the_latest_month_as_the_source_reference(self):
        history_df = parse_api_payload(_payload(_every_group([("2026", "M09", "1"), ("2025", "M01", "1")])))
        assert set(history_df["source_reference_month"]) == {"2026-09"}

    def test_raises_when_a_month_lacks_a_group(self):
        observations = _every_group([("2026", "M09", "100")])
        observations["15"] = [("2026", "M08", "100")]
        with pytest.raises(ValueError, match="2026-08|2026-09"):
            parse_api_payload(_payload(observations))

    def test_raises_when_the_api_refuses_the_request(self):
        with pytest.raises(ValueError, match="REQUEST_NOT_PROCESSED"):
            parse_api_payload(_payload({}, status="REQUEST_NOT_PROCESSED"))

    def test_rejects_a_fractional_level(self):
        with pytest.raises(ValueError, match="whole thousands"):
            parse_api_payload(_payload(_every_group([("2026", "M09", "100.5")])))
