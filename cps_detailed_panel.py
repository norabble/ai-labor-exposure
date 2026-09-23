"""
cps_detailed_panel.py
─────────────────────
Local build of the detailed CPS employment panel for Phase 2 of the deep history
extension. Tabulates IPUMS basic-monthly microdata, 1983 onward, into annual
employment on the time-consistent occ1990dd codes in two universes, attaches a
household-bootstrap sampling variance to every cell, runs the build-time gates
(G1, G2, G5, G6), and — only when every gate passes — promotes the aggregates
to seeds/.

Never runs in CI. The pipeline reads the committed seeds through
cps_detailed_measurement.py and cps_detailed_validation.py. Seeds hold
aggregates only; IPUMS terms prohibit redistributing microdata.

Universes (spec § Universe and weights): `all_employed` feeds every headline
test; `wage_salary` excludes both self-employed classes and unpaid family
workers and is used only for the OEWS overlap comparison. WTFINL is the
tabulation weight in every year; the gates that compare against published BLS
figures use COMPWT from 1998, because that is what BLS publishes from.

Inputs:
  • data/raw/ipums/basic/{year}/                 (download_ipums_cps.py)
  • seeds/occ1990dd_crosswalks/occ1990_occ1990dd.csv (the spine), seeds/cps_soc_crosswalks/
  • seeds/cps_occupation_panel.csv               (Phase 1 published series, gate G1)
  • BLS series LNU02000000                       (gate G2, cached)
Outputs:
  • data/raw/ipums/tabulated/{year}_*.csv        per-year cache (gitignored)
  • data/output/cps_detailed_occupation_panel_rebuilt.csv
  • data/output/cps_detailed_occ_crosstab_rebuilt.csv
  • data/output/cps_detailed_gates_rebuilt.csv
  • seeds/cps_detailed_occupation_panel.csv, seeds/cps_detailed_occ_crosstab.csv,
    seeds/cps_detailed_gates.csv                 (`promote` only, and only if every gate passed)

Usage:
  python cps_detailed_panel.py build 1983 2026
  python cps_detailed_panel.py promote
"""

import os
import shutil
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import sparse

import download_ipums_cps
import ipums_cps_variables as ipums_variables
from composition_displacement_validation import soc_major_to_dws_group
from occ1990dd_reference import (
    load_census_code_list,
    load_dorn_crosswalk,
    load_occ1990dd_groups,
    soc_reference_prefix,
    uncovered_codes,
)

UNIVERSES = ("all_employed", "wage_salary")
TABULATION_COLUMNS = ["year", "occ1990dd", "universe", "employed_thousands", "person_months", "distinct_households", "months_observed"]
PANEL_COLUMNS = TABULATION_COLUMNS + ["sampling_variance"]

# block -> (first year, last year, Census code-list vintage CPS used in those years)
CODING_BLOCKS: dict[str, tuple[int, int, str]] = {
    "2003_2010": (2003, 2010, "2002"),
    "2011_2019": (2011, 2019, "2010"),
    "2020_2026": (2020, 2026, "2018"),
}


def coding_block_for_year(year: int) -> str | None:
    """The coding block a year's raw OCC codes belong to, or None before 2003."""
    for block_name, (first_year, last_year, _) in CODING_BLOCKS.items():
        if first_year <= year <= last_year:
            return block_name
    return None


def select_civilian_employed(person_df: pd.DataFrame) -> pd.DataFrame:
    """Civilian employed persons aged 16 and over."""
    employed_mask = person_df["EMPSTAT"].isin(ipums_variables.EMPLOYED_EMPSTAT_CODES) & (person_df["AGE"] >= ipums_variables.MINIMUM_AGE)
    return person_df[employed_mask].copy()


