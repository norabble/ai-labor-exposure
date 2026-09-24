"""
dws_detailed_panel.py
─────────────────────
Local build of the detailed Displaced Worker Supplement panel for Phase 2 of the
deep history extension (spec § Displacement, 2b). Tabulates each January
supplement's displaced workers — aged 20+, displaced by a plant or company
closing or move, insufficient work, or an abolished position or shift — onto
Dorn's ~25-group occ1990dd partition, by tenure class, with a household-bootstrap
variance per cell. Then runs gates G3 and G6D and, only if both pass, promotes
the aggregates to seeds/.

The occupation is the *lost job's*, a different variable from current
occupation. It maps to occ1990dd through the harmonized IPUMS variable when one
exists, otherwise through the survey year's coding vintage (see the plan's
route table); a raw code reaching k occ1990dd codes gives each 1/k of its weight.

Never runs in CI. Seeds hold aggregates only.

Inputs:
  • data/raw/ipums/dws/{survey_year}/ (download_ipums_cps.py)
  • seeds/occ1990dd_crosswalks/, seeds/cps_soc_crosswalks/, seeds/occ1990dd_groups.csv
  • seeds/dws_displacement_panel.csv (published Table 5, gate G3)
Outputs:
  • data/output/dws_detailed_panel_rebuilt.csv, data/output/dws_detailed_gates_rebuilt.csv
  • seeds/dws_detailed_panel.csv, seeds/dws_detailed_gates.csv (`promote` only, all gates passed)

Usage:
  python dws_detailed_panel.py build
  python dws_detailed_panel.py promote
"""

import os
import sys

import numpy as np
import pandas as pd

import download_ipums_cps
import ipums_cps_variables as ipums_variables
from cps_detailed_panel import (
    GATE_COLUMNS,
    all_gates_pass,
    bootstrap_group_variance,
    census_code_ten_group_lookup,
    promote_rebuilt,
    spine_lookup,
)
from occ1990dd_reference import (
    UNCLASSIFIED_OCC1990DD,
    load_census_2002_to_2010,
    load_census_2018_to_2010,
    load_census_code_list,
    load_dorn_crosswalk,
    load_occ1990dd_groups,
)

TENURE_CLASSES = ("all_tenures", "long_tenured")
LONG_TENURE_MINIMUM_YEARS = 3.0
PANEL_COLUMNS = ["survey_year", "dorn_group", "tenure_class", "displaced_thousands", "unweighted_count", "sampling_variance"]

SEED_PATH = "seeds/dws_detailed_panel.csv"
GATES_SEED_PATH = "seeds/dws_detailed_gates.csv"
REBUILT_PANEL_PATH = "data/output/dws_detailed_panel_rebuilt.csv"
REBUILT_GATES_PATH = "data/output/dws_detailed_gates_rebuilt.csv"
PUBLISHED_DWS_PANEL_PATH = "seeds/dws_displacement_panel.csv"

G3_TOLERANCE = 0.03
# Table 5 publishes whole thousands, so a small group can be off by half a unit from rounding alone.
G3_ROUNDING_THOUSANDS = 0.5
G6D_MAXIMUM_UNMAPPED_SHARE = 0.01
REQUIRED_GATES = ("G3", "G6D")


def lost_job_raw_vintage(survey_year: int) -> str:
    """The Census occupation-code vintage CPS used in a survey year's resolved sample month.

    CPS switched to 1990 Census occupation codes in January 1992, so a survey year's own
    resolved month (see `ipums_cps_variables.dws_sample_month` — January for most years, February
    for 1994/1996/1998/2000) never crosses that boundary within one survey year.
    """
    if survey_year <= 1991:
        return "1980"
    if survey_year <= 2002:
        return "1990"
    if survey_year <= 2010:
        return "2002"
    if survey_year <= 2018:
        return "2010"
    return "2018"


