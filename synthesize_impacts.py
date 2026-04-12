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
UNBOUNDED_REBOUND   = 0.5
BOUNDED_DECLINE     = 1.0

OUTPUT_PATH = "data/output/occupation_impact_report.csv"


# ── 1. Load and match data ────────────────────────────────────────────────────

def load_and_match() -> pd.DataFrame:
    print("Loading classified tasks...")
    df_cls = pd.read_csv("data/output/classified_all_tasks.csv")

    print("Loading Anthropic task penetration data...")
    df_pen = pd.read_csv("data/raw/anthropic_task_penetration.csv")

    # Normalise for matching
    df_cls["task_lower"] = df_cls["Task"].str.lower().str.strip()
    df_pen["task_lower"] = df_pen["task"].str.lower().str.strip()

    df = df_cls.merge(df_pen[["task_lower", "penetration"]], on="task_lower", how="left")
    df["penetration"] = df["penetration"].fillna(0.0)

    n_matched = df["penetration"].notna().sum()
    n_nonzero = (df["penetration"] > 0).sum()
    print(f"  Matched {len(df)} tasks | {n_nonzero} with measured AI penetration > 0")

    return df


# ── 2. Compute per-task net impact score ─────────────────────────────────────

def compute_task_impact(df: pd.DataFrame) -> pd.DataFrame:
    """
    net_impact is positive (demand expansion) or negative (labour reduction).
    Tasks with zero penetration contribute 0 to the score.
    """
    def _impact(row) -> float:
        p = row["penetration"]
        if p == 0:
            return 0.0
        d = row["Demand Type"]
        if d == "Adversarial":
            return p * ADVERSARIAL_REBOUND    # bounces back fully → no net loss
        elif d == "Unbounded":
            return p * UNBOUNDED_REBOUND      # partially rebound → mild net gain
        elif d == "Bounded":
            return -p * BOUNDED_DECLINE       # full reduction → negative impact
        return 0.0  # ERROR rows

    df["task_net_impact"] = df.apply(_impact, axis=1)
    return df


# ── 3. Roll up to occupation level ────────────────────────────────────────────

def rollup_to_occupation(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each occupation:
      - Count tasks by demand type
      - Compute penetration-weighted mean net_impact
      - Compute average penetration across tasks (a proxy for overall AI exposure)
    """
    # Exclude ERROR rows from aggregation
    df_valid = df[df["Demand Type"] != "ERROR"].copy()

    agg = df_valid.groupby(["O*NET-SOC Code", "Title"]).agg(
        total_tasks       = ("Task", "count"),
        n_bounded         = ("Demand Type", lambda x: (x == "Bounded").sum()),
        n_unbounded       = ("Demand Type", lambda x: (x == "Unbounded").sum()),
        n_adversarial     = ("Demand Type", lambda x: (x == "Adversarial").sum()),
        mean_penetration  = ("penetration", "mean"),
        max_penetration   = ("penetration", "max"),
        # Penetration-weighted net impact
        # weighted mean: sum(net_impact) / total_tasks
        # (tasks with 0 penetration contribute 0 — correct behaviour)
        occupation_impact = ("task_net_impact", "mean"),
    ).reset_index()

    agg["pct_bounded"]     = agg["n_bounded"]     / agg["total_tasks"]
    agg["pct_unbounded"]   = agg["n_unbounded"]   / agg["total_tasks"]
    agg["pct_adversarial"] = agg["n_adversarial"] / agg["total_tasks"]
    agg["dominant_demand"] = agg[["n_bounded", "n_unbounded", "n_adversarial"]].rename(
        columns={"n_bounded": "Bounded", "n_unbounded": "Unbounded", "n_adversarial": "Adversarial"}
    ).idxmax(axis=1)

    return agg


# ── 4. Merge Eloundou theoretical exposure ─────────────────────────────────────

def merge_eloundou(df_occ: pd.DataFrame) -> pd.DataFrame:
    eloundou_path = "data/raw/eloundou_exposure.csv"
    if not os.path.exists(eloundou_path):
        print("Warning: eloundou_exposure.csv not found — skipping.")
        return df_occ

    df_el = pd.read_csv(eloundou_path)
    df_el["eloundou_exposure_mid"] = df_el[["dv_rating_beta", "human_rating_beta"]].mean(axis=1)
    df_el["_code_base"] = df_el["O*NET-SOC Code"].astype(str).str.split(".").str[0]
    df_occ["_code_base"] = df_occ["O*NET-SOC Code"].str.split(".").str[0]

    df_merged = df_occ.merge(
        df_el[["_code_base", "eloundou_exposure_mid"]].drop_duplicates("_code_base"),
        on="_code_base",
        how="left",
    ).drop(columns=["_code_base"])

    return df_merged


# ── 5. Derive narrative label from occupation_impact score ────────────────────

IMPACT_THRESHOLDS = {
    "Strong Decline (Efficiency Transition)": lambda s, p: s < -0.02 and p > 0.05,
    "Mild Decline":                           lambda s, p: s < -0.005 and p > 0.02,
    "The Arms Race (Stable / Inflation)":     lambda s, p: s >= 0.05,
    "The Infinite Frontier (Expansion)":      lambda s, p: 0.005 <= s < 0.05,
    "Limited AI Impact":                      lambda s, p: True,   # fallback
}

def derive_narrative(row: pd.Series) -> str:
    score = row["occupation_impact"]
    pen   = row["mean_penetration"]
    for label, condition in IMPACT_THRESHOLDS.items():
        if condition(score, pen):
            return label
    return "Unknown"


# ── 6. Main ──────────────────────────────────────────────────────────────────

def synthesize():
    df = load_and_match()
    df = compute_task_impact(df)
    df_occ = rollup_to_occupation(df)
    df_occ = merge_eloundou(df_occ)

    # Narrative
    df_occ["impact_narrative"] = df_occ.apply(derive_narrative, axis=1)

    # Sort: most negative impact first (highest displacement risk), then expansionary
    df_occ = df_occ.sort_values("occupation_impact", ascending=True)

    os.makedirs("data/output", exist_ok=True)
    df_occ.to_csv(OUTPUT_PATH, index=False)
    print(f"\nSaved final report → {OUTPUT_PATH}")
    print(f"Occupations in report: {len(df_occ)}")

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n── Impact Narrative Distribution ──")
    print(df_occ["impact_narrative"].value_counts().to_string())

    print("\n── Dominant Demand Type ──")
    print(df_occ["dominant_demand"].value_counts().to_string())

    print("\n── Occupation Impact Score distribution ──")
    print(df_occ["occupation_impact"].describe().round(4).to_string())

    print("\n── Top 15: Highest Displacement Risk (most negative impact score) ──")
    top_decline = df_occ.head(15)[
        ["Title", "dominant_demand", "mean_penetration", "occupation_impact", "impact_narrative"]
    ]
    print(top_decline.to_string(index=False))

    print("\n── Top 15: Highest Expansion / Resilience (most positive impact score) ──")
    top_expand = df_occ.tail(15).sort_values("occupation_impact", ascending=False)[
        ["Title", "dominant_demand", "mean_penetration", "occupation_impact", "impact_narrative"]
    ]
    print(top_expand.to_string(index=False))

    return df_occ


if __name__ == "__main__":
    synthesize()
