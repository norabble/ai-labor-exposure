"""
historical_displacement.py
──────────────────────────
Estimates the economy-wide displacement rate D used by the demand composition
model — the fraction of economy-wide labor input displaced per year.

D is the model's only empirical input. It replaces the per-task AI penetration
scores the dynamic model uses, and it is deliberately a single scalar per year
rather than a per-occupation series: a scalar cannot manufacture a
cross-sectional pattern, so the demand-type composition does all the work of
deciding which occupations are displaced and which absorb. That is what makes
the model's validation non-circular. It also means D cancels out of every
cross-sectional Pearson correlation — see synthesize_composition.py — so D
governs the model's amplitude and its time variation, not its shape.

Inputs:
  • seeds/dws_displacement_panel.csv  (via dws_panel.py — the primary source)
  • https://api.bls.gov/publicAPI/v2/timeseries/data/  (productivity, employment)
  • BLS_API_KEY (environment, via .env) — optional but strongly preferred

Outputs:
  • data/output/historical_displacement_rate.csv
  • data/raw/bls_api/<series_id>_<start>_<end>.json  (fetch cache)

Five estimates are produced, so the model can be swept across D sources the way
synthesize_dynamic.compute_equilibration_sensitivity sweeps the absorption
scalar:

  dws_all_tenures             every displaced worker, all job tenures
  dws_long_tenured            workers with 3+ years on the lost job
  dws_structural_long_tenured long-tenured, "position or shift abolished" only
  dws_structural_all_tenures  all tenures scaled by the long-tenured structural
                              share — assumes short-tenured workers are
                              displaced for the same mix of reasons, which the
                              release does not report
  productivity                smoothed nonfarm business output per hour

Why the DWS is primary, and what was rejected — measured against BLS data
2005-2024 before this module was written:

  CPS permanent job losers      r = 0.944 with the unemployment rate. It is the
                                business cycle; purging it leaves 11% of the
                                variance, too thin at n = 20.
  BED gross job losses          r = 0.860 with the change in unemployment, and
                                ~23%/yr is ordinary establishment churn rather
                                than displacement.
  BED excess reallocation       least cyclical, but a coefficient of variation
                                of 0.055 — it barely moves, so it carries no
                                time signal.
  Labor productivity growth     theoretically exact (x% more output per hour
                                means x% of hours are redundant at constant
                                output) but volatile, and negative in 2 of 20
                                years. A negative D inverts every prediction the
                                model makes, so it is clipped and smoothed here
                                and kept only as a secondary source.

The DWS is the only candidate that isolates structural displacement by
definition rather than by statistical purging: "position or shift abolished"
separates technological and organisational displacement from plant closings and
insufficient work at the survey instrument, losing no variance in the process.
"""

import functools
import json
import os
import warnings

import pandas as pd
import requests
from dotenv import load_dotenv

from dws_panel import STRUCTURAL_REASON, load_dws_panel

BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
API_CACHE_DIR = "data/raw/bls_api"
OUTPUT_PATH = "data/output/historical_displacement_rate.csv"

# Nonfarm business sector output per hour, percent change from previous quarter
# at an annual rate.
PRODUCTIVITY_SERIES_ID = "PRS85006092"
# Total nonfarm employment, thousands — the denominator that turns displaced
# worker counts into a rate.
EMPLOYMENT_SERIES_ID = "CES0000000001"

# A registered key raises the API's limits from 25 requests/day, 25 series and 10
# years per request to 500/day, 50 series and 20 years. Requests still succeed
# without one, so the key is optional.
API_KEY_VARIABLE = "BLS_API_KEY"
UNREGISTERED_MAX_YEARS = 10
REGISTERED_MAX_YEARS = 20

REQUEST_TIMEOUT_SECONDS = 60

PRODUCTIVITY_SMOOTHING_YEARS = 3

DISPLACEMENT_SOURCES = (
    "dws_all_tenures",
    "dws_long_tenured",
    "dws_structural_long_tenured",
    "dws_structural_all_tenures",
    "productivity",
)

DEFAULT_SOURCE = "dws_structural_all_tenures"

OUTPUT_COLUMNS = ["year", "source", "displacement_rate", "n_observations", "is_interpolated"]


@functools.cache
def _load_environment() -> None:
    """Load .env on first use rather than at import.

    Importing a module must not mutate the process environment: doing so leaked
    GCP_PROJECT_ID into pytest and silently un-skipped the Vertex AI model
    availability tests in tests/test_models.py, which then failed.
    """
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))


def _api_key() -> str:
    _load_environment()
    return os.environ.get(API_KEY_VARIABLE, "").strip()


def _cache_path(series_id: str, start_year: int, end_year: int) -> str:
    return os.path.join(API_CACHE_DIR, f"{series_id}_{start_year}_{end_year}.json")


