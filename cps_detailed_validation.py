"""
cps_detailed_validation.py
──────────────────────────
Phase 2 of the deep history extension: the demand composition era test and
cycle decomposition at two new levels built from IPUMS CPS microdata, 1983–2026 —
~330 detailed occ1990dd occupations, and the 22 SOC major groups rolled up from
them.

Every choice below was pinned in the spec before any seed existed
(docs/superpowers/specs/2026-09-23-deep-history-phase-2-design.md § Analysis
choices). The views computed, all written, none chosen after the fact:

  headline                  per-period eligibility (RSE ≤ 20% at both ends), labeled
                            share ≥ 0.8, seam periods excluded, raw r
  noise_corrected           the same periods, r / sqrt(reliability)
  seams_included            the headline with the four seam periods put back
  fixed_set                 units at RSE ≤ 20% in every year — selects on the outcome
  direct_scores_diagnostic  2003–2026 only, direct Census-code scores in place of chained

An era difference counts only if raw and noise-corrected r agree in sign. Raw r is
biased toward zero and corrected r away from it, because the bootstrap
overstates noise; the two bracket the truth. Year-over-year growth at this grain
is known, and accepted by decision, to be mostly sampling noise.

Inputs:
  • seeds/cps_detailed_occupation_panel.csv, seeds/cps_detailed_occ_crosstab.csv
  • data/output/occupation_composition_model_report.csv, occupation_dynamic_model_report.csv
  • data/output/bls_trends.csv, bls_sector_trends.csv, seeds/cps_occupation_panel.csv
Outputs:
  • data/output/cps_detailed_period_correlations.csv
  • data/output/composition_model_era_comparison_cps_detailed.csv
  • data/output/composition_cycle_decomposition_cps_detailed.csv
  • data/output/cps_detailed_eligibility_sweep.csv
  • data/output/visualizations/composition_model_signal_over_time_cps_detailed.png
  (Tasks 12–13 add the rollup and the measurement outputs.)
"""

import os

import numpy as np
import pandas as pd
from scipy import stats

import composition_era_validation as era_validation
from cps_detailed_measurement import (
    HEADLINE_EXCLUDED_SEAM_PERIODS,
    HEADLINE_UNIVERSE,
    eligible_for_period,
    fixed_set_units,
    relative_standard_errors,
    reliability_for_units,
)
from cps_detailed_panel import CODING_BLOCKS

RSE_CUTOFF = 0.20
SWEEP_CUTOFFS = (0.10, 0.20, 0.30, None)
MINIMUM_LABELED_SHARE = 0.8

PERIOD_OUTPUT_PATH = "data/output/cps_detailed_period_correlations.csv"
ERA_OUTPUT_PATH = "data/output/composition_model_era_comparison_cps_detailed.csv"
CYCLE_OUTPUT_PATH = "data/output/composition_cycle_decomposition_cps_detailed.csv"
SWEEP_OUTPUT_PATH = "data/output/cps_detailed_eligibility_sweep.csv"

PERIOD_COLUMNS = ["period", "score", "fit_r", "fit_p", "n_units", "era", "is_covid", "is_seam", "reliability", "fit_r_corrected"]


def labeled_units(unit_scores_df: pd.DataFrame) -> pd.Index:
    """Units whose chained score rests on at least 80% labeled SOC weight."""
    return pd.Index(unit_scores_df.loc[unit_scores_df["labeled_share"] >= MINIMUM_LABELED_SHARE, "occ1990dd"])


def corrected_correlation(raw_r: float, reliability: float) -> float:
    """r / sqrt(reliability); undefined (NaN) when reliability ≤ 0 or the result reaches ±1."""
    if not reliability > 0:
        return float("nan")
    corrected = raw_r / np.sqrt(reliability)
    return float(corrected) if abs(corrected) < 1 else float("nan")


