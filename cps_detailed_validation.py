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
import warnings

import numpy as np
import pandas as pd
from scipy import stats

import composition_era_validation as era_validation
from analyze_bls import attach_growth_columns
from composition_displacement_validation import soc_major_to_dws_group
from cps_detailed_measurement import (
    HEADLINE_EXCLUDED_SEAM_PERIODS,
    HEADLINE_UNIVERSE,
    SEAM_PERIODS,
    build_detailed_trends,
    eligible_for_period,
    fixed_set_units,
    load_detailed_panel,
    measure_vintage_seams,
    period_reliability,
    relative_standard_errors,
    reliability_for_units,
)
from cps_detailed_panel import CODING_BLOCKS, CROSSTAB_SEED_PATH, SEED_PATH
from cps_historical_panel import compare_with_oews
from occ1990dd_soc_bridge import (
    COMPOSITION_REPORT_PATH,
    DISPLACEMENT_SCORE_COLUMNS,
    bridge_check,
    build_bridge_weights,
    census_scores_by_block,
    direct_unit_scores,
    g4_passed,
    load_anchor_employment,
    load_soc_scores,
    load_soc_tables,
    occ1990dd_composition_stability,
    score_units,
)

RSE_CUTOFF = 0.20
SWEEP_CUTOFFS = (0.10, 0.20, 0.30, None)
MINIMUM_LABELED_SHARE = 0.8

PERIOD_OUTPUT_PATH = "data/output/cps_detailed_period_correlations.csv"
ERA_OUTPUT_PATH = "data/output/composition_model_era_comparison_cps_detailed.csv"
CYCLE_OUTPUT_PATH = "data/output/composition_cycle_decomposition_cps_detailed.csv"
SWEEP_OUTPUT_PATH = "data/output/cps_detailed_eligibility_sweep.csv"
PANEL_OUTPUT_PATH = "data/output/cps_detailed_occupation_panel.csv"
TRENDS_OUTPUT_PATH = "data/output/cps_detailed_trends.csv"
RELIABILITY_OUTPUT_PATH = "data/output/cps_detailed_reliability.csv"
SEAM_BREAKS_OUTPUT_PATH = "data/output/cps_detailed_seam_breaks.csv"
UNIT_SCORES_OUTPUT_PATH = "data/output/occ1990dd_scores.csv"
STABILITY_OUTPUT_PATH = "data/output/occ1990dd_composition_stability.csv"
BRIDGE_CHECK_OUTPUT_PATH = "data/output/occ1990dd_bridge_check.csv"
OCCUPATION_TRENDS_PATH = "data/output/bls_trends.csv"

PERIOD_COLUMNS = ["period", "score", "fit_r", "fit_p", "n_units", "era", "is_covid", "is_seam", "reliability", "fit_r_corrected"]

# This run's gate G4 verdict, set every time run() executes (including every early-return path)
# so a caller — dws_detailed_validation.run(g4_passed_this_run=...) in particular — never acts on
# a stale on-disk occ1990dd_bridge_check.csv left over from an earlier, different run. None means
# "this run never reached the G4 check" (an earlier warning already explains why).
LAST_RUN_G4_PASSED: bool | None = None


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


ROLLUP_TRENDS_OUTPUT_PATH = "data/output/cps_major_rollup_trends.csv"
MAJOR_ERA_OUTPUT_PATH = "data/output/composition_model_era_comparison_cps_major.csv"
MAJOR_CYCLE_OUTPUT_PATH = "data/output/composition_cycle_decomposition_cps_major.csv"
MAJOR_OEWS_AGREEMENT_OUTPUT_PATH = "data/output/cps_major_oews_agreement.csv"
PUBLISHED_AGREEMENT_OUTPUT_PATH = "data/output/cps_detailed_published_agreement.csv"
PUBLISHED_TEN_GROUP_PANEL_PATH = "seeds/cps_occupation_panel.csv"
SECTOR_TRENDS_PATH = "data/output/bls_sector_trends.csv"
# The ten-group level's 8-of-10 convention, at 22.
MINIMUM_ROLLUP_MAJORS = 20


