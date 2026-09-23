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

import numpy as np
import pandas as pd
from scipy import sparse

import ipums_cps_variables as ipums_variables
from composition_displacement_validation import soc_major_to_dws_group
from occ1990dd_reference import soc_reference_prefix

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
