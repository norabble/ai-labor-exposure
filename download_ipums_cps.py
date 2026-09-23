"""
download_ipums_cps.py
─────────────────────
Submit and download IPUMS CPS microdata extracts for Phase 2 of the deep history
extension: basic-monthly samples for the detailed employment panel, and January
Displaced Worker Supplement samples for the detailed displacement panel.

Local and manual only — never run in CI. IPUMS terms prohibit redistributing
microdata, so everything this writes lands under data/raw/ipums/, which git
ignores; only aggregate tables built from it are ever committed.

Needs IPUMS_API_KEY in .env (https://account.ipums.org/api_keys) and the optional
dependency group (`uv sync --group ipums`). ipumspy is imported inside the
functions that use it, so importing this module — and running the test suite —
does not require it.

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
import os
import sys
from collections.abc import Iterator

import pandas as pd
from dotenv import load_dotenv

import ipums_cps_variables as ipums_variables

RAW_DIR = "data/raw/ipums"
READ_CHUNK_ROWS = 500_000


def basic_monthly_sample_id(year: int, month: int) -> str:
    """IPUMS sample ID for one basic-monthly CPS month, e.g. (1983, 1) -> 'cps1983_01b'."""
    return ipums_variables.BASIC_MONTHLY_SAMPLE_PATTERN.format(year=year, month=month)


def dws_sample_id(survey_year: int) -> str:
    """IPUMS sample ID carrying one survey year's Displaced Worker Supplement."""
    return ipums_variables.DWS_SAMPLE_PATTERN.format(year=survey_year)


def _api_key() -> str:
    load_dotenv()
    api_key = os.environ.get("IPUMS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "IPUMS_API_KEY is not set in .env. Register for IPUMS CPS at https://cps.ipums.org "
            "and create a key at https://account.ipums.org/api_keys"
        )
    return api_key


def make_client():
    """An authenticated IpumsApiClient."""
    from ipumspy import IpumsApiClient

    return IpumsApiClient(_api_key())


def available_sample_ids(client) -> set[str]:
    """Every CPS sample ID IPUMS currently publishes."""
    return set(client.get_all_sample_info(ipums_variables.COLLECTION))


def extract_is_downloaded(extract_dir: str) -> bool:
    """True when a directory already holds a DDI codebook and a data file."""
    return bool(glob.glob(os.path.join(extract_dir, "*.xml"))) and bool(glob.glob(os.path.join(extract_dir, "*.dat.gz")))


def _submit_and_download(client, samples: list[str], variables: list[str], description: str, extract_dir: str) -> str:
    from ipumspy import MicrodataExtract

    extract = MicrodataExtract(
        collection=ipums_variables.COLLECTION,
        samples=samples,
        variables=variables,
        description=description,
    )
    client.submit_extract(extract)
    client.wait_for_extract(extract)
    os.makedirs(extract_dir, exist_ok=True)
    client.download_extract(extract, download_dir=extract_dir)
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
    samples = [basic_monthly_sample_id(year, month) for month in range(1, 13)]
    samples = [sample_id for sample_id in samples if sample_id in published_samples]
    if not samples:
        return None
    return _submit_and_download(
        client,
        samples,
        ipums_variables.BASIC_MONTHLY_VARIABLES,
        f"ai-exposure deep history phase 2: basic monthly {year}",
        extract_dir,
    )


def fetch_dws_survey(survey_year: int, raw_dir: str = RAW_DIR, client=None) -> str | None:
    """Download one survey year's January sample with the Displaced Worker Supplement variables."""
    extract_dir = os.path.join(raw_dir, "dws", str(survey_year))
    if extract_is_downloaded(extract_dir):
        return extract_dir
    client = client or make_client()
    sample_id = dws_sample_id(survey_year)
    if sample_id not in available_sample_ids(client):
        return None
    return _submit_and_download(
        client,
        [sample_id],
        ipums_variables.DWS_VARIABLES,
        f"ai-exposure deep history phase 2: displaced worker supplement {survey_year}",
        extract_dir,
    )


def _extract_paths(extract_dir: str) -> tuple[str, str]:
    ddi_paths = sorted(glob.glob(os.path.join(extract_dir, "*.xml")))
    data_paths = sorted(glob.glob(os.path.join(extract_dir, "*.dat.gz")))
    if not ddi_paths or not data_paths:
        raise FileNotFoundError(f"{extract_dir} holds no downloaded IPUMS extract")
    return ddi_paths[0], data_paths[0]


def read_codebook(extract_dir: str):
    """The DDI codebook of a downloaded extract."""
    from ipumspy import readers

    ddi_path, _ = _extract_paths(extract_dir)
    return readers.read_ipums_ddi(ddi_path)


def read_extract(extract_dir: str) -> Iterator[pd.DataFrame]:
    """Yield a downloaded extract's person records in chunks, so a full year never sits in memory twice."""
    from ipumspy import readers

    ddi_path, data_path = _extract_paths(extract_dir)
    codebook = readers.read_ipums_ddi(ddi_path)
    yield from readers.read_microdata_chunked(codebook, data_path, chunksize=READ_CHUNK_ROWS)


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
