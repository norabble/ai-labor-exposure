"""
forecast_composition.py
───────────────────────
Decomposed-slope composition forecast to 2030
(docs/superpowers/specs/2026-10-02-decomposed-slope-forecast-design.md).

The dynamic model's sector score is used unchanged. The forecast is built from how
strongly that score has sorted sector employment shares in each historical year:

  Stage 1  relative_growth_s,t = α_t + β_t · score_s           per period, 22 sectors
  Stage 2  β_t = β_structural + β_cycle · ΔU_t + β_AI · A_t     across periods (WLS)
  Stage 3  β_y for 2026–2030 under unemployment and adoption scenarios
  Stage 4  share_s(y+1) = share_s(y) · (1 + β_y · score_s), renormalised

Total employment is held at its start level; only shares move. Each instrument
(OEWS, CPS) is estimated on its own history and drives its own projection. The
occupation output is an allocation of each sector's projected change in proportion
to start-date employment — there is no occupation-level signal to forecast from.

Inputs:
  • data/output/occupation_dynamic_model_report.csv (validate stage)
  • data/output/bls_sector_trends.csv              (analyze stage)
  • data/output/cps_major_rollup_trends.csv        (composition stage)
  • data/output/cps_a19_panel.csv                  (validate stage)
  • BTOS series and fits                           (btos_adoption.py)
  • unemployment rate LNS14000000                  (BLS API, via composition_era_validation)
Outputs:
  • data/output/forecast_period_slopes.csv
  • data/output/forecast_slope_decomposition.csv
  • data/output/forecast_sector_paths.csv
  • data/output/forecast_sector_stability.csv
  • data/output/forecast_occupation_allocation_2030.csv
  • data/output/cps_seasonal_factors.csv
  • six charts via forecast_charts.py
CPS projects from a raw and a seasonally adjusted latest-month start (`start_basis`).
"""

import os
import re
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
import scipy.stats as stats

import btos_adoption
import forecast_charts
from btos_adoption import AdoptionFit, accepted_fits, annual_mean_adoption, run_adoption
from composition_era_validation import COVID_PERIODS, unemployment_change_by_period
from cps_detailed_panel import SEED_PATH as CPS_DETAILED_PANEL_PATH
from cps_panel import seasonal_factors

DYNAMIC_REPORT_PATH = "data/output/occupation_dynamic_model_report.csv"
OEWS_SECTOR_TRENDS_PATH = "data/output/bls_sector_trends.csv"
CPS_SECTOR_TRENDS_PATH = "data/output/cps_major_rollup_trends.csv"
CPS_A19_PANEL_PATH = "data/output/cps_a19_panel.csv"

PERIOD_SLOPES_OUTPUT_PATH = "data/output/forecast_period_slopes.csv"
DECOMPOSITION_OUTPUT_PATH = "data/output/forecast_slope_decomposition.csv"
SECTOR_PATHS_OUTPUT_PATH = "data/output/forecast_sector_paths.csv"
STABILITY_OUTPUT_PATH = "data/output/forecast_sector_stability.csv"
OCCUPATION_OUTPUT_PATH = "data/output/forecast_occupation_allocation_2030.csv"

# SOC revisions move occupations between major groups, which shows up as relative
# growth the score did not cause. Excluded from the main Stage 2 fit, kept in a
# sensitivity row. decompose_fit_strength keeps them — a deliberate departure.
OEWS_EXCLUDED_PERIODS = {"2009_2010": "SOC 2010 revision level break", "2018_2019": "SOC 2018 revision level break"}
COMPLETE_YEAR_MONTHS = 12


def cps_excluded_periods(detailed_panel_df: pd.DataFrame) -> dict[str, str]:
    """Exclude the CPS rollup's terminal period when its last year averages fewer than 12 months.

    The rollup (cps_major_rollup_trends.csv) is built from the IPUMS detailed panel,
    not from A-19, so its month count comes from that panel's months_observed.
    """
    months_by_year = detailed_panel_df.groupby("year")["months_observed"].max()
    terminal_year = int(months_by_year.index.max())
    months_observed = int(months_by_year[terminal_year])
    if months_observed >= COMPLETE_YEAR_MONTHS:
        return {}
    return {f"{terminal_year - 1}_{terminal_year}": f"partial year ({terminal_year} averages {months_observed} months)"}


PERIOD_SLOPE_COLUMNS = [
    "instrument",
    "period",
    "start_year",
    "end_year",
    "slope",
    "std_error",
    "residual_sd",
    "n_sectors",
    "is_covid",
    "excluded_reason",
]
EMPLOYMENT_YEAR_COLUMN = re.compile(r"TOT_EMP_(\d{4})")


def sector_code(value) -> str:
    """11, 11.0 and '11' all become '11', so sector joins never silently miss."""
    return f"{int(float(value)):02d}"


def report_employment_column(dynamic_report_df: pd.DataFrame) -> str:
    """The report's single TOT_EMP_<year> column, so a new OEWS vintage needs no code change."""
    employment_columns = [column for column in dynamic_report_df.columns if EMPLOYMENT_YEAR_COLUMN.fullmatch(column)]
    if len(employment_columns) != 1:
        raise ValueError(f"Expected exactly one TOT_EMP_<year> column in the dynamic report, found {employment_columns}")
    return employment_columns[0]


