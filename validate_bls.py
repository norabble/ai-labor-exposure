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
  • data/raw/cps/table_a19.html         (optional — from download_data.py)

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
  • cps_2026_direction.png                    — CPS Apr 2025→Apr 2026 employment direction by major group
  • cps_model_vs_actual.png                   — scatter: employment-weighted exposure score vs. CPS growth, major group level
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

from plot_constants import DEMAND_PALETTE, SOC_MAJOR_GROUPS
from synthesize_dynamic import (
    compute_dynamic_equilibrium,
    plot_dynamic_sector_level_validation,
    plot_dynamic_vs_rebound_comparison,
    plot_net_change_distribution,
    plot_winners_losers,
)


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
) -> None:
    """
    2×2 grid of sector-level bubble scatters, one panel per period.
    Each panel: employment-weighted sector mean of score_col (x) vs. sector mean
    growth (y). Bubble size ∝ sector employment; sectors labeled by name.
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
                    "sector_score": _weighted_mean(score_col, group_df),
                    "sector_growth": _weighted_mean(growth_col, group_df),
                    "total_emp": group_df[employment_col].sum(),
                    "dominant_demand": group_df.groupby("dominant_demand")[employment_col].sum().idxmax(),
                }
            )
        sector_agg_df = pd.DataFrame(sector_agg_rows).dropna(subset=["sector_score", "sector_growth"])

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


# CPS Table A-19 group name (lowercased) → SOC 2-digit major group code
_CPS_TO_SOC_MAJOR: dict[str, str] = {
    "management occupations": "11",
    "business and financial operations occupations": "13",
    "computer and mathematical occupations": "15",
    "architecture and engineering occupations": "17",
    "life, physical, and social science occupations": "19",
    "community and social service occupations": "21",
    "legal occupations": "23",
    "education, training, and library occupations": "25",
    "arts, design, entertainment, sports, and media occupations": "27",
    "healthcare practitioners and technical occupations": "29",
    "healthcare support occupations": "31",
    "protective service occupations": "33",
    "food preparation and serving related occupations": "35",
    "building and grounds cleaning and maintenance occupations": "37",
    "personal care and service occupations": "39",
    "sales and related occupations": "41",
    "office and administrative support occupations": "43",
    "farming, fishing, and forestry occupations": "45",
    "construction and extraction occupations": "47",
    "installation, maintenance, and repair occupations": "49",
    "production occupations": "51",
    "transportation and material moving occupations": "53",
}


def _parse_cps_a19() -> pd.DataFrame | None:
    """Parse CPS Table A-19 HTML; return DataFrame with soc_major + emp_growth_apr25_apr26, or None."""
    cps_path = "data/raw/cps/table_a19.html"
    if not os.path.exists(cps_path):
        return None

    raw_cps_df = pd.read_html(cps_path, flavor="bs4")[0]

    # Multi-level columns: col 0 = occupation name, col 1 = Total 16+ Apr 2025, col 2 = Total 16+ Apr 2026
    cps_parsed_df = raw_cps_df.iloc[:, [0, 1, 2]].copy()
    cps_parsed_df.columns = ["occupation", "apr_2025", "apr_2026"]
    cps_parsed_df = cps_parsed_df.dropna(subset=["occupation"])
    cps_parsed_df["soc_major"] = cps_parsed_df["occupation"].str.lower().str.strip().map(_CPS_TO_SOC_MAJOR)
    cps_mapped_df = cps_parsed_df.dropna(subset=["soc_major"]).copy()
    cps_mapped_df["apr_2025"] = pd.to_numeric(cps_mapped_df["apr_2025"], errors="coerce")
    cps_mapped_df["apr_2026"] = pd.to_numeric(cps_mapped_df["apr_2026"], errors="coerce")
    cps_mapped_df = cps_mapped_df.dropna(subset=["apr_2025", "apr_2026"])
    cps_mapped_df["emp_growth_apr25_apr26"] = (cps_mapped_df["apr_2026"] - cps_mapped_df["apr_2025"]) / cps_mapped_df["apr_2025"]
    return cps_mapped_df.reset_index(drop=True)


def _plot_cps_2026_direction(output_dir: str, cps_mapped_df: pd.DataFrame, exposure_group_df: pd.DataFrame) -> None:
    """Horizontal bar chart of CPS major group employment direction (Apr 2025 → Apr 2026)."""
    group_demand_df = exposure_group_df[["soc_major", "group_dominant_demand"]].copy()
    group_demand_df["soc_major"] = group_demand_df["soc_major"].astype(str)
    cps_chart_df = cps_mapped_df.merge(group_demand_df, on="soc_major", how="left")
    cps_chart_df = cps_chart_df.sort_values("emp_growth_apr25_apr26", ascending=True)

    print("\n── CPS Table A-19: Major Group Employment Direction (Apr 2025 → Apr 2026) ──")
    print("   (CPS monthly survey — directional indicator only; not BLS OEWS)\n")
    display_df = cps_chart_df[["occupation", "apr_2025", "apr_2026", "emp_growth_apr25_apr26", "group_dominant_demand"]].copy()
    display_df["apr_2025"] = display_df["apr_2025"].map("{:,.0f}".format)
    display_df["apr_2026"] = display_df["apr_2026"].map("{:,.0f}".format)
    display_df["emp_growth_apr25_apr26"] = display_df["emp_growth_apr25_apr26"].map("{:+.1%}".format)
    print(display_df.to_string(index=False))

    bar_colors = [DEMAND_PALETTE.get(d, "grey") for d in cps_chart_df["group_dominant_demand"]]
    short_labels = [SOC_MAJOR_GROUPS.get(row["soc_major"], row["occupation"])[:40] for _, row in cps_chart_df.iterrows()]

    fig, ax_cps = plt.subplots(figsize=(12, 9))
    bars = ax_cps.barh(short_labels, cps_chart_df["emp_growth_apr25_apr26"], color=bar_colors, edgecolor="white", linewidth=0.5)

    for bar_rect, growth_val in zip(bars, cps_chart_df["emp_growth_apr25_apr26"]):
        x_pos = growth_val + (0.001 if growth_val >= 0 else -0.001)
        ha = "left" if growth_val >= 0 else "right"
        ax_cps.text(x_pos, bar_rect.get_y() + bar_rect.get_height() / 2, f"{growth_val:+.1%}", va="center", ha=ha, fontsize=8)

    ax_cps.axvline(0, color="black", linewidth=0.8)
    ax_cps.xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=1))
    ax_cps.set_xlabel("Employment Growth Apr 2025 → Apr 2026", fontsize=10)
    ax_cps.set_title(
        "Major Group Employment Direction: Apr 2025 → Apr 2026\nCPS Table A-19 (monthly survey) — directional indicator only; not BLS OEWS",
        fontsize=11,
    )
    legend_handles_cps = [Patch(facecolor=color, label=demand_type) for demand_type, color in DEMAND_PALETTE.items()]
    ax_cps.legend(handles=legend_handles_cps, title="Dominant Demand Type", fontsize=9, loc="lower right")
    plt.tight_layout()
    plt.savefig(f"{output_dir}/cps_2026_direction.png", dpi=300, bbox_inches="tight")
    plt.close()
    print(f"\n  Saved {output_dir}/cps_2026_direction.png")


def _plot_cps_model_vs_actual(
    output_dir: str,
    cps_mapped_df: pd.DataFrame,
    merged_validation_df: pd.DataFrame,
    exposure_group_df: pd.DataFrame,
) -> None:
    """Scatter of employment-weighted exposure score vs. CPS Apr 2025→Apr 2026 growth, major group level."""
    emp_col = next((c for c in ["TOT_EMP_25", "TOT_EMP_24", "TOT_EMP_23"] if c in merged_validation_df.columns), None)
    if emp_col is None:
        print("  Skipping CPS model comparison — no employment column found.")
        return

    valid_df = merged_validation_df.dropna(subset=["occupation_exposure", emp_col]).copy()
    valid_df["soc_major"] = valid_df["OCC_CODE"].str[:2]

    group_exposure_df = (
        valid_df.groupby("soc_major")
        .apply(
            lambda g: pd.Series(
                {
                    "group_exposure": (g["occupation_exposure"] * g[emp_col]).sum() / g[emp_col].sum(),
                    "n_occupations": len(g),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )

    group_demand_df = exposure_group_df[["soc_major", "group_dominant_demand"]].copy()
    group_demand_df["soc_major"] = group_demand_df["soc_major"].astype(str)

    comparison_df = group_exposure_df.merge(cps_mapped_df[["soc_major", "emp_growth_apr25_apr26"]], on="soc_major").merge(
        group_demand_df, on="soc_major", how="left"
    )
    comparison_df["group_label"] = comparison_df["soc_major"].map(SOC_MAJOR_GROUPS)

    cps_r, cps_p = stats.pearsonr(comparison_df["group_exposure"], comparison_df["emp_growth_apr25_apr26"])

    print(f"\n── CPS Model vs. Actual (Major Group Level, n={len(comparison_df)}) ──")
    print(f"Pearson r = {cps_r:.3f}, p = {cps_p:.4f}")

    dot_colors = [DEMAND_PALETTE.get(d, "grey") for d in comparison_df["group_dominant_demand"]]
    fig, ax_cps_scatter = plt.subplots(figsize=(11, 8))
    ax_cps_scatter.scatter(
        comparison_df["group_exposure"],
        comparison_df["emp_growth_apr25_apr26"],
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
            (scatter_row["group_exposure"], scatter_row["emp_growth_apr25_apr26"]),
            xytext=(5, 3),
            textcoords="offset points",
            fontsize=7.5,
            alpha=0.9,
        )
    sns.regplot(
        data=comparison_df,
        x="group_exposure",
        y="emp_growth_apr25_apr26",
        scatter=False,
        ax=ax_cps_scatter,
        line_kws={"color": "steelblue", "linewidth": 1.5},
    )
    ax_cps_scatter.axhline(0, color="grey", linestyle="--", linewidth=0.8)
    ax_cps_scatter.set_xlabel("Employment-Weighted Mean Rebound-Adjusted Exposure Score", fontsize=10)
    ax_cps_scatter.set_ylabel("Employment Growth Apr 2025 → Apr 2026 (CPS)", fontsize=10)
    ax_cps_scatter.set_title(
        f"Model Impact vs. CPS Employment Growth — Major Group Level\n"
        f"r = {cps_r:.3f}, p = {cps_p:.3f}, n = {len(comparison_df)} groups  |  CPS monthly, not BLS OEWS",
        fontsize=11,
    )
    ax_cps_scatter.xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=1))
    ax_cps_scatter.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=1))
    legend_handles_scatter = [Patch(facecolor=color, label=demand_type) for demand_type, color in DEMAND_PALETTE.items()]
    ax_cps_scatter.legend(handles=legend_handles_scatter, title="Dominant Demand Type", fontsize=9)
    plt.tight_layout()
    plt.savefig(f"{output_dir}/cps_model_vs_actual.png", dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  Saved {output_dir}/cps_model_vs_actual.png")


def main():
    bls_trends_df = pd.read_csv("data/output/bls_trends.csv")
    occupation_exposure_df = pd.read_csv("data/output/occupation_exposure_report.csv")

    occupation_exposure_df["OCC_CODE"] = occupation_exposure_df["O*NET-SOC Code"].astype(str).str.split(".").str[0]

    _agg_dict: dict = {
        "occupation_exposure": "mean",
        "Title": "first",
        "mean_penetration": "mean",
        "dominant_demand": "first",
        "dominant_strength": "first",
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
    # gives a cleaner test of whether occupation_impact predicts anything beyond
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
    plot_dynamic_sector_level_validation(dynamic_validation_df, latest_emp_col, output_dir)

    dynamic_validation_df["soc_major"] = dynamic_validation_df["OCC_CODE"].str[:2]
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
        ).reset_index()
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
            "(bubble size ∝ sector employment; wage result holds when any single sector is excluded)",
            fontsize=12,
        )
        plt.tight_layout()
        plt.savefig(f"{output_dir}/sector_level_validation.png", dpi=300, bbox_inches="tight")
        plt.close()

        print(f"\n── Sector-Level Validation (n={len(sector_agg_df)}) ──")
        print(f"Employment: r = {sector_r_emp:.3f}, p = {sector_p_emp:.3f}")
        print(f"Wage:       r = {sector_r_wage:.3f}, p = {sector_p_wage:.3f}  (jackknife-robust)")

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
    cps_mapped_df = _parse_cps_a19()
    if cps_mapped_df is not None:
        _plot_cps_2026_direction(output_dir, cps_mapped_df, group_rollup_df)
        _plot_cps_model_vs_actual(output_dir, cps_mapped_df, merged_validation_df, group_rollup_df)
    else:
        print("  Skipping CPS charts — data/raw/cps/table_a19.html not found.")
        print("  Run: uv run download_data.py  (or make download-data) to fetch it.")


if __name__ == "__main__":
    main()