def attach_occ1990dd(person_df: pd.DataFrame, spine: dict[int, int], weight_column: str = "WTFINL") -> tuple[pd.DataFrame, float]:
    """Map OCC1990 to occ1990dd, dropping unmapped records and reporting their weighted share (gate G6)."""
    mapped_codes = person_df["OCC1990"].astype(int).map(spine)
    weights = person_df[weight_column].astype(float)
    total_weight = weights.sum()
    unmapped_share = float(weights[mapped_codes.isna()].sum() / total_weight) if total_weight > 0 else 0.0
    spine_df = person_df.assign(occ1990dd=mapped_codes).dropna(subset=["occ1990dd"])
    return spine_df.astype({"occ1990dd": int}), unmapped_share


def universe_mask(person_df: pd.DataFrame, universe: str) -> pd.Series:
    """Which records belong to a universe."""
    if universe == "all_employed":
        return pd.Series(True, index=person_df.index)
    if universe == "wage_salary":
        return person_df["CLASSWKR"].isin(ipums_variables.WAGE_SALARY_CLASSWKR_CODES)
    raise ValueError(f"Unknown universe {universe!r}")


def household_cluster_ids(person_df: pd.DataFrame) -> pd.Series:
    """The bootstrap cluster of each record: a linked household, or a household-month, per Task 2's decision."""
    if ipums_variables.HOUSEHOLD_CLUSTER == "CPSID":
        return person_df["CPSID"].astype("int64").astype(str)
    return person_df["YEAR"].astype(str) + "_" + person_df["MONTH"].astype(str) + "_" + person_df["SERIAL"].astype(str)


def tabulate_year(spine_df: pd.DataFrame, year: int, weight_column: str = "WTFINL") -> pd.DataFrame:
    """Annual employment per occ1990dd code and universe: the mean of the year's monthly weighted totals."""
    months_observed = int(spine_df["MONTH"].nunique())
    households_link = ipums_variables.HOUSEHOLD_CLUSTER == "CPSID"
    clustered_df = spine_df.assign(cluster_id=household_cluster_ids(spine_df))

    universe_frames = []
    for universe in UNIVERSES:
        universe_df = clustered_df[universe_mask(clustered_df, universe)]
        summary_df = (
            universe_df.groupby("occ1990dd")
            .agg(
                weighted_person_months=(weight_column, "sum"),
                person_months=(weight_column, "size"),
                distinct_households=("cluster_id", "nunique"),
            )
            .reset_index()
        )
        summary_df["employed_thousands"] = summary_df["weighted_person_months"] / months_observed / 1000.0
        summary_df["distinct_households"] = summary_df["distinct_households"].astype(float) if households_link else np.nan
        summary_df = summary_df.assign(year=year, universe=universe, months_observed=months_observed)
        universe_frames.append(summary_df[TABULATION_COLUMNS])
    return pd.concat(universe_frames, ignore_index=True)


def tabulate_crosstab(spine_df: pd.DataFrame, year: int, weight_column: str = "WTFINL") -> pd.DataFrame:
    """Employment by occ1990dd x raw vintage OCC code, the input the pipeline's bridge check (G4) needs."""
    crosstab_columns = ["year", "coding_block", "occ1990dd", "census_code", "employed_thousands"]
    coding_block = coding_block_for_year(year)
    if coding_block is None:
        return pd.DataFrame(columns=crosstab_columns)
    months_observed = spine_df["MONTH"].nunique()
    crosstab_df = (
        spine_df.groupby(["occ1990dd", "OCC"])[weight_column].sum().div(months_observed * 1000.0).reset_index(name="employed_thousands")
    )
    crosstab_df = crosstab_df.rename(columns={"OCC": "census_code"}).astype({"census_code": int})
    return crosstab_df.assign(year=year, coding_block=coding_block)[crosstab_columns]


def collapse_crosstab(yearly_crosstab_df: pd.DataFrame) -> pd.DataFrame:
    """Sum each block's years. Only within-unit proportions matter, so the scale is immaterial."""
    return (
        yearly_crosstab_df.groupby(["coding_block", "occ1990dd", "census_code"], as_index=False)["employed_thousands"]
        .sum()
        .sort_values(["coding_block", "occ1990dd", "census_code"])
        .reset_index(drop=True)
    )