def sector_scores(dynamic_report_df: pd.DataFrame) -> pd.Series:
    """Employment-weighted mean net_employment_change per SOC major group."""
    employment_column = report_employment_column(dynamic_report_df)
    scored_df = dynamic_report_df.dropna(subset=[employment_column, "net_employment_change"]).copy()
    scored_df["soc_major"] = scored_df["OCC_CODE"].astype(str).str[:2].map(sector_code)
    weighted_change = (scored_df["net_employment_change"] * scored_df[employment_column]).groupby(scored_df["soc_major"]).sum()
    sector_employment = scored_df.groupby("soc_major")[employment_column].sum()
    return (weighted_change / sector_employment).rename("score")


def sector_employment_panel(sector_trends_df: pd.DataFrame) -> pd.DataFrame:
    """Sector × year employment from a TOT_EMP_<year> table (bls_sector_trends or cps_major_rollup_trends)."""
    year_by_column = {
        column: int(match.group(1)) for column in sector_trends_df.columns if (match := EMPLOYMENT_YEAR_COLUMN.fullmatch(column))
    }
    panel_df = sector_trends_df[list(year_by_column)].astype(float)
    panel_df.index = sector_trends_df["soc_major"].map(sector_code)
    panel_df.columns = [year_by_column[column] for column in year_by_column]
    return panel_df.sort_index(axis=1)


def align_sectors(panel_df: pd.DataFrame, scores: pd.Series) -> pd.Series:
    """Scores in the panel's sector order; a sector with employment but no score raises."""
    missing_sectors = sorted(set(panel_df.index) - set(scores.index))
    if missing_sectors:
        raise ValueError(f"No dynamic-model score for sector(s) {missing_sectors}")
    return scores.reindex(panel_df.index)


def estimate_period_slopes(panel_df: pd.DataFrame, scores: pd.Series, instrument: str, excluded_periods: dict[str, str]) -> pd.DataFrame:
    """Stage 1: OLS slope of relative share growth on score for every consecutive year pair."""
    aligned_scores = align_sectors(panel_df, scores)
    years = sorted(panel_df.columns)
    slope_rows = []
    for start_year, end_year in zip(years, years[1:]):
        if end_year != start_year + 1:
            continue
        period = f"{start_year}_{end_year}"
        pair_df = panel_df[[start_year, end_year]].dropna()
        if len(pair_df) < 3:
            continue
        sector_growth = pair_df[end_year] / pair_df[start_year] - 1.0
        total_growth = pair_df[end_year].sum() / pair_df[start_year].sum() - 1.0
        relative_growth = sector_growth - total_growth
        period_scores = aligned_scores[pair_df.index]
        regression = stats.linregress(period_scores, relative_growth)
        residuals = relative_growth - (regression.intercept + regression.slope * period_scores)
        slope_rows.append(
            {
                "instrument": instrument,
                "period": period,
                "start_year": start_year,
                "end_year": end_year,
                "slope": regression.slope,
                "std_error": regression.stderr,
                "residual_sd": float(np.std(residuals, ddof=2)),
                "n_sectors": len(pair_df),
                "is_covid": period in COVID_PERIODS,
                "excluded_reason": excluded_periods.get(period, ""),
            }
        )
    return pd.DataFrame(slope_rows, columns=PERIOD_SLOPE_COLUMNS)


# ── Stage 2: decompose the slope over time ─────────────────────────────────────

PRE_ADOPTION_LAST_YEAR = 2022
DECOMPOSITION_TERMS = ("structural", "cycle", "ai")
DECOMPOSITION_COLUMNS = ["term", "coefficient", "std_error", "t_statistic", "p_value", "r_squared", "n_periods"]


def attach_drivers(period_slopes_df: pd.DataFrame, unemployment_change: pd.Series, adoption_by_year: pd.Series) -> pd.DataFrame:
    """Add ΔU_t and A_t; A_t is 0 for any period ending in 2022 or earlier."""
    driven_df = period_slopes_df.copy()
    driven_df["unemployment_change"] = driven_df["period"].map(unemployment_change)
    driven_df["adoption"] = [
        0.0 if end_year <= PRE_ADOPTION_LAST_YEAR else adoption_by_year.get(end_year, np.nan) for end_year in driven_df["end_year"]
    ]
    return driven_df


def stage2_input(driven_df: pd.DataFrame, include_excluded: bool = False) -> pd.DataFrame:
    """Periods eligible for Stage 2: never COVID, excluded periods only on request, drivers present."""
    eligible = ~driven_df["is_covid"].astype(bool)
    if not include_excluded:
        eligible &= driven_df["excluded_reason"].fillna("") == ""
    eligible &= driven_df[["unemployment_change", "adoption", "slope", "std_error"]].notna().all(axis=1)
    return driven_df[eligible].reset_index(drop=True)


