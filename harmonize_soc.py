"""
harmonize_soc.py
────────────────
Harmonize BLS OEWS occupation codes across the SOC 2000, SOC 2010, OEWS
2019–2020 hybrid, and SOC 2018 code generations into units whose employment
can be summed consistently from 2005 to 2025.

Why: detailed OEWS codes do not survive SOC revisions evenly. The SOC 2018
revision renumbered every computer occupation, so a 2022-anchored join keeps
3% of Computer and Mathematical employment before 2019. Sector-level growth
already avoids this by using major-group totals (see analyze_bls.py); this
module does the equivalent at occupation level by following BLS's own
crosswalks.

Inputs (all read-only, committed under seeds/soc_crosswalks/):
  • soc_2000_to_2010_crosswalk.xls      — BLS SOC 2000 → 2010 crosswalk
  • soc_2010_to_2018_crosswalk.xlsx     — BLS SOC 2010 → 2018 crosswalk
  • oes_2019_hybrid_structure.xlsx      — OEWS hybrid codes used for May 2019
                                          and May 2020, with their SOC 2018,
                                          OEWS 2018 and SOC 2010 equivalents
  • seeds/oews_aggregate_codes.csv      — OEWS-only aggregate codes the files
                                          above do not cover (see `load_aggregate_codes`)

Outputs (written by analyze_bls.py):
  • data/output/soc_harmonization_units.csv         — unit membership per year
  • data/output/soc_harmonization_pruned_edges.csv  — crosswalk edges dropped
  • data/output/bls_harmonized_trends.csv           — unit-level trend series
"""

import os
import re
from dataclasses import dataclass

import pandas as pd

from analyze_bls import COMPOSITE_ANCHOR_YEAR, attach_growth_columns

CROSSWALK_DIR = "seeds/soc_crosswalks"

SOC_CODE_PATTERN = re.compile(r"^\d\d-\d{4}$")
_FOOTNOTE_MARKER_PATTERN = re.compile(r"\s*\(#+\)\s*")


def clean_crosswalk_title(title) -> str:
    """Strip BLS footnote markers such as '(#)' and '(##)', trailing asterisks, and surrounding whitespace."""
    if pd.isna(title):
        return ""
    return _FOOTNOTE_MARKER_PATTERN.sub(" ", str(title)).replace("*", "").strip()


def is_residual_title(title) -> bool:
    """True for residual 'All Other' categories, which crosswalks use as catch-alls."""
    return "all other" in clean_crosswalk_title(title).lower()


def _valid_code_rows(crosswalk_df: pd.DataFrame, code_column: str) -> pd.DataFrame:
    """Keep only rows whose code cell is a detailed SOC code, ignoring the stray padding BLS leaves in some cells."""
    return crosswalk_df[crosswalk_df[code_column].astype(str).str.strip().str.match(SOC_CODE_PATTERN)].copy()


def _load_two_column_crosswalk(path: str, header_row_index: int) -> pd.DataFrame:
    raw_crosswalk_df = pd.read_excel(path, header=None, skiprows=header_row_index + 1).iloc[:, :4]
    raw_crosswalk_df.columns = ["from_code", "from_title", "to_code", "to_title"]
    crosswalk_edges_df = _valid_code_rows(raw_crosswalk_df.dropna(subset=["from_code", "to_code"]), "from_code")
    crosswalk_edges_df = _valid_code_rows(crosswalk_edges_df, "to_code")
    for title_column in ("from_title", "to_title"):
        crosswalk_edges_df[title_column] = crosswalk_edges_df[title_column].map(clean_crosswalk_title)
    for code_column in ("from_code", "to_code"):
        crosswalk_edges_df[code_column] = crosswalk_edges_df[code_column].astype(str).str.strip()
    return crosswalk_edges_df.drop_duplicates().reset_index(drop=True)


