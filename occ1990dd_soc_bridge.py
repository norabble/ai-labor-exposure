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

from dataclasses import dataclass

import numpy as np
import pandas as pd

from harmonize_soc import load_soc_2000_to_2010, load_soc_2010_to_2018, soc_vocabularies
from occ1990dd_reference import (
    SOC_GENERATION_BY_CENSUS_VINTAGE,
    UNCLASSIFIED_OCC1990DD,
    expand_soc_reference,
    load_census_code_list,
    load_dorn_crosswalk,
)

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