def lost_job_edges(survey_year: int) -> pd.DataFrame:
    """Raw lost-job code -> occ1990dd with a share; shares below 1 for a code mean part of it is unmapped."""
    vintage = lost_job_raw_vintage(survey_year)
    if vintage in ("1980", "1990", "2010"):
        edges_df = load_dorn_crosswalk(vintage).rename(columns={"source_code": "raw_code"}).assign(share=1.0)
    else:
        census_bridge_df = load_census_2002_to_2010() if vintage == "2002" else load_census_2018_to_2010()
        dorn_2010_df = load_dorn_crosswalk("2010").rename(columns={"source_code": "census_2010"})
        edges_df = (
            census_bridge_df.merge(dorn_2010_df, on="census_2010", how="inner")[[f"census_{vintage}", "occ1990dd"]]
            .drop_duplicates()
            .rename(columns={f"census_{vintage}": "raw_code"})
        )
        edges_df["share"] = 1.0 / edges_df.groupby("raw_code")["occ1990dd"].transform("count")
    return edges_df.loc[edges_df["occ1990dd"] != UNCLASSIFIED_OCC1990DD, ["raw_code", "occ1990dd", "share"]].reset_index(drop=True)


def _harmonized_edges() -> pd.DataFrame:
    spine = spine_lookup()
    return pd.DataFrame({"raw_code": list(spine), "occ1990dd": list(spine.values()), "share": 1.0})


def select_displaced(person_df: pd.DataFrame) -> pd.DataFrame:
    """Supplement respondents aged 20+ displaced for one of BLS's three reasons, wage-and-salary lost jobs only.

    BLS's published Table 5 population excludes all self-employed lost-job workers, incorporated
    and unincorporated alike (`ipums_variables.DWS_SELF_EMPLOYED_CLASS_CODES`); a record must
    positively match one of those codes to be dropped. A record whose lost-job class of worker is
    missing, NIU, refused, or don't-know (`ipums_variables.DWS_MISSING_CLASS_CODES`) is kept rather
    than guessed at — see `missing_lost_job_class_count` for how many such records survive per
    survey.
    """
    weights = person_df[ipums_variables.DWS_WEIGHT_VARIABLE].astype(float)
    self_employed_mask = (
        person_df[ipums_variables.DWS_LOST_JOB_CLASS_VARIABLE].astype(int).isin(ipums_variables.DWS_SELF_EMPLOYED_CLASS_CODES)
    )
    displaced_mask = (
        (weights > 0)
        & (person_df["AGE"] >= ipums_variables.DWS_MINIMUM_AGE)
        & person_df[ipums_variables.DWS_REASON_VARIABLE].isin(ipums_variables.DWS_DISPLACED_REASON_CODES)
        & ~self_employed_mask
    )
    return person_df[displaced_mask].copy()


def missing_lost_job_class_count(displaced_df: pd.DataFrame) -> int:
    """How many already-selected displaced records carry a missing/NIU/refused/don't-know lost-job class.

    `select_displaced` keeps these records rather than assuming they are (or are not)
    self-employed, so this count is reported per survey rather than silently absorbed.
    """
    class_values = displaced_df[ipums_variables.DWS_LOST_JOB_CLASS_VARIABLE].astype(int)
    return int(class_values.isin(ipums_variables.DWS_MISSING_CLASS_CODES).sum())


def is_long_tenured(frame: pd.DataFrame) -> pd.Series:
    """Three or more years at the lost job; not-in-universe codes are never long-tenured."""
    tenure = frame[ipums_variables.DWS_TENURE_VARIABLE].astype(float)
    return (tenure >= LONG_TENURE_MINIMUM_YEARS) & (tenure <= ipums_variables.DWS_TENURE_VALID_MAXIMUM)


def attach_lost_job_occ1990dd(displaced_df: pd.DataFrame, survey_year: int) -> tuple[pd.DataFrame, float]:
    """One row per (record, occ1990dd) with the weight allocated to it, and the unmapped weighted share (G6D)."""
    if ipums_variables.DWS_LOST_JOB_OCC1990_VARIABLE:
        edges_df, code_column = _harmonized_edges(), ipums_variables.DWS_LOST_JOB_OCC1990_VARIABLE
    else:
        edges_df, code_column = lost_job_edges(survey_year), ipums_variables.DWS_LOST_JOB_OCC_VARIABLE
    weight_column = ipums_variables.DWS_WEIGHT_VARIABLE
    coded_df = displaced_df.assign(raw_code=displaced_df[code_column].astype(int))
    mapped_df = coded_df.merge(edges_df, on="raw_code", how="inner")
    mapped_df["allocated_weight"] = mapped_df[weight_column].astype(float) * mapped_df["share"]
    total_weight = coded_df[weight_column].astype(float).sum()
    # A survey with no displaced weight at all (e.g. an empty extract, or a resolved sample month
    # that carries no supplement) must fail G6D rather than report a vacuous 0.0 unmapped share —
    # there is nothing here to have mapped successfully.
    unmapped_share = float(1 - mapped_df["allocated_weight"].sum() / total_weight) if total_weight > 0 else 1.0
    return mapped_df, unmapped_share