def detailed_period_correlations(
    unit_scores_df: pd.DataFrame,
    trends_df: pd.DataFrame,
    panel_df: pd.DataFrame,
    score_columns: list[str],
    labeled: pd.Index,
    cutoff: float | None = RSE_CUTOFF,
    fixed_units: pd.Index | None = None,
    periods: set[str] | None = None,
) -> pd.DataFrame:
    """One row per (period, score): raw r over eligible labeled units, plus reliability and corrected r.

    Shares the frame shape summarise_eras and decompose_fit_strength read, with
    `is_seam`, `reliability` and `fit_r_corrected` added.
    """
    rse_df = relative_standard_errors(panel_df, HEADLINE_UNIVERSE)
    scores_df = unit_scores_df.set_index("occ1990dd")
    growth_by_unit = trends_df.set_index("occ1990dd")
    correlation_rows = []
    for growth_column in era_validation.discover_period_columns(trends_df):
        period = era_validation.period_key(growth_column)
        if periods is not None and period not in periods:
            continue
        start_year, end_year = (int(part) for part in period.split("_"))
        units = fixed_units if fixed_units is not None else eligible_for_period(rse_df, start_year, end_year, cutoff)
        units = pd.Index(units).intersection(labeled)
        reliability = reliability_for_units(panel_df, start_year, end_year, units, HEADLINE_UNIVERSE)
        for score_column in score_columns:
            if score_column not in scores_df.columns:
                continue
            paired_df = pd.DataFrame(
                {"score": scores_df[score_column].reindex(units), "growth": growth_by_unit[growth_column].reindex(units)}
            ).dropna()
            if len(paired_df) < era_validation.MINIMUM_UNITS or paired_df["score"].nunique() < 2 or paired_df["growth"].nunique() < 2:
                continue
            correlation, p_value = stats.pearsonr(paired_df["score"], paired_df["growth"])
            correlation_rows.append(
                {
                    "period": period,
                    "score": score_column,
                    "fit_r": float(correlation),
                    "fit_p": float(p_value),
                    "n_units": len(paired_df),
                    "era": "ai" if era_validation.is_ai_era(growth_column) else "pre_ai",
                    "is_covid": period in era_validation.COVID_PERIODS,
                    "is_seam": period in HEADLINE_EXCLUDED_SEAM_PERIODS,
                    "reliability": reliability,
                    "fit_r_corrected": corrected_correlation(float(correlation), reliability),
                }
            )
    return pd.DataFrame(correlation_rows, columns=PERIOD_COLUMNS)


def direct_period_correlations(
    direct_scores_df: pd.DataFrame, trends_df: pd.DataFrame, panel_df: pd.DataFrame, score_columns: list[str], labeled: pd.Index
) -> pd.DataFrame:
    """The headline computation with direct scores, for periods lying inside one coding block. Diagnostic only."""
    all_periods = {era_validation.period_key(column) for column in era_validation.discover_period_columns(trends_df)}
    block_frames = []
    for coding_block, (first_year, last_year, _) in CODING_BLOCKS.items():
        block_periods = {
            period for period in all_periods if first_year <= int(period.split("_")[0]) and int(period.split("_")[1]) <= last_year
        }
        block_scores_df = direct_scores_df[direct_scores_df["coding_block"] == coding_block]
        if block_periods and not block_scores_df.empty:
            block_frames.append(
                detailed_period_correlations(block_scores_df, trends_df, panel_df, score_columns, labeled, periods=block_periods)
            )
    return pd.concat(block_frames, ignore_index=True) if block_frames else pd.DataFrame(columns=PERIOD_COLUMNS)


def run_views(period_df: pd.DataFrame, fixed_period_df: pd.DataFrame, direct_period_df: pd.DataFrame | None) -> dict[str, pd.DataFrame]:
    """The five pre-specified views of the detailed-level result."""
    headline_df = period_df[~period_df["is_seam"]]
    views = {
        "headline": headline_df,
        "noise_corrected": headline_df.assign(fit_r=headline_df["fit_r_corrected"]).dropna(subset=["fit_r"]),
        "seams_included": period_df,
        "fixed_set": fixed_period_df[~fixed_period_df["is_seam"]],
    }
    if direct_period_df is not None and not direct_period_df.empty:
        views["direct_scores_diagnostic"] = direct_period_df[~direct_period_df["is_seam"]]
    return views