def fetch_bls_series(series_id: str, start_year: int, end_year: int) -> pd.DataFrame | None:
    """Fetch one BLS time series, caching the response so re-runs need no network.

    Returns a frame of year / period / value, or None when the series cannot be
    fetched and nothing is cached — callers skip rather than fail.
    """
    os.makedirs(API_CACHE_DIR, exist_ok=True)
    cache_path = _cache_path(series_id, start_year, end_year)

    payload = None
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as cache_file:
            payload = json.load(cache_file)
    else:
        request_body: dict[str, object] = {
            "seriesid": [series_id],
            "startyear": str(start_year),
            "endyear": str(end_year),
        }
        if _api_key():
            request_body["registrationkey"] = _api_key()
        try:
            response = requests.post(BLS_API_URL, json=request_body, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as request_error:
            warnings.warn(f"Could not fetch BLS series {series_id}: {request_error}", stacklevel=2)
            return None

        if payload.get("status") != "REQUEST_SUCCEEDED":
            warnings.warn(f"BLS API refused series {series_id}: {payload.get('message')}", stacklevel=2)
            return None
        with open(cache_path, "w", encoding="utf-8") as cache_file:
            json.dump(payload, cache_file)

    observation_rows = []
    for series in payload.get("Results", {}).get("series", []):
        for observation in series.get("data", []):
            value = pd.to_numeric(str(observation.get("value", "")).replace(",", ""), errors="coerce")
            if pd.notna(value):
                observation_rows.append({"year": int(observation["year"]), "period": observation["period"], "value": value})

    if not observation_rows:
        warnings.warn(f"BLS series {series_id} returned no usable observations", stacklevel=2)
        return None
    return pd.DataFrame(observation_rows)


def fetch_annual_means(series_id: str, start_year: int, end_year: int) -> pd.Series | None:
    """Fetch a BLS series and collapse its sub-annual periods to annual means.

    The API caps a single request at 10 years unregistered and 20 registered, so
    longer spans are fetched in chunks.
    """
    max_years = REGISTERED_MAX_YEARS if _api_key() else UNREGISTERED_MAX_YEARS

    chunk_frames = []
    chunk_start = start_year
    while chunk_start <= end_year:
        chunk_end = min(chunk_start + max_years - 1, end_year)
        chunk_df = fetch_bls_series(series_id, chunk_start, chunk_end)
        if chunk_df is not None:
            chunk_frames.append(chunk_df)
        chunk_start = chunk_end + 1

    if not chunk_frames:
        return None

    observation_df = pd.concat(chunk_frames, ignore_index=True).drop_duplicates(subset=["year", "period"])
    # M13 and Q05 are BLS's own annual-average periods; including them alongside
    # the monthly or quarterly values would weight the average twice.
    observation_df = observation_df[~observation_df["period"].isin(["M13", "Q05"])]
    return observation_df.groupby("year")["value"].mean().sort_index()


def productivity_displacement_rate(
    start_year: int = 2005,
    end_year: int = 2025,
    smoothing_years: int = PRODUCTIVITY_SMOOTHING_YEARS,
) -> pd.Series | None:
    """Displacement rate from smoothed labor productivity growth, clipped at zero.

    Raw annual productivity growth is negative in some years (−1.3% in 2022,
    −0.3% in 2011). A negative D would flip the sign of gross_displacement and
    invert every prediction the model makes, so negative values are clipped to
    zero and warned about rather than propagated.
    """
    productivity_growth = fetch_annual_means(PRODUCTIVITY_SERIES_ID, start_year, end_year)
    if productivity_growth is None:
        return None

    smoothed_growth = productivity_growth.rolling(window=smoothing_years, center=True, min_periods=1).mean()
    negative_years = sorted(smoothed_growth.index[smoothed_growth < 0])
    if negative_years:
        warnings.warn(
            f"Smoothed productivity growth is negative in {negative_years}; clipping to zero because a negative "
            f"displacement rate would invert the demand composition model.",
            stacklevel=2,
        )
    return (smoothed_growth.clip(lower=0.0) / 100.0).rename("displacement_rate")


def employment_by_year(start_year: int = 2005, end_year: int = 2025) -> pd.Series | None:
    """Total nonfarm employment in thousands, annual means — the displacement rate denominator."""
    return fetch_annual_means(EMPLOYMENT_SERIES_ID, start_year, end_year)


def dws_displacement_rate(
    displacement_panel_df: pd.DataFrame,
    employment_thousands_by_year: pd.Series,
    tenure_class: str = "all_tenures",
    structural_only: bool = False,
) -> pd.Series:
    """Annual displacement rate from one DWS survey window, spread across the years it covers.

    Each survey reports displacement over the three calendar years preceding it, so
    the resulting rate is an annual average over that window and is assigned to
    every year in it. The window length comes from the panel, not a hardcoded 3.

    When structural_only is set, the count is restricted to "position or shift
    abolished". For the long-tenured tenure class the release reports that reason
    directly; for all tenures it is applied as a share, because the release does
    not break short-tenured displacement down by reason.
    """
    rate_by_year: dict[int, float] = {}

    for survey_year, survey_df in displacement_panel_df.groupby("survey_year"):
        period_years = int(survey_df["period_years"].iloc[0])
        period_start_year = int(survey_df["period_start_year"].iloc[0])
        period_end_year = int(survey_df["period_end_year"].iloc[0])

        reason_df = survey_df[survey_df["source_table"] == "table_2_reason"]
        long_tenured_total = reason_df["displaced_thousands"].sum()
        structural_share = (
            reason_df.loc[reason_df["reason"] == STRUCTURAL_REASON, "displaced_thousands"].sum() / long_tenured_total
            if long_tenured_total
            else float("nan")
        )

        if tenure_class == "all_tenures":
            displaced_thousands = survey_df.loc[survey_df["source_table"] == "table_8_all_tenures", "displaced_thousands"].sum()
            if structural_only:
                displaced_thousands *= structural_share
        else:
            if structural_only:
                displaced_thousands = reason_df.loc[reason_df["reason"] == STRUCTURAL_REASON, "displaced_thousands"].sum()
            else:
                displaced_thousands = survey_df.loc[survey_df["source_table"] == "table_5_occupation", "displaced_thousands"].sum()

        if not displaced_thousands or pd.isna(displaced_thousands):
            warnings.warn(f"DWS survey {survey_year} has no usable displacement count; skipping it.", stacklevel=2)
            continue

        window_years = [year for year in range(period_start_year, period_end_year + 1)]
        window_employment = employment_thousands_by_year.reindex(window_years).mean()
        if pd.isna(window_employment) or not window_employment:
            warnings.warn(f"No employment denominator for DWS survey {survey_year} ({window_years}); skipping it.", stacklevel=2)
            continue

        annual_rate = displaced_thousands / window_employment / period_years
        for year in window_years:
            rate_by_year[year] = annual_rate

    return pd.Series(rate_by_year, name="displacement_rate").sort_index()


def economy_displacement_rate(
    source: str = DEFAULT_SOURCE,
    start_year: int = 2005,
    end_year: int = 2025,
) -> pd.Series | None:
    """Return the annual economy-wide displacement rate from the named source."""
    if source not in DISPLACEMENT_SOURCES:
        raise ValueError(f"unknown displacement rate source {source!r}; choose from {list(DISPLACEMENT_SOURCES)}")

    if source == "productivity":
        return productivity_displacement_rate(start_year, end_year)

    displacement_panel_df = load_dws_panel()
    if displacement_panel_df is None:
        warnings.warn("No DWS panel available; cannot compute a DWS displacement rate.", stacklevel=2)
        return None

    employment_thousands_by_year = employment_by_year(start_year, end_year)
    if employment_thousands_by_year is None:
        warnings.warn("No employment denominator available; cannot compute a DWS displacement rate.", stacklevel=2)
        return None

    return dws_displacement_rate(
        displacement_panel_df,
        employment_thousands_by_year,
        tenure_class="long_tenured" if "long_tenured" in source else "all_tenures",
        structural_only="structural" in source,
    )


def build_displacement_rate_table(start_year: int = 2005, end_year: int = 2025) -> pd.DataFrame:
    """Compute every displacement rate source into one long table for comparison and sweeping."""
    rate_rows = []
    for source in DISPLACEMENT_SOURCES:
        rate_series = economy_displacement_rate(source, start_year, end_year)
        if rate_series is None:
            continue
        for year, displacement_rate in rate_series.items():
            rate_rows.append(
                {
                    "year": int(year),
                    "source": source,
                    "displacement_rate": float(displacement_rate),
                    "n_observations": int(len(rate_series)),
                    # A DWS survey's rate is one window average repeated across the
                    # years it covers, not an independent reading per year.
                    "is_interpolated": source.startswith("dws"),
                }
            )

    if not rate_rows:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    return pd.DataFrame(rate_rows)[OUTPUT_COLUMNS].sort_values(["source", "year"]).reset_index(drop=True)


def main() -> None:
    """Build the displacement rate table and write it to data/output/."""
    print("Estimating economy-wide displacement rates...")
    displacement_rate_df = build_displacement_rate_table()

    if displacement_rate_df.empty:
        print("  ⚠ No displacement rate could be estimated; the composition model will need an explicit rate.")
        return

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    displacement_rate_df.to_csv(OUTPUT_PATH, index=False)

    for source, source_df in displacement_rate_df.groupby("source"):
        print(
            f"  {source:<28} {source_df['displacement_rate'].mean():.4%} mean "
            f"({source_df['year'].min()}–{source_df['year'].max()}, n={len(source_df)})"
        )
    print(f"  ✓ {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
