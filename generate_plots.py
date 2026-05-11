"""
generate_plots.py
─────────────────
Generates visualizations from the occupation impact report.

Inputs:
  • data/output/occupation_impact_report.csv

Outputs (saved to data/output/visualizations/):
  • most_impacted_jobs.png        — Top 15 highest/lowest impact occupations
  • exposure_vs_impact.png        — Eloundou exposure vs. our full model impact score
  • biggest_differences.png       — Occupations most different from naive exposure prediction
"""

import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


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
        plt.text(label_x_pos, bar.get_y() + bar.get_height() / 2, f"{width:.2f}", va="center", ha=ha, fontsize=10)

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
        palette={"Bounded": "#d73027", "Unbounded": "#fee08b", "Adversarial": "#1a9850"},
        alpha=0.7,
        s=60,
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
    outliers = clean_impact_report_df.nlargest(10, "difference_from_naive")

    for i, row in outliers.iterrows():
        plt.annotate(
            row["Title"],
            (row["eloundou_exposure_mid"], row["occupation_impact"]),
            xytext=(5, 5),
            textcoords="offset points",
            fontsize=8,
            alpha=0.8,
        )

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
            f"Impact: {row['occupation_impact']:.2f} | Exp: {row['eloundou_exposure_mid']:.2f}",
            va="center",
            ha="right",
            color="white",
            fontweight="bold",
            fontsize=9,
        )

    plt.tight_layout()
    plt.savefig(f"{output_dir}/biggest_differences.png", dpi=300)
    plt.close()

    print(f"Visualizations saved to {output_dir}")


if __name__ == "__main__":
    main()
