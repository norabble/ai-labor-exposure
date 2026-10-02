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

import numpy as np
import pandas as pd
import scipy.stats as stats

from composition_era_validation import COVID_PERIODS

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