def census_code_ten_group_lookup(code_list_df: pd.DataFrame) -> dict[int, str]:
    """Census code -> Phase 1 CPS group, through the SOC major of its reference. Gate G1 bypasses the bridge with this."""
    group_by_major = soc_major_to_dws_group()
    lookup: dict[int, str] = {}
    for census_code, soc_reference in zip(code_list_df["census_code"], code_list_df["soc_reference"]):
        prefix = soc_reference_prefix(soc_reference)
        if prefix is not None and prefix[:2] in group_by_major:
            lookup[int(census_code)] = group_by_major[prefix[:2]]
    return lookup


def tabulate_ten_groups_direct(employed_df: pd.DataFrame, year: int, ten_group_lookup: dict[int, str], weight_column: str) -> pd.DataFrame:
    """Annual employment per Phase 1 CPS group, mapped from raw OCC codes without the bridge."""
    months_observed = int(employed_df["MONTH"].nunique())
    grouped_df = employed_df.assign(cps_group=employed_df["OCC"].astype(int).map(ten_group_lookup)).dropna(subset=["cps_group"])
    group_totals = grouped_df.groupby("cps_group")[weight_column].sum() / months_observed / 1000.0
    return pd.DataFrame(
        {"year": year, "cps_group": group_totals.index, "employed_thousands": group_totals.to_numpy(), "months_observed": months_observed}
    )


def tabulate_total(employed_df: pd.DataFrame, year: int, weight_column: str) -> dict:
    """Economy-wide civilian employment, annual mean in thousands (gate G2)."""
    months_observed = int(employed_df["MONTH"].nunique())
    total_thousands = float(employed_df[weight_column].astype(float).sum()) / months_observed / 1000.0
    return {"year": year, "total_thousands": total_thousands, "months_observed": months_observed}


BOOTSTRAP_REPLICATES = 200
BOOTSTRAP_BLOCK_SIZE = 50
BOOTSTRAP_SEED = 20260923


def bootstrap_group_variance(
    group_codes: np.ndarray,
    values: np.ndarray,
    cluster_ids: np.ndarray,
    scale: float,
    replicates: int = BOOTSTRAP_REPLICATES,
    seed: int = BOOTSTRAP_SEED,
) -> pd.Series:
    """Variance of each group's scaled total under a Poisson(1) household-cluster bootstrap.

    Every cluster draws one weight per replicate and all of its records share it,
    so records from one household move together. Replicates are drawn in blocks so
    a year's ~100k households never need a full clusters x replicates matrix at once.
    """
    cluster_codes, cluster_index = np.unique(np.asarray(cluster_ids), return_inverse=True)
    group_labels, group_index = np.unique(np.asarray(group_codes), return_inverse=True)
    group_by_cluster = sparse.csr_matrix(
        (np.asarray(values, dtype=float), (group_index, cluster_index)), shape=(len(group_labels), len(cluster_codes))
    )
    random_generator = np.random.default_rng(seed)
    replicate_blocks = []
    remaining_replicates = replicates
    while remaining_replicates > 0:
        block_size = min(BOOTSTRAP_BLOCK_SIZE, remaining_replicates)
        cluster_weights = random_generator.poisson(1.0, size=(len(cluster_codes), block_size)).astype(float)
        replicate_blocks.append(np.asarray(group_by_cluster @ cluster_weights))
        remaining_replicates -= block_size
    replicate_totals = np.hstack(replicate_blocks) * scale
    return pd.Series(replicate_totals.var(axis=1, ddof=1), index=group_labels)