def _design_matrix(stage2_df: pd.DataFrame, terms) -> np.ndarray:
    columns = {
        "structural": np.ones(len(stage2_df)),
        "cycle": stage2_df["unemployment_change"].to_numpy(float),
        "ai": stage2_df["adoption"].to_numpy(float),
    }
    return np.column_stack([columns[term] for term in terms])


def _weighted_least_squares(design_matrix: np.ndarray, slopes: np.ndarray, weights: np.ndarray) -> np.ndarray:
    root_weights = np.sqrt(weights)
    coefficients, *_ = np.linalg.lstsq(design_matrix * root_weights[:, None], slopes * root_weights, rcond=None)
    return coefficients


def fit_coefficients(stage2_df: pd.DataFrame, terms=DECOMPOSITION_TERMS) -> dict[str, float] | None:
    """Coefficients only, or None when the design is rank-deficient — the bootstrap's fast path."""
    design_matrix = _design_matrix(stage2_df, terms)
    if len(stage2_df) <= len(terms) or np.linalg.matrix_rank(design_matrix) < len(terms):
        return None
    weights = 1.0 / stage2_df["std_error"].to_numpy(float) ** 2
    coefficients = _weighted_least_squares(design_matrix, stage2_df["slope"].to_numpy(float), weights)
    return dict(zip(terms, coefficients))


def decompose_slopes(stage2_df: pd.DataFrame) -> pd.DataFrame:
    """Stage 2: WLS of β_t on (1, ΔU_t, A_t), weights 1/se². Drops the AI term with a warning if unidentified."""
    nonpositive_periods = stage2_df.loc[stage2_df["std_error"] <= 0, "period"].tolist()
    if nonpositive_periods:
        raise ValueError(f"Period(s) {nonpositive_periods} have a non-positive standard error; their WLS weight would be infinite")
    terms = list(DECOMPOSITION_TERMS)
    if np.linalg.matrix_rank(_design_matrix(stage2_df, terms)) < len(terms):
        warnings.warn(
            "The AI term is not identified (no period with nonzero adoption, or adoption collinear with the "
            "other terms); fitting structural + cycle only.",
            stacklevel=2,
        )
        terms = terms[:2]

    design_matrix = _design_matrix(stage2_df, terms)
    slopes = stage2_df["slope"].to_numpy(float)
    weights = 1.0 / stage2_df["std_error"].to_numpy(float) ** 2
    degrees_of_freedom = len(stage2_df) - len(terms)
    if degrees_of_freedom <= 0:
        raise ValueError(f"Stage 2 needs more than {len(terms)} periods, got {len(stage2_df)}")

    coefficients = _weighted_least_squares(design_matrix, slopes, weights)
    residuals = slopes - design_matrix @ coefficients
    residual_variance = np.sum(weights * residuals**2) / degrees_of_freedom
    covariance = residual_variance * np.linalg.inv(design_matrix.T @ (design_matrix * weights[:, None]))
    std_errors = np.sqrt(np.diag(covariance))
    with np.errstate(divide="ignore", invalid="ignore"):
        t_statistics = coefficients / std_errors
    p_values = 2.0 * stats.t.sf(np.abs(t_statistics), degrees_of_freedom)
    weighted_mean = np.average(slopes, weights=weights)
    total_sum_of_squares = np.sum(weights * (slopes - weighted_mean) ** 2)
    r_squared = 1.0 - np.sum(weights * residuals**2) / total_sum_of_squares if total_sum_of_squares > 0 else np.nan

    return pd.DataFrame(
        {
            "term": terms,
            "coefficient": coefficients,
            "std_error": std_errors,
            "t_statistic": t_statistics,
            "p_value": p_values,
            "r_squared": r_squared,
            "n_periods": len(stage2_df),
        },
        columns=DECOMPOSITION_COLUMNS,
    )


def coefficients_from(decomposition_df: pd.DataFrame) -> dict[str, float]:
    """{term: coefficient} with every term present; an omitted AI term contributes 0."""
    coefficients = dict.fromkeys(DECOMPOSITION_TERMS, 0.0)
    coefficients.update(dict(zip(decomposition_df["term"], decomposition_df["coefficient"])))
    return coefficients


# ── Estimation entry point ─────────────────────────────────────────────────────

STAGE2_ADOPTION_FIT = "logistic"


class MissingDriverError(ValueError):
    """An eligible Stage 2 period has no unemployment change, so n would shrink silently."""


@dataclass
class InstrumentEstimate:
    instrument: str
    scores: pd.Series
    panel_df: pd.DataFrame
    driven_df: pd.DataFrame
    stage2_df: pd.DataFrame
    decomposition_df: pd.DataFrame
    coefficients: dict[str, float]


def _labelled(decomposition_df: pd.DataFrame, instrument: str, specification: str) -> pd.DataFrame:
    return decomposition_df.assign(instrument=instrument, specification=specification)


