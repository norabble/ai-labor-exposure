"""
cps_detailed_measurement.py
───────────────────────────
Pipeline-side measurement of the committed detailed CPS panel (Phase 2 of the
deep history extension): the occ1990dd trend table, each cell's relative
standard error, the sampling variance of each year-over-year growth rate,
per-period eligibility and its fixed-set sensitivity, per-period reliability,
and growth across the coding-vintage seams.

No model score enters here. These are properties of the measurement, computed
before any correlation so no choice below can be tuned toward a result.

Reliability (spec § Reliability), over a period's eligible units:
    reliability = 1 − mean(sampling variance of growth) / variance(observed growth)
Growth variance uses the delta method with adjacent years treated as
independent. Half the sample carries over between years, so this overstates the
noise — conservative, and documented.

Inputs:
  • seeds/cps_detailed_occupation_panel.csv
Outputs: none directly — cps_detailed_validation.run() writes
  cps_detailed_occupation_panel.csv, cps_detailed_trends.csv,
  cps_detailed_reliability.csv and cps_detailed_seam_breaks.csv from these.
"""

import os

import numpy as np
import pandas as pd

from analyze_bls import attach_growth_columns
from composition_era_validation import discover_period_columns, period_key
from cps_detailed_panel import SEED_PATH

HEADLINE_UNIVERSE = "all_employed"
RELIABILITY_CUTOFF = 0.20
SEAM_PERIODS = ("1991_1992", "1993_1994", "2002_2003", "2010_2011", "2019_2020")
# 2019_2020 is already excluded as COVID; the headline excludes the other four.
HEADLINE_EXCLUDED_SEAM_PERIODS = ("1991_1992", "1993_1994", "2002_2003", "2010_2011")


def load_detailed_panel(seed_path: str = SEED_PATH) -> pd.DataFrame | None:
    """The committed panel, or None when the seed has not been built yet."""
    return pd.read_csv(seed_path) if os.path.exists(seed_path) else None


def wide_by_year(panel_df: pd.DataFrame, universe: str, value_column: str) -> pd.DataFrame:
    """One universe's values as occ1990dd x integer year."""
    universe_df = panel_df[panel_df["universe"] == universe]
    wide_df = universe_df.pivot(index="occ1990dd", columns="year", values=value_column)
    wide_df.columns = [int(year) for year in wide_df.columns]
    return wide_df.sort_index(axis=1)


def build_detailed_trends(panel_df: pd.DataFrame, universe: str = HEADLINE_UNIVERSE) -> pd.DataFrame:
    """Trend table keyed by occ1990dd, in the shared TOT_EMP / growth-column layout."""
    employment_df = wide_by_year(panel_df, universe, "employed_thousands")
    available_years = [str(year) for year in employment_df.columns]
    employment_df.columns = [f"TOT_EMP_{year}" for year in available_years]
    return attach_growth_columns(employment_df.reset_index(), available_years)


def relative_standard_errors(panel_df: pd.DataFrame, universe: str = HEADLINE_UNIVERSE) -> pd.DataFrame:
    """Each cell's standard error over its level, occ1990dd x year."""
    return np.sqrt(wide_by_year(panel_df, universe, "sampling_variance")) / wide_by_year(panel_df, universe, "employed_thousands")


def growth_frame(panel_df: pd.DataFrame, start_year: int, end_year: int, universe: str = HEADLINE_UNIVERSE) -> pd.DataFrame:
    """Per unit: growth over the period, its delta-method sampling variance, and end-year employment."""
    employment_df = wide_by_year(panel_df, universe, "employed_thousands")
    variance_df = wide_by_year(panel_df, universe, "sampling_variance")
    if start_year not in employment_df.columns or end_year not in employment_df.columns:
        return pd.DataFrame(columns=["growth", "growth_variance", "end_employment"])
    start_level, end_level = employment_df[start_year], employment_df[end_year]
    level_ratio = end_level / start_level
    growth_variance = level_ratio**2 * (variance_df[end_year] / end_level**2 + variance_df[start_year] / start_level**2)
    return pd.DataFrame({"growth": level_ratio - 1, "growth_variance": growth_variance, "end_employment": end_level}).dropna()


