"""
verify_ipums_cps.py
───────────────────
Plan Task 2 of the deep history extension, Phase 2: confirm against IPUMS itself
every IPUMS fact the detailed panels depend on, before any real data is
tabulated — basic-monthly sample coverage, variable names and code values,
OCC1990 coverage after 2019, composite weights, household linkage across months,
and the Displaced Worker Supplement's variables.

Local and manual only. Needs IPUMS_API_KEY in .env.
Results are transcribed by hand into
docs/superpowers/plans/2026-09-23-ipums-verification.md and into
ipums_cps_variables.py.

Inputs:
  • IPUMS CPS extract API
  • BLS series LNU02000000 via historical_displacement.fetch_bls_series (cached)
Outputs:
  • data/raw/ipums/probe/basic/ and data/raw/ipums/probe/dws/  (gitignored probe extracts)
  • a printed report

Usage:
  python verify_ipums_cps.py samples
  python verify_ipums_cps.py basic-probe
  python verify_ipums_cps.py dws-probe
"""

import os
import sys

import pandas as pd

import download_ipums_cps
import ipums_cps_variables as ipums_variables

PROBE_DIR = "data/raw/ipums/probe"
BASIC_PROBE_MONTHS = [(1983, 1), (1988, 1), (1989, 1), (1994, 1), (1998, 1), (2003, 1), (2011, 1), (2020, 1)]
DWS_PROBE_YEARS = (1984, 1994, 2002, 2004, 2020)
OCC1990_MINIMUM_VALID_SHARE = 0.99
CPSID_MINIMUM_LINKED_SHARE = 0.99
TOTAL_EMPLOYMENT_SERIES_ID = "LNU02000000"


def summarise_basic_probe(person_df: pd.DataFrame) -> pd.DataFrame:
    """One row per probe month: employment, OCC1990 coverage, composite-weight and linkage coverage."""
    summary_rows = []
    for (year, month), month_df in person_df.groupby(["YEAR", "MONTH"]):
        employed_mask = month_df["EMPSTAT"].isin(ipums_variables.EMPLOYED_EMPSTAT_CODES) & (month_df["AGE"] >= ipums_variables.MINIMUM_AGE)
        employed_df = month_df[employed_mask]
        employed_weight = employed_df["WTFINL"].astype(float)
        valid_occupation = employed_df["OCC1990"] != ipums_variables.OCC1990_NOT_IN_UNIVERSE
        summary_rows.append(
            {
                "year": int(year),
                "month": int(month),
                "employed_thousands": float(employed_weight.sum()) / 1000.0,
                "occ1990_valid_share": float(employed_weight[valid_occupation].sum() / employed_weight.sum()),
                "compwt_positive_share": float((employed_df["COMPWT"].astype(float) > 0).mean()),
                "cpsid_linked_share": float((month_df["CPSID"].astype(float) > 0).mean()),
                "classwkr_codes": ",".join(str(int(code)) for code in sorted(employed_df["CLASSWKR"].unique())),
            }
        )
    return pd.DataFrame(summary_rows)


def household_cluster_decision(summary_df: pd.DataFrame) -> str:
    """'CPSID' only if households link across months in every probe month; else one unit for the whole span."""
    if (summary_df["cpsid_linked_share"] >= CPSID_MINIMUM_LINKED_SHARE).all():
        return "CPSID"
    return "household_month"


def displaced_reason_codes(reason_labels: dict[str, int], label_fragments: tuple[str, ...]) -> tuple[int, ...]:
    """Codes whose label names one of BLS's three displacement reasons."""
    return tuple(
        sorted(int(code) for label, code in reason_labels.items() if any(fragment in label.lower() for fragment in label_fragments))
    )


def _published_monthly_employment(year: int, month: int) -> float | None:
    from historical_displacement import fetch_bls_series

    series_df = fetch_bls_series(TOTAL_EMPLOYMENT_SERIES_ID, year, year)
    if series_df is None:
        return None
    month_rows = series_df[series_df["period"] == f"M{month:02d}"]
    return float(month_rows["value"].iloc[0]) if not month_rows.empty else None


def run_samples() -> None:
    """Print which basic-monthly months IPUMS publishes, 1983 to the present."""
    published_samples = download_ipums_cps.available_sample_ids(download_ipums_cps.make_client())
    present_years = []
    for year in range(ipums_variables.BASIC_MONTHLY_FIRST_YEAR, 2027):
        months = [month for month in range(1, 13) if download_ipums_cps.basic_monthly_sample_id(year, month) in published_samples]
        if months:
            present_years.append(year)
        if months and len(months) < 12:
            print(f"  {year}: {len(months)} months published ({months[0]}-{months[-1]})")
        elif not months:
            print(f"  {year}: NO basic-monthly samples under pattern {ipums_variables.BASIC_MONTHLY_SAMPLE_PATTERN}")
    print(f"  Years with samples: {present_years[0] if present_years else None}-{present_years[-1] if present_years else None}")
    dws_present = [year for year in ipums_variables.DWS_SURVEY_YEARS if download_ipums_cps.dws_sample_id(year) in published_samples]
    print(f"  DWS survey-year January samples present: {dws_present}")


