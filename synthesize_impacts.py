"""
synthesize_impacts.py
─────────────────────
Task-level synthesis: match classified O*NET tasks to Anthropic's task
penetration data, compute rebound-adjusted exposure per task, then
roll up to the occupation level.

Core logic
──────────
For each task that has measured AI penetration:

  task_exposure = penetration × (1 − rebound_fraction)

  • Adversarial  → rebound = 0.9 → task_exposure ≈ 0     (arms race absorbs nearly all)
  • Unbounded    → rebound = 0.7 → task_exposure = 0.3×p  (demand expansion absorbs most)
  • Bounded      → rebound = 0.1 → task_exposure = 0.9×p  (little absorption; mostly structural)

The occupation-level score is the importance-weighted average of task exposures,
ranging from 0 (fully absorbed) to ~max(penetration) (fully Bounded with
high AI coverage). Higher scores indicate greater structural AI exposure.

Inputs:
  • data/output/classified_all_tasks.csv
  • data/raw/anthropic_task_penetration.csv
  • data/raw/eloundou_exposure.csv

Output:
  • data/output/occupation_exposure_report.csv
"""

import os

import pandas as pd

# ── Rebound fractions ────────────────────────────────────────────────────────
# task_exposure = penetration × (1 − rebound). Tune these to adjust the model.
#
#  ADVERSARIAL_REBOUND  = 0.9  → nearly full rebound; task_exposure ≈ 0
#  UNBOUNDED_REBOUND    = 0.7  → most absorbed by demand expansion
#  BOUNDED_REBOUND      = 0.1  → little absorption; exposure is mostly structural

ADVERSARIAL_REBOUND = 0.9
UNBOUNDED_REBOUND = 0.7
BOUNDED_REBOUND = 0.1

OUTPUT_PATH = "data/output/occupation_exposure_report.csv"


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


# ── 2. Compute per-task rebound-adjusted exposure ────────────────────────────


def compute_task_exposure(task_dataframe: pd.DataFrame) -> pd.DataFrame:
    """
    task_exposure = penetration × (1 − rebound). Always ≥ 0; higher means more
    structural AI exposure. Tasks with zero penetration contribute 0.
    """
    _rebound = {"Adversarial": ADVERSARIAL_REBOUND, "Unbounded": UNBOUNDED_REBOUND, "Bounded": BOUNDED_REBOUND}

    def _exposure(row) -> float:
        penetration_value = row["penetration"]
        if penetration_value == 0:
            return 0.0
        rebound = _rebound.get(row["Demand Type"], None)
        if rebound is None:
            return 0.0  # ERROR rows
        return penetration_value * (1 - rebound)

    task_dataframe["task_exposure"] = task_dataframe.apply(_exposure, axis=1) * task_dataframe["task_importance"]
    return task_dataframe


# ── 3. Roll up to occupation level ────────────────────────────────────────────


def rollup_to_occupation(task_dataframe: pd.DataFrame) -> pd.DataFrame:
    """
    For each occupation:
      - Count tasks by demand type
      - Compute importance-weighted mean occupation_exposure
      - Compute average penetration across tasks (a proxy for overall observed exposure)
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
                    "occupation_exposure": (g["task_exposure"].sum() / g["task_importance"].sum() if g["task_importance"].sum() > 0 else 0),
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

    pct_col_map = {"Bounded": "pct_bounded", "Unbounded": "pct_unbounded", "Adversarial": "pct_adversarial"}
    occupation_aggregation_df["dominant_strength"] = occupation_aggregation_df.apply(
        lambda row: row[pct_col_map[row["dominant_demand"]]],
        axis=1,
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


# ── 5. Derive exposure tier label from occupation_exposure score ──────────────

EXPOSURE_TIERS = {
    "High Structural Exposure": lambda s, p: s > 0.04 and p > 0.05,
    "Moderate Structural Exposure": lambda s, p: s > 0.01 and p > 0.02,
    "Low Structural Exposure": lambda s, p: s > 0.002,
    "Minimal AI Exposure": lambda s, p: True,  # fallback
}


def derive_exposure_tier(row: pd.Series) -> str:
    occupation_score = row["occupation_exposure"]
    mean_penetration_value = row["mean_penetration"]
    for label, condition in EXPOSURE_TIERS.items():
        if condition(occupation_score, mean_penetration_value):
            return label
    return "Unknown"


# ── 6. Main ──────────────────────────────────────────────────────────────────


def synthesize():
    merged_task_data = load_and_match()
    merged_task_data = compute_task_exposure(merged_task_data)
    occupation_data_df = rollup_to_occupation(merged_task_data)
    occupation_data_df = merge_eloundou(occupation_data_df)

    occupation_data_df["exposure_tier"] = occupation_data_df.apply(derive_exposure_tier, axis=1)

    # Sort: highest exposure first
    occupation_data_df = occupation_data_df.sort_values("occupation_exposure", ascending=False)

    os.makedirs("data/output", exist_ok=True)
    occupation_data_df.to_csv(OUTPUT_PATH, index=False)
    print(f"\nSaved final report → {OUTPUT_PATH}")
    print(f"Occupations in report: {len(occupation_data_df)}")

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n── Exposure Tier Distribution ──")
    print(occupation_data_df["exposure_tier"].value_counts().to_string())

    print("\n── Dominant Demand Type ──")
    print(occupation_data_df["dominant_demand"].value_counts().to_string())

    print("\n── Occupation Exposure Score distribution ──")
    print(occupation_data_df["occupation_exposure"].describe().round(4).to_string())

    print("\n── Top 20: Highest Observed AI Exposure ──")
    exposure_display_df = occupation_data_df.nlargest(20, "mean_penetration")[
        ["Title", "dominant_demand", "dominant_strength", "mean_penetration"]
    ].copy()
    exposure_display_df["dominant_strength"] = exposure_display_df["dominant_strength"].map("{:.0%}".format)
    exposure_display_df["mean_penetration"] = exposure_display_df["mean_penetration"].map("{:.0%}".format)
    print(exposure_display_df.to_string(index=False))

    print("\n── Top 15: Highest Structural Exposure ──")
    top_exposed = occupation_data_df.head(15)[["Title", "dominant_demand", "mean_penetration", "occupation_exposure", "exposure_tier"]]
    print(top_exposed.to_string(index=False))

    print("\n── Top 15: Lowest Structural Exposure ──")
    top_resilient = occupation_data_df.tail(15).sort_values("occupation_exposure", ascending=True)[
        ["Title", "dominant_demand", "mean_penetration", "occupation_exposure", "exposure_tier"]
    ]
    print(top_resilient.to_string(index=False))

    return occupation_data_df


if __name__ == "__main__":
    synthesize()
