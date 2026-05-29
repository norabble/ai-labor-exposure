"""
synthesize_dynamic.py
─────────────────────
Dynamic labor equilibrium model: redistributes Bounded + Adversarial AI
displacement to Unbounded-heavy occupations under a total-labor-constant
assumption, producing a signed net employment change per occupation.

Core logic
──────────
For each occupation, gross displacement is the rebound-adjusted task exposure
already absorbed into the Bounded and Adversarial contribution columns:

  gross_displacement = bounded_exposure_contribution + adversarial_exposure_contribution

Economy-wide, the total displaced labor rate is the employment-weighted mean
of gross_displacement. That total is redistributed to Unbounded-capacity
occupations in proportion to their share of total Unbounded-weighted labor:

  absorption = (pct_unbounded / employment_weighted_avg_pct_unbounded) × total_displaced

  net_employment_change = absorption − gross_displacement

The employment-weighted sum of net_employment_change is zero by construction
(verified by assertion). Occupations with above-average Unbounded capacity gain
workers; Bounded-heavy occupations lose them.

Scope: only the ~770 BLS-matched occupations in merged_validation_df. Does not
model the full labor force.

Inputs:
  • merged_validation_df (from validate_bls.py) — must include columns:
      OCC_CODE, Title, dominant_demand, dominant_strength,
      occupation_exposure, pct_bounded, pct_unbounded, pct_adversarial,
      bounded_exposure_contribution, adversarial_exposure_contribution,
      unbounded_exposure_contribution,
      TOT_EMP_{year} (employment column passed as employment_col)

Outputs:
  • data/output/occupation_dynamic_model_report.csv  (written by caller)
  • data/output/visualizations/dynamic_model_net_change_distribution.png
  • data/output/visualizations/dynamic_model_winners_losers.png
  • data/output/visualizations/dynamic_vs_rebound_model_comparison.png
"""

import matplotlib.pyplot as plt
import pandas as pd
import scipy.stats as stats
import seaborn as sns
from matplotlib.patches import Patch
from matplotlib.ticker import PercentFormatter

from plot_constants import DEMAND_PALETTE, SOC_MAJOR_GROUPS


def compute_dynamic_equilibrium(
    merged_occupation_df: pd.DataFrame,
    employment_col: str,
) -> pd.DataFrame:
    """
    Compute signed net employment change for each occupation under labor conservation.

    Returns a DataFrame with one row per matched occupation containing gross
    displacement, absorption, net_employment_change, and carry-through columns
    for comparison with the existing rebound-adjusted model.
    """
    valid_occupation_df = merged_occupation_df.dropna(subset=[employment_col]).copy()

    total_employment = valid_occupation_df[employment_col].sum()
    valid_occupation_df["employment_share"] = valid_occupation_df[employment_col] / total_employment

    valid_occupation_df["gross_displacement"] = (
        valid_occupation_df["bounded_exposure_contribution"] + valid_occupation_df["adversarial_exposure_contribution"]
    )

    # Economy-wide employment-weighted displacement rate
    total_displaced = (valid_occupation_df[employment_col] * valid_occupation_df["gross_displacement"]).sum() / total_employment

    # Total Unbounded labor capacity (employment × pct_unbounded, summed)
    total_unbounded_weighted = (valid_occupation_df[employment_col] * valid_occupation_df["pct_unbounded"]).sum()
    if total_unbounded_weighted == 0:
        raise ValueError(
            "No Unbounded capacity in the dataset — labor redistribution is undefined. At least one occupation must have pct_unbounded > 0."
        )

    # Each occupation absorbs displaced labor in proportion to its Unbounded capacity share.
    # Simplifies to: (pct_unbounded_o / employment_weighted_avg_pct_unbounded) × total_displaced
    valid_occupation_df["absorption"] = (
        valid_occupation_df["pct_unbounded"] * total_employment / total_unbounded_weighted
    ) * total_displaced

    valid_occupation_df["net_employment_change"] = valid_occupation_df["absorption"] - valid_occupation_df["gross_displacement"]
    valid_occupation_df["net_employment_change_workers"] = (
        valid_occupation_df["net_employment_change"] * valid_occupation_df[employment_col]
    )

    conservation_residual = valid_occupation_df["net_employment_change_workers"].sum()
    assert abs(conservation_residual) < 1.0, f"Labor conservation violated: net worker sum = {conservation_residual:.2f} (expected < 1.0)"

    output_columns = [
        "OCC_CODE",
        "Title",
        "dominant_demand",
        "dominant_strength",
        employment_col,
        "employment_share",
        "pct_bounded",
        "pct_unbounded",
        "pct_adversarial",
        "bounded_exposure_contribution",
        "adversarial_exposure_contribution",
        "unbounded_exposure_contribution",
        "occupation_exposure",
        "gross_displacement",
        "absorption",
        "net_employment_change",
        "net_employment_change_workers",
    ]
    return valid_occupation_df[[c for c in output_columns if c in valid_occupation_df.columns]].reset_index(drop=True)


