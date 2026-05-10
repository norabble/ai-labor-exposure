"""
analyze_bls.py
──────────────
Analyzes the Bureau of Labor Statistics (BLS) Occupational Employment and Wage Statistics (OEWS) data.
Computes year-over-year employment and wage growth trends for detailed occupations,
which are then used to validate the AI labor impact model predictions.
"""

import os
import zipfile

import pandas as pd


def load_bls_data(zip_path):
    print(f"Reading {zip_path}...")
    with zipfile.ZipFile(zip_path) as zip_file:
        # Find the excel file in the zip
        xls_files = [f for f in zip_file.namelist() if f.endswith(".xlsx")]
        if not xls_files:
            print(f"No .xlsx file found in {zip_path}")
            return None

        print(f"Found {xls_files[0]}")
        with zip_file.open(xls_files[0]) as excel_file:
            bls_dataframe = pd.read_excel(excel_file)

    # Normalize column names
    bls_dataframe.columns = [str(c).upper().strip() for c in bls_dataframe.columns]

    # We need OCC_CODE, OCC_TITLE, TOT_EMP, A_MEDIAN
    # In some older years it might be differently named, but usually it's standard
    # Some rows are aggregates. We only want detailed occupations (O*NET level if possible, but BLS usually provides SOC level)
    # The BLS OEWS data is at the SOC level.

    return bls_dataframe


def main():
    bls_data_path_2023 = "data/raw/bls/oesm23nat.zip"
    bls_data_path_2022 = "data/raw/bls/oesm22nat.zip"

    if not os.path.exists(bls_data_path_2023) or not os.path.exists(bls_data_path_2022):
        print("BLS data files not found. Please download them first.")
        return

    bls_data_2023 = load_bls_data(bls_data_path_2023)
    bls_data_2022 = load_bls_data(bls_data_path_2022)

    # Process and merge...
    # Keep only detailed occupations (O*NET-SOC usually matches SOC for the first 6 digits)

    bls_data_2023 = bls_data_2023[bls_data_2023["O_GROUP"] == "detailed"] if "O_GROUP" in bls_data_2023.columns else bls_data_2023
    bls_data_2022 = bls_data_2022[bls_data_2022["O_GROUP"] == "detailed"] if "O_GROUP" in bls_data_2022.columns else bls_data_2022

    # Select columns
    target_columns = ["OCC_CODE", "OCC_TITLE", "TOT_EMP", "A_MEDIAN"]
    bls_data_2023 = bls_data_2023[target_columns].copy()
    bls_data_2022 = bls_data_2022[target_columns].copy()

    # Clean numeric columns
    for dataset in [bls_data_2023, bls_data_2022]:
        for col in ["TOT_EMP", "A_MEDIAN"]:
            dataset[col] = pd.to_numeric(dataset[col].astype(str).str.replace(",", "").str.replace("*", ""), errors="coerce")

    merged_bls_data = bls_data_2022.merge(bls_data_2023, on="OCC_CODE", suffixes=("_22", "_23"))

    # Calculate YoY change
    merged_bls_data["emp_growth"] = (merged_bls_data["TOT_EMP_23"] - merged_bls_data["TOT_EMP_22"]) / merged_bls_data["TOT_EMP_22"]
    merged_bls_data["wage_growth"] = (merged_bls_data["A_MEDIAN_23"] - merged_bls_data["A_MEDIAN_22"]) / merged_bls_data["A_MEDIAN_22"]

    print(merged_bls_data.head())
    merged_bls_data.to_csv("data/output/bls_trends.csv", index=False)
    print("Saved data/output/bls_trends.csv")


if __name__ == "__main__":
    main()
