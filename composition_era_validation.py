"""
composition_era_validation.py
─────────────────────────────
The headline test of the demand composition model: is the Bounded/Unbounded/
Adversarial signal era-invariant, or does it only appear after AI?

Runs the sector-level validation for every year-over-year period 2005→2025 for
four scores side by side, then compares the pre-2022 and AI-era means:

  composition_net_change   demand composition only — no technology data at all
  net_employment_change    the AI-penetration dynamic model
  occupation_exposure      the rebound-adjusted model
  observed_exposure        Anthropic observed task coverage, when available

Inputs:
  • data/output/occupation_composition_model_report.csv
  • data/output/occupation_dynamic_model_report.csv
  • data/output/bls_trends.csv
  • data/output/bls_sector_trends.csv
  • data/raw/anthropic_job_exposure.csv  (optional)

Outputs:
  • data/output/composition_model_era_comparison.csv
  • data/output/visualizations/composition_model_signal_over_time.png

How to read the result
──────────────────────
docs/model_vs_observed_exposure.md § "Confound: pre-existing sector composition"
records that the AI model's sector-level r was already +0.40 to +0.50 in 2006-09
and files that as a threat to AI attribution. This module tests the opposite
reading. Three outcomes, all publishable:

  • composition-only fits the pre-AI era as well as the AI era → the taxonomy is
    a general theory of productivity-shock pass-through, and AI is one instance.
  • the AI model pulls ahead only after 2022 → there is a real, separable
    AI-specific increment on top of the general effect.
  • the AI model never pulls ahead → the AI-specific claim is weak and the honest
    headline is that this was always a general theory.

Two caveats that bound every number here
─────────────────────────────────────────
**The demand-type labels are from 2025 O*NET task statements, applied
backwards.** docs/framework.md already flags this. Occupational task content
genuinely changed over 2005-2025, so the further back a period sits, the more
anachronistic its labels. Reaching further back buys statistical power at the
cost of construct validity.

**The era test is badly under-powered on the AI side.** There are only three
AI-era YoY periods against sixteen pre-AI ones, and the periods are
autocorrelated, so the Welch test on Fisher-z transformed correlations reported
here should be read as a descriptive comparison rather than an inferential
result. A non-significant difference is the expected outcome either way and is
not evidence of equivalence.

Sector growth always comes from the major-group totals in bls_sector_trends.csv
via sector_growth_series, never from the survivor occupations — detailed
pre-2019 codes lose 97% of Computer and Mathematical employment, per CLAUDE.md.
"""

import os
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.stats as stats
import seaborn as sns

# _sector_weighted_means is imported rather than reimplemented so this module and
# every existing sector-level chart aggregate identically. Duplicating it would
# let the two drift and report different numbers for the same quantity.
from synthesize_dynamic import _sector_weighted_means

COMPOSITION_REPORT_PATH = "data/output/occupation_composition_model_report.csv"
DYNAMIC_REPORT_PATH = "data/output/occupation_dynamic_model_report.csv"
BLS_TRENDS_PATH = "data/output/bls_trends.csv"
SECTOR_TRENDS_PATH = "data/output/bls_sector_trends.csv"
ANTHROPIC_EXPOSURE_PATH = "data/raw/anthropic_job_exposure.csv"

OUTPUT_PATH = "data/output/composition_model_era_comparison.csv"
CHART_NAME = "composition_model_signal_over_time.png"

COMPOSITION_SCORE_COLUMN = "composition_net_change"

# Sign convention differs by score: the gross exposure measures validate with
# negative r (more exposure → less growth) while the redistribution models
# validate with positive r (more net change → more growth).
SCORE_CONFIGS: list[tuple[str, str, str, str]] = [
    (COMPOSITION_SCORE_COLUMN, "Demand composition only (+r = correct)", "#6a51a3", "D"),
    ("net_employment_change", "Dynamic, AI penetration (+r = correct)", "darkorange", "s"),
    ("occupation_exposure", "Rebound-adjusted (−r = correct)", "steelblue", "o"),
    ("observed_exposure", "Observed AI coverage (−r = correct)", "seagreen", "^"),
]

