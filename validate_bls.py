"""
validate_bls.py
───────────────
Validates the occupation impact model against actual BLS employment and wage
trends across multiple year periods.

For each growth period (YoY pairs + composite), computes Pearson correlation
between our occupation_exposure score and real-world growth outcomes, and
compares against the naive Eloundou exposure baseline.

Inputs:
  • data/output/bls_trends.csv          (from analyze_bls.py)
  • data/output/occupation_exposure_report.csv
  • seeds/cps_a19_panel.csv             (committed CPS month panel)
  • data/raw/cps/table_a19.html         (optional — from download_cps.js)

Outputs (saved to data/output/visualizations/):
  • model_vs_actual_employment_growth.png      — exposure score vs. YoY employment growth per period
  • model_vs_actual_wage_growth.png            — exposure score vs. YoY wage growth per period
  • employment_vs_wage_growth_by_demand_type.png — composite emp vs wage growth, colored by demand type
  • sector_adjusted_employment_growth.png      — exposure score vs. sector-adjusted employment growth
  • sector_adjusted_wage_growth.png            — exposure score vs. sector-adjusted wage growth
  • employment_by_demand_type.png              — workers by dominant demand type bucket
  • wage_quartile_demand_type.png              — demand type share and mean impact by wage quartile
  • observed_vs_rebound_adjusted_exposure.png      — observed AI task coverage vs. rebound-adjusted exposure score
  • sector_level_validation.png               — sector-level labeled bubble scatter (n=22 sectors)
  • top_exposure_trajectories.png                 — 2022-2025 employment index for top 10 highest-exposure occupations
  • high_exposure_concentration.png               — bubble chart of high displacement-pressure occupations
  • exposure_volume_by_group.png              — employment-weighted AI exposure by SOC group
  • exposure_share_by_group.png               — share of total AI exposure by SOC group
  • cps_2026_direction.png                    — CPS employment direction by major group, since-OEWS and year-over-year windows
  • cps_rebound_model_vs_actual.png           — scatter: employment-weighted rebound-adjusted exposure vs. CPS growth, major group level
  • cps_dynamic_model_vs_actual.png           — scatter: employment-weighted dynamic net employment change vs. CPS growth, major group level
  • model_signal_over_time.png                — sector-level Pearson r by YoY period (2005→2025) for all three models;
                                                2022 boundary marked to distinguish pre-AI baseline from AI era
"""

import math
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.stats as stats
import seaborn as sns
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import PercentFormatter

from cps_panel import (
    CpsComparisonWindows,
    build_growth_frame,
    build_year_over_year_growth,
    format_month,
    load_cps_panel,
    oews_reference_month,
    resolve_comparison_windows,
    year_over_year_month_pairs,
)
from plot_constants import DEMAND_PALETTE, SOC_MAJOR_GROUPS
from synthesize_dynamic import (
    compute_dynamic_equilibrium,
    compute_equilibration_sensitivity,
    compute_sector_jackknife,
    plot_dynamic_sector_level_validation,
    plot_dynamic_vs_rebound_comparison,
    plot_net_change_distribution,
    plot_winners_losers,
    sector_growth_series,
)
from synthesize_impacts import attach_dominant_demand


def _label(period: str) -> str:
    """Convert a period key like '22_23' or 'composite' to a readable label."""
    if period == "composite":
        return "Composite (2022→latest)"
    parts = period.split("_")
    return f"20{parts[0]}→20{parts[1]}"


def _clean(merged_df: pd.DataFrame, growth_col: str, is_composite: bool, score_col: str = "occupation_exposure") -> pd.DataFrame:
    """Drop NaN/inf and remove extreme outliers for a single growth column."""
    clean_df = merged_df.replace([float("inf"), -float("inf")], pd.NA).dropna(subset=[growth_col, score_col])
    if growth_col.startswith("emp_growth"):
        upper = 2.0 if is_composite else 1.0
        lower = -0.75 if is_composite else -0.5
        clean_df = clean_df[(clean_df[growth_col] < upper) & (clean_df[growth_col] > lower)]
    return clean_df


def _correlations(clean_df: pd.DataFrame, growth_col: str) -> tuple[float, float, float, float]:
    """Return (r_impact, p_impact, r_eloundou, p_eloundou) for a growth column."""
    r_impact, p_impact = stats.pearsonr(clean_df["occupation_exposure"], clean_df[growth_col])
    r_eloundou, p_eloundou = stats.pearsonr(clean_df["eloundou_exposure_mid"], clean_df[growth_col])
    return r_impact, p_impact, r_eloundou, p_eloundou


def _compute_shift_share_residuals(df: pd.DataFrame, growth_col: str, emp_weight_col: str, soc_major_col: str) -> pd.Series:
    """
    Occupation-specific shift-share residual: observed growth minus the
    employment-weighted mean of its SOC major group. Strips out the national
    trend and sector-level cycle, leaving only the occupation-specific
    deviation — a cleaner target for model validation.
    """
    valid_df = df[[soc_major_col, growth_col, emp_weight_col]].dropna()
    sector_means = valid_df.groupby(soc_major_col).apply(lambda g: (g[growth_col] * g[emp_weight_col]).sum() / g[emp_weight_col].sum())
    return df[growth_col] - df[soc_major_col].map(sector_means)


def _make_subplot_figure(
    merged_df: pd.DataFrame,
    growth_type: str,
    periods: list[str],
    ylabel: str,
    output_path: str,
    score_col: str = "occupation_exposure",
    xlabel: str = "Rebound-Adjusted Exposure Score",
) -> None:
    n_periods = len(periods)
    ncols = min(n_periods, 2)
    nrows = math.ceil(n_periods / ncols)
    fig, axes_grid = plt.subplots(nrows, ncols, figsize=(7 * ncols, 6 * nrows), sharey=False)

    if nrows == 1 and ncols == 1:
        axes_flat = [axes_grid]
    elif nrows == 1 or ncols == 1:
        axes_flat = list(axes_grid)
    else:
        axes_flat = [ax for row in axes_grid for ax in row]

    for ax in axes_flat[n_periods:]:
        ax.set_visible(False)

    last_ax = axes_flat[n_periods - 1]

    for subplot_idx, (ax, period) in enumerate(zip(axes_flat, periods)):
        growth_col = f"{growth_type}_growth_{period}"
        is_composite = period == "composite"
        clean_df = _clean(merged_df, growth_col, is_composite, score_col=score_col)

        r_impact, p_impact = stats.pearsonr(clean_df[score_col], clean_df[growth_col])

        # Colored scatter by demand type, then regression lines overlaid
        sns.scatterplot(
            data=clean_df,
            x=score_col,
            y=growth_col,
            hue="dominant_demand",
            palette=DEMAND_PALETTE,
            alpha=0.6,
            s=25,
            legend=(ax is last_ax),
            ax=ax,
        )
        sns.regplot(
            data=clean_df,
            x=score_col,
            y=growth_col,
            scatter=False,
            line_kws={"color": "steelblue", "linewidth": 1.5},
            ax=ax,
        )
        for demand_type, color in DEMAND_PALETTE.items():
            subset_df = clean_df[clean_df["dominant_demand"] == demand_type]
            if len(subset_df) < 3:
                continue
            sns.regplot(
                data=subset_df,
                x=score_col,
                y=growth_col,
                scatter=False,
                ci=None,
                line_kws={"color": color, "linewidth": 1.5},
                ax=ax,
            )

        ax.set_title(f"{_label(period)}\nr={r_impact:.3f} (p={p_impact:.3f})", fontsize=11)
        ax.set_xlabel(xlabel, fontsize=10)
        ax.set_ylabel(ylabel if subplot_idx % ncols == 0 else "", fontsize=10)
        ax.axhline(0, color="grey", linestyle="--", linewidth=0.8)
        ax.axvline(0, color="grey", linestyle="--", linewidth=0.8)
        ax.text(0.02, 0.98, f"n={len(clean_df)}", transform=ax.transAxes, va="top", fontsize=8, color="grey")
        ax.xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
        ax.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))

        if ax is last_ax:
            handles, labels = ax.get_legend_handles_labels()
            overall_line = Line2D([0], [0], color="steelblue", linewidth=1.5, label="All occupations")
            ax.legend(
                handles=handles + [overall_line],
                labels=labels + ["All occupations"],
                title="Demand Type",
                fontsize=8,
                title_fontsize=8,
                loc="upper right",
            )

    fig.suptitle(f"{xlabel} vs. {ylabel}", fontsize=13, y=1.02)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()


def _make_sector_subplot_figure(
    merged_df: pd.DataFrame,
    score_col: str,
    growth_type: str,
    periods: list[str],
    employment_col: str,
    soc_major_col: str,
    output_path: str,
    xlabel: str,
    ylabel: str,
    suptitle: str,
    sector_growth_df: pd.DataFrame | None = None,
) -> None:
    """
    2×2 grid of sector-level bubble scatters, one panel per period.
    Each panel: employment-weighted sector mean of score_col (x) vs. sector
    growth (y) — the major-group total from `sector_growth_df` when given,
    otherwise the employment-weighted mean growth of the scored occupations.
    Bubble size ∝ sector employment; sectors labeled by name.
    """
    n_periods = len(periods)
    ncols = min(n_periods, 2)
    nrows = math.ceil(n_periods / ncols)
    fig, axes_grid = plt.subplots(nrows, ncols, figsize=(8 * ncols, 7 * nrows), sharey=False)

    if nrows == 1 and ncols == 1:
        axes_flat = [axes_grid]
    elif nrows == 1 or ncols == 1:
        axes_flat = list(axes_grid)
    else:
        axes_flat = [ax for row in axes_grid for ax in row]

    for ax in axes_flat[n_periods:]:
        ax.set_visible(False)

    for subplot_idx, (ax, period) in enumerate(zip(axes_flat, periods)):
        growth_col = f"{growth_type}_growth_{period}"
        if growth_col not in merged_df.columns:
            ax.set_visible(False)
            continue

        sector_source_df = merged_df.dropna(subset=[score_col, employment_col, growth_col]).copy()
        sector_source_df["soc_group"] = sector_source_df[soc_major_col].map(SOC_MAJOR_GROUPS).fillna("Other")

        def _weighted_mean(col: str, group_df: pd.DataFrame) -> float:
            return (group_df[col] * group_df[employment_col]).sum() / group_df[employment_col].sum()

        sector_agg_rows = []
        for soc_group, group_df in sector_source_df.groupby("soc_group"):
            sector_agg_rows.append(
                {
                    "soc_group": soc_group,
                    "soc_major": str(group_df[soc_major_col].iloc[0]),
                    "sector_score": _weighted_mean(score_col, group_df),
                    "sector_growth": _weighted_mean(growth_col, group_df),
                    "total_emp": group_df[employment_col].sum(),
                    "dominant_demand": group_df.groupby("dominant_demand")[employment_col].sum().idxmax(),
                }
            )
        sector_agg_df = pd.DataFrame(sector_agg_rows)
        total_growth = sector_growth_series(sector_growth_df, growth_col, pd.Index(sector_agg_df["soc_major"]))
        if total_growth is not None:
            sector_agg_df["sector_growth"] = total_growth.values
        sector_agg_df = sector_agg_df.dropna(subset=["sector_score", "sector_growth"])

        if len(sector_agg_df) < 3:
            ax.set_visible(False)
            continue

        sector_r, sector_p = stats.pearsonr(sector_agg_df["sector_score"], sector_agg_df["sector_growth"])
        bubble_size_scale = 1200 / sector_agg_df["total_emp"].max()
        bubble_colors = [DEMAND_PALETTE.get(d, "grey") for d in sector_agg_df["dominant_demand"]]

        ax.scatter(
            sector_agg_df["sector_score"],
            sector_agg_df["sector_growth"],
            s=(sector_agg_df["total_emp"] * bubble_size_scale).clip(20),
            c=bubble_colors,
            alpha=0.75,
            edgecolors="white",
            linewidths=0.5,
        )
        for _, sector_row in sector_agg_df.iterrows():
            ax.annotate(
                sector_row["soc_group"],
                (sector_row["sector_score"], sector_row["sector_growth"]),
                xytext=(4, 3),
                textcoords="offset points",
                fontsize=6,
                alpha=0.85,
            )
        ax.axhline(0, color="grey", linestyle="--", linewidth=0.8)
        ax.axvline(0, color="grey", linestyle="--", linewidth=0.8)
        ax.set_xlabel(xlabel if subplot_idx >= n_periods - ncols else "", fontsize=9)
        ax.set_ylabel(ylabel if subplot_idx % ncols == 0 else "", fontsize=9)
        ax.set_title(f"{_label(period)}\nr={sector_r:.3f} (p={sector_p:.3f}), n={len(sector_agg_df)}", fontsize=10)
        ax.xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
        ax.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))

    legend_handles = [Patch(facecolor=color, label=demand_type) for demand_type, color in DEMAND_PALETTE.items()]
    axes_flat[n_periods - 1].legend(handles=legend_handles, title="Dominant Demand Type", fontsize=7, loc="lower right")

    fig.suptitle(suptitle, fontsize=12, y=1.02)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()


