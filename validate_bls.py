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

import os

import matplotlib.pyplot as plt
import pandas as pd
import scipy.stats as stats
import seaborn as sns


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
    fig, axes = plt.subplots(1, n_periods, figsize=(6 * n_periods, 6), sharey=False)
    if n_periods == 1:
        axes = [axes]

    for ax, period in zip(axes, periods):
        growth_col = f"{growth_type}_growth_{period}"
        is_composite = period == "composite"
        clean_df = _clean(merged_df, growth_col, is_composite)

        r_impact, p_impact, _, _ = _correlations(clean_df, growth_col)

        sns.regplot(
            data=clean_df,
            x="occupation_impact",
            y=growth_col,
            scatter_kws={"alpha": 0.4, "s": 20},
            line_kws={"color": "steelblue"},
            ax=ax,
        )
        ax.set_title(f"{_label(period)}\nr={r_impact:.3f} (p={p_impact:.3f})", fontsize=11)
        ax.set_xlabel("Occupation Impact Score", fontsize=10)
        ax.set_ylabel(ylabel if ax == axes[0] else "", fontsize=10)
        ax.axhline(0, color="red", linestyle="--", linewidth=0.8)
        ax.axvline(0, color="red", linestyle="--", linewidth=0.8)
        ax.text(0.02, 0.98, f"n={len(clean_df)}", transform=ax.transAxes, va="top", fontsize=8, color="grey")

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
            palette={"Bounded": "#d73027", "Unbounded": "#fee08b", "Adversarial": "#1a9850"},
            alpha=0.7,
            s=60,
        )
        plt.title("Productivity Premium vs Red Queen's Race\nComposite Employment vs Wage Growth by Demand Type")
        plt.xlabel("Composite Employment Growth (2022→latest)")
        plt.ylabel("Composite Median Wage Growth (2022→latest)")
        plt.axhline(0, color="black", linestyle="--", linewidth=1)
        plt.axvline(0, color="black", linestyle="--", linewidth=1)
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


if __name__ == "__main__":
    main()