# Periods whose later year is <= 22 carry the hist_ prefix; see analyze_bls.py.
AI_ERA_FIRST_PERIOD = "22_23"

MINIMUM_SECTORS = 5
MINIMUM_OCCUPATIONS = 10

COVID_PERIODS = ("19_20", "20_21")

OUTPUT_COLUMNS = [
    "score",
    "era",
    "n_periods",
    "mean_r",
    "min_r",
    "max_r",
    "n_significant",
    "era_difference_r",
    "welch_t",
    "welch_p",
]


def period_key(growth_column: str) -> str:
    """Strip the prefix from a growth column, leaving e.g. '18_19'."""
    return growth_column.replace("hist_emp_growth_", "").replace("emp_growth_", "")


def _period_sort_key(growth_column: str) -> tuple[int, int]:
    key = period_key(growth_column)
    if key in ("composite", "pre_ai"):
        return (99, 0)
    start_year, end_year = key.split("_")
    return (int(start_year), int(end_year))


def discover_period_columns(trends_df: pd.DataFrame) -> list[str]:
    """Every year-over-year employment growth column, chronologically.

    Excludes the composite and pre_ai aggregates, which span many years and would
    not be a period in the series.
    """
    historical_columns = [column for column in trends_df.columns if column.startswith("hist_emp_growth_") and "_pre_ai" not in column]
    current_columns = [column for column in trends_df.columns if column.startswith("emp_growth_") and "composite" not in column]
    return sorted(historical_columns, key=_period_sort_key) + sorted(current_columns, key=_period_sort_key)


def is_ai_era(growth_column: str) -> bool:
    """True for periods from 2022→23 onward."""
    return _period_sort_key(growth_column) >= _period_sort_key(f"emp_growth_{AI_ERA_FIRST_PERIOD}")


def load_scored_occupations() -> tuple[pd.DataFrame, str, pd.DataFrame | None, list[str]]:
    """Join every model score onto the BLS trend series, keyed by SOC code.

    Returns the joined frame, the latest employment column, the sector growth
    table, and the score columns actually present.
    """
    composition_df = pd.read_csv(COMPOSITION_REPORT_PATH)
    dynamic_df = pd.read_csv(DYNAMIC_REPORT_PATH)
    trends_df = pd.read_csv(BLS_TRENDS_PATH)

    scored_df = composition_df[["OCC_CODE", "net_employment_change"]].rename(columns={"net_employment_change": COMPOSITION_SCORE_COLUMN})
    scored_df = scored_df.merge(
        dynamic_df[["OCC_CODE", "net_employment_change", "occupation_exposure"]],
        on="OCC_CODE",
        how="outer",
        validate="one_to_one",
    )

    if os.path.exists(ANTHROPIC_EXPOSURE_PATH):
        anthropic_df = pd.read_csv(ANTHROPIC_EXPOSURE_PATH)
        if "occ_code" in anthropic_df.columns:
            anthropic_df = anthropic_df.rename(columns={"occ_code": "OCC_CODE"})
        if "observed_exposure" in anthropic_df.columns:
            observed_df = anthropic_df[["OCC_CODE", "observed_exposure"]].drop_duplicates(subset=["OCC_CODE"])
            scored_df = scored_df.merge(observed_df, on="OCC_CODE", how="left")

    scored_df = scored_df.merge(trends_df, on="OCC_CODE", how="inner")
    scored_df["soc_major"] = scored_df["OCC_CODE"].astype(str).str[:2]

    employment_col = sorted(column for column in scored_df.columns if column.startswith("TOT_EMP_"))[-1]

    sector_growth_df = None
    if os.path.exists(SECTOR_TRENDS_PATH):
        sector_growth_df = pd.read_csv(SECTOR_TRENDS_PATH, dtype={"soc_major": str}).set_index("soc_major")

    present_score_columns = [score_col for score_col, _, _, _ in SCORE_CONFIGS if score_col in scored_df.columns]
    return scored_df, employment_col, sector_growth_df, present_score_columns