def estimate_instrument(
    instrument: str,
    panel_df: pd.DataFrame,
    scores: pd.Series,
    excluded_periods: dict[str, str],
    unemployment_change: pd.Series,
    adoption_fits: dict[str, AdoptionFit],
) -> tuple[InstrumentEstimate, pd.DataFrame]:
    """Stages 1–2 for one instrument, plus the excluded-period and adoption-backcast sensitivity rows."""
    period_slopes_df = estimate_period_slopes(panel_df, scores, instrument, excluded_periods)
    adoption_years = sorted(period_slopes_df["end_year"].loc[lambda end_years: end_years > PRE_ADOPTION_LAST_YEAR])

    main_adoption = annual_mean_adoption(adoption_fits[STAGE2_ADOPTION_FIT], adoption_years)
    driven_df = attach_drivers(period_slopes_df, unemployment_change, main_adoption)
    # A partial BLS fetch returns a series with gaps; stage2_input would drop those
    # periods without a word, and losing the AI-era ones silently removes β_AI.
    is_eligible = ~driven_df["is_covid"].astype(bool) & (driven_df["excluded_reason"].fillna("") == "")
    undriven_periods = driven_df.loc[is_eligible & driven_df["unemployment_change"].isna(), "period"].tolist()
    if undriven_periods:
        raise MissingDriverError(f"{instrument}: unemployment change missing for eligible period(s) {undriven_periods}")
    main_stage2_df = stage2_input(driven_df)
    main_decomposition_df = decompose_slopes(main_stage2_df)

    decomposition_frames = [_labelled(main_decomposition_df, instrument, "main")]
    if excluded_periods:
        decomposition_frames.append(
            _labelled(decompose_slopes(stage2_input(driven_df, include_excluded=True)), instrument, "with_excluded_periods")
        )
    for fit_name, adoption_fit in adoption_fits.items():
        if fit_name == STAGE2_ADOPTION_FIT:
            continue
        backcast_driven_df = attach_drivers(period_slopes_df, unemployment_change, annual_mean_adoption(adoption_fit, adoption_years))
        decomposition_frames.append(_labelled(decompose_slopes(stage2_input(backcast_driven_df)), instrument, f"backcast_{fit_name}"))

    estimate = InstrumentEstimate(
        instrument=instrument,
        scores=align_sectors(panel_df, scores),
        panel_df=panel_df,
        driven_df=driven_df,
        stage2_df=main_stage2_df,
        decomposition_df=main_decomposition_df,
        coefficients=coefficients_from(main_decomposition_df),
    )
    return estimate, pd.concat(decomposition_frames, ignore_index=True)


def cps_rollup_usable() -> bool:
    """Whether the CPS instrument may run: gate G4 passed and the rollup exists.

    cps_detailed_validation writes the rollup only after G4 passes, so a rollup on
    disk may be stale from an earlier run whose bridge has since been rejected.
    Mirrors dws_detailed_validation.run: this run's in-process verdict wins; with no
    verdict (the module never ran in this process) the on-disk bridge check decides.
    """
    import cps_detailed_validation

    g4_this_run = cps_detailed_validation.LAST_RUN_G4_PASSED
    if g4_this_run is False:
        print("  ⚠ Gate G4 did not pass in this run; the CPS instrument is withheld and OEWS runs alone.")
        return False
    if g4_this_run is None:
        bridge_check_path = cps_detailed_validation.BRIDGE_CHECK_OUTPUT_PATH
        if not os.path.exists(bridge_check_path) or not cps_detailed_validation.g4_passed(pd.read_csv(bridge_check_path)):
            print("  ⚠ Gate G4 has not passed; the CPS instrument is withheld and OEWS runs alone.")
            return False
    if not os.path.exists(CPS_SECTOR_TRENDS_PATH):
        print(f"  ⚠ {CPS_SECTOR_TRENDS_PATH} absent; the CPS instrument is withheld and OEWS runs alone.")
        return False
    return True


def _load_dynamic_report() -> pd.DataFrame:
    return pd.read_csv(DYNAMIC_REPORT_PATH, dtype={"OCC_CODE": str})


def _load_inputs() -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """The dynamic report and each usable instrument's sector employment panel (OEWS always; CPS when gated in)."""
    panels = {"oews": sector_employment_panel(pd.read_csv(OEWS_SECTOR_TRENDS_PATH))}
    if cps_rollup_usable():
        panels["cps"] = sector_employment_panel(pd.read_csv(CPS_SECTOR_TRENDS_PATH))
    return _load_dynamic_report(), panels


def print_checkpoint(estimates: dict[str, InstrumentEstimate]) -> None:
    """The Stage 2 result the plan's checkpoint task reads: β_AI and its p-value per instrument."""
    print("\n  Stage 2 — β_t = β_structural + β_cycle·ΔU + β_AI·A  (main specification)")
    for instrument, estimate in estimates.items():
        for row in estimate.decomposition_df.itertuples():
            print(
                f"    {instrument:<5} {row.term:<11} {row.coefficient:+.5f}  se {row.std_error:.5f}  "
                f"p = {row.p_value:.4f}  (n = {row.n_periods}, R² = {row.r_squared:.3f})"
            )


