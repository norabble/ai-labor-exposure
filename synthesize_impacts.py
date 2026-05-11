"""
synthesize_impacts.py
─────────────────────
Task-level synthesis: match classified O*NET tasks to Anthropic's task
penetration data, compute expected labor-demand impact per task, then
roll up to the occupation level.

Core logic
──────────
For each task that has measured AI penetration:

  • Adversarial  → demand bounces back quickly (arms race refills the work)
                   net_impact = +penetration * ADVERSARIAL_REBOUND

  • Unbounded    → demand recovers but with a delay (backlog absorbs savings,
                   though some structural reduction happens first)
                   net_impact = +penetration * UNBOUNDED_REBOUND  (partial)

  • Bounded      → demand is permanently reduced; time saved means fewer
                   workers needed with no offsetting expansion
                   net_impact = -penetration * BOUNDED_DECLINE

The occupation-level score is the penetration-weighted average of task
net_impacts, giving a number between -1 (full labour displacement) and
+1 (full demand expansion).

Inputs:
  • data/output/classified_all_tasks.csv
  • data/raw/anthropic_task_penetration.csv
  • data/raw/eloundou_exposure.csv

Output:
  • data/output/occupation_impact_report.csv
"""

import os

import pandas as pd

# ── Rebound / decline multipliers ────────────────────────────────────────────
# These are intentionally interpretable parameters you can tune.
#
#  ADVERSARIAL_REBOUND  = 1.0  → full task rebound; no net job loss
#  UNBOUNDED_REBOUND    = 0.5  → partial rebound; the backlog absorbs half the
#                                AI savings, the other half reduces headcount
#  BOUNDED_DECLINE      = 1.0  → full labour reduction; no rebound at all

ADVERSARIAL_REBOUND = 1.0
UNBOUNDED_REBOUND = 0.5
BOUNDED_DECLINE = 1.0

OUTPUT_PATH = "data/output/occupation_impact_report.csv"


# ── 1. Load and match data ────────────────────────────────────────────────────


def load_and_match() -> pd.DataFrame:
    print("Loading classified tasks...")
    classified_tasks_df = pd.read_csv("data/output/classified_all_tasks.csv")

    print("Loading Anthropic task penetration data...")
    penetration_df = pd.read_csv("data/raw/anthropic_task_penetration.csv")

    # Normalise for matching
    classified_tasks_df["task_lower"] = classified_tasks_df["Task"].str.lower().str.strip()
    penetration_df["task_lower"] = penetration_df["task"].str.lower().str.strip()

    merged_task_data = classified_tasks_df.merge(penetration_df[["task_lower", "penetration"]], on="task_lower", how="left")
    merged_task_data["penetration"] = merged_task_data["penetration"].fillna(0.0)

    print("Loading O*NET task ratings (Importance)...")
    ratings_path = "data/raw/onet_task_ratings.csv"
    if os.path.exists(ratings_path):
        ratings_df = pd.read_csv(ratings_path)
        merged_task_data = merged_task_data.merge(ratings_df, on="Task ID", how="left")
        merged_task_data["task_importance"] = merged_task_data["task_importance"].fillna(1.0)
    else:
        print("Warning: onet_task_ratings.csv not found — assuming weight=1.0 for all tasks.")
        merged_task_data["task_importance"] = 1.0

    n_nonzero = (merged_task_data["penetration"] > 0).sum()
    print(f"  Matched {len(merged_task_data)} tasks | {n_nonzero} with measured AI penetration > 0")

    return merged_task_data


# ── 2. Compute per-task net impact score ─────────────────────────────────────


def compute_task_impact(task_dataframe: pd.DataFrame) -> pd.DataFrame:
    """
    net_impact is positive (demand expansion) or negative (labour reduction).
    Tasks with zero penetration contribute 0 to the score.
    """

    def _impact(row) -> float:
        penetration_value = row["penetration"]
        if penetration_value == 0:
            return 0.0
        demand_type = row["Demand Type"]
        if demand_type == "Adversarial":
            return penetration_value * ADVERSARIAL_REBOUND  # bounces back fully → no net loss
        elif demand_type == "Unbounded":
            return penetration_value * UNBOUNDED_REBOUND  # partially rebound → mild net gain
        elif demand_type == "Bounded":
            return -penetration_value * BOUNDED_DECLINE  # full reduction → negative impact
        return 0.0  # ERROR rows

    task_dataframe["task_net_impact"] = task_dataframe.apply(_impact, axis=1) * task_dataframe["task_importance"]
    return task_dataframe


# ── 3. Roll up to occupation level ────────────────────────────────────────────


