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
  • data/output/visualizations/historical_displacement_rate_sources.png
  • data/raw/bls_api/<series_id>_<start>_<end>.json  (fetch cache)

Six estimates are produced, so the model can be swept across D sources the way
synthesize_dynamic.compute_equilibration_sensitivity sweeps the absorption
scalar:

  dws_all_tenures             every displaced worker, all job tenures
  dws_long_tenured            workers with 3+ years on the lost job
  dws_structural_long_tenured long-tenured, "position or shift abolished" only
  dws_structural_all_tenures  all tenures scaled by the long-tenured structural
                              share — assumes short-tenured workers are
                              displaced for the same mix of reasons, which the
                              release does not report
  mlr_long_tenured            pre-2008 Monthly Labor Review displaced-worker
                              articles' economy-wide rate, 1981-2000. A SEPARATE
                              source from the four dws_* rows above, never
                              spliced onto them: it divides by long-tenured
                              workers employed, where the dws_* count-derived
                              rows divide by total employment — two different
                              quantities that happen to share units. See
                              mlr_displacement_rate.
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

import matplotlib.pyplot as plt
import pandas as pd
import requests
import seaborn as sns
from dotenv import load_dotenv

from dws_panel import STRUCTURAL_REASON, load_dws_panel
from mlr_displacement import parse_total_displacement_rate

BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
API_CACHE_DIR = "data/raw/bls_api"
OUTPUT_PATH = "data/output/historical_displacement_rate.csv"
VISUALIZATION_OUTPUT_DIR = "data/output/visualizations"
CHART_NAME = "historical_displacement_rate_sources.png"

# The DWS-derived and MLR sources divide by different denominators — total
# employment for the four dws_* rows, long-tenured workers employed for
# mlr_long_tenured (see mlr_displacement_rate's docstring) — so they are drawn
# on separate axes rather than one shared scale. productivity is neither: it
# has no displacement denominator at all (it is smoothed productivity growth,
# not a count over any population), so it is drawn as a dotted reference line
# on the total-employment panel only, labelled as a proxy rather than a rate,
# and left off the long-tenured panel rather than assigned to either group.
TOTAL_EMPLOYMENT_DENOMINATOR_SOURCES = (
    "dws_all_tenures",
    "dws_long_tenured",
    "dws_structural_long_tenured",
    "dws_structural_all_tenures",
)
LONG_TENURED_EMPLOYMENT_DENOMINATOR_SOURCES = ("mlr_long_tenured",)

# Fixed categorical order (never cycled) — the first four slots of the
# project's validated 8-hue sequence for the total-employment group, plus the
# fifth (magenta) reserved for the long-tenured-denominator group so it never
# shares a hue with anything on the panel above it. Validated with
# scripts/validate_palette.js "#2a78d6,#eb6834,#1baf7a,#4a3aa7,#e87ba4" --mode light.
SOURCE_COLORS = {
    "dws_all_tenures": "#2a78d6",
    "dws_long_tenured": "#eb6834",
    "dws_structural_long_tenured": "#1baf7a",
    "dws_structural_all_tenures": "#4a3aa7",
    "mlr_long_tenured": "#e87ba4",
}
PRODUCTIVITY_COLOR = "gray"

SOURCE_LABELS = {
    "dws_all_tenures": "DWS, all tenures",
    "dws_long_tenured": "DWS, long-tenured (3+ yrs)",
    "dws_structural_long_tenured": "DWS, structural + long-tenured",
    "dws_structural_all_tenures": "DWS, structural, all tenures — DEFAULT_SOURCE",
    "mlr_long_tenured": "MLR long-tenured (pre-2008 articles)",
}

# No archived DWS release or MLR article covers the 2002 or 2004 surveys — a
# genuine hole in survey coverage, not a gap to be bridged. See CLAUDE.md's
# seeds/dws_displacement_panel.csv note.
SURVEY_COVERAGE_HOLE = (2001, 2004)

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
    "mlr_long_tenured",
    "productivity",
)