def run_estimation() -> tuple[dict[str, InstrumentEstimate], dict[str, AdoptionFit]] | None:
    """Stages 1–2 for both instruments; writes the period-slope and decomposition CSVs."""
    _, adoption_fits = run_adoption()
    dynamic_report_df, panels = _load_inputs()

    all_period_keys = sorted({f"{year}_{year + 1}" for panel_df in panels.values() for year in panel_df.columns})
    unemployment_change = unemployment_change_by_period(all_period_keys)
    if unemployment_change is None:
        print("  ⚠ No unemployment series available; skipping the composition forecast.")
        return None

    usable_fits = accepted_fits(adoption_fits)
    if STAGE2_ADOPTION_FIT not in usable_fits:
        print(f"  ⚠ The {STAGE2_ADOPTION_FIT} adoption fit was rejected; skipping the composition forecast.")
        return None

    excluded_periods_by_instrument = {"oews": OEWS_EXCLUDED_PERIODS}
    if "cps" in panels:
        excluded_periods_by_instrument["cps"] = cps_excluded_periods(
            pd.read_csv(CPS_DETAILED_PANEL_PATH, usecols=["year", "months_observed"])
        )

    scores = sector_scores(dynamic_report_df)
    estimates, slope_frames, decomposition_frames = {}, [], []
    for instrument, panel_df in panels.items():
        try:
            estimate, decomposition_rows = estimate_instrument(
                instrument, panel_df, scores, excluded_periods_by_instrument[instrument], unemployment_change, usable_fits
            )
        except MissingDriverError as missing_driver:
            print(f"  ⚠ {missing_driver}; skipping the composition forecast.")
            return None
        estimates[instrument] = estimate
        slope_frames.append(estimate.driven_df)
        decomposition_frames.append(decomposition_rows)

    pd.concat(slope_frames, ignore_index=True).to_csv(PERIOD_SLOPES_OUTPUT_PATH, index=False)
    pd.concat(decomposition_frames, ignore_index=True).to_csv(DECOMPOSITION_OUTPUT_PATH, index=False)
    print(f"  ✓ {PERIOD_SLOPES_OUTPUT_PATH}\n  ✓ {DECOMPOSITION_OUTPUT_PATH}")
    print_checkpoint(estimates)
    return estimates, usable_fits


# ── Stages 3–4: scenario slopes and share projection ───────────────────────────

FORECAST_END_YEAR = 2030
# ΔU for the period ending in each year; a year not listed is 0.
UNEMPLOYMENT_SCENARIOS = {
    "steady": {},
    "mild_recession": {2027: 1.5, 2028: -0.75, 2029: -0.75},
}
START_BASES = ("raw", "seasonally_adjusted")
SEASONAL_FACTORS_OUTPUT_PATH = "data/output/cps_seasonal_factors.csv"
SECTOR_PATH_COLUMNS = ["instrument", "start_basis", "unemployment_scenario", "adoption_fit", "as_of", "soc_major", "share", "employment"]
REQUIRED_SECTOR_COUNT = 22


@dataclass(frozen=True)
class ProjectionStep:
    as_of: str
    driver_year: int
    year_fraction: float


def oews_steps(start_year: int) -> list[ProjectionStep]:
    """OEWS is a May reference month: one full-year step per May to 2030."""
    return [ProjectionStep(f"{year}-05", year, 1.0) for year in range(start_year + 1, FORECAST_END_YEAR + 1)]


def cps_steps(start_month: str) -> list[ProjectionStep]:
    """From the start month to December (partial), then full calendar years to 2030."""
    start_year, month = (int(part) for part in start_month.split("-"))
    remaining_fraction = (12 - month) / 12
    steps = [ProjectionStep(f"{start_year}-12", start_year, remaining_fraction)] if remaining_fraction > 0 else []
    return steps + [ProjectionStep(f"{year}-12", year, 1.0) for year in range(start_year + 1, FORECAST_END_YEAR + 1)]


def slope_path(
    coefficients: dict[str, float], unemployment_path: dict[int, float], adoption_by_year: pd.Series, driver_years
) -> dict[int, float]:
    """Stage 3: β_y = β_structural + β_cycle·ΔU_y + β_AI·A_y."""
    return {
        year: coefficients["structural"]
        + coefficients["cycle"] * unemployment_path.get(year, 0.0)
        + coefficients.get("ai", 0.0) * float(adoption_by_year[year])
        for year in driver_years
    }


def step_shares(shares: pd.Series, scores: pd.Series, slope: float, year_fraction: float = 1.0) -> pd.Series:
    """One multiplicative step, renormalised. Raises rather than clipping a share at or below zero."""
    updated_shares = shares * (1.0 + slope * year_fraction * scores.reindex(shares.index))
    if updated_shares.isna().any() or (updated_shares <= 0).any():
        raise ValueError(f"Projection produced a non-positive share (slope {slope:+.4f}); the scenario is outside the model's range")
    return updated_shares / updated_shares.sum()


def project_shares(
    start_shares: pd.Series, scores: pd.Series, start_label: str, steps: list[ProjectionStep], slope_by_year: dict[int, float]
) -> pd.DataFrame:
    """Stage 4: share path, one row per as_of label (start first), one column per sector."""
    shares = start_shares / start_shares.sum()
    path = {start_label: shares}
    for step in steps:
        shares = step_shares(shares, scores, slope_by_year[step.driver_year], step.year_fraction)
        path[step.as_of] = shares
    return pd.DataFrame(path).T


