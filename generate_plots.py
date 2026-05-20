"""
generate_plots.py
─────────────────
Generates visualizations from the occupation impact report.

Inputs:
  • data/output/occupation_impact_report.csv
  • data/output/classified_all_tasks.csv          (for usage_by_demand_type chart)
  • data/raw/anthropic_task_conversation_pct.csv  (for usage_by_demand_type chart)

Outputs (saved to data/output/visualizations/):
  • most_impacted_jobs.png        — Top 15 highest/lowest impact occupations
  • exposure_vs_impact.png        — Eloundou exposure vs. our full model impact score
  • biggest_differences.png       — Occupations most different from naive exposure prediction
  • usage_by_demand_type.png           — Claude conversation share vs. task share by demand type
  • task_importance_vs_penetration.png — task importance vs. AI penetration by demand type
"""

import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.patches import Patch
from matplotlib.ticker import PercentFormatter

from plot_constants import DEMAND_PALETTE, SOC_MAJOR_GROUPS


def main():
    output_dir = "data/output/visualizations"
    os.makedirs(output_dir, exist_ok=True)

    impact_report_df = pd.read_csv("data/output/occupation_impact_report.csv")
    clean_impact_report_df = impact_report_df.dropna(subset=["eloundou_exposure_mid", "occupation_impact"]).copy()

    sns.set_theme(style="whitegrid")

    # 1. Most Impacted Jobs (Top 15 Negative, Top 15 Positive)
    plt.figure(figsize=(14, 10))

    top_negative = impact_report_df.nsmallest(15, "occupation_impact")
    top_positive = impact_report_df.nlargest(15, "occupation_impact")
    most_impacted = pd.concat([top_positive, top_negative]).sort_values("occupation_impact")

    colors = ["#d73027" if x < 0 else "#1a9850" for x in most_impacted["occupation_impact"]]
    bars = plt.barh(most_impacted["Title"], most_impacted["occupation_impact"], color=colors)
    plt.axvline(0, color="black", linewidth=1)
    plt.title("Most Impacted Occupations (Our Full Model)", fontsize=16, pad=20)
    plt.xlabel("Occupation Impact Score", fontsize=12)
    plt.ylabel("", fontsize=12)

    for bar in bars:
        width = bar.get_width()
        label_x_pos = width - 0.02 if width < 0 else width + 0.02
        ha = "right" if width < 0 else "left"
        plt.text(label_x_pos, bar.get_y() + bar.get_height() / 2, f"{width:.0%}", va="center", ha=ha, fontsize=10)

    plt.gca().xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    plt.tight_layout()
    plt.savefig(f"{output_dir}/most_impacted_jobs.png", dpi=300)
    plt.close()

    # 2. Eloundou Exposure vs. Full Model Impact
    plt.figure(figsize=(12, 10))
    sns.scatterplot(
        data=clean_impact_report_df,
        x="eloundou_exposure_mid",
        y="occupation_impact",
        hue="dominant_demand",
        palette=DEMAND_PALETTE,
        alpha=0.5,
        s=15,
    )

    x_vals = np.array([clean_impact_report_df["eloundou_exposure_mid"].min(), clean_impact_report_df["eloundou_exposure_mid"].max()])
    plt.plot(x_vals, -x_vals, "--", color="grey", label="Naive Expectation (Impact = -Exposure)")

    plt.title("Eloundou Exposure vs. Full Model Impact", fontsize=16, pad=20)
    plt.xlabel("Eloundou Exposure (Mid)", fontsize=12)
    plt.ylabel("Our Occupation Impact Score", fontsize=12)
    plt.axhline(0, color="black", linewidth=0.5, linestyle=":")
    plt.legend(title="Dominant Demand Type")

    clean_impact_report_df["difference_from_naive"] = (
        clean_impact_report_df["occupation_impact"] + clean_impact_report_df["eloundou_exposure_mid"]
    )
    outliers = clean_impact_report_df.nlargest(5, "difference_from_naive")

    for _, row in outliers.iterrows():
        plt.annotate(
            row["Title"],
            (row["eloundou_exposure_mid"], row["occupation_impact"]),
            xytext=(12, 6),
            textcoords="offset points",
            fontsize=8,
            alpha=0.9,
            arrowprops={"arrowstyle": "->", "color": "grey", "lw": 0.8},
        )

    plt.gca().xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    plt.gca().yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    plt.tight_layout()
    plt.savefig(f"{output_dir}/exposure_vs_impact.png", dpi=300)
    plt.close()

    # 3. Occupations most different from naive exposure prediction
    plt.figure(figsize=(14, 8))
    outliers_sorted = outliers.sort_values("difference_from_naive", ascending=True)

    plt.barh(outliers_sorted["Title"], outliers_sorted["difference_from_naive"], color="#4575b4")
    plt.title("Occupations Most Different from Exposure-Only Data", fontsize=16, pad=20)
    plt.xlabel("Difference Score (Our Impact vs. Naive Negative Exposure)", fontsize=12)
    plt.ylabel("")

    for i, row in outliers_sorted.iterrows():
        plt.text(
            row["difference_from_naive"] - 0.02,
            list(outliers_sorted["Title"]).index(row["Title"]),
            f"Impact: {row['occupation_impact']:.0%} | Exp: {row['eloundou_exposure_mid']:.0%}",
            va="center",
            ha="right",
            color="white",
            fontweight="bold",
            fontsize=9,
        )

    plt.gca().xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    plt.tight_layout()
    plt.savefig(f"{output_dir}/biggest_differences.png", dpi=300)
    plt.close()

    # 4. Claude conversation share by demand type, stacked by occupational category
    classified_path = "data/output/classified_all_tasks.csv"
    conv_pct_path = "data/raw/anthropic_task_conversation_pct.csv"
    if os.path.exists(classified_path) and os.path.exists(conv_pct_path):
        classified_tasks_df = pd.read_csv(classified_path)
        task_conv_pct_df = pd.read_csv(conv_pct_path)

        classified_tasks_df["task_lower"] = classified_tasks_df["Task"].str.lower().str.strip()
        task_conv_pct_df["task_lower"] = task_conv_pct_df["task_name"].str.lower().str.strip()

        demand_types = ["Bounded", "Unbounded", "Adversarial"]

        # One demand type per unique task text
        unique_classified_df = classified_tasks_df[classified_tasks_df["Demand Type"] != "ERROR"].drop_duplicates("task_lower")[
            ["task_lower", "Demand Type"]
        ]

        # Task share: fraction of all classified O*NET tasks in each demand type
        total_unique_tasks = len(unique_classified_df)
        pct_tasks = [(unique_classified_df["Demand Type"] == dt).sum() / total_unique_tasks * 100 for dt in demand_types]

        # Map each occupation to its SOC major group
        valid_classified_df = classified_tasks_df[classified_tasks_df["Demand Type"] != "ERROR"].copy()
        valid_classified_df["soc_major"] = valid_classified_df["O*NET-SOC Code"].str[:2]
        valid_classified_df["soc_group"] = valid_classified_df["soc_major"].map(SOC_MAJOR_GROUPS).fillna("Other")

        # Unique (task, soc_group) pairs — a task appearing in many occupations within one group is counted once
        task_group_df = valid_classified_df[["task_lower", "soc_group"]].drop_duplicates()
        # Distribute each task's conversation pct equally across all distinct SOC groups it appears in
        n_groups_per_task = task_group_df.groupby("task_lower").size().rename("n_groups")
        task_group_df = task_group_df.merge(n_groups_per_task, on="task_lower")
        task_group_df = task_group_df.merge(unique_classified_df, on="task_lower")
        task_group_df = task_group_df.merge(task_conv_pct_df[["task_lower", "pct"]], on="task_lower", how="inner")
        task_group_df["adjusted_pct"] = task_group_df["pct"] / task_group_df["n_groups"]

        # Roll up to (Demand Type, soc_group) and normalize to total matched pct
        group_demand_df = task_group_df.groupby(["Demand Type", "soc_group"])["adjusted_pct"].sum().reset_index()
        total_matched_pct = group_demand_df["adjusted_pct"].sum()
        group_demand_df["norm_pct"] = group_demand_df["adjusted_pct"] / total_matched_pct * 100

        # Keep top 10 groups by total conversation share; collapse the rest into "Other"
        top_groups = group_demand_df.groupby("soc_group")["norm_pct"].sum().nlargest(10).index.tolist()
        group_demand_df["plot_group"] = group_demand_df["soc_group"].apply(lambda g: g if g in top_groups else "Other")
        plot_df = group_demand_df.groupby(["Demand Type", "plot_group"])["norm_pct"].sum().reset_index()

        # Pivot: rows = demand types, columns = occupational groups
        pivot_df = plot_df.pivot(index="Demand Type", columns="plot_group", values="norm_pct").fillna(0)
        pivot_df = pivot_df.reindex(demand_types)

        # Sort columns by total share descending, "Other" last
        col_totals = pivot_df.drop(columns=["Other"], errors="ignore").sum()
        sorted_cols = col_totals.sort_values(ascending=False).index.tolist()
        if "Other" in pivot_df.columns:
            sorted_cols = sorted_cols + ["Other"]
        pivot_df = pivot_df[sorted_cols]

        # Color palette for occupational groups
        group_palette = sns.color_palette("tab20", n_colors=len(sorted_cols))
        color_map = {col: group_palette[i] for i, col in enumerate(sorted_cols)}
        if "Other" in color_map:
            color_map["Other"] = "#cccccc"

        bar_width = 0.35
        x_positions = np.arange(len(demand_types))

        fig, ax = plt.subplots(figsize=(13, 7))

        # Task share: simple reference bars on the left of each group
        task_bar_positions = x_positions - bar_width / 2
        task_bar_objs = ax.bar(task_bar_positions, pct_tasks, width=bar_width, color="lightgrey", edgecolor="grey", zorder=2)
        for bar in task_bar_objs:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.4,
                f"{bar.get_height():.1f}%",
                ha="center",
                va="bottom",
                fontsize=8,
                color="dimgrey",
            )

        # Conversation share: stacked by occupational category on the right of each group
        conv_bar_positions = x_positions + bar_width / 2
        bottom = np.zeros(len(demand_types))
        for group in sorted_cols:
            vals = pivot_df[group].values
            ax.bar(conv_bar_positions, vals, width=bar_width, bottom=bottom, color=color_map[group], edgecolor="white", linewidth=0.3)
            bottom += vals

        # Total label on top of each stacked bar
        for i, dt in enumerate(demand_types):
            total = pivot_df.loc[dt].sum()
            ax.text(conv_bar_positions[i], total + 0.4, f"{total:.1f}%", ha="center", va="bottom", fontsize=8)

        ax.set_xticks(x_positions)
        ax.set_xticklabels(demand_types, fontsize=11)
        ax.set_ylabel("Share of Matched Conversations (%)", fontsize=10)
        ax.yaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=0))

        legend_handles = [Patch(color=color_map[g], label=g) for g in sorted_cols]
        legend_handles.append(Patch(facecolor="lightgrey", edgecolor="grey", label="O*NET task share (reference)"))
        ax.legend(handles=legend_handles, fontsize=8, loc="upper left", bbox_to_anchor=(1.01, 1), borderaxespad=0)

        ax.set_title(
            f"Claude Conversation Share by Demand Type and Occupational Category\n"
            f"(matched to {total_matched_pct:.0f}% of conversation volume; right bars stacked by occupational category)",
            fontsize=11,
        )
        plt.tight_layout()
        plt.savefig(f"{output_dir}/usage_by_demand_type.png", dpi=300, bbox_inches="tight")
        plt.close()

    # 5. Task importance vs. AI penetration by demand type
    task_ratings_path = "data/raw/onet_task_ratings.csv"
    task_penetration_path = "data/raw/anthropic_task_penetration.csv"
    if os.path.exists(classified_path) and os.path.exists(task_ratings_path) and os.path.exists(task_penetration_path):
        importance_classified_df = pd.read_csv(classified_path)
        importance_classified_df = importance_classified_df[importance_classified_df["Demand Type"] != "ERROR"]
        task_ratings_df = pd.read_csv(task_ratings_path)
        task_penetration_raw_df = pd.read_csv(task_penetration_path)
        task_penetration_raw_df["task_lower"] = task_penetration_raw_df["task"].str.lower().str.strip()

        # Join ratings by Task ID; join penetration by lowercased text
        importance_df = importance_classified_df.drop_duplicates("Task ID").merge(task_ratings_df, on="Task ID", how="inner")
        importance_df["task_lower"] = importance_df["Task"].str.lower().str.strip()
        importance_df = importance_df.merge(task_penetration_raw_df[["task_lower", "penetration"]], on="task_lower", how="inner")
        importance_df["ai_penetrated"] = importance_df["penetration"] > 0

        plt.figure(figsize=(12, 7))
        sns.boxplot(
            data=importance_df,
            x="Demand Type",
            y="task_importance",
            hue="ai_penetrated",
            order=["Bounded", "Unbounded", "Adversarial"],
            hue_order=[True, False],
            palette={True: "#2166ac", False: "#d1e5f0"},
            width=0.5,
        )

        y_min = importance_df["task_importance"].min()
        for dt_idx, demand_type in enumerate(["Bounded", "Unbounded", "Adversarial"]):
            for pen_idx, penetrated in enumerate([True, False]):
                n = len(importance_df[(importance_df["Demand Type"] == demand_type) & (importance_df["ai_penetrated"] == penetrated)])
                x_offset = -0.2 if pen_idx == 0 else 0.2
                plt.text(dt_idx + x_offset, y_min - 0.15, f"n={n}", ha="center", fontsize=8, color="dimgrey")

        plt.title(
            "Task Importance vs. AI Penetration by Demand Type\n" "Are AI-penetrated Bounded tasks the important ones or peripheral ones?",
            fontsize=12,
        )
        plt.xlabel("Demand Type", fontsize=11)
        plt.ylabel("Task Importance Score", fontsize=11)
        handles_imp, _ = plt.gca().get_legend_handles_labels()
        plt.legend(handles=handles_imp, labels=["AI Penetrated (penetration > 0)", "Not Penetrated"], title="AI Coverage")
        plt.tight_layout()
        plt.savefig(f"{output_dir}/task_importance_vs_penetration.png", dpi=300)
        plt.close()

    print(f"Visualizations saved to {output_dir}")


if __name__ == "__main__":
    main()