# Publication order of the three MLR articles (each covers more periods than the
# last: 8, then 9, then 10) — see mlr_displacement.MLR_OCCUPATION_LEAVES's module
# docstring and download_dws.MLR_ARTICLE_URLS for the source URLs these were
# fetched from.
MLR_ARTICLE_PATHS = (
    "data/raw/dws/mlr/mid_1990s_1999.pdf",
    "data/raw/dws/mlr/strong_labor_market_2001.pdf",
    "data/raw/dws/mlr/displacement_1999_2000_2004.pdf",
)

DEFAULT_SOURCE = "dws_structural_all_tenures"

# 1981 is mlr_long_tenured's own start year — the earliest period the MLR articles'
# Table 2 publishes (see mlr_displacement.py). The DWS count-derived sources start
# in 1984 (see dws_panel.py); the employment and CPS/OEWS instruments reach back
# further still (1983 and 1999 respectively), and the productivity series
# (PRS85006092) begins in 1947. mlr_long_tenured is now the binding constraint on
# how far back the model's time variation can reach; before it was added, that
# constraint was the DWS's 1984 floor.
DEFAULT_START_YEAR = 1981

OUTPUT_COLUMNS = ["year", "source", "displacement_rate", "n_observations", "is_interpolated"]

# A pre-1994 DWS survey asked about displacement over the previous five years
# rather than three (see dws_panel.py's release parsers), but every survey window
# length is read directly off the panel's own `period_years` column — computed
# by every producer as `period_end_year - period_start_year + 1` from the parsed
# survey window itself — so no `survey_year`-keyed lookup table is needed to
# reconstruct it. A `recall_window_years(survey_year)` helper keyed on
# RECALL_WINDOW_CHANGE_YEAR = 1994 previously stood in as a fallback for a
# missing `period_years` value; it was removed (2026-09-15) because every panel
# producer always sets `period_years`, so the fallback branch was provably
# unreachable and had no test that exercised it as a fallback (only the
# standalone function was tested).


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
    start_year: int = DEFAULT_START_YEAR,
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


def employment_by_year(start_year: int = DEFAULT_START_YEAR, end_year: int = 2025) -> pd.Series | None:
    """Total nonfarm employment in thousands, annual means — the displacement rate denominator."""
    return fetch_annual_means(EMPLOYMENT_SERIES_ID, start_year, end_year)


def dws_displacement_rate(
    displacement_panel_df: pd.DataFrame,
    employment_thousands_by_year: pd.Series,
    tenure_class: str = "all_tenures",
    structural_only: bool = False,
) -> pd.Series:
    """Annual displacement rate from one DWS survey window, spread across the years it covers.

    Each survey reports displacement over the three calendar years preceding it
    (five for surveys before 1994), so the resulting rate is an annual average over
    that window and is assigned to every year in it. The window length is read from
    the panel's own `period_years` column, which every panel producer
    (`dws_panel.py`'s four release parsers) always sets from the parsed survey
    window, so no fallback is needed here.

    When structural_only is set, the count is restricted to "position or shift
    abolished". For the long-tenured tenure class the release reports that reason
    directly; for all tenures it is applied as a share, because the release does
    not break short-tenured displacement down by reason.

    Restricted to `measurement_basis == "count_thousands"` rows: the pre-2008 MLR
    rate rows (see dws_panel.mlr_rows_for_panel) must never reach this count-based
    arithmetic — a rate and a count cannot be summed. The column is REQUIRED, not
    optional, because a mutation test showed that treating it as optional (`if
    "measurement_basis" in ...columns`) made this filter an unreachable no-op:
    every real caller already carries the column, so the conditional only ever
    existed to let a hand-built test fixture skip it — precisely the anti-pattern
    this project rejected elsewhere as a Critical defect (weakening production
    code to suit a fixture, rather than fixing the fixture). Callers must supply
    `measurement_basis`; see tests/test_historical_displacement.py's `_panel` helper.
    """
    displacement_panel_df = displacement_panel_df[displacement_panel_df["measurement_basis"] == "count_thousands"]

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