def run_basic_probe() -> None:
    """Submit one small extract across the coding vintages and print everything Task 2 must confirm."""
    client = download_ipums_cps.make_client()
    published_samples = download_ipums_cps.available_sample_ids(client)
    latest_january = max(year for year in range(2020, 2027) if download_ipums_cps.basic_monthly_sample_id(year, 1) in published_samples)
    probe_months = BASIC_PROBE_MONTHS + [(latest_january, 1)]
    samples = [download_ipums_cps.basic_monthly_sample_id(year, month) for year, month in probe_months]
    probe_dir = os.path.join(PROBE_DIR, "basic")
    if not download_ipums_cps.extract_is_downloaded(probe_dir):
        download_ipums_cps._submit_and_download(
            client, samples, ipums_variables.BASIC_MONTHLY_VARIABLES, "ai-exposure phase 2 verification probe", probe_dir
        )

    person_df = pd.concat(download_ipums_cps.read_extract(probe_dir), ignore_index=True)
    summary_df = summarise_basic_probe(person_df)
    summary_df["published_thousands"] = [
        _published_monthly_employment(year, month) for year, month in zip(summary_df["year"], summary_df["month"])
    ]
    summary_df["relative_difference"] = summary_df["employed_thousands"] / summary_df["published_thousands"] - 1
    print(summary_df.to_string(index=False))
    print(f"\n  Household cluster decision: {household_cluster_decision(summary_df)}")

    codebook = download_ipums_cps.read_codebook(probe_dir)
    for variable_name in ("EMPSTAT", "CLASSWKR"):
        print(f"\n  {variable_name} codes: {codebook.get_variable_info(variable_name).codes}")

    data_file_bytes = sum(os.path.getsize(os.path.join(probe_dir, name)) for name in os.listdir(probe_dir) if name.endswith(".csv.gz"))
    estimated_total_gigabytes = data_file_bytes / len(probe_months) * 12 * 44 / 1e9
    print(f"\n  Probe data file: {data_file_bytes / 1e6:.1f} MB for {len(probe_months)} months")
    print(f"  Full 1983-2026 basic monthly, extrapolated: ≈ {estimated_total_gigabytes:.1f} GB")


def run_dws_probe() -> None:
    """Submit the DWS variables for the probe survey years and print their availability and codes."""
    client = download_ipums_cps.make_client()
    published_samples = download_ipums_cps.available_sample_ids(client)
    samples = [
        download_ipums_cps.dws_sample_id(year) for year in DWS_PROBE_YEARS if download_ipums_cps.dws_sample_id(year) in published_samples
    ]
    probe_dir = os.path.join(PROBE_DIR, "dws")
    if not download_ipums_cps.extract_is_downloaded(probe_dir):
        download_ipums_cps._submit_and_download(client, samples, ipums_variables.DWS_VARIABLES, "ai-exposure phase 2 DWS probe", probe_dir)

    person_df = pd.concat(download_ipums_cps.read_extract(probe_dir), ignore_index=True)
    weight_column = ipums_variables.DWS_WEIGHT_VARIABLE
    for year, year_df in person_df.groupby("YEAR"):
        in_supplement = year_df[year_df[weight_column].astype(float) > 0]
        print(f"\n  {year}: {len(in_supplement)} records with positive {weight_column}")
        for variable_name in ipums_variables.DWS_VARIABLES:
            if variable_name in year_df.columns:
                variable_values = in_supplement[variable_name]
                value_range = f"{variable_values.min()}-{variable_values.max()}"
                print(f"    {variable_name}: {variable_values.nunique()} distinct values, range {value_range}")

    codebook = download_ipums_cps.read_codebook(probe_dir)
    reason_labels = codebook.get_variable_info(ipums_variables.DWS_REASON_VARIABLE).codes
    print(f"\n  {ipums_variables.DWS_REASON_VARIABLE} codes: {reason_labels}")
    print(
        f"  Displaced reason codes by label: {displaced_reason_codes(reason_labels, ipums_variables.DWS_DISPLACED_REASON_LABEL_FRAGMENTS)}"
    )
    print(f"  {ipums_variables.DWS_TENURE_VARIABLE} codes: {codebook.get_variable_info(ipums_variables.DWS_TENURE_VARIABLE).codes}")


def main(arguments: list[str]) -> None:
    """Command-line entry: `samples`, `basic-probe` or `dws-probe`."""
    commands = {"samples": run_samples, "basic-probe": run_basic_probe, "dws-probe": run_dws_probe}
    if not arguments or arguments[0] not in commands:
        raise SystemExit(f"usage: python verify_ipums_cps.py {{{'|'.join(commands)}}}")
    commands[arguments[0]]()


if __name__ == "__main__":
    main(sys.argv[1:])