def tabulate_survey(mapped_df: pd.DataFrame, survey_year: int, groups_df: pd.DataFrame) -> pd.DataFrame:
    """Displaced workers (thousands) per Dorn group and tenure class, with bootstrap variance."""
    grouped_df = mapped_df.merge(groups_df, on="occ1990dd", how="inner")
    survey_frames = []
    for tenure_class in TENURE_CLASSES:
        class_df = grouped_df if tenure_class == "all_tenures" else grouped_df[is_long_tenured(grouped_df)]
        if class_df.empty:
            continue
        totals = class_df.groupby("dorn_group")["allocated_weight"].sum() / 1000.0
        counts = class_df.groupby("dorn_group").size()
        variance = bootstrap_group_variance(
            class_df["dorn_group"].to_numpy(),
            class_df["allocated_weight"].to_numpy(dtype=float),
            class_df["SERIAL"].to_numpy(),
            scale=1 / 1000.0,
        )
        survey_frames.append(
            pd.DataFrame(
                {
                    "survey_year": survey_year,
                    "dorn_group": totals.index,
                    "tenure_class": tenure_class,
                    "displaced_thousands": totals.to_numpy(),
                    "unweighted_count": counts.reindex(totals.index).to_numpy(),
                    "sampling_variance": variance.reindex(totals.index).to_numpy(),
                }
            )
        )
    return pd.concat(survey_frames, ignore_index=True) if survey_frames else pd.DataFrame(columns=PANEL_COLUMNS)


def ten_group_long_tenured_direct(displaced_df: pd.DataFrame, survey_year: int) -> pd.DataFrame:
    """Long-tenured displaced workers per Phase 1 group through raw codes and the Census list — gate G3's side."""
    vintage = lost_job_raw_vintage(survey_year)
    if vintage not in ("2002", "2010", "2018"):
        return pd.DataFrame(columns=["survey_year", "cps_group", "displaced_thousands"])
    group_lookup = census_code_ten_group_lookup(load_census_code_list(vintage))
    long_df = displaced_df[is_long_tenured(displaced_df)]
    grouped_df = long_df.assign(cps_group=long_df[ipums_variables.DWS_LOST_JOB_OCC_VARIABLE].astype(int).map(group_lookup)).dropna(
        subset=["cps_group"]
    )
    totals = grouped_df.groupby("cps_group")[ipums_variables.DWS_WEIGHT_VARIABLE].sum() / 1000.0
    return pd.DataFrame({"survey_year": survey_year, "cps_group": totals.index, "displaced_thousands": totals.to_numpy()})


def gate_g3(direct_df: pd.DataFrame, published_panel_df: pd.DataFrame) -> pd.DataFrame:
    """G3: long-tenured displacement by the ten groups against published Table 5, within 3% or half a published unit."""
    table_five_df = published_panel_df[
        (published_panel_df["source_table"] == "table_5_occupation") & (published_panel_df["measurement_basis"] == "count_thousands")
    ]
    table_five_df = table_five_df.assign(cps_group=table_five_df["group_name"].astype(str).str.strip().str.lower())
    table_five_df = table_five_df.rename(columns={"displaced_thousands": "published_thousands"})[
        ["survey_year", "cps_group", "published_thousands"]
    ].dropna()
    merged_df = direct_df.merge(table_five_df, on=["survey_year", "cps_group"], how="inner")
    absolute_gap = (merged_df["displaced_thousands"] - merged_df["published_thousands"]).abs()
    allowed_gap = np.maximum(G3_TOLERANCE * merged_df["published_thousands"], G3_ROUNDING_THOUSANDS)
    gate_df = pd.DataFrame(
        {
            "gate": "G3",
            "scope": merged_df["survey_year"].astype(str) + " " + merged_df["cps_group"],
            "observed": absolute_gap / merged_df["published_thousands"],
            "threshold": allowed_gap / merged_df["published_thousands"],
            "gated": True,
            "passed": absolute_gap <= allowed_gap,
        }
    )
    return gate_df[GATE_COLUMNS]