def oews_start(panel_df: pd.DataFrame) -> tuple[str, int, pd.Series]:
    """Latest OEWS year's sector totals; label uses OEWS's May reference month."""
    start_year = max(panel_df.columns)
    return f"{start_year}-05", start_year, panel_df[start_year].dropna()


def cps_start_shares(a19_panel_df: pd.DataFrame, factors_df: pd.DataFrame | None = None) -> tuple[str, pd.Series]:
    """Latest A-19 month's sector levels, raw or divided by that calendar month's seasonal factor.

    The adjusted levels are rescaled to the raw month's total, so both starts describe
    the same workforce and differ only in how it is split across sectors.
    """
    latest_month = str(a19_panel_df["month"].max())
    month_df = a19_panel_df[a19_panel_df["month"].astype(str) == latest_month]
    employment = month_df.set_index(month_df["soc_major"].map(sector_code))["employed_thousands"].astype(float)
    if employment.index.nunique() != REQUIRED_SECTOR_COUNT:
        raise ValueError(f"A-19 {latest_month} has {employment.index.nunique()} sectors; a missing sector would distort every share")
    if factors_df is None:
        return latest_month, employment.sort_index()
    month_factors_df = factors_df[factors_df["calendar_month"] == int(latest_month[5:7])]
    month_factors = month_factors_df.set_index(month_factors_df["soc_major"].map(sector_code))["factor"].reindex(employment.index)
    if month_factors.isna().any():
        raise ValueError(f"No seasonal factor for sector(s) {sorted(month_factors[month_factors.isna()].index)}")
    adjusted_employment = employment / month_factors
    return latest_month, (adjusted_employment * employment.sum() / adjusted_employment.sum()).sort_index()


def cps_seasonal_factors_or_none(a19_panel_df: pd.DataFrame) -> pd.DataFrame | None:
    """Seasonal factors, written and printed; None (with a warning) when the panel cannot support them."""
    try:
        factors_df = seasonal_factors(a19_panel_df)
    except ValueError as factor_error:
        print(f"  ⚠ {factor_error}; seasonally adjusted start skipped, CPS projects from the raw start only.")
        return None
    factors_df.to_csv(SEASONAL_FACTORS_OUTPUT_PATH, index=False)
    print(f"  ✓ {SEASONAL_FACTORS_OUTPUT_PATH}")
    print(factors_df.pivot(index="soc_major", columns="calendar_month", values="factor").round(3).to_string())
    return factors_df


def project_scenarios(
    estimate: InstrumentEstimate,
    start_label: str,
    start_employment: pd.Series,
    steps: list[ProjectionStep],
    adoption_fits: dict[str, AdoptionFit],
    coefficients: dict[str, float] | None = None,
    start_basis: str = "raw",
) -> pd.DataFrame:
    """Every ΔU scenario × adoption fit for one instrument, as long-form share and employment paths."""
    coefficients = coefficients or estimate.coefficients
    driver_years = [step.driver_year for step in steps]
    total_employment = start_employment.sum()
    scores = estimate.scores.reindex(start_employment.index)
    path_frames = []
    for scenario_name, unemployment_path in UNEMPLOYMENT_SCENARIOS.items():
        for fit_name, adoption_fit in adoption_fits.items():
            slope_by_year = slope_path(coefficients, unemployment_path, annual_mean_adoption(adoption_fit, driver_years), driver_years)
            share_path = project_shares(start_employment, scores, start_label, steps, slope_by_year)
            long_df = share_path.rename_axis("as_of").reset_index().melt(id_vars="as_of", var_name="soc_major", value_name="share")
            long_df["employment"] = long_df["share"] * total_employment
            path_frames.append(
                long_df.assign(
                    instrument=estimate.instrument, start_basis=start_basis, unemployment_scenario=scenario_name, adoption_fit=fit_name
                )
            )
    return pd.concat(path_frames, ignore_index=True)[SECTOR_PATH_COLUMNS]


def project_both_instruments(estimates: dict[str, InstrumentEstimate], adoption_fits: dict[str, AdoptionFit]) -> tuple[pd.DataFrame, dict]:
    """Point projections per (instrument, start_basis); returns the paths and each start's (label, employment, steps)."""
    starts = {}
    if "oews" in estimates:
        oews_label, oews_year, oews_employment = oews_start(estimates["oews"].panel_df)
        starts[("oews", "raw")] = (oews_label, oews_employment, oews_steps(oews_year))
    if "cps" in estimates:
        a19_panel_df = pd.read_csv(CPS_A19_PANEL_PATH, dtype={"month": str, "soc_major": str})
        cps_label, cps_employment = cps_start_shares(a19_panel_df)
        starts[("cps", "raw")] = (cps_label, cps_employment, cps_steps(cps_label))
        factors_df = cps_seasonal_factors_or_none(a19_panel_df)
        if factors_df is not None:
            _, adjusted_employment = cps_start_shares(a19_panel_df, factors_df)
            starts[("cps", "seasonally_adjusted")] = (cps_label, adjusted_employment, cps_steps(cps_label))
    path_frames = [
        project_scenarios(estimates[instrument], *starts[(instrument, start_basis)], adoption_fits, start_basis=start_basis)
        for instrument, start_basis in starts
    ]
    return pd.concat(path_frames, ignore_index=True), starts


