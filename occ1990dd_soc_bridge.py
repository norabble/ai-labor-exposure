"""
occ1990dd_soc_bridge.py
───────────────────────
The label bridge for Phase 2 of the deep history extension. The model's
demand-type labels live on SOC 2018 codes and the CPS microdata panel lives on
occ1990dd; this module gives every occ1990dd occupation a score by following
published crosswalks between them, and measures the error that chain
introduces (gate G4).

Chain (spec § The bridge), anchored on the newest vintage Dorn covers:

  occ1990dd ─(Dorn occ2010)─► Census 2010 code ─(Census list)─► SOC 2010 ─(BLS)─► SOC 2018

Split weights come from OEWS 2022 employment, the anchor the harmonized SOC
units already use. A SOC code reachable from k owners gives each owner 1/k of its
employment before weights are normalised within the owner; an owner none of
whose members have OEWS employment weights its members equally. OEWS excludes
the self-employed, so self-employment-heavy occupations are misweighted — the
bridge check measures the consequence rather than assuming it away.

Inputs:
  • seeds/occ1990dd_crosswalks/, seeds/cps_soc_crosswalks/, seeds/soc_crosswalks/
  • data/output/bls_trends.csv (OEWS 2022 employment)
  • data/output/occupation_composition_model_report.csv
  • data/output/occupation_dynamic_model_report.csv
  • data/raw/anthropic_job_exposure.csv (optional)
Outputs: none directly — cps_detailed_validation.py writes what these functions build.
"""

import os
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from cps_detailed_panel import CODING_BLOCKS
from harmonize_soc import load_soc_2000_to_2010, load_soc_2010_to_2018, soc_vocabularies
from occ1990dd_reference import (
    SOC_GENERATION_BY_CENSUS_VINTAGE,
    UNCLASSIFIED_OCC1990DD,
    expand_soc_reference,
    load_census_code_list,
    load_dorn_crosswalk,
)
from synthesize_impacts import DEMAND_TYPE_PCT_COLUMNS, attach_dominant_demand

OEWS_TRENDS_PATH = "data/output/bls_trends.csv"
ANCHOR_YEAR = "2022"
CHAIN_CENSUS_VINTAGE = "2010"


@dataclass(frozen=True)
class SocTables:
    """SOC vocabularies per generation plus the two BLS generation-to-generation crosswalks."""

    vocabularies: dict[str, set[str]]
    soc2000_to_soc2010: dict[str, set[str]]
    soc2010_to_soc2018: dict[str, set[str]]


def _edge_lookup(edges_df: pd.DataFrame) -> dict[str, set[str]]:
    lookup: dict[str, set[str]] = {}
    for from_code, to_code in zip(edges_df["from_code"], edges_df["to_code"]):
        lookup.setdefault(from_code, set()).add(to_code)
    return lookup


def load_soc_tables() -> SocTables:
    """The committed SOC crosswalks, shaped for chaining."""
    return SocTables(
        vocabularies=soc_vocabularies(),
        soc2000_to_soc2010=_edge_lookup(load_soc_2000_to_2010()),
        soc2010_to_soc2018=_edge_lookup(load_soc_2010_to_2018()),
    )


def _map_codes(soc_codes: set[str], lookup: dict[str, set[str]]) -> set[str]:
    mapped_codes: set[str] = set()
    for code in soc_codes:
        mapped_codes |= lookup.get(code, set())
    return mapped_codes


def to_soc_2018(soc_codes: set[str], generation: str, soc_tables: SocTables) -> set[str]:
    """Carry detailed codes of one SOC generation forward to SOC 2018."""
    if generation == "soc2018":
        return set(soc_codes)
    if generation == "soc2010":
        return _map_codes(soc_codes, soc_tables.soc2010_to_soc2018)
    if generation == "soc2000":
        return _map_codes(_map_codes(soc_codes, soc_tables.soc2000_to_soc2010), soc_tables.soc2010_to_soc2018)
    raise ValueError(f"Unknown SOC generation {generation!r}")


def census_code_members(code_list_df: pd.DataFrame, census_vintage: str, soc_tables: SocTables) -> pd.DataFrame:
    """Every SOC 2018 code each Census code of one vintage reaches."""
    generation = SOC_GENERATION_BY_CENSUS_VINTAGE[census_vintage]
    vocabulary = soc_tables.vocabularies[generation]
    member_rows = []
    for census_code, soc_reference in zip(code_list_df["census_code"], code_list_df["soc_reference"]):
        for soc_2018_code in sorted(to_soc_2018(expand_soc_reference(soc_reference, vocabulary), generation, soc_tables)):
            member_rows.append({"census_code": int(census_code), "soc_2018_code": soc_2018_code})
    return pd.DataFrame(member_rows, columns=["census_code", "soc_2018_code"])


