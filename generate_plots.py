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
  • usage_by_demand_type.png      — Claude conversation share vs. task share by demand type
"""

import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.ticker import PercentFormatter

from plot_constants import DEMAND_PALETTE


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

    # 4. Claude conversation share vs. O*NET task share by demand type
    classified_path = "data/output/classified_all_tasks.csv"
    conv_pct_path = "data/raw/anthropic_task_conversation_pct.csv"
    if os.path.exists(classified_path) and os.path.exists(conv_pct_path):
        classified_tasks_df = pd.read_csv(classified_path)
        task_conv_pct_df = pd.read_csv(conv_pct_path)

        classified_tasks_df["task_lower"] = classified_tasks_df["Task"].str.lower().str.strip()
        task_conv_pct_df["task_lower"] = task_conv_pct_df["task_name"].str.lower().str.strip()

        # One demand type per unique task text (a task may appear across many occupations)
        unique_classified_df = classified_tasks_df[classified_tasks_df["Demand Type"] != "ERROR"].drop_duplicates("task_lower")[
            ["task_lower", "Demand Type"]
        ]

        matched_conv_df = task_conv_pct_df.merge(unique_classified_df, on="task_lower", how="inner")

        demand_types = ["Bounded", "Unbounded", "Adversarial"]
        total_unique_tasks = len(unique_classified_df)
        total_matched_conv_pct = matched_conv_df["pct"].sum()

        # Task share: fraction of all classified O*NET tasks in each demand type
        pct_tasks = [(unique_classified_df["Demand Type"] == dt).sum() / total_unique_tasks * 100 for dt in demand_types]

        # Conversation share: fraction of matched conversations in each demand type (normalized to matched)
        pct_conversations = [
            matched_conv_df[matched_conv_df["Demand Type"] == dt]["pct"].sum() / total_matched_conv_pct * 100 for dt in demand_types
        ]

        bar_width = 0.35
        x_positions = range(len(demand_types))

        fig, ax = plt.subplots(figsize=(9, 6))
        task_bars = ax.bar(
            [xi - bar_width / 2 for xi in x_positions],
            pct_tasks,
            width=bar_width,
            color="lightgrey",
            edgecolor="grey",
            label="Share of O*NET tasks",
        )
        conv_bars = ax.bar(
            [xi + bar_width / 2 for xi in x_positions],
            pct_conversations,
            width=bar_width,
            color=[DEMAND_PALETTE[dt] for dt in demand_types],
            edgecolor="white",
            alpha=0.85,
            label="Share of Claude conversations",
        )

        for bar in task_bars:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.5,
                f"{bar.get_height():.1f}%",
                ha="center",
                va="bottom",
                fontsize=9,
                color="dimgrey",
            )
        for bar in conv_bars:
            ax.text(
                bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5, f"{bar.get_height():.1f}%", ha="center", va="bottom", fontsize=9
            )

        ax.set_xticks(list(x_positions))
        ax.set_xticklabels(demand_types, fontsize=11)
        ax.set_ylabel("Share of Total (%)", fontsize=10)
        ax.yaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=0))
        coverage_pct = total_matched_conv_pct
        ax.set_title(
            f"Claude Conversation Share vs. O*NET Task Share by Demand Type\n"
            f"(conversations cover {coverage_pct:.0f}% of all tasks; shares normalized to matched tasks)",
            fontsize=11,
        )
        ax.legend(fontsize=9)
        plt.tight_layout()
        plt.savefig(f"{output_dir}/usage_by_demand_type.png", dpi=300, bbox_inches="tight")
        plt.close()

    print(f"Visualizations saved to {output_dir}")


if __name__ == "__main__":
    main()
