"""
composition_displacement_validation.py
──────────────────────────────────────
Tests the demand composition model's displacement term against *measured*
displacement, rather than against employment growth.

Every other validation in this project correlates a model score with employment
or wage growth. This one compares a modeled quantity with a direct measurement of
that same quantity: `gross_displacement` against the Displaced Worker
Supplement's count of workers who lost a job, by occupation group. Employment
growth never enters, so circularity is structurally impossible here rather than
merely avoided.

It also isolates the two halves of the model, which the growth-based tests
cannot. The equilibrium is `net = K·absorption_capacity − gross_displacement`;
correlating `net` with growth tests the two terms jointly and a failure cannot be
attributed. This test exercises the displacement half alone.

Inputs:
  • data/output/occupation_composition_model_report.csv
  • data/output/occupation_dynamic_model_report.csv   (for the AI-model comparison)
  • seeds/dws_displacement_panel.csv                  (via dws_panel.py)

Outputs:
  • data/output/composition_model_displacement_validation.csv
  • data/output/visualizations/dws_observed_vs_predicted_displacement.png

Why shares rather than rates
────────────────────────────
The DWS is a household survey counting people 20 and over who lost a job; OEWS
counts wage and salary jobs. Their denominators are not the same population, so a
displacement *rate* built from one over the other is not well defined. Comparing
each group's *share* of total displacement sidesteps that entirely: both sides
become unit-free distributions over the same ten groups. The rate version is
reported alongside for reference, with that mismatch noted, but the share
comparison is the headline.

The economy-wide displacement rate D cancels here for the same reason it cancels
from every cross-sectional correlation — it is one scalar multiplying every
occupation's displacement, so it leaves the shares untouched.

What this test cannot do
────────────────────────
**The DWS publishes no occupation × reason cross-tab.** Table 5 gives occupation
without reason; Table 2 gives reason without occupation. So the test can only be
run against all-reasons displacement, of which "position or shift abolished" —
the structural category this project cares about — is 44.4%. The remaining 55.6%
is plant or company closings and insufficient work: demand and cyclical shocks
rather than technological displacement. That dilutes the test, and in a direction
that should weaken the correlation rather than inflate it.

Applying the aggregate structural share uniformly across groups would change
nothing: it is a constant multiplier, so it leaves both the shares and every
correlation identical. There is no way to recover the structural subset by
occupation from the published tables.

**n = 10 groups.** Pearson r alone is not reportable at that size, so Spearman
and the full leave-one-out range are reported beside it, following the jackknife
discipline the project already applies to its 22-sector results.
"""

import os

import matplotlib.pyplot as plt
import pandas as pd
import scipy.stats as stats
import seaborn as sns

from dws_panel import DWS_TO_SOC_MAJOR, load_dws_panel

COMPOSITION_REPORT_PATH = "data/output/occupation_composition_model_report.csv"
DYNAMIC_REPORT_PATH = "data/output/occupation_dynamic_model_report.csv"

OUTPUT_PATH = "data/output/composition_model_displacement_validation.csv"
CHART_NAME = "dws_observed_vs_predicted_displacement.png"

OCCUPATION_TABLE = "table_5_occupation"

MINIMUM_GROUPS = 5

OUTPUT_COLUMNS = [
    "dws_group",
    "soc_majors",
    "observed_displaced_thousands",
    "observed_share",
    "composition_predicted_share",
    "ai_model_predicted_share",
    "group_employment",
    "observed_rate",
    "composition_predicted_rate",
]


def soc_major_to_dws_group() -> dict[str, str]:
    """Invert DWS_TO_SOC_MAJOR into a lookup from two-digit SOC major to group name."""
    return {major: group_name for group_name, majors in DWS_TO_SOC_MAJOR.items() for major in majors}


def observed_displacement_by_group(displacement_panel_df: pd.DataFrame, survey_year: int | None = None) -> pd.DataFrame:
    """Measured displaced workers per DWS occupation group, from Table 5.

    Uses the most recent survey unless one is named. Groups whose count was
    suppressed (base under 75,000) are dropped rather than read as zero.
    """
    occupation_rows_df = displacement_panel_df[displacement_panel_df["source_table"] == OCCUPATION_TABLE]
    if occupation_rows_df.empty:
        return pd.DataFrame(columns=["dws_group", "soc_majors", "observed_displaced_thousands"])

    chosen_year = survey_year if survey_year is not None else int(occupation_rows_df["survey_year"].max())
    survey_df = occupation_rows_df[occupation_rows_df["survey_year"] == chosen_year].dropna(subset=["displaced_thousands"]).copy()

    # The panel keeps the release's own capitalisation; DWS_TO_SOC_MAJOR is keyed
    # lowercase. Both sides of the join are normalised so a casing change in a
    # future release cannot silently empty the merge.
    survey_df["dws_group"] = survey_df["group_name"].astype(str).str.strip().str.lower()

    return survey_df[["dws_group", "soc_majors", "displaced_thousands"]].rename(
        columns={"displaced_thousands": "observed_displaced_thousands"}
    )


