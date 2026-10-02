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
  • six charts via forecast_charts.py
"""

import re
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
import scipy.stats as stats

from btos_adoption import AdoptionFit, accepted_fits, annual_mean_adoption, run_adoption
from composition_era_validation import COVID_PERIODS, unemployment_change_by_period

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
# cps_major_rollup_trends.csv's 2026 averages Jan–Aug only.
CPS_EXCLUDED_PERIODS = {"2025_2026": "partial year (2026 averages Jan–Aug)"}

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


def _load_inputs() -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """The dynamic report and each instrument's sector employment panel."""
    dynamic_report_df = pd.read_csv(DYNAMIC_REPORT_PATH, dtype={"OCC_CODE": str})
    panels = {
        "oews": sector_employment_panel(pd.read_csv(OEWS_SECTOR_TRENDS_PATH)),
        "cps": sector_employment_panel(pd.read_csv(CPS_SECTOR_TRENDS_PATH)),
    }
    return dynamic_report_df, panels


EXCLUDED_PERIODS_BY_INSTRUMENT = {"oews": OEWS_EXCLUDED_PERIODS, "cps": CPS_EXCLUDED_PERIODS}


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

    scores = sector_scores(dynamic_report_df)
    estimates, slope_frames, decomposition_frames = {}, [], []
    for instrument, panel_df in panels.items():
        estimate, decomposition_rows = estimate_instrument(
            instrument, panel_df, scores, EXCLUDED_PERIODS_BY_INSTRUMENT[instrument], unemployment_change, usable_fits
        )
        estimates[instrument] = estimate
        slope_frames.append(estimate.driven_df)
        decomposition_frames.append(decomposition_rows)

    pd.concat(slope_frames, ignore_index=True).to_csv(PERIOD_SLOPES_OUTPUT_PATH, index=False)
    pd.concat(decomposition_frames, ignore_index=True).to_csv(DECOMPOSITION_OUTPUT_PATH, index=False)
    print(f"  ✓ {PERIOD_SLOPES_OUTPUT_PATH}\n  ✓ {DECOMPOSITION_OUTPUT_PATH}")
    print_checkpoint(estimates)
    return estimates, usable_fits


def run_stage() -> None:
    """The `forecast` pipeline stage."""
    run_estimation()


if __name__ == "__main__":
    run_stage()
