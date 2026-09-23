"""
download_ipums_cps.py
─────────────────────
Submit and download IPUMS CPS microdata extracts for Phase 2 of the deep history
extension: basic-monthly samples for the detailed employment panel, and January
Displaced Worker Supplement samples for the detailed displacement panel.

Talks to the IPUMS extract API v2 directly with `requests`
(https://developer.ipums.org/docs/v2/workflows/create_extracts/microdata/)
rather than through an IPUMS client library, because the only such library's
latest release pins a pandas version this project cannot run alongside. Extract
data arrives as gzipped CSV (IPUMS `dataFormat: "csv"`), with a DDI XML codebook
describing each variable's category labels.

Local and manual only — never run in CI. IPUMS terms prohibit redistributing
microdata, so everything this writes lands under data/raw/ipums/, which git
ignores; only aggregate tables built from it are ever committed.

Needs IPUMS_API_KEY in .env (https://account.ipums.org/api_keys).

Downloads are resumable: a directory that already holds a codebook and a data
file is not requested again. To refresh a partially published year (e.g. the
current year as new months appear), delete that year's directory first.

Inputs:
  • IPUMS CPS extract API (collection "cps")
Outputs:
  • data/raw/ipums/basic/{year}/        one extract per year (data file + DDI codebook)
  • data/raw/ipums/dws/{survey_year}/   one extract per DWS survey

Usage:
  python download_ipums_cps.py basic 1983 2026
  python download_ipums_cps.py dws
"""

import glob
import hashlib
import os
import sys
import time
import xml.etree.ElementTree as ElementTree
from collections.abc import Iterator
from dataclasses import dataclass
from urllib.parse import urlparse

import pandas as pd
import requests
from dotenv import load_dotenv

import ipums_cps_variables as ipums_variables

RAW_DIR = "data/raw/ipums"
READ_CHUNK_ROWS = 500_000

IPUMS_API_BASE_URL = "https://api.ipums.org"
IPUMS_API_VERSION = 2
SAMPLES_PAGE_SIZE = 2500
EXTRACT_DATA_FORMAT = "csv"
DEFAULT_POLL_INTERVAL_SECONDS = 30
DEFAULT_WAIT_TIMEOUT_SECONDS = 12 * 60 * 60

# `wait_for_extract`'s `timeout_seconds` budget is only checked between requests, so a request
# that itself never returns (a hung TCP connection, not just IPUMS reporting "queued") would
# defeat it silently without a per-call timeout on every `requests.Session` call below.
REQUEST_TIMEOUT_SECONDS = 60
# (connect, read), for the two file downloads only. `requests`' read timeout is a stall
# detector — it resets on every chunk received rather than capping total transfer time — so
# 300s tolerates a slow but steady multi-hundred-MB extract download while still catching a
# connection that has genuinely gone silent; 10s fails fast if IPUMS never accepts the connection.
DOWNLOAD_TIMEOUT_SECONDS = (10, 300)

TERMINAL_FAILURE_STATUSES = {"failed", "canceled"}


def _resolve_month_sample_id(year: int, month: int, published_samples: set[str] | None) -> str:
    """The ID IPUMS actually publishes for one CPS month, resolving the 'b'/'s' suffix.

    Confirmed live 2026-09-23 (Task 2, Step 4): IPUMS does not use a fixed suffix per month —
    of 523 basic-monthly month-samples published 1983-2025, some months publish as '...b' and
    others as '...s' with no year/month rule. March is the one month that always publishes
    both, because '03s' there names the unrelated ASEC supplement rather than a second basic
    sample, so 'b' is checked first and preferred whenever both exist. Without
    `published_samples` this can only guess 'b', which is wrong for any month IPUMS instead
    published under 's'.
    """
    b_id = f"cps{year}_{month:02d}b"
    if published_samples is None:
        return b_id
    if b_id in published_samples:
        return b_id
    s_id = f"cps{year}_{month:02d}s"
    if s_id in published_samples:
        return s_id
    return b_id