def cluster_bootstrap_variance(
    spine_df: pd.DataFrame,
    weight_column: str = "WTFINL",
    replicates: int = BOOTSTRAP_REPLICATES,
    seed: int = BOOTSTRAP_SEED,
) -> pd.DataFrame:
    """Sampling variance of every (occ1990dd, universe) annual mean, in thousands squared.

    Adjacent years are treated as independent downstream, which overstates growth
    noise because half the sample carries over — conservative, and documented.
    """
    months_observed = spine_df["MONTH"].nunique()
    scale = 1.0 / (months_observed * 1000.0)
    cluster_ids = household_cluster_ids(spine_df).to_numpy()
    variance_frames = []
    for universe in UNIVERSES:
        in_universe = universe_mask(spine_df, universe).to_numpy()
        if not in_universe.any():
            continue
        variance = bootstrap_group_variance(
            spine_df["occ1990dd"].to_numpy()[in_universe],
            spine_df[weight_column].to_numpy(dtype=float)[in_universe],
            cluster_ids[in_universe],
            scale,
            replicates,
            seed,
        )
        variance_frames.append(
            pd.DataFrame({"occ1990dd": variance.index.astype(int), "universe": universe, "sampling_variance": variance.to_numpy()})
        )
    return pd.concat(variance_frames, ignore_index=True)


TABULATED_DIR = os.path.join(download_ipums_cps.RAW_DIR, "tabulated")
REBUILT_PANEL_PATH = "data/output/cps_detailed_occupation_panel_rebuilt.csv"
REBUILT_CROSSTAB_PATH = "data/output/cps_detailed_occ_crosstab_rebuilt.csv"
REBUILT_GATES_PATH = "data/output/cps_detailed_gates_rebuilt.csv"
SEED_PATH = "seeds/cps_detailed_occupation_panel.csv"
CROSSTAB_SEED_PATH = "seeds/cps_detailed_occ_crosstab.csv"
GATES_SEED_PATH = "seeds/cps_detailed_gates.csv"
PUBLISHED_TEN_GROUP_PANEL_PATH = "seeds/cps_occupation_panel.csv"
TOTAL_EMPLOYMENT_SERIES_ID = "LNU02000000"

GATE_COLUMNS = ["gate", "scope", "observed", "threshold", "gated", "passed"]
COMPLETE_YEAR_MONTHS = 12
G1_FIRST_GATED_YEAR = 2003
G1_TOLERANCE = 0.01
G2_TOLERANCE = 0.01
G6_MAXIMUM_UNMAPPED_SHARE = 0.01
REQUIRED_GATES = ("G1", "G2", "G5", "G6")


class GateFailureError(RuntimeError):
    """A seed was about to be promoted from a build whose gates did not all pass."""


def _as_bool(column: pd.Series) -> pd.Series:
    """True only for real true values; NaN and 'False' read back from CSV are False."""
    return column.astype(str).str.strip().str.lower().eq("true")


def spine_lookup() -> dict[int, int]:
    """IPUMS OCC1990 (1990 Census basis) -> occ1990dd, from Dorn's occ1990 table."""
    crosswalk_df = load_dorn_crosswalk("1990")
    return dict(zip(crosswalk_df["source_code"].astype(int), crosswalk_df["occ1990dd"].astype(int)))


def gate_weight_column(year: int) -> str:
    """The weight whose totals match BLS's published figures in that year."""
    return "COMPWT" if year >= ipums_variables.COMPOSITE_WEIGHT_FIRST_YEAR else "WTFINL"


def ten_group_lookups() -> dict[str, dict[int, str]]:
    """Per coding block, raw Census code -> Phase 1 CPS group."""
    return {block: census_code_ten_group_lookup(load_census_code_list(vintage)) for block, (_, _, vintage) in CODING_BLOCKS.items()}


@dataclass
class YearTables:
    """Everything one year of microdata contributes to the seeds and the gates."""

    panel_df: pd.DataFrame
    crosstab_df: pd.DataFrame
    ten_group_df: pd.DataFrame
    summary: dict


