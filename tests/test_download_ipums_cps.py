"""Tests for download_ipums_cps.py — IPUMS extract API requests, without touching IPUMS.

Ruling 4 replaced the ipumspy-based client with a direct REST client (ipumspy
cannot be installed alongside this project's pandas 3), so these tests fake the
`requests.Session` the client uses rather than an ipumspy client object.
"""

import gzip
import hashlib

import pytest
import requests

import download_ipums_cps
import ipums_cps_variables as ipums_variables


class TestSampleIds:
    def test_basic_monthly_id_zero_pads_the_month(self):
        assert download_ipums_cps.basic_monthly_sample_id(1983, 1) == "cps1983_01b"

    def test_dws_id_is_the_january_sample(self):
        assert download_ipums_cps.dws_sample_id(2024) == "cps2024_01b"


class TestNoIpumspyReference:
    """ipumspy cannot be installed alongside this project's pandas 3 (Ruling 4), so
    neither IPUMS module may reference it at all, not merely import it lazily."""

    @pytest.mark.parametrize("module_path", ["download_ipums_cps.py", "ipums_cps_variables.py"])
    def test_module_does_not_reference_ipumspy(self, module_path):
        with open(module_path) as source_file:
            source_text = source_file.read()
        assert "ipumspy" not in source_text


