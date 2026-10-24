"""
download_cps_history.py
───────────────────────
Fetches monthly CPS employment for the 22 SOC major groups of Table A-19 from the
BLS public API and writes it in the A-19 panel schema, so cps_panel.py can merge it
with no structural change. One batched request carries all 22 series.

The API is the panel's source; the A-19 page that download_cps.js fetches is kept
only as a cross-check (cps_panel.check_release_against_history). Unlike www.bls.gov,
api.bls.gov answers plain HTTP, so no browser is needed.

October 2025 has no observation — CPS was not collected during the federal
shutdown — and is left absent, never filled.

Inputs:
  • BLS_API_KEY (optional, .env or environment) — raises the API's request limits
Outputs:
  • data/raw/cps/a19_api_history.csv — month, soc_major, occupation,
    employed_thousands, source_reference_month; 2020-01 onward

Like download_cps.js, this warns and exits 0 under CI when the fetch fails, so the
pipeline still renders from seeds/cps_a19_panel.csv; locally it exits non-zero.
"""

import os
import sys
from datetime import date

import pandas as pd
import requests

from cps_panel import (
    A19_SERIES_BY_SOC_MAJOR,
    API_HISTORY_PATH,
    OCCUPATION_BY_SOC_MAJOR,
    PANEL_COLUMNS,
    SEED_PANEL_PATH,
)
from historical_displacement import BLS_API_URL, REQUEST_TIMEOUT_SECONDS, _api_key

# CPS adopted the 2018 Census occupation coding in January 2020; earlier months are
# not comparable and are deliberately not fetched.
HISTORY_START_YEAR = 2020
ANNUAL_AVERAGE_PERIOD = "M13"


def fetch_history_payload(start_year: int = HISTORY_START_YEAR, end_year: int | None = None) -> dict:
    """One POST for all 22 series; raises on an HTTP or JSON failure."""
    # Unregistered requests are limited to 10 years. 2020 through the current year
    # exceeds that from 2030 on: chunk the range then, or rely on BLS_API_KEY
    # (registered: 20 years).
    request_body: dict[str, object] = {
        "seriesid": list(A19_SERIES_BY_SOC_MAJOR.values()),
        "startyear": str(start_year),
        "endyear": str(end_year or date.today().year),
    }
    if _api_key():
        request_body["registrationkey"] = _api_key()
    response = requests.post(BLS_API_URL, json=request_body, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def parse_api_payload(payload: dict) -> pd.DataFrame:
    """API response → panel rows. Raises if BLS refused the request or any month lacks a group."""
    if payload.get("status") != "REQUEST_SUCCEEDED":
        raise ValueError(f"BLS API returned {payload.get('status')}: {payload.get('message')}")

    soc_major_by_series = {series_id: soc_major for soc_major, series_id in A19_SERIES_BY_SOC_MAJOR.items()}
    history_rows = []
    for series in payload.get("Results", {}).get("series", []):
        soc_major = soc_major_by_series[series["seriesID"]]
        for observation in series.get("data", []):
            period = observation["period"]
            if not period.startswith("M") or period == ANNUAL_AVERAGE_PERIOD:
                continue
            employed_thousands = pd.to_numeric(str(observation["value"]).replace(",", ""), errors="coerce")
            if pd.isna(employed_thousands):
                continue
            if employed_thousands != int(employed_thousands):
                raise ValueError(f"{series['seriesID']} {observation['year']}-{period[1:]} is {employed_thousands}, not whole thousands")
            history_rows.append(
                {
                    "month": f"{observation['year']}-{period[1:]}",
                    "soc_major": soc_major,
                    "occupation": OCCUPATION_BY_SOC_MAJOR[soc_major],
                    "employed_thousands": int(employed_thousands),
                }
            )

    history_df = pd.DataFrame(history_rows, columns=["month", "soc_major", "occupation", "employed_thousands"])
    groups_per_month = history_df.groupby("month")["soc_major"].nunique()
    incomplete_months = sorted(groups_per_month[groups_per_month != len(A19_SERIES_BY_SOC_MAJOR)].index)
    if history_df.empty or incomplete_months:
        raise ValueError(
            f"BLS API history is missing groups for month(s) {incomplete_months or 'all'}; a partial month would distort shares"
        )

    history_df["employed_thousands"] = history_df["employed_thousands"].astype("int64")
    history_df["source_reference_month"] = history_df["month"].max()
    return history_df.sort_values(["month", "soc_major"]).reset_index(drop=True)[PANEL_COLUMNS]


def main() -> None:
    try:
        history_df = parse_api_payload(fetch_history_payload())
    except (requests.RequestException, ValueError, KeyError) as fetch_error:
        message = f"Could not fetch CPS A-19 history from the BLS API: {fetch_error}"
        if os.environ.get("CI"):
            print(f"WARNING: {message} — the pipeline will use {SEED_PANEL_PATH}.")
            return
        sys.exit(message)

    os.makedirs(os.path.dirname(API_HISTORY_PATH), exist_ok=True)
    history_df.to_csv(API_HISTORY_PATH, index=False)
    print(f"Saved {API_HISTORY_PATH} ({history_df['month'].nunique()} months, {history_df['month'].min()} → {history_df['month'].max()})")


if __name__ == "__main__":
    main()