def build_year_tables(year: int, person_df: pd.DataFrame, spine: dict[int, int], lookups_by_block: dict[str, dict[int, str]]) -> YearTables:
    """Tabulate one year: panel with variance, raw-code crosstab, direct ten-group totals, total and G6 share."""
    employed_df = select_civilian_employed(person_df)
    spine_df, unmapped_share = attach_occ1990dd(employed_df, spine)
    panel_df = tabulate_year(spine_df, year).merge(cluster_bootstrap_variance(spine_df), on=["occ1990dd", "universe"], how="left")
    gate_weight = gate_weight_column(year)
    coding_block = coding_block_for_year(year)
    ten_group_df = (
        tabulate_ten_groups_direct(employed_df, year, lookups_by_block[coding_block], gate_weight)
        if coding_block
        else pd.DataFrame(columns=["year", "cps_group", "employed_thousands", "months_observed"])
    )
    summary = {**tabulate_total(employed_df, year, gate_weight), "unmapped_share": unmapped_share}
    return YearTables(panel_df[PANEL_COLUMNS], tabulate_crosstab(spine_df, year), ten_group_df, summary)


def read_year_persons(year: int, raw_dir: str = download_ipums_cps.RAW_DIR) -> pd.DataFrame | None:
    """A downloaded year's civilian employed records, or None if the year is not downloaded."""
    extract_dir = os.path.join(raw_dir, "basic", str(year))
    if not download_ipums_cps.extract_is_downloaded(extract_dir):
        return None
    chunk_frames = [
        select_civilian_employed(chunk_df[ipums_variables.BASIC_MONTHLY_VARIABLES])
        for chunk_df in download_ipums_cps.read_extract(extract_dir)
    ]
    return pd.concat(chunk_frames, ignore_index=True)


def _year_cache_paths(year: int, tabulated_dir: str) -> dict[str, str]:
    return {name: os.path.join(tabulated_dir, f"{year}_{name}.csv") for name in ("panel", "crosstab", "ten_group", "summary")}


def write_year_cache(year: int, year_tables: YearTables, tabulated_dir: str = TABULATED_DIR) -> None:
    """Cache one year's tables, so an interrupted 44-year build resumes where it stopped."""
    os.makedirs(tabulated_dir, exist_ok=True)
    cache_paths = _year_cache_paths(year, tabulated_dir)
    year_tables.panel_df.to_csv(cache_paths["panel"], index=False)
    year_tables.crosstab_df.to_csv(cache_paths["crosstab"], index=False)
    year_tables.ten_group_df.to_csv(cache_paths["ten_group"], index=False)
    pd.DataFrame([year_tables.summary]).to_csv(cache_paths["summary"], index=False)


def read_year_cache(year: int, tabulated_dir: str = TABULATED_DIR) -> YearTables | None:
    """A cached year, or None if any of its four files is missing."""
    cache_paths = _year_cache_paths(year, tabulated_dir)
    if not all(os.path.exists(path) for path in cache_paths.values()):
        return None
    return YearTables(
        pd.read_csv(cache_paths["panel"]),
        pd.read_csv(cache_paths["crosstab"]),
        pd.read_csv(cache_paths["ten_group"]),
        pd.read_csv(cache_paths["summary"]).iloc[0].to_dict(),
    )


def _published_year_is_complete(published_panel_df: pd.DataFrame) -> pd.Series:
    """Per published row: 12 recorded months, or no month count and a later published year exists."""
    latest_year = published_panel_df["year"].max()
    months = (
        published_panel_df["months_observed"]
        if "months_observed" in published_panel_df.columns
        else pd.Series(np.nan, index=published_panel_df.index)
    )
    return (months == COMPLETE_YEAR_MONTHS) | (months.isna() & (published_panel_df["year"] < latest_year))