def predicted_displacement_by_group(
    scored_df: pd.DataFrame,
    displacement_col: str,
    employment_col: str,
) -> pd.DataFrame:
    """Aggregate a model's per-occupation displacement into DWS occupation groups.

    The modeled quantity is a *rate* per occupation, so it is multiplied by
    employment to become a worker count before being summed — a rate cannot be
    added across occupations of different size.
    """
    group_lookup = soc_major_to_dws_group()

    aggregation_df = scored_df.dropna(subset=[displacement_col, employment_col]).copy()
    aggregation_df["soc_major"] = aggregation_df["OCC_CODE"].astype(str).str[:2]
    aggregation_df["dws_group"] = aggregation_df["soc_major"].map(group_lookup)
    aggregation_df = aggregation_df.dropna(subset=["dws_group"])
    aggregation_df["predicted_displaced_workers"] = aggregation_df[displacement_col] * aggregation_df[employment_col]

    return (
        aggregation_df.groupby("dws_group")
        .agg(predicted_displaced_workers=("predicted_displaced_workers", "sum"), group_employment=(employment_col, "sum"))
        .reset_index()
    )


def build_displacement_comparison(displacement_panel_df: pd.DataFrame) -> pd.DataFrame | None:
    """Join measured displacement to both models' predictions, as shares and as rates."""
    if not os.path.exists(COMPOSITION_REPORT_PATH):
        return None

    composition_df = pd.read_csv(COMPOSITION_REPORT_PATH)
    employment_col = sorted(column for column in composition_df.columns if column.startswith("TOT_EMP_"))[-1]

    observed_df = observed_displacement_by_group(displacement_panel_df)
    if observed_df.empty:
        return None

    comparison_df = observed_df.merge(
        predicted_displacement_by_group(composition_df, "gross_displacement", employment_col),
        on="dws_group",
        how="inner",
    ).rename(columns={"predicted_displaced_workers": "composition_predicted_workers"})

    if os.path.exists(DYNAMIC_REPORT_PATH):
        dynamic_df = pd.read_csv(DYNAMIC_REPORT_PATH)
        ai_employment_col = sorted(column for column in dynamic_df.columns if column.startswith("TOT_EMP_"))[-1]
        ai_predicted_df = predicted_displacement_by_group(dynamic_df, "gross_displacement", ai_employment_col)[
            ["dws_group", "predicted_displaced_workers"]
        ].rename(columns={"predicted_displaced_workers": "ai_model_predicted_workers"})
        comparison_df = comparison_df.merge(ai_predicted_df, on="dws_group", how="left")
    else:
        comparison_df["ai_model_predicted_workers"] = pd.NA

    comparison_df["observed_share"] = comparison_df["observed_displaced_thousands"] / comparison_df["observed_displaced_thousands"].sum()
    comparison_df["composition_predicted_share"] = (
        comparison_df["composition_predicted_workers"] / comparison_df["composition_predicted_workers"].sum()
    )
    if comparison_df["ai_model_predicted_workers"].notna().any():
        comparison_df["ai_model_predicted_share"] = (
            comparison_df["ai_model_predicted_workers"] / comparison_df["ai_model_predicted_workers"].sum()
        )
    else:
        comparison_df["ai_model_predicted_share"] = pd.NA

    # Rate form, reported for reference only: the DWS counts people 20+ who lost a
    # job while OEWS counts wage and salary jobs, so the denominators are not the
    # same population.
    comparison_df["observed_rate"] = comparison_df["observed_displaced_thousands"] * 1_000 / comparison_df["group_employment"]
    comparison_df["composition_predicted_rate"] = comparison_df["composition_predicted_workers"] / comparison_df["group_employment"]

    return comparison_df[OUTPUT_COLUMNS].sort_values("observed_share", ascending=False).reset_index(drop=True)


def correlate_with_leave_one_out(comparison_df: pd.DataFrame, predicted_column: str) -> dict[str, float] | None:
    """Pearson and Spearman against observed share, with the leave-one-out Pearson range.

    At n = 10 a single group can carry the whole correlation, so the range matters
    at least as much as the point estimate.
    """
    paired_df = comparison_df[["dws_group", "observed_share", predicted_column]].dropna()
    if len(paired_df) < MINIMUM_GROUPS:
        return None

    pearson_r, pearson_p = stats.pearsonr(paired_df[predicted_column], paired_df["observed_share"])
    spearman_r, spearman_p = stats.spearmanr(paired_df[predicted_column], paired_df["observed_share"])

    leave_one_out_r = []
    for dropped_group in paired_df["dws_group"]:
        remaining_df = paired_df[paired_df["dws_group"] != dropped_group]
        leave_one_out_r.append(stats.pearsonr(remaining_df[predicted_column], remaining_df["observed_share"])[0])

    return {
        "pearson_r": float(pearson_r),
        "pearson_p": float(pearson_p),
        "spearman_r": float(spearman_r),
        "spearman_p": float(spearman_p),
        "leave_one_out_min": float(min(leave_one_out_r)),
        "leave_one_out_max": float(max(leave_one_out_r)),
        "n_groups": len(paired_df),
    }


