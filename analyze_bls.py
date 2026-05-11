"""
analyze_bls.py
──────────────
Analyzes the Bureau of Labor Statistics (BLS) Occupational Employment and Wage Statistics (OEWS) data.
Computes year-over-year employment and wage growth trends for detailed occupations,
which are then used to validate the AI labor impact model predictions.

Inputs:
  • data/raw/bls/oesm23nat.zip  — 2023 national-only file
  • data/raw/bls/oesm24all.zip  — 2024 all-areas file (national rows filtered by AREA_TYPE==1)

Output:
  • data/output/bls_trends.csv
"""

import os
import zipfile

import pandas as pd


def load_bls_data(zip_path):
    print(f"Reading {zip_path}...")
    with zipfile.ZipFile(zip_path) as zip_file:
        xls_files = [f for f in zip_file.namelist() if f.endswith(".xlsx")]
        if not xls_files:
            print(f"No .xlsx file found in {zip_path}")
            return None

        print(f"Found {xls_files[0]}")
        with zip_file.open(xls_files[0]) as excel_file:
            bls_dataframe = pd.read_excel(excel_file)

    bls_dataframe.columns = [str(c).upper().strip() for c in bls_dataframe.columns]

    # Filter to national cross-industry data. The 2024 all-areas file requires
    # explicit area and ownership filters; the 2023 national file already satisfies
    # them, but filtering is harmless.
    if "AREA_TYPE" in bls_dataframe.columns:
        bls_dataframe = bls_dataframe[bls_dataframe["AREA_TYPE"] == 1]
    if "OWN_CODE" in bls_dataframe.columns:
        bls_dataframe = bls_dataframe[bls_dataframe["OWN_CODE"] == 1235]
    # NAICS '000000' (2024 all-areas) and 0 (2023 national) both mean cross-industry
    if "NAICS" in bls_dataframe.columns:
        bls_dataframe = bls_dataframe[bls_dataframe["NAICS"].astype(str).str.strip("0") == ""]

    return bls_dataframe


def main():
    bls_data_path_2024 = "data/raw/bls/oesm24all.zip"
    bls_data_path_2023 = "data/raw/bls/oesm23nat.zip"

    if not os.path.exists(bls_data_path_2024) or not os.path.exists(bls_data_path_2023):
        print("BLS data files not found. Please run: node download_bls.js")
        return

    bls_data_2024 = load_bls_data(bls_data_path_2024)
    bls_data_2023 = load_bls_data(bls_data_path_2023)

    bls_data_2024 = bls_data_2024[bls_data_2024["O_GROUP"] == "detailed"] if "O_GROUP" in bls_data_2024.columns else bls_data_2024
    bls_data_2023 = bls_data_2023[bls_data_2023["O_GROUP"] == "detailed"] if "O_GROUP" in bls_data_2023.columns else bls_data_2023

    target_columns = ["OCC_CODE", "OCC_TITLE", "TOT_EMP", "A_MEDIAN"]
    bls_data_2024 = bls_data_2024[target_columns].copy()
    bls_data_2023 = bls_data_2023[target_columns].copy()

    for dataset in [bls_data_2024, bls_data_2023]:
        for col in ["TOT_EMP", "A_MEDIAN"]:
            dataset[col] = pd.to_numeric(dataset[col].astype(str).str.replace(",", "").str.replace("*", ""), errors="coerce")

    merged_bls_data = bls_data_2023.merge(bls_data_2024, on="OCC_CODE", suffixes=("_23", "_24"))

    merged_bls_data["emp_growth"] = (merged_bls_data["TOT_EMP_24"] - merged_bls_data["TOT_EMP_23"]) / merged_bls_data["TOT_EMP_23"]
    merged_bls_data["wage_growth"] = (merged_bls_data["A_MEDIAN_24"] - merged_bls_data["A_MEDIAN_23"]) / merged_bls_data["A_MEDIAN_23"]

    print(merged_bls_data.head())
    merged_bls_data.to_csv("data/output/bls_trends.csv", index=False)
    print("Saved data/output/bls_trends.csv")