def sector_correlation(
    scored_df: pd.DataFrame,
    score_col: str,
    growth_col: str,
    employment_col: str,
    sector_growth_df: pd.DataFrame | None,
) -> tuple[float, float, int] | None:
    """Sector-level Pearson r between one score and one period's growth, or None if too thin."""
    subset_df = scored_df[[score_col, growth_col, "soc_major", employment_col]].dropna()
    if len(subset_df) < MINIMUM_OCCUPATIONS:
        return None

    sector_means_df = _sector_weighted_means(subset_df, score_col, growth_col, employment_col, "soc_major", sector_growth_df)
    if len(sector_means_df) < MINIMUM_SECTORS:
        return None

    correlation, p_value = stats.pearsonr(sector_means_df["sector_score"], sector_means_df["sector_growth"])
    return correlation, p_value, len(sector_means_df)


def build_period_correlations(
    scored_df: pd.DataFrame,
    employment_col: str,
    sector_growth_df: pd.DataFrame | None,
    score_columns: list[str],
) -> pd.DataFrame:
    """One row per (period, score) with the sector-level r, p and sector count."""
    correlation_rows = []
    for growth_col in discover_period_columns(scored_df):
        for score_col in score_columns:
            result = sector_correlation(scored_df, score_col, growth_col, employment_col, sector_growth_df)
            if result is None:
                continue
            correlation, p_value, n_sectors = result
            correlation_rows.append(
                {
                    "period": period_key(growth_col),
                    "score": score_col,
                    "sector_r": correlation,
                    "sector_p": p_value,
                    "n_sectors": n_sectors,
                    "era": "ai" if is_ai_era(growth_col) else "pre_ai",
                    "is_covid": period_key(growth_col) in COVID_PERIODS,
                }
            )
    return pd.DataFrame(correlation_rows)


def summarise_eras(period_correlation_df: pd.DataFrame, exclude_covid: bool = True) -> pd.DataFrame:
    """Compare pre-2022 and AI-era correlations per score.

    Correlations are Fisher z-transformed before averaging and testing, because r
    is bounded and its sampling distribution is skewed. The Welch test does not
    assume equal variances, which matters when one era has 16 periods and the
    other 3.

    COVID periods are excluded by default: 2019→20 and 2020→21 are dominated by
    shutdown and rehiring, not by any displacement mechanism this model describes.
    """
    comparison_df = period_correlation_df[~period_correlation_df["is_covid"]] if exclude_covid else period_correlation_df

    summary_rows = []
    for score_col in comparison_df["score"].unique():
        score_df = comparison_df[comparison_df["score"] == score_col]
        pre_ai_r = score_df.loc[score_df["era"] == "pre_ai", "sector_r"]
        ai_era_r = score_df.loc[score_df["era"] == "ai", "sector_r"]

        era_difference = welch_t = welch_p = np.nan
        if len(pre_ai_r) >= 2 and len(ai_era_r) >= 2:
            pre_ai_z, ai_era_z = np.arctanh(pre_ai_r), np.arctanh(ai_era_r)
            welch_t, welch_p = stats.ttest_ind(ai_era_z, pre_ai_z, equal_var=False)
            era_difference = float(np.tanh(ai_era_z.mean()) - np.tanh(pre_ai_z.mean()))

        for era_name, era_r in (("pre_ai", pre_ai_r), ("ai", ai_era_r)):
            if era_r.empty:
                continue
            era_p = score_df.loc[score_df["era"] == era_name, "sector_p"]
            summary_rows.append(
                {
                    "score": score_col,
                    "era": era_name,
                    "n_periods": len(era_r),
                    # Averaged in z space then transformed back, not averaged in r space.
                    "mean_r": float(np.tanh(np.arctanh(era_r).mean())),
                    "min_r": float(era_r.min()),
                    "max_r": float(era_r.max()),
                    "n_significant": int((era_p < 0.05).sum()),
                    "era_difference_r": era_difference,
                    "welch_t": float(welch_t) if not np.isnan(welch_t) else np.nan,
                    "welch_p": float(welch_p) if not np.isnan(welch_p) else np.nan,
                }
            )

    return pd.DataFrame(summary_rows)[OUTPUT_COLUMNS]