# ── Plotting ──────────────────────────────────────────────────────────────────


def plot_net_change_distribution(dynamic_equilibrium_df: pd.DataFrame, output_dir: str) -> None:
    """Histogram of net_employment_change across occupations, colored by dominant demand type."""
    sns.set_theme(style="whitegrid")
    plt.figure(figsize=(12, 7))

    for demand_type, color in DEMAND_PALETTE.items():
        subset_df = dynamic_equilibrium_df[dynamic_equilibrium_df["dominant_demand"] == demand_type]
        if len(subset_df) == 0:
            continue
        plt.hist(
            subset_df["net_employment_change"],
            bins=40,
            alpha=0.6,
            color=color,
            label=demand_type,
            edgecolor="none",
        )

    plt.axvline(0, color="black", linewidth=1.2, linestyle="--", label="Zero (no change)")
    plt.axvline(
        dynamic_equilibrium_df["net_employment_change"].mean(),
        color="steelblue",
        linewidth=1.2,
        linestyle=":",
        label=f"Mean ({dynamic_equilibrium_df['net_employment_change'].mean():.1%})",
    )

    plt.title(
        "Dynamic Equilibrium Model: Net Employment Change Distribution\n"
        "(positive = absorption exceeds displacement; negative = net labor loss)",
        fontsize=13,
    )
    plt.xlabel("Net Employment Change (per worker, under total-labor-constant assumption)", fontsize=11)
    plt.ylabel("Occupation Count", fontsize=11)
    plt.gca().xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=1))
    mean_label = f"Mean ({dynamic_equilibrium_df['net_employment_change'].mean():.1%})"
    legend_handles = [Patch(facecolor=DEMAND_PALETTE[dt], label=dt) for dt in ["Bounded", "Unbounded", "Adversarial"]]
    legend_handles += [
        plt.Line2D([0], [0], color="black", linewidth=1.2, linestyle="--", label="Zero"),
        plt.Line2D([0], [0], color="steelblue", linewidth=1.2, linestyle=":", label=mean_label),
    ]
    plt.legend(handles=legend_handles, title="Dominant Demand Type", fontsize=9)
    plt.tight_layout()
    plt.savefig(f"{output_dir}/dynamic_model_net_change_distribution.png", dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  Saved {output_dir}/dynamic_model_net_change_distribution.png")


def plot_winners_losers(dynamic_equilibrium_df: pd.DataFrame, output_dir: str) -> None:
    """Diverging horizontal bar chart: top 20 gainers and top 20 losers by net employment change."""
    sns.set_theme(style="whitegrid")

    top_gainers_df = dynamic_equilibrium_df.nlargest(20, "net_employment_change").sort_values("net_employment_change")
    top_losers_df = dynamic_equilibrium_df.nsmallest(20, "net_employment_change").sort_values("net_employment_change")
    combined_df = pd.concat([top_losers_df, top_gainers_df])

    bar_colors = [DEMAND_PALETTE.get(demand_type, "grey") for demand_type in combined_df["dominant_demand"]]

    fig, ax = plt.subplots(figsize=(14, 14))
    bars = ax.barh(combined_df["Title"], combined_df["net_employment_change"], color=bar_colors, alpha=0.85)

    for bar_rect, (_, occupation_row) in zip(bars, combined_df.iterrows()):
        net_change_value = occupation_row["net_employment_change"]
        x_offset = 0.001 if net_change_value >= 0 else -0.001
        ax.text(
            net_change_value + x_offset,
            bar_rect.get_y() + bar_rect.get_height() / 2,
            f"{net_change_value:+.1%}",
            va="center",
            ha="left" if net_change_value >= 0 else "right",
            fontsize=8,
        )

    ax.axvline(0, color="black", linewidth=1.0)
    ax.xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=1))
    ax.set_xlabel("Net Employment Change (per worker)", fontsize=11)
    ax.set_title(
        "Dynamic Equilibrium Model: Top 20 Gainers and Top 20 Losers\n"
        "(economy-wide Bounded+Adversarial displacement redistributed to Unbounded-capacity occupations)",
        fontsize=12,
    )
    legend_handles = [Patch(facecolor=color, label=demand_type) for demand_type, color in DEMAND_PALETTE.items()]
    ax.legend(handles=legend_handles, title="Dominant Demand Type", fontsize=9)

    # Separator line between losers and gainers
    ax.axhline(len(top_losers_df) - 0.5, color="grey", linewidth=0.8, linestyle=":")

    plt.tight_layout()
    plt.savefig(f"{output_dir}/dynamic_model_winners_losers.png", dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  Saved {output_dir}/dynamic_model_winners_losers.png")


def plot_dynamic_vs_rebound_comparison(dynamic_equilibrium_df: pd.DataFrame, output_dir: str) -> None:
    """Scatter comparing occupation_exposure (existing model) vs net_employment_change (dynamic model)."""
    sns.set_theme(style="whitegrid")
    plt.figure(figsize=(13, 10))

    sns.scatterplot(
        data=dynamic_equilibrium_df,
        x="occupation_exposure",
        y="net_employment_change",
        hue="dominant_demand",
        palette=DEMAND_PALETTE,
        alpha=0.6,
        s=30,
    )

    plt.axhline(0, color="black", linewidth=0.8, linestyle="--")
    plt.axvline(0, color="grey", linewidth=0.8, linestyle="--")

    # Annotate extreme occupations in each quadrant
    quadrants = [
        (dynamic_equilibrium_df["occupation_exposure"] > 0) & (dynamic_equilibrium_df["net_employment_change"] > 0),
        (dynamic_equilibrium_df["occupation_exposure"] > 0) & (dynamic_equilibrium_df["net_employment_change"] < 0),
    ]
    for quadrant_mask in quadrants:
        quadrant_df = dynamic_equilibrium_df[quadrant_mask]
        if len(quadrant_df) == 0:
            continue
        annotate_df = quadrant_df.nlargest(5, "occupation_exposure")
        for _, annotate_row in annotate_df.iterrows():
            plt.annotate(
                annotate_row["Title"][:30],
                (annotate_row["occupation_exposure"], annotate_row["net_employment_change"]),
                xytext=(8, 3),
                textcoords="offset points",
                fontsize=7,
                alpha=0.85,
                arrowprops={"arrowstyle": "->", "color": "grey", "lw": 0.6},
            )

    plt.title(
        "Rebound-Adjusted Exposure Score vs. Dynamic Net Employment Change\n"
        "High-Bounded occupations: high exposure (right) + negative net change (below zero)\n"
        "High-Unbounded occupations: low exposure (left) + positive net change (above zero)",
        fontsize=11,
    )
    plt.xlabel("Rebound-Adjusted Exposure Score (existing model, ≥ 0)", fontsize=11)
    plt.ylabel("Net Employment Change (dynamic model, signed)", fontsize=11)
    plt.gca().xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=1))
    plt.gca().yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=1))
    plt.legend(title="Dominant Demand Type")
    plt.tight_layout()
    plt.savefig(f"{output_dir}/dynamic_vs_rebound_model_comparison.png", dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  Saved {output_dir}/dynamic_vs_rebound_model_comparison.png")


def plot_dynamic_sector_level_validation(
    dynamic_validation_df: pd.DataFrame,
    employment_col: str,
    output_dir: str,
) -> None:
    """
    2-panel bubble scatter: employment-weighted mean net_employment_change per SOC
    sector vs. composite employment growth (left) and composite wage growth (right).
    Bubble size proportional to sector employment. Labels each sector by name.
    """
    if "emp_growth_composite" not in dynamic_validation_df.columns or "wage_growth_composite" not in dynamic_validation_df.columns:
        print("  Skipping dynamic sector validation — composite growth columns not present.")
        return

    sector_source_df = dynamic_validation_df.dropna(subset=[employment_col]).copy()
    sector_source_df["soc_major"] = sector_source_df["OCC_CODE"].str[:2]
    sector_source_df["soc_group"] = sector_source_df["soc_major"].map(SOC_MAJOR_GROUPS).fillna("Other")

    def _sector_weighted_mean(col: str) -> pd.Series:
        valid_df = sector_source_df.dropna(subset=[col])
        return valid_df.groupby("soc_group").apply(lambda g: (g[col] * g[employment_col]).sum() / g[employment_col].sum())

    sector_agg_df = pd.DataFrame(
        {
            "sector_net_change": _sector_weighted_mean("net_employment_change"),
            "emp_growth": _sector_weighted_mean("emp_growth_composite"),
            "wage_growth": _sector_weighted_mean("wage_growth_composite"),
        }
    ).reset_index()
    sector_agg_df = sector_agg_df.merge(
        sector_source_df.groupby("soc_group")[employment_col].sum().rename("total_emp").reset_index(),
        on="soc_group",
    )
    sector_dominant_df = (
        sector_source_df.groupby(["soc_group", "dominant_demand"])[employment_col]
        .sum()
        .reset_index()
        .sort_values(employment_col, ascending=False)
        .drop_duplicates("soc_group")[["soc_group", "dominant_demand"]]
    )
    sector_agg_df = sector_agg_df.merge(sector_dominant_df, on="soc_group").dropna(
        subset=["sector_net_change", "emp_growth", "wage_growth"]
    )

    sector_r_emp, sector_p_emp = stats.pearsonr(sector_agg_df["sector_net_change"], sector_agg_df["emp_growth"])
    sector_r_wage, sector_p_wage = stats.pearsonr(sector_agg_df["sector_net_change"], sector_agg_df["wage_growth"])

    sns.set_theme(style="whitegrid")
    fig, (ax_emp, ax_wage) = plt.subplots(1, 2, figsize=(16, 8))
    bubble_size_scale = 1500 / sector_agg_df["total_emp"].max()

    for ax, growth_col, r_val, p_val, ylabel in [
        (ax_emp, "emp_growth", sector_r_emp, sector_p_emp, "Composite Employment Growth"),
        (ax_wage, "wage_growth", sector_r_wage, sector_p_wage, "Composite Wage Growth"),
    ]:
        bubble_colors = [DEMAND_PALETTE.get(demand_type, "grey") for demand_type in sector_agg_df["dominant_demand"]]
        ax.scatter(
            sector_agg_df["sector_net_change"],
            sector_agg_df[growth_col],
            s=(sector_agg_df["total_emp"] * bubble_size_scale).clip(30),
            c=bubble_colors,
            alpha=0.75,
            edgecolors="white",
            linewidths=0.5,
        )
        for _, sector_row in sector_agg_df.iterrows():
            ax.annotate(
                sector_row["soc_group"],
                (sector_row["sector_net_change"], sector_row[growth_col]),
                xytext=(5, 3),
                textcoords="offset points",
                fontsize=6.5,
                alpha=0.85,
            )
        ax.axhline(0, color="grey", linestyle="--", linewidth=0.8)
        ax.axvline(0, color="grey", linestyle="--", linewidth=0.8)
        ax.set_xlabel("Sector Mean Net Employment Change, employment-weighted (dynamic model)", fontsize=10)
        ax.set_ylabel(ylabel, fontsize=10)
        ax.set_title(f"r = {r_val:.3f}, p = {p_val:.3f}, n = {len(sector_agg_df)}", fontsize=11)
        ax.xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
        ax.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))

    legend_handles = [Patch(facecolor=color, label=demand_type) for demand_type, color in DEMAND_PALETTE.items()]
    ax_wage.legend(handles=legend_handles, title="Dominant Demand Type", fontsize=8)
    fig.suptitle(
        "Sector-Level Validation: Dynamic Model Net Employment Change vs. Observed Growth\n(bubble size ∝ sector employment)",
        fontsize=12,
    )
    plt.tight_layout()
    plt.savefig(f"{output_dir}/dynamic_sector_level_validation.png", dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  Saved {output_dir}/dynamic_sector_level_validation.png")

    print(f"\n── Dynamic Sector-Level Validation (n={len(sector_agg_df)}) ──")
    print(f"Employment: r = {sector_r_emp:.3f}, p = {sector_p_emp:.3f}")
    print(f"Wage:       r = {sector_r_wage:.3f}, p = {sector_p_wage:.3f}")