# ── Uncertainty ────────────────────────────────────────────────────────────────

BOOTSTRAP_REPLICATES = 2000
BOOTSTRAP_SEED = 20261002
REFERENCE_SCENARIO = ("steady", "logistic")
NINETY_PERCENT_Z = 1.645


def bootstrap_coefficients(stage2_df: pd.DataFrame, replicates: int, rng: np.random.Generator, terms) -> tuple[pd.DataFrame, int]:
    """Resample Stage 2 periods with replacement; a rank-deficient replicate is skipped and counted, never zero-filled."""
    coefficient_draws, skipped = [], 0
    for _ in range(replicates):
        resampled_df = stage2_df.iloc[rng.integers(0, len(stage2_df), len(stage2_df))]
        coefficients = fit_coefficients(resampled_df, terms)
        if coefficients is None:
            skipped += 1
            continue
        coefficient_draws.append(coefficients)
    return pd.DataFrame(coefficient_draws, columns=list(terms)), skipped


def bootstrap_bands(
    estimate: InstrumentEstimate,
    start: tuple,
    adoption_fits: dict[str, AdoptionFit],
    coefficient_draws: pd.DataFrame,
    start_basis: str = "raw",
) -> pd.DataFrame:
    """5th–95th percentile of each sector's share path across bootstrap coefficient draws."""
    draw_frames = []
    for draw_index, draw in enumerate(coefficient_draws.to_dict("records")):
        draw_coefficients = {**dict.fromkeys(DECOMPOSITION_TERMS, 0.0), **draw}
        draw_frames.append(
            project_scenarios(estimate, *start, adoption_fits, coefficients=draw_coefficients, start_basis=start_basis).assign(
                draw=draw_index
            )
        )
    draws_df = pd.concat(draw_frames, ignore_index=True)
    keys = ["instrument", "start_basis", "unemployment_scenario", "adoption_fit", "as_of", "soc_major"]
    return (
        draws_df.groupby(keys)["share"].quantile([0.05, 0.95]).unstack().rename(columns={0.05: "share_p5", 0.95: "share_p95"}).reset_index()
    )


def add_sector_noise(sector_paths_df: pd.DataFrame, estimates: dict[str, InstrumentEstimate], starts: dict) -> pd.DataFrame:
    """Sector-noise interval: median Stage 1 residual SD per year, accumulated as a random walk in relative growth."""
    noisy_frames = []
    for (instrument, start_basis), instrument_df in sector_paths_df.groupby(["instrument", "start_basis"]):
        residual_sd = float(estimates[instrument].stage2_df["residual_sd"].median())
        _, _, steps = starts[(instrument, start_basis)]
        elapsed_years = dict(zip([step.as_of for step in steps], np.cumsum([step.year_fraction for step in steps])))
        horizon = instrument_df["as_of"].map(elapsed_years).fillna(0.0)
        half_width = NINETY_PERCENT_Z * residual_sd * np.sqrt(horizon)
        noisy_frames.append(
            instrument_df.assign(noise_low=instrument_df["share"] * (1 - half_width), noise_high=instrument_df["share"] * (1 + half_width))
        )
    return pd.concat(noisy_frames, ignore_index=True)


def leave_one_period_out(
    estimate: InstrumentEstimate, start: tuple, adoption_fits: dict[str, AdoptionFit], start_basis: str = "raw"
) -> pd.DataFrame:
    """Range of each sector's start→2030 share change when each Stage 2 period is dropped in turn (reference scenario)."""
    scenario_name, fit_name = REFERENCE_SCENARIO
    terms = tuple(estimate.decomposition_df["term"])
    final_changes = []
    for dropped_index in range(len(estimate.stage2_df)):
        refit = fit_coefficients(estimate.stage2_df.drop(index=dropped_index), terms)
        if refit is None:
            continue
        refit_coefficients = {**dict.fromkeys(DECOMPOSITION_TERMS, 0.0), **refit}
        paths_df = project_scenarios(
            estimate, *start, {fit_name: adoption_fits[fit_name]}, coefficients=refit_coefficients, start_basis=start_basis
        )
        paths_df = paths_df[paths_df["unemployment_scenario"] == scenario_name]
        share_by_label = paths_df.pivot(index="as_of", columns="soc_major", values="share")
        final_changes.append(share_by_label.iloc[-1] - share_by_label.iloc[0])
    changes_df = pd.DataFrame(final_changes)
    return pd.DataFrame(
        {
            "instrument": estimate.instrument,
            "start_basis": start_basis,
            "soc_major": changes_df.columns,
            "change_min": changes_df.min().to_numpy(),
            "change_max": changes_df.max().to_numpy(),
            "n_refits": len(changes_df),
        }
    )


# ── Occupation allocation ──────────────────────────────────────────────────────