def build_chain_edges(dorn_2010_df: pd.DataFrame, census_2010_members_df: pd.DataFrame) -> pd.DataFrame:
    """occ1990dd → Census 2010 code → SOC 2018 edges, without the unclassified code."""
    chain_df = dorn_2010_df.rename(columns={"source_code": "census_code"}).merge(census_2010_members_df, on="census_code", how="inner")
    chain_df = chain_df[chain_df["occ1990dd"] != UNCLASSIFIED_OCC1990DD]
    return chain_df[["occ1990dd", "census_code", "soc_2018_code"]].drop_duplicates().reset_index(drop=True)


def equal_division_weights(edges_df: pd.DataFrame, owner_column: str, anchor_employment: pd.Series) -> pd.DataFrame:
    """Per-owner SOC 2018 weights from anchor employment, dividing shared codes equally among owners."""
    owner_members_df = edges_df[[owner_column, "soc_2018_code"]].drop_duplicates().copy()
    owners_per_code = owner_members_df.groupby("soc_2018_code")[owner_column].transform("nunique")
    owner_members_df["raw_weight"] = owner_members_df["soc_2018_code"].map(anchor_employment).fillna(0.0).astype(float) / owners_per_code
    owner_totals = owner_members_df.groupby(owner_column)["raw_weight"].transform("sum")
    member_counts = owner_members_df.groupby(owner_column)["soc_2018_code"].transform("count")
    owner_members_df["weight"] = np.where(
        owner_totals > 0,
        owner_members_df["raw_weight"] / owner_totals.where(owner_totals > 0, 1.0),
        1.0 / member_counts,
    )
    return owner_members_df[[owner_column, "soc_2018_code", "weight"]].sort_values([owner_column, "soc_2018_code"]).reset_index(drop=True)


def load_anchor_employment(trends_path: str = OEWS_TRENDS_PATH, anchor_year: str = ANCHOR_YEAR) -> pd.Series:
    """OEWS anchor-year employment keyed by SOC 2018 code; suppressed cells dropped."""
    employment_column = f"TOT_EMP_{anchor_year}"
    trends_df = pd.read_csv(trends_path, usecols=["OCC_CODE", employment_column])
    trends_df[employment_column] = pd.to_numeric(trends_df[employment_column], errors="coerce")
    trends_df = trends_df.dropna(subset=[employment_column]).drop_duplicates(subset=["OCC_CODE"])
    return trends_df.set_index("OCC_CODE")[employment_column].astype(float)


def build_bridge_weights(anchor_employment: pd.Series, soc_tables: SocTables | None = None) -> pd.DataFrame:
    """Chained occ1990dd → SOC 2018 weights from the committed seeds."""
    soc_tables = soc_tables or load_soc_tables()
    census_members_df = census_code_members(load_census_code_list(CHAIN_CENSUS_VINTAGE), CHAIN_CENSUS_VINTAGE, soc_tables)
    chain_edges_df = build_chain_edges(load_dorn_crosswalk(CHAIN_CENSUS_VINTAGE), census_members_df)
    return equal_division_weights(chain_edges_df, "occ1990dd", anchor_employment)


COMPOSITION_REPORT_PATH = "data/output/occupation_composition_model_report.csv"
DYNAMIC_REPORT_PATH = "data/output/occupation_dynamic_model_report.csv"
ANTHROPIC_EXPOSURE_PATH = "data/raw/anthropic_job_exposure.csv"

PCT_COLUMNS = list(DEMAND_TYPE_PCT_COLUMNS.values())
# A SOC code is "labeled" when the demand composition model scored it.
LABEL_SCORE_COLUMN = "composition_net_change"
# The four era-test scores, in composition_era_validation.SCORE_CONFIGS order.
SOC_SCORE_COLUMNS = ["composition_net_change", "net_employment_change", "occupation_exposure", "observed_exposure"]
# Per-occupation displacement rates, for the Phase 2b predicted displacement.
DISPLACEMENT_SCORE_COLUMNS = ["composition_gross_displacement", "dynamic_gross_displacement"]