def plot_model_signal_over_time(
    merged_validation_df: pd.DataFrame,
    dynamic_validation_df: pd.DataFrame,
    output_dir: str,
    anthropic_exp_df: pd.DataFrame | None = None,
    cps_panel_df: pd.DataFrame | None = None,
    sector_growth_df: pd.DataFrame | None = None,
) -> None:
    """
    Sector-level Pearson r between each model score and YoY employment growth,
    plotted as a time series spanning 2015→2025. The 2022 boundary is marked to
    separate pre-AI and AI-era periods. COVID-affected periods are shaded.

    Three model lines:
      • Rebound-adjusted exposure (occupation_exposure) — gross, ≥ 0
      • Dynamic net employment change (net_employment_change) — signed
      • Anthropic observed task coverage (observed_exposure) — gross, ≥ 0 (if available)

    Because the rebound-adjusted and observed measures validate with *negative* r
    (higher exposure → less growth) while the dynamic measure validates with
    *positive* r (higher net change → more growth), the y-axis is labeled with
    the sign convention for each line noted in the legend.

    When a CPS panel is supplied, a separate right-hand panel is drawn for the
    2025→2026 span that OEWS does not yet reach. It is deliberately not an
    extension of the main line. CPS is a different survey (household, ~60k
    interviews, self-reported occupation) measured against a different statistic
    (major-group totals, not an employment-weighted mean of occupation growth
    rates), and no period exists where both surveys overlap, so the two cannot be
    calibrated against each other. Its x-axis is the endpoint month rather than
    time: all three points measure the same 12-month span from endpoints two
    months apart, so their spread is endpoint sensitivity, not a trend.
    """
    latest_emp_col = sorted(c for c in merged_validation_df.columns if c.startswith("TOT_EMP_"))[-1]

    # Collect all YoY growth columns in chronological order
    def _sort_period(col_name: str) -> tuple[int, int]:
        key = col_name.replace("hist_emp_growth_", "").replace("emp_growth_", "")
        if key == "composite" or key == "pre_ai":
            return (99, 0)
        parts = key.split("_")
        return (int(parts[0]), int(parts[1]))

    hist_yoy = sorted(
        [c for c in merged_validation_df.columns if c.startswith("hist_emp_growth_") and "_pre_ai" not in c],
        key=_sort_period,
    )
    current_yoy = sorted(
        [c for c in merged_validation_df.columns if c.startswith("emp_growth_") and "composite" not in c],
        key=_sort_period,
    )
    all_period_cols = hist_yoy + current_yoy

    if len(all_period_cols) < 2:
        return

    # Build common dataframe: join dynamic net_employment_change and (optionally) observed_exposure
    base_df = merged_validation_df.copy()
    base_df = base_df.merge(
        dynamic_validation_df[["OCC_CODE", "net_employment_change"]],
        on="OCC_CODE",
        how="left",
    )
    has_observed = anthropic_exp_df is not None and "observed_exposure" in anthropic_exp_df.columns
    if has_observed:
        obs_col_map = {"occ_code": "OCC_CODE"} if "occ_code" in anthropic_exp_df.columns else {}
        obs_df = anthropic_exp_df.rename(columns=obs_col_map)[["OCC_CODE", "observed_exposure"]]
        base_df = base_df.merge(obs_df, on="OCC_CODE", how="left")

    base_df["soc_major"] = base_df["OCC_CODE"].str[:2]

    def _sector_r(emp_col: str, score_col: str) -> tuple[float, float, int] | None:
        """
        Sector-level Pearson r for one period and score column. Growth is the
        major-group total when the sector table carries this period, so that
        pre-2019 periods are not measured on the few occupations whose codes
        survived the SOC revisions.
        """
        subset = base_df[[score_col, emp_col, "soc_major", latest_emp_col]].dropna()
        if len(subset) < 10:
            return None
        rows = []
        for soc_grp, grp in subset.groupby("soc_major"):
            w = grp[latest_emp_col]
            rows.append(
                {
                    "soc_major": soc_grp,
                    "score": (grp[score_col] * w).sum() / w.sum(),
                    "growth": (grp[emp_col] * w).sum() / w.sum(),
                }
            )
        sec = pd.DataFrame(rows)
        total_growth = sector_growth_series(sector_growth_df, emp_col, pd.Index(sec["soc_major"]))
        if total_growth is not None:
            sec["growth"] = total_growth.values
        sec = sec.dropna()
        if len(sec) < 5:
            return None
        r, p = stats.pearsonr(sec["score"], sec["growth"])
        return r, p, len(sec)

    def _sector_scores(score_col: str) -> pd.DataFrame:
        """Employment-weighted mean model score per SOC major group."""
        subset = base_df[[score_col, "soc_major", latest_emp_col]].dropna()
        if subset.empty:
            return pd.DataFrame(columns=["soc_major", "sector_score"])
        weighted_score_series = subset.groupby("soc_major").apply(
            lambda grp: (grp[score_col] * grp[latest_emp_col]).sum() / grp[latest_emp_col].sum(),
            include_groups=False,
        )
        return weighted_score_series.rename("sector_score").reset_index()

    # Compute r for each period and each model
    score_configs = [
        ("occupation_exposure", "Rebound-adjusted (−r = correct)", "steelblue", "-o"),
        ("net_employment_change", "Dynamic net change (+r = correct)", "darkorange", "-s"),
    ]
    if has_observed:
        score_configs.append(("observed_exposure", "Observed AI coverage (−r = correct)", "seagreen", "-^"))

    period_labels = []
    for col in all_period_cols:
        key = col.replace("hist_emp_growth_", "").replace("emp_growth_", "")
        parts = key.split("_")
        period_labels.append(f"20{parts[0]}→\n20{parts[1]}")

    r_series: dict[str, list[float | None]] = {cfg[0]: [] for cfg in score_configs}
    p_series: dict[str, list[float | None]] = {cfg[0]: [] for cfg in score_configs}
    for period_col in all_period_cols:
        for score_col, _, _, _ in score_configs:
            result = _sector_r(period_col, score_col)
            if result is not None:
                r_series[score_col].append(result[0])
                p_series[score_col].append(result[1])
            else:
                r_series[score_col].append(None)
                p_series[score_col].append(None)

    # CPS year-over-year correlations for the span OEWS does not yet reach.
    # Every pair covers the same 12 months from a different endpoint month, so
    # these are repeated measurements of one period, not successive periods.
    cps_month_pairs = year_over_year_month_pairs(cps_panel_df) if cps_panel_df is not None else []
    cps_results: dict[str, list[tuple[str, float, float]]] = {cfg[0]: [] for cfg in score_configs}
    if cps_month_pairs:
        for score_col, _, _, _ in score_configs:
            sector_score_df = _sector_scores(score_col)
            if sector_score_df.empty:
                continue
            for year_ago_month, latest_month in cps_month_pairs:
                cps_growth_df = build_year_over_year_growth(cps_panel_df, year_ago_month, latest_month)
                cps_comparison_df = sector_score_df.merge(cps_growth_df, on="soc_major").dropna()
                if len(cps_comparison_df) < 5:
                    continue
                cps_r, cps_p = stats.pearsonr(cps_comparison_df["sector_score"], cps_comparison_df["emp_growth_year_over_year"])
                cps_results[score_col].append((latest_month, cps_r, cps_p))
    has_cps_panel = any(cps_results[score_col] for score_col in cps_results)

    if has_cps_panel:
        span_label = f"{cps_month_pairs[0][0][:4]}→{cps_month_pairs[-1][1][:4]}"
        print(f"\n── CPS year-over-year signal, {span_label} (n=22 sectors; each endpoint is the same 12-month span) ──")
        for score_col, label, _, _ in score_configs:
            if not cps_results[score_col]:
                continue
            endpoint_text = "  ".join(
                f"{format_month(month)}: r={r:+.3f} (p={p_value:.3f})" for month, r, p_value in cps_results[score_col]
            )
            r_values = [r for _, r, _ in cps_results[score_col]]
            print(f"  {label:<38} {endpoint_text}  | spread {max(r_values) - min(r_values):.3f}")

    sns.set_theme(style="whitegrid")
    if has_cps_panel:
        fig, (ax, cps_ax) = plt.subplots(
            1,
            2,
            figsize=(17, 5),
            sharey=True,
            gridspec_kw={"width_ratios": [len(all_period_cols), 3.4], "wspace": 0.04},
        )
    else:
        fig, ax = plt.subplots(figsize=(14, 5))
        cps_ax = None

    x = list(range(len(all_period_cols)))

    # Shade COVID-affected periods (2019→20 and 2020→21)
    covid_cols = ["hist_emp_growth_19_20", "hist_emp_growth_20_21"]
    for i, col in enumerate(all_period_cols):
        if col in covid_cols:
            ax.axvspan(i - 0.4, i + 0.4, alpha=0.12, color="red", zorder=0)

    # Shade AI era (from 2022→23 onward)
    ai_start = next((i for i, c in enumerate(all_period_cols) if not c.startswith("hist_")), None)
    if ai_start is not None:
        ax.axvspan(ai_start - 0.5, len(all_period_cols) - 0.5, alpha=0.08, color="royalblue", zorder=0)
        ax.axvline(ai_start - 0.5, color="royalblue", linestyle="--", linewidth=1.2, alpha=0.7, label="AI era begins (2022→23)")

    ax.axhline(0, color="grey", linewidth=0.8)

    for score_col, label, color, marker in score_configs:
        xs = [xi for xi, v in zip(x, r_series[score_col]) if v is not None]
        ys = [v for v in r_series[score_col] if v is not None]
        ps = [v for v in p_series[score_col] if v is not None]
        ax.plot(
            xs,
            ys,
            marker[1:] or "o",
            marker=marker[1:] if len(marker) > 1 else "o",
            linestyle="-",
            color=color,
            label=label,
            linewidth=1.6,
            markersize=6,
            zorder=3,
        )
        # Annotate significant periods with r and actual p-value
        for xi, yi, pi in zip(xs, ys, ps):
            if pi is not None and pi < 0.05:
                ax.annotate(
                    f"r={yi:+.2f}\np={pi:.3f}",
                    (xi, yi),
                    textcoords="offset points",
                    xytext=(0, 8 if yi >= 0 else -22),
                    ha="center",
                    fontsize=7,
                    color=color,
                )

    ax.set_xticks(x)
    ax.set_xticklabels(period_labels, fontsize=8)
    ax.set_ylabel("Sector-Level Pearson r (n=22 sectors)", fontsize=10)
    ax.set_xlabel("YoY Period — BLS OEWS (employer survey, May reference month)", fontsize=10)
    ax.legend(fontsize=9, loc="lower left")
    ax.set_ylim(-0.75, 0.75)

    # ── CPS panel: the 2025→2026 span OEWS does not yet reach ────────────────
    # Drawn as a separate axes rather than as more points on the line above. The
    # y-scale is shared so the r values stay directly comparable, but the x-axis
    # is the CPS endpoint month, not time — every point covers the same 12-month
    # span, so their spread measures endpoint sensitivity rather than a trend.
    if cps_ax is not None:
        cps_months = sorted({month for entries in cps_results.values() for month, _, _ in entries})
        cps_x_by_month = {month: index for index, month in enumerate(cps_months)}
        cps_ax.set_facecolor("#f4f1ea")
        cps_ax.axhline(0, color="grey", linewidth=0.8)

        for score_col, _, color, marker in score_configs:
            entries = cps_results[score_col]
            if not entries:
                continue
            marker_shape = marker[1:] if len(marker) > 1 else "o"
            entry_x = [cps_x_by_month[month] for month, _, _ in entries]
            entry_r = [r for _, r, _ in entries]
            # Markers only, deliberately unconnected. A line across the month axis
            # would read as a trend, but these are one 12-month span measured from
            # three endpoints — the vertical spread is endpoint sensitivity.
            cps_ax.plot(
                entry_x,
                entry_r,
                linestyle="none",
                marker=marker_shape,
                markersize=7,
                markerfacecolor="white",
                markeredgecolor=color,
                markeredgewidth=1.6,
                zorder=3,
            )
            for x_position, (_, r_value, p_value) in zip(entry_x, entries):
                if p_value < 0.05:
                    cps_ax.annotate(
                        f"r={r_value:+.2f}\np={p_value:.3f}",
                        (x_position, r_value),
                        textcoords="offset points",
                        xytext=(0, 9 if r_value >= 0 else -22),
                        ha="center",
                        fontsize=7,
                        color=color,
                    )

        cps_ax.set_xticks(list(cps_x_by_month.values()))
        cps_ax.set_xticklabels([pd.Period(month, freq="M").strftime("%b") for month in cps_months], fontsize=8)
        cps_ax.set_xlim(-0.7, len(cps_months) - 0.3)
        cps_ax.set_xlabel("CPS A-19 endpoint month", fontsize=9)
        cps_ax.set_title(
            "CPS 2025→2026\nsame span, 3 endpoints",
            fontsize=9,
            color="dimgrey",
        )
        cps_ax.text(
            0.5,
            0.015,
            "Different survey — not\ncalibrated to OEWS;\nhollow = not a time series",
            transform=cps_ax.transAxes,
            fontsize=7,
            ha="center",
            va="bottom",
            color="dimgrey",
        )

    figure_title = (
        "Model Predictive Signal Over Time: Sector-Level Correlation with Employment Growth\n"
        "Red shading = COVID-disrupted periods; blue shading = AI era (2022→). "
        "Significant periods annotated with r and p-value."
    )
    if cps_ax is not None:
        figure_title += (
            "\nRight panel is a separate survey covering the span OEWS has not reached — read it beside the line, not as part of it."
        )
    fig.suptitle(figure_title, fontsize=11)

    # Text box for note on sign conventions
    ax.text(
        0.30,
        0.02,
        "Sign note: rebound-adjusted and observed validate negative (more exposure → less growth);\n"
        "dynamic net change validates positive (predicted gainers grow). Both directions are 'correct'.",
        transform=ax.transAxes,
        fontsize=7,
        va="bottom",
        color="dimgrey",
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "alpha": 0.7},
    )

    plt.tight_layout()
    plt.savefig(f"{output_dir}/model_signal_over_time.png", dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved {output_dir}/model_signal_over_time.png")


def plot_model_signal_over_time_occupation(
    merged_validation_df: pd.DataFrame,
    dynamic_validation_df: pd.DataFrame,
    output_dir: str,
    anthropic_exp_df: pd.DataFrame | None = None,
    harmonized_trends_df: pd.DataFrame | None = None,
    unit_membership_df: pd.DataFrame | None = None,
) -> None:
    """
    Occupation-level Pearson r between each model score and YoY employment growth,
    plotted as a time series spanning 2005→2025. Unlike the sector-level version,
    no sector aggregation step is applied — each occupation, or each harmonized
    SOC unit, is one data point. n counts harmonized units when
    bls_harmonized_trends.csv is present, else surviving 2022 codes. Significant
    periods annotated with r, p, and n.
    """

    # Collect all YoY growth columns in chronological order
    def _sort_period(col_name: str) -> tuple[int, int]:
        key = col_name.replace("hist_emp_growth_", "").replace("emp_growth_", "")
        if key in ("composite", "pre_ai"):
            return (99, 0)
        parts = key.split("_")
        return (int(parts[0]), int(parts[1]))

    hist_yoy = sorted(
        [c for c in merged_validation_df.columns if c.startswith("hist_emp_growth_") and "_pre_ai" not in c],
        key=_sort_period,
    )
    current_yoy = sorted(
        [c for c in merged_validation_df.columns if c.startswith("emp_growth_") and "composite" not in c],
        key=_sort_period,
    )
    all_period_cols = hist_yoy + current_yoy

    if len(all_period_cols) < 2:
        return

    latest_emp_col = sorted(c for c in merged_validation_df.columns if c.startswith("TOT_EMP_"))[-1]

    base_df = merged_validation_df.copy()
    base_df = base_df.merge(
        dynamic_validation_df[["OCC_CODE", "net_employment_change"]],
        on="OCC_CODE",
        how="left",
    )
    has_observed = anthropic_exp_df is not None and "observed_exposure" in anthropic_exp_df.columns
    if has_observed:
        obs_col_map = {"occ_code": "OCC_CODE"} if "occ_code" in anthropic_exp_df.columns else {}
        obs_df = anthropic_exp_df.rename(columns=obs_col_map)[["OCC_CODE", "observed_exposure"]]
        base_df = base_df.merge(obs_df, on="OCC_CODE", how="left")

    # On harmonized units every period is measured on the same occupation definitions,
    # so n no longer swings with which detailed codes happened to survive a SOC revision.
    use_units = harmonized_trends_df is not None and unit_membership_df is not None
    if use_units:
        score_cols_present = [
            score_col for score_col in ("occupation_exposure", "net_employment_change", "observed_exposure") if score_col in base_df.columns
        ]
        unit_scores_df = build_unit_scores(base_df, unit_membership_df, latest_emp_col, score_cols_present)
        growth_cols_present = [column for column in harmonized_trends_df.columns if "emp_growth_" in column]
        base_df = unit_scores_df.merge(harmonized_trends_df[["unit_id"] + growth_cols_present], on="unit_id", how="inner")
        hist_yoy = sorted(
            [c for c in base_df.columns if c.startswith("hist_emp_growth_") and "_pre_ai" not in c],
            key=_sort_period,
        )
        current_yoy = sorted(
            [c for c in base_df.columns if c.startswith("emp_growth_") and "composite" not in c],
            key=_sort_period,
        )
        all_period_cols = hist_yoy + current_yoy
        if len(all_period_cols) < 2:
            return

    def _occupation_r(emp_col: str, score_col: str) -> tuple[float, float, int] | None:
        """Compute unit- or occupation-level Pearson r for one period and score column."""
        subset = base_df[[score_col, emp_col]].dropna()
        if len(subset) < 20:
            return None
        r, p = stats.pearsonr(subset[score_col], subset[emp_col])
        return r, p, len(subset)

    score_configs = [
        ("occupation_exposure", "Rebound-adjusted (−r = correct)", "steelblue", "-o"),
        ("net_employment_change", "Dynamic net change (+r = correct)", "darkorange", "-s"),
    ]
    if has_observed:
        score_configs.append(("observed_exposure", "Observed AI coverage (−r = correct)", "seagreen", "-^"))

    period_labels = []
    for col in all_period_cols:
        key = col.replace("hist_emp_growth_", "").replace("emp_growth_", "")
        parts = key.split("_")
        period_labels.append(f"20{parts[0]}→\n20{parts[1]}")

    r_series: dict[str, list[float | None]] = {cfg[0]: [] for cfg in score_configs}
    p_series: dict[str, list[float | None]] = {cfg[0]: [] for cfg in score_configs}
    n_series: list[int | None] = []
    for period_col in all_period_cols:
        period_n = None
        for score_col, _, _, _ in score_configs:
            result = _occupation_r(period_col, score_col)
            if result is not None:
                r_series[score_col].append(result[0])
                p_series[score_col].append(result[1])
                period_n = result[2]
            else:
                r_series[score_col].append(None)
                p_series[score_col].append(None)
        n_series.append(period_n)

    sns.set_theme(style="whitegrid")
    fig, ax = plt.subplots(figsize=(14, 5))

    x = list(range(len(all_period_cols)))

    covid_cols = ["hist_emp_growth_19_20", "hist_emp_growth_20_21"]
    for i, col in enumerate(all_period_cols):
        if col in covid_cols:
            ax.axvspan(i - 0.4, i + 0.4, alpha=0.12, color="red", zorder=0)

    ai_start = next((i for i, c in enumerate(all_period_cols) if not c.startswith("hist_")), None)
    if ai_start is not None:
        ax.axvspan(ai_start - 0.5, len(all_period_cols) - 0.5, alpha=0.08, color="royalblue", zorder=0)
        ax.axvline(ai_start - 0.5, color="royalblue", linestyle="--", linewidth=1.2, alpha=0.7, label="AI era begins (2022→23)")

    ax.axhline(0, color="grey", linewidth=0.8)

    for score_col, label, color, marker in score_configs:
        xs = [xi for xi, v in zip(x, r_series[score_col]) if v is not None]
        ys = [v for v in r_series[score_col] if v is not None]
        ps = [v for v in p_series[score_col] if v is not None]
        ax.plot(
            xs,
            ys,
            marker[1:] or "o",
            marker=marker[1:] if len(marker) > 1 else "o",
            linestyle="-",
            color=color,
            label=label,
            linewidth=1.6,
            markersize=6,
            zorder=3,
        )
        for xi, yi, pi in zip(xs, ys, ps):
            if pi is not None and pi < 0.05:
                ax.annotate(
                    f"r={yi:+.2f}\np={pi:.3f}",
                    (xi, yi),
                    textcoords="offset points",
                    xytext=(0, 8 if yi >= 0 else -22),
                    ha="center",
                    fontsize=7,
                    color=color,
                )

    # Annotate n below each x-tick
    y_bottom = ax.get_ylim()[0]
    for xi, n_val in enumerate(n_series):
        if n_val is not None:
            ax.text(xi, y_bottom + 0.01, f"n={n_val}", ha="center", va="bottom", fontsize=6, color="dimgrey")

    ax.set_xticks(x)
    ax.set_xticklabels(period_labels, fontsize=8)
    ax.set_ylabel("Occupation-Level Pearson r", fontsize=10)
    ax.set_xlabel("YoY Period", fontsize=10)
    chart_title = (
        "Model Predictive Signal Over Time: Occupation-Level Correlation with Employment Growth\n"
        "Red shading = COVID-disrupted periods; blue shading = AI era (2022→). "
        "Significant periods annotated with r and p-value."
    )
    # Off units, n is whatever survived the SOC revisions; on units it is the unit count.
    chart_title += (
        "\n(harmonized SOC units — consistent occupation definitions 2005→2025)"
        if use_units
        else " n varies with historical SOC survivorship."
    )
    ax.set_title(chart_title, fontsize=11)
    ax.legend(fontsize=9, loc="lower left")
    ax.set_ylim(-0.4, 0.4)

    ax.text(
        0.01,
        0.02,
        "Sign note: rebound-adjusted and observed validate negative (more exposure → less growth);\n"
        "dynamic net change validates positive (predicted gainers grow). Both directions are 'correct'.",
        transform=ax.transAxes,
        fontsize=7,
        va="bottom",
        color="dimgrey",
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "alpha": 0.7},
    )

    plt.tight_layout()
    plt.savefig(f"{output_dir}/model_signal_over_time_occupation.png", dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved {output_dir}/model_signal_over_time_occupation.png")


def _load_cps_growth() -> tuple[pd.DataFrame, CpsComparisonWindows] | None:
    """
    Load the CPS month panel and derive both comparison windows.

    Returns (growth_df, windows), or None when no usable panel is available. A
    panel too thin to define a window is reported and skipped rather than raised:
    the CPS charts are a supplementary indicator and must not take down the rest
    of the validation stage.
    """
    cps_panel_df = load_cps_panel()
    if cps_panel_df is None:
        return None

    bls_trends_columns = list(pd.read_csv("data/output/bls_trends.csv", nrows=1).columns)
    try:
        cps_windows = resolve_comparison_windows(cps_panel_df, oews_reference_month(bls_trends_columns))
    except ValueError as window_error:
        print(f"  Skipping CPS charts — {window_error}")
        return None
    return build_growth_frame(cps_panel_df, cps_windows), cps_windows


def _plot_cps_2026_direction(
    output_dir: str, cps_growth_df: pd.DataFrame, cps_windows: CpsComparisonWindows, exposure_group_df: pd.DataFrame
) -> None:
    """Paired horizontal bars: CPS major group employment direction over both comparison windows."""
    group_demand_df = exposure_group_df[["soc_major", "group_dominant_demand"]].copy()
    group_demand_df["soc_major"] = group_demand_df["soc_major"].astype(str)
    cps_chart_df = cps_growth_df.merge(group_demand_df, on="soc_major", how="left")
    cps_chart_df = cps_chart_df.sort_values("emp_growth_since_anchor", ascending=True).reset_index(drop=True)

    has_year_over_year = "emp_growth_year_over_year" in cps_chart_df.columns

    print(f"\n── CPS Table A-19: Major Group Employment Direction ({cps_windows.since_anchor_label}) ──")
    print("   (CPS monthly survey — directional indicator only; not BLS OEWS)")
    print(f"   {cps_windows.window_caveat}\n")
    display_columns = ["occupation", "anchor_employment", "latest_employment", "emp_growth_since_anchor"]
    if has_year_over_year:
        display_columns.append("emp_growth_year_over_year")
    display_columns.append("group_dominant_demand")
    display_df = cps_chart_df[display_columns].copy()
    display_df["anchor_employment"] = display_df["anchor_employment"].map("{:,.0f}".format)
    display_df["latest_employment"] = display_df["latest_employment"].map("{:,.0f}".format)
    display_df["emp_growth_since_anchor"] = display_df["emp_growth_since_anchor"].map("{:+.1%}".format)
    if has_year_over_year:
        display_df["emp_growth_year_over_year"] = display_df["emp_growth_year_over_year"].map("{:+.1%}".format)
    print(display_df.to_string(index=False))

    bar_colors = [DEMAND_PALETTE.get(demand_type, "grey") for demand_type in cps_chart_df["group_dominant_demand"]]
    short_labels = [SOC_MAJOR_GROUPS.get(row["soc_major"], row["occupation"])[:40] for _, row in cps_chart_df.iterrows()]
    bar_positions = np.arange(len(cps_chart_df))
    bar_height = 0.4 if has_year_over_year else 0.7

    fig, ax_cps = plt.subplots(figsize=(12, 10))
    since_anchor_offset = bar_height / 2 if has_year_over_year else 0
    since_anchor_bars = ax_cps.barh(
        bar_positions + since_anchor_offset,
        cps_chart_df["emp_growth_since_anchor"],
        height=bar_height,
        color=bar_colors,
        edgecolor="white",
        linewidth=0.5,
    )
    bar_groups = [(since_anchor_bars, cps_chart_df["emp_growth_since_anchor"])]

    if has_year_over_year:
        year_over_year_bars = ax_cps.barh(
            bar_positions - bar_height / 2,
            cps_chart_df["emp_growth_year_over_year"],
            height=bar_height,
            color=bar_colors,
            edgecolor="white",
            linewidth=0.5,
            alpha=0.45,
            hatch="///",
        )
        bar_groups.append((year_over_year_bars, cps_chart_df["emp_growth_year_over_year"]))

    for bars, growth_values in bar_groups:
        for bar_rect, growth_value in zip(bars, growth_values):
            x_position = growth_value + (0.001 if growth_value >= 0 else -0.001)
            horizontal_alignment = "left" if growth_value >= 0 else "right"
            ax_cps.text(
                x_position,
                bar_rect.get_y() + bar_rect.get_height() / 2,
                f"{growth_value:+.1%}",
                va="center",
                ha=horizontal_alignment,
                fontsize=6.5,
            )

    ax_cps.set_yticks(bar_positions)
    ax_cps.set_yticklabels(short_labels)
    ax_cps.axvline(0, color="black", linewidth=0.8)
    ax_cps.xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=1))
    ax_cps.set_xlabel("Employment Growth", fontsize=10)
    ax_cps.set_title(
        f"Major Group Employment Direction — CPS Table A-19\n"
        f"Since OEWS: {cps_windows.since_anchor_label}"
        + (f"   |   Year-over-year: {cps_windows.year_over_year_label}" if has_year_over_year else "")
        + "\nDirectional indicator only; not BLS OEWS",
        fontsize=11,
    )

    demand_legend_handles = [Patch(facecolor=color, label=demand_type) for demand_type, color in DEMAND_PALETTE.items()]
    demand_legend = ax_cps.legend(handles=demand_legend_handles, title="Dominant Demand Type", fontsize=8, loc="lower right")
    if has_year_over_year:
        ax_cps.add_artist(demand_legend)
        window_legend_handles = [
            Patch(facecolor="grey", label=f"Since OEWS ({cps_windows.since_anchor_label})"),
            Patch(facecolor="grey", alpha=0.45, hatch="///", label=f"Year-over-year ({cps_windows.year_over_year_label})"),
        ]
        ax_cps.legend(handles=window_legend_handles, title="Comparison Window", fontsize=8, loc="upper left")

    fig.text(0.5, -0.01, cps_windows.window_caveat, ha="center", fontsize=7.5, color="dimgrey", wrap=True)
    plt.tight_layout()
    plt.savefig(f"{output_dir}/cps_2026_direction.png", dpi=300, bbox_inches="tight")
    plt.close()
    print(f"\n  Saved {output_dir}/cps_2026_direction.png")