def load_mlr_total_displacement_rate(article_paths: tuple[str, ...] = MLR_ARTICLE_PATHS) -> pd.DataFrame | None:
    """Parse and combine the economy-wide total row from every available MLR article.

    Mirrors load_dws_panel's shape: the file I/O and cross-article merge live here,
    so mlr_displacement_rate itself stays a pure function of the combined table, the
    same split dws_displacement_rate/load_dws_panel already uses.

    Later articles cover more periods than earlier ones (8, then 9, then 10), so all
    available articles are parsed and any period appearing in more than one is
    deduplicated, keeping the later article's value — moot in practice, since every
    overlapping period agrees exactly across all three articles
    (tests/test_mlr_displacement.py). Returns None, with a warning, if none of
    article_paths exist, so callers can skip this source rather than fail.
    """
    available_paths = [path for path in article_paths if os.path.exists(path)]
    if not available_paths:
        warnings.warn("No MLR articles found; cannot compute the mlr_long_tenured displacement rate.", stacklevel=2)
        return None

    total_rate_frames = [parse_total_displacement_rate(path) for path in available_paths]
    combined_total_rate_df = pd.concat(total_rate_frames, ignore_index=True)
    return combined_total_rate_df.drop_duplicates(subset=["period_label"], keep="last").sort_values("period_start_year")


def mlr_displacement_rate(total_rate_df: pd.DataFrame) -> pd.Series:
    """Annual displacement rate from the MLR economy-wide total row, spread across each period's years.

    Each MLR article's Table 2 reports a two-year displacement rate for "Total, 20
    years and older" (mlr_displacement.parse_total_displacement_rate); this divides
    that published figure by the period length (always 2 years for every period seen
    so far) and assigns the resulting annual rate to every year in the period — the
    same spreading rule dws_displacement_rate applies to a DWS survey window.

    This is a SEPARATE source from dws_long_tenured / dws_structural_long_tenured and
    must never be spliced onto them. The denominators differ: this MLR figure is
    displaced long-tenured workers over *long-tenured workers employed*, while the
    count-derived dws_long_tenured divides displaced long-tenured workers by *total
    employment* (see dws_displacement_rate). That is why the MLR annual values run
    higher than the count path's — two different quantities that happen to share
    units, not one series with a level break. This is the same rule the project
    already applies to CPS-versus-OEWS employment (see CLAUDE.md): separate series,
    drawn apart, never spliced into one.
    """
    rate_by_year: dict[int, float] = {}
    for _, period_row in total_rate_df.iterrows():
        period_start_year = int(period_row["period_start_year"])
        period_end_year = int(period_row["period_end_year"])
        period_years = period_end_year - period_start_year + 1
        annual_rate = (period_row["displacement_rate_percent"] / 100.0) / period_years
        for year in range(period_start_year, period_end_year + 1):
            rate_by_year[year] = annual_rate

    return pd.Series(rate_by_year, name="displacement_rate").sort_index()


def economy_displacement_rate(
    source: str = DEFAULT_SOURCE,
    start_year: int = DEFAULT_START_YEAR,
    end_year: int = 2025,
) -> pd.Series | None:
    """Return the annual economy-wide displacement rate from the named source."""
    if source not in DISPLACEMENT_SOURCES:
        raise ValueError(f"unknown displacement rate source {source!r}; choose from {list(DISPLACEMENT_SOURCES)}")

    if source == "productivity":
        return productivity_displacement_rate(start_year, end_year)

    if source == "mlr_long_tenured":
        total_rate_df = load_mlr_total_displacement_rate()
        if total_rate_df is None:
            return None
        rate_series = mlr_displacement_rate(total_rate_df)
        return rate_series[(rate_series.index >= start_year) & (rate_series.index <= end_year)]

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