def score_units(weights_df: pd.DataFrame, owner_column: str, soc_scores_df: pd.DataFrame, score_columns: list[str]) -> pd.DataFrame:
    """Weighted mean of each score over an owner's labeled SOC members, with the labeled share.

    Weights are renormalised over the members that carry each column, so an
    unlabeled member dilutes nothing — it only lowers `labeled_share`, which the
    validation filters on. `dominant_demand` is re-derived from the blended pct_*
    columns with attach_dominant_demand, never carried from a member.
    """
    merged_df = weights_df.merge(soc_scores_df, left_on="soc_2018_code", right_on="OCC_CODE", how="left")
    is_labeled = (
        merged_df[LABEL_SCORE_COLUMN].notna() if LABEL_SCORE_COLUMN in merged_df.columns else pd.Series(False, index=merged_df.index)
    )
    merged_df = merged_df.assign(is_labeled=is_labeled)
    blended_columns = list(dict.fromkeys(score_columns + [column for column in PCT_COLUMNS if column in merged_df.columns]))

    unit_rows = []
    for owner, member_df in merged_df.groupby(owner_column):
        unit_row: dict[str, float | int | str] = {
            owner_column: owner,
            "labeled_share": float(member_df.loc[member_df["is_labeled"], "weight"].sum()),
        }
        for column in blended_columns:
            scored_df = member_df.dropna(subset=[column])
            weight_total = scored_df["weight"].sum()
            unit_row[column] = float((scored_df[column] * scored_df["weight"]).sum() / weight_total) if weight_total > 0 else float("nan")
        unit_rows.append(unit_row)

    units_df = pd.DataFrame(unit_rows)
    if all(column in units_df.columns for column in PCT_COLUMNS):
        units_df = attach_dominant_demand(units_df)
    return units_df


def load_soc_scores(
    composition_report_path: str = COMPOSITION_REPORT_PATH,
    dynamic_report_path: str = DYNAMIC_REPORT_PATH,
    anthropic_path: str = ANTHROPIC_EXPOSURE_PATH,
) -> tuple[pd.DataFrame, list[str]]:
    """Every model score per SOC 2018 code, and which of the four era-test scores are present.

    Both reports call their net change `net_employment_change`; the composition
    model's is renamed `composition_net_change`, matching composition_era_validation.
    """
    composition_df = pd.read_csv(
        composition_report_path, usecols=["OCC_CODE", "net_employment_change", "gross_displacement", *PCT_COLUMNS]
    ).rename(columns={"net_employment_change": "composition_net_change", "gross_displacement": "composition_gross_displacement"})
    dynamic_df = pd.read_csv(
        dynamic_report_path, usecols=["OCC_CODE", "net_employment_change", "occupation_exposure", "gross_displacement"]
    ).rename(columns={"gross_displacement": "dynamic_gross_displacement"})
    soc_scores_df = composition_df.merge(dynamic_df, on="OCC_CODE", how="outer", validate="one_to_one")

    if os.path.exists(anthropic_path):
        anthropic_df = pd.read_csv(anthropic_path).rename(columns={"occ_code": "OCC_CODE"})
        if "observed_exposure" in anthropic_df.columns:
            observed_df = anthropic_df[["OCC_CODE", "observed_exposure"]].drop_duplicates(subset=["OCC_CODE"])
            soc_scores_df = soc_scores_df.merge(observed_df, on="OCC_CODE", how="left")

    score_columns = [column for column in SOC_SCORE_COLUMNS if column in soc_scores_df.columns]
    return soc_scores_df, score_columns


def occ1990dd_composition_stability(
    weights_df: pd.DataFrame, occupation_trends_df: pd.DataFrame, earliest_year: str = "1999"
) -> pd.DataFrame:
    """Share of each unit's bridge weight on SOC codes OEWS already published in `earliest_year`.

    The detailed-grain version of cps_historical_panel.sector_composition_stability:
    a bound on where carrying 2025 labels back is least safe, not a measure of
    task-content drift.
    """
    antecedent_df = occupation_trends_df.drop_duplicates(subset=["OCC_CODE"]).set_index("OCC_CODE")
    has_antecedent = antecedent_df[f"TOT_EMP_{earliest_year}"].notna()
    stability_df = weights_df.assign(has_antecedent=weights_df["soc_2018_code"].map(has_antecedent).fillna(False).astype(bool))
    stability_df["stable_weight"] = stability_df["weight"] * stability_df["has_antecedent"]
    return (
        stability_df.groupby("occ1990dd", as_index=False)["stable_weight"]
        .sum()
        .rename(columns={"stable_weight": "stable_share"})
        .sort_values("stable_share")
        .reset_index(drop=True)
    )