def basic_monthly_sample_id(year: int, month: int, published_samples: set[str] | None = None) -> str:
    """IPUMS sample ID for one basic-monthly CPS month.

    Pass `published_samples` (from `available_sample_ids`) to resolve IPUMS's actual per-month
    suffix; see `_resolve_month_sample_id`. Without it, this returns the 'b' guess from
    `BASIC_MONTHLY_SAMPLE_PATTERN`, kept only for offline/formatting use.
    """
    if published_samples is not None:
        return _resolve_month_sample_id(year, month, published_samples)
    return ipums_variables.BASIC_MONTHLY_SAMPLE_PATTERN.format(year=year, month=month)


def dws_sample_id(survey_year: int, published_samples: set[str] | None = None) -> str:
    """IPUMS sample ID carrying one survey year's Displaced Worker Supplement.

    The supplement rides inside a basic-monthly sample rather than a separately named sample —
    January for most survey years, but February for 1994, 1996, 1998 and 2000
    (`ipums_variables.dws_sample_month`, confirmed against IPUMS's own DWSUPPWT availability
    table) — and shares `basic_monthly_sample_id`'s 'b'/'s' suffix resolution (pass
    `published_samples` to resolve it correctly).
    """
    survey_month = ipums_variables.dws_sample_month(survey_year)
    if published_samples is not None:
        return _resolve_month_sample_id(survey_year, survey_month, published_samples)
    return ipums_variables.BASIC_MONTHLY_SAMPLE_PATTERN.format(year=survey_year, month=survey_month)


def _api_key() -> str:
    load_dotenv()
    api_key = os.environ.get("IPUMS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "IPUMS_API_KEY is not set in .env. Register for IPUMS CPS at https://cps.ipums.org "
            "and create a key at https://account.ipums.org/api_keys"
        )
    return api_key


@dataclass
class IpumsVariableInfo:
    """One DDI variable's parsed category labels, e.g. {'At work': 10, ...}."""

    codes: dict[str, int]


class IpumsCodebook:
    """A parsed DDI codebook: variable name -> category label/code mapping."""

    def __init__(self, variable_codes: dict[str, dict[str, int]]):
        self._variable_codes = variable_codes

    def get_variable_info(self, variable_name: str) -> IpumsVariableInfo:
        """The parsed category codes for one variable. Raises KeyError if unknown."""
        if variable_name not in self._variable_codes:
            raise KeyError(variable_name)
        return IpumsVariableInfo(codes=self._variable_codes[variable_name])