def gate_g6d(unmapped_by_survey: pd.Series) -> pd.DataFrame:
    """G6D (pinned by this plan): lost-job weight reaching no occ1990dd is at most 1% in every survey."""
    unmapped_shares = unmapped_by_survey.to_numpy(dtype=float)
    return pd.DataFrame(
        {
            "gate": "G6D",
            "scope": unmapped_by_survey.index.astype(str),
            "observed": unmapped_shares,
            "threshold": G6D_MAXIMUM_UNMAPPED_SHARE,
            "gated": True,
            "passed": unmapped_shares <= G6D_MAXIMUM_UNMAPPED_SHARE,
        }
    )[GATE_COLUMNS]


def read_survey_persons(survey_year: int, raw_dir: str = download_ipums_cps.RAW_DIR) -> pd.DataFrame | None:
    """A downloaded survey's displaced records, or None if not downloaded."""
    extract_dir = os.path.join(raw_dir, "dws", str(survey_year))
    if not download_ipums_cps.extract_is_downloaded(extract_dir):
        return None
    return pd.concat([select_displaced(chunk_df) for chunk_df in download_ipums_cps.read_extract(extract_dir)], ignore_index=True)


def build_rebuilt_panel(
    survey_years: list[int] | None = None,
    raw_dir: str = download_ipums_cps.RAW_DIR,
    panel_path: str = REBUILT_PANEL_PATH,
    gates_path: str = REBUILT_GATES_PATH,
) -> pd.DataFrame:
    """Tabulate every downloaded survey, run G3 and G6D, and write the rebuilt panel and gate record."""
    if ipums_variables.VERIFICATION_STATUS != "verified":
        raise RuntimeError("ipums_cps_variables is unverified — complete plan Task 2 before tabulating real data")
    groups_df = load_occ1990dd_groups()
    survey_frames, direct_frames, unmapped_by_survey = [], [], {}
    for survey_year in survey_years or list(ipums_variables.DWS_SURVEY_YEARS):
        displaced_df = read_survey_persons(survey_year, raw_dir)
        if displaced_df is None:
            print(f"  {survey_year}: not downloaded; skipped")
            continue
        mapped_df, unmapped_by_survey[survey_year] = attach_lost_job_occ1990dd(displaced_df, survey_year)
        survey_frames.append(tabulate_survey(mapped_df, survey_year, groups_df))
        direct_frames.append(ten_group_long_tenured_direct(displaced_df, survey_year))
        missing_class_count = missing_lost_job_class_count(displaced_df)
        print(
            f"  {survey_year}: {len(displaced_df)} displaced records, unmapped share {unmapped_by_survey[survey_year]:.4f}, "
            f"missing/NIU lost-job class {missing_class_count}"
        )

    if not survey_frames:
        raise RuntimeError(
            f"No survey in {survey_years or list(ipums_variables.DWS_SURVEY_YEARS)} is downloaded to {raw_dir} — "
            "nothing to tabulate. Run download_ipums_cps.py dws first."
        )
    panel_df = pd.concat(survey_frames, ignore_index=True)
    gates_df = pd.concat(
        [
            gate_g3(pd.concat(direct_frames, ignore_index=True), pd.read_csv(PUBLISHED_DWS_PANEL_PATH)),
            gate_g6d(pd.Series(unmapped_by_survey)),
        ],
        ignore_index=True,
    )
    for output_path, output_df in ((panel_path, panel_df), (gates_path, gates_df)):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        output_df.to_csv(output_path, index=False)
    print(f"  Gates: {'ALL PASS' if all_gates_pass(gates_df, REQUIRED_GATES) else 'FAILED'} — {gates_path}")
    return gates_df


def main(arguments: list[str]) -> None:
    """Command-line entry: `build` or `promote`."""
    if arguments == ["build"]:
        build_rebuilt_panel()
    elif arguments == ["promote"]:
        promote_rebuilt({REBUILT_PANEL_PATH: SEED_PATH, REBUILT_GATES_PATH: GATES_SEED_PATH}, REBUILT_GATES_PATH, REQUIRED_GATES)
        print(f"  Promoted to {SEED_PATH}, {GATES_SEED_PATH}")
    else:
        raise SystemExit("usage: python dws_detailed_panel.py build | promote")


if __name__ == "__main__":
    main(sys.argv[1:])
