"""
analyze_bls.py
──────────────
Analyzes BLS Occupational Employment and Wage Statistics (OEWS) data across
multiple years. Computes year-over-year growth for each consecutive pair of
years, plus a composite total change from the anchor year (2022) to the most
recent year.

Inputs (any subset that exists under data/raw/bls/):
  • oesm05nat.zip – oesm14nat.zip — deep-history national files (2005–2014; .xls format for 2005–2013)
  • oesm15nat.zip – oesm21nat.zip — historical national files (2015–2021)
  • oesm22nat.zip — 2022 national-only file (merge anchor; composite base)
  • oesm23nat.zip — 2023 national-only file
  • oesm24all.zip — 2024 all-areas file (filtered to AREA_TYPE==1)
  • oesm25all.zip — 2025 all-areas file (filtered to AREA_TYPE==1)

Output:
  • data/output/bls_trends.csv
    Core columns (2022-onward):
      TOT_EMP_{yy}, A_MEDIAN_{yy}         — employment and median wage per year
      emp_growth_{yy}_{yy}                — YoY growth for 2022→2023 onward
      emp_growth_composite                 — 2022→latest
    Historical columns (pre-2022, prefixed hist_ to exclude from auto-detection):
      TOT_EMP_{yy}, A_MEDIAN_{yy}         — employment and median wage per year
      hist_emp_growth_{yy}_{yy}            — YoY growth for periods before 2022
      hist_emp_growth_pre_ai               — composite from earliest available year → 2022

Note on SOC codes and file formats:
  • 2005–2009: SOC 2000 codes, .xls format (requires xlrd), GROUP column (NaN = detailed)
  • 2010–2013: SOC 2010 codes, .xls format, GROUP column (NaN = detailed)
  • 2014–2018: SOC 2010 codes, .xlsx format, OCC_GROUP column
  • 2019+:      SOC 2018 codes, .xlsx format, O_GROUP column
All joins are left-joins anchored at 2022, preserving the existing 830-occupation result set.
Survivorship when joining against 2022: ~82% for 2005–2009, ~83–87% for 2010–2018.
"""

import os
import zipfile

import pandas as pd

YEAR_CONFIGS = [
    ("05", "data/raw/bls/oesm05nat.zip"),
    ("06", "data/raw/bls/oesm06nat.zip"),
    ("07", "data/raw/bls/oesm07nat.zip"),
    ("08", "data/raw/bls/oesm08nat.zip"),
    ("09", "data/raw/bls/oesm09nat.zip"),
    ("10", "data/raw/bls/oesm10nat.zip"),
    ("11", "data/raw/bls/oesm11nat.zip"),
    ("12", "data/raw/bls/oesm12nat.zip"),
    ("13", "data/raw/bls/oesm13nat.zip"),
    ("14", "data/raw/bls/oesm14nat.zip"),
    ("15", "data/raw/bls/oesm15nat.zip"),
    ("16", "data/raw/bls/oesm16nat.zip"),
    ("17", "data/raw/bls/oesm17nat.zip"),
    ("18", "data/raw/bls/oesm18nat.zip"),
    ("19", "data/raw/bls/oesm19nat.zip"),
    ("20", "data/raw/bls/oesm20nat.zip"),
    ("21", "data/raw/bls/oesm21nat.zip"),
    ("22", "data/raw/bls/oesm22nat.zip"),
    ("23", "data/raw/bls/oesm23nat.zip"),
    ("24", "data/raw/bls/oesm24all.zip"),
    ("25", "data/raw/bls/oesm25all.zip"),
]

# The composite growth column is always anchored at this year, regardless of
# which historical years are available. Do not change without updating
# validate_bls.py and all downstream docs.
COMPOSITE_ANCHOR_YEAR = "22"