UNEMPLOYMENT_SERIES_ID = "LNS14000000"

CYCLE_OUTPUT_PATH = "data/output/composition_cycle_decomposition.csv"
CYCLE_OUTPUT_COLUMNS = ["score", "term", "coefficient", "std_error", "t_statistic", "p_value", "n_periods", "r_squared"]


def unemployment_change_by_period(period_keys: list[str]) -> pd.Series | None:
    """Change in the annual mean unemployment rate across each period, e.g. '07_08' → +1.18."""
    from historical_displacement import fetch_annual_means

    unemployment_rate = fetch_annual_means(UNEMPLOYMENT_SERIES_ID, 2005, 2026)
    if unemployment_rate is None:
        return None

    change_by_period = {}
    for key in period_keys:
        start_year, end_year = (2000 + int(part) for part in key.split("_"))
        if start_year in unemployment_rate.index and end_year in unemployment_rate.index:
            change_by_period[key] = unemployment_rate[end_year] - unemployment_rate[start_year]
    return pd.Series(change_by_period, name="unemployment_change")


def decompose_fit_strength(
    period_correlation_df: pd.DataFrame,
    unemployment_change: pd.Series,
    exclude_covid: bool = True,
) -> pd.DataFrame:
    """Regress each model's per-period fit strength on the business cycle and an AI-era dummy.

    The era comparison on its own cannot separate two explanations of a pre-AI
    signal: that the taxonomy describes a general mechanism, or that it is picking
    up cyclical sorting — Bounded and clerical work is shed in downturns and
    rehired in recoveries, which docs/framework.md § "Future investigation: the
    business cycle" already suspected.

    Regressing Fisher-z fit strength on the change in unemployment plus an AI-era
    indicator separates them:

      intercept    the taxonomy's signal at zero cyclical movement — a general,
                   non-cyclical baseline if it is positive
      change in U  how much of the fit is cyclical sorting
      AI era       whatever remains specific to 2022 onward once the cycle is
                   accounted for

    COVID periods are excluded by default; they are shutdown and rehiring rather
    than any mechanism the model describes, and they dominate the cycle term.
    """
    comparison_df = period_correlation_df[~period_correlation_df["is_covid"]] if exclude_covid else period_correlation_df

    coefficient_rows = []
    for score_col in comparison_df["score"].unique():
        score_df = comparison_df[comparison_df["score"] == score_col].copy()
        score_df["unemployment_change"] = score_df["period"].map(unemployment_change)
        score_df = score_df.dropna(subset=["unemployment_change", "sector_r"])

        term_names = ["intercept", "unemployment_change", "ai_era"]
        if len(score_df) <= len(term_names):
            continue

        fit_strength = np.arctanh(score_df["sector_r"].to_numpy())
        design_matrix = np.column_stack(
            [
                np.ones(len(score_df)),
                score_df["unemployment_change"].to_numpy(),
                (score_df["era"] == "ai").astype(float).to_numpy(),
            ]
        )

        # With every period in one era the AI-era column is constant and the normal
        # equations are singular, which would raise rather than degrade. That happens
        # for real whenever the trend series has not reached 2022 yet.
        if np.linalg.matrix_rank(design_matrix) < design_matrix.shape[1]:
            warnings.warn(
                f"Cannot decompose fit strength for {score_col}: the periods do not span both eras "
                f"(or the cycle term is constant), so the AI-era effect is not identified.",
                stacklevel=2,
            )
            continue

        coefficients, *_ = np.linalg.lstsq(design_matrix, fit_strength, rcond=None)
        residuals = fit_strength - design_matrix @ coefficients
        degrees_of_freedom = len(score_df) - design_matrix.shape[1]
        residual_variance = np.sum(residuals**2) / degrees_of_freedom
        standard_errors = np.sqrt(residual_variance * np.diag(np.linalg.inv(design_matrix.T @ design_matrix)))
        t_statistics = coefficients / standard_errors
        p_values = 2 * (1 - stats.t.cdf(np.abs(t_statistics), degrees_of_freedom))
        total_sum_of_squares = np.sum((fit_strength - fit_strength.mean()) ** 2)

        for term_name, coefficient, standard_error, t_statistic, p_value in zip(
            term_names, coefficients, standard_errors, t_statistics, p_values
        ):
            coefficient_rows.append(
                {
                    "score": score_col,
                    "term": term_name,
                    "coefficient": float(coefficient),
                    "std_error": float(standard_error),
                    "t_statistic": float(t_statistic),
                    "p_value": float(p_value),
                    "n_periods": len(score_df),
                    "r_squared": float(1 - np.sum(residuals**2) / total_sum_of_squares),
                }
            )

    return pd.DataFrame(coefficient_rows, columns=CYCLE_OUTPUT_COLUMNS)