def rollup_to_majors(panel_df: pd.DataFrame, bridge_weights_df: pd.DataFrame, universe: str = HEADLINE_UNIVERSE) -> pd.DataFrame:
    """Allocate each occ1990dd unit's employment to SOC major groups by its bridge weights.

    Uses every SOC constituent, labeled or not — employment allocation needs no
    demand-type label. Units the chain does not reach drop out; run_major_level
    prints how much employment that costs.
    """
    major_weights_df = (
        bridge_weights_df.assign(soc_major=bridge_weights_df["soc_2018_code"].str[:2])
        .groupby(["occ1990dd", "soc_major"], as_index=False)["weight"]
        .sum()
    )
    universe_df = panel_df.loc[panel_df["universe"] == universe, ["year", "occ1990dd", "employed_thousands"]]
    allocated_df = universe_df.merge(major_weights_df, on="occ1990dd", how="inner")
    allocated_df["employed_thousands"] = allocated_df["employed_thousands"] * allocated_df["weight"]
    return allocated_df.groupby(["year", "soc_major"], as_index=False)["employed_thousands"].sum()


def build_rollup_trends(rollup_df: pd.DataFrame) -> pd.DataFrame:
    """The rollup in bls_sector_trends.csv's layout, keyed by soc_major."""
    wide_df = rollup_df.pivot(index="soc_major", columns="year", values="employed_thousands")
    available_years = [str(int(year)) for year in sorted(wide_df.columns)]
    wide_df = wide_df[sorted(wide_df.columns)]
    wide_df.columns = [f"TOT_EMP_{year}" for year in available_years]
    return attach_growth_columns(wide_df.reset_index(), available_years)


def major_scores(scored_df: pd.DataFrame, employment_column: str, score_columns: list[str]) -> pd.DataFrame:
    """Employment-weighted mean score per SOC major, as cps_group_correlation aggregates to the ten groups."""
    base_df = scored_df.dropna(subset=[employment_column]).assign(soc_major=scored_df["OCC_CODE"].astype(str).str[:2])
    score_frames = []
    for score_column in score_columns:
        scored_rows_df = base_df.dropna(subset=[score_column])
        weighted = (scored_rows_df[score_column] * scored_rows_df[employment_column]).groupby(scored_rows_df["soc_major"]).sum()
        score_frames.append((weighted / scored_rows_df.groupby("soc_major")[employment_column].sum()).rename(score_column))
    return pd.concat(score_frames, axis=1).reset_index()


def major_period_correlations(major_scores_df: pd.DataFrame, rollup_trends_df: pd.DataFrame, score_columns: list[str]) -> pd.DataFrame:
    """Pearson r per (period, score) across SOC majors — the sector specification, seams flagged but kept."""
    correlation_rows = []
    for growth_column in era_validation.discover_period_columns(rollup_trends_df):
        period = era_validation.period_key(growth_column)
        for score_column in score_columns:
            paired_df = (
                major_scores_df[["soc_major", score_column]].merge(rollup_trends_df[["soc_major", growth_column]], on="soc_major").dropna()
            )
            if len(paired_df) < MINIMUM_ROLLUP_MAJORS or paired_df[score_column].nunique() < 2 or paired_df[growth_column].nunique() < 2:
                continue
            correlation, p_value = stats.pearsonr(paired_df[score_column], paired_df[growth_column])
            correlation_rows.append(
                {
                    "period": period,
                    "score": score_column,
                    "fit_r": float(correlation),
                    "fit_p": float(p_value),
                    "n_units": len(paired_df),
                    "era": "ai" if era_validation.is_ai_era(growth_column) else "pre_ai",
                    "is_covid": period in era_validation.COVID_PERIODS,
                    "is_seam": period in SEAM_PERIODS,
                }
            )
    return pd.DataFrame(correlation_rows, columns=["period", "score", "fit_r", "fit_p", "n_units", "era", "is_covid", "is_seam"])


def oews_major_agreement(wage_salary_trends_df: pd.DataFrame, sector_trends_df: pd.DataFrame) -> pd.DataFrame:
    """Rollup (wage and salary) against OEWS sector growth, 1999–2025. Reported, never reconciled (Phase 1 D3)."""
    renamed_df = wage_salary_trends_df.rename(columns={"soc_major": "cps_group"})
    identity_lookup = {major: major for major in renamed_df["cps_group"]}
    return compare_with_oews(renamed_df, sector_trends_df, identity_lookup).rename(columns={"cps_group": "soc_major"})


