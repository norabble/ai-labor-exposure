"""
validate_bls.py
───────────────
Validates the occupation impact model against actual BLS employment and wage
trends across multiple year periods.

For each growth period (YoY pairs + composite), computes Pearson correlation
between our occupation_impact score and real-world growth outcomes, and
compares against the naive Eloundou exposure baseline.

Inputs:
  • data/output/bls_trends.csv          (from analyze_bls.py)
  • data/output/occupation_impact_report.csv

Outputs (saved to data/output/visualizations/):
  • validation_emp_growth.png   — impact score vs emp growth, one subplot per period
  • validation_wage_growth.png  — impact score vs wage growth, one subplot per period
  • productivity_vs_red_queen.png — emp vs wage growth by demand type (composite)
"""

import math
import os

import matplotlib.pyplot as plt
import pandas as pd
import scipy.stats as stats
import seaborn as sns
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import PercentFormatter

from plot_constants import DEMAND_PALETTE

SOC_MAJOR_GROUPS = {
    "11": "Management",
    "13": "Business and Financial Operations",
    "15": "Computer and Mathematical",
    "17": "Architecture and Engineering",
    "19": "Life, Physical, and Social Science",
    "21": "Community and Social Service",
    "23": "Legal",
    "25": "Educational Instruction and Library",
    "27": "Arts, Design, Entertainment, Sports, and Media",
    "29": "Healthcare Practitioners and Technical",
    "31": "Healthcare Support",
    "33": "Protective Service",
    "35": "Food Preparation and Serving Related",
    "37": "Building and Grounds Cleaning and Maintenance",
    "39": "Personal Care and Service",
    "41": "Sales and Related",
    "43": "Office and Administrative Support",
    "45": "Farming, Fishing, and Forestry",
    "47": "Construction and Extraction",
    "49": "Installation, Maintenance, and Repair",
    "51": "Production",
    "53": "Transportation and Material Moving",
    "55": "Military Specific",
}


def _label(period: str) -> str:
    """Convert a period key like '22_23' or 'composite' to a readable label."""
    if period == "composite":
        return "Composite (2022→latest)"
    parts = period.split("_")
    return f"20{parts[0]}→20{parts[1]}"


def _clean(merged_df: pd.DataFrame, growth_col: str, is_composite: bool) -> pd.DataFrame:
    """Drop NaN/inf and remove extreme outliers for a single growth column."""
    clean_df = merged_df.replace([float("inf"), -float("inf")], pd.NA).dropna(subset=[growth_col, "occupation_impact"])
    if growth_col.startswith("emp_growth"):
        upper = 2.0 if is_composite else 1.0
        lower = -0.75 if is_composite else -0.5
        clean_df = clean_df[(clean_df[growth_col] < upper) & (clean_df[growth_col] > lower)]
    return clean_df


def _correlations(clean_df: pd.DataFrame, growth_col: str) -> tuple[float, float, float, float]:
    """Return (r_impact, p_impact, r_eloundou, p_eloundou) for a growth column."""
    r_impact, p_impact = stats.pearsonr(clean_df["occupation_impact"], clean_df[growth_col])
    r_eloundou, p_eloundou = stats.pearsonr(clean_df["eloundou_exposure_mid"], clean_df[growth_col])
    return r_impact, p_impact, r_eloundou, p_eloundou


def _make_subplot_figure(
    merged_df: pd.DataFrame,
    growth_type: str,
    periods: list[str],
    ylabel: str,
    output_path: str,
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
        clean_df = _clean(merged_df, growth_col, is_composite)

        r_impact, p_impact, _, _ = _correlations(clean_df, growth_col)

        # Colored scatter by demand type, then regression lines overlaid
        sns.scatterplot(
            data=clean_df,
            x="occupation_impact",
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
            x="occupation_impact",
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
                x="occupation_impact",
                y=growth_col,
                scatter=False,
                ci=None,
                line_kws={"color": color, "linewidth": 1.5},
                ax=ax,
            )

        ax.set_title(f"{_label(period)}\nr={r_impact:.3f} (p={p_impact:.3f})", fontsize=11)
        ax.set_xlabel("Occupation Impact Score", fontsize=10)
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

    fig.suptitle(f"Occupation Impact Score vs {ylabel}", fontsize=13, y=1.02)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()


def main():
    bls_trends_df = pd.read_csv("data/output/bls_trends.csv")
    occupation_impact_df = pd.read_csv("data/output/occupation_impact_report.csv")

    occupation_impact_df["OCC_CODE"] = occupation_impact_df["O*NET-SOC Code"].astype(str).str.split(".").str[0]

    aggregated_impact_df = (
        occupation_impact_df.groupby("OCC_CODE")
        .agg(
            {
                "occupation_impact": "mean",
                "Title": "first",
                "mean_penetration": "mean",
                "eloundou_exposure_mid": "mean",
                "dominant_demand": "first",
                "dominant_strength": "first",
            }
        )
        .reset_index()
    )

    merged_validation_df = pd.merge(aggregated_impact_df, bls_trends_df, on="OCC_CODE", how="inner")

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
        f"{output_dir}/validation_emp_growth.png",
    )
    _make_subplot_figure(
        merged_validation_df,
        "wage",
        wage_periods,
        "Year-over-Year Median Wage Growth",
        f"{output_dir}/validation_wage_growth.png",
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
        plt.title("Productivity Premium vs Red Queen's Race\nComposite Employment vs Wage Growth by Demand Type")
        plt.xlabel("Composite Employment Growth (2022→latest)")
        plt.ylabel("Composite Median Wage Growth (2022→latest)")
        plt.axhline(0, color="black", linestyle="--", linewidth=1)
        plt.axvline(0, color="black", linestyle="--", linewidth=1)
        plt.gca().xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
        plt.gca().yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
        plt.tight_layout()
        plt.savefig(f"{output_dir}/productivity_vs_red_queen.png", dpi=300)
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

    # ── AI exposure volume ────────────────────────────────────────────────────
    # exposure_volume = (occupation employment / total modeled employment) × mean_penetration
    # Gives each occupation's contribution to economy-wide AI exposure as a fraction of total employment.
    latest_emp_col = sorted(c for c in merged_validation_df.columns if c.startswith("TOT_EMP_"))[-1]
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
        bars = ax.barh(sorted_df["group_name"], sorted_df[value_col] * 100, color=bar_colors, alpha=0.85)
        ax.set_xlabel(xlabel, fontsize=10)
        ax.set_title(title, fontsize=12)
        ax.xaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=1))
        legend_handles = [Patch(facecolor=color, label=demand_type) for demand_type, color in DEMAND_PALETTE.items()]
        ax.legend(handles=legend_handles, title="Dominant Demand Type", fontsize=9, title_fontsize=9, loc="lower right")
        for bar, (_, row) in zip(bars, sorted_df.iterrows()):
            ax.text(
                bar.get_width() + 0.05,
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


if __name__ == "__main__":
    main()