def print_cycle_decomposition(cycle_decomposition_df: pd.DataFrame) -> None:
    """Print the cycle-versus-AI-era decomposition of each model's fit strength."""
    print("\n── Fit strength decomposed: general mechanism, business cycle, or AI era? ──")
    for score_col, _, _, _ in SCORE_CONFIGS:
        score_df = cycle_decomposition_df[cycle_decomposition_df["score"] == score_col]
        if score_df.empty:
            continue
        print(f"  {score_col}  (n={int(score_df['n_periods'].iloc[0])} periods, R²={score_df['r_squared'].iloc[0]:.3f})")
        for _, coefficient_row in score_df.iterrows():
            significance = "*" if coefficient_row["p_value"] < 0.05 else " "
            print(
                f"    {coefficient_row['term']:<22}{coefficient_row['coefficient']:+.4f}"
                f"  t={coefficient_row['t_statistic']:+5.2f}  p={coefficient_row['p_value']:.4f} {significance}"
            )


def plot_signal_over_time(period_correlation_df: pd.DataFrame, output_dir: str) -> None:
    """Sector-level r by period for every model, with the AI boundary and COVID marked."""
    ordered_periods = sorted(period_correlation_df["period"].unique(), key=lambda key: _period_sort_key(f"emp_growth_{key}"))
    if len(ordered_periods) < 2:
        return

    sns.set_theme(style="whitegrid")
    figure, axis = plt.subplots(figsize=(15, 5.5))
    period_positions = {period: index for index, period in enumerate(ordered_periods)}

    for period in ordered_periods:
        if period in COVID_PERIODS:
            axis.axvspan(period_positions[period] - 0.4, period_positions[period] + 0.4, alpha=0.12, color="red", zorder=0)

    ai_era_start = next((period_positions[p] for p in ordered_periods if is_ai_era(f"emp_growth_{p}")), None)
    if ai_era_start is not None:
        axis.axvspan(ai_era_start - 0.5, len(ordered_periods) - 0.5, alpha=0.08, color="royalblue", zorder=0)
        axis.axvline(ai_era_start - 0.5, color="royalblue", linestyle="--", linewidth=1.2, alpha=0.7, label="AI era begins (2022→23)")

    axis.axhline(0, color="grey", linewidth=0.8)

    for score_col, label, color, marker in SCORE_CONFIGS:
        score_df = period_correlation_df[period_correlation_df["score"] == score_col]
        if score_df.empty:
            continue
        score_df = score_df.assign(position=score_df["period"].map(period_positions)).sort_values("position")
        axis.plot(
            score_df["position"],
            score_df["sector_r"],
            marker=marker,
            linestyle="-",
            color=color,
            label=label,
            linewidth=1.8 if score_col == COMPOSITION_SCORE_COLUMN else 1.3,
            markersize=6 if score_col == COMPOSITION_SCORE_COLUMN else 5,
            alpha=1.0 if score_col == COMPOSITION_SCORE_COLUMN else 0.75,
            zorder=5 if score_col == COMPOSITION_SCORE_COLUMN else 3,
        )
        significant_df = score_df[score_df["sector_p"] < 0.05]
        axis.scatter(
            significant_df["position"],
            significant_df["sector_r"],
            s=110,
            facecolors="none",
            edgecolors=color,
            linewidths=1.6,
            zorder=6,
        )

    axis.set_xticks(list(period_positions.values()))
    axis.set_xticklabels([f"20{p.split('_')[0]}→\n20{p.split('_')[1]}" for p in ordered_periods], fontsize=8)
    axis.set_ylabel("Sector-level Pearson r vs. employment growth")
    axis.set_title(
        "Is the demand-type signal era-invariant?\n"
        "Sector-level correlation by year-over-year period, n=22 sectors. Ringed markers are p < 0.05.",
        fontsize=11,
    )
    axis.legend(fontsize=8, loc="best", framealpha=0.9)
    figure.text(
        0.5,
        -0.02,
        "Demand-type labels come from 2025 O*NET task statements applied backwards; earlier periods are more anachronistic. "
        "Red bands are COVID periods, excluded from the era comparison.",
        ha="center",
        fontsize=7.5,
        style="italic",
        color="dimgray",
    )

    os.makedirs(output_dir, exist_ok=True)
    figure.savefig(os.path.join(output_dir, CHART_NAME), dpi=150, bbox_inches="tight")
    plt.close(figure)
    print(f"  Saved {os.path.join(output_dir, CHART_NAME)}")


