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

Outputs:
  • data/output/bls_sector_trends.csv
    One row per SOC major group (soc_major), built from each file's own
    major-group summary rows. Major-group codes are stable across every SOC
    revision, so this series is complete for all 22 sectors in every year —
    unlike the detailed-occupation series below, which loses whole sectors
    before 2019 (Computer and Mathematical keeps 3% of its 2022 employment
    into 2018 because the SOC 2018 revision renumbered every computer code).
    validate_bls.py uses this file for every sector-level growth measure.
    Same column layout as bls_trends.csv, keyed by soc_major instead of
    OCC_CODE. Two level breaks remain: SOC 2000→2010 (2009→2010) and SOC
    2010→2018 (2018→2019) moved some occupations between major groups.
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
Survivorship when joining against 2022: ~82% for 2005–2009, ~83–87% for 2010–2018
overall, but as low as 3% for individual sectors — which is why sector-level
growth comes from bls_sector_trends.csv rather than from these rows.
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


# Occupation-grouping column by file era. Checked in this order: 2019+ files
# also carry an industry-grouping I_GROUP column, which must not be picked up
# by a looser "any column containing GROUP" match.
OCCUPATION_GROUP_COLUMNS = ("O_GROUP", "OCC_GROUP", "GROUP")


def _occupation_group_column(bls_dataframe: pd.DataFrame) -> str | None:
    for column_name in OCCUPATION_GROUP_COLUMNS:
        if column_name in bls_dataframe.columns:
            return column_name
    return None


def _numeric_bls_columns(bls_dataframe: pd.DataFrame) -> pd.DataFrame:
    """Coerce TOT_EMP / A_MEDIAN, which older files store as strings with commas and '*' suppressions."""
    bls_dataframe = bls_dataframe.copy()
    for col in ["TOT_EMP", "A_MEDIAN"]:
        if col in bls_dataframe.columns:
            bls_dataframe[col] = pd.to_numeric(
                bls_dataframe[col].astype(str).str.replace(",", "").str.replace("*", ""),
                errors="coerce",
            )
    return bls_dataframe


def select_detailed_rows(bls_dataframe: pd.DataFrame) -> pd.DataFrame:
    """
    Detailed-occupation rows from one year's national cross-industry frame.

    Group column varies by era:
      2019+:      O_GROUP == "detailed"
      2012–2018:  OCC_GROUP == "detailed"
      2005–2011:  GROUP column; detailed rows have GROUP == NaN (totals/majors have non-NaN values)
    """
    group_column = _occupation_group_column(bls_dataframe)
    if group_column == "GROUP":
        bls_dataframe = bls_dataframe[bls_dataframe[group_column].isna()]
    elif group_column is not None:
        bls_dataframe = bls_dataframe[bls_dataframe[group_column] == "detailed"]

    # Exclude total/aggregate OCC_CODEs (e.g. "00-0000", "11-0000") that slip
    # through the NaN GROUP filter in pre-2012 files. No detailed occupation
    # code ends in 0000.
    if "OCC_CODE" in bls_dataframe.columns:
        bls_dataframe = bls_dataframe[~bls_dataframe["OCC_CODE"].astype(str).str.endswith("0000")]

    target_columns = ["OCC_CODE", "OCC_TITLE", "TOT_EMP", "A_MEDIAN"]
    return _numeric_bls_columns(bls_dataframe[[c for c in target_columns if c in bls_dataframe.columns]])


def select_major_group_rows(bls_dataframe: pd.DataFrame) -> pd.DataFrame:
    """
    The 22 SOC major-group summary rows from one year's frame, keyed by the
    two-digit `soc_major` code. Every era labels these rows "major" in its
    grouping column, and the major-group codes are the same across SOC 2000,
    2010 and 2018, so this is the one level at which the OEWS series is
    directly comparable across the whole 2005→present span.
    """
    group_column = _occupation_group_column(bls_dataframe)
    if group_column is None:
        return pd.DataFrame(columns=["soc_major", "OCC_TITLE", "TOT_EMP", "A_MEDIAN"])
    major_rows = bls_dataframe[bls_dataframe[group_column] == "major"].copy()
    major_rows["soc_major"] = major_rows["OCC_CODE"].astype(str).str[:2]
    target_columns = ["soc_major", "OCC_TITLE", "TOT_EMP", "A_MEDIAN"]
    return _numeric_bls_columns(major_rows[[c for c in target_columns if c in major_rows.columns]]).reset_index(drop=True)


def load_bls_year(zip_path: str) -> pd.DataFrame | None:
    """Load one year's OEWS file, filtered to national cross-industry rows at every grouping level."""
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

    return bls_dataframe


def load_bls_data(zip_path: str) -> pd.DataFrame | None:
    """Load BLS OEWS data for one year, filtered to national cross-industry detailed occupations."""
    year_frame = load_bls_year(zip_path)
    return None if year_frame is None else select_detailed_rows(year_frame)