def load_soc_2000_to_2010(crosswalk_dir: str = CROSSWALK_DIR) -> pd.DataFrame:
    """
    SOC 2000 → SOC 2010 crosswalk as from_code/from_title/to_code/to_title rows.

    BLS publishes this one as a legacy .xls, which is what the seed holds; an
    .xlsx of the same name is accepted as a fallback so the file can also be
    supplied by writers that cannot emit the legacy format.
    """
    legacy_path = f"{crosswalk_dir}/soc_2000_to_2010_crosswalk.xls"
    crosswalk_path = legacy_path if os.path.exists(legacy_path) else f"{crosswalk_dir}/soc_2000_to_2010_crosswalk.xlsx"
    return _load_two_column_crosswalk(crosswalk_path, header_row_index=6)


def load_soc_2010_to_2018(crosswalk_dir: str = CROSSWALK_DIR) -> pd.DataFrame:
    """SOC 2010 → SOC 2018 crosswalk as from_code/from_title/to_code/to_title rows."""
    return _load_two_column_crosswalk(f"{crosswalk_dir}/soc_2010_to_2018_crosswalk.xlsx", header_row_index=8)


HYBRID_COLUMNS = [
    "hybrid_code",
    "hybrid_title",
    "soc_2018_code",
    "soc_2018_title",
    "oews_2018_code",
    "oews_2018_title",
    "soc_2010_code",
    "soc_2010_title",
]


def load_oews_hybrid_structure(crosswalk_dir: str = CROSSWALK_DIR) -> pd.DataFrame:
    """
    OEWS hybrid structure used for the May 2019 and May 2020 estimates.

    Each row links one hybrid code to one SOC 2018 code, one OEWS 2018 code,
    and one SOC 2010 code; aggregate hybrid codes therefore repeat across rows.
    """
    raw_hybrid_df = pd.read_excel(
        f"{crosswalk_dir}/oes_2019_hybrid_structure.xlsx", sheet_name="OES2019 Hybrid", header=None, skiprows=6
    ).iloc[:, :8]
    raw_hybrid_df.columns = HYBRID_COLUMNS
    hybrid_df = _valid_code_rows(raw_hybrid_df.dropna(subset=["hybrid_code"]), "hybrid_code")
    for column_name in HYBRID_COLUMNS:
        if column_name.endswith("_title"):
            hybrid_df[column_name] = hybrid_df[column_name].map(clean_crosswalk_title)
        else:
            hybrid_df[column_name] = hybrid_df[column_name].where(hybrid_df[column_name].notna(), None)
            hybrid_df[column_name] = hybrid_df[column_name].map(lambda code: None if code is None else str(code).strip())
    return hybrid_df.drop_duplicates().reset_index(drop=True)


# ── Code generations and OEWS-only aggregate codes ────────────────────────────

GENERATION_BY_YEAR: dict[str, str] = {
    **{year_suffix: "soc2000" for year_suffix in ("05", "06", "07", "08", "09")},
    **{year_suffix: "soc2010" for year_suffix in ("10", "11", "12", "13", "14", "15", "16", "17", "18")},
    **{year_suffix: "hybrid" for year_suffix in ("19", "20")},
    **{year_suffix: "soc2018" for year_suffix in ("21", "22", "23", "24", "25")},
}

AGGREGATE_CODES_PATH = "seeds/oews_aggregate_codes.csv"
AGGREGATE_CODES_COLUMNS = ["generation", "oews_code", "oews_title", "member_soc_code", "source"]


def load_aggregate_codes(path: str = AGGREGATE_CODES_PATH) -> pd.DataFrame:
    """
    OEWS-only aggregate codes that neither the SOC crosswalks nor the hybrid
    structure cover, mapped to their member SOC codes. One row per member.
    """
    aggregate_codes_df = pd.read_csv(path, dtype=str)
    missing_columns = [column for column in AGGREGATE_CODES_COLUMNS if column not in aggregate_codes_df.columns]
    if missing_columns:
        raise ValueError(f"{path} lacks columns {missing_columns}")
    return aggregate_codes_df[AGGREGATE_CODES_COLUMNS]


