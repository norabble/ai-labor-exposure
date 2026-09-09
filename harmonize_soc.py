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
                                          above do not cover (see Task 2)

Outputs (written by analyze_bls.py):
  • data/output/soc_harmonization_units.csv         — unit membership per year
  • data/output/soc_harmonization_pruned_edges.csv  — crosswalk edges dropped
  • data/output/bls_harmonized_trends.csv           — unit-level trend series
"""

import re

import pandas as pd

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
    """SOC 2000 → SOC 2010 crosswalk as from_code/from_title/to_code/to_title rows."""
    return _load_two_column_crosswalk(f"{crosswalk_dir}/soc_2000_to_2010_crosswalk.xls", header_row_index=6)


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