class TestApiKey:
    def test_missing_key_raises_with_registration_instructions(self, monkeypatch):
        monkeypatch.setattr(download_ipums_cps, "load_dotenv", lambda: None)
        monkeypatch.delenv("IPUMS_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="account.ipums.org"):
            download_ipums_cps._api_key()


class TestExtractDefinition:
    def test_builds_the_documented_extract_json(self):
        extract_body = download_ipums_cps.extract_definition(
            samples=["cps1983_01b", "cps1983_02b"],
            variables=["YEAR", "MONTH"],
            description="a probe extract",
        )
        assert extract_body == {
            "description": "a probe extract",
            "dataStructure": {"rectangular": {"on": "P"}},
            "dataFormat": "csv",
            "samples": {"cps1983_01b": {}, "cps1983_02b": {}},
            "variables": {"YEAR": {}, "MONTH": {}},
        }


class FakeResponse:
    def __init__(self, json_data=None, content=b"", status_code=200):
        self._json_data = json_data
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._json_data


class FakeSession:
    """A stand-in for requests.Session that serves queued responses in order."""

    def __init__(self, responses):
        self.headers = {}
        self.calls = []
        self._responses = list(responses)

    def get(self, url, params=None, **kwargs):
        self.calls.append(("GET", url, params))
        return self._responses.pop(0)

    def post(self, url, params=None, json=None, headers=None, **kwargs):
        self.calls.append(("POST", url, params, json, headers))
        return self._responses.pop(0)


class TestSamplePagination:
    def test_follows_next_page_across_two_fake_pages(self):
        first_page = FakeResponse(
            json_data={
                "data": [{"name": "cps1983_01b", "description": "January 1983"}],
                "links": {"nextPage": "https://api.ipums.org/metadata/samples?page=2"},
            }
        )
        second_page = FakeResponse(
            json_data={
                "data": [{"name": "cps1983_02b", "description": "February 1983"}],
                "links": {"nextPage": None},
            }
        )
        fake_session = FakeSession([first_page, second_page])
        client = download_ipums_cps.IpumsCpsApi("test-key", session=fake_session)

        sample_descriptions = client.get_all_sample_info("cps")

        assert sample_descriptions == {
            "cps1983_01b": "January 1983",
            "cps1983_02b": "February 1983",
        }
        assert len(fake_session.calls) == 2
        assert fake_session.calls[1][1] == "https://api.ipums.org/metadata/samples?page=2"


class TestWaitForExtract:
    def test_returns_the_completed_status(self):
        fake_session = FakeSession([FakeResponse(json_data={"status": "completed", "downloadLinks": {}})])
        client = download_ipums_cps.IpumsCpsApi("test-key", session=fake_session)

        status = client.wait_for_extract(42)

        assert status["status"] == "completed"

    def test_raises_on_failed(self):
        fake_session = FakeSession([FakeResponse(json_data={"status": "failed"})])
        client = download_ipums_cps.IpumsCpsApi("test-key", session=fake_session)

        with pytest.raises(RuntimeError, match="failed"):
            client.wait_for_extract(42)


class TestDownloadExtract:
    def test_writes_files_and_verifies_sha256(self, tmp_path):
        data_content = b"YEAR,MONTH\n1983,1\n"
        codebook_content = b"<codebook/>"
        status = {
            "downloadLinks": {
                "data": {
                    "url": "https://api.ipums.org/extracts/1/cps_00001.csv.gz",
                    "bytes": len(data_content),
                    "sha256": hashlib.sha256(data_content).hexdigest(),
                },
                "ddiCodebook": {
                    "url": "https://api.ipums.org/extracts/1/cps_00001.xml",
                    "bytes": len(codebook_content),
                    "sha256": hashlib.sha256(codebook_content).hexdigest(),
                },
            }
        }
        fake_session = FakeSession([FakeResponse(content=data_content), FakeResponse(content=codebook_content)])
        client = download_ipums_cps.IpumsCpsApi("test-key", session=fake_session)

        client.download_extract(status, str(tmp_path))

        assert (tmp_path / "cps_00001.csv.gz").read_bytes() == data_content
        assert (tmp_path / "cps_00001.xml").read_bytes() == codebook_content

    def test_raises_on_sha256_mismatch(self, tmp_path):
        data_content = b"YEAR,MONTH\n1983,1\n"
        status = {
            "downloadLinks": {
                "data": {
                    "url": "https://api.ipums.org/extracts/1/cps_00001.csv.gz",
                    "bytes": len(data_content),
                    "sha256": "0" * 64,
                },
                "ddiCodebook": {
                    "url": "https://api.ipums.org/extracts/1/cps_00001.xml",
                    "bytes": 0,
                    "sha256": "0" * 64,
                },
            }
        }
        fake_session = FakeSession([FakeResponse(content=data_content)])
        client = download_ipums_cps.IpumsCpsApi("test-key", session=fake_session)

        with pytest.raises(RuntimeError, match="sha256 mismatch"):
            client.download_extract(status, str(tmp_path))


class TestReadExtract:
    def test_yields_rows_of_a_downloaded_csv_gz(self, tmp_path):
        extract_dir = tmp_path / "basic" / "1983"
        extract_dir.mkdir(parents=True)
        with gzip.open(extract_dir / "cps_00001.csv.gz", "wt") as data_file:
            data_file.write("YEAR,MONTH\n1983,1\n1983,2\n")

        chunks = list(download_ipums_cps.read_extract(str(extract_dir)))

        assert len(chunks) == 1
        assert list(chunks[0]["YEAR"]) == [1983, 1983]
        assert list(chunks[0]["MONTH"]) == [1, 2]


class TestReadCodebook:
    def test_parses_category_codes_from_namespaced_ddi_xml(self, tmp_path):
        extract_dir = tmp_path / "basic" / "1983"
        extract_dir.mkdir(parents=True)
        ddi_xml = """<?xml version="1.0"?>
        <codeBook xmlns="ddi:codebook:2_5">
          <dataDscr>
            <var name="EMPSTAT">
              <catgry><catValu>10</catValu><labl>At work</labl></catgry>
              <catgry><catValu>12</catValu><labl>Has job, not at work last week</labl></catgry>
            </var>
          </dataDscr>
        </codeBook>
        """
        (extract_dir / "cps_00001.xml").write_text(ddi_xml)

        codebook = download_ipums_cps.read_codebook(str(extract_dir))

        assert codebook.get_variable_info("EMPSTAT").codes == {
            "At work": 10,
            "Has job, not at work last week": 12,
        }

    def test_unknown_variable_raises_key_error(self, tmp_path):
        extract_dir = tmp_path / "basic" / "1983"
        extract_dir.mkdir(parents=True)
        (extract_dir / "cps_00001.xml").write_text('<codeBook xmlns="ddi:codebook:2_5"><dataDscr/></codeBook>')

        codebook = download_ipums_cps.read_codebook(str(extract_dir))

        with pytest.raises(KeyError):
            codebook.get_variable_info("NOT_A_VARIABLE")


class FakeClient:
    def __init__(self, sample_ids):
        self.sample_ids = sample_ids

    def get_all_sample_info(self, collection):
        return {sample_id: f"description of {sample_id}" for sample_id in self.sample_ids}


class TestFetchBasicMonthlyYear:
    def test_requests_only_samples_ipums_publishes(self, tmp_path, monkeypatch):
        requested = {}

        def fake_submit(client, samples, variables, description, extract_dir):
            requested["samples"] = samples
            requested["variables"] = variables
            return extract_dir

        monkeypatch.setattr(download_ipums_cps, "_submit_and_download", fake_submit)
        client = FakeClient({"cps2026_01b", "cps2026_02b", "cps2025_12b"})
        download_ipums_cps.fetch_basic_monthly_year(2026, raw_dir=str(tmp_path), client=client)
        assert requested["samples"] == ["cps2026_01b", "cps2026_02b"]
        assert requested["variables"] == ipums_variables.BASIC_MONTHLY_VARIABLES

    def test_a_year_already_downloaded_is_not_requested_again(self, tmp_path, monkeypatch):
        extract_dir = tmp_path / "basic" / "1983"
        extract_dir.mkdir(parents=True)
        (extract_dir / "cps_00001.xml").write_text("<codebook/>")
        (extract_dir / "cps_00001.csv.gz").write_bytes(b"")

        def fail_submit(*args, **kwargs):
            raise AssertionError("must not resubmit a downloaded year")

        monkeypatch.setattr(download_ipums_cps, "_submit_and_download", fail_submit)
        result = download_ipums_cps.fetch_basic_monthly_year(1983, raw_dir=str(tmp_path), client=FakeClient(set()))
        assert result == str(extract_dir)

    def test_a_year_with_no_published_samples_returns_none(self, tmp_path):
        assert download_ipums_cps.fetch_basic_monthly_year(1975, raw_dir=str(tmp_path), client=FakeClient(set())) is None


class TestFetchDwsSurvey:
    def test_requests_the_january_sample_with_dws_variables(self, tmp_path, monkeypatch):
        requested = {}

        def fake_submit(client, samples, variables, description, extract_dir):
            requested["samples"] = samples
            requested["variables"] = variables
            return extract_dir

        monkeypatch.setattr(download_ipums_cps, "_submit_and_download", fake_submit)
        download_ipums_cps.fetch_dws_survey(2024, raw_dir=str(tmp_path), client=FakeClient({"cps2024_01b"}))
        assert requested["samples"] == ["cps2024_01b"]
        assert set(ipums_variables.DWS_VARIABLES) <= set(requested["variables"])