def gate_g1(ten_group_df: pd.DataFrame, published_panel_df: pd.DataFrame) -> pd.DataFrame:
    """G1: microdata mapped to the ten groups through raw OCC, against Phase 1's published series.

    Gated from 2003 in complete years at 1%; every other matched row is reported.
    """
    published_df = published_panel_df.assign(published_complete=_published_year_is_complete(published_panel_df))
    published_df = published_df.rename(columns={"employed_thousands": "published_thousands"})[
        ["year", "cps_group", "published_thousands", "published_complete"]
    ]
    merged_df = ten_group_df.merge(published_df, on=["year", "cps_group"], how="inner")
    relative_difference = (merged_df["employed_thousands"] / merged_df["published_thousands"] - 1).abs()
    gated = (
        (merged_df["months_observed"] == COMPLETE_YEAR_MONTHS)
        & merged_df["published_complete"]
        & (merged_df["year"] >= G1_FIRST_GATED_YEAR)
    )
    return pd.DataFrame(
        {
            "gate": "G1",
            "scope": merged_df["year"].astype(str) + " " + merged_df["cps_group"],
            "observed": relative_difference,
            "threshold": G1_TOLERANCE,
            "gated": gated,
            "passed": (relative_difference <= G1_TOLERANCE).where(gated, None),
        }
    )[GATE_COLUMNS]


def gate_g2(totals_df: pd.DataFrame, published_totals: pd.Series | None) -> pd.DataFrame:
    """G2: economy-wide employment against LNU02000000 annual means — gated at 1% from 1998, reported before."""
    if published_totals is None:
        return pd.DataFrame(
            [
                {
                    "gate": "G2",
                    "scope": f"{TOTAL_EMPLOYMENT_SERIES_ID} unavailable",
                    "observed": np.nan,
                    "threshold": G2_TOLERANCE,
                    "gated": True,
                    "passed": False,
                }
            ]
        )
    published_thousands = totals_df["year"].map(published_totals)
    relative_difference = (totals_df["total_thousands"] / published_thousands - 1).abs()
    gated = (
        (totals_df["year"] >= ipums_variables.COMPOSITE_WEIGHT_FIRST_YEAR)
        & (totals_df["months_observed"] == COMPLETE_YEAR_MONTHS)
        & published_thousands.notna()
    )
    return pd.DataFrame(
        {
            "gate": "G2",
            "scope": totals_df["year"].astype(str),
            "observed": relative_difference,
            "threshold": G2_TOLERANCE,
            "gated": gated,
            "passed": (relative_difference <= G2_TOLERANCE).where(gated, None),
        }
    )[GATE_COLUMNS]


def gate_g5(panel_df: pd.DataFrame, groups_df: pd.DataFrame) -> pd.DataFrame:
    """G5: every occ1990dd code carrying employment falls in exactly one Dorn group."""
    missing_codes = uncovered_codes(panel_df.loc[panel_df["employed_thousands"] > 0, "occ1990dd"].unique(), groups_df)
    return pd.DataFrame(
        [
            {
                "gate": "G5",
                "scope": f"codes in no Dorn group: {missing_codes}",
                "observed": float(len(missing_codes)),
                "threshold": 0.0,
                "gated": True,
                "passed": not missing_codes,
            }
        ]
    )


def gate_g6(unmapped_by_year: pd.Series) -> pd.DataFrame:
    """G6 (pinned by this plan): OCC1990 employment with no occ1990dd is at most 1% in every year."""
    return pd.DataFrame(
        {
            "gate": "G6",
            "scope": unmapped_by_year.index.astype(str),
            "observed": unmapped_by_year.to_numpy(dtype=float),
            "threshold": G6_MAXIMUM_UNMAPPED_SHARE,
            "gated": True,
            "passed": unmapped_by_year.to_numpy(dtype=float) <= G6_MAXIMUM_UNMAPPED_SHARE,
        }
    )[GATE_COLUMNS]


def all_gates_pass(gates_df: pd.DataFrame, required_gates: tuple[str, ...] = REQUIRED_GATES) -> bool:
    """True only if every required gate has at least one gated row and every gated row passed."""
    gated_df = gates_df[_as_bool(gates_df["gated"])]
    if any(gate not in set(gated_df["gate"]) for gate in required_gates):
        return False
    return bool(_as_bool(gated_df["passed"]).all())


