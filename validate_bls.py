import os

import matplotlib.pyplot as plt
import pandas as pd
import scipy.stats as stats
import seaborn as sns


def main():
    # Load BLS trends
    bls_trends_df = pd.read_csv("data/output/bls_trends.csv")

    # Load Occupation Impact
    occupation_impact_df = pd.read_csv("data/output/occupation_impact_report.csv")

    # Merge
    # O*NET-SOC has format '11-1011.00', BLS OCC_CODE is '11-1011'
    occupation_impact_df["OCC_CODE"] = occupation_impact_df["O*NET-SOC Code"].astype(str).str.split(".").str[0]

    # Since multiple O*NET codes might map to one BLS code, let's group by BLS code
    # and take the mean impact score
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

    # Drop NaNs or infinite values from growth columns
    merged_validation_df = merged_validation_df.replace([float("inf"), -float("inf")], pd.NA)
    merged_validation_df = merged_validation_df.dropna(subset=["emp_growth", "wage_growth", "occupation_impact"])

    # Remove crazy outliers in employment growth just to be safe (e.g., >100% or <-50% in one year)
    merged_validation_df = merged_validation_df[(merged_validation_df["emp_growth"] < 1.0) & (merged_validation_df["emp_growth"] > -0.5)]

    print(f"Matched {len(merged_validation_df)} occupations for validation.")

    output_dir = "data/output/visualizations"
    os.makedirs(output_dir, exist_ok=True)
    sns.set_theme(style="whitegrid")

    # Plot 1: Impact vs Emp Growth
    plt.figure(figsize=(10, 8))
    sns.regplot(data=merged_validation_df, x="occupation_impact", y="emp_growth", scatter_kws={"alpha": 0.5})

    # Calculate correlation
    r_emp, p_emp = stats.pearsonr(merged_validation_df["occupation_impact"], merged_validation_df["emp_growth"])

    plt.title(f"Predicted AI Impact vs Actual Employment Growth (BLS YoY)\nPearson r: {r_emp:.3f} (p={p_emp:.3f})")
    plt.xlabel("Our Occupation Impact Score (<0 = Decline, >0 = Expansion)")
    plt.ylabel("Year-over-Year Employment Growth (%)")
    plt.axhline(0, color="red", linestyle="--", linewidth=1)
    plt.axvline(0, color="red", linestyle="--", linewidth=1)

    plt.tight_layout()
    plt.savefig(f"{output_dir}/bls_emp_growth_vs_impact.png", dpi=300)
    plt.close()

    # Plot 2: Impact vs Wage Growth
    plt.figure(figsize=(10, 8))
    sns.regplot(data=merged_validation_df, x="occupation_impact", y="wage_growth", scatter_kws={"alpha": 0.5})

    r_wage, p_wage = stats.pearsonr(merged_validation_df["occupation_impact"], merged_validation_df["wage_growth"])

    plt.title(f"Predicted AI Impact vs Actual Wage Growth (BLS YoY)\nPearson r: {r_wage:.3f} (p={p_wage:.3f})")
    plt.xlabel("Our Occupation Impact Score (<0 = Decline, >0 = Expansion)")
    plt.ylabel("Year-over-Year Median Wage Growth (%)")
    plt.axhline(0, color="red", linestyle="--", linewidth=1)
    plt.axvline(0, color="red", linestyle="--", linewidth=1)

    plt.tight_layout()
    plt.savefig(f"{output_dir}/bls_wage_growth_vs_impact.png", dpi=300)
    plt.close()

    # Plot 3: Productivity Premium vs Red Queen's Race (Emp Growth vs Wage Growth)
    plt.figure(figsize=(12, 10))
    sns.scatterplot(
        data=merged_validation_df,
        x="emp_growth",
        y="wage_growth",
        hue="dominant_demand",
        palette={"Bounded": "#d73027", "Unbounded": "#fee08b", "Adversarial": "#1a9850"},
        alpha=0.7,
        s=60,
    )
    plt.title("Productivity Premium vs Red Queen's Race\nEmployment Growth vs Wage Growth by Demand Type")
    plt.xlabel("Year-over-Year Employment Growth (%)")
    plt.ylabel("Year-over-Year Median Wage Growth (%)")
    plt.axhline(0, color="black", linestyle="--", linewidth=1)
    plt.axvline(0, color="black", linestyle="--", linewidth=1)

    plt.tight_layout()
    plt.savefig(f"{output_dir}/productivity_vs_red_queen.png", dpi=300)
    plt.close()

    # Compare with Eloundou exposure only correlation
    r_emp_elo, p_emp_elo = stats.pearsonr(merged_validation_df["eloundou_exposure_mid"], merged_validation_df["emp_growth"])
    r_wage_elo, p_wage_elo = stats.pearsonr(merged_validation_df["eloundou_exposure_mid"], merged_validation_df["wage_growth"])

    print("\n--- Correlation Results ---")
    print(f"Our Impact Score vs Emp Growth:  r = {r_emp:.3f} (p={p_emp:.3f})")
    print(f"Eloundou Exposure vs Emp Growth: r = {r_emp_elo:.3f} (p={p_emp_elo:.3f})")
    print(f"Our Impact Score vs Wage Growth: r = {r_wage:.3f} (p={p_wage:.3f})")
    print(f"Eloundou Exposure vs Wage Growth:r = {r_wage_elo:.3f} (p={p_wage_elo:.3f})")

    print("\n--- Productivity Premium vs Red Queen's Race ---")
    demand_stats = (
        merged_validation_df.groupby("dominant_demand")
        .agg({"emp_growth": "mean", "wage_growth": "mean", "Title": "count"})
        .rename(columns={"Title": "N_Occupations"})
    )

    print(demand_stats.to_string())


if __name__ == "__main__":
    main()
