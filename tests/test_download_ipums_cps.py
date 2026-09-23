"""Tests for download_ipums_cps.py — IPUMS extract requests, without touching IPUMS."""

import ast

import pytest

import download_ipums_cps
import ipums_cps_variables as ipums_variables


class TestSampleIds:
    def test_basic_monthly_id_zero_pads_the_month(self):
        assert download_ipums_cps.basic_monthly_sample_id(1983, 1) == "cps1983_01b"

    def test_dws_id_is_the_january_sample(self):
        assert download_ipums_cps.dws_sample_id(2024) == "cps2024_01b"


class TestNoTopLevelIpumspyImport:
    """CI never installs ipumspy, so importing either IPUMS module must not require it."""

    @pytest.mark.parametrize("module_path", ["download_ipums_cps.py", "ipums_cps_variables.py"])
    def test_ipumspy_is_imported_only_inside_functions(self, module_path):
        with open(module_path) as source_file:
            module_tree = ast.parse(source_file.read())
        top_level_imports = [node for node in module_tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
        imported_names = set()
        for import_node in top_level_imports:
            if isinstance(import_node, ast.ImportFrom):
                imported_names.add((import_node.module or "").split(".")[0])
            else:
                imported_names.update(alias.name.split(".")[0] for alias in import_node.names)
        assert "ipumspy" not in imported_names


class TestApiKey:
    def test_missing_key_raises_with_registration_instructions(self, monkeypatch):
        monkeypatch.setattr(download_ipums_cps, "load_dotenv", lambda: None)
        monkeypatch.delenv("IPUMS_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="account.ipums.org"):
            download_ipums_cps._api_key()


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
        (extract_dir / "cps_00001.dat.gz").write_bytes(b"")

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