def soc_vocabularies(crosswalk_dir: str = CROSSWALK_DIR, aggregate_codes_path: str = AGGREGATE_CODES_PATH) -> dict[str, set[str]]:
    """Every SOC code of each generation known to the crosswalks, plus seed members."""
    soc_2000_to_2010_df = load_soc_2000_to_2010(crosswalk_dir)
    soc_2010_to_2018_df = load_soc_2010_to_2018(crosswalk_dir)
    vocabularies = {
        "soc2000": set(soc_2000_to_2010_df["from_code"]),
        "soc2010": set(soc_2000_to_2010_df["to_code"]) | set(soc_2010_to_2018_df["from_code"]),
        "soc2018": set(soc_2010_to_2018_df["to_code"]),
    }
    aggregate_codes_df = load_aggregate_codes(aggregate_codes_path)
    for generation, generation_rows_df in aggregate_codes_df.groupby("generation"):
        vocabularies.setdefault(generation, set()).update(generation_rows_df["member_soc_code"])
    return vocabularies


def resolve_oews_codes(
    oews_codes_df: pd.DataFrame,
    generation: str,
    vocabularies: dict[str, set[str]],
    aggregate_codes_df: pd.DataFrame,
    hybrid_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Map each OEWS detailed-row code of one year to the SOC code(s) of that
    year's generation. Resolution order: identity, aggregate seed, broad-group
    rule. Hybrid years resolve every code through the hybrid structure to SOC
    2018. Raises ValueError naming every code that resolves nowhere.
    """
    resolved_rows: list[dict[str, str]] = []
    unresolved_codes: list[str] = []

    if generation == "hybrid":
        hybrid_members = hybrid_df.dropna(subset=["hybrid_code", "soc_2018_code"]).groupby("hybrid_code")["soc_2018_code"]
        hybrid_lookup = {hybrid_code: sorted(set(member_codes)) for hybrid_code, member_codes in hybrid_members}
        for oews_code in oews_codes_df["OCC_CODE"].astype(str):
            if oews_code not in hybrid_lookup:
                unresolved_codes.append(oews_code)
                continue
            resolved_rows.extend(
                {"oews_code": oews_code, "soc_code": soc_code, "resolution": "hybrid"} for soc_code in hybrid_lookup[oews_code]
            )
    else:
        vocabulary = vocabularies[generation]
        seed_rows_df = aggregate_codes_df[aggregate_codes_df["generation"] == generation]
        seed_lookup = {
            oews_code: sorted(set(member_rows["member_soc_code"])) for oews_code, member_rows in seed_rows_df.groupby("oews_code")
        }
        for oews_code in oews_codes_df["OCC_CODE"].astype(str):
            if oews_code in vocabulary:
                resolved_rows.append({"oews_code": oews_code, "soc_code": oews_code, "resolution": "identity"})
            elif oews_code in seed_lookup:
                resolved_rows.extend(
                    {"oews_code": oews_code, "soc_code": soc_code, "resolution": "aggregate_seed"} for soc_code in seed_lookup[oews_code]
                )
            elif oews_code.endswith("0"):
                broad_members = sorted(code for code in vocabulary if code[:6] == oews_code[:6])
                if not broad_members:
                    unresolved_codes.append(oews_code)
                    continue
                resolved_rows.extend(
                    {"oews_code": oews_code, "soc_code": soc_code, "resolution": "broad_group"} for soc_code in broad_members
                )
            else:
                unresolved_codes.append(oews_code)

    if unresolved_codes:
        raise ValueError(
            f"{len(unresolved_codes)} OEWS code(s) in generation {generation!r} resolve to no SOC code: {unresolved_codes}. "
            f"Add them to {AGGREGATE_CODES_PATH}."
        )
    return pd.DataFrame(resolved_rows, columns=["oews_code", "soc_code", "resolution"])


# ── Harmonized units ──────────────────────────────────────────────────────────

SocNode = tuple[str, str]

CONSECUTIVE_GENERATION_PAIRS = [("soc2000", "soc2010"), ("soc2010", "soc2018")]

MEMBERSHIP_COLUMNS = ["unit_id", "year", "oews_code", "oews_title"]
UNIT_SUMMARY_COLUMNS = ["unit_id", "n_soc_2018_codes", "soc_2018_codes", "major_groups", "n_nodes", "discontinued"]
PRUNED_EDGE_COLUMNS = ["from_generation", "from_code", "from_title", "to_generation", "to_code", "to_title"]
COMPLETENESS_COLUMNS = ["unit_id", "year", "complete"]


class _UnionFind:
    """Disjoint-set forest over (generation, soc_code) nodes, with path halving."""

    def __init__(self) -> None:
        self._parent: dict[SocNode, SocNode] = {}

    def find(self, node: SocNode) -> SocNode:
        """The representative of the node's component, registering the node the first time it is seen."""
        self._parent.setdefault(node, node)
        while self._parent[node] != node:
            self._parent[node] = self._parent[self._parent[node]]
            node = self._parent[node]
        return node

    def union(self, left: SocNode, right: SocNode) -> None:
        """Merge the components holding the two nodes."""
        self._parent[self.find(left)] = self.find(right)

    def components(self) -> dict[SocNode, set[SocNode]]:
        """Every component, keyed by its representative node."""
        grouped: dict[SocNode, set[SocNode]] = {}
        for node in list(self._parent):
            grouped.setdefault(self.find(node), set()).add(node)
        return grouped


@dataclass
class HarmonizationResult:
    """
    The four tables describing harmonized occupation units: which OEWS code of
    each year belongs to which unit, what each unit is made of, which crosswalk
    edges were pruned before the components were cut, and whether each unit's
    membership is fully observed in each year.
    """

    membership_df: pd.DataFrame
    unit_summary_df: pd.DataFrame
    pruned_edges_df: pd.DataFrame
    completeness_df: pd.DataFrame


def resolved_generation(year_suffix: str) -> str:
    """The SOC generation an OEWS year's codes resolve into (hybrid years resolve to SOC 2018)."""
    generation = GENERATION_BY_YEAR[year_suffix]
    return "soc2018" if generation == "hybrid" else generation


def _unit_id_for(component: set[SocNode]) -> str:
    """Name a component after its lowest SOC 2018 code, or after its lowest code at all when it survives into no SOC 2018 code."""
    soc_2018_codes = sorted(code for generation, code in component if generation == "soc2018")
    if soc_2018_codes:
        return f"U-{soc_2018_codes[0]}"
    return f"U-{min(code for _, code in component)}-discontinued"


def _split_residual_edges(
    titled_pairs_df: pd.DataFrame, from_generation: str, to_generation: str, prune_residual_edges: bool
) -> tuple[list[tuple[SocNode, SocNode]], list[dict[str, str]]]:
    """
    Turn from_code/from_title/to_code/to_title rows into node pairs, holding back
    the edges that run between a residual 'All Other' category and a named one.
    Those edges are how a catch-all fuses unrelated occupations into one unit.
    """
    kept_edges: list[tuple[SocNode, SocNode]] = []
    pruned_rows: list[dict[str, str]] = []
    for titled_pair in titled_pairs_df.itertuples(index=False):
        crosses_residual_boundary = is_residual_title(titled_pair.from_title) != is_residual_title(titled_pair.to_title)
        if prune_residual_edges and crosses_residual_boundary:
            pruned_rows.append(
                {
                    "from_generation": from_generation,
                    "from_code": titled_pair.from_code,
                    "from_title": titled_pair.from_title,
                    "to_generation": to_generation,
                    "to_code": titled_pair.to_code,
                    "to_title": titled_pair.to_title,
                }
            )
            continue
        kept_edges.append(((from_generation, titled_pair.from_code), (to_generation, titled_pair.to_code)))
    return kept_edges, pruned_rows


def _hybrid_titled_pairs(hybrid_df: pd.DataFrame) -> pd.DataFrame:
    """
    The SOC 2010 → SOC 2018 links the hybrid structure implies, in the column
    shape of a crosswalk. They mostly duplicate crosswalk rows; they are carried
    so that the aggregates the hybrid file spells out are linked as well.
    """
    linked_rows_df = hybrid_df.dropna(subset=["soc_2010_code", "soc_2018_code"])
    titled_pairs_df = linked_rows_df.rename(
        columns={
            "soc_2010_code": "from_code",
            "soc_2010_title": "from_title",
            "soc_2018_code": "to_code",
            "soc_2018_title": "to_title",
        }
    )
    return titled_pairs_df[["from_code", "from_title", "to_code", "to_title"]].drop_duplicates().reset_index(drop=True)


def _identity_edges_for_unlinked_codes(
    vocabularies: dict[str, set[str]], crosswalk_edges_df: pd.DataFrame, from_generation: str, to_generation: str
) -> list[tuple[SocNode, SocNode]]:
    """
    Link a code to itself across a generation boundary when both generations
    publish it but the crosswalk between them never mentions it — BLS omits
    codes it did not touch, and without this they would split into two units.
    """
    codes_named_by_crosswalk = set(crosswalk_edges_df["from_code"]) | set(crosswalk_edges_df["to_code"])
    unchanged_codes = (vocabularies.get(from_generation, set()) & vocabularies.get(to_generation, set())) - codes_named_by_crosswalk
    return [((from_generation, code), (to_generation, code)) for code in sorted(unchanged_codes)]


def _aggregate_membership_edges(resolved_codes_by_year: dict[str, pd.DataFrame]) -> list[tuple[SocNode, SocNode]]:
    """Union the members of every OEWS code that reports several SOC codes together, so such a row never straddles two units."""
    aggregate_edges: list[tuple[SocNode, SocNode]] = []
    for year_suffix, resolved_codes_df in resolved_codes_by_year.items():
        generation = resolved_generation(year_suffix)
        for _, resolved_rows_df in resolved_codes_df.groupby("oews_code"):
            member_nodes = [(generation, soc_code) for soc_code in sorted(set(resolved_rows_df["soc_code"]))]
            aggregate_edges.extend((member_nodes[0], member_node) for member_node in member_nodes[1:])
    return aggregate_edges


def _assign_unit_ids(union_find: _UnionFind) -> tuple[dict[SocNode, str], dict[str, set[SocNode]]]:
    """Name every component and index its nodes by that name."""
    component_by_unit_id: dict[str, set[SocNode]] = {}
    unit_id_by_node: dict[SocNode, str] = {}
    for component in union_find.components().values():
        unit_id = _unit_id_for(component)
        if unit_id in component_by_unit_id:
            raise AssertionError(f"unit id {unit_id!r} names two components; the lowest-code naming rule is ambiguous here")
        component_by_unit_id[unit_id] = component
        unit_id_by_node.update({node: unit_id for node in component})
    return unit_id_by_node, component_by_unit_id


def _build_membership(
    oews_codes_by_year: dict[str, pd.DataFrame], resolved_codes_by_year: dict[str, pd.DataFrame], unit_id_by_node: dict[SocNode, str]
) -> pd.DataFrame:
    """One row per OEWS code per year, naming the unit that code's employment belongs to."""
    membership_rows: list[dict[str, str]] = []
    for year_suffix, resolved_codes_df in resolved_codes_by_year.items():
        generation = resolved_generation(year_suffix)
        oews_codes_df = oews_codes_by_year[year_suffix]
        title_by_oews_code = dict(zip(oews_codes_df["OCC_CODE"].astype(str), oews_codes_df["OCC_TITLE"].astype(str)))
        for oews_code, resolved_rows_df in resolved_codes_df.groupby("oews_code"):
            unit_ids = {unit_id_by_node[(generation, soc_code)] for soc_code in resolved_rows_df["soc_code"]}
            if len(unit_ids) != 1:
                raise AssertionError(f"OEWS code {oews_code!r} in year {year_suffix!r} straddles units {sorted(unit_ids)}")
            membership_rows.append(
                {
                    "unit_id": unit_ids.pop(),
                    "year": year_suffix,
                    "oews_code": oews_code,
                    "oews_title": title_by_oews_code.get(oews_code, ""),
                }
            )
    return pd.DataFrame(membership_rows, columns=MEMBERSHIP_COLUMNS)


def _build_completeness(
    component_by_unit_id: dict[str, set[SocNode]], resolved_codes_by_year: dict[str, pd.DataFrame], unit_id_by_node: dict[SocNode, str]
) -> pd.DataFrame:
    """
    Whether each unit's employment can be summed for each year: true when every
    member code of that year's generation that the OEWS ever published is
    actually present in that year's file.
    """
    published_vocabulary_by_generation: dict[str, set[str]] = {}
    for year_suffix, resolved_codes_df in resolved_codes_by_year.items():
        published_vocabulary_by_generation.setdefault(resolved_generation(year_suffix), set()).update(resolved_codes_df["soc_code"])

    completeness_rows: list[dict[str, object]] = []
    for year_suffix, resolved_codes_df in resolved_codes_by_year.items():
        generation = resolved_generation(year_suffix)
        present_codes_by_unit_id: dict[str, set[str]] = {}
        for soc_code in set(resolved_codes_df["soc_code"]):
            present_codes_by_unit_id.setdefault(unit_id_by_node[(generation, soc_code)], set()).add(soc_code)
        for unit_id, component in component_by_unit_id.items():
            member_codes = {code for node_generation, code in component if node_generation == generation}
            expected_codes = member_codes & published_vocabulary_by_generation[generation]
            completeness_rows.append(
                {
                    "unit_id": unit_id,
                    "year": year_suffix,
                    "complete": expected_codes <= present_codes_by_unit_id.get(unit_id, set()),
                }
            )
    return pd.DataFrame(completeness_rows, columns=COMPLETENESS_COLUMNS)


def _build_unit_summary(component_by_unit_id: dict[str, set[SocNode]]) -> pd.DataFrame:
    """One row per unit describing what it is made of, for auditing which occupations a unit fuses."""
    summary_rows: list[dict[str, object]] = []
    for unit_id, component in sorted(component_by_unit_id.items()):
        soc_2018_codes = sorted({code for generation, code in component if generation == "soc2018"})
        major_groups = sorted({code[:2] for _, code in component})
        summary_rows.append(
            {
                "unit_id": unit_id,
                "n_soc_2018_codes": len(soc_2018_codes),
                "soc_2018_codes": ";".join(soc_2018_codes),
                "major_groups": ";".join(major_groups),
                "n_nodes": len(component),
                "discontinued": not soc_2018_codes,
            }
        )
    return pd.DataFrame(summary_rows, columns=UNIT_SUMMARY_COLUMNS)


def build_harmonized_units(
    oews_codes_by_year: dict[str, pd.DataFrame],
    crosswalk_dir: str = CROSSWALK_DIR,
    aggregate_codes_path: str = AGGREGATE_CODES_PATH,
    prune_residual_edges: bool = True,
) -> HarmonizationResult:
    """
    Cut the SOC code generations into harmonized units whose employment can be
    summed consistently across years.

    Nodes are (generation, soc_code) pairs; a unit is one connected component of
    the graph joining them by BLS crosswalk rows, hybrid-structure rows,
    membership of an OEWS aggregate code, and identity across a generation
    boundary the crosswalk does not mention. Edges between a residual 'All
    Other' category and a named occupation are pruned first unless
    `prune_residual_edges` is false — left in, they fuse the whole computer
    block with unrelated residuals into a single unit.

    Each value of `oews_codes_by_year` holds that year's detailed OEWS rows with
    columns OCC_CODE and OCC_TITLE, keyed by two-digit year suffix.
    """
    soc_2000_to_2010_df = load_soc_2000_to_2010(crosswalk_dir)
    soc_2010_to_2018_df = load_soc_2010_to_2018(crosswalk_dir)
    hybrid_df = load_oews_hybrid_structure(crosswalk_dir)
    aggregate_codes_df = load_aggregate_codes(aggregate_codes_path)
    vocabularies = soc_vocabularies(crosswalk_dir, aggregate_codes_path)

    resolved_codes_by_year = {
        year_suffix: resolve_oews_codes(oews_codes_df, GENERATION_BY_YEAR[year_suffix], vocabularies, aggregate_codes_df, hybrid_df)
        for year_suffix, oews_codes_df in oews_codes_by_year.items()
    }

    unit_edges: list[tuple[SocNode, SocNode]] = []
    pruned_rows: list[dict[str, str]] = []
    for titled_pairs_df, (from_generation, to_generation) in (
        (soc_2000_to_2010_df, CONSECUTIVE_GENERATION_PAIRS[0]),
        (soc_2010_to_2018_df, CONSECUTIVE_GENERATION_PAIRS[1]),
        (_hybrid_titled_pairs(hybrid_df), CONSECUTIVE_GENERATION_PAIRS[1]),
    ):
        kept_edges, edges_pruned_here = _split_residual_edges(titled_pairs_df, from_generation, to_generation, prune_residual_edges)
        unit_edges.extend(kept_edges)
        pruned_rows.extend(edges_pruned_here)

    for crosswalk_edges_df, (from_generation, to_generation) in (
        (soc_2000_to_2010_df, CONSECUTIVE_GENERATION_PAIRS[0]),
        (soc_2010_to_2018_df, CONSECUTIVE_GENERATION_PAIRS[1]),
    ):
        unit_edges.extend(_identity_edges_for_unlinked_codes(vocabularies, crosswalk_edges_df, from_generation, to_generation))
    unit_edges.extend(_aggregate_membership_edges(resolved_codes_by_year))

    union_find = _UnionFind()
    for generation, generation_codes in vocabularies.items():
        for soc_code in generation_codes:
            union_find.find((generation, soc_code))
    for year_suffix, resolved_codes_df in resolved_codes_by_year.items():
        for soc_code in set(resolved_codes_df["soc_code"]):
            union_find.find((resolved_generation(year_suffix), soc_code))
    for left_node, right_node in unit_edges:
        union_find.union(left_node, right_node)

    unit_id_by_node, component_by_unit_id = _assign_unit_ids(union_find)
    return HarmonizationResult(
        membership_df=_build_membership(oews_codes_by_year, resolved_codes_by_year, unit_id_by_node),
        unit_summary_df=_build_unit_summary(component_by_unit_id),
        pruned_edges_df=pd.DataFrame(pruned_rows, columns=PRUNED_EDGE_COLUMNS).drop_duplicates().reset_index(drop=True),
        completeness_df=_build_completeness(component_by_unit_id, resolved_codes_by_year, unit_id_by_node),
    )


# ── Unit-level trend series ───────────────────────────────────────────────────

HARMONIZED_TREND_ID_COLUMNS = ["unit_id", "soc_2018_codes", "major_groups"]
_GROWTH_PERIOD_PATTERN = re.compile(r"^(?:hist_)?emp_growth_(\d\d_\d\d)$")
LARGE_ANNUAL_MOVE_THRESHOLD = 0.25


def _unit_year_totals(year_frame: pd.DataFrame, year_membership_df: pd.DataFrame) -> pd.DataFrame:
    """
    One year's employment total and employment-weighted median wage per unit.

    The wage is weighted over the members that actually report a median: OEWS
    suppresses A_MEDIAN for some detailed rows, and letting a suppressed member
    drop the whole unit would lose far more series than it protects.
    """
    member_rows_df = year_membership_df.merge(
        year_frame[["OCC_CODE", "TOT_EMP", "A_MEDIAN"]], left_on="oews_code", right_on="OCC_CODE", how="inner", validate="one_to_one"
    )
    member_rows_df["wage_weight"] = member_rows_df["TOT_EMP"].where(member_rows_df["A_MEDIAN"].notna())
    member_rows_df["weighted_wage"] = member_rows_df["A_MEDIAN"] * member_rows_df["wage_weight"]
    unit_totals_df = member_rows_df.groupby("unit_id").agg(
        TOT_EMP=("TOT_EMP", lambda member_employment: member_employment.sum(min_count=1)),
        weighted_wage_total=("weighted_wage", "sum"),
        wage_weight_total=("wage_weight", "sum"),
    )
    unit_totals_df["A_MEDIAN"] = (unit_totals_df["weighted_wage_total"] / unit_totals_df["wage_weight_total"]).where(
        unit_totals_df["wage_weight_total"] > 0
    )
    return unit_totals_df[["TOT_EMP", "A_MEDIAN"]]


def build_harmonized_trends(
    year_frames: dict[str, pd.DataFrame], harmonization: HarmonizationResult, available_years: list[str]
) -> pd.DataFrame:
    """
    Employment and median-wage series per harmonized unit, with the same growth
    columns as bls_trends.csv.

    One row per unit that OEWS publishes in the composite anchor year. A unit's
    year is NaN — never 0 — when the unit has no member row in that year's file
    at all, or when its membership for that year is incomplete: summing a
    partial membership would read as a collapse in employment rather than as
    the missing observation it is.
    """
    membership_df = harmonization.membership_df
    anchor_unit_ids = sorted(set(membership_df.loc[membership_df["year"] == COMPOSITE_ANCHOR_YEAR, "unit_id"]))
    completeness_by_unit_year = harmonization.completeness_df.set_index(["unit_id", "year"])["complete"].to_dict()

    trend_df = pd.DataFrame(index=pd.Index(anchor_unit_ids, name="unit_id"))
    for year_suffix in available_years:
        unit_totals_df = _unit_year_totals(year_frames[year_suffix], membership_df[membership_df["year"] == year_suffix]).reindex(
            anchor_unit_ids
        )
        complete_flags = pd.Series(
            [bool(completeness_by_unit_year.get((unit_id, year_suffix), False)) for unit_id in anchor_unit_ids], index=anchor_unit_ids
        )
        trend_df[f"TOT_EMP_{year_suffix}"] = unit_totals_df["TOT_EMP"].where(complete_flags)
        trend_df[f"A_MEDIAN_{year_suffix}"] = unit_totals_df["A_MEDIAN"].where(complete_flags)

    trend_df = trend_df.reset_index()
    unit_labels_df = harmonization.unit_summary_df[["unit_id", "soc_2018_codes", "major_groups"]]
    trend_df = trend_df.merge(unit_labels_df, on="unit_id", how="left", validate="one_to_one")
    ordered_columns = HARMONIZED_TREND_ID_COLUMNS + [column for column in trend_df.columns if column not in HARMONIZED_TREND_ID_COLUMNS]
    return attach_growth_columns(trend_df[ordered_columns], available_years)


def boundary_continuity_report(harmonized_trends_df: pd.DataFrame) -> pd.DataFrame:
    """
    Share of units moving more than 25% in each year-over-year period.

    A SOC revision that the harmonization failed to absorb would show up as a
    spike in this share at the 2009→10, 2018→19 or 2020→21 boundary; an ordinary
    year is the comparison.
    """
    report_rows: list[dict[str, object]] = []
    for column_name in harmonized_trends_df.columns:
        period_match = _GROWTH_PERIOD_PATTERN.match(str(column_name))
        if period_match is None:
            continue
        growth_values = harmonized_trends_df[column_name].dropna()
        report_rows.append(
            {
                "period": period_match.group(1),
                "n_units": len(growth_values),
                "share_abs_growth_over_25pct": float((growth_values.abs() > LARGE_ANNUAL_MOVE_THRESHOLD).mean())
                if len(growth_values)
                else float("nan"),
            }
        )
    report_df = pd.DataFrame(report_rows, columns=["period", "n_units", "share_abs_growth_over_25pct"])
    return report_df.sort_values("period").reset_index(drop=True)
