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
  python verify_ipums_cps.py basic-legacy-probe
  python verify_ipums_cps.py dws-probe
"""

import os
import sys

import pandas as pd

import download_ipums_cps
import ipums_cps_variables as ipums_variables

PROBE_DIR = "data/raw/ipums/probe"
# Includes 1983 and 1994 pre-1998 (COMPWT unavailable — Ruling 11) alongside 1998 itself, so the
# probe's own COMPWT/CLASSWKR/OCC1990 coverage check spans both sides of that availability floor.
# This one combined extract cannot fully substitute for per-year eligibility checking, though:
# `run_basic_probe` requests ipums_variables.BASIC_MONTHLY_VARIABLES (including COMPWT) for every
# sample here in a single extract, so it would not by itself reveal a real per-year rejection —
# `download_ipums_cps.fetch_basic_monthly_year`'s per-year `variables_for_year` filtering is what
# actually protects the real build; a genuinely single-vintage probe extract (one pre-1998 year
# alone, requesting only `ipums_variables.variables_for_year(year)`) is the direct confirmation
# Task 2 Step 6 still owes.
BASIC_PROBE_MONTHS = [(1983, 1), (1988, 1), (1989, 1), (1994, 1), (1998, 1), (2003, 1), (2011, 1), (2020, 1)]
DWS_PROBE_YEARS = (1984, 1994, 2002, 2004, 2024, 2026)
OCC1990_MINIMUM_VALID_SHARE = 0.99
CPSID_MINIMUM_LINKED_SHARE = 0.99
TOTAL_EMPLOYMENT_SERIES_ID = "LNU02000000"
# Pre-1998, so COMPWT is outside its VARIABLE_FIRST_YEAR floor (Ruling 11) — the direct,
# extract-level confirmation that requesting only `variables_for_year(year)` for a legacy year is
# accepted by IPUMS and simply omits COMPWT, rather than rejecting the whole extract or returning
# a bogus column. Distinct from every BASIC_PROBE_MONTHS year so it is independent evidence.
LEGACY_PROBE_YEAR = 1985


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
        months = [
            month
            for month in range(1, 13)
            if download_ipums_cps.basic_monthly_sample_id(year, month, published_samples) in published_samples
        ]
        if months:
            present_years.append(year)
        if months and len(months) < 12:
            print(f"  {year}: {len(months)} months published ({months[0]}-{months[-1]})")
        elif not months:
            print(f"  {year}: NO basic-monthly samples under pattern {ipums_variables.BASIC_MONTHLY_SAMPLE_PATTERN}")
    print(f"  Years with samples: {present_years[0] if present_years else None}-{present_years[-1] if present_years else None}")
    dws_present = [
        year for year in ipums_variables.DWS_SURVEY_YEARS if download_ipums_cps.dws_sample_id(year, published_samples) in published_samples
    ]
    # Not every survey year's supplement rides January's sample (1994, 1996, 1998 and 2000 carry
    # it in February — ipums_variables.dws_sample_month), so this reports the resolved sample
    # actually checked for each year rather than assuming January.
    print(f"  DWS survey-year samples present (per-year resolved month): {dws_present}")


def run_basic_probe() -> None:
    """Submit one small extract across the coding vintages and print everything Task 2 must confirm."""
    client = download_ipums_cps.make_client()
    published_samples = download_ipums_cps.available_sample_ids(client)
    latest_january = max(
        year for year in range(2020, 2027) if download_ipums_cps.basic_monthly_sample_id(year, 1, published_samples) in published_samples
    )
    probe_months = BASIC_PROBE_MONTHS + [(latest_january, 1)]
    samples = [download_ipums_cps.basic_monthly_sample_id(year, month, published_samples) for year, month in probe_months]
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


def run_legacy_variable_probe() -> None:
    """Submit one pre-1998 basic-monthly month requesting only that year's eligible variables.

    Confirms `ipums_variables.variables_for_year` is safe to hand IPUMS directly: the extract
    must be accepted (not rejected for a variable outside its availability range) and the
    resulting columns must simply omit COMPWT rather than returning it as a bogus/empty column.
    """
    client = download_ipums_cps.make_client()
    published_samples = download_ipums_cps.available_sample_ids(client)
    sample_id = download_ipums_cps.basic_monthly_sample_id(LEGACY_PROBE_YEAR, 1, published_samples)
    requested_variables = ipums_variables.variables_for_year(LEGACY_PROBE_YEAR)
    probe_dir = os.path.join(PROBE_DIR, "basic_legacy")
    if not download_ipums_cps.extract_is_downloaded(probe_dir):
        download_ipums_cps._submit_and_download(
            client, [sample_id], requested_variables, f"ai-exposure phase 2 legacy-variable probe {LEGACY_PROBE_YEAR}", probe_dir
        )
    person_df = pd.concat(download_ipums_cps.read_extract(probe_dir), ignore_index=True)
    print(f"  Sample: {sample_id}")
    print(f"  Requested variables ({len(requested_variables)}): {requested_variables}")
    print(f"  Columns actually returned ({len(person_df.columns)}): {sorted(person_df.columns)}")
    print(f"  COMPWT requested: {'COMPWT' in requested_variables}")
    print(f"  COMPWT present in returned columns: {'COMPWT' in person_df.columns}")
    print(f"  Row count: {len(person_df)}")


def run_dws_probe() -> None:
    """Submit ONE single-sample extract per DWS probe survey year and print each year's own coverage.

    Deliberately never combines survey years into one extract: a wrong resolved sample month for
    one year (an empty supplement) would otherwise hide behind another year's real data in a
    shared extract. Each year's own DWREAS/DWYEARS codebook is printed too, since a supplement's
    category codes could in principle differ by vintage even though IPUMS harmonizes most
    variables across years.
    """
    client = download_ipums_cps.make_client()
    published_samples = download_ipums_cps.available_sample_ids(client)
    weight_column = ipums_variables.DWS_WEIGHT_VARIABLE
    occ1990_column = ipums_variables.DWS_LOST_JOB_OCC1990_VARIABLE
    reason_codes_by_year: dict[int, dict[str, int]] = {}
    tenure_codes_by_year: dict[int, dict[str, int]] = {}

    for year in DWS_PROBE_YEARS:
        resolved_month = ipums_variables.dws_sample_month(year)
        sample_id = download_ipums_cps.dws_sample_id(year, published_samples)
        if sample_id not in published_samples:
            print(f"\n  {year}: resolved sample {sample_id} (month {resolved_month}) not published — skipped")
            continue
        year_probe_dir = os.path.join(PROBE_DIR, "dws", str(year))
        if not download_ipums_cps.extract_is_downloaded(year_probe_dir):
            downloaded_dir = download_ipums_cps.submit_and_download_or_none(
                client, [sample_id], ipums_variables.DWS_VARIABLES, f"ai-exposure phase 2 DWS probe {year}", year_probe_dir
            )
            if downloaded_dir is None:
                print(f"\n  {year}: sample {sample_id} (resolved month {resolved_month}) does not carry the DWS supplement — skipped")
                continue
        year_df = pd.concat(download_ipums_cps.read_extract(year_probe_dir), ignore_index=True)
        in_supplement = year_df[year_df[weight_column].astype(float) > 0]
        print(
            f"\n  {year} (sample {sample_id}, resolved month {resolved_month}): "
            f"{len(in_supplement)} of {len(year_df)} records with positive {weight_column}"
        )
        for variable_name in ipums_variables.DWS_VARIABLES:
            if variable_name in year_df.columns:
                variable_values = in_supplement[variable_name]
                value_range = f"{variable_values.min()}-{variable_values.max()}" if len(variable_values) else "n/a"
                print(f"    {variable_name}: {variable_values.nunique()} distinct values, range {value_range}")
        if occ1990_column and occ1990_column in year_df.columns and len(in_supplement):
            occ1990_values = in_supplement[occ1990_column].astype(float)
            nonzero_share = float((occ1990_values > 0).mean())
            print(f"    {occ1990_column} nonzero share among supplement records: {nonzero_share:.3f}")

        year_codebook = download_ipums_cps.read_codebook(year_probe_dir)
        year_reason_codes = year_codebook.get_variable_info(ipums_variables.DWS_REASON_VARIABLE).codes
        year_tenure_codes = year_codebook.get_variable_info(ipums_variables.DWS_TENURE_VARIABLE).codes
        reason_codes_by_year[year] = year_reason_codes
        tenure_codes_by_year[year] = year_tenure_codes
        print(f"    {ipums_variables.DWS_REASON_VARIABLE} codes ({year}): {year_reason_codes}")
        print(
            f"    Displaced reason codes by label ({year}): "
            f"{displaced_reason_codes(year_reason_codes, ipums_variables.DWS_DISPLACED_REASON_LABEL_FRAGMENTS)}"
        )
        print(f"    {ipums_variables.DWS_TENURE_VARIABLE} codes ({year}): {year_tenure_codes}")

    distinct_reason_codebooks = {tuple(sorted(codes.items())) for codes in reason_codes_by_year.values()}
    distinct_tenure_codebooks = {tuple(sorted(codes.items())) for codes in tenure_codes_by_year.values()}
    print(f"\n  Distinct {ipums_variables.DWS_REASON_VARIABLE} codebooks across probe years: {len(distinct_reason_codebooks)}")
    print(f"  Distinct {ipums_variables.DWS_TENURE_VARIABLE} codebooks across probe years: {len(distinct_tenure_codebooks)}")


def main(arguments: list[str]) -> None:
    """Command-line entry: `samples`, `basic-probe` or `dws-probe`."""
    commands = {
        "samples": run_samples,
        "basic-probe": run_basic_probe,
        "basic-legacy-probe": run_legacy_variable_probe,
        "dws-probe": run_dws_probe,
    }
    if not arguments or arguments[0] not in commands:
        raise SystemExit(f"usage: python verify_ipums_cps.py {{{'|'.join(commands)}}}")
    commands[arguments[0]]()


if __name__ == "__main__":
    main(sys.argv[1:])