def eligible_for_period(rse_df: pd.DataFrame, start_year: int, end_year: int, cutoff: float | None) -> pd.Index:
    """Headline eligibility: RSE at or below the cutoff in BOTH endpoint years (spec § Analysis choices)."""
    if start_year not in rse_df.columns or end_year not in rse_df.columns:
        return pd.Index([])
    endpoint_rse_df = rse_df[[start_year, end_year]].dropna()
    if cutoff is None:
        return endpoint_rse_df.index
    return endpoint_rse_df.index[(endpoint_rse_df[start_year] <= cutoff) & (endpoint_rse_df[end_year] <= cutoff)]


def fixed_set_units(rse_df: pd.DataFrame, cutoff: float) -> pd.Index:
    """Sensitivity: units at or below the cutoff in EVERY year. Selects on the outcome; never the headline."""
    return rse_df.index[(rse_df <= cutoff).all(axis=1)]


def reliability_for_units(
    panel_df: pd.DataFrame, start_year: int, end_year: int, units: pd.Index, universe: str = HEADLINE_UNIVERSE
) -> float:
    """1 − mean sampling variance of growth / observed variance of growth, over the given units."""
    units_df = growth_frame(panel_df, start_year, end_year, universe).reindex(units).dropna()
    if len(units_df) < 2:
        return float("nan")
    observed_variance = units_df["growth"].var(ddof=1)
    if not observed_variance > 0:
        return float("nan")
    return float(1 - units_df["growth_variance"].mean() / observed_variance)


def period_reliability(
    panel_df: pd.DataFrame, trends_df: pd.DataFrame, cutoff: float | None = RELIABILITY_CUTOFF, universe: str = HEADLINE_UNIVERSE
) -> pd.DataFrame:
    """One row per growth period: eligible units, employment they cover, noise, observed spread, reliability."""
    rse_df = relative_standard_errors(panel_df, universe)
    reliability_rows = []
    for growth_column in discover_period_columns(trends_df):
        period = period_key(growth_column)
        start_year, end_year = (int(part) for part in period.split("_"))
        units = eligible_for_period(rse_df, start_year, end_year, cutoff)
        period_growth_df = growth_frame(panel_df, start_year, end_year, universe)
        eligible_growth_df = period_growth_df.reindex(units).dropna()
        total_end_employment = period_growth_df["end_employment"].sum()
        reliability_rows.append(
            {
                "period": period,
                "n_eligible": len(eligible_growth_df),
                "employment_share_covered": float(eligible_growth_df["end_employment"].sum() / total_end_employment)
                if total_end_employment
                else np.nan,
                "mean_growth_sampling_variance": float(eligible_growth_df["growth_variance"].mean()) if len(eligible_growth_df) else np.nan,
                "observed_growth_variance": float(eligible_growth_df["growth"].var(ddof=1)) if len(eligible_growth_df) > 1 else np.nan,
                "reliability": reliability_for_units(panel_df, start_year, end_year, units, universe),
            }
        )
    return pd.DataFrame(reliability_rows)


def measure_vintage_seams(trends_df: pd.DataFrame) -> pd.DataFrame:
    """Per code, growth in every period with the coding-vintage seams flagged — measured, never patched."""
    seam_frames = []
    for growth_column in discover_period_columns(trends_df):
        period = period_key(growth_column)
        seam_frames.append(
            pd.DataFrame(
                {
                    "period": period,
                    "occ1990dd": trends_df["occ1990dd"],
                    "emp_growth": trends_df[growth_column],
                    "is_seam_period": period in SEAM_PERIODS,
                }
            )
        )
    return (
        pd.concat(seam_frames, ignore_index=True)
        if seam_frames
        else pd.DataFrame(columns=["period", "occ1990dd", "emp_growth", "is_seam_period"])
    )