def summarise_views(views: dict[str, pd.DataFrame], unemployment_change: pd.Series | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Era comparison and cycle decomposition for every view, each row labelled with its view."""
    era_frames, cycle_frames = [], []
    for view_name, view_df in views.items():
        if view_df.empty:
            continue
        era_frames.append(era_validation.summarise_eras(view_df).assign(run=view_name))
        if unemployment_change is not None:
            cycle_frames.append(era_validation.decompose_fit_strength(view_df, unemployment_change).assign(run=view_name))
    era_df = pd.concat(era_frames, ignore_index=True) if era_frames else pd.DataFrame()
    cycle_df = pd.concat(cycle_frames, ignore_index=True) if cycle_frames else pd.DataFrame()
    for summary_df in (era_df, cycle_df):
        if "run" in summary_df.columns:
            summary_df.insert(0, "run", summary_df.pop("run"))
    return era_df, cycle_df


def _cutoff_label(cutoff: float | None) -> str:
    return "none" if cutoff is None else f"{cutoff:.2f}"


def eligibility_sweep(
    unit_scores_df: pd.DataFrame,
    trends_df: pd.DataFrame,
    panel_df: pd.DataFrame,
    score_columns: list[str],
    labeled: pd.Index,
    fixed_period_df: pd.DataFrame,
) -> pd.DataFrame:
    """The headline era comparison at every pinned cutoff, plus the fixed-set run, with mean units per era."""
    sweep_inputs = [
        (_cutoff_label(cutoff), detailed_period_correlations(unit_scores_df, trends_df, panel_df, score_columns, labeled, cutoff=cutoff))
        for cutoff in SWEEP_CUTOFFS
    ]
    sweep_inputs.append((f"fixed_{RSE_CUTOFF:.2f}", fixed_period_df))
    sweep_frames = []
    for cutoff_label, period_df in sweep_inputs:
        headline_df = period_df[~period_df["is_seam"]]
        if headline_df.empty:
            continue
        mean_units = headline_df[~headline_df["is_covid"]].groupby(["score", "era"])["n_units"].mean().rename("mean_n_units")
        era_df = era_validation.summarise_eras(headline_df).merge(mean_units.reset_index(), on=["score", "era"], how="left")
        era_df.insert(0, "cutoff", cutoff_label)
        sweep_frames.append(era_df)
    return pd.concat(sweep_frames, ignore_index=True) if sweep_frames else pd.DataFrame()


def _write(frame: pd.DataFrame, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    frame.to_csv(path, index=False)
    print(f"  ✓ {path}")


def run_detailed_level(
    unit_scores_df: pd.DataFrame,
    direct_scores_df: pd.DataFrame | None,
    panel_df: pd.DataFrame,
    trends_df: pd.DataFrame,
    score_columns: list[str],
    output_dir: str,
) -> pd.DataFrame:
    """Every pre-specified view at detailed level: period rows, era and cycle summaries, the sweep, the chart."""
    print("\n── Demand composition model, CPS detailed-occupation level (occ1990dd, 1983–2026) ──")
    labeled = labeled_units(unit_scores_df)
    period_df = detailed_period_correlations(unit_scores_df, trends_df, panel_df, score_columns, labeled)
    fixed_period_df = detailed_period_correlations(
        unit_scores_df,
        trends_df,
        panel_df,
        score_columns,
        labeled,
        fixed_units=fixed_set_units(relative_standard_errors(panel_df), RSE_CUTOFF),
    )
    direct_period_df = (
        direct_period_correlations(direct_scores_df, trends_df, panel_df, score_columns, labeled) if direct_scores_df is not None else None
    )
    views = run_views(period_df, fixed_period_df, direct_period_df)

    _write(pd.concat([view_df.assign(run=view_name) for view_name, view_df in views.items()], ignore_index=True), PERIOD_OUTPUT_PATH)
    unemployment_change = era_validation.unemployment_change_by_period(sorted(period_df["period"].unique()))
    era_df, cycle_df = summarise_views(views, unemployment_change)
    _write(era_df, ERA_OUTPUT_PATH)
    if not cycle_df.empty:
        _write(cycle_df, CYCLE_OUTPUT_PATH)

    for view_name in ("headline", "noise_corrected"):
        print(f"\n  View: {view_name}")
        era_validation.print_era_summary(era_df[era_df["run"] == view_name].drop(columns="run"))
    undefined_count = int(period_df["fit_r_corrected"].isna().sum())
    print(f"  {undefined_count} period/score rows have undefined corrected r (reliability ≤ 0 or |corrected r| ≥ 1).")
    if not cycle_df.empty:
        era_validation.print_cycle_decomposition(cycle_df[cycle_df["run"] == "headline"].drop(columns="run"))

    _write(eligibility_sweep(unit_scores_df, trends_df, panel_df, score_columns, labeled, fixed_period_df), SWEEP_OUTPUT_PATH)
    era_validation.plot_signal_over_time(views["headline"], output_dir, level="cps_detailed")
    return era_df
