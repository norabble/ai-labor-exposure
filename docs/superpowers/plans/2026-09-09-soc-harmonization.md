# SOC Crosswalk Harmonization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build occupation-level BLS employment series that are consistent from 2005 to 2025 by harmonizing SOC 2000, SOC 2010, the OEWS 2019–2020 hybrid, and SOC 2018 codes into units, so the occupation-level historical validation no longer depends on which detailed codes happened to survive the code revisions.

**Architecture:** A new `harmonize_soc.py` parses the three BLS crosswalk spreadsheets committed under `seeds/soc_crosswalks/`, resolves OEWS-only aggregate codes to SOC codes, builds a graph of (generation, code) nodes joined by crosswalk edges, and takes connected components as harmonized units — after dropping crosswalk edges that link a residual "All Other" category to a specific occupation, because those edges otherwise fuse the whole computer block with management and business residuals into one 39-node unit. `analyze_bls.py` then sums each unit's member rows per year into `bls_harmonized_trends.csv` with the same growth-column layout as the existing trend files, and `validate_bls.py`'s occupation-level signal-over-time chart runs on units instead of surviving 2022 codes. Sector-level code is untouched: it already uses major-group totals.

**Tech Stack:** Python 3.12, pandas, openpyxl (xlsx) and xlrd (xls) — both already in the environment because `analyze_bls.py` reads OEWS files in both formats. No new dependencies. No network access: implementers cannot reach bls.gov; every input is already on disk.

**Spec:** No separate spec document. The requirements are this plan plus the repository's `CLAUDE.md` and `CONTRIBUTING.md`. The controller's design notes are in the "Background" section below; treat them as the authority when a task is ambiguous.

## Global Constraints