def promote_rebuilt(promotions: dict[str, str], gates_path: str, required_gates: tuple[str, ...] = REQUIRED_GATES) -> None:
    """Copy rebuilt tables to their seed paths — only if the build's gate record shows every gate passed."""
    gates_df = pd.read_csv(gates_path)
    if not all_gates_pass(gates_df, required_gates):
        failing_df = gates_df[_as_bool(gates_df["gated"]) & ~_as_bool(gates_df["passed"])]
        raise GateFailureError(
            f"Refusing to promote: {len(failing_df)} gated check(s) failed.\n{failing_df.head(25).to_string(index=False)}"
        )
    for source_path, destination_path in promotions.items():
        shutil.copyfile(source_path, destination_path)


def build_rebuilt_tables(
    first_year: int,
    last_year: int,
    raw_dir: str = download_ipums_cps.RAW_DIR,
    tabulated_dir: str = TABULATED_DIR,
    panel_path: str = REBUILT_PANEL_PATH,
    crosstab_path: str = REBUILT_CROSSTAB_PATH,
    gates_path: str = REBUILT_GATES_PATH,
) -> pd.DataFrame:
    """Tabulate every downloaded year, run gates G1, G2, G5 and G6, and write the rebuilt tables and gate record."""
    if ipums_variables.VERIFICATION_STATUS != "verified":
        raise RuntimeError("ipums_cps_variables is unverified — complete plan Task 2 before tabulating real data")
    from historical_displacement import fetch_annual_means

    spine = spine_lookup()
    lookups_by_block = ten_group_lookups()
    collected_tables = []
    for year in range(first_year, last_year + 1):
        year_tables = read_year_cache(year, tabulated_dir)
        if year_tables is None:
            person_df = read_year_persons(year, raw_dir)
            if person_df is None:
                print(f"  {year}: not downloaded; skipped")
                continue
            year_tables = build_year_tables(year, person_df, spine, lookups_by_block)
            write_year_cache(year, year_tables, tabulated_dir)
        collected_tables.append(year_tables)
        print(f"  {year}: {len(year_tables.panel_df)} cells, unmapped share {year_tables.summary['unmapped_share']:.4f}")

    panel_df = pd.concat([tables.panel_df for tables in collected_tables], ignore_index=True)
    crosstab_df = collapse_crosstab(pd.concat([tables.crosstab_df for tables in collected_tables], ignore_index=True))
    ten_group_df = pd.concat([tables.ten_group_df for tables in collected_tables], ignore_index=True)
    summary_df = pd.DataFrame([tables.summary for tables in collected_tables])

    gates_df = pd.concat(
        [
            gate_g1(ten_group_df, pd.read_csv(PUBLISHED_TEN_GROUP_PANEL_PATH)),
            gate_g2(summary_df, fetch_annual_means(TOTAL_EMPLOYMENT_SERIES_ID, first_year, last_year)),
            gate_g5(panel_df, load_occ1990dd_groups()),
            gate_g6(summary_df.set_index("year")["unmapped_share"]),
        ],
        ignore_index=True,
    )
    for output_path, output_df in ((panel_path, panel_df), (crosstab_path, crosstab_df), (gates_path, gates_df)):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        output_df.to_csv(output_path, index=False)
    print(f"  Gates: {'ALL PASS' if all_gates_pass(gates_df) else 'FAILED'} — {gates_path}")
    return gates_df


def main(arguments: list[str]) -> None:
    """Command-line entry: `build FIRST_YEAR LAST_YEAR` or `promote`."""
    if arguments[:1] == ["build"] and len(arguments) == 3:
        build_rebuilt_tables(int(arguments[1]), int(arguments[2]))
    elif arguments == ["promote"]:
        promote_rebuilt(
            {REBUILT_PANEL_PATH: SEED_PATH, REBUILT_CROSSTAB_PATH: CROSSTAB_SEED_PATH, REBUILT_GATES_PATH: GATES_SEED_PATH},
            REBUILT_GATES_PATH,
        )
        print(f"  Promoted to {SEED_PATH}, {CROSSTAB_SEED_PATH}, {GATES_SEED_PATH}")
    else:
        raise SystemExit("usage: python cps_detailed_panel.py build FIRST_YEAR LAST_YEAR | promote")


if __name__ == "__main__":
    main(sys.argv[1:])