def load_bls_data(zip_path: str) -> pd.DataFrame | None:
    """Load BLS OEWS data for one year, filtered to national cross-industry detailed occupations."""
    print(f"Reading {zip_path}...")
    with zipfile.ZipFile(zip_path) as zip_file:
        # Skip layout/field-description files that appear in older zip archives
        xls_files = [
            f
            for f in zip_file.namelist()
            if (f.endswith(".xlsx") or f.endswith(".xls")) and "field" not in f.lower() and "layout" not in f.lower()
        ]
        if not xls_files:
            print(f"No data .xlsx/.xls file found in {zip_path}")
            return None
        print(f"Found {xls_files[0]}")
        with zip_file.open(xls_files[0]) as excel_file:
            bls_dataframe = pd.read_excel(excel_file)

    bls_dataframe.columns = [str(c).upper().strip() for c in bls_dataframe.columns]

    # Filter to national cross-industry data. The all-areas files require
    # explicit area and ownership filters; national-only files already satisfy
    # them, but filtering is harmless.
    if "AREA_TYPE" in bls_dataframe.columns:
        bls_dataframe = bls_dataframe[bls_dataframe["AREA_TYPE"] == 1]
    if "OWN_CODE" in bls_dataframe.columns:
        bls_dataframe = bls_dataframe[bls_dataframe["OWN_CODE"] == 1235]
    # NAICS '000000' (all-areas files) and 0 (national files) both mean cross-industry
    if "NAICS" in bls_dataframe.columns:
        bls_dataframe = bls_dataframe[bls_dataframe["NAICS"].astype(str).str.strip("0") == ""]

    # Group column varies by era:
    #   2019+:      O_GROUP == "detailed"
    #   2012–2018:  OCC_GROUP == "detailed"
    #   2005–2011:  GROUP column; detailed rows have GROUP == NaN (totals/majors have non-NaN values)
    if "O_GROUP" in bls_dataframe.columns:
        bls_dataframe = bls_dataframe[bls_dataframe["O_GROUP"] == "detailed"]
    elif "OCC_GROUP" in bls_dataframe.columns:
        bls_dataframe = bls_dataframe[bls_dataframe["OCC_GROUP"] == "detailed"]
    elif "GROUP" in bls_dataframe.columns:
        bls_dataframe = bls_dataframe[bls_dataframe["GROUP"].isna()]

    # Exclude total/aggregate OCC_CODEs (e.g. "00-0000", "11-0000") that slip
    # through the NaN GROUP filter in pre-2012 files. No detailed occupation
    # code ends in 0000.
    if "OCC_CODE" in bls_dataframe.columns:
        bls_dataframe = bls_dataframe[~bls_dataframe["OCC_CODE"].astype(str).str.endswith("0000")]

    target_columns = ["OCC_CODE", "OCC_TITLE", "TOT_EMP", "A_MEDIAN"]
    available_targets = [c for c in target_columns if c in bls_dataframe.columns]
    bls_dataframe = bls_dataframe[available_targets].copy()

    for col in ["TOT_EMP", "A_MEDIAN"]:
        if col in bls_dataframe.columns:
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

    if COMPOSITE_ANCHOR_YEAR not in year_dataframes:
        print(f"Error: composite anchor year {COMPOSITE_ANCHOR_YEAR} not available.")
        return

    # Anchor all merges at the composite anchor year (2022) to preserve the
    # existing occupation set. Earlier years are left-joined so that occupations
    # whose codes changed across the SOC 2010→2018 revision (2015–2018 data) keep
    # NaN for those historical columns rather than being dropped.
    anchor_df = year_dataframes[COMPOSITE_ANCHOR_YEAR].rename(
        columns={
            "OCC_TITLE": f"OCC_TITLE_{COMPOSITE_ANCHOR_YEAR}",
            "TOT_EMP": f"TOT_EMP_{COMPOSITE_ANCHOR_YEAR}",
            "A_MEDIAN": f"A_MEDIAN_{COMPOSITE_ANCHOR_YEAR}",
        }
    )
    merged_bls_data = anchor_df

    for year_suffix in available_years:
        if year_suffix == COMPOSITE_ANCHOR_YEAR:
            continue
        year_df = year_dataframes[year_suffix].rename(
            columns={
                "OCC_TITLE": f"OCC_TITLE_{year_suffix}",
                "TOT_EMP": f"TOT_EMP_{year_suffix}",
                "A_MEDIAN": f"A_MEDIAN_{year_suffix}",
            }
        )
        merged_bls_data = merged_bls_data.merge(
            year_df[["OCC_CODE"] + [c for c in year_df.columns if c != "OCC_CODE"]],
            on="OCC_CODE",
            how="left",
        )

    # Year-over-year growth for each consecutive pair.
    # Pre-2022 pairs use the hist_ prefix so that validate_bls.py's auto-detection
    # of emp_growth_* columns does not add them to the existing 2×2 grid charts.
    for i in range(len(available_years) - 1):
        prev_year = available_years[i]
        curr_year = available_years[i + 1]
        prefix = "hist_" if curr_year <= COMPOSITE_ANCHOR_YEAR else ""
        merged_bls_data[f"{prefix}emp_growth_{prev_year}_{curr_year}"] = (
            merged_bls_data[f"TOT_EMP_{curr_year}"] - merged_bls_data[f"TOT_EMP_{prev_year}"]
        ) / merged_bls_data[f"TOT_EMP_{prev_year}"]
        if f"A_MEDIAN_{prev_year}" in merged_bls_data.columns and f"A_MEDIAN_{curr_year}" in merged_bls_data.columns:
            merged_bls_data[f"{prefix}wage_growth_{prev_year}_{curr_year}"] = (
                merged_bls_data[f"A_MEDIAN_{curr_year}"] - merged_bls_data[f"A_MEDIAN_{prev_year}"]
            ) / merged_bls_data[f"A_MEDIAN_{prev_year}"]

    # Composite: always 2022 → latest year
    latest_year = [y for y in available_years if y > COMPOSITE_ANCHOR_YEAR]
    if latest_year:
        latest_year = latest_year[-1]
        merged_bls_data["emp_growth_composite"] = (
            merged_bls_data[f"TOT_EMP_{latest_year}"] - merged_bls_data[f"TOT_EMP_{COMPOSITE_ANCHOR_YEAR}"]
        ) / merged_bls_data[f"TOT_EMP_{COMPOSITE_ANCHOR_YEAR}"]
        if f"A_MEDIAN_{latest_year}" in merged_bls_data.columns:
            merged_bls_data["wage_growth_composite"] = (
                merged_bls_data[f"A_MEDIAN_{latest_year}"] - merged_bls_data[f"A_MEDIAN_{COMPOSITE_ANCHOR_YEAR}"]
            ) / merged_bls_data[f"A_MEDIAN_{COMPOSITE_ANCHOR_YEAR}"]

    # Pre-AI composite: earliest available year → 2022.
    # Uses hist_ prefix to stay out of auto-detection.
    earliest_year = available_years[0]
    if earliest_year < COMPOSITE_ANCHOR_YEAR and f"TOT_EMP_{earliest_year}" in merged_bls_data.columns:
        merged_bls_data["hist_emp_growth_pre_ai"] = (
            merged_bls_data[f"TOT_EMP_{COMPOSITE_ANCHOR_YEAR}"] - merged_bls_data[f"TOT_EMP_{earliest_year}"]
        ) / merged_bls_data[f"TOT_EMP_{earliest_year}"]
        if f"A_MEDIAN_{earliest_year}" in merged_bls_data.columns:
            merged_bls_data["hist_wage_growth_pre_ai"] = (
                merged_bls_data[f"A_MEDIAN_{COMPOSITE_ANCHOR_YEAR}"] - merged_bls_data[f"A_MEDIAN_{earliest_year}"]
            ) / merged_bls_data[f"A_MEDIAN_{earliest_year}"]

    os.makedirs("data/output", exist_ok=True)
    merged_bls_data.to_csv("data/output/bls_trends.csv", index=False)

    growth_cols = [c for c in merged_bls_data.columns if "growth" in c]
    print(f"Saved data/output/bls_trends.csv ({len(merged_bls_data)} occupations)")
    print(f"Growth columns: {growth_cols}")


if __name__ == "__main__":
    main()