- Coding standards from `CLAUDE.md`: no generic abbreviations (`df`, `res`, `tmp`, `val` are forbidden — use `crosswalk_edges_df`, `unit_membership_df`, etc.); variable names carry domain meaning; every Python file has a module docstring naming its purpose, inputs and outputs (ruff `D100`).
- Lint: `.venv/bin/ruff check <files>` and `.venv/bin/ruff format <files>` must pass. Line length limit is 140. Run ruff on the specific files you touched, not `.` (a protected path under `.claude/` breaks a repo-wide format run).
- Tests: `.venv/bin/python -m pytest tests/ -q`. New tests for this plan go in a new file `tests/test_harmonize_soc.py`; tests that need the raw OEWS zips must skip cleanly when `data/raw/bls/` is absent (CI does not have it) using `pytest.mark.skipif(not os.path.exists(...))`.
- Run Python through `.venv/bin/python`, never `uv run` (the uv cache directory is read-only in this environment).
- Never modify anything under `data/raw/` or `seeds/soc_crosswalks/` (the three spreadsheets there are the authoritative inputs, fetched from BLS by the controller). Never modify `seeds/classified_all_tasks.csv` or `seeds/cps_a19_panel.csv`.
- Every new pipeline output file gets a row in the `CLAUDE.md` "Outputs Reference" table before the task that creates it is committed. Every new seed file gets a sentence in the `CLAUDE.md` "Release Pipeline" section following the existing `seeds/` convention.
- Commit messages end with these two trailer lines exactly:
  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_017h8BcjpaxoxWqEDgwwsSqt
  ```
  Commit with `PATH="$PWD/.venv/bin:$PATH"` on the environment so the pre-commit hook can find ruff.
- Existing outputs and their numbers must not change: `bls_trends.csv`, `bls_sector_trends.csv`, every sector-level correlation, and every occupation-level correlation for 2022→2025 that is computed on `merged_validation_df`. Only the occupation-level *historical* chart (`model_signal_over_time_occupation.png`) changes what it plots.
- Do not dispatch subagents. Do not run `make`, `uv`, or anything that touches the network.

## Background: the data shapes an implementer must know

**Four code generations in the OEWS files** (verified on the files on disk):

| OEWS years (suffix) | Vocabulary | Detailed rows | Notes |
|---|---|---|---|
| 05–09 | SOC 2000 | 799–800 | one OEWS-only code: `47-2111` Electricians, which the 2000→2010 crosswalk file does not list (it is a genuine SOC 2000 code; the crosswalk row is simply missing) |
| 10–18 | SOC 2010 | 796–820 | 2010–11 carry 19 OEWS-only aggregate codes (e.g. `15-1150` Computer Support Specialists, `15-1179` Information Security Analysts, Web Developers, and Computer Network Architects, `29-1111` Registered Nurses, `31-1012` Nursing Aides…); 2012–16 carry `25-3097`/`25-3098` (teachers); 2017–18 carry 12 (e.g. `13-1020` Buyers and Purchasing Agents, `51-2028`, `53-1048`) |
| 19–20 | OEWS hybrid | 789 | 30 hybrid aggregate codes (e.g. `15-1256` = SOC 2018 `15-1252` + `15-1253`); the rest are SOC 2018 codes |
| 21–25 | SOC 2018 | 830–831 | 12 OEWS-only aggregate codes in every year including the 2022 anchor: `13-1020`, `13-2020`, `21-1018`, `25-2052`, `25-9045`, `29-2010`, `31-1120`, `39-7010`, `47-4090`, `51-2028`, `51-2090`, `53-1047` |

**Three crosswalk files in `seeds/soc_crosswalks/`:**

- `soc_2000_to_2010_crosswalk.xls`, sheet `sort by SOC 2000`. Header row is at spreadsheet row index 6 (0-based) with columns `2000 SOC code`, `2000 SOC title`, `2010 SOC code`, `2010 SOC title`; data starts at row 8. 860 data rows, 821 distinct 2000 codes, 840 distinct 2010 codes (ten code cells carry stray whitespace and must be stripped before matching); 29 SOC 2000 codes map to more than one 2010 code, 13 SOC 2010 codes come from more than one 2000 code. Read with `header=None`, strip, then keep rows whose first column matches `^\d\d-\d{4}$`.
- `soc_2010_to_2018_crosswalk.xlsx`, sheet `Sorted by 2010`. Header at row index 8: `2010 SOC Code`, `2010 SOC Title`, `2018 SOC Code`, `2018 SOC Title`; data from row 9. 900 rows, 840 distinct 2010 codes, 867 distinct 2018 codes; 42 SOC 2010 codes split, 31 SOC 2018 codes merge. Titles carry footnote markers like `(#)` and `(##)` that must be stripped before use.
- `oes_2019_hybrid_structure.xlsx`, sheet `OES2019 Hybrid`. Header at row index 5: `OES 2019 Estimates Code`, `OES 2019 Estimates Title`, `2018 SOC Code`, `2018 SOC Title`, `OES 2018 Estimates Code`, `OES 2018 Estimates Title`, `2010 SOC Code`, `2010 SOC Title`, `NOTES`; data from row 6. 868 rows, 790 distinct hybrid codes, 810 distinct OES-2018 codes. It gives two mappings this plan needs: hybrid code → SOC 2018 code(s) (for the 2019–20 files) and OES-2018 code → SOC 2010 code(s) (which resolves the 12 OEWS-only codes in the 2017–18 files, e.g. `13-1020` → `13-1021`, `13-1022`, `13-1023`).

**Residual pruning.** Building components from all crosswalk edges gives 775 components, 714 of them clean 1:1:1 chains, but one component of 39 nodes contains 17 SOC 2018 codes across major groups 11, 13 and 15 — Software Developers fused with Managers, All Other — because the SOC 2000 `15-1099 Computer specialists, all other` and SOC 2010 `15-1199 Computer Occupations, All Other` residuals fan out to many specific codes. Dropping every crosswalk edge whose two endpoint titles disagree on containing the phrase "all other" (case-insensitive) drops 61 edges and yields 836 components with a largest of 16 nodes (the seven SOC 2018 computer codes that genuinely descend from `15-1099` via the 2010 systems-analyst and support codes). Software Developers `15-1252` then sits in its own unit with `15-1132`+`15-1133` (SOC 2010) and `15-1031`+`15-1032` (SOC 2000). Pruned edges are recorded so the leakage is auditable. Residual-to-residual and specific-to-specific edges are always kept.

**Aggregate codes resolve, in order:** (1) the code is in the generation's SOC vocabulary → itself; (2) the code is in `seeds/oews_aggregate_codes.csv` for that generation → the listed member SOC codes; (3) the code ends in `0` (a SOC *broad* code used as a detailed row) → every vocabulary code sharing its first six characters (e.g. `13-1020` → `13-1021`, `13-1022`, `13-1023`); (4) otherwise raise `ValueError` naming the year and code. Hybrid-generation codes resolve to SOC 2018 codes through the hybrid file rather than the seed. The seed exists for the codes rules 1, 3 and the hybrid file cannot cover — the 2010–11 aggregates, `25-3097`/`25-3098`, and the 2021+ codes that neither the hybrid file nor the broad-group rule covers (`25-9045` Teaching Assistants, Except Postsecondary and `53-1047` First-Line Supervisors of Transportation and Material Moving Workers, Except Aircraft Cargo Handling Supervisors — the other three, `13-2020`, `31-1120`, `51-2090`, end in `0` and resolve by rule 3), plus `47-2111`.

**Unit identity.** A unit's id is `U-` followed by its smallest SOC 2018 member code (e.g. `U-15-1252`). Components with no SOC 2018 member (occupations discontinued before 2018) get `U-` followed by their smallest SOC 2010 or SOC 2000 code and a `-discontinued` suffix; they appear in the membership file but never in the trends file, which is anchored at 2022 like every other trend file.

**Unit completeness per year.** A unit's employment in a year is the sum of the OEWS rows assigned to it that year, but only if every SOC code the unit holds in that year's generation is covered by a present OEWS row; otherwise `NaN`. "Every SOC code" means every code of that generation that OEWS publishes at all — the vocabulary for completeness is the union, over all OEWS years of that generation, of the resolved SOC codes — so crosswalk codes OEWS never publishes do not mark units incomplete.

**Unit wage** is the employment-weighted mean of member rows' `A_MEDIAN`, ignoring members with a missing median.

**Unit model scores** (validation only) are the `TOT_EMP_25`-weighted mean of member 2022 OEWS codes' scores, where the members are the unit's rows for year `22` (the anchor code set that `merged_validation_df` is keyed on).

---

### Task 1: Crosswalk loaders

**Files:**
- Create: `harmonize_soc.py`
- Test: `tests/test_harmonize_soc.py`

**Interfaces:**
- Consumes: the three spreadsheets under `seeds/soc_crosswalks/` (read-only).
- Produces:
  - `CROSSWALK_DIR = "seeds/soc_crosswalks"`
  - `load_soc_2000_to_2010(crosswalk_dir: str = CROSSWALK_DIR) -> pd.DataFrame` with columns `from_code, from_title, to_code, to_title` (strings, titles stripped of `(#)`/`(##)` markers and surrounding whitespace, `*` removed).
  - `load_soc_2010_to_2018(crosswalk_dir: str = CROSSWALK_DIR) -> pd.DataFrame`, same columns.
  - `load_oews_hybrid_structure(crosswalk_dir: str = CROSSWALK_DIR) -> pd.DataFrame` with columns `hybrid_code, hybrid_title, soc_2018_code, soc_2018_title, oews_2018_code, oews_2018_title, soc_2010_code, soc_2010_title` (strings; `NaN` where the source cell is empty).
  - `clean_crosswalk_title(title) -> str`.
  - `is_residual_title(title) -> bool` — `True` when the cleaned title contains `all other` (case-insensitive).

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for harmonize_soc.py — SOC crosswalk loading, aggregate resolution, and unit construction."""

import pandas as pd
import pytest

from harmonize_soc import (
    clean_crosswalk_title,
    is_residual_title,
    load_oews_hybrid_structure,
    load_soc_2000_to_2010,
    load_soc_2010_to_2018,
)


class TestCrosswalkLoaders:
    def test_2010_to_2018_has_the_software_developer_merge(self):
        crosswalk_edges_df = load_soc_2010_to_2018()
        merged_into_developers = crosswalk_edges_df[crosswalk_edges_df["to_code"] == "15-1252"]
        assert sorted(merged_into_developers["from_code"]) == ["15-1132", "15-1133"]
        assert list(crosswalk_edges_df.columns) == ["from_code", "from_title", "to_code", "to_title"]

    def test_2010_to_2018_titles_are_cleaned(self):
        crosswalk_edges_df = load_soc_2010_to_2018()
        all_other_row = crosswalk_edges_df[crosswalk_edges_df["from_code"] == "15-1199"].iloc[0]
        assert all_other_row["from_title"] == "Computer Occupations, All Other"
        assert "(#" not in " ".join(crosswalk_edges_df["from_title"]) + " ".join(crosswalk_edges_df["to_title"])

    def test_2000_to_2010_has_the_systems_software_relabel(self):
        crosswalk_edges_df = load_soc_2000_to_2010()
        assert list(crosswalk_edges_df[crosswalk_edges_df["from_code"] == "15-1032"]["to_code"]) == ["15-1133"]
        assert crosswalk_edges_df["from_code"].str.match(r"^\d\d-\d{4}$").all()
        assert crosswalk_edges_df["to_code"].str.match(r"^\d\d-\d{4}$").all()

    def test_hybrid_structure_maps_software_developers_both_ways(self):
        hybrid_df = load_oews_hybrid_structure()
        developer_rows = hybrid_df[hybrid_df["hybrid_code"] == "15-1256"]
        assert set(developer_rows["soc_2018_code"]) == {"15-1252", "15-1253"}
        assert set(developer_rows["oews_2018_code"]) == {"15-1132", "15-1133"}
        buyers_rows = hybrid_df[hybrid_df["oews_2018_code"] == "13-1020"]
        assert set(buyers_rows["soc_2010_code"]) == {"13-1021", "13-1022", "13-1023"}


class TestTitleHelpers:
    def test_clean_strips_footnote_markers_and_asterisks(self):
        assert clean_crosswalk_title("Computer Occupations, All Other (#) ") == "Computer Occupations, All Other"
        assert clean_crosswalk_title("Registered Nurses*") == "Registered Nurses"

    def test_residual_detection_is_case_insensitive(self):
        assert is_residual_title("Computer Occupations, All Other (##)")
        assert is_residual_title("computer specialists, all other")
        assert not is_residual_title("Software Developers")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_harmonize_soc.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'harmonize_soc'`.

- [ ] **Step 3: Write the module**

```python
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
    return crosswalk_df[crosswalk_df[code_column].astype(str).str.match(SOC_CODE_PATTERN)].copy()


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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_harmonize_soc.py -q`
Expected: 6 passed. If a header-row offset is off by one for a file, print `pd.read_excel(path, header=None).head(12)` and correct `header_row_index` — the numbers in Background were verified on these files, but the loader must be checked against them, not assumed.

- [ ] **Step 5: Lint and commit**

Run: `.venv/bin/ruff check harmonize_soc.py tests/test_harmonize_soc.py && .venv/bin/ruff format harmonize_soc.py tests/test_harmonize_soc.py`

```bash
PATH="$PWD/.venv/bin:$PATH" git add harmonize_soc.py tests/test_harmonize_soc.py seeds/soc_crosswalks/
git commit -m "Add SOC crosswalk loaders for occupation-code harmonization

Parses the BLS SOC 2000→2010 and 2010→2018 crosswalks and the OEWS 2019
hybrid structure into edge tables with cleaned titles, the inputs for
harmonizing OEWS occupation codes across code generations. The three
spreadsheets are committed under seeds/soc_crosswalks/ because bls.gov
refuses non-browser requests and they are static reference data.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_017h8BcjpaxoxWqEDgwwsSqt"
```

---

### Task 2: OEWS aggregate-code resolution

**Files:**
- Create: `seeds/oews_aggregate_codes.csv`
- Modify: `harmonize_soc.py` (append)
- Modify: `CLAUDE.md` — add one sentence to the "Release Pipeline" section after the `seeds/cps_a19_panel.csv` paragraph describing `seeds/soc_crosswalks/` and `seeds/oews_aggregate_codes.csv` as committed reference data that the pipeline reads directly (no download step; bls.gov blocks plain HTTP and the files are static).
- Test: `tests/test_harmonize_soc.py` (append)

**Interfaces:**
- Consumes: `load_oews_hybrid_structure`, `load_soc_2000_to_2010`, `load_soc_2010_to_2018`; `analyze_bls.load_bls_year` and `analyze_bls.select_detailed_rows` (existing: `load_bls_year(zip_path) -> DataFrame | None` returns the national cross-industry frame; `select_detailed_rows(frame) -> DataFrame[OCC_CODE, OCC_TITLE, TOT_EMP, A_MEDIAN]`); `analyze_bls.YEAR_CONFIGS` (list of `(year_suffix, zip_path)`).
- Produces:
  - `GENERATION_BY_YEAR: dict[str, str]` mapping two-digit year suffix → one of `"soc2000"`, `"soc2010"`, `"hybrid"`, `"soc2018"` for `"05"`…`"25"`.
  - `AGGREGATE_CODES_PATH = "seeds/oews_aggregate_codes.csv"`
  - `load_aggregate_codes(path: str = AGGREGATE_CODES_PATH) -> pd.DataFrame` with columns `generation, oews_code, oews_title, member_soc_code, source`.
  - `soc_vocabularies(crosswalk_dir: str = CROSSWALK_DIR) -> dict[str, set[str]]` keyed `"soc2000"`, `"soc2010"`, `"soc2018"`: every code appearing on the relevant side of the crosswalks (SOC 2010 = union of the 2000→2010 `to_code` and 2010→2018 `from_code` sets), plus every code listed as a member in the aggregate seed for that generation.
  - `resolve_oews_codes(oews_codes_df: pd.DataFrame, generation: str, vocabularies: dict[str, set[str]], aggregate_codes_df: pd.DataFrame, hybrid_df: pd.DataFrame) -> pd.DataFrame` — input has columns `OCC_CODE, OCC_TITLE`; output has columns `oews_code, soc_code, resolution` where `resolution` is one of `"identity"`, `"hybrid"`, `"aggregate_seed"`, `"broad_group"`. One output row per (oews_code, soc_code) pair. Raises `ValueError` listing every unresolvable code. For `generation == "hybrid"`, `soc_code` is a SOC 2018 code from the hybrid file's `hybrid_code → soc_2018_code` rows and `resolution` is `"hybrid"` (identity is not used for hybrid even when the code equals a SOC 2018 code, so all hybrid rows resolve the same way).

The seed file's `member_soc_code` values must be codes in the generation's SOC vocabulary from the crosswalks (for `soc2018`, SOC 2018 codes; for `soc2010`, SOC 2010 codes; for `soc2000`, SOC 2000 codes). Derive the members from the OEWS titles and the crosswalk titles — for example, 2010's `15-1179 Information Security Analysts, Web Developers, and Computer Network Architects` is `15-1122`, `15-1134`, `15-1143`; `29-1111 Registered Nurses*` is `29-1141`; `31-1012 Nursing Aides, Orderlies, and Attendants*` is `31-1014`; `47-2111` is itself (`source` = `"missing_from_crosswalk"`, member `47-2111`, and Task 3 must treat a code present in one generation's vocabulary and the next generation's OEWS files under the same number as an identity edge). Where a 2010–11 residual like `29-2799 Health Technologists and Technicians, All Other*` corresponds to the SOC 2010 residual `29-2099` plus codes that OEWS published separately from 2012, list every SOC 2010 code that the 2012 file publishes but the 2011 file does not within that broad/minor group, and confirm by checking that the 2011 aggregate's `TOT_EMP` is within 25% of the 2012 sum of the listed members — record the reconciliation in the report file. The `source` column takes `"title"` for title-derived rows, `"missing_from_crosswalk"` for `47-2111`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_harmonize_soc.py`:

```python
import os

from analyze_bls import YEAR_CONFIGS, load_bls_year, select_detailed_rows
from harmonize_soc import (
    GENERATION_BY_YEAR,
    load_aggregate_codes,
    resolve_oews_codes,
    soc_vocabularies,
)

RAW_BLS_PRESENT = os.path.exists("data/raw/bls/oesm22nat.zip")


class TestGenerationMap:
    def test_every_year_in_year_configs_has_a_generation(self):
        for year_suffix, _ in YEAR_CONFIGS:
            assert year_suffix in GENERATION_BY_YEAR
        assert GENERATION_BY_YEAR["09"] == "soc2000"
        assert GENERATION_BY_YEAR["10"] == "soc2010"
        assert GENERATION_BY_YEAR["19"] == "hybrid"
        assert GENERATION_BY_YEAR["21"] == "soc2018"


class TestResolveOewsCodes:
    def _fixture(self):
        vocabularies = {
            "soc2010": {"13-1021", "13-1022", "13-1023", "15-1151", "15-1152", "29-1141"},
            "soc2018": {"15-1252", "15-1253"},
            "soc2000": set(),
        }
        aggregate_codes_df = pd.DataFrame(
            {
                "generation": ["soc2010"],
                "oews_code": ["29-1111"],
                "oews_title": ["Registered Nurses*"],
                "member_soc_code": ["29-1141"],
                "source": ["title"],
            }
        )
        hybrid_df = pd.DataFrame(
            {
                "hybrid_code": ["15-1256", "15-1256"],
                "hybrid_title": ["Software Developers and Software Quality Assurance Analysts and Testers"] * 2,
                "soc_2018_code": ["15-1252", "15-1253"],
                "soc_2018_title": ["Software Developers", "Software Quality Assurance Analysts and Testers"],
                "oews_2018_code": ["15-1132", "15-1133"],
                "oews_2018_title": ["Software Developers, Applications", "Software Developers, Systems Software"],
                "soc_2010_code": ["15-1132", "15-1133"],
                "soc_2010_title": ["Software Developers, Applications", "Software Developers, Systems Software"],
            }
        )
        return vocabularies, aggregate_codes_df, hybrid_df

    def test_identity_seed_and_broad_group_resolutions(self):
        vocabularies, aggregate_codes_df, hybrid_df = self._fixture()
        oews_codes_df = pd.DataFrame(
            {
                "OCC_CODE": ["29-1141", "29-1111", "13-1020"],
                "OCC_TITLE": ["Registered Nurses", "Registered Nurses*", "Buyers and Purchasing Agents"],
            }
        )
        resolved_df = resolve_oews_codes(oews_codes_df, "soc2010", vocabularies, aggregate_codes_df, hybrid_df)
        by_code = resolved_df.groupby("oews_code")
        assert list(by_code.get_group("29-1141")["soc_code"]) == ["29-1141"]
        assert list(by_code.get_group("29-1141")["resolution"]) == ["identity"]
        assert list(by_code.get_group("29-1111")["soc_code"]) == ["29-1141"]
        assert list(by_code.get_group("29-1111")["resolution"]) == ["aggregate_seed"]
        assert sorted(by_code.get_group("13-1020")["soc_code"]) == ["13-1021", "13-1022", "13-1023"]
        assert set(by_code.get_group("13-1020")["resolution"]) == {"broad_group"}

    def test_hybrid_codes_resolve_through_the_hybrid_file(self):
        vocabularies, aggregate_codes_df, hybrid_df = self._fixture()
        oews_codes_df = pd.DataFrame({"OCC_CODE": ["15-1256"], "OCC_TITLE": ["Software Developers and SQA"]})
        resolved_df = resolve_oews_codes(oews_codes_df, "hybrid", vocabularies, aggregate_codes_df, hybrid_df)
        assert sorted(resolved_df["soc_code"]) == ["15-1252", "15-1253"]
        assert set(resolved_df["resolution"]) == {"hybrid"}

    def test_unresolvable_code_raises_with_the_code_named(self):
        vocabularies, aggregate_codes_df, hybrid_df = self._fixture()
        oews_codes_df = pd.DataFrame({"OCC_CODE": ["99-9999"], "OCC_TITLE": ["Nothing"]})
        with pytest.raises(ValueError, match="99-9999"):
            resolve_oews_codes(oews_codes_df, "soc2010", vocabularies, aggregate_codes_df, hybrid_df)


@pytest.mark.skipif(not RAW_BLS_PRESENT, reason="raw OEWS zips not present")
class TestEveryOewsCodeResolves:
    def test_all_years_resolve_without_error(self):
        vocabularies = soc_vocabularies()
        aggregate_codes_df = load_aggregate_codes()
        hybrid_df = load_oews_hybrid_structure()
        for year_suffix, zip_path in YEAR_CONFIGS:
            detailed_rows_df = select_detailed_rows(load_bls_year(zip_path))
            resolved_df = resolve_oews_codes(
                detailed_rows_df[["OCC_CODE", "OCC_TITLE"]], GENERATION_BY_YEAR[year_suffix], vocabularies, aggregate_codes_df, hybrid_df
            )
            assert set(resolved_df["oews_code"]) == set(detailed_rows_df["OCC_CODE"]), year_suffix
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_harmonize_soc.py -q`
Expected: `ImportError` for the new names.

- [ ] **Step 3: Build the seed file**

Write a throwaway script under `$TMPDIR` (do not commit it) that, for each OEWS year, lists the detailed codes absent from that generation's crosswalk vocabulary along with their titles and `TOT_EMP` (the loop in the Background section's last table is the method: `select_detailed_rows(load_bls_year(zip_path))` filtered by `~OCC_CODE.isin(vocabulary)`), and for the `soc2010` era also lists which codes appear in the 2012 file but not the 2011 file. From those listings and the crosswalk titles, write `seeds/oews_aggregate_codes.csv` with header `generation,oews_code,oews_title,member_soc_code,source` and one row per member. Do not include codes that rule 3 (broad-group, code ending in `0`) or the hybrid file already resolves — the seed is only for the remainder. Record every reconciliation check (aggregate `TOT_EMP` in the last year it appears vs. the sum of its members' `TOT_EMP` in the first year they appear separately) in your report file with the two numbers and the percentage gap.

- [ ] **Step 4: Append the resolution code to `harmonize_soc.py`**

```python
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_harmonize_soc.py -q`
Expected: all pass, including `TestEveryOewsCodeResolves` (the raw zips are on disk in this environment; the test reads all 21 files and takes a couple of minutes). If it raises for a code, add that code to the seed with its members and re-run; every code in every year must resolve before this task is done.

- [ ] **Step 6: Update CLAUDE.md, lint, commit**

Add the `seeds/` sentence described under Files. Run ruff on `harmonize_soc.py` and `tests/test_harmonize_soc.py`.

```bash
PATH="$PWD/.venv/bin:$PATH" git add harmonize_soc.py tests/test_harmonize_soc.py seeds/oews_aggregate_codes.csv CLAUDE.md
git commit -m "Resolve OEWS-only aggregate codes to SOC codes

Every OEWS era publishes a handful of codes that are not SOC codes of that
era — broad-group codes used as detailed rows, OEWS combinations like
15-1179, and the 2019–20 hybrid aggregates. resolve_oews_codes maps each
to its member SOC codes through the vocabulary, the hybrid structure, a
broad-group rule, and a committed seed for the remainder, and fails loudly
on anything it cannot place. Verified across all 21 OEWS years on disk.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_017h8BcjpaxoxWqEDgwwsSqt"
```

---

### Task 3: Harmonized units

**Files:**
- Modify: `harmonize_soc.py` (append)
- Test: `tests/test_harmonize_soc.py` (append)

**Interfaces:**
- Consumes: everything Task 1 and Task 2 produce.
- Produces:
  - `HarmonizationResult` — a `dataclasses.dataclass` with fields `membership_df: pd.DataFrame` (columns `unit_id, year, oews_code, oews_title`), `unit_summary_df: pd.DataFrame` (columns `unit_id, n_soc_2018_codes, soc_2018_codes` (semicolon-joined), `major_groups` (semicolon-joined two-digit codes), `n_nodes`, `discontinued` (bool)), `pruned_edges_df: pd.DataFrame` (columns `from_generation, from_code, from_title, to_generation, to_code, to_title`), `completeness_df: pd.DataFrame` (columns `unit_id, year, complete` (bool)).
  - `build_harmonized_units(oews_codes_by_year: dict[str, pd.DataFrame], crosswalk_dir: str = CROSSWALK_DIR, aggregate_codes_path: str = AGGREGATE_CODES_PATH, prune_residual_edges: bool = True) -> HarmonizationResult`, where each value of `oews_codes_by_year` has columns `OCC_CODE, OCC_TITLE` (the detailed rows of that year).

Algorithm, in this order:

1. Load crosswalks, hybrid structure, vocabularies, aggregate seed. Resolve every year's codes with `resolve_oews_codes`, giving per year a table `oews_code → soc_code` in that year's SOC generation (hybrid years resolve to `soc2018`). Define `generation_of_resolved_codes(year)` = `"soc2018"` for hybrid years, else `GENERATION_BY_YEAR[year]`.
2. Nodes are `(generation, soc_code)` tuples. Union-find over:
   - every crosswalk row `(soc2000, from_code) — (soc2010, to_code)` and `(soc2010, from_code) — (soc2018, to_code)`, **except** rows where `is_residual_title(from_title) != is_residual_title(to_title)` when `prune_residual_edges` is true — those go to `pruned_edges_df` instead;
   - every hybrid-structure row `(soc2010, soc_2010_code) — (soc2018, soc_2018_code)` where both are present (these duplicate crosswalk rows for the most part; they are included so the OEWS-2018-code aggregates are linked, and they are subject to the same residual pruning using `soc_2010_title` and `soc_2018_title`);
   - every resolved OEWS aggregate (a code resolving to more than one `soc_code`): union all of its member nodes with each other, so an OEWS row that reports several SOC codes together never straddles two units;
   - identity links for codes absent from the crosswalks: for each pair of consecutive generations (`soc2000→soc2010`, `soc2010→soc2018`), a code that is in both vocabularies but appears in no crosswalk row for that pair is linked to itself (this is the `47-2111` case and any like it).
3. Every node in any vocabulary participates, even if isolated (its own unit).
4. `unit_id`: `"U-" + min(soc2018 codes in component)`; if none, `"U-" + min(other codes) + "-discontinued"`.
5. `membership_df`: for each year and each OEWS row, the unit of its resolved node(s) (all of a row's resolved nodes are in one unit by construction — assert it).
6. `completeness_df`: for each unit and year, `complete` is true when the set of `soc_code`s of that year's resolved generation in the component, intersected with the *published vocabulary* of that generation (the union over all OEWS years of that generation of their resolved `soc_code`s), is a subset of the resolved `soc_code`s of the OEWS rows present that year.
7. `unit_summary_df` as specified; `major_groups` are the distinct first two characters of all member codes across generations.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_harmonize_soc.py`:

```python
from harmonize_soc import HarmonizationResult, build_harmonized_units


class TestBuildHarmonizedUnits:
    """
    Synthetic three-generation world exercising a relabel, a merge, a split
    through a residual, an OEWS aggregate, and a discontinued code.
    """

    def _write_fixture_crosswalks(self, tmp_path):
        crosswalk_dir = tmp_path / "crosswalks"
        crosswalk_dir.mkdir()
        padding_rows = [[None] * 4] * 8
        soc_2000_to_2010 = pd.DataFrame(
            padding_rows
            + [["2000 SOC code", "2000 SOC title", "2010 SOC code", "2010 SOC title"], [None] * 4]
            + [
                ["15-1031", "Software engineers, applications", "15-1132", "Software Developers, Applications"],
                ["15-1099", "Computer specialists, all other", "15-1132", "Software Developers, Applications"],
                ["15-1099", "Computer specialists, all other", "15-1199", "Computer Occupations, All Other"],
                ["11-9011", "Farm managers", "11-9013", "Farmers, Ranchers, and Other Agricultural Managers"],
                ["11-9012", "Farmers and ranchers", "11-9013", "Farmers, Ranchers, and Other Agricultural Managers"],
                ["43-0001", "Discontinued clerks", "43-0002", "Discontinued clerks"],
            ]
        )
        soc_2000_to_2010.to_excel(crosswalk_dir / "soc_2000_to_2010_crosswalk.xls", header=False, index=False, engine="openpyxl")
        soc_2010_to_2018 = pd.DataFrame(
            [[None] * 4] * 9
            + [["2010 SOC Code", "2010 SOC Title", "2018 SOC Code", "2018 SOC Title"]]
            + [
                ["15-1132", "Software Developers, Applications", "15-1252", "Software Developers"],
                ["15-1199", "Computer Occupations, All Other (#)", "15-1299", "Computer Occupations, All Other (##)"],
                [
                    "11-9013",
                    "Farmers, Ranchers, and Other Agricultural Managers",
                    "11-9013",
                    "Farmers, Ranchers, and Other Agricultural Managers",
                ],
                ["29-1141", "Registered Nurses", "29-1141", "Registered Nurses"],
            ]
        )
        soc_2010_to_2018.to_excel(crosswalk_dir / "soc_2010_to_2018_crosswalk.xlsx", header=False, index=False)
        hybrid = pd.DataFrame(
            [[None] * 9] * 6
            + [
                [
                    "15-1252",
                    "Software Developers",
                    "15-1252",
                    "Software Developers",
                    "15-1132",
                    "Software Developers, Applications",
                    "15-1132",
                    "Software Developers, Applications",
                    None,
                ],
                [
                    "15-1299",
                    "Computer Occupations, All Other",
                    "15-1299",
                    "Computer Occupations, All Other",
                    "15-1199",
                    "Computer Occupations, All Other",
                    "15-1199",
                    "Computer Occupations, All Other",
                    None,
                ],
                [
                    "11-9013",
                    "Farmers, Ranchers, and Other Agricultural Managers",
                    "11-9013",
                    "Farmers, Ranchers, and Other Agricultural Managers",
                    "11-9013",
                    "Farmers, Ranchers, and Other Agricultural Managers",
                    "11-9013",
                    "Farmers, Ranchers, and Other Agricultural Managers",
                    None,
                ],
                [
                    "29-1141",
                    "Registered Nurses",
                    "29-1141",
                    "Registered Nurses",
                    "29-1141",
                    "Registered Nurses",
                    "29-1141",
                    "Registered Nurses",
                    None,
                ],
            ]
        )
        with pd.ExcelWriter(crosswalk_dir / "oes_2019_hybrid_structure.xlsx") as writer:
            hybrid.to_excel(writer, sheet_name="OES2019 Hybrid", header=False, index=False)
        aggregate_path = tmp_path / "oews_aggregate_codes.csv"
        pd.DataFrame(
            {
                "generation": ["soc2010"],
                "oews_code": ["29-1111"],
                "oews_title": ["Registered Nurses*"],
                "member_soc_code": ["29-1141"],
                "source": ["title"],
            }
        ).to_csv(aggregate_path, index=False)
        return str(crosswalk_dir), str(aggregate_path)

    def _oews_codes_by_year(self):
        return {
            "09": pd.DataFrame(
                {"OCC_CODE": ["15-1031", "15-1099", "11-9011", "11-9012", "43-0001"], "OCC_TITLE": ["a", "b", "c", "d", "e"]}
            ),
            "10": pd.DataFrame(
                {"OCC_CODE": ["15-1132", "15-1199", "11-9013", "29-1111", "43-0002"], "OCC_TITLE": ["a", "b", "c", "d", "e"]}
            ),
            "18": pd.DataFrame({"OCC_CODE": ["15-1132", "15-1199", "11-9013", "29-1141"], "OCC_TITLE": ["a", "b", "c", "d"]}),
            "19": pd.DataFrame({"OCC_CODE": ["15-1252", "15-1299", "11-9013", "29-1141"], "OCC_TITLE": ["a", "b", "c", "d"]}),
            "22": pd.DataFrame({"OCC_CODE": ["15-1252", "15-1299", "11-9013", "29-1141"], "OCC_TITLE": ["a", "b", "c", "d"]}),
        }

    def test_relabel_chain_forms_one_unit_and_residual_edge_is_pruned(self, tmp_path):
        crosswalk_dir, aggregate_path = self._write_fixture_crosswalks(tmp_path)
        result = build_harmonized_units(self._oews_codes_by_year(), crosswalk_dir, aggregate_path)
        assert isinstance(result, HarmonizationResult)
        developers_2009 = result.membership_df.query("year == '09' and oews_code == '15-1031'")["unit_id"].iloc[0]
        developers_2022 = result.membership_df.query("year == '22' and oews_code == '15-1252'")["unit_id"].iloc[0]
        assert developers_2009 == developers_2022 == "U-15-1252"
        residual_2009 = result.membership_df.query("year == '09' and oews_code == '15-1099'")["unit_id"].iloc[0]
        assert residual_2009 == "U-15-1299"
        assert len(result.pruned_edges_df) == 1
        assert result.pruned_edges_df.iloc[0]["from_code"] == "15-1099"
        assert result.pruned_edges_df.iloc[0]["to_code"] == "15-1132"

    def test_merge_and_aggregate_seed_land_in_one_unit(self, tmp_path):
        crosswalk_dir, aggregate_path = self._write_fixture_crosswalks(tmp_path)
        result = build_harmonized_units(self._oews_codes_by_year(), crosswalk_dir, aggregate_path)
        farm_units = set(result.membership_df.query("year == '09' and oews_code in ['11-9011', '11-9012']")["unit_id"])
        assert farm_units == {"U-11-9013"}
        nurses_2010 = result.membership_df.query("year == '10' and oews_code == '29-1111'")["unit_id"].iloc[0]
        assert nurses_2010 == "U-29-1141"

    def test_discontinued_codes_get_a_discontinued_unit(self, tmp_path):
        crosswalk_dir, aggregate_path = self._write_fixture_crosswalks(tmp_path)
        result = build_harmonized_units(self._oews_codes_by_year(), crosswalk_dir, aggregate_path)
        clerks_unit = result.membership_df.query("year == '10' and oews_code == '43-0002'")["unit_id"].iloc[0]
        assert clerks_unit == "U-43-0001-discontinued"
        assert result.unit_summary_df.set_index("unit_id").loc[clerks_unit, "discontinued"]

    def test_completeness_marks_years_missing_a_member(self, tmp_path):
        crosswalk_dir, aggregate_path = self._write_fixture_crosswalks(tmp_path)
        oews_codes_by_year = self._oews_codes_by_year()
        oews_codes_by_year["18"] = oews_codes_by_year["18"][oews_codes_by_year["18"]["OCC_CODE"] != "11-9013"]
        result = build_harmonized_units(oews_codes_by_year, crosswalk_dir, aggregate_path)
        completeness = result.completeness_df.set_index(["unit_id", "year"])["complete"]
        assert not completeness.loc[("U-11-9013", "18")]
        assert completeness.loc[("U-11-9013", "10")]
        assert completeness.loc[("U-15-1252", "09")]

    def test_no_pruning_fuses_developers_with_the_residual(self, tmp_path):
        crosswalk_dir, aggregate_path = self._write_fixture_crosswalks(tmp_path)
        result = build_harmonized_units(self._oews_codes_by_year(), crosswalk_dir, aggregate_path, prune_residual_edges=False)
        developers = result.membership_df.query("year == '22' and oews_code == '15-1252'")["unit_id"].iloc[0]
        residual = result.membership_df.query("year == '22' and oews_code == '15-1299'")["unit_id"].iloc[0]
        assert developers == residual
        assert result.pruned_edges_df.empty
```

Note on the `.xls` fixture: `pd.DataFrame.to_excel` cannot write legacy `.xls`. Make `load_soc_2000_to_2010` tolerant of this by trying the `.xls` path first and falling back to `.xlsx` if the `.xls` file does not exist (`os.path.exists`), and have the fixture write `soc_2000_to_2010_crosswalk.xlsx`. Adjust the fixture line accordingly (drop `engine="openpyxl"`, use the `.xlsx` name). The real seed stays `.xls`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_harmonize_soc.py -q -k Build`
Expected: `ImportError` for `HarmonizationResult`.

- [ ] **Step 3: Implement**

Append to `harmonize_soc.py`. The union-find is small enough to write inline:

```python
# ── Harmonized units ──────────────────────────────────────────────────────────

from dataclasses import dataclass  # noqa: E402 — keep imports at top in the real file; shown here for locality


class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[tuple[str, str], tuple[str, str]] = {}

    def find(self, node: tuple[str, str]) -> tuple[str, str]:
        self._parent.setdefault(node, node)
        while self._parent[node] != node:
            self._parent[node] = self._parent[self._parent[node]]
            node = self._parent[node]
        return node

    def union(self, left: tuple[str, str], right: tuple[str, str]) -> None:
        self._parent[self.find(left)] = self.find(right)

    def components(self) -> dict[tuple[str, str], set[tuple[str, str]]]:
        grouped: dict[tuple[str, str], set[tuple[str, str]]] = {}
        for node in list(self._parent):
            grouped.setdefault(self.find(node), set()).add(node)
        return grouped


@dataclass
class HarmonizationResult:
    membership_df: pd.DataFrame
    unit_summary_df: pd.DataFrame
    pruned_edges_df: pd.DataFrame
    completeness_df: pd.DataFrame


def resolved_generation(year_suffix: str) -> str:
    """The SOC generation an OEWS year's codes resolve into (hybrid years resolve to SOC 2018)."""
    generation = GENERATION_BY_YEAR[year_suffix]
    return "soc2018" if generation == "hybrid" else generation


def _unit_id_for(component: set[tuple[str, str]]) -> str:
    soc_2018_codes = sorted(code for generation, code in component if generation == "soc2018")
    if soc_2018_codes:
        return f"U-{soc_2018_codes[0]}"
    return f"U-{min(code for _, code in component)}-discontinued"
```

Then `build_harmonized_units` following the seven numbered steps under Interfaces. Put the `dataclass` import at the top of the module with the others. Move the `_UnionFind` class and `HarmonizationResult` above the function that uses them. Pruned-edge rows carry the generation pair and both titles. Assert, while building `membership_df`, that all resolved nodes of one OEWS row share a unit; raise `AssertionError` with the offending code if not.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_harmonize_soc.py -q`
Expected: all pass.

- [ ] **Step 5: Real-data smoke check (do not commit the script)**

In `$TMPDIR`, run `build_harmonized_units` over the real files (`{year: select_detailed_rows(load_bls_year(zip_path))[["OCC_CODE", "OCC_TITLE"]] for year, zip_path in YEAR_CONFIGS}`) and record in your report: number of units, number of discontinued units, number of pruned edges, the five largest units by `n_nodes` with their `soc_2018_codes`, the number of units whose `major_groups` has more than one entry, and the share of (unit, year) pairs that are complete for years `05`, `10`, `12`, `17`, `19`, `21`, `22`. Expected magnitudes from the controller's exploration: about 830–840 units, 61 pruned edges, largest unit 16 nodes holding seven computer SOC 2018 codes, and every 2022 code in a complete unit. If `U-15-1252` does not contain exactly `15-1031`, `15-1032`, `15-1132`, `15-1133`, `15-1256` (hybrid years) and `15-1252` across years, something is wrong — say so in the report rather than adjusting the tests.

- [ ] **Step 6: Lint and commit**

```bash
PATH="$PWD/.venv/bin:$PATH" git add harmonize_soc.py tests/test_harmonize_soc.py
git commit -m "Build harmonized occupation units from SOC crosswalk components

Connected components over (generation, code) nodes joined by crosswalk,
hybrid-structure and aggregate-membership edges, after pruning edges that
run through residual 'All Other' categories — those otherwise fuse the
whole computer block with management and business residuals into one
39-node unit. Records membership per year, per-year completeness, and the
pruned edges for audit.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_017h8BcjpaxoxWqEDgwwsSqt"
```

---

### Task 4: Unit-level trend series

**Files:**
- Modify: `harmonize_soc.py` (append `build_harmonized_trends`)
- Modify: `analyze_bls.py` — `main()` (after the sector file is written) and the module docstring's Outputs list
- Modify: `CLAUDE.md` — three new rows in the "Data files" table
- Test: `tests/test_harmonize_soc.py` (append)

**Interfaces:**
- Consumes: `HarmonizationResult`; `analyze_bls.attach_growth_columns(trend_df, available_years) -> DataFrame` (existing; adds `hist_emp_growth_*`, `emp_growth_*`, `*_composite`, `*_pre_ai` columns from `TOT_EMP_{yy}`/`A_MEDIAN_{yy}` columns); `analyze_bls.COMPOSITE_ANCHOR_YEAR == "22"`.
- Produces:
  - `build_harmonized_trends(year_frames: dict[str, pd.DataFrame], harmonization: HarmonizationResult, available_years: list[str]) -> pd.DataFrame` — `year_frames[yy]` has columns `OCC_CODE, OCC_TITLE, TOT_EMP, A_MEDIAN`. Output: one row per unit that has at least one member in year `COMPOSITE_ANCHOR_YEAR`, columns `unit_id, soc_2018_codes, major_groups, TOT_EMP_{yy}, A_MEDIAN_{yy}` for every year, then the growth columns from `attach_growth_columns`. `TOT_EMP_{yy}` is the member sum when the unit is complete that year, else `NaN`; `A_MEDIAN_{yy}` is the `TOT_EMP`-weighted mean of member `A_MEDIAN` over members with a non-null median, `NaN` if none or if incomplete.
  - `boundary_continuity_report(harmonized_trends_df: pd.DataFrame) -> pd.DataFrame` — one row per year-over-year period (`period`, `n_units`, `share_abs_growth_over_25pct`), computed on the unit `hist_emp_growth_*`/`emp_growth_*` columns. Printed by `analyze_bls.main` with the three revision boundaries (`09_10`, `18_19`, `20_21`) marked, so a reader can see whether unit growth at the boundaries looks like an ordinary year.
  - Files written by `analyze_bls.main`: `data/output/soc_harmonization_units.csv` (the membership table joined with `unit_summary_df` columns), `data/output/soc_harmonization_pruned_edges.csv`, `data/output/bls_harmonized_trends.csv`.

- [ ] **Step 1: Write the failing tests**

```python
from harmonize_soc import boundary_continuity_report, build_harmonized_trends


class TestBuildHarmonizedTrends:
    def _harmonization(self):
        membership_df = pd.DataFrame(
            {
                "unit_id": ["U-15-1252", "U-15-1252", "U-15-1252", "U-15-1252", "U-15-1252", "U-11-9013", "U-11-9013"],
                "year": ["21", "21", "22", "23", "23", "22", "23"],
                "oews_code": ["15-1132", "15-1133", "15-1252", "15-1252", "15-1253", "11-9013", "11-9013"],
                "oews_title": ["a", "b", "c", "c", "d", "e", "e"],
            }
        )
        completeness_df = pd.DataFrame(
            {
                "unit_id": ["U-15-1252", "U-15-1252", "U-15-1252", "U-11-9013", "U-11-9013", "U-11-9013"],
                "year": ["21", "22", "23", "21", "22", "23"],
                "complete": [True, True, True, False, True, True],
            }
        )
        unit_summary_df = pd.DataFrame(
            {
                "unit_id": ["U-15-1252", "U-11-9013"],
                "n_soc_2018_codes": [2, 1],
                "soc_2018_codes": ["15-1252;15-1253", "11-9013"],
                "major_groups": ["15", "11"],
                "n_nodes": [6, 3],
                "discontinued": [False, False],
            }
        )
        return HarmonizationResult(membership_df, unit_summary_df, pd.DataFrame(), completeness_df)

    def _year_frames(self):
        return {
            "21": pd.DataFrame(
                {"OCC_CODE": ["15-1132", "15-1133"], "OCC_TITLE": ["a", "b"], "TOT_EMP": [600.0, 400.0], "A_MEDIAN": [100.0, 120.0]}
            ),
            "22": pd.DataFrame(
                {"OCC_CODE": ["15-1252", "11-9013"], "OCC_TITLE": ["c", "e"], "TOT_EMP": [1100.0, 50.0], "A_MEDIAN": [110.0, 60.0]}
            ),
            "23": pd.DataFrame(
                {
                    "OCC_CODE": ["15-1252", "15-1253", "11-9013"],
                    "OCC_TITLE": ["c", "d", "e"],
                    "TOT_EMP": [1000.0, 210.0, 55.0],
                    "A_MEDIAN": [115.0, None, 62.0],
                }
            ),
        }

    def test_unit_employment_sums_members_and_growth_columns_follow(self):
        trends_df = build_harmonized_trends(self._year_frames(), self._harmonization(), ["21", "22", "23"]).set_index("unit_id")
        assert trends_df.loc["U-15-1252", "TOT_EMP_21"] == 1000.0
        assert trends_df.loc["U-15-1252", "TOT_EMP_23"] == 1210.0
        assert trends_df.loc["U-15-1252", "emp_growth_22_23"] == pytest.approx(0.1)
        assert trends_df.loc["U-15-1252", "hist_emp_growth_21_22"] == pytest.approx(0.1)

    def test_unit_wage_is_employment_weighted_over_members_with_a_median(self):
        trends_df = build_harmonized_trends(self._year_frames(), self._harmonization(), ["21", "22", "23"]).set_index("unit_id")
        assert trends_df.loc["U-15-1252", "A_MEDIAN_21"] == pytest.approx(108.0)
        assert trends_df.loc["U-15-1252", "A_MEDIAN_23"] == pytest.approx(115.0)

    def test_incomplete_year_is_nan(self):
        trends_df = build_harmonized_trends(self._year_frames(), self._harmonization(), ["21", "22", "23"]).set_index("unit_id")
        assert pd.isna(trends_df.loc["U-11-9013", "TOT_EMP_21"])
        assert pd.isna(trends_df.loc["U-11-9013", "hist_emp_growth_21_22"])
        assert trends_df.loc["U-11-9013", "emp_growth_22_23"] == pytest.approx(0.1)

    def test_units_without_an_anchor_year_member_are_dropped(self):
        harmonization = self._harmonization()
        harmonization.membership_df = harmonization.membership_df[harmonization.membership_df["unit_id"] != "U-11-9013"]
        trends_df = build_harmonized_trends(self._year_frames(), harmonization, ["21", "22", "23"])
        assert list(trends_df["unit_id"]) == ["U-15-1252"]

    def test_boundary_report_counts_large_moves(self):
        trends_df = pd.DataFrame(
            {"unit_id": ["a", "b", "c"], "hist_emp_growth_18_19": [0.5, 0.01, None], "emp_growth_22_23": [0.02, -0.3, 0.1]}
        )
        report_df = boundary_continuity_report(trends_df).set_index("period")
        assert report_df.loc["18_19", "n_units"] == 2
        assert report_df.loc["18_19", "share_abs_growth_over_25pct"] == pytest.approx(0.5)
        assert report_df.loc["22_23", "share_abs_growth_over_25pct"] == pytest.approx(1 / 3)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_harmonize_soc.py -q -k "Trends or boundary"`
Expected: `ImportError`.

- [ ] **Step 3: Implement**

`build_harmonized_trends`: for each year, merge `year_frames[year]` with `membership_df[membership_df.year == year]` on `OCC_CODE == oews_code`; group by `unit_id` to get `TOT_EMP` sum and the weighted median; set both to `NaN` where `completeness_df` says incomplete; pivot to wide `TOT_EMP_{yy}`/`A_MEDIAN_{yy}`; keep units present in `membership_df` for `COMPOSITE_ANCHOR_YEAR`; join `soc_2018_codes` and `major_groups` from `unit_summary_df`; then `attach_growth_columns(trend_df, available_years)` (import it from `analyze_bls` inside `harmonize_soc.py` — `analyze_bls` must not import `harmonize_soc` at module level to avoid a cycle; `analyze_bls.main` imports `harmonize_soc` locally inside the function).

`boundary_continuity_report`: for every column matching `hist_emp_growth_\d\d_\d\d` or `emp_growth_\d\d_\d\d`, `n_units` = non-null count and `share_abs_growth_over_25pct` = mean of `abs(growth) > 0.25` over non-null rows; `period` is the `yy_yy` key.

In `analyze_bls.main`, after the sector file is written:

```python
    # Harmonized occupation units: consistent series across SOC revisions.
    from harmonize_soc import boundary_continuity_report, build_harmonized_trends, build_harmonized_units

    oews_codes_by_year = {year_suffix: year_dataframes[year_suffix][["OCC_CODE", "OCC_TITLE"]] for year_suffix in available_years}
    harmonization = build_harmonized_units(oews_codes_by_year)
    harmonization.membership_df.merge(harmonization.unit_summary_df, on="unit_id", how="left").to_csv(
        "data/output/soc_harmonization_units.csv", index=False
    )
    harmonization.pruned_edges_df.to_csv("data/output/soc_harmonization_pruned_edges.csv", index=False)
    harmonized_trends_df = build_harmonized_trends(year_dataframes, harmonization, available_years)
    harmonized_trends_df.to_csv("data/output/bls_harmonized_trends.csv", index=False)
    print(
        f"Saved data/output/bls_harmonized_trends.csv ({len(harmonized_trends_df)} units; "
        f"{len(harmonization.pruned_edges_df)} residual crosswalk edges pruned)"
    )
    print("\n── Unit growth continuity across SOC revision boundaries (share of units moving >25% in a year) ──")
    for _, report_row in boundary_continuity_report(harmonized_trends_df).iterrows():
        boundary_flag = "  ← SOC revision" if report_row["period"] in ("09_10", "18_19", "20_21") else ""
        print(f"  {report_row['period']}  n={int(report_row['n_units']):4d}  {report_row['share_abs_growth_over_25pct']:.1%}{boundary_flag}")
```

`year_dataframes` there holds the detailed rows per year already (`select_detailed_rows` output), which is what `build_harmonized_trends` consumes.

- [ ] **Step 4: Run tests, then the analyze stage**

Run: `.venv/bin/python -m pytest tests/ -q` — expected all pass.
Run: `.venv/bin/python -u main.py analyze 2>&1 | grep -v -i matplotlib | tail -40` — expected: the three new files exist, `bls_trends.csv` and `bls_sector_trends.csv` are byte-identical to before (check with `git stash`-free method: `md5sum` them before and after the run; they are gitignored outputs, so record the before-hashes in your report first). Record the continuity table in the report.

- [ ] **Step 5: Docs, lint, commit**

Add the three output rows to `CLAUDE.md` (Data files table) and update the `analyze_bls.py` module docstring Outputs list. Rows:

```
| `bls_harmonized_trends.csv` | `analyze_bls.py` (via `harmonize_soc.py`) | Occupation-level employment/wage trends 2005–2025 on harmonized units — connected components of the SOC 2000→2010→2018 crosswalks (plus the OEWS 2019–20 hybrid), with residual "All Other" edges pruned. Same column layout as `bls_trends.csv`, keyed by `unit_id`. A unit's year is NaN when any member code OEWS publishes was absent. Used for the occupation-level historical validation. |
| `soc_harmonization_units.csv` | `analyze_bls.py` (via `harmonize_soc.py`) | Which OEWS code in which year belongs to which harmonized unit, with the unit's SOC 2018 members and major groups. |
| `soc_harmonization_pruned_edges.csv` | `analyze_bls.py` (via `harmonize_soc.py`) | Crosswalk edges dropped because they link a residual "All Other" category to a specific occupation. The leakage the harmonization accepts, listed for audit. |
```

```bash
PATH="$PWD/.venv/bin:$PATH" git add harmonize_soc.py analyze_bls.py tests/test_harmonize_soc.py CLAUDE.md
git commit -m "Write unit-level BLS trends on harmonized occupation codes

bls_harmonized_trends.csv sums each harmonized unit's OEWS rows per year,
NaN where a member OEWS publishes was absent, and carries the same growth
columns as bls_trends.csv. A continuity table printed during analyze shows
whether unit growth at the 2009→10, 2018→19 and 2020→21 code boundaries
looks like an ordinary year.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_017h8BcjpaxoxWqEDgwwsSqt"
```

---

### Task 5: Occupation-level historical validation on units

**Files:**
- Modify: `validate_bls.py` — `plot_model_signal_over_time_occupation` (around line 641) and its call in `main` (around line 1386); add `load_harmonized_trends` and `build_unit_scores` near `load_sector_growth_table`.
- Modify: `docs/charts/model_signal_over_time_occupation.md` — replace the "Survivorship note" section.
- Modify: `CLAUDE.md` — the `model_signal_over_time_occupation.png` row.
- Test: `tests/test_pipeline.py` (append a class for `build_unit_scores`)

**Interfaces:**
- Consumes: `data/output/bls_harmonized_trends.csv` and `data/output/soc_harmonization_units.csv` from Task 4.
- Produces:
  - `load_harmonized_trends(path: str = "data/output/bls_harmonized_trends.csv") -> pd.DataFrame | None` (None with a printed warning if absent).
  - `load_unit_membership(path: str = "data/output/soc_harmonization_units.csv") -> pd.DataFrame | None`.
  - `build_unit_scores(merged_validation_df: pd.DataFrame, unit_membership_df: pd.DataFrame, employment_col: str, score_cols: list[str], anchor_year: str = "22") -> pd.DataFrame` — one row per unit with a column per score: the `employment_col`-weighted mean over the unit's anchor-year OEWS codes that appear in `merged_validation_df["OCC_CODE"]`. Units with no scored member are omitted. `merged_validation_df` rows carry `OCC_CODE`, `employment_col`, and the score columns; missing scores are ignored in the weighted mean (weights renormalised over non-missing).
  - `plot_model_signal_over_time_occupation(..., harmonized_trends_df: pd.DataFrame | None = None, unit_membership_df: pd.DataFrame | None = None)` — when both are given, every period's correlation is computed over units: scores from `build_unit_scores` (for `occupation_exposure`, `net_employment_change`, and `observed_exposure` when present), growth from `harmonized_trends_df`; the chart title says "harmonized SOC units" and the per-period `n` annotation counts units. When either is `None`, behaviour is exactly as today.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pipeline.py`:

```python
from validate_bls import build_unit_scores


class TestBuildUnitScores:
    def test_scores_are_employment_weighted_over_anchor_year_members(self):
        merged_validation_df = pd.DataFrame(
            {
                "OCC_CODE": ["15-1252", "15-1253", "11-9013"],
                "TOT_EMP_25": [1000.0, 200.0, 50.0],
                "occupation_exposure": [0.10, 0.40, 0.02],
                "net_employment_change": [0.15, None, -0.05],
            }
        )
        unit_membership_df = pd.DataFrame(
            {
                "unit_id": ["U-15-1252", "U-15-1252", "U-15-1252", "U-11-9013", "U-99-0000"],
                "year": ["22", "22", "21", "22", "22"],
                "oews_code": ["15-1252", "15-1253", "15-1132", "11-9013", "99-0000"],
            }
        )
        unit_scores_df = build_unit_scores(
            merged_validation_df, unit_membership_df, "TOT_EMP_25", ["occupation_exposure", "net_employment_change"]
        ).set_index("unit_id")
        assert unit_scores_df.loc["U-15-1252", "occupation_exposure"] == pytest.approx(0.15)
        assert unit_scores_df.loc["U-15-1252", "net_employment_change"] == pytest.approx(0.15)
        assert unit_scores_df.loc["U-11-9013", "occupation_exposure"] == pytest.approx(0.02)
        assert "U-99-0000" not in unit_scores_df.index
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/python -m pytest tests/test_pipeline.py -q -k UnitScores` → `ImportError`.

- [ ] **Step 3: Implement**

In `validate_bls.py`, next to `load_sector_growth_table`:

```python
def load_harmonized_trends(path: str = "data/output/bls_harmonized_trends.csv") -> pd.DataFrame | None:
    """Unit-level trend series from analyze_bls.py; None (with a warning) if the analyze stage did not write it."""
    if not os.path.exists(path):
        print(f"Warning: {path} not found — occupation-level history will use surviving 2022 codes.")
        return None
    return pd.read_csv(path, dtype={"unit_id": str})


def load_unit_membership(path: str = "data/output/soc_harmonization_units.csv") -> pd.DataFrame | None:
    """Per-year unit membership from analyze_bls.py; None if absent."""
    if not os.path.exists(path):
        return None
    return pd.read_csv(path, dtype={"unit_id": str, "year": str, "oews_code": str})


def build_unit_scores(
    merged_validation_df: pd.DataFrame,
    unit_membership_df: pd.DataFrame,
    employment_col: str,
    score_cols: list[str],
    anchor_year: str = "22",
) -> pd.DataFrame:
    """
    Employment-weighted mean of each score over a unit's anchor-year OEWS codes.

    merged_validation_df is keyed on the 2022 OEWS code set, so a unit's score
    is the weighted mean over its year-22 members that were scored. Weights are
    renormalised over members with a non-missing score, and units with no scored
    member are omitted.
    """
    anchor_members_df = unit_membership_df[unit_membership_df["year"] == anchor_year][["unit_id", "oews_code"]]
    scored_members_df = anchor_members_df.merge(
        merged_validation_df[["OCC_CODE", employment_col] + score_cols], left_on="oews_code", right_on="OCC_CODE", how="inner"
    )
    unit_score_rows = []
    for unit_id, member_rows_df in scored_members_df.groupby("unit_id"):
        unit_score_row: dict[str, float | str] = {"unit_id": unit_id}
        for score_col in score_cols:
            valid_rows_df = member_rows_df.dropna(subset=[score_col, employment_col])
            weight_total = valid_rows_df[employment_col].sum()
            unit_score_row[score_col] = (
                (valid_rows_df[score_col] * valid_rows_df[employment_col]).sum() / weight_total if weight_total > 0 else float("nan")
            )
        unit_score_rows.append(unit_score_row)
    return pd.DataFrame(unit_score_rows, columns=["unit_id"] + score_cols)
```

In `plot_model_signal_over_time_occupation`, after `base_df` is built, add:

```python
use_units = harmonized_trends_df is not None and unit_membership_df is not None
if use_units:
    score_cols_present = [
        score_col for score_col in ("occupation_exposure", "net_employment_change", "observed_exposure") if score_col in base_df.columns
    ]
    unit_scores_df = build_unit_scores(base_df, unit_membership_df, latest_emp_col, score_cols_present)
    growth_cols_present = [column for column in harmonized_trends_df.columns if "emp_growth_" in column]
    base_df = unit_scores_df.merge(harmonized_trends_df[["unit_id"] + growth_cols_present], on="unit_id", how="inner")
```

where `latest_emp_col` is derived the same way `plot_model_signal_over_time` derives it (`sorted(c for c in merged_validation_df.columns if c.startswith("TOT_EMP_"))[-1]`), computed before `base_df` is replaced. `all_period_cols` must then be recomputed from `base_df` columns when `use_units` (the unit file carries the same column names, so the existing list is valid — but compute it from `base_df` to be safe). Title suffix: append `\n(harmonized SOC units — consistent occupation definitions 2005→2025)` when `use_units`; the existing docstring sentence about survivorship becomes "n counts harmonized units when bls_harmonized_trends.csv is present, else surviving 2022 codes." In `main`, load both files once next to `sector_growth_df` and pass them through.

- [ ] **Step 4: Run tests and the validate stage**

Run: `.venv/bin/python -m pytest tests/ -q` — all pass.
Run: `.venv/bin/python main.py validate 2>&1 | grep -v -i matplotlib > $TMPDIR/validate.log; echo EXIT $?` — exit 0. Confirm in the log that the sector-level numbers are unchanged from the previous run (`Dynamic Sector-Level Validation`: `r = 0.509, p = 0.015`; `Sector-Level Validation`: `r = -0.290`). Look at `data/output/visualizations/model_signal_over_time_occupation.png` (use the Read tool on the PNG) and record in the report the per-period `n` values and the AI-era r values for the three lines, and whether the pre-2019 `n` now sits near the unit count rather than ~650–690.

- [ ] **Step 5: Docs**

Replace the "Survivorship note" section of `docs/charts/model_signal_over_time_occupation.md` with a section titled "Harmonized units" that explains: each point is a harmonized unit (a connected component of the BLS crosswalks with residual edges pruned, see `harmonize_soc.py`); why (the 3% Computer and Mathematical survivorship example); that `n` is now roughly constant across periods and what it is; that units are NaN in years where a member OEWS publishes was suppressed; and that residual pruning is the one approximation, with `data/output/soc_harmonization_pruned_edges.csv` listing what was dropped. Update the `CLAUDE.md` row for `model_signal_over_time_occupation.png` to say units instead of survivorship. Copy the regenerated PNG to `docs/charts/images/model_signal_over_time_occupation.png`.

- [ ] **Step 6: Lint and commit**

```bash
PATH="$PWD/.venv/bin:$PATH" git add validate_bls.py tests/test_pipeline.py docs/charts/model_signal_over_time_occupation.md CLAUDE.md docs/charts/images/model_signal_over_time_occupation.png
git commit -m "Run the occupation-level historical validation on harmonized units

The occupation-level signal-over-time chart now correlates unit scores —
the 2025-employment-weighted mean over each unit's 2022 members — against
unit growth from bls_harmonized_trends.csv, so pre-2019 points no longer
rest on whichever detailed codes survived the SOC revisions. n is close to
constant across periods. Sector-level results are unchanged.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_017h8BcjpaxoxWqEDgwwsSqt"
```

---

### Task 6: Framework and README notes

**Files:**
- Modify: `docs/framework.md` — no new section; in the "Future investigation: the business cycle" section, replace the final sentence ("Testing it properly would mean extending the BLS series much further back … rather than carrying today's labels backwards.") with one that notes the crosswalk harmonization now in `harmonize_soc.py` covers 2005→2025 at occupation level, and that going back to 1960 would need the same treatment for the pre-2000 classifications plus per-year task reclassification.
- Modify: `README.md` — in the "Key Findings" paragraph that ends "…do not depend on which detailed SOC codes survived the 2010 and 2018 code revisions.", append one sentence: occupation-level history is likewise measured on harmonized crosswalk units (`bls_harmonized_trends.csv`).
- Modify: `docs/charts/model_signal_over_time.md` — in "How sector growth is measured", append one sentence pointing to the occupation-level chart's harmonized units as the occupation-level counterpart.

No code, no tests. Lint is not applicable.

- [ ] **Step 1: Make the three edits**
- [ ] **Step 2: Commit**

```bash
PATH="$PWD/.venv/bin:$PATH" git add docs/framework.md README.md docs/charts/model_signal_over_time.md
git commit -m "Point framework, README and sector chart doc at the harmonized units

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_017h8BcjpaxoxWqEDgwwsSqt"
```