class IpumsCpsApi:
    """A small direct REST client for the IPUMS CPS extract API v2.

    Holds the API key (sent as the `Authorization` header, per IPUMS's own
    convention) and a `requests.Session`. A caller may inject its own session
    (tests do, to fake IPUMS's responses without touching the network).
    """

    def __init__(self, api_key: str, session: requests.Session | None = None):
        self._session = session if session is not None else requests.Session()
        self._session.headers.update({"Authorization": api_key})

    def get_all_sample_info(self, collection: str) -> dict[str, str]:
        """Every sample IPUMS currently publishes for a collection, id -> description."""
        sample_descriptions: dict[str, str] = {}
        request_url = f"{IPUMS_API_BASE_URL}/metadata/samples"
        request_params = {"collection": collection, "version": IPUMS_API_VERSION, "pageSize": SAMPLES_PAGE_SIZE}
        while request_url:
            response = self._session.get(request_url, params=request_params, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            response_body = response.json()
            for sample_record in response_body.get("data", []):
                sample_descriptions[sample_record["name"]] = sample_record.get("description", sample_record["name"])
            request_url = (response_body.get("links") or {}).get("nextPage")
            request_params = None
        return sample_descriptions

    def submit_extract(self, extract_body: dict) -> int:
        """Submit an extract definition (see `extract_definition`) and return its extract number."""
        response = self._session.post(
            f"{IPUMS_API_BASE_URL}/extracts",
            params={"collection": ipums_variables.COLLECTION, "version": IPUMS_API_VERSION},
            json=extract_body,
            headers={"Content-Type": "application/json"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()["number"]

    def wait_for_extract(
        self,
        extract_number: int,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        timeout_seconds: float = DEFAULT_WAIT_TIMEOUT_SECONDS,
    ) -> dict:
        """Poll an extract's status until IPUMS finishes producing it.

        Returns the completed status JSON. Raises RuntimeError if IPUMS reports the
        extract failed or was canceled, or if it does not complete within
        `timeout_seconds`.
        """
        status_url = f"{IPUMS_API_BASE_URL}/extracts/{extract_number}"
        status_params = {"collection": ipums_variables.COLLECTION, "version": IPUMS_API_VERSION}
        started_at = time.monotonic()
        while True:
            response = self._session.get(status_url, params=status_params, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            extract_status = response.json()
            status_value = extract_status["status"]
            if status_value == "completed":
                return extract_status
            if status_value in TERMINAL_FAILURE_STATUSES:
                raise RuntimeError(f"IPUMS extract {extract_number} {status_value}")
            if time.monotonic() - started_at > timeout_seconds:
                raise RuntimeError(
                    f"IPUMS extract {extract_number} did not complete within {timeout_seconds} seconds (last status: {status_value})"
                )
            time.sleep(poll_interval_seconds)

    def download_extract(self, extract_status: dict, download_dir: str) -> None:
        """Download an extract's data file and DDI codebook, verifying each one's sha256."""
        os.makedirs(download_dir, exist_ok=True)
        download_links = extract_status["downloadLinks"]
        for file_key in ("data", "ddiCodebook"):
            file_link = download_links[file_key]
            file_url = file_link["url"]
            file_name = os.path.basename(urlparse(file_url).path)
            response = self._session.get(file_url, timeout=DOWNLOAD_TIMEOUT_SECONDS)
            response.raise_for_status()
            actual_sha256 = hashlib.sha256(response.content).hexdigest()
            expected_sha256 = file_link["sha256"]
            if actual_sha256 != expected_sha256:
                raise RuntimeError(f"sha256 mismatch downloading {file_url}: expected {expected_sha256}, got {actual_sha256}")
            with open(os.path.join(download_dir, file_name), "wb") as downloaded_file:
                downloaded_file.write(response.content)


def make_client() -> IpumsCpsApi:
    """An authenticated IpumsCpsApi client."""
    return IpumsCpsApi(_api_key())


def available_sample_ids(client) -> set[str]:
    """Every CPS sample ID IPUMS currently publishes."""
    return set(client.get_all_sample_info(ipums_variables.COLLECTION))


def extract_definition(samples: list[str], variables: list[str], description: str) -> dict:
    """The JSON body IPUMS's extract submission endpoint expects."""
    return {
        "description": description,
        "dataStructure": {"rectangular": {"on": "P"}},
        "dataFormat": EXTRACT_DATA_FORMAT,
        "samples": {sample_id: {} for sample_id in samples},
        "variables": {variable_name: {} for variable_name in variables},
    }


def extract_is_downloaded(extract_dir: str) -> bool:
    """True when a directory already holds a DDI codebook and a gzipped CSV data file."""
    return bool(glob.glob(os.path.join(extract_dir, "*.xml"))) and bool(glob.glob(os.path.join(extract_dir, "*.csv.gz")))


def _submit_and_download(client, samples: list[str], variables: list[str], description: str, extract_dir: str) -> str:
    extract_number = client.submit_extract(extract_definition(samples, variables, description))
    extract_status = client.wait_for_extract(extract_number)
    os.makedirs(extract_dir, exist_ok=True)
    client.download_extract(extract_status, extract_dir)
    return extract_dir


def fetch_basic_monthly_year(year: int, raw_dir: str = RAW_DIR, client=None) -> str | None:
    """Download every published basic-monthly sample for one year as a single extract.

    Returns the extract directory, or None when IPUMS publishes no month of that year.
    """
    extract_dir = os.path.join(raw_dir, "basic", str(year))
    if extract_is_downloaded(extract_dir):
        return extract_dir
    client = client or make_client()
    published_samples = available_sample_ids(client)
    samples = [basic_monthly_sample_id(year, month, published_samples) for month in range(1, 13)]
    samples = [sample_id for sample_id in samples if sample_id in published_samples]
    if not samples:
        return None
    return _submit_and_download(
        client,
        samples,
        ipums_variables.variables_for_year(year),
        f"ai-exposure deep history phase 2: basic monthly {year}",
        extract_dir,
    )


def fetch_dws_survey(survey_year: int, raw_dir: str = RAW_DIR, client=None) -> str | None:
    """Download one survey year's January sample with the Displaced Worker Supplement variables."""
    extract_dir = os.path.join(raw_dir, "dws", str(survey_year))
    if extract_is_downloaded(extract_dir):
        return extract_dir
    client = client or make_client()
    published_samples = available_sample_ids(client)
    sample_id = dws_sample_id(survey_year, published_samples)
    if sample_id not in published_samples:
        return None
    return _submit_and_download(
        client,
        [sample_id],
        ipums_variables.DWS_VARIABLES,
        f"ai-exposure deep history phase 2: displaced worker supplement {survey_year}",
        extract_dir,
    )


def _ddi_path(extract_dir: str) -> str:
    ddi_paths = sorted(glob.glob(os.path.join(extract_dir, "*.xml")))
    if not ddi_paths:
        raise FileNotFoundError(f"{extract_dir} holds no downloaded DDI codebook (.xml)")
    return ddi_paths[0]


def _data_path(extract_dir: str) -> str:
    data_paths = sorted(glob.glob(os.path.join(extract_dir, "*.csv.gz")))
    if not data_paths:
        raise FileNotFoundError(f"{extract_dir} holds no downloaded IPUMS data file (.csv.gz)")
    return data_paths[0]


def _local_tag_name(qualified_tag: str) -> str:
    """An XML tag's name without its namespace, so the DDI namespace never matters."""
    return qualified_tag.split("}")[-1] if "}" in qualified_tag else qualified_tag


def _parse_ddi_codebook(ddi_path: str) -> IpumsCodebook:
    codebook_tree = ElementTree.parse(ddi_path)
    variable_codes: dict[str, dict[str, int]] = {}
    for element in codebook_tree.iter():
        if _local_tag_name(element.tag) != "var":
            continue
        variable_name = element.get("name")
        if variable_name is None:
            continue
        category_codes: dict[str, int] = {}
        for category_element in element.iter():
            if _local_tag_name(category_element.tag) != "catgry":
                continue
            code_value = None
            code_label = None
            for category_child in category_element:
                child_tag_name = _local_tag_name(category_child.tag)
                if child_tag_name == "catValu":
                    code_value = category_child.text
                elif child_tag_name == "labl":
                    code_label = category_child.text
            if code_value is not None and code_label is not None:
                category_codes[code_label] = int(code_value)
        variable_codes[variable_name] = category_codes
    return IpumsCodebook(variable_codes)


def read_codebook(extract_dir: str) -> IpumsCodebook:
    """The DDI codebook of a downloaded extract, parsed for each variable's category codes."""
    return _parse_ddi_codebook(_ddi_path(extract_dir))


def read_extract(extract_dir: str) -> Iterator[pd.DataFrame]:
    """Yield a downloaded extract's person records in chunks, so a full year never sits in memory twice.

    IPUMS CSV extracts are gzipped with upper-case variable names as headers, so
    no codebook is needed to read them — only to decode a variable's category codes.
    """
    yield from pd.read_csv(_data_path(extract_dir), chunksize=READ_CHUNK_ROWS)


def main(arguments: list[str]) -> None:
    """Command-line entry: `basic FIRST_YEAR LAST_YEAR` or `dws`."""
    if not arguments or arguments[0] not in {"basic", "dws"}:
        raise SystemExit("usage: python download_ipums_cps.py basic FIRST_YEAR LAST_YEAR | dws")
    client = make_client()
    if arguments[0] == "basic":
        first_year, last_year = int(arguments[1]), int(arguments[2])
        for year in range(first_year, last_year + 1):
            print(f"  {year}: {fetch_basic_monthly_year(year, client=client) or 'no published samples'}")
    else:
        for survey_year in ipums_variables.DWS_SURVEY_YEARS:
            print(f"  {survey_year}: {fetch_dws_survey(survey_year, client=client) or 'no published sample'}")


if __name__ == "__main__":
    main(sys.argv[1:])
