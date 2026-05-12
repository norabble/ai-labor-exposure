"""
analyze_bls.py
──────────────
Analyzes BLS Occupational Employment and Wage Statistics (OEWS) data across
multiple years. Computes year-over-year growth for each consecutive pair of
years, plus a composite total change from the anchor year (2022) to the most
recent year.

Inputs (any subset that exists under data/raw/bls/):
  • oesm22nat.zip — 2022 national-only file
  • oesm23nat.zip — 2023 national-only file
  • oesm24all.zip — 2024 all-areas file (filtered to AREA_TYPE==1)

Output:
  • data/output/bls_trends.csv
    Columns include TOT_EMP_{yy}, A_MEDIAN_{yy} per year, then:
      emp_growth_{yy}_{yy}  / wage_growth_{yy}_{yy}  for each consecutive pair
      emp_growth_composite  / wage_growth_composite   from anchor to latest year
"""

import os
import zipfile

import pandas as pd

YEAR_CONFIGS = [
    ("22", "data/raw/bls/oesm22nat.zip"),
    ("23", "data/raw/bls/oesm23nat.zip"),
    ("24", "data/raw/bls/oesm24all.zip"),
]


def load_bls_data(zip_path: str) -> pd.DataFrame | None:
    """Load BLS OEWS data for one year, filtered to national cross-industry detailed occupations."""
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
    # explicit area and ownership filters; the national-only files already satisfy
    # them, but filtering is harmless.
    if "AREA_TYPE" in bls_dataframe.columns:
        bls_dataframe = bls_dataframe[bls_dataframe["AREA_TYPE"] == 1]
    if "OWN_CODE" in bls_dataframe.columns:
        bls_dataframe = bls_dataframe[bls_dataframe["OWN_CODE"] == 1235]
    # NAICS '000000' (2024 all-areas) and 0 (national files) both mean cross-industry
    if "NAICS" in bls_dataframe.columns:
        bls_dataframe = bls_dataframe[bls_dataframe["NAICS"].astype(str).str.strip("0") == ""]

    if "O_GROUP" in bls_dataframe.columns:
        bls_dataframe = bls_dataframe[bls_dataframe["O_GROUP"] == "detailed"]

    target_columns = ["OCC_CODE", "OCC_TITLE", "TOT_EMP", "A_MEDIAN"]
    bls_dataframe = bls_dataframe[target_columns].copy()

    for col in ["TOT_EMP", "A_MEDIAN"]:
        bls_dataframe[col] = pd.to_numeric(
            bls_dataframe[col].astype(str).str.replace(",", "").str.replace("*", ""),
            errors="coerce",
        )

    return bls_dataframe


def main():
    year_dataframes: dict[str, pd.DataFrame] = {}
    for year_suffix, zip_path in YEAR_CONFIGS:
        if os.path.exists(zip_path):
            year_df = load_bls_data(zip_path)
            if year_df is not None:
                year_dataframes[year_suffix] = year_df
        else:
            print(f"Warning: {zip_path} not found, skipping year '{year_suffix}'")

    if len(year_dataframes) < 2:
        print("Need at least 2 years of data. Please run: node download_bls.js")
        return

    available_years = sorted(year_dataframes.keys())
    print(f"Building trends for years: {available_years}")

    # Merge all years onto a common OCC_CODE index
    anchor_year = available_years[0]
    merged_bls_data = year_dataframes[anchor_year].rename(
        columns={
            "OCC_TITLE": f"OCC_TITLE_{anchor_year}",
            "TOT_EMP": f"TOT_EMP_{anchor_year}",
            "A_MEDIAN": f"A_MEDIAN_{anchor_year}",
        }
    )

    for year_suffix in available_years[1:]:
        year_df = year_dataframes[year_suffix].rename(
            columns={
                "OCC_TITLE": f"OCC_TITLE_{year_suffix}",
                "TOT_EMP": f"TOT_EMP_{year_suffix}",
                "A_MEDIAN": f"A_MEDIAN_{year_suffix}",
            }
        )
        merged_bls_data = merged_bls_data.merge(
            year_df[["OCC_CODE", f"TOT_EMP_{year_suffix}", f"A_MEDIAN_{year_suffix}"]],
            on="OCC_CODE",
        )

    # Year-over-year growth for each consecutive pair
    for i in range(len(available_years) - 1):
        prev_year = available_years[i]
        curr_year = available_years[i + 1]
        merged_bls_data[f"emp_growth_{prev_year}_{curr_year}"] = (
            merged_bls_data[f"TOT_EMP_{curr_year}"] - merged_bls_data[f"TOT_EMP_{prev_year}"]
        ) / merged_bls_data[f"TOT_EMP_{prev_year}"]
        merged_bls_data[f"wage_growth_{prev_year}_{curr_year}"] = (
            merged_bls_data[f"A_MEDIAN_{curr_year}"] - merged_bls_data[f"A_MEDIAN_{prev_year}"]
        ) / merged_bls_data[f"A_MEDIAN_{prev_year}"]

    # Composite: total change from anchor year to the most recent year
    latest_year = available_years[-1]
    merged_bls_data["emp_growth_composite"] = (
        merged_bls_data[f"TOT_EMP_{latest_year}"] - merged_bls_data[f"TOT_EMP_{anchor_year}"]
    ) / merged_bls_data[f"TOT_EMP_{anchor_year}"]
    merged_bls_data["wage_growth_composite"] = (
        merged_bls_data[f"A_MEDIAN_{latest_year}"] - merged_bls_data[f"A_MEDIAN_{anchor_year}"]
    ) / merged_bls_data[f"A_MEDIAN_{anchor_year}"]

    os.makedirs("data/output", exist_ok=True)
    merged_bls_data.to_csv("data/output/bls_trends.csv", index=False)

    growth_cols = [c for c in merged_bls_data.columns if "growth" in c]
    print(f"Saved data/output/bls_trends.csv ({len(merged_bls_data)} occupations)")
    print(f"Growth columns: {growth_cols}")


if __name__ == "__main__":
    main()