G4_MINIMUM_R = 0.8
BRIDGE_CHECK_COLUMNS = [
    "coding_block",
    "occ1990dd",
    "chained_score",
    "direct_score",
    "gap",
    "block_pearson_r",
    "threshold",
    "block_gate_passed",
]


def census_scores_by_block(
    soc_scores_df: pd.DataFrame, score_columns: list[str], anchor_employment: pd.Series, soc_tables: SocTables | None = None
) -> dict[str, pd.DataFrame]:
    """Per coding block, a score for every Census code of that block's vintage, straight from SOC."""
    soc_tables = soc_tables or load_soc_tables()
    block_scores: dict[str, pd.DataFrame] = {}
    for coding_block, (_, _, census_vintage) in CODING_BLOCKS.items():
        members_df = census_code_members(load_census_code_list(census_vintage), census_vintage, soc_tables)
        census_weights_df = equal_division_weights(members_df, "census_code", anchor_employment)
        block_scores[coding_block] = score_units(census_weights_df, "census_code", soc_scores_df, score_columns)
    return block_scores


def direct_unit_scores(crosstab_df: pd.DataFrame, census_scores: dict[str, pd.DataFrame], score_columns: list[str]) -> pd.DataFrame:
    """Each unit scored through the raw Census codes CPS coded its workers into, weighted by CPS employment.

    Diagnostic only: these never replace chained scores in a reported result,
    because that would reopen the method seam Phase 1's D2 forbids.
    """
    unit_rows = []
    for coding_block, block_census_scores_df in census_scores.items():
        block_df = crosstab_df[crosstab_df["coding_block"] == coding_block].merge(
            block_census_scores_df[["census_code", *score_columns]], on="census_code", how="inner"
        )
        for occ1990dd_code, unit_df in block_df.groupby("occ1990dd"):
            unit_row: dict[str, float | int | str] = {"coding_block": coding_block, "occ1990dd": occ1990dd_code}
            for column in score_columns:
                scored_df = unit_df.dropna(subset=[column])
                weight_total = scored_df["employed_thousands"].sum()
                unit_row[column] = (
                    float((scored_df[column] * scored_df["employed_thousands"]).sum() / weight_total) if weight_total > 0 else float("nan")
                )
            unit_rows.append(unit_row)
    return pd.DataFrame(unit_rows, columns=["coding_block", "occ1990dd", *score_columns])


def bridge_check(chained_scores_df: pd.DataFrame, direct_scores_df: pd.DataFrame, score_column: str = LABEL_SCORE_COLUMN) -> pd.DataFrame:
    """Chained against direct score per unit and coding block, with each block's correlation and G4 verdict."""
    paired_df = direct_scores_df[["coding_block", "occ1990dd", score_column]].rename(columns={score_column: "direct_score"})
    paired_df = paired_df.merge(
        chained_scores_df[["occ1990dd", score_column]].rename(columns={score_column: "chained_score"}), on="occ1990dd", how="inner"
    ).dropna()
    paired_df["gap"] = paired_df["direct_score"] - paired_df["chained_score"]

    block_correlation: dict[str, float] = {}
    for coding_block, block_df in paired_df.groupby("coding_block"):
        enough_variation = len(block_df) >= 3 and block_df["direct_score"].nunique() > 1 and block_df["chained_score"].nunique() > 1
        block_correlation[coding_block] = (
            float(stats.pearsonr(block_df["chained_score"], block_df["direct_score"])[0]) if enough_variation else float("nan")
        )

    paired_df["block_pearson_r"] = paired_df["coding_block"].map(block_correlation)
    paired_df["threshold"] = G4_MINIMUM_R
    paired_df["block_gate_passed"] = paired_df["block_pearson_r"] >= G4_MINIMUM_R
    return paired_df[BRIDGE_CHECK_COLUMNS].sort_values(["coding_block", "occ1990dd"]).reset_index(drop=True)


def g4_passed(check_df: pd.DataFrame) -> bool:
    """G4: every coding block present, each with chained-vs-direct r of at least 0.8."""
    block_verdicts = check_df.groupby("coding_block")["block_gate_passed"].first()
    return all(coding_block in block_verdicts.index and bool(block_verdicts[coding_block]) for coding_block in CODING_BLOCKS)