def attach_growth_columns(trend_df: pd.DataFrame, available_years: list[str]) -> pd.DataFrame:
    """
    Add year-over-year, composite and pre-AI growth columns to a frame that
    already holds TOT_EMP_{yy} / A_MEDIAN_{yy} per year.

    Pre-2022 pairs use the hist_ prefix so that validate_bls.py's auto-detection
    of emp_growth_* columns does not add them to the existing 2×2 grid charts.
    The composite is always 2022 → latest; pre_ai is earliest → 2022. Shared by
    the occupation-level and sector-level trend files so both carry identical
    column layouts.
    """
    trend_df = trend_df.copy()
    for prev_year, curr_year in zip(available_years[:-1], available_years[1:]):
        prefix = "hist_" if curr_year <= COMPOSITE_ANCHOR_YEAR else ""
        trend_df[f"{prefix}emp_growth_{prev_year}_{curr_year}"] = (
            trend_df[f"TOT_EMP_{curr_year}"] - trend_df[f"TOT_EMP_{prev_year}"]
        ) / trend_df[f"TOT_EMP_{prev_year}"]
        if f"A_MEDIAN_{prev_year}" in trend_df.columns and f"A_MEDIAN_{curr_year}" in trend_df.columns:
            trend_df[f"{prefix}wage_growth_{prev_year}_{curr_year}"] = (
                trend_df[f"A_MEDIAN_{curr_year}"] - trend_df[f"A_MEDIAN_{prev_year}"]
            ) / trend_df[f"A_MEDIAN_{prev_year}"]

    later_years = [y for y in available_years if y > COMPOSITE_ANCHOR_YEAR]
    if later_years:
        latest_year = later_years[-1]
        trend_df["emp_growth_composite"] = (trend_df[f"TOT_EMP_{latest_year}"] - trend_df[f"TOT_EMP_{COMPOSITE_ANCHOR_YEAR}"]) / trend_df[
            f"TOT_EMP_{COMPOSITE_ANCHOR_YEAR}"
        ]
        if f"A_MEDIAN_{latest_year}" in trend_df.columns and f"A_MEDIAN_{COMPOSITE_ANCHOR_YEAR}" in trend_df.columns:
            trend_df["wage_growth_composite"] = (
                trend_df[f"A_MEDIAN_{latest_year}"] - trend_df[f"A_MEDIAN_{COMPOSITE_ANCHOR_YEAR}"]
            ) / trend_df[f"A_MEDIAN_{COMPOSITE_ANCHOR_YEAR}"]

    earliest_year = available_years[0]
    if earliest_year < COMPOSITE_ANCHOR_YEAR and f"TOT_EMP_{earliest_year}" in trend_df.columns:
        trend_df["hist_emp_growth_pre_ai"] = (
            trend_df[f"TOT_EMP_{COMPOSITE_ANCHOR_YEAR}"] - trend_df[f"TOT_EMP_{earliest_year}"]
        ) / trend_df[f"TOT_EMP_{earliest_year}"]
        if f"A_MEDIAN_{earliest_year}" in trend_df.columns and f"A_MEDIAN_{COMPOSITE_ANCHOR_YEAR}" in trend_df.columns:
            trend_df["hist_wage_growth_pre_ai"] = (
                trend_df[f"A_MEDIAN_{COMPOSITE_ANCHOR_YEAR}"] - trend_df[f"A_MEDIAN_{earliest_year}"]
            ) / trend_df[f"A_MEDIAN_{earliest_year}"]

    return trend_df


def _merge_years(year_frames: dict[str, pd.DataFrame], key_column: str, available_years: list[str]) -> pd.DataFrame:
    """Left-join every year onto the 2022 anchor by key_column, suffixing the value columns with the year."""

    def _suffixed(year_suffix: str) -> pd.DataFrame:
        return year_frames[year_suffix].rename(
            columns={
                "OCC_TITLE": f"OCC_TITLE_{year_suffix}",
                "TOT_EMP": f"TOT_EMP_{year_suffix}",
                "A_MEDIAN": f"A_MEDIAN_{year_suffix}",
            }
        )

    merged_df = _suffixed(COMPOSITE_ANCHOR_YEAR)
    for year_suffix in available_years:
        if year_suffix != COMPOSITE_ANCHOR_YEAR:
            merged_df = merged_df.merge(_suffixed(year_suffix), on=key_column, how="left")
    return merged_df


def main():
    year_dataframes: dict[str, pd.DataFrame] = {}
    sector_dataframes: dict[str, pd.DataFrame] = {}
    for year_suffix, zip_path in YEAR_CONFIGS:
        if os.path.exists(zip_path):
            year_frame = load_bls_year(zip_path)
            if year_frame is not None:
                year_dataframes[year_suffix] = select_detailed_rows(year_frame)
                sector_dataframes[year_suffix] = select_major_group_rows(year_frame)
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
    merged_bls_data = attach_growth_columns(_merge_years(year_dataframes, "OCC_CODE", available_years), available_years)

    os.makedirs("data/output", exist_ok=True)
    merged_bls_data.to_csv("data/output/bls_trends.csv", index=False)

    growth_cols = [c for c in merged_bls_data.columns if "growth" in c]
    print(f"Saved data/output/bls_trends.csv ({len(merged_bls_data)} occupations)")
    print(f"Growth columns: {growth_cols}")

    # Sector series from each file's own major-group rows: complete for all 22
    # sectors in every year, because major-group codes survive SOC revisions.
    sector_years = [y for y in available_years if not sector_dataframes[y].empty]
    if COMPOSITE_ANCHOR_YEAR in sector_years:
        sector_trends_df = attach_growth_columns(_merge_years(sector_dataframes, "soc_major", sector_years), sector_years)
        sector_trends_df.to_csv("data/output/bls_sector_trends.csv", index=False)
        print(f"Saved data/output/bls_sector_trends.csv ({len(sector_trends_df)} major groups)")


if __name__ == "__main__":
    main()
