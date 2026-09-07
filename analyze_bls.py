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

# BLS wage suppression flags, from the field_descriptions sheet shipped in the
# OEWS zips: "*" means an estimate was not released, "#" means the wage is at or
# above a published ceiling. They mean different things and are kept apart.
CENSORED_WAGE_FLAG = "#"
WITHHELD_ESTIMATE_FLAG = "*"

# BLS publishes the "#" ceiling in field_descriptions.xlsx, but only ships that
# sheet through 2018: $145,600 (2005-07), $166,400 (2008-10), $187,200 (2011-15),
# $208,000 (2016-18). The ceiling then moved again without documentation — 2022
# publishes a wage of $226,880 — and censoring stops entirely in 2025. So the
# floor is derived from the data instead of hardcoded; see derive_censoring_floor.

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

    target_columns = ["OCC_CODE", "OCC_TITLE", "TOT_EMP", "A_MEDIAN", "H_MEDIAN"]
    available_targets = [c for c in target_columns if c in bls_dataframe.columns]
    bls_dataframe = bls_dataframe[available_targets].copy()

    # Record what the suppression flags meant before they are coerced away. They are
    # not interchangeable: "#" is a wage censored at a published floor, "*" is an
    # estimate BLS withheld, and both would otherwise become an indistinguishable NaN.
    if "A_MEDIAN" in bls_dataframe.columns:
        annual_wage_text = bls_dataframe["A_MEDIAN"].astype(str).str.strip()
        bls_dataframe["A_MEDIAN_censored"] = annual_wage_text == CENSORED_WAGE_FLAG
        bls_dataframe["A_MEDIAN_withheld"] = annual_wage_text == WITHHELD_ESTIMATE_FLAG

    for col in ["TOT_EMP", "A_MEDIAN", "H_MEDIAN"]:
        if col in bls_dataframe.columns:
            bls_dataframe[col] = pd.to_numeric(
                bls_dataframe[col].astype(str).str.replace(",", "").str.replace("*", ""),
                errors="coerce",
            )

    return bls_dataframe


def derive_censoring_floor(bls_dataframe: pd.DataFrame) -> float | None:
    """
    Lower bound on any wage BLS censored this year, derived from the data.

    Censoring is applied on the value: a wage at or above the year's ceiling is
    replaced with "#", everything below it is published. So every censored wage
    exceeds every published wage, and the highest published wage is a valid floor
    for all of them — without needing to know what ceiling BLS actually used.

    That matters because BLS ships the ceiling in field_descriptions.xlsx only
    through 2018, then moves it twice without documenting it. A derived floor
    tracks those changes on its own; a hardcoded table would have gone stale in
    2019 and silently wrong in 2022.

    Returns None when nothing was censored.
    """
    if "A_MEDIAN_censored" not in bls_dataframe.columns or not bls_dataframe["A_MEDIAN_censored"].any():
        return None
    published_wages = bls_dataframe.loc[~bls_dataframe["A_MEDIAN_censored"], "A_MEDIAN"]
    return None if published_wages.isna().all() else float(published_wages.max())


def report_wage_suppression(year_suffix: str, bls_dataframe: pd.DataFrame) -> None:
    """
    Print how many wage estimates were suppressed, and why.

    Coercing the flags to NaN silently is what hid the fact that every physician
    and surgeon is absent from the wage panel: they are censored, not missing, and
    the censoring is on the variable being analysed.
    """
    if "A_MEDIAN_censored" not in bls_dataframe.columns:
        return

    censored_count = int(bls_dataframe["A_MEDIAN_censored"].sum())
    withheld_count = int(bls_dataframe["A_MEDIAN_withheld"].sum())
    if censored_count == 0 and withheld_count == 0:
        return

    censoring_floor = derive_censoring_floor(bls_dataframe)
    threshold_text = f" (wage > ${censoring_floor:,.0f})" if censoring_floor else ""
    recoverable_count = int((bls_dataframe["A_MEDIAN_withheld"] & bls_dataframe["H_MEDIAN"].notna()).sum())
    print(
        f"  Suppressed annual wages: {censored_count} censored{threshold_text}, "
        f"{withheld_count} withheld ({recoverable_count} with an hourly wage to fall back on)"
    )