def published_ten_group_agreement(rollup_df: pd.DataFrame, published_panel_df: pd.DataFrame) -> pd.DataFrame:
    """Rollup summed to the ten Phase 1 groups against the published series, every year. Reported only."""
    group_lookup = soc_major_to_dws_group()
    grouped_df = (
        rollup_df.assign(cps_group=rollup_df["soc_major"].map(group_lookup))
        .dropna(subset=["cps_group"])
        .groupby(["year", "cps_group"], as_index=False)["employed_thousands"]
        .sum()
        .rename(columns={"employed_thousands": "rollup_thousands"})
    )
    published_df = published_panel_df.rename(columns={"employed_thousands": "published_thousands"})[
        ["year", "cps_group", "published_thousands"]
    ]
    agreement_df = grouped_df.merge(published_df, on=["year", "cps_group"], how="inner")
    agreement_df["relative_difference"] = agreement_df["rollup_thousands"] / agreement_df["published_thousands"] - 1
    agreement_df["segment"] = np.select(
        [agreement_df["year"] <= 1999, agreement_df["year"] <= 2002], ["reconstruction_1983_1999", "bridge_2000_2002"], "published_2003_on"
    )
    return agreement_df


def _print_seam_summary(seam_df: pd.DataFrame) -> None:
    absolute_growth = seam_df.assign(absolute_growth=seam_df["emp_growth"].abs()).dropna(subset=["absolute_growth"])
    ordinary_growth = absolute_growth.loc[~absolute_growth["is_seam_period"], "absolute_growth"]
    print(f"  Ordinary periods: median |growth| {ordinary_growth.median():.4f}, 95th percentile {ordinary_growth.quantile(0.95):.4f}")
    for period, period_df in absolute_growth[absolute_growth["is_seam_period"]].groupby("period"):
        print(f"  Seam {period}: median |growth| {period_df['absolute_growth'].median():.4f}, max {period_df['absolute_growth'].max():.4f}")


def run_major_level(panel_df: pd.DataFrame, bridge_weights_df: pd.DataFrame, output_dir: str) -> pd.DataFrame | None:
    """The 22-major rollup: trends, era and cycle tests, chart, and both agreement reports."""
    print("\n── Demand composition model, CPS 22-SOC-major rollup (1983–2026) ──")
    rollup_df = rollup_to_majors(panel_df, bridge_weights_df)
    universe_totals = panel_df[panel_df["universe"] == HEADLINE_UNIVERSE].groupby("year")["employed_thousands"].sum()
    coverage = rollup_df.groupby("year")["employed_thousands"].sum() / universe_totals
    print(f"  Employment the chain reaches: {coverage.min():.4f}-{coverage.max():.4f} of the panel, by year")
    rollup_trends_df = build_rollup_trends(rollup_df)
    _write(rollup_trends_df, ROLLUP_TRENDS_OUTPUT_PATH)

    scored_df, employment_column, _, score_columns = era_validation.load_scored_occupations()
    period_df = major_period_correlations(major_scores(scored_df, employment_column, score_columns), rollup_trends_df, score_columns)
    if period_df.empty:
        print("  ⚠ No 22-major period correlations could be computed.")
        return None
    era_df = era_validation.summarise_eras(period_df)
    _write(era_df, MAJOR_ERA_OUTPUT_PATH)
    era_validation.print_era_summary(era_df)
    unemployment_change = era_validation.unemployment_change_by_period(sorted(period_df["period"].unique()))
    if unemployment_change is not None:
        cycle_df = era_validation.decompose_fit_strength(period_df, unemployment_change)
        _write(cycle_df, MAJOR_CYCLE_OUTPUT_PATH)
        era_validation.print_cycle_decomposition(cycle_df)
    era_validation.plot_signal_over_time(period_df, output_dir, level="cps_major")

    if os.path.exists(SECTOR_TRENDS_PATH):
        wage_salary_trends_df = build_rollup_trends(rollup_to_majors(panel_df, bridge_weights_df, "wage_salary"))
        agreement_df = oews_major_agreement(wage_salary_trends_df, pd.read_csv(SECTOR_TRENDS_PATH, dtype={"soc_major": str}))
        _write(agreement_df, MAJOR_OEWS_AGREEMENT_OUTPUT_PATH)
        if len(agreement_df) > 2:
            agreement_r = stats.pearsonr(agreement_df["cps_growth"], agreement_df["oews_growth"])[0]
            print(f"  Rollup vs OEWS sector growth (wage and salary): r = {agreement_r:+.3f}, n = {len(agreement_df)}")
            print("  Reported, never reconciled (Phase 1 D3).")
    _write(published_ten_group_agreement(rollup_df, pd.read_csv(PUBLISHED_TEN_GROUP_PANEL_PATH)), PUBLISHED_AGREEMENT_OUTPUT_PATH)
    return era_df


