"""
occ1990dd_reference.py
──────────────────────
Loaders for the committed reference data behind Phase 2 of the deep history
extension: David Dorn's crosswalks from each Census occupation-code vintage to
the time-consistent `occ1990dd` codes, the Census Bureau's code lists relating
each CPS coding vintage to SOC, and Dorn's occupation-group partition.

Also resolves the Census lists' SOC references — which mix detailed codes,
broad groups ending in 0 and wildcards containing X — to the detailed SOC codes
they cover.

Inputs:
  • seeds/occ1990dd_crosswalks/occ{vintage}_occ1990dd.csv
  • seeds/cps_soc_crosswalks/ (three Census code-list workbooks)
  • seeds/occ1990dd_groups.csv
Outputs: none — loaders only.
"""

import os
import re

import pandas as pd

DORN_CROSSWALK_DIR = "seeds/occ1990dd_crosswalks"
CENSUS_CODE_LIST_DIR = "seeds/cps_soc_crosswalks"
GROUPS_PATH = "seeds/occ1990dd_groups.csv"

DORN_VINTAGES = ("1980", "1990", "2000", "2005", "2010")
UNCLASSIFIED_OCC1990DD = 999
# Codes Dorn's group partition assigns to no group; neither should carry civilian employment.
OUTSIDE_GROUP_OCC1990DD = frozenset({905, 991})

# vintage -> (file name, sheet name)
CENSUS_CODE_LISTS: dict[str, tuple[str, str]] = {
    "2002": ("2002-census-occupation-codes.xls", "Occ Codes"),
    "2010": ("2010-occ-codes-with-crosswalk-from-2002-2011.xls", "2010OccCodeList"),
    "2018": ("2018-occupation-code-list-and-crosswalk.xlsx", "2018 Census Occ Code List"),
}
SOC_GENERATION_BY_CENSUS_VINTAGE = {"2002": "soc2000", "2010": "soc2010", "2018": "soc2018"}
CENSUS_2018_TO_2010_SHEET = "2010 to 2018 Crosswalk "

_FOUR_DIGIT_CODE = r"\d{4}"
_SOC_REFERENCE_PATTERN = re.compile(r"\d\d-[0-9X]{4}")


def load_dorn_crosswalk(vintage: str, crosswalk_dir: str = DORN_CROSSWALK_DIR) -> pd.DataFrame:
    """One Census vintage's codes mapped to occ1990dd, as integer source_code / occ1990dd."""
    crosswalk_df = pd.read_csv(os.path.join(crosswalk_dir, f"occ{vintage}_occ1990dd.csv"))
    return crosswalk_df.astype({"source_code": int, "occ1990dd": int})


def known_occ1990dd_codes(crosswalk_dir: str = DORN_CROSSWALK_DIR) -> set[int]:
    """Every occ1990dd code any Dorn crosswalk reaches, excluding 999 (unclassified)."""
    codes: set[int] = set()
    for vintage in DORN_VINTAGES:
        codes |= set(load_dorn_crosswalk(vintage, crosswalk_dir)["occ1990dd"])
    codes.discard(UNCLASSIFIED_OCC1990DD)
    return codes


def _is_four_digit(column: pd.Series) -> pd.Series:
    return column.astype(str).str.strip().str.fullmatch(_FOUR_DIGIT_CODE)


def load_census_code_list(vintage: str, code_list_dir: str = CENSUS_CODE_LIST_DIR) -> pd.DataFrame:
    """One vintage's Census occupation codes with their titles and SOC references.

    Data rows are the ones whose code cell is exactly four digits; section headers
    carry ranges such as '0010-0430' and are skipped.
    """
    file_name, sheet_name = CENSUS_CODE_LISTS[vintage]
    raw_df = pd.read_excel(os.path.join(code_list_dir, file_name), sheet_name=sheet_name, header=None, dtype=str)
    code_rows_df = raw_df[_is_four_digit(raw_df[2]).fillna(False)]
    return pd.DataFrame(
        {
            "census_code": code_rows_df[2].str.strip().astype(int).to_numpy(),
            "census_title": code_rows_df[1].astype(str).str.strip().to_numpy(),
            "soc_reference": code_rows_df[3].astype(str).str.strip().to_numpy(),
        }
    )


def load_census_2018_to_2010(code_list_dir: str = CENSUS_CODE_LIST_DIR) -> pd.DataFrame:
    """2018 Census codes paired with the 2010 Census code each descends from.

    Continuation rows leave the 2010 column blank, so it is forward-filled. Every
    2018 code gets exactly one 2010 source; where Census merged several 2010 codes
    into one 2018 code, only the last-listed 2010 source survives the fill.
    """
    file_name, _ = CENSUS_CODE_LISTS["2018"]
    raw_df = pd.read_excel(os.path.join(code_list_dir, file_name), sheet_name=CENSUS_2018_TO_2010_SHEET, header=None, dtype=str)
    census_2010 = raw_df[1].where(_is_four_digit(raw_df[1]).fillna(False)).ffill()
    census_2018 = raw_df[4].where(_is_four_digit(raw_df[4]).fillna(False))
    pairs_df = pd.DataFrame({"census_2018": census_2018, "census_2010": census_2010}).dropna()
    return pairs_df.astype(int).drop_duplicates().reset_index(drop=True)


def soc_reference_prefix(reference: str) -> str | None:
    """The code prefix a SOC reference stands for, or None for 'none'.

    Detailed codes never end in 0, so a trailing zero marks a group ('11-2020' ->
    '11-202'). Wildcards keep every digit before the first X ('25-90XX' -> '25-90'):
    there the zero is a real digit.
    """
    normalised = reference.strip().upper()
    if not _SOC_REFERENCE_PATTERN.fullmatch(normalised):
        return None
    if "X" in normalised:
        return normalised.split("X", 1)[0]
    return normalised.rstrip("0")


def expand_soc_reference(reference: str, vocabulary: set[str]) -> set[str]:
    """Every detailed code in `vocabulary` that a Census list's SOC reference covers."""
    prefix = soc_reference_prefix(reference)
    if prefix is None:
        return set()
    return {code for code in vocabulary if code.startswith(prefix)}


def load_occ1990dd_groups(groups_path: str = GROUPS_PATH, crosswalk_dir: str = DORN_CROSSWALK_DIR) -> pd.DataFrame:
    """Each known occ1990dd code with its Dorn group. Codes in no group are omitted, not guessed."""
    ranges_df = pd.read_csv(groups_path)
    group_rows = []
    for code in sorted(known_occ1990dd_codes(crosswalk_dir)):
        matching_groups = ranges_df.loc[(ranges_df["first_code"] <= code) & (ranges_df["last_code"] >= code), "dorn_group"].unique()
        if len(matching_groups) > 1:
            raise ValueError(f"occ1990dd {code} falls in more than one Dorn group: {list(matching_groups)}")
        if len(matching_groups) == 1:
            group_rows.append({"occ1990dd": code, "dorn_group": matching_groups[0]})
    return pd.DataFrame(group_rows, columns=["occ1990dd", "dorn_group"])


def uncovered_codes(codes, groups_df: pd.DataFrame) -> list[int]:
    """The codes in `codes` that no Dorn group covers, sorted."""
    return sorted(set(int(code) for code in codes) - set(groups_df["occ1990dd"].astype(int)))