def plot_observed_vs_predicted(comparison_df: pd.DataFrame, output_dir: str) -> None:
    """Scatter each group's predicted displacement share against its measured share."""
    plottable_df = comparison_df.dropna(subset=["composition_predicted_share", "observed_share"])
    if len(plottable_df) < MINIMUM_GROUPS:
        return

    sns.set_theme(style="whitegrid")
    figure, axis = plt.subplots(figsize=(9, 7.5))

    axis_limit = max(plottable_df["composition_predicted_share"].max(), plottable_df["observed_share"].max()) * 1.18
    axis.plot([0, axis_limit], [0, axis_limit], linestyle="--", color="grey", linewidth=1, label="Perfect agreement", zorder=1)

    axis.scatter(
        plottable_df["composition_predicted_share"],
        plottable_df["observed_share"],
        s=plottable_df["group_employment"] / 22_000,
        color="#6a51a3",
        alpha=0.75,
        edgecolors="white",
        linewidths=1.2,
        zorder=3,
    )
    for _, group_row in plottable_df.iterrows():
        axis.annotate(
            group_row["dws_group"].replace(" occupations", ""),
            (group_row["composition_predicted_share"], group_row["observed_share"]),
            textcoords="offset points",
            xytext=(7, 5),
            fontsize=7.5,
            color="dimgray",
        )

    correlations = correlate_with_leave_one_out(plottable_df, "composition_predicted_share")
    subtitle = ""
    if correlations is not None:
        subtitle = (
            f"Pearson r = {correlations['pearson_r']:+.3f} (p = {correlations['pearson_p']:.3f}), "
            f"Spearman ρ = {correlations['spearman_r']:+.3f}, "
            f"leave-one-out {correlations['leave_one_out_min']:+.3f} to {correlations['leave_one_out_max']:+.3f}, "
            f"n = {correlations['n_groups']}"
        )

    axis.set_xlabel("Predicted share of total displacement (demand composition model)")
    axis.set_ylabel("Measured share of total displacement (DWS Table 5)")
    axis.set_title(
        "Predicted displacement against measured displacement\n" + subtitle,
        fontsize=10.5,
    )
    axis.set_xlim(0, axis_limit)
    axis.set_ylim(0, axis_limit)
    axis.legend(fontsize=8, loc="lower right")
    figure.text(
        0.5,
        -0.02,
        "Bubble area ∝ group employment. Employment growth never enters this test. The DWS publishes no occupation × reason\n"
        "cross-tab, so this is all-reasons displacement — 55.6% of it is plant closings and insufficient work, not technology.",
        ha="center",
        fontsize=7.5,
        style="italic",
        color="dimgray",
    )

    os.makedirs(output_dir, exist_ok=True)
    figure.savefig(os.path.join(output_dir, CHART_NAME), dpi=150, bbox_inches="tight")
    plt.close(figure)
    print(f"  Saved {os.path.join(output_dir, CHART_NAME)}")


def run(output_dir: str = "data/output/visualizations") -> pd.DataFrame | None:
    """Build the displacement comparison, report it, and draw the scatter."""
    displacement_panel_df = load_dws_panel()
    if displacement_panel_df is None:
        print("  ⚠ No DWS panel available; skipping the displacement validation.")
        return None

    comparison_df = build_displacement_comparison(displacement_panel_df)
    if comparison_df is None or comparison_df.empty:
        print("  ⚠ Could not build the displacement comparison; run the composition stage first.")
        return None

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    comparison_df.to_csv(OUTPUT_PATH, index=False)

    print("\n── Predicted displacement vs. measured displacement (DWS Table 5, no growth data) ──")
    for predicted_column, label in (
        ("composition_predicted_share", "Demand composition model"),
        ("ai_model_predicted_share", "Dynamic, AI penetration"),
    ):
        correlations = correlate_with_leave_one_out(comparison_df, predicted_column)
        if correlations is None:
            continue
        print(
            f"  {label:<26} Pearson {correlations['pearson_r']:+.3f} (p={correlations['pearson_p']:.3f})  "
            f"Spearman {correlations['spearman_r']:+.3f} (p={correlations['spearman_p']:.3f})  "
            f"LOO {correlations['leave_one_out_min']:+.3f} to {correlations['leave_one_out_max']:+.3f}  "
            f"n={correlations['n_groups']}"
        )
    print("  All-reasons displacement: 55.6% is plant closings and insufficient work, not technological displacement.")

    plot_observed_vs_predicted(comparison_df, output_dir)
    print(f"  ✓ {OUTPUT_PATH}")
    return comparison_df


if __name__ == "__main__":
    run()