def rollup_to_occupation(task_dataframe: pd.DataFrame) -> pd.DataFrame:
    """
    For each occupation:
      - Count tasks by demand type
      - Compute penetration-weighted mean net_impact
      - Compute average penetration across tasks (a proxy for overall AI exposure)
    """
    # Exclude ERROR rows from aggregation
    valid_tasks_df = task_dataframe[task_dataframe["Demand Type"] != "ERROR"].copy()

    occupation_aggregation_df = (
        valid_tasks_df.groupby(["O*NET-SOC Code", "Title"])
        .apply(
            lambda g: pd.Series(
                {
                    "total_tasks": len(g),
                    "total_importance": g["task_importance"].sum(),
                    "weighted_bounded": g.loc[g["Demand Type"] == "Bounded", "task_importance"].sum(),
                    "weighted_unbounded": g.loc[g["Demand Type"] == "Unbounded", "task_importance"].sum(),
                    "weighted_adversarial": g.loc[g["Demand Type"] == "Adversarial", "task_importance"].sum(),
                    "mean_penetration": (
                        (g["penetration"] * g["task_importance"]).sum() / g["task_importance"].sum()
                        if g["task_importance"].sum() > 0
                        else 0
                    ),
                    "max_penetration": g["penetration"].max(),
                    "occupation_impact": (g["task_net_impact"].sum() / g["task_importance"].sum() if g["task_importance"].sum() > 0 else 0),
                }
            )
        )
        .reset_index()
    )

    occupation_aggregation_df["pct_bounded"] = occupation_aggregation_df["weighted_bounded"] / occupation_aggregation_df["total_importance"]
    occupation_aggregation_df["pct_unbounded"] = (
        occupation_aggregation_df["weighted_unbounded"] / occupation_aggregation_df["total_importance"]
    )
    occupation_aggregation_df["pct_adversarial"] = (
        occupation_aggregation_df["weighted_adversarial"] / occupation_aggregation_df["total_importance"]
    )

    occupation_aggregation_df["dominant_demand"] = (
        occupation_aggregation_df[["weighted_bounded", "weighted_unbounded", "weighted_adversarial"]]
        .rename(columns={"weighted_bounded": "Bounded", "weighted_unbounded": "Unbounded", "weighted_adversarial": "Adversarial"})
        .idxmax(axis=1)
    )

    return occupation_aggregation_df


# ── 4. Merge Eloundou theoretical exposure ─────────────────────────────────────


def merge_eloundou(occupation_data_df: pd.DataFrame) -> pd.DataFrame:
    eloundou_path = "data/raw/eloundou_exposure.csv"
    if not os.path.exists(eloundou_path):
        print("Warning: eloundou_exposure.csv not found — skipping.")
        return occupation_data_df

    eloundou_exposure_df = pd.read_csv(eloundou_path)
    eloundou_exposure_df["eloundou_exposure_mid"] = eloundou_exposure_df[["dv_rating_beta", "human_rating_beta"]].mean(axis=1)
    eloundou_exposure_df["_code_base"] = eloundou_exposure_df["O*NET-SOC Code"].astype(str).str.split(".").str[0]
    occupation_data_df["_code_base"] = occupation_data_df["O*NET-SOC Code"].str.split(".").str[0]

    merged_occupation_data = occupation_data_df.merge(
        eloundou_exposure_df[["_code_base", "eloundou_exposure_mid"]].drop_duplicates("_code_base"),
        on="_code_base",
        how="left",
    ).drop(columns=["_code_base"])

    return merged_occupation_data


# ── 5. Derive narrative label from occupation_impact score ────────────────────

IMPACT_THRESHOLDS = {
    "Strong Decline (Efficiency Transition)": lambda s, p: s < -0.02 and p > 0.05,
    "Mild Decline": lambda s, p: s < -0.005 and p > 0.02,
    "The Arms Race (Stable / Inflation)": lambda s, p: s >= 0.05,
    "The Infinite Frontier (Expansion)": lambda s, p: 0.005 <= s < 0.05,
    "Limited AI Impact": lambda s, p: True,  # fallback
}


def derive_narrative(row: pd.Series) -> str:
    occupation_score = row["occupation_impact"]
    mean_penetration_value = row["mean_penetration"]
    for label, condition in IMPACT_THRESHOLDS.items():
        if condition(occupation_score, mean_penetration_value):
            return label
    return "Unknown"


# ── 6. Main ──────────────────────────────────────────────────────────────────


def synthesize():
    merged_task_data = load_and_match()
    merged_task_data = compute_task_impact(merged_task_data)
    occupation_data_df = rollup_to_occupation(merged_task_data)
    occupation_data_df = merge_eloundou(occupation_data_df)

    # Narrative
    occupation_data_df["impact_narrative"] = occupation_data_df.apply(derive_narrative, axis=1)

    # Sort: most negative impact first (highest displacement risk), then expansionary
    occupation_data_df = occupation_data_df.sort_values("occupation_impact", ascending=True)

    os.makedirs("data/output", exist_ok=True)
    occupation_data_df.to_csv(OUTPUT_PATH, index=False)
    print(f"\nSaved final report → {OUTPUT_PATH}")
    print(f"Occupations in report: {len(occupation_data_df)}")

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n── Impact Narrative Distribution ──")
    print(occupation_data_df["impact_narrative"].value_counts().to_string())

    print("\n── Dominant Demand Type ──")
    print(occupation_data_df["dominant_demand"].value_counts().to_string())

    print("\n── Occupation Impact Score distribution ──")
    print(occupation_data_df["occupation_impact"].describe().round(4).to_string())

    print("\n── Top 15: Highest Displacement Risk (most negative impact score) ──")
    top_decline = occupation_data_df.head(15)[["Title", "dominant_demand", "mean_penetration", "occupation_impact", "impact_narrative"]]
    print(top_decline.to_string(index=False))

    print("\n── Top 15: Highest Expansion / Resilience (most positive impact score) ──")
    top_expand = occupation_data_df.tail(15).sort_values("occupation_impact", ascending=False)[
        ["Title", "dominant_demand", "mean_penetration", "occupation_impact", "impact_narrative"]
    ]
    print(top_expand.to_string(index=False))

    return occupation_data_df


if __name__ == "__main__":
    synthesize()