def allocate_to_occupations(dynamic_report_df: pd.DataFrame, sector_paths_df: pd.DataFrame) -> pd.DataFrame:
    """OEWS only: each occupation takes its sector's projected growth — an allocation, not an occupation forecast."""
    employment_column = report_employment_column(dynamic_report_df)
    occupation_df = dynamic_report_df.dropna(subset=[employment_column])[["OCC_CODE", "Title", "dominant_demand", employment_column]].copy()
    occupation_df = occupation_df.rename(columns={employment_column: "start_employment"})
    occupation_df["soc_major"] = occupation_df["OCC_CODE"].astype(str).str[:2].map(sector_code)

    oews_paths_df = sector_paths_df[sector_paths_df["instrument"] == "oews"].copy()
    oews_paths_df["soc_major"] = oews_paths_df["soc_major"].map(sector_code)
    start_label = oews_paths_df["as_of"].min()
    start_employment = (
        oews_paths_df[oews_paths_df["as_of"] == start_label]
        .groupby(["unemployment_scenario", "adoption_fit", "soc_major"])["employment"]
        .first()
    )
    oews_paths_df["sector_growth_factor"] = (
        oews_paths_df["employment"].to_numpy()
        / start_employment.reindex(
            pd.MultiIndex.from_frame(oews_paths_df[["unemployment_scenario", "adoption_fit", "soc_major"]])
        ).to_numpy()
    )

    allocation_df = occupation_df.merge(
        oews_paths_df[["soc_major", "unemployment_scenario", "adoption_fit", "as_of", "sector_growth_factor"]], on="soc_major", how="inner"
    )
    allocation_df["allocated_employment"] = allocation_df["start_employment"] * allocation_df["sector_growth_factor"]
    return allocation_df.drop(columns="sector_growth_factor")


def demand_type_shares(allocation_df: pd.DataFrame) -> pd.DataFrame:
    """Share of allocated employment by dominant_demand, per scenario and as_of."""
    keys = ["unemployment_scenario", "adoption_fit", "as_of"]
    by_type = allocation_df.groupby([*keys, "dominant_demand"])["allocated_employment"].sum().rename("employment").reset_index()
    by_type["share"] = by_type["employment"] / by_type.groupby(keys)["employment"].transform("sum")
    return by_type.drop(columns="employment")


def run_stage() -> None:
    """The `forecast` pipeline stage."""
    estimation = run_estimation()
    if estimation is None:
        return
    estimates, adoption_fits = estimation
    sector_paths_df, starts = project_both_instruments(estimates, adoption_fits)

    rng = np.random.default_rng(BOOTSTRAP_SEED)
    band_frames, stability_frames = [], []
    for instrument, estimate in estimates.items():
        terms = tuple(estimate.decomposition_df["term"])
        coefficient_draws, skipped = bootstrap_coefficients(estimate.stage2_df, BOOTSTRAP_REPLICATES, rng, terms)
        print(f"  {instrument}: {len(coefficient_draws)} bootstrap replicates used, {skipped} skipped as rank-deficient")
        # Both CPS starts share one set of draws, so their bands differ only by start shares.
        for start_key in [key for key in starts if key[0] == instrument]:
            band_frames.append(bootstrap_bands(estimate, starts[start_key], adoption_fits, coefficient_draws, start_basis=start_key[1]))
            stability_frames.append(leave_one_period_out(estimate, starts[start_key], adoption_fits, start_basis=start_key[1]))

    keys = ["instrument", "start_basis", "unemployment_scenario", "adoption_fit", "as_of", "soc_major"]
    sector_paths_df = add_sector_noise(
        sector_paths_df.merge(pd.concat(band_frames), on=keys, how="left", validate="one_to_one"), estimates, starts
    )
    sector_paths_df.to_csv(SECTOR_PATHS_OUTPUT_PATH, index=False)
    pd.concat(stability_frames, ignore_index=True).to_csv(STABILITY_OUTPUT_PATH, index=False)
    print(f"  ✓ {SECTOR_PATHS_OUTPUT_PATH}\n  ✓ {STABILITY_OUTPUT_PATH}")

    allocation_df = allocate_to_occupations(_load_dynamic_report(), sector_paths_df)
    final_label = allocation_df["as_of"].max()
    allocation_df[allocation_df["as_of"] == final_label].to_csv(OCCUPATION_OUTPUT_PATH, index=False)
    print(f"  ✓ {OCCUPATION_OUTPUT_PATH}")

    written_charts = forecast_charts.draw_all(
        pd.read_csv(PERIOD_SLOPES_OUTPUT_PATH),
        pd.read_csv(DECOMPOSITION_OUTPUT_PATH),
        pd.read_csv(btos_adoption.SERIES_OUTPUT_PATH, parse_dates=["ref_end"]),
        pd.read_csv(btos_adoption.FITS_OUTPUT_PATH, parse_dates=["month"]),
        pd.read_csv(SECTOR_PATHS_OUTPUT_PATH, dtype={"soc_major": str}),
        demand_type_shares(allocation_df),
        pd.read_csv(SEASONAL_FACTORS_OUTPUT_PATH, dtype={"soc_major": str}) if ("cps", "seasonally_adjusted") in starts else None,
    )
    for chart_name in written_charts:
        print(f"  ✓ data/output/visualizations/{chart_name}")


if __name__ == "__main__":
    run_stage()