def compute_wage_growth(merged_bls_data: pd.DataFrame, prev_year: str, curr_year: str) -> tuple[pd.Series, pd.Series]:
    """
    Median wage growth between two years, annual where possible, hourly otherwise.

    Growth is a ratio, so hourly and annual growth are directly comparable and can
    sit in one column. The fallback matters for the handful of occupations BLS
    publishes hourly-only each year — actors, dancers, musicians and singers, disc
    jockeys, other entertainers. BLS marks them HOURLY and withholds an annual
    figure because they "generally don't work a standard 2,080 hour work year", so
    their annual wage is not missing data, it is a number BLS declines to invent.
    Reading only A_MEDIAN dropped them from every wage analysis while a perfectly
    good hourly wage sat in the adjacent column.

    Do not reconstruct an annual wage as hourly x 2080 instead: that fabricates the
    exact quantity BLS withheld, for the occupations where it is least meaningful.

    Returns (growth, source) where source is "annual", "hourly", or NA.
    """

    def _growth(prefix: str) -> pd.Series:
        earlier_column, later_column = f"{prefix}_{prev_year}", f"{prefix}_{curr_year}"
        if earlier_column not in merged_bls_data.columns or later_column not in merged_bls_data.columns:
            return pd.Series(float("nan"), index=merged_bls_data.index)
        return (merged_bls_data[later_column] - merged_bls_data[earlier_column]) / merged_bls_data[earlier_column]

    annual_growth = _growth("A_MEDIAN")
    hourly_growth = _growth("H_MEDIAN")

    combined_growth = annual_growth.where(annual_growth.notna(), hourly_growth)
    growth_source = pd.Series(pd.NA, index=merged_bls_data.index, dtype="object")
    growth_source[annual_growth.notna()] = "annual"
    growth_source[annual_growth.isna() & hourly_growth.notna()] = "hourly"

    return combined_growth, growth_source


def main():
    year_dataframes: dict[str, pd.DataFrame] = {}
    censoring_rows: list[dict] = []
    for year_suffix, zip_path in YEAR_CONFIGS:
        if os.path.exists(zip_path):
            year_df = load_bls_data(zip_path)
            if year_df is not None:
                report_wage_suppression(year_suffix, year_df)
                if "A_MEDIAN_censored" in year_df.columns:
                    censoring_rows.append(
                        {
                            "year": f"20{year_suffix}",
                            "year_suffix": year_suffix,
                            # Derived from the complete single-year file, before the
                            # 2022-anchored left join drops non-surviving SOC codes.
                            "censoring_floor": derive_censoring_floor(year_df),
                            "n_censored": int(year_df["A_MEDIAN_censored"].sum()),
                            "n_withheld": int(year_df["A_MEDIAN_withheld"].sum()),
                            "n_detailed": len(year_df),
                        }
                    )
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
            "H_MEDIAN": f"H_MEDIAN_{COMPOSITE_ANCHOR_YEAR}",
            "A_MEDIAN_censored": f"A_MEDIAN_censored_{COMPOSITE_ANCHOR_YEAR}",
            "A_MEDIAN_withheld": f"A_MEDIAN_withheld_{COMPOSITE_ANCHOR_YEAR}",
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
                "H_MEDIAN": f"H_MEDIAN_{year_suffix}",
                "A_MEDIAN_censored": f"A_MEDIAN_censored_{year_suffix}",
                "A_MEDIAN_withheld": f"A_MEDIAN_withheld_{year_suffix}",
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
            wage_growth, wage_growth_source = compute_wage_growth(merged_bls_data, prev_year, curr_year)
            merged_bls_data[f"{prefix}wage_growth_{prev_year}_{curr_year}"] = wage_growth
            hourly_fallback_count = int((wage_growth_source == "hourly").sum())
            if hourly_fallback_count:
                print(f"  {prev_year}->{curr_year}: {hourly_fallback_count} occupation(s) using the hourly wage series")

    # Composite: always 2022 → latest year
    latest_year = [y for y in available_years if y > COMPOSITE_ANCHOR_YEAR]
    if latest_year:
        latest_year = latest_year[-1]
        merged_bls_data["emp_growth_composite"] = (
            merged_bls_data[f"TOT_EMP_{latest_year}"] - merged_bls_data[f"TOT_EMP_{COMPOSITE_ANCHOR_YEAR}"]
        ) / merged_bls_data[f"TOT_EMP_{COMPOSITE_ANCHOR_YEAR}"]
        if f"A_MEDIAN_{latest_year}" in merged_bls_data.columns:
            composite_wage_growth, composite_wage_source = compute_wage_growth(merged_bls_data, COMPOSITE_ANCHOR_YEAR, latest_year)
            merged_bls_data["wage_growth_composite"] = composite_wage_growth
            merged_bls_data["wage_source_composite"] = composite_wage_source

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

    if censoring_rows:
        pd.DataFrame(censoring_rows).to_csv("data/output/wage_censoring.csv", index=False)
        print("Saved data/output/wage_censoring.csv")

    growth_cols = [c for c in merged_bls_data.columns if "growth" in c]
    print(f"Saved data/output/bls_trends.csv ({len(merged_bls_data)} occupations)")
    print(f"Growth columns: {growth_cols}")


if __name__ == "__main__":
    main()