def print_era_summary(era_summary_df: pd.DataFrame) -> None:
    """Print the 2x2 that the model exists to fill in."""
    print("\n── Era comparison: is the demand-type signal era-invariant? ──")
    print(f"  {'score':<26}{'era':<9}{'n':>4}{'mean r':>9}{'range':>18}{'sig':>5}")
    for score_col, _, _, _ in SCORE_CONFIGS:
        score_df = era_summary_df[era_summary_df["score"] == score_col]
        for _, summary_row in score_df.iterrows():
            era_label = "pre-2022" if summary_row["era"] == "pre_ai" else "AI era"
            range_text = f"{summary_row['min_r']:+.3f} to {summary_row['max_r']:+.3f}"
            print(
                f"  {score_col:<26}{era_label:<9}{int(summary_row['n_periods']):>4}"
                f"{summary_row['mean_r']:>+9.3f}{range_text:>18}{int(summary_row['n_significant']):>5}"
            )
        if not score_df.empty and pd.notna(score_df["welch_p"].iloc[0]):
            print(
                f"  {'':<26}difference {score_df['era_difference_r'].iloc[0]:+.3f}  "
                f"Welch t={score_df['welch_t'].iloc[0]:+.2f}, p={score_df['welch_p'].iloc[0]:.3f}"
            )
    print("  Only 3 AI-era periods against 16 pre-AI, autocorrelated — descriptive, not inferential.")


def run(output_dir: str = "data/output/visualizations") -> pd.DataFrame | None:
    """Build the era comparison, write it, and draw the signal-over-time chart."""
    if not os.path.exists(COMPOSITION_REPORT_PATH):
        print(f"  ⚠ {COMPOSITION_REPORT_PATH} not found; run the composition stage first.")
        return None

    scored_df, employment_col, sector_growth_df, score_columns = load_scored_occupations()
    period_correlation_df = build_period_correlations(scored_df, employment_col, sector_growth_df, score_columns)
    if period_correlation_df.empty:
        print("  ⚠ No period correlations could be computed.")
        return None

    era_summary_df = summarise_eras(period_correlation_df)
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    era_summary_df.to_csv(OUTPUT_PATH, index=False)
    print_era_summary(era_summary_df)

    unemployment_change = unemployment_change_by_period(sorted(period_correlation_df["period"].unique()))
    if unemployment_change is None:
        print("  ⚠ No unemployment series available; skipping the cycle decomposition.")
    else:
        cycle_decomposition_df = decompose_fit_strength(period_correlation_df, unemployment_change)
        cycle_decomposition_df.to_csv(CYCLE_OUTPUT_PATH, index=False)
        print_cycle_decomposition(cycle_decomposition_df)
        print(f"  ✓ {CYCLE_OUTPUT_PATH}")

    plot_signal_over_time(period_correlation_df, output_dir)
    print(f"  ✓ {OUTPUT_PATH}")
    return era_summary_df


if __name__ == "__main__":
    run()