def _plot_cps_model_vs_actual(
    output_dir: str,
    cps_growth_df: pd.DataFrame,
    cps_windows: CpsComparisonWindows,
    model_df: pd.DataFrame,
    exposure_group_df: pd.DataFrame,
    score_col: str = "occupation_exposure",
    xlabel: str = "Employment-Weighted Mean Rebound-Adjusted Exposure Score",
    output_filename: str = "cps_rebound_model_vs_actual.png",
) -> None:
    """
    Scatter of employment-weighted model score vs. CPS growth since the OEWS snapshot, major group level.

    Plots the since-OEWS window — the stretch OEWS does not yet cover — and reports
    the year-over-year correlation alongside it for comparison.
    """
    employment_columns = sorted(column for column in model_df.columns if column.startswith("TOT_EMP_"))
    if not employment_columns:
        print(f"  Skipping CPS {output_filename} — no employment column found.")
        return
    emp_col = employment_columns[-1]

    valid_df = model_df.dropna(subset=[score_col, emp_col]).copy()
    valid_df["soc_major"] = valid_df["OCC_CODE"].str[:2]

    group_score_df = (
        valid_df.groupby("soc_major")
        .apply(
            lambda g: pd.Series(
                {
                    "group_score": (g[score_col] * g[emp_col]).sum() / g[emp_col].sum(),
                    "n_occupations": len(g),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )

    group_demand_df = exposure_group_df[["soc_major", "group_dominant_demand"]].copy()
    group_demand_df["soc_major"] = group_demand_df["soc_major"].astype(str)

    growth_columns = ["soc_major", "emp_growth_since_anchor"]
    if "emp_growth_year_over_year" in cps_growth_df.columns:
        growth_columns.append("emp_growth_year_over_year")
    comparison_df = group_score_df.merge(cps_growth_df[growth_columns], on="soc_major").merge(group_demand_df, on="soc_major", how="left")
    comparison_df["group_label"] = comparison_df["soc_major"].map(SOC_MAJOR_GROUPS)

    cps_r, cps_p = stats.pearsonr(comparison_df["group_score"], comparison_df["emp_growth_since_anchor"])
    year_over_year_correlation = None
    if "emp_growth_year_over_year" in comparison_df.columns:
        year_over_year_correlation = stats.pearsonr(comparison_df["group_score"], comparison_df["emp_growth_year_over_year"])

    print(f"\n── CPS {output_filename} (Major Group Level, n={len(comparison_df)}) ──")
    print(f"Since OEWS ({cps_windows.since_anchor_label}): Pearson r = {cps_r:.3f}, p = {cps_p:.4f}")
    if year_over_year_correlation is not None:
        print(
            f"Year-over-year ({cps_windows.year_over_year_label}): "
            f"Pearson r = {year_over_year_correlation[0]:.3f}, p = {year_over_year_correlation[1]:.4f}"
        )

    dot_colors = [DEMAND_PALETTE.get(d, "grey") for d in comparison_df["group_dominant_demand"]]
    fig, ax_cps_scatter = plt.subplots(figsize=(11, 8))
    ax_cps_scatter.scatter(
        comparison_df["group_score"],
        comparison_df["emp_growth_since_anchor"],
        c=dot_colors,
        s=90,
        alpha=0.85,
        edgecolors="white",
        linewidths=0.5,
    )
    for _, scatter_row in comparison_df.iterrows():
        label_text = scatter_row["group_label"][:28] if pd.notna(scatter_row["group_label"]) else scatter_row["soc_major"]
        ax_cps_scatter.annotate(
            label_text,
            (scatter_row["group_score"], scatter_row["emp_growth_since_anchor"]),
            xytext=(5, 3),
            textcoords="offset points",
            fontsize=7.5,
            alpha=0.9,
        )
    sns.regplot(
        data=comparison_df,
        x="group_score",
        y="emp_growth_since_anchor",
        scatter=False,
        ax=ax_cps_scatter,
        line_kws={"color": "steelblue", "linewidth": 1.5},
    )
    ax_cps_scatter.axhline(0, color="grey", linestyle="--", linewidth=0.8)
    ax_cps_scatter.set_xlabel(xlabel, fontsize=10)
    ax_cps_scatter.set_ylabel(f"Employment Growth {cps_windows.since_anchor_label} (CPS)", fontsize=10)
    year_over_year_note = (
        f"  |  YoY ({cps_windows.year_over_year_label}): r = {year_over_year_correlation[0]:.3f}, p = {year_over_year_correlation[1]:.3f}"
        if year_over_year_correlation is not None
        else ""
    )
    ax_cps_scatter.set_title(
        f"Model vs. CPS Employment Growth Since OEWS — Major Group Level\n"
        f"r = {cps_r:.3f}, p = {cps_p:.3f}, n = {len(comparison_df)} groups{year_over_year_note}\n"
        f"CPS monthly, not BLS OEWS",
        fontsize=11,
    )
    fig.text(0.5, -0.01, cps_windows.window_caveat, ha="center", fontsize=7.5, color="dimgrey", wrap=True)
    ax_cps_scatter.xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=1))
    ax_cps_scatter.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=1))
    legend_handles_scatter = [Patch(facecolor=color, label=demand_type) for demand_type, color in DEMAND_PALETTE.items()]
    ax_cps_scatter.legend(handles=legend_handles_scatter, title="Dominant Demand Type", fontsize=9)
    plt.tight_layout()
    plt.savefig(f"{output_dir}/{output_filename}", dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  Saved {output_dir}/{output_filename}")


def load_sector_growth_table(path: str = "data/output/bls_sector_trends.csv") -> pd.DataFrame | None:
    """
    Major-group growth series written by analyze_bls.py, indexed by two-digit
    soc_major. None if the file is absent, in which case every sector-level
    growth measure falls back to the survivor-occupation mean.
    """
    if not os.path.exists(path):
        print(f"Warning: {path} not found — sector growth will use the survivor-occupation mean.")
        return None
    sector_trends_df = pd.read_csv(path, dtype={"soc_major": str})
    sector_trends_df["soc_major"] = sector_trends_df["soc_major"].str.zfill(2)
    return sector_trends_df.set_index("soc_major")


def load_harmonized_trends(path: str = "data/output/bls_harmonized_trends.csv") -> pd.DataFrame | None:
    """Unit-level trend series from analyze_bls.py; None (with a warning) if the analyze stage did not write it."""
    if not os.path.exists(path):
        print(f"Warning: {path} not found — occupation-level history will use surviving 2022 codes.")
        return None
    return pd.read_csv(path, dtype={"unit_id": str})


def load_unit_membership(path: str = "data/output/soc_harmonization_units.csv") -> pd.DataFrame | None:
    """Per-year unit membership from analyze_bls.py; None (with a warning) if the analyze stage did not write it."""
    if not os.path.exists(path):
        print(f"Warning: {path} not found — occupation-level history will use surviving 2022 codes.")
        return None
    return pd.read_csv(path, dtype={"unit_id": str, "year": str, "oews_code": str})


def build_unit_scores(
    merged_validation_df: pd.DataFrame,
    unit_membership_df: pd.DataFrame,
    employment_col: str,
    score_cols: list[str],
    anchor_year: str = "22",
) -> pd.DataFrame:
    """
    Employment-weighted mean of each model score over a unit's anchor-year OEWS codes.

    merged_validation_df is keyed on the 2022 OEWS code set, so a unit's score is
    the weighted mean over its year-22 members that were scored. Weights are
    renormalised over members with a non-missing score, and units with no scored
    member are omitted.
    """
    anchor_members_df = unit_membership_df[unit_membership_df["year"] == anchor_year][["unit_id", "oews_code"]]
    scored_members_df = anchor_members_df.merge(
        merged_validation_df[["OCC_CODE", employment_col] + score_cols],
        left_on="oews_code",
        right_on="OCC_CODE",
        how="inner",
        validate="many_to_one",
    )
    unit_score_rows = []
    for unit_id, member_rows_df in scored_members_df.groupby("unit_id"):
        unit_score_row: dict[str, float | str] = {"unit_id": unit_id}
        for score_col in score_cols:
            scored_rows_df = member_rows_df.dropna(subset=[score_col, employment_col])
            weight_total = scored_rows_df[employment_col].sum()
            unit_score_row[score_col] = (
                (scored_rows_df[score_col] * scored_rows_df[employment_col]).sum() / weight_total if weight_total > 0 else float("nan")
            )
        unit_score_rows.append(unit_score_row)
    return pd.DataFrame(unit_score_rows, columns=["unit_id"] + score_cols)


def main():
    bls_trends_df = pd.read_csv("data/output/bls_trends.csv")
    sector_growth_df = load_sector_growth_table()
    harmonized_trends_df = load_harmonized_trends()
    unit_membership_df = load_unit_membership()
    occupation_exposure_df = pd.read_csv("data/output/occupation_exposure_report.csv")

    occupation_exposure_df["OCC_CODE"] = occupation_exposure_df["O*NET-SOC Code"].astype(str).str.split(".").str[0]

    # dominant_demand and dominant_strength are deliberately absent here: several
    # O*NET occupations collapse into one BLS SOC code, so the composition these
    # labels summarise changes and they must be re-derived from the aggregated
    # pct_* columns rather than carried over from an arbitrary first row.
    _agg_dict: dict = {
        "occupation_exposure": "mean",
        "Title": "first",
        "mean_penetration": "mean",
        # Demand-type exposure contributions for the dynamic equilibrium model
        "bounded_exposure_contribution": "mean",
        "unbounded_exposure_contribution": "mean",
        "adversarial_exposure_contribution": "mean",
        "pct_bounded": "mean",
        "pct_unbounded": "mean",
        "pct_adversarial": "mean",
    }
    if "eloundou_exposure_mid" in occupation_exposure_df.columns:
        _agg_dict["eloundou_exposure_mid"] = "mean"
    aggregated_exposure_df = occupation_exposure_df.groupby("OCC_CODE").agg(_agg_dict).reset_index()
    aggregated_exposure_df = attach_dominant_demand(aggregated_exposure_df)

    merged_validation_df = pd.merge(aggregated_exposure_df, bls_trends_df, on="OCC_CODE", how="inner")

    # Detect all growth periods from columns in bls_trends
    emp_growth_cols = [c for c in merged_validation_df.columns if c.startswith("emp_growth_")]
    wage_growth_cols = [c for c in merged_validation_df.columns if c.startswith("wage_growth_")]

    # Extract period keys (e.g. "22_23", "23_24", "composite"), sorted with composite last
    def _sort_key(col: str) -> tuple:
        period = col.split("growth_", 1)[1]
        return (1, period) if period == "composite" else (0, period)

    emp_periods = sorted([c.replace("emp_growth_", "") for c in emp_growth_cols], key=lambda p: _sort_key(f"emp_growth_{p}"))
    wage_periods = sorted([c.replace("wage_growth_", "") for c in wage_growth_cols], key=lambda p: _sort_key(f"wage_growth_{p}"))

    output_dir = "data/output/visualizations"
    os.makedirs(output_dir, exist_ok=True)
    sns.set_theme(style="whitegrid")

    # ── Subplot figures ───────────────────────────────────────────────────────
    _make_subplot_figure(
        merged_validation_df,
        "emp",
        emp_periods,
        "Year-over-Year Employment Growth",
        f"{output_dir}/model_vs_actual_employment_growth.png",
    )
    _make_subplot_figure(
        merged_validation_df,
        "wage",
        wage_periods,
        "Year-over-Year Median Wage Growth",
        f"{output_dir}/model_vs_actual_wage_growth.png",
    )

    # ── Productivity Premium vs Red Queen's Race (composite) ──────────────────
    if "emp_growth_composite" in merged_validation_df.columns:
        composite_df = _clean(merged_validation_df, "emp_growth_composite", is_composite=True)
        composite_df = composite_df.replace([float("inf"), -float("inf")], pd.NA).dropna(
            subset=["emp_growth_composite", "wage_growth_composite"]
        )
        plt.figure(figsize=(12, 10))
        sns.scatterplot(
            data=composite_df,
            x="emp_growth_composite",
            y="wage_growth_composite",
            hue="dominant_demand",
            palette=DEMAND_PALETTE,
            alpha=0.7,
            s=60,
        )
        plt.title("Composite Employment vs. Wage Growth by Demand Type (2022→latest)")
        plt.xlabel("Composite Employment Growth (2022→latest)")
        plt.ylabel("Composite Median Wage Growth (2022→latest)")
        plt.axhline(0, color="black", linestyle="--", linewidth=1)
        plt.axvline(0, color="black", linestyle="--", linewidth=1)
        plt.gca().xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
        plt.gca().yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
        plt.legend(title="Demand Type")
        plt.tight_layout()
        plt.savefig(f"{output_dir}/employment_vs_wage_growth_by_demand_type.png", dpi=300)
        plt.close()

    # ── Correlation summary ───────────────────────────────────────────────────
    print("\n── Correlation Results ──────────────────────────────────────────────────")
    header = f"{'Period':<30} {'Metric':<10} {'Our r':>8} {'p':>8} {'Eloundou r':>12} {'p':>8} {'n':>6}"
    print(header)
    print("-" * len(header))

    for period in emp_periods:
        for growth_type, label in [("emp", "Emp"), ("wage", "Wage")]:
            growth_col = f"{growth_type}_growth_{period}"
            if growth_col not in merged_validation_df.columns:
                continue
            is_composite = period == "composite"
            clean_df = _clean(merged_validation_df, growth_col, is_composite)
            clean_df = clean_df.dropna(subset=["eloundou_exposure_mid"])
            if len(clean_df) < 10:
                continue
            r_impact, p_impact, r_eloundou, p_eloundou = _correlations(clean_df, growth_col)
            print(
                f"{_label(period):<30} {label:<10} {r_impact:>8.3f} {p_impact:>8.3f}"
                f" {r_eloundou:>12.3f} {p_eloundou:>8.3f} {len(clean_df):>6}"
            )

    # ── Dominant demand stats (composite) ────────────────────────────────────
    if "emp_growth_composite" in merged_validation_df.columns:
        composite_df = _clean(merged_validation_df, "emp_growth_composite", is_composite=True)
        composite_df = composite_df.dropna(subset=["wage_growth_composite"])
        print("\n── Dominant Demand Type — Composite Growth ──")
        demand_stats = composite_df.groupby("dominant_demand").agg(
            emp_growth=("emp_growth_composite", "mean"), wage_growth=("wage_growth_composite", "mean"), n=("Title", "count")
        )
        print(demand_stats.to_string())

    # ── Shift-share validation ────────────────────────────────────────────────
    # Decompose observed growth into sector trend + occupation-specific residual.
    # Correlating our model against the residual removes sector-cycle noise and
    # gives a cleaner test of whether occupation_exposure predicts anything beyond
    # what the sector average already explains.
    merged_validation_df["soc_major"] = merged_validation_df["OCC_CODE"].str[:2]
    ss_weight_col = sorted(c for c in merged_validation_df.columns if c.startswith("TOT_EMP_"))[-1]

    for period in emp_periods:
        raw_col = f"emp_growth_{period}"
        if raw_col in merged_validation_df.columns:
            merged_validation_df[f"ss_emp_growth_{period}"] = _compute_shift_share_residuals(
                merged_validation_df, raw_col, ss_weight_col, "soc_major"
            )

    for period in wage_periods:
        raw_col = f"wage_growth_{period}"
        if raw_col in merged_validation_df.columns:
            merged_validation_df[f"ss_wage_growth_{period}"] = _compute_shift_share_residuals(
                merged_validation_df, raw_col, ss_weight_col, "soc_major"
            )

    _make_subplot_figure(
        merged_validation_df,
        "ss_emp",
        emp_periods,
        "Employment Growth Residual (occupation minus sector average)",
        f"{output_dir}/sector_adjusted_employment_growth.png",
    )
    _make_subplot_figure(
        merged_validation_df,
        "ss_wage",
        wage_periods,
        "Wage Growth Residual (occupation minus sector average)",
        f"{output_dir}/sector_adjusted_wage_growth.png",
    )

    print("\n── Shift-Share Correlation Comparison (our impact score) ───────────────")
    header = f"{'Period':<28} {'Metric':<8} {'Raw r':>7} {'SS r':>7} {'Δr':>7}"
    print(header)
    print("-" * len(header))
    for period in emp_periods:
        for growth_type, label in [("emp", "Emp"), ("wage", "Wage")]:
            raw_col = f"{growth_type}_growth_{period}"
            ss_col = f"ss_{growth_type}_growth_{period}"
            if raw_col not in merged_validation_df.columns or ss_col not in merged_validation_df.columns:
                continue
            is_composite = period == "composite"
            raw_clean = _clean(merged_validation_df, raw_col, is_composite).dropna(subset=["occupation_exposure"])
            ss_clean = merged_validation_df.replace([float("inf"), -float("inf")], pd.NA).dropna(subset=[ss_col, "occupation_exposure"])
            if len(raw_clean) < 10 or len(ss_clean) < 10:
                continue
            r_raw, _ = stats.pearsonr(raw_clean["occupation_exposure"], raw_clean[raw_col])
            r_ss, _ = stats.pearsonr(ss_clean["occupation_exposure"], ss_clean[ss_col])
            print(f"{_label(period):<28} {label:<8} {r_raw:>7.3f} {r_ss:>7.3f} {r_ss - r_raw:>+7.3f}")

    # ── Dynamic labor equilibrium model ──────────────────────────────────────
    latest_emp_col = sorted(c for c in merged_validation_df.columns if c.startswith("TOT_EMP_"))[-1]
    dynamic_equilibrium_df = compute_dynamic_equilibrium(merged_validation_df, latest_emp_col)
    dynamic_equilibrium_df.to_csv("data/output/occupation_dynamic_model_report.csv", index=False)
    print("\nSaved dynamic model report → data/output/occupation_dynamic_model_report.csv")
    plot_net_change_distribution(dynamic_equilibrium_df, output_dir)
    plot_winners_losers(dynamic_equilibrium_df, output_dir)
    plot_dynamic_vs_rebound_comparison(dynamic_equilibrium_df, output_dir)

    # Join growth columns from merged_validation_df so the dynamic model can be
    # validated against the same BLS actuals as the rebound-adjusted model.
    growth_cols = [c for c in merged_validation_df.columns if "growth" in c]
    dynamic_validation_df = dynamic_equilibrium_df.merge(
        merged_validation_df[["OCC_CODE"] + growth_cols],
        on="OCC_CODE",
        how="inner",
    )

    _make_subplot_figure(
        dynamic_validation_df,
        "emp",
        emp_periods,
        "Year-over-Year Employment Growth",
        f"{output_dir}/dynamic_model_vs_actual_employment_growth.png",
        score_col="net_employment_change",
        xlabel="Net Employment Change (dynamic model)",
    )
    _make_subplot_figure(
        dynamic_validation_df,
        "wage",
        wage_periods,
        "Year-over-Year Median Wage Growth",
        f"{output_dir}/dynamic_model_vs_actual_wage_growth.png",
        score_col="net_employment_change",
        xlabel="Net Employment Change (dynamic model)",
    )
    _make_subplot_figure(
        dynamic_validation_df,
        "ss_emp",
        emp_periods,
        "Employment Growth Residual (occupation minus sector average)",
        f"{output_dir}/dynamic_model_sector_adjusted_employment_growth.png",
        score_col="net_employment_change",
        xlabel="Net Employment Change (dynamic model)",
    )
    _make_subplot_figure(
        dynamic_validation_df,
        "ss_wage",
        wage_periods,
        "Wage Growth Residual (occupation minus sector average)",
        f"{output_dir}/dynamic_model_sector_adjusted_wage_growth.png",
        score_col="net_employment_change",
        xlabel="Net Employment Change (dynamic model)",
    )
    plot_dynamic_sector_level_validation(dynamic_validation_df, latest_emp_col, output_dir, sector_growth_df=sector_growth_df)

    dynamic_validation_df["soc_major"] = dynamic_validation_df["OCC_CODE"].str[:2]

    if "emp_growth_composite" in dynamic_validation_df.columns:
        equilibration_sensitivity_df = compute_equilibration_sensitivity(
            dynamic_validation_df,
            employment_col=latest_emp_col,
            growth_col="emp_growth_composite",
            soc_major_col="soc_major",
            sector_growth_df=sector_growth_df,
        )
        equilibration_sensitivity_df.to_csv("data/output/equilibration_sensitivity.csv", index=False)
        print("\n── Equilibration sensitivity (sector-level, composite employment growth) ──")
        print("  How much of the headline result depends on the conservation constraint?")
        print(f"  {'× conservation K':>19s} {'absorption K':>13s} {'sector r':>9s} {'p':>8s}")
        for _, sensitivity_row in equilibration_sensitivity_df.iterrows():
            multiplier_label = f"{sensitivity_row['equilibration_multiplier']:.2f}×"
            if sensitivity_row["equilibration_multiplier"] == 0.0:
                multiplier_label += " (no equilib.)"
            elif sensitivity_row["equilibration_multiplier"] == 1.0:
                multiplier_label += " (pinned)"
            print(
                f"  {multiplier_label:>19s} {sensitivity_row['absorption_scalar']:13.4f} "
                f"{sensitivity_row['sector_r']:+9.3f} {sensitivity_row['sector_p']:8.4f}"
            )
        print("  Saved data/output/equilibration_sensitivity.csv")

        sector_jackknife_df = compute_sector_jackknife(
            dynamic_validation_df,
            employment_col=latest_emp_col,
            growth_col="emp_growth_composite",
            score_col="net_employment_change",
            soc_major_col="soc_major",
            sector_growth_df=sector_growth_df,
        )
        sector_jackknife_df.to_csv("data/output/sector_jackknife.csv", index=False)
        weakest_row = sector_jackknife_df.iloc[0]
        strongest_row = sector_jackknife_df.iloc[-1]
        print("\n── Sector jackknife (dynamic model, composite employment growth) ──")
        print("  Leave-one-sector-out range of the headline sector-level r:")
        full_sample_n = weakest_row["n_sectors"] + 1
        print(f"  full sample:  r = {weakest_row['full_sample_r']:+.3f}, p = {weakest_row['full_sample_p']:.3f}, n = {full_sample_n}")
        print(
            f"  weakest:      r = {weakest_row['sector_r']:+.3f}, p = {weakest_row['sector_p']:.3f}  "
            f"dropping {weakest_row['dropped_sector_name']}"
        )
        print(
            f"  strongest:    r = {strongest_row['sector_r']:+.3f}, p = {strongest_row['sector_p']:.3f}  "
            f"dropping {strongest_row['dropped_sector_name']}"
        )
        decisive_df = sector_jackknife_df[sector_jackknife_df["sector_p"] >= 0.05]
        if decisive_df.empty:
            print("  No single sector's removal takes the result above p = 0.05.")
        else:
            print(f"  Removal takes the result above p = 0.05 for: {', '.join(decisive_df['dropped_sector_name'])}")
        print("  Saved data/output/sector_jackknife.csv")

    _make_sector_subplot_figure(
        dynamic_validation_df,
        score_col="net_employment_change",
        growth_type="emp",
        periods=emp_periods,
        employment_col=latest_emp_col,
        soc_major_col="soc_major",
        output_path=f"{output_dir}/dynamic_sector_level_employment_validation.png",
        xlabel="Sector Mean Net Employment Change (dynamic model)",
        ylabel="Sector Mean Employment Growth",
        suptitle="Sector-Level Validation: Dynamic Net Employment Change vs. Employment Growth",
        sector_growth_df=sector_growth_df,
    )
    _make_sector_subplot_figure(
        dynamic_validation_df,
        score_col="net_employment_change",
        growth_type="wage",
        periods=wage_periods,
        employment_col=latest_emp_col,
        soc_major_col="soc_major",
        output_path=f"{output_dir}/dynamic_sector_level_wage_validation.png",
        xlabel="Sector Mean Net Employment Change (dynamic model)",
        ylabel="Sector Mean Wage Growth",
        suptitle="Sector-Level Validation: Dynamic Net Employment Change vs. Wage Growth",
        sector_growth_df=sector_growth_df,
    )

    # ── Model signal over time (historical baseline) ─────────────────────────
    _anthropic_exp_df = (
        pd.read_csv("data/raw/anthropic_job_exposure.csv").rename(columns={"occ_code": "OCC_CODE"})
        if os.path.exists("data/raw/anthropic_job_exposure.csv")
        else None
    )
    # Loaded without an output path here: the CPS block near the end of main() owns
    # writing the merged panel, and this call only needs to read it.
    signal_cps_panel_df = load_cps_panel(output_path=None)
    plot_model_signal_over_time(
        merged_validation_df, dynamic_validation_df, output_dir, _anthropic_exp_df, signal_cps_panel_df, sector_growth_df=sector_growth_df
    )
    plot_model_signal_over_time_occupation(
        merged_validation_df,
        dynamic_validation_df,
        output_dir,
        _anthropic_exp_df,
        harmonized_trends_df=harmonized_trends_df,
        unit_membership_df=unit_membership_df,
    )

    # ── AI exposure volume ────────────────────────────────────────────────────
    # exposure_volume = (occupation employment / total modeled employment) × mean_penetration
    # Gives each occupation's contribution to economy-wide AI exposure as a fraction of total employment.
    latest_year = latest_emp_col.replace("TOT_EMP_", "20")
    exposure_volume_df = merged_validation_df.dropna(subset=[latest_emp_col, "mean_penetration"]).copy()
    total_modeled_emp = exposure_volume_df[latest_emp_col].sum()
    exposure_volume_df["employment_share"] = exposure_volume_df[latest_emp_col] / total_modeled_emp
    exposure_volume_df["exposure_volume"] = exposure_volume_df["employment_share"] * exposure_volume_df["mean_penetration"]

    # Occupation-level CSV
    occupation_exposure_save_df = exposure_volume_df[
        [
            "OCC_CODE",
            "Title",
            "dominant_demand",
            "dominant_strength",
            latest_emp_col,
            "employment_share",
            "mean_penetration",
            "exposure_volume",
        ]
    ].sort_values("exposure_volume", ascending=False)
    occupation_exposure_save_df.to_csv("data/output/exposure_volume_by_occupation.csv", index=False)

    # Group-level rollup — dominant demand is whichever type accumulates the most exposure_volume in the group
    exposure_volume_df["soc_major"] = exposure_volume_df["OCC_CODE"].str.split("-").str[0]

    group_demand_df = exposure_volume_df.groupby(["soc_major", "dominant_demand"])["exposure_volume"].sum().reset_index()
    group_dominant_demand_df = group_demand_df.loc[
        group_demand_df.groupby("soc_major")["exposure_volume"].idxmax(),
        ["soc_major", "dominant_demand"],
    ].rename(columns={"dominant_demand": "group_dominant_demand"})

    group_rollup_df = (
        exposure_volume_df.groupby("soc_major")
        .agg(
            group_name=("soc_major", lambda codes: SOC_MAJOR_GROUPS.get(codes.iloc[0], "Other")),
            total_employment=(latest_emp_col, "sum"),
            employment_share=("employment_share", "sum"),
            avg_penetration=("mean_penetration", "mean"),
            total_exposure_volume=("exposure_volume", "sum"),
            n_occupations=("Title", "count"),
        )
        .reset_index()
        .merge(group_dominant_demand_df, on="soc_major")
        .sort_values("total_exposure_volume", ascending=False)
        .reset_index(drop=True)
    )
    total_all_exposure = group_rollup_df["total_exposure_volume"].sum()
    group_rollup_df["pct_of_total_exposure"] = group_rollup_df["total_exposure_volume"] / total_all_exposure
    group_rollup_df.to_csv("data/output/exposure_volume_by_group.csv", index=False)

    def _exposure_bar_chart(plot_df: pd.DataFrame, value_col: str, xlabel: str, title: str, output_path: str) -> None:
        sorted_df = plot_df.sort_values(value_col, ascending=True)
        bar_colors = [DEMAND_PALETTE.get(demand_type, "grey") for demand_type in sorted_df["group_dominant_demand"]]
        fig, ax = plt.subplots(figsize=(12, 9))
        bars = ax.barh(sorted_df["group_name"], sorted_df[value_col], color=bar_colors, alpha=0.85)
        ax.set_xlabel(xlabel, fontsize=10)
        ax.set_title(title, fontsize=12)
        ax.xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=1))
        legend_handles = [Patch(facecolor=color, label=demand_type) for demand_type, color in DEMAND_PALETTE.items()]
        ax.legend(handles=legend_handles, title="Dominant Demand Type", fontsize=9, title_fontsize=9, loc="lower right")
        for bar, (_, row) in zip(bars, sorted_df.iterrows()):
            ax.text(
                bar.get_width() + 0.001,
                bar.get_y() + bar.get_height() / 2,
                f"{row[value_col]:.1%}",
                va="center",
                fontsize=8,
                color="dimgrey",
            )
        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()

    _exposure_bar_chart(
        group_rollup_df,
        "total_exposure_volume",
        f"Employment Share × Mean Penetration ({latest_year} employment, %)",
        f"Employment-Weighted AI Exposure by Occupational Group ({latest_year})\nColored by dominant demand type",
        f"{output_dir}/exposure_volume_by_group.png",
    )
    _exposure_bar_chart(
        group_rollup_df,
        "pct_of_total_exposure",
        "Share of Total AI Exposure Volume (%)",
        f"Share of Total AI Exposure Volume by Occupational Group ({latest_year})\nColored by dominant demand type",
        f"{output_dir}/exposure_share_by_group.png",
    )

    # Console summary
    print(f"\n── AI Exposure Volume by Occupation — Top 20 ({latest_emp_col}) ──")
    top_exposure_display_df = occupation_exposure_save_df.head(20).copy()
    top_exposure_display_df[latest_emp_col] = top_exposure_display_df[latest_emp_col].map("{:,.0f}".format)
    top_exposure_display_df["employment_share"] = top_exposure_display_df["employment_share"].map("{:.2%}".format)
    top_exposure_display_df["mean_penetration"] = top_exposure_display_df["mean_penetration"].map("{:.0%}".format)
    top_exposure_display_df["exposure_volume"] = top_exposure_display_df["exposure_volume"].map("{:.3%}".format)
    print(
        top_exposure_display_df[["Title", "dominant_demand", "employment_share", "mean_penetration", "exposure_volume"]].to_string(
            index=False
        )
    )

    print("\n── AI Exposure Volume by Occupational Group ──")
    group_display_df = group_rollup_df.copy()
    group_display_df["total_employment"] = group_display_df["total_employment"].map("{:,.0f}".format)
    group_display_df["employment_share"] = group_display_df["employment_share"].map("{:.1%}".format)
    group_display_df["avg_penetration"] = group_display_df["avg_penetration"].map("{:.0%}".format)
    group_display_df["total_exposure_volume"] = group_display_df["total_exposure_volume"].map("{:.2%}".format)
    group_display_df["pct_of_total_exposure"] = group_display_df["pct_of_total_exposure"].map("{:.1%}".format)
    print(
        group_display_df[
            ["group_name", "group_dominant_demand", "employment_share", "avg_penetration", "total_exposure_volume", "pct_of_total_exposure"]
        ].to_string(index=False)
    )

    # ── Employment by dominant demand type ───────────────────────────────────
    demand_emp_df = (
        exposure_volume_df.groupby("dominant_demand")
        .agg(
            total_workers=(latest_emp_col, "sum"),
            mean_exposure=("occupation_exposure", "mean"),
            n_occupations=("OCC_CODE", "count"),
        )
        .reindex(["Bounded", "Unbounded", "Adversarial"])
        .reset_index()
    )
    demand_emp_df["pct_of_modeled"] = demand_emp_df["total_workers"] / demand_emp_df["total_workers"].sum()
    demand_emp_df["workers_millions"] = demand_emp_df["total_workers"] / 1e6
    demand_emp_df.to_csv("data/output/employment_by_demand_type.csv", index=False)

    fig, ax = plt.subplots(figsize=(9, 7))
    emp_bars = ax.bar(
        range(3),
        demand_emp_df["workers_millions"],
        color=[DEMAND_PALETTE[d] for d in demand_emp_df["dominant_demand"]],
        alpha=0.85,
        width=0.55,
    )
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels(demand_emp_df["dominant_demand"], fontsize=11)
    ax.set_ylabel("Workers (millions)", fontsize=10)
    # extra headroom so annotations don't collide with the title
    ax.set_ylim(0, demand_emp_df["workers_millions"].max() * 1.35)
    ax.set_title(
        f"U.S. Workers by Dominant AI Demand Type ({latest_year})\n"
        "Classified by the demand type with the most task importance weight\n"
        "Higher score = greater structural AI exposure (non-negative; does not predict net demand direction)",
        fontsize=10,
        pad=12,
    )
    for bar, (_, row) in zip(emp_bars, demand_emp_df.iterrows()):
        label = f"{row['workers_millions']:.1f}M\n({row['pct_of_modeled']:.0%} of modeled)\nMean exposure: {row['mean_exposure']:.1%}"
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.8, label, ha="center", va="bottom", fontsize=9)
    plt.tight_layout()
    plt.savefig(f"{output_dir}/employment_by_demand_type.png", dpi=300, bbox_inches="tight")
    plt.close()

    print("\n── Employment by Dominant Demand Type ──")
    emp_display_df = demand_emp_df.copy()
    emp_display_df["workers_millions"] = emp_display_df["workers_millions"].map("{:.1f}M".format)
    emp_display_df["pct_of_modeled"] = emp_display_df["pct_of_modeled"].map("{:.0%}".format)
    emp_display_df["mean_exposure"] = emp_display_df["mean_exposure"].map("{:.1%}".format)
    print(
        emp_display_df[["dominant_demand", "workers_millions", "pct_of_modeled", "mean_exposure", "n_occupations"]].to_string(index=False)
    )

    # ── Wage quartile × demand type ──────────────────────────────────────────
    latest_wage_col = f"A_MEDIAN_{latest_emp_col.replace('TOT_EMP_', '')}"
    wage_quartile_df = merged_validation_df.dropna(subset=[latest_wage_col, latest_emp_col, "dominant_demand"]).copy()
    wage_quartile_df = wage_quartile_df.sort_values(latest_wage_col).reset_index(drop=True)

    # Employment-weighted quartiles: each quartile spans ~25% of total worker-count
    wage_quartile_df["cum_emp"] = wage_quartile_df[latest_emp_col].cumsum()
    total_wq_emp = wage_quartile_df[latest_emp_col].sum()
    quartile_labels = ["Q1 (lowest wages)", "Q2", "Q3", "Q4 (highest wages)"]
    wage_quartile_df["quartile"] = pd.cut(
        wage_quartile_df["cum_emp"] / total_wq_emp,
        bins=[0, 0.25, 0.5, 0.75, 1.01],
        labels=quartile_labels,
        include_lowest=True,
    )

    # Employment-weighted demand type share within each quartile
    quartile_demand_emp = wage_quartile_df.groupby(["quartile", "dominant_demand"])[latest_emp_col].sum().reset_index()
    quartile_total_emp = quartile_demand_emp.groupby("quartile")[latest_emp_col].sum().rename("quartile_total")
    quartile_demand_emp = quartile_demand_emp.merge(quartile_total_emp, on="quartile")
    quartile_demand_emp["share"] = quartile_demand_emp[latest_emp_col] / quartile_demand_emp["quartile_total"]

    # Employment-weighted mean impact per quartile
    quartile_impact_series = (
        wage_quartile_df.groupby("quartile")
        .apply(lambda g: (g["occupation_exposure"] * g[latest_emp_col]).sum() / g[latest_emp_col].sum())
        .rename("weighted_impact")
        .reindex(quartile_labels)
    )

    pivot_wq = quartile_demand_emp.pivot(index="quartile", columns="dominant_demand", values="share").fillna(0)
    pivot_wq = pivot_wq.reindex(quartile_labels)
    for col in ["Bounded", "Unbounded", "Adversarial"]:
        if col not in pivot_wq.columns:
            pivot_wq[col] = 0.0

    fig, (ax_stack, ax_impact) = plt.subplots(1, 2, figsize=(14, 6))

    bottom = np.zeros(len(quartile_labels))
    for demand_type in ["Bounded", "Unbounded", "Adversarial"]:
        vals = pivot_wq[demand_type].values
        ax_stack.bar(range(4), vals, bottom=bottom, color=DEMAND_PALETTE[demand_type], label=demand_type, alpha=0.85)
        for i, (v, b) in enumerate(zip(vals, bottom)):
            if v > 0.06:
                ax_stack.text(i, b + v / 2, f"{v:.0%}", ha="center", va="center", fontsize=8.5, color="white", fontweight="bold")
        bottom += vals

    ax_stack.set_xticks([0, 1, 2, 3])
    ax_stack.set_xticklabels(quartile_labels, fontsize=9)
    ax_stack.set_ylabel("Share of Workers in Quartile", fontsize=10)
    ax_stack.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    ax_stack.set_title(f"Demand Type by Wage Quartile ({latest_year})\n(employment-weighted; each quartile ≈ 25% of workers)", fontsize=11)
    legend_handles_wq = [Patch(facecolor=DEMAND_PALETTE[d], label=d) for d in ["Bounded", "Unbounded", "Adversarial"]]
    ax_stack.legend(handles=legend_handles_wq, title="Demand Type", fontsize=9)

    impact_bars = ax_impact.bar(range(4), quartile_impact_series.values, color="#1a9850", alpha=0.85, width=0.55)
    ax_impact.set_xticks([0, 1, 2, 3])
    ax_impact.set_xticklabels(quartile_labels, fontsize=9)
    ax_impact.axhline(0, color="black", linewidth=0.8)
    ax_impact.set_ylabel("Employment-Weighted Mean Impact Score", fontsize=10)
    ax_impact.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=1))
    ax_impact.set_title(f"Mean Rebound-Adjusted Exposure Score by Wage Quartile ({latest_year})\n(employment-weighted)", fontsize=11)
    for bar, val in zip(impact_bars, quartile_impact_series.values):
        ax_impact.text(
            bar.get_x() + bar.get_width() / 2,
            val + 0.001,
            f"{val:.1%}",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    plt.tight_layout()
    plt.savefig(f"{output_dir}/wage_quartile_demand_type.png", dpi=300, bbox_inches="tight")
    plt.close()

    # ── Anthropic observed exposure vs. our model impact ─────────────────────
    anthropic_job_path = "data/raw/anthropic_job_exposure.csv"
    if os.path.exists(anthropic_job_path):
        anthropic_exp_df = pd.read_csv(anthropic_job_path)
        anthropic_merged_df = aggregated_exposure_df.merge(
            anthropic_exp_df[["occ_code", "observed_exposure"]],
            left_on="OCC_CODE",
            right_on="occ_code",
            how="inner",
        ).dropna(subset=["occupation_exposure", "observed_exposure", "dominant_demand"])

        pearson_r, pearson_p = stats.pearsonr(anthropic_merged_df["observed_exposure"], anthropic_merged_df["occupation_exposure"])

        plt.figure(figsize=(12, 10))
        sns.scatterplot(
            data=anthropic_merged_df,
            x="observed_exposure",
            y="occupation_exposure",
            hue="dominant_demand",
            palette=DEMAND_PALETTE,
            alpha=0.55,
            s=20,
        )
        # High-coverage occupations with high displacement impact (Bounded-dominated)
        high_impact_outliers = anthropic_merged_df.nlargest(5, "occupation_exposure")
        # High-coverage occupations where rebound keeps model impact low (Adversarial/Unbounded)
        low_impact_outliers = anthropic_merged_df[anthropic_merged_df["observed_exposure"] > 0.3].nsmallest(3, "occupation_exposure")
        for _, row in pd.concat([high_impact_outliers, low_impact_outliers]).drop_duplicates("OCC_CODE").iterrows():
            plt.annotate(
                row["Title"],
                (row["observed_exposure"], row["occupation_exposure"]),
                xytext=(10, 5),
                textcoords="offset points",
                fontsize=7.5,
                alpha=0.9,
                arrowprops={"arrowstyle": "->", "color": "grey", "lw": 0.7},
            )

        plt.title(
            f"Observed AI Task Coverage vs. Rebound-Adjusted Exposure Score\n"
            f"Pearson r = {pearson_r:.3f} (p = {pearson_p:.3f}, n = {len(anthropic_merged_df)})",
            fontsize=13,
        )
        plt.xlabel("Observed AI Task Coverage (share of occupation's tasks covered by Claude conversations)", fontsize=11)
        plt.ylabel("Model Occupation Impact Score", fontsize=11)
        plt.gca().xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
        plt.gca().yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
        plt.legend(title="Dominant Demand Type")
        plt.tight_layout()
        plt.savefig(f"{output_dir}/observed_vs_rebound_adjusted_exposure.png", dpi=300)
        plt.close()

        print(f"\n── Anthropic Exposure vs. Our Impact (n={len(anthropic_merged_df)}) ──")
        print(f"Pearson r = {pearson_r:.3f}, p = {pearson_p:.4f}")

        # Sector-level validation for Anthropic observed exposure
        anthropic_sector_df = anthropic_merged_df.merge(
            merged_validation_df[["OCC_CODE", "soc_major", latest_emp_col] + [c for c in merged_validation_df.columns if "growth" in c]],
            on="OCC_CODE",
            how="inner",
        )
        _make_sector_subplot_figure(
            anthropic_sector_df,
            score_col="observed_exposure",
            growth_type="emp",
            periods=emp_periods,
            employment_col=latest_emp_col,
            soc_major_col="soc_major",
            output_path=f"{output_dir}/anthropic_observed_sector_level_employment_validation.png",
            xlabel="Sector Mean Observed AI Task Coverage",
            ylabel="Sector Mean Employment Growth",
            suptitle="Sector-Level Validation: Anthropic Observed Exposure vs. Employment Growth",
            sector_growth_df=sector_growth_df,
        )
        _make_sector_subplot_figure(
            anthropic_sector_df,
            score_col="observed_exposure",
            growth_type="wage",
            periods=wage_periods,
            employment_col=latest_emp_col,
            soc_major_col="soc_major",
            output_path=f"{output_dir}/anthropic_observed_sector_level_wage_validation.png",
            xlabel="Sector Mean Observed AI Task Coverage",
            ylabel="Sector Mean Wage Growth",
            suptitle="Sector-Level Validation: Anthropic Observed Exposure vs. Wage Growth",
            sector_growth_df=sector_growth_df,
        )

    # ── Sector-level validation ───────────────────────────────────────────────
    if "emp_growth_composite" in merged_validation_df.columns:
        sector_source_df = merged_validation_df.dropna(subset=[latest_emp_col]).copy()
        sector_source_df["soc_group"] = sector_source_df["soc_major"].map(SOC_MAJOR_GROUPS).fillna("Other")

        def _sector_weighted_mean(col: str) -> pd.Series:
            valid = sector_source_df.dropna(subset=[col])
            return valid.groupby("soc_group").apply(lambda g: (g[col] * g[latest_emp_col]).sum() / g[latest_emp_col].sum())

        sector_agg_df = pd.DataFrame(
            {
                "sector_exposure": _sector_weighted_mean("occupation_exposure"),
                "emp_growth": _sector_weighted_mean("emp_growth_composite"),
                "wage_growth": _sector_weighted_mean("wage_growth_composite"),
            }
        )
        group_to_major = sector_source_df.drop_duplicates("soc_group").set_index("soc_group")["soc_major"]
        composite_major_index = pd.Index(group_to_major.reindex(sector_agg_df.index).values)
        for growth_key, growth_col in [("emp_growth", "emp_growth_composite"), ("wage_growth", "wage_growth_composite")]:
            total_growth = sector_growth_series(sector_growth_df, growth_col, composite_major_index)
            if total_growth is not None:
                sector_agg_df[growth_key] = total_growth.values
        sector_agg_df = sector_agg_df.reset_index()
        sector_agg_df = sector_agg_df.merge(
            sector_source_df.groupby("soc_group")[latest_emp_col].sum().rename("total_emp").reset_index(),
            on="soc_group",
        )
        sector_dominant_df = (
            sector_source_df.groupby(["soc_group", "dominant_demand"])[latest_emp_col]
            .sum()
            .reset_index()
            .sort_values(latest_emp_col, ascending=False)
            .drop_duplicates("soc_group")[["soc_group", "dominant_demand"]]
        )
        sector_agg_df = sector_agg_df.merge(sector_dominant_df, on="soc_group").dropna(
            subset=["sector_exposure", "emp_growth", "wage_growth"]
        )

        sector_r_emp, sector_p_emp = stats.pearsonr(sector_agg_df["sector_exposure"], sector_agg_df["emp_growth"])
        sector_r_wage, sector_p_wage = stats.pearsonr(sector_agg_df["sector_exposure"], sector_agg_df["wage_growth"])

        fig, (ax_emp_s, ax_wage_s) = plt.subplots(1, 2, figsize=(16, 8))
        bubble_size_scale = 1500 / sector_agg_df["total_emp"].max()

        for ax_s, growth_col_s, r_s, p_s, ylabel_s in [
            (ax_emp_s, "emp_growth", sector_r_emp, sector_p_emp, "Composite Employment Growth"),
            (ax_wage_s, "wage_growth", sector_r_wage, sector_p_wage, "Composite Wage Growth"),
        ]:
            bubble_colors_s = [DEMAND_PALETTE.get(d, "grey") for d in sector_agg_df["dominant_demand"]]
            ax_s.scatter(
                sector_agg_df["sector_exposure"],
                sector_agg_df[growth_col_s],
                s=(sector_agg_df["total_emp"] * bubble_size_scale).clip(30),
                c=bubble_colors_s,
                alpha=0.75,
                edgecolors="white",
                linewidths=0.5,
            )
            for _, row_s in sector_agg_df.iterrows():
                ax_s.annotate(
                    row_s["soc_group"],
                    (row_s["sector_exposure"], row_s[growth_col_s]),
                    xytext=(5, 3),
                    textcoords="offset points",
                    fontsize=6.5,
                    alpha=0.85,
                )
            ax_s.axhline(0, color="grey", linestyle="--", linewidth=0.8)
            ax_s.axvline(0, color="grey", linestyle="--", linewidth=0.8)
            ax_s.set_xlabel("Sector Mean Impact Score (employment-weighted)", fontsize=10)
            ax_s.set_ylabel(ylabel_s, fontsize=10)
            ax_s.set_title(f"r = {r_s:.3f}, p = {p_s:.3f}, n = {len(sector_agg_df)}", fontsize=11)
            ax_s.xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
            ax_s.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))

        legend_handles_s = [Patch(facecolor=color, label=demand_type) for demand_type, color in DEMAND_PALETTE.items()]
        ax_wage_s.legend(handles=legend_handles_s, title="Dominant Demand Type", fontsize=8)
        fig.suptitle(
            "Sector-Level Validation: Employment-Weighted Model Impact vs. Observed Growth\n"
            "(bubble size ∝ sector employment; growth = BLS major-group totals)",
            fontsize=12,
        )
        plt.tight_layout()
        plt.savefig(f"{output_dir}/sector_level_validation.png", dpi=300, bbox_inches="tight")
        plt.close()

        print(f"\n── Sector-Level Validation (n={len(sector_agg_df)}) ──")
        print(f"Employment: r = {sector_r_emp:.3f}, p = {sector_p_emp:.3f}")
        print(f"Wage:       r = {sector_r_wage:.3f}, p = {sector_p_wage:.3f}")

        merged_validation_df["soc_group"] = merged_validation_df["soc_major"].map(SOC_MAJOR_GROUPS).fillna("Other")
        _make_sector_subplot_figure(
            merged_validation_df,
            score_col="occupation_exposure",
            growth_type="emp",
            periods=emp_periods,
            employment_col=latest_emp_col,
            soc_major_col="soc_major",
            output_path=f"{output_dir}/sector_level_employment_validation.png",
            xlabel="Sector Mean Rebound-Adjusted Exposure Score",
            ylabel="Sector Mean Employment Growth",
            suptitle="Sector-Level Validation: Rebound-Adjusted Exposure vs. Employment Growth",
            sector_growth_df=sector_growth_df,
        )
        _make_sector_subplot_figure(
            merged_validation_df,
            score_col="occupation_exposure",
            growth_type="wage",
            periods=wage_periods,
            employment_col=latest_emp_col,
            soc_major_col="soc_major",
            output_path=f"{output_dir}/sector_level_wage_validation.png",
            xlabel="Sector Mean Rebound-Adjusted Exposure Score",
            ylabel="Sector Mean Wage Growth",
            suptitle="Sector-Level Validation: Rebound-Adjusted Exposure vs. Wage Growth",
            sector_growth_df=sector_growth_df,
        )

        # Sector-level validation for Eloundou theoretical exposure
        if "eloundou_exposure_mid" in merged_validation_df.columns:
            _make_sector_subplot_figure(
                merged_validation_df,
                score_col="eloundou_exposure_mid",
                growth_type="emp",
                periods=emp_periods,
                employment_col=latest_emp_col,
                soc_major_col="soc_major",
                output_path=f"{output_dir}/eloundou_sector_level_employment_validation.png",
                xlabel="Sector Mean Eloundou Theoretical Exposure",
                ylabel="Sector Mean Employment Growth",
                suptitle="Sector-Level Validation: Eloundou Theoretical Exposure vs. Employment Growth",
                sector_growth_df=sector_growth_df,
            )
            _make_sector_subplot_figure(
                merged_validation_df,
                score_col="eloundou_exposure_mid",
                growth_type="wage",
                periods=wage_periods,
                employment_col=latest_emp_col,
                soc_major_col="soc_major",
                output_path=f"{output_dir}/eloundou_sector_level_wage_validation.png",
                xlabel="Sector Mean Eloundou Theoretical Exposure",
                ylabel="Sector Mean Wage Growth",
                suptitle="Sector-Level Validation: Eloundou Theoretical Exposure vs. Wage Growth",
                sector_growth_df=sector_growth_df,
            )

    # ── Employment trajectories for top-risk occupations ─────────────────────
    top_risk_df = aggregated_exposure_df.nlargest(10, "occupation_exposure")[["OCC_CODE", "Title", "occupation_exposure"]]
    trajectory_emp_cols = [c for c in ["TOT_EMP_22", "TOT_EMP_23", "TOT_EMP_24", "TOT_EMP_25"] if c in bls_trends_df.columns]
    trajectory_years = [int("20" + c.replace("TOT_EMP_", "")) for c in trajectory_emp_cols]
    trajectory_df = top_risk_df.merge(bls_trends_df[["OCC_CODE"] + trajectory_emp_cols], on="OCC_CODE", how="inner")

    fig, ax_traj = plt.subplots(figsize=(14, 9))
    color_cycle = plt.cm.tab10.colors

    for i, (_, occ_row) in enumerate(trajectory_df.iterrows()):
        emp_values = [occ_row[c] for c in trajectory_emp_cols]
        if any(pd.isna(v) for v in emp_values) or emp_values[0] == 0:
            continue
        base_emp = emp_values[0]
        indexed = [v / base_emp * 100 for v in emp_values]
        color = color_cycle[i % len(color_cycle)]
        ax_traj.plot(trajectory_years, indexed, color=color, linewidth=1.8, marker="o", markersize=4)
        actual_change = (emp_values[-1] - base_emp) / base_emp
        endpoint_label = f"{occ_row['Title'][:32]}\nmodel: {occ_row['occupation_exposure']:.0%} / actual: {actual_change:.0%}"
        ax_traj.annotate(
            endpoint_label,
            (trajectory_years[-1], indexed[-1]),
            xytext=(7, 0),
            textcoords="offset points",
            fontsize=6.5,
            color=color,
            va="center",
        )

    ax_traj.axhline(100, color="black", linestyle="--", linewidth=1, label="2022 baseline")
    ax_traj.set_xlabel("Year", fontsize=10)
    ax_traj.set_ylabel("Employment (indexed to 2022 = 100)", fontsize=10)
    ax_traj.set_title(
        "Employment Trajectories: Top 10 At-Risk Occupations (2022–2025)\n"
        "(model prediction vs. actual BLS employment, indexed to 100 at 2022)",
        fontsize=12,
    )
    ax_traj.set_xticks(trajectory_years)
    plt.tight_layout()
    plt.savefig(f"{output_dir}/top_exposure_trajectories.png", dpi=300, bbox_inches="tight")
    plt.close()

    # ── High-risk concentration bubble chart ─────────────────────────────────
    occ_pct_bounded_df = (
        occupation_exposure_df.assign(OCC_CODE=occupation_exposure_df["O*NET-SOC Code"].astype(str).str.split(".").str[0])
        .groupby("OCC_CODE")
        .agg(pct_bounded=("pct_bounded", "mean"), dominant_demand=("dominant_demand", "first"), Title=("Title", "first"))
        .reset_index()
    )
    bubble_df = occ_pct_bounded_df.merge(
        exposure_volume_df[["OCC_CODE", "employment_share", "exposure_volume", "mean_penetration"]],
        on="OCC_CODE",
        how="inner",
    )
    bubble_df["displacement_pressure"] = bubble_df["pct_bounded"] * bubble_df["mean_penetration"]
    high_risk_bubble_df = bubble_df[bubble_df["displacement_pressure"] > 0.05].copy()

    top_annotate_df = high_risk_bubble_df.nlargest(15, "exposure_volume")
    bubble_colors = [DEMAND_PALETTE.get(d, "grey") for d in high_risk_bubble_df["dominant_demand"]]

    fig, ax_bubble = plt.subplots(figsize=(14, 10))
    ax_bubble.scatter(
        high_risk_bubble_df["displacement_pressure"],
        high_risk_bubble_df["employment_share"],
        s=(high_risk_bubble_df["exposure_volume"] * 50000).clip(10),
        c=bubble_colors,
        alpha=0.65,
        edgecolors="white",
        linewidths=0.5,
    )
    for _, row_b in top_annotate_df.iterrows():
        ax_bubble.annotate(
            row_b["Title"][:35],
            (row_b["displacement_pressure"], row_b["employment_share"]),
            xytext=(8, 0),
            textcoords="offset points",
            fontsize=7,
            alpha=0.9,
        )
    ax_bubble.set_xlabel("Structural Exposure Pressure (share of Bounded tasks × mean AI penetration)", fontsize=10)
    ax_bubble.set_ylabel("Employment Share of Modeled Workforce", fontsize=10)
    ax_bubble.set_title(
        f"High-Risk Occupation Concentration (structural exposure pressure > 5%)\n"
        f"Bubble size ∝ AI exposure volume; n = {len(high_risk_bubble_df)} occupations",
        fontsize=12,
    )
    ax_bubble.xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    ax_bubble.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=2))
    legend_handles_b = [Patch(facecolor=color, label=demand_type) for demand_type, color in DEMAND_PALETTE.items()]
    ax_bubble.legend(handles=legend_handles_b, title="Dominant Demand Type", fontsize=9)
    plt.tight_layout()
    plt.savefig(f"{output_dir}/high_exposure_concentration.png", dpi=300, bbox_inches="tight")
    plt.close()

    # ── CPS 2026 directional indicator + model comparison ────────────────────
    cps_growth = _load_cps_growth()
    if cps_growth is not None:
        cps_growth_df, cps_windows = cps_growth
        _plot_cps_2026_direction(output_dir, cps_growth_df, cps_windows, group_rollup_df)
        _plot_cps_model_vs_actual(
            output_dir,
            cps_growth_df,
            cps_windows,
            merged_validation_df,
            group_rollup_df,
            score_col="occupation_exposure",
            xlabel="Employment-Weighted Mean Rebound-Adjusted Exposure Score",
            output_filename="cps_rebound_model_vs_actual.png",
        )
        _plot_cps_model_vs_actual(
            output_dir,
            cps_growth_df,
            cps_windows,
            dynamic_validation_df,
            group_rollup_df,
            score_col="net_employment_change",
            xlabel="Employment-Weighted Mean Net Employment Change (dynamic model)",
            output_filename="cps_dynamic_model_vs_actual.png",
        )
    else:
        print("  Skipping CPS charts — no CPS panel available.")
        print("  Expected seeds/cps_a19_panel.csv, or run: node download_cps.js (or make download-data).")


if __name__ == "__main__":
    main()