def run(
    output_dir: str = "data/output/visualizations", seed_path: str = SEED_PATH, crosstab_seed_path: str = CROSSTAB_SEED_PATH
) -> pd.DataFrame | None:
    """Phase 2 pipeline entry: measurement tables, bridge scores, gate G4, then both detailed levels.

    A missing seed warns and skips, like every other seed-backed instrument here.
    A failed G4 still writes the bridge check but withholds every detailed-level
    and rollup result: a result resting on an unfit bridge is not published.

    Sets the module-level `LAST_RUN_G4_PASSED` on every path (True, False, or None if this run
    never reached the G4 check), so a caller can tell `dws_detailed_validation.run()` this run's
    verdict rather than letting it trust a possibly-stale `occ1990dd_bridge_check.csv` from an
    earlier run.
    """
    global LAST_RUN_G4_PASSED
    LAST_RUN_G4_PASSED = None
    panel_df = load_detailed_panel(seed_path)
    if panel_df is None:
        warnings.warn(
            f"{seed_path} absent — it is built locally from IPUMS microdata (cps_detailed_panel.py); detailed CPS levels skipped",
            stacklevel=2,
        )
        return None
    if not os.path.exists(COMPOSITION_REPORT_PATH):
        warnings.warn(f"{COMPOSITION_REPORT_PATH} absent; run the composition stage first — detailed CPS levels skipped", stacklevel=2)
        return None

    print("\n── CPS detailed-occupation panel (IPUMS, occ1990dd) ──")
    _write(panel_df, PANEL_OUTPUT_PATH)
    trends_df = build_detailed_trends(panel_df)
    _write(trends_df, TRENDS_OUTPUT_PATH)
    reliability_df = period_reliability(panel_df, trends_df)
    _write(reliability_df, RELIABILITY_OUTPUT_PATH)
    print(
        f"  Reliability of year-over-year growth: median {reliability_df['reliability'].median():.3f} across {len(reliability_df)} periods"
    )
    seam_df = measure_vintage_seams(trends_df)
    _write(seam_df, SEAM_BREAKS_OUTPUT_PATH)
    _print_seam_summary(seam_df)

    soc_scores_df, score_columns = load_soc_scores()
    anchor_employment = load_anchor_employment()
    soc_tables = load_soc_tables()
    bridge_weights_df = build_bridge_weights(anchor_employment, soc_tables)
    unit_scores_df = score_units(bridge_weights_df, "occ1990dd", soc_scores_df, score_columns + DISPLACEMENT_SCORE_COLUMNS)
    _write(unit_scores_df, UNIT_SCORES_OUTPUT_PATH)
    _write(occ1990dd_composition_stability(bridge_weights_df, pd.read_csv(OCCUPATION_TRENDS_PATH)), STABILITY_OUTPUT_PATH)

    if not os.path.exists(crosstab_seed_path):
        warnings.warn(f"{crosstab_seed_path} absent, so gate G4 cannot run — detailed CPS levels withheld", stacklevel=2)
        return None
    direct_scores_df = direct_unit_scores(
        pd.read_csv(crosstab_seed_path), census_scores_by_block(soc_scores_df, score_columns, anchor_employment, soc_tables), score_columns
    )
    check_df = bridge_check(unit_scores_df, direct_scores_df)
    _write(check_df, BRIDGE_CHECK_OUTPUT_PATH)
    for coding_block, block_r in check_df.groupby("coding_block")["block_pearson_r"].first().items():
        print(f"  G4 {coding_block}: chained vs direct r = {block_r:+.3f}")
    LAST_RUN_G4_PASSED = g4_passed(check_df)
    if not LAST_RUN_G4_PASSED:
        warnings.warn(
            "Gate G4 failed: the chained bridge does not track direct Census-code scoring in every coding block. "
            "Detailed-level and 22-major results are withheld; the design returns for review.",
            stacklevel=2,
        )
        return None

    era_df = run_detailed_level(unit_scores_df, direct_scores_df, panel_df, trends_df, score_columns, output_dir)
    run_major_level(panel_df, bridge_weights_df, output_dir)
    return era_df