def build_displacement_rate_table(start_year: int = DEFAULT_START_YEAR, end_year: int = 2025) -> pd.DataFrame:
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
                    # A DWS survey's or MLR article period's rate is one window
                    # average repeated across the years it covers, not an
                    # independent reading per year.
                    "is_interpolated": source.startswith("dws") or source == "mlr_long_tenured",
                }
            )

    if not rate_rows:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    return pd.DataFrame(rate_rows)[OUTPUT_COLUMNS].sort_values(["source", "year"]).reset_index(drop=True)


def plot_displacement_rate_history(displacement_rate_df: pd.DataFrame, output_dir: str = VISUALIZATION_OUTPUT_DIR) -> None:
    """Draw every displacement rate source across the 45-year span, on two axes.

    Two properties of this data would mislead a reader if drawn as one smooth
    line on one axis, so the design answers both directly rather than in a
    caption alone:

    Different denominators. The four dws_* sources divide displaced workers by
    *total employment*; mlr_long_tenured divides by *long-tenured workers
    employed* — a different quantity, not a level break in the same one (see
    mlr_displacement_rate's docstring). They are drawn on two stacked axes with
    their own denominator named in the axis label and title, never on one
    shared scale, and each axis is left to autoscale to its own series so the
    long-tenured panel's much narrower range (roughly 1.1-2.0%) is visibly
    different from the total-employment panel's rather than matched to it.
    productivity has no displacement denominator at all — it is smoothed
    productivity growth, not a count over any population — so it is drawn only
    on the total-employment panel, as a dotted line labelled as a proxy rather
    than a rate, and left off the long-tenured panel entirely: plotting it
    there against a "% of long-tenured workers employed" axis would assert a
    denominator it does not have, and drawing it at matching heights on both
    panels would invite exactly the cross-panel comparison the two-panel split
    exists to prevent.

    Step functions, not annual readings. is_interpolated sources repeat one
    survey-window or article-period average across every year it covers
    (dws_long_tenured: 10 distinct values across 21 years; mlr_long_tenured: 6
    across 20 — computed below, not hardcoded, so this stays correct if the
    panel grows). drawstyle="steps-post" draws the flat window and the
    instantaneous jump at the survey boundary that a smooth line would hide.

    The 2001-2004 hole (no archived DWS release or MLR article covers the 2002
    or 2004 survey) is shown as a hatched band rather than bridged — the two
    step lines already stop and start either side of it, so nothing connects
    across it, and the band makes the absence legible instead of just blank.

    dws_structural_all_tenures is DEFAULT_SOURCE — the rate the demand
    composition model actually uses — and is drawn heavier, with markers, at
    the top of the legend, so that is legible without reading the caption.
    """
    sns.set_theme(style="whitegrid")
    figure, (total_employment_axis, long_tenured_axis) = plt.subplots(2, 1, figsize=(13, 8.5), sharex=True, height_ratios=[2, 1])

    hole_start, hole_end = SURVEY_COVERAGE_HOLE
    for axis in (total_employment_axis, long_tenured_axis):
        axis.axvspan(
            hole_start - 0.5,
            hole_end + 0.5,
            facecolor="lightgray",
            alpha=0.45,
            hatch="//",
            edgecolor="dimgray",
            linewidth=0,
            zorder=0,
        )

    # Drawn on the total-employment panel only: productivity growth has no
    # displacement denominator at all (it is not a count over any population),
    # so plotting it against either axis's "% of ... employed" label would
    # assert something false, and drawing it at matching heights on both
    # panels would invite exactly the cross-panel comparison this chart's
    # split into two panels exists to prevent.
    productivity_df = displacement_rate_df[displacement_rate_df["source"] == "productivity"].sort_values("year")
    total_employment_axis.plot(
        productivity_df["year"],
        productivity_df["displacement_rate"] * 100,
        color=PRODUCTIVITY_COLOR,
        linestyle=":",
        linewidth=1.4,
        label="Productivity growth (proxy — no displacement denominator)",
        zorder=2,
    )

    for source in TOTAL_EMPLOYMENT_DENOMINATOR_SOURCES:
        source_df = displacement_rate_df[displacement_rate_df["source"] == source].sort_values("year")
        if source_df.empty:
            continue
        is_default_source = source == DEFAULT_SOURCE
        total_employment_axis.plot(
            source_df["year"],
            source_df["displacement_rate"] * 100,
            drawstyle="steps-post",
            color=SOURCE_COLORS[source],
            linewidth=2.4 if is_default_source else 1.3,
            marker="o" if is_default_source else None,
            markersize=4,
            label=SOURCE_LABELS[source],
            alpha=1.0 if is_default_source else 0.8,
            zorder=5 if is_default_source else 3,
        )

    for source in LONG_TENURED_EMPLOYMENT_DENOMINATOR_SOURCES:
        source_df = displacement_rate_df[displacement_rate_df["source"] == source].sort_values("year")
        if source_df.empty:
            continue
        long_tenured_axis.plot(
            source_df["year"],
            source_df["displacement_rate"] * 100,
            drawstyle="steps-post",
            color=SOURCE_COLORS[source],
            linewidth=1.8,
            marker="o",
            markersize=4,
            label=SOURCE_LABELS[source],
            zorder=4,
        )

    total_employment_axis.set_ylabel("Displacement rate\n(% of total employment)")
    long_tenured_axis.set_ylabel("Displacement rate\n(% of long-tenured\nworkers employed)")
    long_tenured_axis.set_xlabel("Year")

    total_employment_axis.set_title(
        "Total-employment denominator — DWS displaced-worker counts ÷ total employment", fontsize=10, loc="left"
    )
    long_tenured_axis.set_title(
        "Long-tenured-employment denominator — a DIFFERENT quantity, not comparable to the panel above",
        fontsize=9.5,
        loc="left",
        color=SOURCE_COLORS["mlr_long_tenured"],
    )

    for axis in (total_employment_axis, long_tenured_axis):
        if axis.get_legend_handles_labels()[0]:  # empty when its source group has no data to plot
            axis.legend(fontsize=8, loc="upper right", framealpha=0.9)

    figure.suptitle(
        "Economy-wide displacement rate D, 1981–2025 — six estimates feeding the demand composition model",
        fontsize=12,
        y=0.95,
    )

    dws_long_tenured_df = displacement_rate_df[displacement_rate_df["source"] == "dws_long_tenured"]
    mlr_df = displacement_rate_df[displacement_rate_df["source"] == "mlr_long_tenured"]
    footnote_text = (
        "Step lines are one survey-window (DWS) or article-period (MLR) average repeated across every year it "
        f"covers, not an annual reading: dws_long_tenured holds {dws_long_tenured_df['displacement_rate'].nunique()} "
        f"distinct values across {len(dws_long_tenured_df)} years; mlr_long_tenured holds "
        f"{mlr_df['displacement_rate'].nunique()} across {len(mlr_df)}. Hatched band marks "
        f"{hole_start}–{hole_end}, where BLS published neither an archived DWS release nor an MLR article — left "
        "blank, not bridged. dws_structural_all_tenures (bold, top panel) is DEFAULT_SOURCE, the rate the model "
        "actually uses. Productivity growth has no displacement denominator and appears only on the top panel. "
        "The two panels are independently scaled, not a shared axis."
    )
    figure.text(0.5, 0.01, footnote_text, ha="center", fontsize=7.3, style="italic", color="dimgray", wrap=True)

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, CHART_NAME)
    figure.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(figure)
    print(f"  Saved {output_path}")


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

    try:
        plot_displacement_rate_history(displacement_rate_df)
    except Exception as chart_error:  # a reporting artifact must never break this entry point
        warnings.warn(f"Could not draw the displacement rate chart ({chart_error})", stacklevel=2)


if __name__ == "__main__":
    main()
