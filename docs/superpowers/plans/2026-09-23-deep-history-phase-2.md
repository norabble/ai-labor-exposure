# Deep History Phase 2 — Detailed Occupations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise the 1983–2026 CPS validation from ten occupation groups to ~330 `occ1990dd` occupations (plus a 22-SOC-major rollup), and the DWS validation from ten groups to the ~25-group Autor–Dorn partition per survey, from IPUMS CPS microdata.

**Architecture:** Two halves. A **local build** (never CI) downloads IPUMS extracts, tabulates them onto `occ1990dd`, runs gates G1/G2/G3/G5/G6, and — only if every gate passes — promotes aggregate tables to `seeds/`. The **pipeline** reads those seeds only: it builds trend, reliability and seam tables, scores every `occ1990dd` code through a published-crosswalk chain to SOC 2018 (gate G4 measures the chain's error), and runs the existing era and cycle machinery at the new levels.

**Tech Stack:** Python 3.12, pandas, numpy, scipy (incl. `scipy.sparse`), matplotlib/seaborn. New optional dependency `ipumspy>=0.8.2` in an `ipums` dependency group, imported only inside the download and verification modules.

**Spec:** `docs/superpowers/specs/2026-09-23-deep-history-phase-2-design.md` — read it before starting. The analysis choices, gates and thresholds pinned there are **not** re-decided by this plan.

## Global Constraints

- **No generic abbreviations.** Never `df`, `res`, `tmp`, `val`. Use `panel_df`, `person_df`, `bridge_weights_df`, `growth_column`.
- **Module docstrings required** on every Python file — ruff `D100`. Name, purpose, inputs, outputs.
- Ruff line length **140**; rules `E`, `W`, `F`, `I`, `N`, `D100` (so exceptions end in `Error`). Run ruff only on files you touch, **format first** — it wraps most long lines — then check: `.venv/bin/ruff format <files> && .venv/bin/ruff check --fix <files>`. `--fix` also sorts the imports each task adds mid-file.
- Tests: `.venv/bin/python -m pytest tests/ -q`. Baseline before this plan: **459 passed, 6 skipped, 1 xfailed** (measured 2026-09-23; the full suite takes ~3 minutes).
- Run Python through `.venv/bin/python`, not `uv run`.
- **No test touches the network.** IPUMS, BLS and Census are always faked or read from committed seeds.
- **Never modify** `data/raw/` contents you did not create, `seeds/classified_all_tasks.csv`, `seeds/cps_a19_panel.csv`, `seeds/dws_displacement_panel.csv`, `seeds/cps_occupation_panel.csv`, or `seeds/soc_crosswalks/`.
- **Existing outputs must not change.** Every file under `data/output/` that exists before this plan must be byte-identical afterwards. Task 13 verifies this.
- Every new pipeline output gets a `CLAUDE.md` Outputs Reference row **in the commit that creates it**.
- **IPUMS never runs in CI.** `ipumspy` lives in the optional `ipums` group; nothing outside `download_ipums_cps.py` and `verify_ipums_cps.py` imports it, and those import it inside functions.
- **Seeds hold aggregates only** — IPUMS terms prohibit redistributing microdata.
- **Pinned analysis values (spec § Analysis choices), verbatim:** RSE cutoff **20%**, per period, both endpoint years; fixed-set sensitivity at 20% every year; sweep **10%, 20%, 30%, none**; labeled share **≥ 0.8**; headline excludes seam periods **1991→92, 1993→94, 2002→03, 2010→11**; COVID `2019_2020`, `2020_2021` excluded; AI era from `2022_2023`; `MINIMUM_UNITS = 20`; universe `all_employed` for every headline; year-over-year growth; chained scores only. Gates: **G1 ≤ 1%** (2003–2026, `COMPWT`), **G2 ≤ 1%** (1998+, `COMPWT`), **G3 ≤ 3%**, **G4 r ≥ 0.8 in every coding block**, **G5** structural.
- **Deviations.** Any change to a pinned choice after a seed exists is recorded in § Deviations log at the bottom of this file, with its reason, in the same commit as the change.
- Commit with `PATH="$PWD/.venv/bin:$PATH" git commit ...` so the pre-commit hooks find ruff. Stage explicit paths — **never `git add -A`**; this repo's root carries untracked dotfiles that are not ours.
- Commit message trailer, exactly:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  ```

---

## Verified facts this plan depends on

Checked on 2026-09-22/23. Do not re-derive; do not assume differently.

| Check | Result |
|---|---|
| Dorn crosswalks, `www.ddorn.net/data/occ{1980,1990,2000,2005,2010}_occ1990dd.zip` | Each unzips to one Stata `.dta` with columns `occ`, `occ1990dd`. Rows: 504, 502, 471, 471, 489. **Every source code maps to exactly one `occ1990dd`** (no duplicate source codes). `occ2010`'s `occ` is a zero-padded string (`"0010"`); the others are integers. |
| `occ1990dd` universe | **333 distinct codes** across the five tables, excluding `999` (unclassified). The spec's "~380" was an estimate; 333 is the verified count. |
| Dorn groups, `subfile_occ1990dd_occgroups.do` | The 25-group partition in Task 3's seed covers all 333 codes exactly once **except `905` and `991`**, which fall in no group. |
| Census code lists, `www2.census.gov/programs-surveys/demo/guidance/industry-occupation/` | `2002-census-occupation-codes.xls` sheet `Occ Codes`; `2010-occ-codes-with-crosswalk-from-2002-2011.xls` sheet `2010OccCodeList`; `2018-occupation-code-list-and-crosswalk.xlsx` sheet `2018 Census Occ Code List`. In all three, read with `header=None, dtype=str`: column 1 = title, column 2 = Census code, column 3 = SOC reference; **data rows are those whose column 2 is exactly four digits**. Counts: **510 / 540 / 570** codes. |
| SOC references in those lists | Detailed (`11-1011`): 369 / 406 / 430. Broad group ending in `0` (`11-2020`): 126 / 119 / 100. Wildcard with `X` (`15-113X`, `25-90XX`): 13 / 13 / 38. Literal `none`: 2 / 2 / 2. **No detailed SOC code in any vocabulary ends in `0`** (checked against `harmonize_soc.soc_vocabularies()`: soc2000 821, soc2010 840, soc2018 867 codes). |
| Census 2010→2018 crosswalk, sheet `2010 to 2018 Crosswalk ` (trailing space) of the 2018 file | Rows from index 4; column 1 = 2010 Census code, column 4 = 2018 Census code; continuation rows leave column 1 blank. Forward-filling column 1 yields 570 pairs covering **every** 2018 code once; 56 of the 540 2010 codes (Census merges) appear in no pair. |
| `ipumspy` on PyPI | Version **0.8.2**, Python ≥3.10. API: `IpumsApiClient(api_key)`, `.get_all_sample_info(collection)`, `.submit_extract(extract)`, `.wait_for_extract(extract)`, `.download_extract(extract, download_dir=...)`; `MicrodataExtract(collection=, samples=, variables=, description=)`; `ipumspy.readers.read_ipums_ddi(path)`, `readers.read_microdata_chunked(ddi, data_path, chunksize=)`; `Codebook.get_variable_info(name)`. |
| IPUMS access | `api.ipums.org` returns 401 without a key. **No `IPUMS_API_KEY` in `.env` as of 2026-09-23.** |
| `composition_era_validation` | `discover_period_columns`, `period_key`, `is_ai_era`, `summarise_eras`, `decompose_fit_strength`, `unemployment_change_by_period`, `print_era_summary`, `print_cycle_decomposition`, `plot_signal_over_time(frame, output_dir, level)`, `load_scored_occupations()`, `COVID_PERIODS`, `MINIMUM_UNITS = 20`. The shared period frame shape is `period, score, fit_r, fit_p, n_units, era, is_covid`. |
| `analyze_bls.attach_growth_columns(trend_df, available_years)` | Takes a frame with `TOT_EMP_{yyyy}` columns and four-digit string years; adds `hist_emp_growth_{a}_{b}` (end year ≤ 2022) and `emp_growth_{a}_{b}`. |
| `synthesize_impacts.attach_dominant_demand(frame)` | Reads `pct_bounded`, `pct_unbounded`, `pct_adversarial`; writes `dominant_demand`, `dominant_strength`. |
| Model reports | `occupation_composition_model_report.csv` and `occupation_dynamic_model_report.csv` both carry `OCC_CODE` (SOC 2018), `pct_*`, `gross_displacement`, `net_employment_change`; dynamic also `occupation_exposure`. 770 rows. |
| `cps_historical_panel` | `compare_with_oews(cps_trends_df, oews_sector_trends_df, soc_major_to_group)` expects a `cps_group` column; `seeds/cps_occupation_panel.csv` columns `year, cps_group, employed_thousands, months_observed`. |
| `composition_displacement_validation` | `soc_major_to_dws_group()`, `correlate_with_leave_one_out(frame, predicted_column)` (needs `dws_group`, `observed_share`), `MINIMUM_GROUPS = 5`. |

## Where this plan refines the spec

Each of these is recorded here so no reviewer mistakes it for drift. None changes a pinned analysis choice.

1. **Verification is Task 2, not Task 1.** It needs the download client built in Task 1. **Nothing that reads real IPUMS data runs before Task 2 passes**; the build code refuses while `ipums_cps_variables.VERIFICATION_STATUS != "verified"`.
2. **`occ1990dd` count is 333**, not ~380 (verified above).
3. **Module split.** The spec's `cps_detailed_panel.py` is split into `cps_detailed_panel.py` (local build: tabulation, bootstrap, gates, promotion) and `cps_detailed_measurement.py` (pipeline: trends, variance, eligibility, reliability, seams). The detailed and rollup validation live in a new `cps_detailed_validation.py`, and 2b's in `dws_detailed_validation.py`, both reusing `composition_era_validation` and `composition_displacement_validation` functions rather than growing those files. `composition_era_validation.plot_signal_over_time` gains two chart levels.
4. **Gate G6, spine coverage — added.** The spec did not pin what happens if IPUMS `OCC1990` codes fall outside Dorn's `occ1990_occ1990dd` table. G6: employment whose `OCC1990` has no `occ1990dd` must be **≤ 1% of civilian employment in every year**. Pinned here, before any seed exists.
5. **Shared SOC codes are divided equally.** When one SOC 2018 code is reachable from *k* owners (units or Census codes), each owner gets 1/*k* of its OEWS 2022 employment before within-owner normalisation. An owner none of whose members have OEWS employment gets equal weights.
6. **Corrected r of magnitude ≥ 1 is undefined**, reported as NaN like reliability ≤ 0, and the count of such periods is printed.
7. **Rollup minimum:** a 22-major period correlation needs ≥ 20 majors present (the ten-group level's 8-of-10 convention).
8. **Bootstrap:** Poisson(1) weights per household cluster, 200 replicates, seed `20260923`, drawn in blocks of 50.
9. **Complete years only for G1/G2.** A year enters those gates only if both sides have 12 months; partial years are reported, not gated. Each gate must compare at least one year, or it fails.
10. **Three reported-only outputs added**, all required by the spec's text but missing from its outputs table: `cps_detailed_period_correlations.csv` (every period row for every run), `cps_major_oews_agreement.csv`, and `cps_detailed_published_agreement.csv`. Plus `occ1990dd_composition_stability.csv` for the spec's detailed composition-stability proxy.
11. **DWS predicted displacement uses the latest complete year's CPS employment** for every survey, so the predicted vector is survey-invariant, matching the existing ten-group validation.
12. **DWS lost-job occupation fallback, completed.** The spec's fallback maps raw lost-job codes through "Dorn's table for the survey's coding vintage". That does not work for two vintages. Dorn has no occ2018 table. And Dorn's `occ2000` uses 3-digit 2000 Census codes, while CPS 2003–2010 recorded 4-digit 2002 Census codes. If IPUMS has no harmonized lost-job `OCC1990`, both vintages therefore route through the Census Bureau's own published crosswalks to 2010 codes (2002→2010 and 2018→2010, both committed in Task 3), then Dorn's `occ2010`. A raw code reaching *k* `occ1990dd` codes splits its weight equally. Task 14's route table is authoritative.
13. **Gate G6D — added.** The displacement twin of G6: lost-job weight that reaches no `occ1990dd` code must be ≤ 1% in every survey. The fallback route drops codes at each Census revision (about 50 codes on the 2010 Census list are absent from Dorn's `occ2010`, checked 2026-09-23), so this loss has to be measured.
14. **The 1990 Census subheadings sensitivity for DWS is not run.** The spec made it conditional on confirming the subheadings form a clean partition. The Census Bureau's industry-occupation guidance directory (checked 2026-09-23) holds 1970 and 1980 code lists and 2002-onward lists, but **no 1990 list at all**, so there is no committed source for that partition. It is dropped rather than hand-built; the Dorn partition remains the headline, exactly as the spec pinned.

## File map

| File | Status | Responsibility |
|---|---|---|
| `ipums_cps_variables.py` | Create (T1), confirm (T2) | Every IPUMS name, code and sample-ID pattern, with `VERIFICATION_STATUS`. |
| `download_ipums_cps.py` | Create (T1) | Submit, wait for, download and read IPUMS extracts. |
| `verify_ipums_cps.py` | Create (T2) | One-off verification against IPUMS; writes the verification record. |
| `occ1990dd_reference.py` | Create (T3) | Loaders for Dorn crosswalks, Census code lists, Dorn groups; SOC reference expansion. |
| `occ1990dd_soc_bridge.py` | Create (T4, T5, T10) | Chain edges, bridge weights, unit scoring, composition stability, bridge check (G4). |
| `cps_detailed_panel.py` | Create (T6–T8) | Local build: tabulation, bootstrap, gates G1/G2/G5/G6, promotion. |
| `cps_detailed_measurement.py` | Create (T9) | Pipeline: trends, RSE, growth variance, eligibility, reliability, seams. |
| `cps_detailed_validation.py` | Create (T11–T13) | Detailed and 22-major era/cycle tests; pipeline entry `run()`. |
| `dws_detailed_panel.py` | Create (T14–T15) | Local build of the DWS panel on the Dorn partition; gate G3. |
| `dws_detailed_validation.py` | Create (T16) | Per-survey displacement validation at Dorn-group level. |
| `composition_era_validation.py` | Modify (T11) | `plot_signal_over_time` gains `cps_detailed` and `cps_major` levels. |
| `synthesize_composition.py` | Modify (T13, T16) | `run_stage` calls the two new validation entry points. |
| `seeds/occ1990dd_crosswalks/`, `seeds/cps_soc_crosswalks/`, `seeds/occ1990dd_groups.csv` | Create (T3) | Committed reference data with citation READMEs. |
| `seeds/cps_detailed_occupation_panel.csv`, `seeds/cps_detailed_occ_crosstab.csv`, `seeds/cps_detailed_gates.csv` | Create (T8, key-gated) | Aggregates from the local build. |
| `seeds/dws_detailed_panel.csv`, `seeds/dws_detailed_gates.csv` | Create (T15, key-gated) | Aggregates from the DWS build. |
| `tests/test_download_ipums_cps.py`, `tests/test_verify_ipums_cps.py`, `tests/test_occ1990dd_reference.py`, `tests/test_occ1990dd_soc_bridge.py`, `tests/test_cps_detailed_panel.py`, `tests/test_cps_detailed_measurement.py`, `tests/test_cps_detailed_validation.py`, `tests/test_dws_detailed_panel.py`, `tests/test_dws_detailed_validation.py` | Create | One test file per module. |
| `pyproject.toml`, `uv.lock` | Modify (T1) | `ipums` dependency group. |
| `CLAUDE.md`, `README.md`, `docs/framework.md`, `docs/charts/*.md` | Modify / create | Output rows, seeds convention, results, chart docs. |

## Task order and the key gate

The byte-identity baseline, Tasks 1, 3–7 and 9–14, Task 16, and Task 17 Steps 1–2 need **no IPUMS key**; everything they test runs on synthetic fixtures or committed seeds. Steps marked **[KEY-GATED]** need `IPUMS_API_KEY` in `.env` **and** Task 2 passed. If the key is missing when execution starts, run the no-key tasks in order and pause at the first [KEY-GATED] step. **Never skip Task 2**, and never hand-edit `VERIFICATION_STATUS` to get past it.

---
### Before Task 1: capture the byte-identity baseline

Tasks 11, 13 and 16 change modules the existing pipeline runs. The spec requires every existing output to stay byte-identical. So record the baseline **before any code changes**, on the commit this plan starts from:

```bash
.venv/bin/python main.py composition
(cd data/output && find . -type f | sort | xargs sha256sum) > data/phase2_baseline_hashes.txt
wc -l data/phase2_baseline_hashes.txt
```

`data/` is gitignored, so the baseline survives across sessions without being committed. Tasks 13 and 17 check against it with `sha256sum --check`.

---

### Task 1: IPUMS variables module and download client

No key needed. Builds everything Task 2 uses to talk to IPUMS, and fixes every IPUMS name in one module so later tasks never hard-code one.

**Files:**
- Modify: `pyproject.toml` (add `ipums` dependency group), `uv.lock`
- Create: `ipums_cps_variables.py`, `download_ipums_cps.py`
- Test: `tests/test_download_ipums_cps.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `ipums_cps_variables`: `VERIFICATION_STATUS: str`, `COLLECTION`, `BASIC_MONTHLY_SAMPLE_PATTERN`, `BASIC_MONTHLY_FIRST_YEAR`, `BASIC_MONTHLY_VARIABLES: list[str]`, `EMPLOYED_EMPSTAT_CODES`, `MINIMUM_AGE`, `WAGE_SALARY_CLASSWKR_CODES`, `COMPOSITE_WEIGHT_FIRST_YEAR`, `HOUSEHOLD_CLUSTER`, and the `DWS_*` constants listed in Step 3.
  - `download_ipums_cps`: `RAW_DIR`, `basic_monthly_sample_id(year: int, month: int) -> str`, `dws_sample_id(survey_year: int) -> str`, `make_client()`, `available_sample_ids(client) -> set[str]`, `extract_is_downloaded(extract_dir: str) -> bool`, `fetch_basic_monthly_year(year: int, raw_dir: str = RAW_DIR, client=None) -> str | None`, `fetch_dws_survey(survey_year: int, raw_dir: str = RAW_DIR, client=None) -> str | None`, `read_extract(extract_dir: str) -> Iterator[pd.DataFrame]`, `read_codebook(extract_dir: str)`.

- [ ] **Step 1: Add the optional dependency group**

In `pyproject.toml`, under `[dependency-groups]`, after the `dev` group:

```toml
ipums = [
    "ipumspy>=0.8.2",
]
```

Run: `uv lock`
Expected: `uv.lock` updated with `ipumspy` and its dependencies. `uv sync --locked` (what CI runs) installs only default groups, so CI is unaffected.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_download_ipums_cps.py`:

```python
"""Tests for download_ipums_cps.py — IPUMS extract requests, without touching IPUMS."""

import ast

import pytest

import download_ipums_cps
import ipums_cps_variables as ipums_variables


class TestSampleIds:
    def test_basic_monthly_id_zero_pads_the_month(self):
        assert download_ipums_cps.basic_monthly_sample_id(1983, 1) == "cps1983_01b"

    def test_dws_id_is_the_january_sample(self):
        assert download_ipums_cps.dws_sample_id(2024) == "cps2024_01b"


class TestNoTopLevelIpumspyImport:
    """CI never installs ipumspy, so importing either IPUMS module must not require it."""

    @pytest.mark.parametrize("module_path", ["download_ipums_cps.py", "ipums_cps_variables.py"])
    def test_ipumspy_is_imported_only_inside_functions(self, module_path):
        with open(module_path) as source_file:
            module_tree = ast.parse(source_file.read())
        top_level_imports = [node for node in module_tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
        imported_names = set()
        for import_node in top_level_imports:
            if isinstance(import_node, ast.ImportFrom):
                imported_names.add((import_node.module or "").split(".")[0])
            else:
                imported_names.update(alias.name.split(".")[0] for alias in import_node.names)
        assert "ipumspy" not in imported_names


class TestApiKey:
    def test_missing_key_raises_with_registration_instructions(self, monkeypatch):
        monkeypatch.setattr(download_ipums_cps, "load_dotenv", lambda: None)
        monkeypatch.delenv("IPUMS_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="account.ipums.org"):
            download_ipums_cps._api_key()


class FakeClient:
    def __init__(self, sample_ids):
        self.sample_ids = sample_ids

    def get_all_sample_info(self, collection):
        return {sample_id: f"description of {sample_id}" for sample_id in self.sample_ids}


class TestFetchBasicMonthlyYear:
    def test_requests_only_samples_ipums_publishes(self, tmp_path, monkeypatch):
        requested = {}

        def fake_submit(client, samples, variables, description, extract_dir):
            requested["samples"] = samples
            requested["variables"] = variables
            return extract_dir

        monkeypatch.setattr(download_ipums_cps, "_submit_and_download", fake_submit)
        client = FakeClient({"cps2026_01b", "cps2026_02b", "cps2025_12b"})
        download_ipums_cps.fetch_basic_monthly_year(2026, raw_dir=str(tmp_path), client=client)
        assert requested["samples"] == ["cps2026_01b", "cps2026_02b"]
        assert requested["variables"] == ipums_variables.BASIC_MONTHLY_VARIABLES

    def test_a_year_already_downloaded_is_not_requested_again(self, tmp_path, monkeypatch):
        extract_dir = tmp_path / "basic" / "1983"
        extract_dir.mkdir(parents=True)
        (extract_dir / "cps_00001.xml").write_text("<codebook/>")
        (extract_dir / "cps_00001.dat.gz").write_bytes(b"")

        def fail_submit(*args, **kwargs):
            raise AssertionError("must not resubmit a downloaded year")

        monkeypatch.setattr(download_ipums_cps, "_submit_and_download", fail_submit)
        result = download_ipums_cps.fetch_basic_monthly_year(1983, raw_dir=str(tmp_path), client=FakeClient(set()))
        assert result == str(extract_dir)

    def test_a_year_with_no_published_samples_returns_none(self, tmp_path):
        assert download_ipums_cps.fetch_basic_monthly_year(1975, raw_dir=str(tmp_path), client=FakeClient(set())) is None


class TestFetchDwsSurvey:
    def test_requests_the_january_sample_with_dws_variables(self, tmp_path, monkeypatch):
        requested = {}

        def fake_submit(client, samples, variables, description, extract_dir):
            requested["samples"] = samples
            requested["variables"] = variables
            return extract_dir

        monkeypatch.setattr(download_ipums_cps, "_submit_and_download", fake_submit)
        download_ipums_cps.fetch_dws_survey(2024, raw_dir=str(tmp_path), client=FakeClient({"cps2024_01b"}))
        assert requested["samples"] == ["cps2024_01b"]
        assert set(ipums_variables.DWS_VARIABLES) <= set(requested["variables"])
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_download_ipums_cps.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'download_ipums_cps'`.

- [ ] **Step 4: Create `ipums_cps_variables.py`**

```python
"""
ipums_cps_variables.py
──────────────────────
Every IPUMS CPS variable name, code value and sample-ID pattern that Phase 2 of
the deep history extension depends on, in one module — because several of them
can only be confirmed against IPUMS itself.

Each value starts as the expected value from IPUMS documentation. Plan Task 2
(`verify_ipums_cps.py`) confirms or corrects every one against a probe extract,
records the evidence in docs/superpowers/plans/2026-09-23-ipums-verification.md,
and only then sets VERIFICATION_STATUS to "verified". The panel builds refuse to
read real data until it is.

Inputs: none. Outputs: none — constants only.
"""

VERIFICATION_STATUS = "unverified"

COLLECTION = "cps"
BASIC_MONTHLY_SAMPLE_PATTERN = "cps{year}_{month:02d}b"
BASIC_MONTHLY_FIRST_YEAR = 1983

BASIC_MONTHLY_VARIABLES = [
    "YEAR",
    "MONTH",
    "SERIAL",
    "CPSID",
    "PERNUM",
    "MISH",
    "WTFINL",
    "COMPWT",
    "AGE",
    "EMPSTAT",
    "OCC",
    "OCC1990",
    "CLASSWKR",
]

# EMPSTAT 10 = at work, 12 = has job, not at work last week. Armed forces (01) excluded.
EMPLOYED_EMPSTAT_CODES = (10, 12)
MINIMUM_AGE = 16

# Wage and salary classes only: both self-employed classes (13, 14), unpaid family
# workers (29) and armed forces (26) are excluded.
WAGE_SALARY_CLASSWKR_CODES = (20, 21, 22, 23, 24, 25, 27, 28)

OCC1990_NOT_IN_UNIVERSE = 999

# BLS's published CPS estimates use composite weights from this year on.
COMPOSITE_WEIGHT_FIRST_YEAR = 1998

# "CPSID" if households link across months in every year 1983-2026, otherwise
# "household_month" (SERIAL within YEAR and MONTH) for the whole span — the
# bootstrap design must be identical in every year (spec § Sampling variance).
HOUSEHOLD_CLUSTER = "CPSID"

# ── Displaced Worker Supplement (Tasks 14-16). Confirmed in Task 2 Step 6. ──
DWS_SURVEY_YEARS: tuple[int, ...] = tuple(range(1984, 2027, 2))
DWS_SAMPLE_PATTERN = "cps{year}_01b"
DWS_WEIGHT_VARIABLE = "DWSUPPWT"
DWS_REASON_VARIABLE = "DWREAS"
DWS_TENURE_VARIABLE = "DWYEARS"
# Raw, vintage-coded occupation of the lost job. Required: gate G3 reads it.
DWS_LOST_JOB_OCC_VARIABLE = "DWOCC"
# Harmonized 1990-basis occupation of the lost job, or None if IPUMS has none.
DWS_LOST_JOB_OCC1990_VARIABLE: str | None = None
# Task 2 fills these from the DWREAS codebook: the codes whose labels name a
# plant or company closing or move, insufficient work, or an abolished position
# or shift — BLS's three displacement reasons.
DWS_DISPLACED_REASON_LABEL_FRAGMENTS = ("closed", "insufficient work", "abolished")
DWS_DISPLACED_REASON_CODES: tuple[int, ...] = ()
# Tenure values above this are IPUMS not-in-universe / missing codes.
DWS_TENURE_VALID_MAXIMUM = 60.0
DWS_MINIMUM_AGE = 20

DWS_VARIABLES = [
    "YEAR",
    "MONTH",
    "SERIAL",
    "CPSID",
    "PERNUM",
    "AGE",
    DWS_WEIGHT_VARIABLE,
    DWS_REASON_VARIABLE,
    DWS_TENURE_VARIABLE,
    DWS_LOST_JOB_OCC_VARIABLE,
] + ([DWS_LOST_JOB_OCC1990_VARIABLE] if DWS_LOST_JOB_OCC1990_VARIABLE else [])
```

- [ ] **Step 5: Create `download_ipums_cps.py`**

```python
"""
download_ipums_cps.py
─────────────────────
Submit and download IPUMS CPS microdata extracts for Phase 2 of the deep history
extension: basic-monthly samples for the detailed employment panel, and January
Displaced Worker Supplement samples for the detailed displacement panel.

Local and manual only — never run in CI. IPUMS terms prohibit redistributing
microdata, so everything this writes lands under data/raw/ipums/, which git
ignores; only aggregate tables built from it are ever committed.

Needs IPUMS_API_KEY in .env (https://account.ipums.org/api_keys) and the optional
dependency group (`uv sync --group ipums`). ipumspy is imported inside the
functions that use it, so importing this module — and running the test suite —
does not require it.

Downloads are resumable: a directory that already holds a codebook and a data
file is not requested again. To refresh a partially published year (e.g. the
current year as new months appear), delete that year's directory first.

Inputs:
  • IPUMS CPS extract API (collection "cps")
Outputs:
  • data/raw/ipums/basic/{year}/        one extract per year (data file + DDI codebook)
  • data/raw/ipums/dws/{survey_year}/   one extract per DWS survey

Usage:
  python download_ipums_cps.py basic 1983 2026
  python download_ipums_cps.py dws
"""

import glob
import os
import sys
from collections.abc import Iterator

import pandas as pd
from dotenv import load_dotenv

import ipums_cps_variables as ipums_variables

RAW_DIR = "data/raw/ipums"
READ_CHUNK_ROWS = 500_000


def basic_monthly_sample_id(year: int, month: int) -> str:
    """IPUMS sample ID for one basic-monthly CPS month, e.g. (1983, 1) -> 'cps1983_01b'."""
    return ipums_variables.BASIC_MONTHLY_SAMPLE_PATTERN.format(year=year, month=month)


def dws_sample_id(survey_year: int) -> str:
    """IPUMS sample ID carrying one survey year's Displaced Worker Supplement."""
    return ipums_variables.DWS_SAMPLE_PATTERN.format(year=survey_year)


def _api_key() -> str:
    load_dotenv()
    api_key = os.environ.get("IPUMS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "IPUMS_API_KEY is not set in .env. Register for IPUMS CPS at https://cps.ipums.org "
            "and create a key at https://account.ipums.org/api_keys"
        )
    return api_key


def make_client():
    """An authenticated IpumsApiClient."""
    from ipumspy import IpumsApiClient

    return IpumsApiClient(_api_key())


def available_sample_ids(client) -> set[str]:
    """Every CPS sample ID IPUMS currently publishes."""
    return set(client.get_all_sample_info(ipums_variables.COLLECTION))


def extract_is_downloaded(extract_dir: str) -> bool:
    """True when a directory already holds a DDI codebook and a data file."""
    return bool(glob.glob(os.path.join(extract_dir, "*.xml"))) and bool(glob.glob(os.path.join(extract_dir, "*.dat.gz")))


def _submit_and_download(client, samples: list[str], variables: list[str], description: str, extract_dir: str) -> str:
    from ipumspy import MicrodataExtract

    extract = MicrodataExtract(
        collection=ipums_variables.COLLECTION,
        samples=samples,
        variables=variables,
        description=description,
    )
    client.submit_extract(extract)
    client.wait_for_extract(extract)
    os.makedirs(extract_dir, exist_ok=True)
    client.download_extract(extract, download_dir=extract_dir)
    return extract_dir


def fetch_basic_monthly_year(year: int, raw_dir: str = RAW_DIR, client=None) -> str | None:
    """Download every published basic-monthly sample for one year as a single extract.

    Returns the extract directory, or None when IPUMS publishes no month of that year.
    """
    extract_dir = os.path.join(raw_dir, "basic", str(year))
    if extract_is_downloaded(extract_dir):
        return extract_dir
    client = client or make_client()
    published_samples = available_sample_ids(client)
    samples = [basic_monthly_sample_id(year, month) for month in range(1, 13)]
    samples = [sample_id for sample_id in samples if sample_id in published_samples]
    if not samples:
        return None
    return _submit_and_download(
        client,
        samples,
        ipums_variables.BASIC_MONTHLY_VARIABLES,
        f"ai-exposure deep history phase 2: basic monthly {year}",
        extract_dir,
    )


def fetch_dws_survey(survey_year: int, raw_dir: str = RAW_DIR, client=None) -> str | None:
    """Download one survey year's January sample with the Displaced Worker Supplement variables."""
    extract_dir = os.path.join(raw_dir, "dws", str(survey_year))
    if extract_is_downloaded(extract_dir):
        return extract_dir
    client = client or make_client()
    sample_id = dws_sample_id(survey_year)
    if sample_id not in available_sample_ids(client):
        return None
    return _submit_and_download(
        client,
        [sample_id],
        ipums_variables.DWS_VARIABLES,
        f"ai-exposure deep history phase 2: displaced worker supplement {survey_year}",
        extract_dir,
    )


def _extract_paths(extract_dir: str) -> tuple[str, str]:
    ddi_paths = sorted(glob.glob(os.path.join(extract_dir, "*.xml")))
    data_paths = sorted(glob.glob(os.path.join(extract_dir, "*.dat.gz")))
    if not ddi_paths or not data_paths:
        raise FileNotFoundError(f"{extract_dir} holds no downloaded IPUMS extract")
    return ddi_paths[0], data_paths[0]


def read_codebook(extract_dir: str):
    """The DDI codebook of a downloaded extract."""
    from ipumspy import readers

    ddi_path, _ = _extract_paths(extract_dir)
    return readers.read_ipums_ddi(ddi_path)


def read_extract(extract_dir: str) -> Iterator[pd.DataFrame]:
    """Yield a downloaded extract's person records in chunks, so a full year never sits in memory twice."""
    from ipumspy import readers

    ddi_path, data_path = _extract_paths(extract_dir)
    codebook = readers.read_ipums_ddi(ddi_path)
    yield from readers.read_microdata_chunked(codebook, data_path, chunksize=READ_CHUNK_ROWS)


def main(arguments: list[str]) -> None:
    """Command-line entry: `basic FIRST_YEAR LAST_YEAR` or `dws`."""
    if not arguments or arguments[0] not in {"basic", "dws"}:
        raise SystemExit("usage: python download_ipums_cps.py basic FIRST_YEAR LAST_YEAR | dws")
    client = make_client()
    if arguments[0] == "basic":
        first_year, last_year = int(arguments[1]), int(arguments[2])
        for year in range(first_year, last_year + 1):
            print(f"  {year}: {fetch_basic_monthly_year(year, client=client) or 'no published samples'}")
    else:
        for survey_year in ipums_variables.DWS_SURVEY_YEARS:
            print(f"  {survey_year}: {fetch_dws_survey(survey_year, client=client) or 'no published sample'}")


if __name__ == "__main__":
    main(sys.argv[1:])
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_download_ipums_cps.py -v`
Expected: all PASS.

- [ ] **Step 7: Lint and commit**

```bash
.venv/bin/ruff format ipums_cps_variables.py download_ipums_cps.py tests/test_download_ipums_cps.py
.venv/bin/ruff check --fix ipums_cps_variables.py download_ipums_cps.py tests/test_download_ipums_cps.py
git add pyproject.toml uv.lock ipums_cps_variables.py download_ipums_cps.py tests/test_download_ipums_cps.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "Add the IPUMS CPS download client and variable registry

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 2: Verify every IPUMS fact against IPUMS itself [KEY-GATED from Step 4]

The spec's § "Must be verified once `IPUMS_API_KEY` exists". Two results are **design-breaking**, and each has an explicit stop below. Steps 1–3 (helpers and their tests) need no key.

**Files:**
- Create: `verify_ipums_cps.py`, `docs/superpowers/plans/2026-09-23-ipums-verification.md`
- Modify: `ipums_cps_variables.py` (confirmed values; `VERIFICATION_STATUS = "verified"`)
- Test: `tests/test_verify_ipums_cps.py`

**Interfaces:**
- Consumes: `download_ipums_cps.make_client`, `available_sample_ids`, `basic_monthly_sample_id`, `dws_sample_id`, `_submit_and_download`, `read_extract`, `read_codebook` (Task 1); `historical_displacement.fetch_bls_series(series_id, start_year, end_year) -> DataFrame[year, period, value]`.
- Produces: `summarise_basic_probe(person_df) -> pd.DataFrame`, `household_cluster_decision(summary_df) -> str`, `displaced_reason_codes(reason_labels: dict[str, int], label_fragments) -> tuple[int, ...]`; confirmed constants in `ipums_cps_variables`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_verify_ipums_cps.py`:

```python
"""Tests for verify_ipums_cps.py's pure helpers — the IPUMS calls themselves are manual."""

import pandas as pd
import pytest

from verify_ipums_cps import displaced_reason_codes, household_cluster_decision, summarise_basic_probe


def _person_rows(year, month, count, occ1990=100, cpsid=1, compwt=1000.0, empstat=10, age=30, classwkr=21):
    return pd.DataFrame(
        {
            "YEAR": [year] * count,
            "MONTH": [month] * count,
            "WTFINL": [1000.0] * count,
            "COMPWT": [compwt] * count,
            "CPSID": [cpsid] * count,
            "EMPSTAT": [empstat] * count,
            "AGE": [age] * count,
            "OCC1990": [occ1990] * count,
            "CLASSWKR": [classwkr] * count,
        }
    )


class TestSummariseBasicProbe:
    def test_employment_counts_only_civilian_employed_adults(self):
        person_df = pd.concat(
            [_person_rows(2020, 1, 3), _person_rows(2020, 1, 2, empstat=21), _person_rows(2020, 1, 1, age=15)],
            ignore_index=True,
        )
        summary_df = summarise_basic_probe(person_df)
        assert summary_df.loc[0, "employed_thousands"] == pytest.approx(3.0)

    def test_occ1990_valid_share_is_weighted_over_the_employed(self):
        person_df = pd.concat([_person_rows(2020, 1, 3), _person_rows(2020, 1, 1, occ1990=999)], ignore_index=True)
        assert summarise_basic_probe(person_df).loc[0, "occ1990_valid_share"] == pytest.approx(0.75)

    def test_linkage_share_counts_zero_cpsid_as_unlinked(self):
        person_df = pd.concat([_person_rows(1983, 1, 1, cpsid=0), _person_rows(1983, 1, 1, cpsid=5)], ignore_index=True)
        assert summarise_basic_probe(person_df).loc[0, "cpsid_linked_share"] == pytest.approx(0.5)


class TestHouseholdClusterDecision:
    def test_cpsid_when_every_probe_month_links(self):
        summary_df = pd.DataFrame({"cpsid_linked_share": [1.0, 0.995]})
        assert household_cluster_decision(summary_df) == "CPSID"

    def test_household_month_when_any_probe_month_does_not(self):
        summary_df = pd.DataFrame({"cpsid_linked_share": [0.0, 1.0]})
        assert household_cluster_decision(summary_df) == "household_month"


class TestDisplacedReasonCodes:
    def test_matches_the_three_bls_displacement_reasons_only(self):
        reason_labels = {
            "Plant or company closed down or moved": 1,
            "Insufficient work": 2,
            "Position or shift abolished": 3,
            "Seasonal job completed": 4,
            "Self-operated business failed": 5,
            "Other": 6,
        }
        fragments = ("closed", "insufficient work", "abolished")
        assert displaced_reason_codes(reason_labels, fragments) == (1, 2, 3)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_verify_ipums_cps.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'verify_ipums_cps'`.

- [ ] **Step 3: Create `verify_ipums_cps.py`**

```python
"""
verify_ipums_cps.py
───────────────────
Plan Task 2 of the deep history extension, Phase 2: confirm against IPUMS itself
every IPUMS fact the detailed panels depend on, before any real data is
tabulated — basic-monthly sample coverage, variable names and code values,
OCC1990 coverage after 2019, composite weights, household linkage across months,
and the Displaced Worker Supplement's variables.

Local and manual only. Needs IPUMS_API_KEY in .env and `uv sync --group ipums`.
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
  python verify_ipums_cps.py dws-probe
"""

import os
import sys

import pandas as pd

import download_ipums_cps
import ipums_cps_variables as ipums_variables

PROBE_DIR = "data/raw/ipums/probe"
BASIC_PROBE_MONTHS = [(1983, 1), (1988, 1), (1989, 1), (1994, 1), (1998, 1), (2003, 1), (2011, 1), (2020, 1)]
DWS_PROBE_YEARS = (1984, 1994, 2002, 2004, 2020)
OCC1990_MINIMUM_VALID_SHARE = 0.99
CPSID_MINIMUM_LINKED_SHARE = 0.99
TOTAL_EMPLOYMENT_SERIES_ID = "LNU02000000"


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
        months = [month for month in range(1, 13) if download_ipums_cps.basic_monthly_sample_id(year, month) in published_samples]
        if months:
            present_years.append(year)
        if months and len(months) < 12:
            print(f"  {year}: {len(months)} months published ({months[0]}-{months[-1]})")
        elif not months:
            print(f"  {year}: NO basic-monthly samples under pattern {ipums_variables.BASIC_MONTHLY_SAMPLE_PATTERN}")
    print(f"  Years with samples: {present_years[0] if present_years else None}-{present_years[-1] if present_years else None}")
    dws_present = [year for year in ipums_variables.DWS_SURVEY_YEARS if download_ipums_cps.dws_sample_id(year) in published_samples]
    print(f"  DWS survey-year January samples present: {dws_present}")


def run_basic_probe() -> None:
    """Submit one small extract across the coding vintages and print everything Task 2 must confirm."""
    client = download_ipums_cps.make_client()
    published_samples = download_ipums_cps.available_sample_ids(client)
    latest_january = max(year for year in range(2020, 2027) if download_ipums_cps.basic_monthly_sample_id(year, 1) in published_samples)
    probe_months = BASIC_PROBE_MONTHS + [(latest_january, 1)]
    samples = [download_ipums_cps.basic_monthly_sample_id(year, month) for year, month in probe_months]
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

    data_file_bytes = sum(os.path.getsize(os.path.join(probe_dir, name)) for name in os.listdir(probe_dir) if name.endswith(".dat.gz"))
    estimated_total_gigabytes = data_file_bytes / len(probe_months) * 12 * 44 / 1e9
    print(f"\n  Probe data file: {data_file_bytes / 1e6:.1f} MB for {len(probe_months)} months")
    print(f"  Full 1983-2026 basic monthly, extrapolated: ≈ {estimated_total_gigabytes:.1f} GB")


def run_dws_probe() -> None:
    """Submit the DWS variables for the probe survey years and print their availability and codes."""
    client = download_ipums_cps.make_client()
    published_samples = download_ipums_cps.available_sample_ids(client)
    samples = [
        download_ipums_cps.dws_sample_id(year) for year in DWS_PROBE_YEARS if download_ipums_cps.dws_sample_id(year) in published_samples
    ]
    probe_dir = os.path.join(PROBE_DIR, "dws")
    if not download_ipums_cps.extract_is_downloaded(probe_dir):
        download_ipums_cps._submit_and_download(client, samples, ipums_variables.DWS_VARIABLES, "ai-exposure phase 2 DWS probe", probe_dir)

    person_df = pd.concat(download_ipums_cps.read_extract(probe_dir), ignore_index=True)
    weight_column = ipums_variables.DWS_WEIGHT_VARIABLE
    for year, year_df in person_df.groupby("YEAR"):
        in_supplement = year_df[year_df[weight_column].astype(float) > 0]
        print(f"\n  {year}: {len(in_supplement)} records with positive {weight_column}")
        for variable_name in ipums_variables.DWS_VARIABLES:
            if variable_name in year_df.columns:
                variable_values = in_supplement[variable_name]
                value_range = f"{variable_values.min()}-{variable_values.max()}"
                print(f"    {variable_name}: {variable_values.nunique()} distinct values, range {value_range}")

    codebook = download_ipums_cps.read_codebook(probe_dir)
    reason_labels = codebook.get_variable_info(ipums_variables.DWS_REASON_VARIABLE).codes
    print(f"\n  {ipums_variables.DWS_REASON_VARIABLE} codes: {reason_labels}")
    print(
        f"  Displaced reason codes by label: {displaced_reason_codes(reason_labels, ipums_variables.DWS_DISPLACED_REASON_LABEL_FRAGMENTS)}"
    )
    print(f"  {ipums_variables.DWS_TENURE_VARIABLE} codes: {codebook.get_variable_info(ipums_variables.DWS_TENURE_VARIABLE).codes}")


def main(arguments: list[str]) -> None:
    """Command-line entry: `samples`, `basic-probe` or `dws-probe`."""
    commands = {"samples": run_samples, "basic-probe": run_basic_probe, "dws-probe": run_dws_probe}
    if not arguments or arguments[0] not in commands:
        raise SystemExit(f"usage: python verify_ipums_cps.py {{{'|'.join(commands)}}}")
    commands[arguments[0]]()


if __name__ == "__main__":
    main(sys.argv[1:])
```

Run: `.venv/bin/python -m pytest tests/test_verify_ipums_cps.py -v`
Expected: all PASS. Then lint and commit:

```bash
.venv/bin/ruff format verify_ipums_cps.py tests/test_verify_ipums_cps.py
.venv/bin/ruff check --fix verify_ipums_cps.py tests/test_verify_ipums_cps.py
git add verify_ipums_cps.py tests/test_verify_ipums_cps.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "Add the IPUMS verification probes for Phase 2

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: [KEY-GATED] Confirm sample coverage**

Prerequisite: the user has added `IPUMS_API_KEY` to `.env`. Then:

```bash
uv sync --group ipums
.venv/bin/python verify_ipums_cps.py samples
```

Expected: every year 1983–2025 has 12 months; the current year has however many months IPUMS has released. If a year prints `NO basic-monthly samples under pattern ...`, the sample-ID pattern is wrong: list a few IDs with `.venv/bin/python -c "import download_ipums_cps as d; print(sorted(d.available_sample_ids(d.make_client()))[:40])"`, correct `BASIC_MONTHLY_SAMPLE_PATTERN` / `DWS_SAMPLE_PATTERN`, and rerun.

- [ ] **Step 5: [KEY-GATED] Run the basic-monthly probe**

Run: `.venv/bin/python verify_ipums_cps.py basic-probe`

If IPUMS rejects the extract because a variable name does not exist, the exception message names it. Look it up in the IPUMS CPS variable browser (https://cps.ipums.org/cps-action/variables/group), correct `BASIC_MONTHLY_VARIABLES`, delete `data/raw/ipums/probe/basic/`, and rerun.

Read the output against these criteria:

| Check | Criterion | If it fails |
|---|---|---|
| `occ1990_valid_share` in the 2020 and latest-January rows | ≥ 0.99 | **STOP. Design-breaking** (spec § Must be verified). Do not continue Phase 2. Report to the user: Dorn has no occ2018 bridge, so the spine needs a new decision. |
| `relative_difference`, every row | within ±2% | A gap near a power of ten means implied decimals were misread. Otherwise **STOP** and report; the weights are not what the plan assumes. |
| `compwt_positive_share`, rows 1998 and later | ≥ 0.99 | Record it. Gates G1/G2 then fall back to `WTFINL` with a 2% tolerance, recorded as a deviation. |
| Household cluster decision | printed | Set `HOUSEHOLD_CLUSTER` to exactly what is printed. |
| `EMPSTAT` codes | 10 and 12 are the two employed codes | Correct `EMPLOYED_EMPSTAT_CODES`. |
| `CLASSWKR` codes | wage/salary codes are the 20s except armed forces and unpaid family work | Correct `WAGE_SALARY_CLASSWKR_CODES` from the printed labels. |
| Estimated full size | printed | If IPUMS's extract limits would refuse ~44 yearly extracts of this size, **STOP** and ask the user about the ASEC fallback (spec § Risks); it is a fidelity cost the user must accept. |

- [ ] **Step 6: [KEY-GATED] Run the DWS probe**

First confirm the supplement's variable names. Open the IPUMS CPS variable browser, choose the Displaced Worker Supplement group, and note: the supplement weight, the reason for job loss, years of tenure at the lost job, the raw occupation of the lost job, and any harmonized 1990-basis occupation of the lost job. Correct the `DWS_*` names in `ipums_cps_variables.py` to match, then:

Run: `.venv/bin/python verify_ipums_cps.py dws-probe`

| Check | Criterion | If it fails |
|---|---|---|
| Positive supplement weights in 1984 | present | Recorded as a deviation: 2b's floor rises to the first year present. |
| 2002 and 2004 | present or absent | Record either way. Absent leaves the 2001–04 hole open; no design change. |
| Displaced reason codes by label | exactly three codes | Set `DWS_DISPLACED_REASON_CODES` to the printed tuple. If not exactly three, read the printed labels and set the codes for closed/moved, insufficient work, and abolished position/shift by hand. |
| Tenure codes | the not-in-universe/missing codes are all above 60 | Correct `DWS_TENURE_VALID_MAXIMUM` so it sits below the smallest missing code. |
| Raw lost-job occupation | present in every probe year | Without it gate G3 cannot run. **STOP 2b** (Tasks 14–16) and report; 2a continues. |
| Harmonized lost-job `OCC1990` | present or absent | Set `DWS_LOST_JOB_OCC1990_VARIABLE` to its name, or leave `None`. |

- [ ] **Step 7: Write the verification record and flip the status**

Create `docs/superpowers/plans/2026-09-23-ipums-verification.md` with one table per step (4, 5, 6): the check, the observed value copied from the output, pass/fail, and the constant set in `ipums_cps_variables.py`. Include the date, the `ipumspy` version, and the IPUMS sample-ID range seen. Then set `VERIFICATION_STATUS = "verified"` in `ipums_cps_variables.py`.

Run: `.venv/bin/python -m pytest tests/test_download_ipums_cps.py tests/test_verify_ipums_cps.py -q`
Expected: PASS. The tests use the constants, so a renamed variable is still consistent.

```bash
git add ipums_cps_variables.py docs/superpowers/plans/2026-09-23-ipums-verification.md
PATH="$PWD/.venv/bin:$PATH" git commit -m "Record the IPUMS verification and confirm the variable registry

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 3: Reference seeds and their loaders

No key needed. Commits the static reference data the bridge and the DWS grouping read, following the `seeds/soc_crosswalks/` precedent.

**Files:**
- Create: `seeds/occ1990dd_crosswalks/occ{1980,1990,2000,2005,2010}_occ1990dd.csv`, `seeds/occ1990dd_crosswalks/README.md`
- Create: `seeds/cps_soc_crosswalks/2002-census-occupation-codes.xls`, `seeds/cps_soc_crosswalks/2010-occ-codes-with-crosswalk-from-2002-2011.xls`, `seeds/cps_soc_crosswalks/2018-occupation-code-list-and-crosswalk.xlsx`, `seeds/cps_soc_crosswalks/README.md`
- Create: `seeds/occ1990dd_groups.csv`
- Create: `occ1990dd_reference.py`
- Test: `tests/test_occ1990dd_reference.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces (`occ1990dd_reference`): `DORN_CROSSWALK_DIR`, `CENSUS_CODE_LIST_DIR`, `GROUPS_PATH`, `DORN_VINTAGES`, `UNCLASSIFIED_OCC1990DD = 999`, `OUTSIDE_GROUP_OCC1990DD = frozenset({905, 991})`, `CENSUS_CODE_LISTS`, `SOC_GENERATION_BY_CENSUS_VINTAGE`, `load_dorn_crosswalk(vintage: str) -> DataFrame[source_code:int, occ1990dd:int]`, `known_occ1990dd_codes() -> set[int]`, `load_census_code_list(vintage: str) -> DataFrame[census_code:int, census_title:str, soc_reference:str]`, `load_census_2018_to_2010() -> DataFrame[census_2018:int, census_2010:int]`, `soc_reference_prefix(reference: str) -> str | None`, `expand_soc_reference(reference: str, vocabulary: set[str]) -> set[str]`, `load_occ1990dd_groups() -> DataFrame[occ1990dd:int, dorn_group:str]`, `uncovered_codes(codes, groups_df) -> list[int]`.

- [ ] **Step 1: Fetch and commit the Census code lists unchanged**

```bash
mkdir -p seeds/cps_soc_crosswalks
UA="ai-exposure-research (${BLS_CONTACT_EMAIL:-research contact})"
BASE="https://www2.census.gov/programs-surveys/demo/guidance/industry-occupation"
for FILE in 2002-census-occupation-codes.xls 2010-occ-codes-with-crosswalk-from-2002-2011.xls 2018-occupation-code-list-and-crosswalk.xlsx; do
  curl -sf -A "$UA" -o "seeds/cps_soc_crosswalks/$FILE" "$BASE/$FILE"
done
ls -la seeds/cps_soc_crosswalks/
```

Expected: three files of ~95 KB, ~376 KB and ~160 KB.

Create `seeds/cps_soc_crosswalks/README.md`:

```markdown
# Census occupation code lists (CPS coding vintages → SOC)

Committed reference data, not a download step. Retrieved 2026-09-23 from
https://www2.census.gov/programs-surveys/demo/guidance/industry-occupation/ and
committed unchanged.

| File | CPS years using these codes | SOC generation of the reference column |
|---|---|---|
| `2002-census-occupation-codes.xls` (sheet `Occ Codes`) | 2003–2010 | SOC 2000 |
| `2010-occ-codes-with-crosswalk-from-2002-2011.xls` (sheet `2010OccCodeList`) | 2011–2019 | SOC 2010 |
| `2018-occupation-code-list-and-crosswalk.xlsx` (sheet `2018 Census Occ Code List`) | 2020 onward | SOC 2018 |

The 2018 file's sheet `2010 to 2018 Crosswalk ` (trailing space) also relates
2010 Census codes to 2018 Census codes; `occ1990dd_reference.load_census_2018_to_2010`
reads it.

Read by `occ1990dd_reference.py`. The SOC reference column mixes detailed codes,
broad groups ending in `0`, and wildcards containing `X`;
`occ1990dd_reference.expand_soc_reference` resolves all three to detailed codes.
```

- [ ] **Step 2: Fetch Dorn's crosswalks and commit them as CSV**

```bash
mkdir -p "$TMPDIR/dorn" seeds/occ1990dd_crosswalks
for VINTAGE in 1980 1990 2000 2005 2010; do
  curl -sf -o "$TMPDIR/dorn/occ${VINTAGE}.zip" "https://www.ddorn.net/data/occ${VINTAGE}_occ1990dd.zip"
  unzip -o -q "$TMPDIR/dorn/occ${VINTAGE}.zip" -d "$TMPDIR/dorn/occ${VINTAGE}"
done
.venv/bin/python - <<'PYTHON'
import glob, os
import pandas as pd
for vintage in ("1980", "1990", "2000", "2005", "2010"):
    stata_path = glob.glob(os.path.join(os.environ["TMPDIR"], "dorn", f"occ{vintage}", f"occ{vintage}_occ1990dd.dta"))[0]
    crosswalk_df = pd.read_stata(stata_path).rename(columns={"occ": "source_code"})
    crosswalk_df["source_code"] = crosswalk_df["source_code"].astype(int)
    crosswalk_df["occ1990dd"] = crosswalk_df["occ1990dd"].astype(int)
    crosswalk_df.sort_values("source_code").to_csv(f"seeds/occ1990dd_crosswalks/occ{vintage}_occ1990dd.csv", index=False)
    print(vintage, len(crosswalk_df))
PYTHON
```

Expected: `1980 504`, `1990 502`, `2000 471`, `2005 471`, `2010 489`.

Create `seeds/occ1990dd_crosswalks/README.md`:

```markdown
# occ1990dd crosswalks (David Dorn)

Committed reference data, not a download step. Retrieved 2026-09-23 from
https://www.ddorn.net/data.htm (files A4–A8) and converted from Stata `.dta` to
CSV with columns `source_code, occ1990dd`. Values are unchanged; `occ2010`'s
zero-padded string codes (`"0010"`) became integers (`10`).

Every source code maps to exactly one `occ1990dd` code. `999` means unclassified.

Please cite:

- occ1980, occ1990, occ2000, occ2005: David Autor and David Dorn. "The Growth of
  Low-Skill Service Jobs and the Polarization of the U.S. Labor Market."
  *American Economic Review* 103(5), 1553–1597, 2013.
- occ2010: David Autor. "Why Are There Still So Many Jobs? The History and Future
  of Workplace Automation." *Journal of Economic Perspectives* 29(3), 3–30, 2015.

`seeds/occ1990dd_groups.csv` is the occupation-group partition from Dorn's
`subfile_occ1990dd_occgroups.do` (file A9, Autor and Dorn 2013): the 16 level-2
non-service groups plus the 9 level-3 service subgroups, with `occ3_protect`
omitted because it is the union of `occ3_guard` and `occ2_firepol`. It covers
every `occ1990dd` code except 905 and 991, which fall in no group.
```

- [ ] **Step 3: Write the Dorn group partition seed**

Create `seeds/occ1990dd_groups.csv`. The `guard` group has two ranges, so two rows.

```csv
dorn_group,group_label,first_code,last_code
exec,"Executive, administrative and managerial",3,22
mgmtrel,Management related,23,37
prof,Professional specialty,43,200
tech,Technicians and related support,203,235
finsales,Financial sales and related,243,258
retsales,Retail sales,274,283
cleric,Administrative support,303,389
clean,"Housekeeping, cleaning, laundry",405,408
guard,Supervisors of guards; guards,415,415
guard,Supervisors of guards; guards,425,427
firepol,"Fire fighting, police, and correctional institutions",417,423
food,Food preparation and service,433,444
shealth,"Health service (dental assistants, health and nursing aides)",445,447
janitor,Building and grounds cleaning and maintenance,448,455
beauty,Personal appearance,457,458
recreation,Recreation and hospitality,459,467
child,Child care workers,468,468
othpers,Miscellaneous personal care and service,469,472
farmer,Farm operators and managers,473,475
otheragr,Other agricultural and related,479,498
mechanic,Mechanics and repairers,503,549
constr,Construction trades,558,599
mining,Extractive,614,617
product,Precision production,628,699
operator,"Machine operators, assemblers, and inspectors",703,799
transp,Transportation and material moving,803,889
```

- [ ] **Step 4: Write the failing tests**

Create `tests/test_occ1990dd_reference.py`:

```python
"""Tests for occ1990dd_reference.py — the committed Dorn, Census and group reference seeds."""

import pandas as pd
import pytest

from occ1990dd_reference import (
    DORN_VINTAGES,
    OUTSIDE_GROUP_OCC1990DD,
    expand_soc_reference,
    known_occ1990dd_codes,
    load_census_2018_to_2010,
    load_census_code_list,
    load_dorn_crosswalk,
    load_occ1990dd_groups,
    soc_reference_prefix,
    uncovered_codes,
)


class TestSocReferencePrefix:
    @pytest.mark.parametrize(
        ("reference", "expected_prefix"),
        [
            ("11-1011", "11-1011"),  # detailed: itself
            ("11-2020", "11-202"),  # broad group: trailing zero dropped
            ("11-2000", "11-2"),  # minor group
            ("15-113X", "15-113"),  # wildcard
            ("25-90XX", "25-90"),  # wildcard whose kept digits end in zero — the zero is real
            ("none", None),
            (" 13-11xx ", "13-11"),  # whitespace and lower-case x tolerated
        ],
    )
    def test_prefix_rules(self, reference, expected_prefix):
        assert soc_reference_prefix(reference) == expected_prefix


class TestExpandSocReference:
    vocabulary = {"11-1011", "11-2021", "11-2022", "11-2031", "25-9021", "25-9031", "25-1011"}

    def test_detailed_code_expands_to_itself(self):
        assert expand_soc_reference("11-1011", self.vocabulary) == {"11-1011"}

    def test_broad_group_expands_to_its_detailed_members(self):
        assert expand_soc_reference("11-2020", self.vocabulary) == {"11-2021", "11-2022"}

    def test_wildcard_keeps_a_zero_before_the_x(self):
        assert expand_soc_reference("25-90XX", self.vocabulary) == {"25-9021", "25-9031"}

    def test_none_expands_to_nothing(self):
        assert expand_soc_reference("none", self.vocabulary) == set()


class TestDornCrosswalks:
    @pytest.mark.parametrize(("vintage", "expected_rows"), [("1980", 504), ("1990", 502), ("2000", 471), ("2005", 471), ("2010", 489)])
    def test_row_counts_match_the_published_files(self, vintage, expected_rows):
        assert len(load_dorn_crosswalk(vintage)) == expected_rows

    @pytest.mark.parametrize("vintage", DORN_VINTAGES)
    def test_every_source_code_maps_to_exactly_one_occ1990dd(self, vintage):
        crosswalk_df = load_dorn_crosswalk(vintage)
        assert not crosswalk_df["source_code"].duplicated().any()

    def test_known_code_universe_is_333_excluding_unclassified(self):
        codes = known_occ1990dd_codes()
        assert len(codes) == 333
        assert 999 not in codes


class TestCensusCodeLists:
    @pytest.mark.parametrize(("vintage", "expected_codes"), [("2002", 510), ("2010", 540), ("2018", 570)])
    def test_code_counts(self, vintage, expected_codes):
        code_list_df = load_census_code_list(vintage)
        assert len(code_list_df) == expected_codes
        assert not code_list_df["census_code"].duplicated().any()

    def test_chief_executives_is_code_10_in_every_vintage(self):
        for vintage in ("2002", "2010", "2018"):
            code_list_df = load_census_code_list(vintage)
            assert code_list_df.loc[code_list_df["census_code"] == 10, "soc_reference"].iloc[0] == "11-1011"

    def test_2018_to_2010_covers_every_2018_code_once(self):
        crosswalk_df = load_census_2018_to_2010()
        codes_2018 = set(load_census_code_list("2018")["census_code"])
        assert set(crosswalk_df["census_2018"]) == codes_2018
        assert not crosswalk_df["census_2018"].duplicated().any()


class TestGroups:
    def test_twenty_five_groups(self):
        assert load_occ1990dd_groups()["dorn_group"].nunique() == 25

    def test_every_known_code_but_905_and_991_is_in_exactly_one_group(self):
        groups_df = load_occ1990dd_groups()
        assert not groups_df["occ1990dd"].duplicated().any()
        assert set(uncovered_codes(known_occ1990dd_codes(), groups_df)) == set(OUTSIDE_GROUP_OCC1990DD)

    def test_uncovered_codes_reports_codes_outside_every_group(self):
        groups_df = pd.DataFrame({"occ1990dd": [4, 22], "dorn_group": ["exec", "exec"]})
        assert uncovered_codes({4, 22, 905}, groups_df) == [905]
```

- [ ] **Step 5: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_occ1990dd_reference.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'occ1990dd_reference'`.

- [ ] **Step 6: Create `occ1990dd_reference.py`**

```python
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
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_occ1990dd_reference.py -v`
Expected: all PASS.

- [ ] **Step 8: Lint and commit**

```bash
.venv/bin/ruff format occ1990dd_reference.py tests/test_occ1990dd_reference.py
.venv/bin/ruff check --fix occ1990dd_reference.py tests/test_occ1990dd_reference.py
git add seeds/occ1990dd_crosswalks seeds/cps_soc_crosswalks seeds/occ1990dd_groups.csv occ1990dd_reference.py tests/test_occ1990dd_reference.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "Commit the occ1990dd, Census code-list and Dorn group reference seeds

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 4: The chain and its split weights

No key needed. Builds the published-crosswalk chain from `occ1990dd` to SOC 2018 (spec § The bridge) and the OEWS-2022 split weights.

**Files:**
- Create: `occ1990dd_soc_bridge.py`
- Test: `tests/test_occ1990dd_soc_bridge.py`

**Interfaces:**
- Consumes: `occ1990dd_reference.load_dorn_crosswalk`, `load_census_code_list`, `expand_soc_reference`, `SOC_GENERATION_BY_CENSUS_VINTAGE`, `UNCLASSIFIED_OCC1990DD` (Task 3); `harmonize_soc.soc_vocabularies()`, `load_soc_2000_to_2010()`, `load_soc_2010_to_2018()` (existing; edges have `from_code`, `to_code`).
- Produces: `SocTables` (frozen dataclass: `vocabularies: dict[str, set[str]]`, `soc2000_to_soc2010: dict[str, set[str]]`, `soc2010_to_soc2018: dict[str, set[str]]`), `load_soc_tables() -> SocTables`, `to_soc_2018(soc_codes: set[str], generation: str, soc_tables: SocTables) -> set[str]`, `census_code_members(code_list_df, census_vintage: str, soc_tables) -> DataFrame[census_code, soc_2018_code]`, `build_chain_edges(dorn_2010_df, census_2010_members_df) -> DataFrame[occ1990dd, census_code, soc_2018_code]`, `equal_division_weights(edges_df, owner_column: str, anchor_employment: pd.Series) -> DataFrame[owner_column, soc_2018_code, weight]`, `load_anchor_employment(trends_path, anchor_year="2022") -> pd.Series`, `build_bridge_weights(anchor_employment, soc_tables=None) -> DataFrame[occ1990dd, soc_2018_code, weight]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_occ1990dd_soc_bridge.py`:

```python
"""Tests for occ1990dd_soc_bridge.py — the chain from occ1990dd to SOC 2018, its weights and its scores."""

import pandas as pd
import pytest

from occ1990dd_soc_bridge import (
    SocTables,
    build_bridge_weights,
    build_chain_edges,
    census_code_members,
    equal_division_weights,
    load_anchor_employment,
    load_soc_tables,
    to_soc_2018,
)

FAKE_TABLES = SocTables(
    vocabularies={
        "soc2000": {"11-2011", "15-1021"},
        "soc2010": {"11-2011", "11-2021", "11-2022", "15-1131"},
        "soc2018": {"11-2011", "11-2021", "11-2022", "15-1251"},
    },
    soc2000_to_soc2010={"11-2011": {"11-2011"}, "15-1021": {"15-1131"}},
    soc2010_to_soc2018={"11-2011": {"11-2011"}, "11-2021": {"11-2021"}, "11-2022": {"11-2022"}, "15-1131": {"15-1251"}},
)


class TestToSoc2018:
    def test_soc_2018_codes_pass_through(self):
        assert to_soc_2018({"11-2021"}, "soc2018", FAKE_TABLES) == {"11-2021"}

    def test_soc_2000_goes_through_2010(self):
        assert to_soc_2018({"15-1021"}, "soc2000", FAKE_TABLES) == {"15-1251"}

    def test_empty_input_gives_empty_output(self):
        assert to_soc_2018(set(), "soc2010", FAKE_TABLES) == set()

    def test_unknown_generation_raises(self):
        with pytest.raises(ValueError):
            to_soc_2018({"11-2011"}, "soc1990", FAKE_TABLES)


class TestCensusCodeMembers:
    def test_a_broad_reference_expands_then_maps_to_2018(self):
        code_list_df = pd.DataFrame({"census_code": [50], "census_title": ["Marketing and sales managers"], "soc_reference": ["11-2020"]})
        members_df = census_code_members(code_list_df, "2010", FAKE_TABLES)
        assert set(members_df["soc_2018_code"]) == {"11-2021", "11-2022"}

    def test_a_none_reference_contributes_no_rows(self):
        code_list_df = pd.DataFrame({"census_code": [9840], "census_title": ["Armed forces"], "soc_reference": ["none"]})
        assert census_code_members(code_list_df, "2010", FAKE_TABLES).empty


class TestBuildChainEdges:
    def test_joins_dorn_codes_to_census_members_and_drops_unclassified(self):
        dorn_2010_df = pd.DataFrame({"source_code": [50, 9999], "occ1990dd": [13, 999]})
        members_df = pd.DataFrame({"census_code": [50, 50, 9999], "soc_2018_code": ["11-2021", "11-2022", "55-1011"]})
        chain_df = build_chain_edges(dorn_2010_df, members_df)
        assert set(chain_df["occ1990dd"]) == {13}
        assert set(chain_df["soc_2018_code"]) == {"11-2021", "11-2022"}


class TestEqualDivisionWeights:
    def test_weights_sum_to_one_within_each_owner(self):
        edges_df = pd.DataFrame({"occ1990dd": [1, 1, 2], "soc_2018_code": ["A", "B", "C"]})
        weights_df = equal_division_weights(edges_df, "occ1990dd", pd.Series({"A": 30.0, "B": 10.0, "C": 5.0}))
        assert weights_df.groupby("occ1990dd")["weight"].sum().tolist() == pytest.approx([1.0, 1.0])
        assert weights_df.set_index("soc_2018_code").loc["A", "weight"] == pytest.approx(0.75)

    def test_a_code_shared_by_two_owners_gives_each_half_its_employment(self):
        # Unit 1 = {A (shared), B}; unit 2 = {A (shared)}. A's 40 splits 20/20, so unit 1 is A 20 : B 20.
        edges_df = pd.DataFrame({"occ1990dd": [1, 1, 2], "soc_2018_code": ["A", "B", "A"]})
        weights_df = equal_division_weights(edges_df, "occ1990dd", pd.Series({"A": 40.0, "B": 20.0}))
        unit_one = weights_df[weights_df["occ1990dd"] == 1].set_index("soc_2018_code")["weight"]
        assert unit_one["A"] == pytest.approx(0.5)
        assert unit_one["B"] == pytest.approx(0.5)

    def test_an_owner_with_no_oews_employment_weights_members_equally(self):
        edges_df = pd.DataFrame({"occ1990dd": [7, 7, 7], "soc_2018_code": ["X", "Y", "Z"]})
        weights_df = equal_division_weights(edges_df, "occ1990dd", pd.Series(dtype=float))
        assert weights_df["weight"].tolist() == pytest.approx([1 / 3, 1 / 3, 1 / 3])


class TestAnchorEmployment:
    def test_reads_2022_employment_keyed_by_soc_code_and_drops_non_numeric(self, tmp_path):
        trends_path = tmp_path / "bls_trends.csv"
        pd.DataFrame({"OCC_CODE": ["11-1011", "11-1021", "11-1031"], "TOT_EMP_2022": [100, "**", 50]}).to_csv(trends_path, index=False)
        anchor_employment = load_anchor_employment(str(trends_path))
        assert anchor_employment.to_dict() == {"11-1011": 100.0, "11-1031": 50.0}


@pytest.fixture(scope="module")
def bridge_weights_df():
    """The real chain from the committed seeds, with uniform employment so bls_trends.csv is not needed."""
    soc_tables = load_soc_tables()
    uniform_employment = pd.Series(1.0, index=sorted(soc_tables.vocabularies["soc2018"]))
    return build_bridge_weights(uniform_employment, soc_tables)


class TestRealChain:
    def test_every_unit_weight_sums_to_one(self, bridge_weights_df):
        assert bridge_weights_df.groupby("occ1990dd")["weight"].sum().to_numpy() == pytest.approx(1.0)

    def test_the_chain_reaches_nearly_every_occ1990dd_code(self, bridge_weights_df):
        # 328 of the 333 known codes on 2026-09-23; a few exist only in pre-2010 vintages.
        assert bridge_weights_df["occ1990dd"].nunique() >= 320

    def test_chief_executives_reach_soc_chief_executives(self, bridge_weights_df):
        # occ1990dd 4 is chief executives and general administrators (Dorn).
        assert "11-1011" in set(bridge_weights_df.loc[bridge_weights_df["occ1990dd"] == 4, "soc_2018_code"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_occ1990dd_soc_bridge.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'occ1990dd_soc_bridge'`.

- [ ] **Step 3: Create `occ1990dd_soc_bridge.py`**

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_occ1990dd_soc_bridge.py -v`
Expected: all PASS.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/ruff format occ1990dd_soc_bridge.py tests/test_occ1990dd_soc_bridge.py
.venv/bin/ruff check --fix occ1990dd_soc_bridge.py tests/test_occ1990dd_soc_bridge.py
git add occ1990dd_soc_bridge.py tests/test_occ1990dd_soc_bridge.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "Chain occ1990dd to SOC 2018 through published crosswalks

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 5: Scoring occ1990dd units

No key needed. Turns bridge weights into per-unit scores, the labeled share, and a re-derived `dominant_demand`, plus the detailed composition-stability proxy.

**Files:**
- Modify: `occ1990dd_soc_bridge.py`
- Test: `tests/test_occ1990dd_soc_bridge.py`

**Interfaces:**
- Consumes: `equal_division_weights` output shape (Task 4); `synthesize_impacts.attach_dominant_demand`, `synthesize_impacts.DEMAND_TYPE_PCT_COLUMNS`.
- Produces: `PCT_COLUMNS: list[str]`, `LABEL_SCORE_COLUMN = "composition_net_change"`, `SOC_SCORE_COLUMNS: list[str]`, `DISPLACEMENT_SCORE_COLUMNS: list[str]`, `score_units(weights_df, owner_column: str, soc_scores_df, score_columns: list[str]) -> DataFrame[owner_column, *score_columns, labeled_share, pct_*, dominant_demand, dominant_strength]`, `load_soc_scores(composition_report_path, dynamic_report_path, anthropic_path) -> tuple[DataFrame, list[str]]`, `occ1990dd_composition_stability(weights_df, occupation_trends_df, earliest_year="1999") -> DataFrame[occ1990dd, stable_share]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_occ1990dd_soc_bridge.py`:

```python
from occ1990dd_soc_bridge import load_soc_scores, occ1990dd_composition_stability, score_units  # noqa: E402


def _soc_scores(rows):
    return pd.DataFrame(rows, columns=["OCC_CODE", "composition_net_change", "pct_bounded", "pct_unbounded", "pct_adversarial"])


class TestScoreUnits:
    def test_score_is_the_weighted_mean_over_labeled_members_only(self):
        weights_df = pd.DataFrame({"occ1990dd": [1, 1, 1], "soc_2018_code": ["A", "B", "C"], "weight": [0.5, 0.25, 0.25]})
        soc_scores_df = _soc_scores([["A", 0.2, 1.0, 0.0, 0.0], ["B", 0.8, 0.0, 1.0, 0.0]])  # C unlabeled
        unit_df = score_units(weights_df, "occ1990dd", soc_scores_df, ["composition_net_change"])
        # Renormalised over A and B: (0.5*0.2 + 0.25*0.8) / 0.75
        assert unit_df.loc[0, "composition_net_change"] == pytest.approx(0.4)
        assert unit_df.loc[0, "labeled_share"] == pytest.approx(0.75)

    def test_dominant_demand_is_rederived_from_the_blended_composition(self):
        """A unit whose largest member is Bounded can still be Unbounded-dominant once blended.

        Regression guard for the Chief Executives failure mode: the label must come
        from the aggregated pct_* columns, never be carried from a member.
        """
        weights_df = pd.DataFrame({"occ1990dd": [1, 1, 1], "soc_2018_code": ["A", "B", "C"], "weight": [0.4, 0.3, 0.3]})
        soc_scores_df = _soc_scores([["A", 0.1, 0.6, 0.4, 0.0], ["B", 0.1, 0.1, 0.9, 0.0], ["C", 0.1, 0.1, 0.9, 0.0]])
        unit_df = score_units(weights_df, "occ1990dd", soc_scores_df, ["composition_net_change"])
        assert unit_df.loc[0, "dominant_demand"] == "Unbounded"
        assert unit_df.loc[0, "pct_unbounded"] == pytest.approx(0.4 * 0.4 + 0.3 * 0.9 + 0.3 * 0.9)

    def test_a_unit_with_no_labeled_member_has_nan_score_and_zero_labeled_share(self):
        weights_df = pd.DataFrame({"occ1990dd": [9], "soc_2018_code": ["Z"], "weight": [1.0]})
        unit_df = score_units(weights_df, "occ1990dd", _soc_scores([["A", 0.2, 1.0, 0.0, 0.0]]), ["composition_net_change"])
        assert pd.isna(unit_df.loc[0, "composition_net_change"])
        assert unit_df.loc[0, "labeled_share"] == 0.0


class TestLoadSocScores:
    def test_renames_the_two_net_change_columns_apart(self, tmp_path):
        composition_path, dynamic_path = tmp_path / "composition.csv", tmp_path / "dynamic.csv"
        pd.DataFrame(
            {
                "OCC_CODE": ["11-1011"],
                "net_employment_change": [0.1],
                "gross_displacement": [0.02],
                "pct_bounded": [0.5],
                "pct_unbounded": [0.5],
                "pct_adversarial": [0.0],
            }
        ).to_csv(composition_path, index=False)
        pd.DataFrame(
            {"OCC_CODE": ["11-1011"], "net_employment_change": [0.3], "occupation_exposure": [0.4], "gross_displacement": [0.05]}
        ).to_csv(dynamic_path, index=False)
        soc_scores_df, score_columns = load_soc_scores(str(composition_path), str(dynamic_path), str(tmp_path / "absent.csv"))
        assert soc_scores_df.loc[0, "composition_net_change"] == pytest.approx(0.1)
        assert soc_scores_df.loc[0, "net_employment_change"] == pytest.approx(0.3)
        assert soc_scores_df.loc[0, "composition_gross_displacement"] == pytest.approx(0.02)
        assert soc_scores_df.loc[0, "dynamic_gross_displacement"] == pytest.approx(0.05)
        assert score_columns == ["composition_net_change", "net_employment_change", "occupation_exposure"]


class TestCompositionStability:
    def test_stable_share_is_the_weight_on_members_oews_published_in_1999(self):
        weights_df = pd.DataFrame({"occ1990dd": [1, 1], "soc_2018_code": ["A", "B"], "weight": [0.7, 0.3]})
        occupation_trends_df = pd.DataFrame({"OCC_CODE": ["A", "B"], "TOT_EMP_1999": [100.0, None]})
        stability_df = occ1990dd_composition_stability(weights_df, occupation_trends_df)
        assert stability_df.loc[0, "stable_share"] == pytest.approx(0.7)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_occ1990dd_soc_bridge.py -v`
Expected: FAIL — `ImportError: cannot import name 'load_soc_scores'`.

- [ ] **Step 3: Implement**

Add to the imports of `occ1990dd_soc_bridge.py`:

```python
import os

from synthesize_impacts import DEMAND_TYPE_PCT_COLUMNS, attach_dominant_demand
```

Append to `occ1990dd_soc_bridge.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_occ1990dd_soc_bridge.py -v`
Expected: all PASS.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/ruff format occ1990dd_soc_bridge.py tests/test_occ1990dd_soc_bridge.py
.venv/bin/ruff check --fix occ1990dd_soc_bridge.py tests/test_occ1990dd_soc_bridge.py
git add occ1990dd_soc_bridge.py tests/test_occ1990dd_soc_bridge.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "Score occ1990dd units over their labeled SOC members

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 6: Tabulating one year of basic-monthly microdata

No key needed; tested on synthetic person records. The core of the local build (spec § Acquisition and tabulation).

**Files:**
- Create: `cps_detailed_panel.py`
- Test: `tests/test_cps_detailed_panel.py`

**Interfaces:**
- Consumes: `ipums_cps_variables` (Task 1); `occ1990dd_reference.soc_reference_prefix` (Task 3); `composition_displacement_validation.soc_major_to_dws_group()` (existing).
- Produces: `UNIVERSES = ("all_employed", "wage_salary")`, `TABULATION_COLUMNS`, `PANEL_COLUMNS` (= `TABULATION_COLUMNS + ["sampling_variance"]`), `CODING_BLOCKS: dict[str, tuple[int, int, str]]`, `coding_block_for_year(year) -> str | None`, `select_civilian_employed(person_df)`, `attach_occ1990dd(person_df, spine: dict[int, int], weight_column="WTFINL") -> tuple[DataFrame, float]`, `universe_mask(person_df, universe) -> pd.Series`, `household_cluster_ids(person_df) -> pd.Series`, `tabulate_year(spine_df, year, weight_column="WTFINL") -> DataFrame[TABULATION_COLUMNS]`, `tabulate_crosstab(spine_df, year, weight_column="WTFINL") -> DataFrame[year, coding_block, occ1990dd, census_code, employed_thousands]`, `collapse_crosstab(yearly_crosstab_df) -> DataFrame[coding_block, occ1990dd, census_code, employed_thousands]`, `census_code_ten_group_lookup(code_list_df) -> dict[int, str]`, `tabulate_ten_groups_direct(employed_df, year, ten_group_lookup, weight_column) -> DataFrame[year, cps_group, employed_thousands, months_observed]`, `tabulate_total(employed_df, year, weight_column) -> dict`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cps_detailed_panel.py`:

```python
"""Tests for cps_detailed_panel.py — the local build of the detailed CPS panel, on synthetic microdata."""

import pandas as pd
import pytest

import cps_detailed_panel
import ipums_cps_variables as ipums_variables
from cps_detailed_panel import (
    attach_occ1990dd,
    census_code_ten_group_lookup,
    coding_block_for_year,
    collapse_crosstab,
    select_civilian_employed,
    tabulate_crosstab,
    tabulate_ten_groups_direct,
    tabulate_total,
    tabulate_year,
)


def person_records(rows):
    """rows: dicts overriding a default employed, wage-and-salary adult in January 2010."""
    defaults = {
        "YEAR": 2010,
        "MONTH": 1,
        "SERIAL": 1,
        "CPSID": 1,
        "PERNUM": 1,
        "WTFINL": 1000.0,
        "COMPWT": 1000.0,
        "AGE": 40,
        "EMPSTAT": 10,
        "OCC": 10,
        "OCC1990": 4,
        "CLASSWKR": 21,
    }
    return pd.DataFrame([{**defaults, **row} for row in rows])


@pytest.fixture(autouse=True)
def linked_households(monkeypatch):
    monkeypatch.setattr(ipums_variables, "HOUSEHOLD_CLUSTER", "CPSID")


class TestCodingBlocks:
    @pytest.mark.parametrize(
        ("year", "block"), [(2002, None), (2003, "2003_2010"), (2011, "2011_2019"), (2020, "2020_2026"), (2026, "2020_2026")]
    )
    def test_year_to_block(self, year, block):
        assert coding_block_for_year(year) == block


class TestSelectCivilianEmployed:
    def test_keeps_only_employed_adults(self):
        person_df = person_records([{}, {"EMPSTAT": 21}, {"AGE": 15}, {"EMPSTAT": 12}, {"EMPSTAT": 1}])
        assert len(select_civilian_employed(person_df)) == 2


class TestAttachOcc1990dd:
    def test_maps_through_the_spine_and_reports_the_unmapped_weighted_share(self):
        person_df = person_records([{"OCC1990": 4}, {"OCC1990": 4}, {"OCC1990": 777, "WTFINL": 2000.0}])
        spine_df, unmapped_share = attach_occ1990dd(person_df, {4: 4})
        assert len(spine_df) == 2
        assert unmapped_share == pytest.approx(0.5)


class TestTabulateYear:
    def test_annual_employment_is_the_mean_of_monthly_weighted_totals(self):
        person_df = person_records([{"MONTH": 1, "occ1990dd": 4}, {"MONTH": 1, "occ1990dd": 4, "CPSID": 2}, {"MONTH": 2, "occ1990dd": 4}])
        panel_df = tabulate_year(person_df, 2010)
        all_employed = panel_df[panel_df["universe"] == "all_employed"].iloc[0]
        assert all_employed["employed_thousands"] == pytest.approx(1.5)  # (2000 + 1000) / 2 months / 1000
        assert all_employed["person_months"] == 3
        assert all_employed["distinct_households"] == 2
        assert all_employed["months_observed"] == 2

    def test_wage_salary_excludes_the_self_employed(self):
        person_df = person_records([{"occ1990dd": 4}, {"occ1990dd": 4, "CLASSWKR": 13, "CPSID": 2}])
        panel_df = tabulate_year(person_df, 2010).set_index("universe")
        assert panel_df.loc["all_employed", "employed_thousands"] == pytest.approx(2.0)
        assert panel_df.loc["wage_salary", "employed_thousands"] == pytest.approx(1.0)

    def test_distinct_households_is_nan_when_households_do_not_link(self, monkeypatch):
        monkeypatch.setattr(ipums_variables, "HOUSEHOLD_CLUSTER", "household_month")
        panel_df = tabulate_year(person_records([{"occ1990dd": 4}]), 2010)
        assert panel_df["distinct_households"].isna().all()


class TestCrosstab:
    def test_crosstab_is_keyed_by_block_unit_and_raw_code(self):
        person_df = person_records([{"occ1990dd": 4, "OCC": 10}, {"occ1990dd": 4, "OCC": 20}])
        crosstab_df = tabulate_crosstab(person_df, 2010)
        assert set(crosstab_df["census_code"]) == {10, 20}
        assert set(crosstab_df["coding_block"]) == {"2003_2010"}

    def test_years_before_2003_contribute_nothing(self):
        assert tabulate_crosstab(person_records([{"YEAR": 1995, "occ1990dd": 4}]), 1995).empty

    def test_collapse_sums_years_within_a_block(self):
        yearly_df = pd.DataFrame(
            {
                "year": [2003, 2004],
                "coding_block": ["2003_2010"] * 2,
                "occ1990dd": [4, 4],
                "census_code": [10, 10],
                "employed_thousands": [1.0, 2.0],
            }
        )
        assert collapse_crosstab(yearly_df)["employed_thousands"].tolist() == [3.0]


class TestTenGroupsDirect:
    def test_raw_codes_map_to_groups_through_the_soc_major(self):
        code_list_df = pd.DataFrame(
            {"census_code": [10, 4700], "census_title": ["Chief executives", "Retail supervisors"], "soc_reference": ["11-1011", "41-1011"]}
        )
        lookup = census_code_ten_group_lookup(code_list_df)
        assert lookup == {
            10: "management, business, and financial operations occupations",
            4700: "sales and related occupations",
        }
        employed_df = person_records([{"OCC": 10}, {"OCC": 4700}, {"OCC": 9999}])
        groups_df = tabulate_ten_groups_direct(employed_df, 2010, lookup, "COMPWT").set_index("cps_group")
        assert groups_df.loc["sales and related occupations", "employed_thousands"] == pytest.approx(1.0)
        assert len(groups_df) == 2


class TestTotal:
    def test_total_is_the_monthly_mean_in_thousands(self):
        employed_df = person_records([{"MONTH": 1}, {"MONTH": 2}, {"MONTH": 2}])
        assert tabulate_total(employed_df, 2010, "WTFINL")["total_thousands"] == pytest.approx(1.5)


def test_module_does_not_import_ipumspy_at_top_level():
    assert "ipumspy" not in cps_detailed_panel.__dict__
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_cps_detailed_panel.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cps_detailed_panel'`.

- [ ] **Step 3: Create `cps_detailed_panel.py`**

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_cps_detailed_panel.py -v`
Expected: all PASS.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/ruff format cps_detailed_panel.py tests/test_cps_detailed_panel.py
.venv/bin/ruff check --fix cps_detailed_panel.py tests/test_cps_detailed_panel.py
git add cps_detailed_panel.py tests/test_cps_detailed_panel.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "Tabulate basic-monthly microdata onto occ1990dd in two universes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: The household-cluster bootstrap

No key needed. Implements spec § Sampling variance: one method for every year, Poisson(1) weights per household cluster, fixed seed.

**Files:**
- Modify: `cps_detailed_panel.py`
- Test: `tests/test_cps_detailed_panel.py`

**Interfaces:**
- Consumes: `household_cluster_ids`, `universe_mask`, `UNIVERSES` (Task 6).
- Produces: `BOOTSTRAP_REPLICATES = 200`, `BOOTSTRAP_SEED = 20260923`, `bootstrap_group_variance(group_codes, values, cluster_ids, scale, replicates=..., seed=...) -> pd.Series` (index = group code), `cluster_bootstrap_variance(spine_df, weight_column="WTFINL", replicates=..., seed=...) -> DataFrame[occ1990dd, universe, sampling_variance]`. Task 14 reuses `bootstrap_group_variance` for the DWS panel.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cps_detailed_panel.py`:

```python
import numpy as np  # noqa: E402

from cps_detailed_panel import bootstrap_group_variance, cluster_bootstrap_variance  # noqa: E402


class TestBootstrapGroupVariance:
    def test_matches_the_analytic_poisson_variance(self):
        # 400 single-record clusters of weight 1000, scaled to thousands: total = sum(w_i), Var = 400.
        cluster_count = 400
        variance = bootstrap_group_variance(
            np.full(cluster_count, 7), np.full(cluster_count, 1000.0), np.arange(cluster_count), scale=1 / 1000.0, replicates=4000
        )
        assert variance.loc[7] == pytest.approx(400.0, rel=0.10)

    def test_records_in_one_household_move_together(self):
        # 200 clusters of two records each: each cluster total is 2, so Var = 200 * 2**2 = 800, not 400.
        cluster_ids = np.repeat(np.arange(200), 2)
        variance = bootstrap_group_variance(np.full(400, 7), np.full(400, 1000.0), cluster_ids, scale=1 / 1000.0, replicates=4000)
        assert variance.loc[7] == pytest.approx(800.0, rel=0.10)

    def test_is_deterministic_under_a_fixed_seed(self):
        arguments = (np.array([1, 1, 2]), np.array([1.0, 2.0, 3.0]), np.array([0, 1, 2]), 1.0)
        first = bootstrap_group_variance(*arguments, replicates=60, seed=5)
        second = bootstrap_group_variance(*arguments, replicates=60, seed=5)
        pd.testing.assert_series_equal(first, second)


class TestClusterBootstrapVariance:
    def test_one_row_per_unit_and_universe(self):
        person_df = person_records(
            [{"occ1990dd": 4, "CPSID": household} for household in range(30)]
            + [{"occ1990dd": 8, "CPSID": 100 + household, "CLASSWKR": 13} for household in range(30)]
        )
        variance_df = cluster_bootstrap_variance(person_df, replicates=50)
        assert set(zip(variance_df["occ1990dd"], variance_df["universe"])) == {(4, "all_employed"), (8, "all_employed"), (4, "wage_salary")}
        assert (variance_df["sampling_variance"] > 0).all()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_cps_detailed_panel.py -v`
Expected: FAIL — `ImportError: cannot import name 'bootstrap_group_variance'`.

- [ ] **Step 3: Implement**

Add `from scipy import sparse` to the imports of `cps_detailed_panel.py`, then append:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_cps_detailed_panel.py -v`
Expected: all PASS.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/ruff format cps_detailed_panel.py tests/test_cps_detailed_panel.py
.venv/bin/ruff check --fix cps_detailed_panel.py tests/test_cps_detailed_panel.py
git add cps_detailed_panel.py tests/test_cps_detailed_panel.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "Estimate cell variance with a household-cluster bootstrap

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 8: The year build, gates G1/G2/G5/G6, and promotion

Code and tests need no key. Steps 6–9 are **[KEY-GATED]**: they run the real build and commit the seeds.

**Files:**
- Modify: `cps_detailed_panel.py`
- Modify: `CLAUDE.md` (seeds-convention paragraph, Step 9)
- Test: `tests/test_cps_detailed_panel.py`
- Create (Step 9): `seeds/cps_detailed_occupation_panel.csv`, `seeds/cps_detailed_occ_crosstab.csv`, `seeds/cps_detailed_gates.csv`

**Interfaces:**
- Consumes: Tasks 6–7 functions; `download_ipums_cps.RAW_DIR`, `extract_is_downloaded`, `read_extract` (Task 1); `occ1990dd_reference.load_dorn_crosswalk`, `load_census_code_list`, `load_occ1990dd_groups`, `uncovered_codes` (Task 3); `historical_displacement.fetch_annual_means`.
- Produces: `SEED_PATH`, `CROSSTAB_SEED_PATH`, `GATES_SEED_PATH`, `GATE_COLUMNS = ["gate", "scope", "observed", "threshold", "gated", "passed"]`, `GateFailureError`, `gate_g1(ten_group_df, published_panel_df) -> DataFrame`, `gate_g2(totals_df, published_totals: pd.Series | None) -> DataFrame`, `gate_g5(panel_df, groups_df) -> DataFrame`, `gate_g6(unmapped_by_year: pd.Series) -> DataFrame`, `all_gates_pass(gates_df, required_gates) -> bool`, `promote_rebuilt(promotions: dict[str, str], gates_path: str, required_gates) -> None`, `build_rebuilt_tables(first_year, last_year, ...) -> DataFrame` (the gate table). Task 15 reuses `GATE_COLUMNS`, `GateFailureError`, `all_gates_pass`, `promote_rebuilt`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cps_detailed_panel.py`:

```python
from cps_detailed_panel import (  # noqa: E402
    GateFailureError,
    all_gates_pass,
    build_rebuilt_tables,
    gate_g1,
    gate_g2,
    gate_g5,
    gate_g6,
    promote_rebuilt,
)

SALES = "sales and related occupations"


def _published(rows):
    return pd.DataFrame(rows, columns=["year", "cps_group", "employed_thousands", "months_observed"])


class TestGateG1:
    def test_a_complete_year_within_one_percent_passes(self):
        rebuilt_df = pd.DataFrame({"year": [2010], "cps_group": [SALES], "employed_thousands": [100.5], "months_observed": [12]})
        published_df = _published([[2010, SALES, 100.0, None], [2011, SALES, 100.0, None]])
        gate_df = gate_g1(rebuilt_df, published_df)
        assert gate_df["gated"].tolist() == [True]
        assert gate_df["passed"].tolist() == [True]

    def test_a_two_percent_gap_fails(self):
        rebuilt_df = pd.DataFrame({"year": [2010], "cps_group": [SALES], "employed_thousands": [102.0], "months_observed": [12]})
        gate_df = gate_g1(rebuilt_df, _published([[2010, SALES, 100.0, None], [2011, SALES, 100.0, None]]))
        assert gate_df["passed"].tolist() == [False]

    def test_the_latest_published_year_without_a_month_count_is_not_gated(self):
        # A year with no month count is complete only if a later published year exists.
        rebuilt_df = pd.DataFrame({"year": [2011], "cps_group": [SALES], "employed_thousands": [150.0], "months_observed": [12]})
        gate_df = gate_g1(rebuilt_df, _published([[2010, SALES, 100.0, None], [2011, SALES, 100.0, None]]))
        assert gate_df["gated"].tolist() == [False]

    def test_partial_rebuilt_years_are_reported_not_gated(self):
        rebuilt_df = pd.DataFrame({"year": [2010], "cps_group": [SALES], "employed_thousands": [150.0], "months_observed": [8]})
        gate_df = gate_g1(rebuilt_df, _published([[2010, SALES, 100.0, None], [2011, SALES, 100.0, None]]))
        assert gate_df["gated"].tolist() == [False]


class TestGateG2:
    def test_years_from_1998_are_gated_and_earlier_years_reported(self):
        totals_df = pd.DataFrame({"year": [1997, 1998], "total_thousands": [130.0, 100.5], "months_observed": [12, 12]})
        gate_df = gate_g2(totals_df, pd.Series({1997: 100.0, 1998: 100.0}))
        assert gate_df["gated"].tolist() == [False, True]
        assert bool(gate_df["passed"].iloc[1])

    def test_an_unavailable_published_series_fails_rather_than_passing_vacuously(self):
        totals_df = pd.DataFrame({"year": [2010], "total_thousands": [100.0], "months_observed": [12]})
        gate_df = gate_g2(totals_df, None)
        assert gate_df["gated"].tolist() == [True]
        assert gate_df["passed"].tolist() == [False]


class TestGateG5AndG6:
    def test_g5_fails_when_an_employed_code_is_in_no_group(self):
        panel_df = pd.DataFrame({"occ1990dd": [4, 905], "employed_thousands": [10.0, 1.0]})
        groups_df = pd.DataFrame({"occ1990dd": [4], "dorn_group": ["exec"]})
        assert gate_g5(panel_df, groups_df)["passed"].tolist() == [False]

    def test_g6_gates_every_year_at_one_percent(self):
        gate_df = gate_g6(pd.Series({1983: 0.004, 1984: 0.02}))
        assert gate_df["passed"].tolist() == [True, False]


def _gate_row(gate, gated, passed):
    return {"gate": gate, "scope": "x", "observed": 0.0, "threshold": 0.01, "gated": gated, "passed": passed}


class TestAllGatesPass:
    def test_every_required_gate_must_have_a_gated_row(self):
        gates_df = pd.DataFrame([_gate_row("G1", True, True), _gate_row("G2", False, None)])
        assert not all_gates_pass(gates_df, ("G1", "G2"))

    def test_a_reported_row_never_blocks(self):
        gates_df = pd.DataFrame([_gate_row("G1", True, True), _gate_row("G1", False, None)])
        assert all_gates_pass(gates_df, ("G1",))


class TestPromote:
    def test_refuses_when_a_gate_failed_and_copies_nothing(self, tmp_path):
        gates_path = tmp_path / "gates.csv"
        pd.DataFrame([_gate_row("G1", True, False)]).to_csv(gates_path, index=False)
        source, destination = tmp_path / "rebuilt.csv", tmp_path / "seed.csv"
        source.write_text("a\n1\n")
        with pytest.raises(GateFailureError):
            promote_rebuilt({str(source): str(destination)}, str(gates_path), ("G1",))
        assert not destination.exists()

    def test_copies_when_every_gate_passed(self, tmp_path):
        gates_path = tmp_path / "gates.csv"
        pd.DataFrame([_gate_row("G1", True, True)]).to_csv(gates_path, index=False)
        source, destination = tmp_path / "rebuilt.csv", tmp_path / "seed.csv"
        source.write_text("a\n1\n")
        promote_rebuilt({str(source): str(destination)}, str(gates_path), ("G1",))
        assert destination.read_text() == "a\n1\n"


def test_the_build_refuses_until_task_2_has_verified_ipums(monkeypatch):
    monkeypatch.setattr(ipums_variables, "VERIFICATION_STATUS", "unverified")
    with pytest.raises(RuntimeError, match="Task 2"):
        build_rebuilt_tables(1983, 1983)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_cps_detailed_panel.py -v`
Expected: FAIL — `ImportError: cannot import name 'GateFailureError'`.

- [ ] **Step 3: Implement**

Add to the imports of `cps_detailed_panel.py`:

```python
import os
import shutil
import sys
from dataclasses import dataclass

import download_ipums_cps
from occ1990dd_reference import load_census_code_list, load_dorn_crosswalk, load_occ1990dd_groups, uncovered_codes
```

Append:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_cps_detailed_panel.py -v`
Expected: all PASS.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/ruff format cps_detailed_panel.py tests/test_cps_detailed_panel.py
.venv/bin/ruff check --fix cps_detailed_panel.py tests/test_cps_detailed_panel.py
git add cps_detailed_panel.py tests/test_cps_detailed_panel.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "Gate the detailed panel build and refuse to promote a failing one

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: [KEY-GATED] Download every basic-monthly year**

Prerequisite: Task 2 committed with `VERIFICATION_STATUS = "verified"`.

Run: `.venv/bin/python download_ipums_cps.py basic 1983 2026`
Expected: one line per year naming its directory under `data/raw/ipums/basic/`. This takes hours; IPUMS processes extracts in a queue. It is resumable, so rerun after any interruption.

- [ ] **Step 7: [KEY-GATED] Build and read the gates**

Run: `.venv/bin/python cps_detailed_panel.py build 1983 2026`
Expected: one line per year, then `Gates: ALL PASS`. Then look at the numbers:

```bash
.venv/bin/python -c "
import pandas as pd
gates_df = pd.read_csv('data/output/cps_detailed_gates_rebuilt.csv')
print(gates_df.groupby(['gate', 'gated'])['observed'].describe().to_string())
print(gates_df[gates_df['gated'].astype(str).str.lower().eq('true') & ~gates_df['passed'].astype(str).str.lower().eq('true')].to_string())
"
```

**If any gate fails, STOP.** Never loosen a threshold to get past it; thresholds are pinned by the spec. Report the failing rows to the user. G1 failing near 2003 or 2011 suggests the coding-block year boundaries; G2 failing only from 1998 suggests `COMPWT`; G6 failing suggests IPUMS `OCC1990` codes Dorn's table lacks — list them from the build output before reporting.

- [ ] **Step 8: [KEY-GATED] Promote**

Run: `.venv/bin/python cps_detailed_panel.py promote`
Expected: `Promoted to seeds/cps_detailed_occupation_panel.csv, ...`. Check that `seeds/cps_detailed_occupation_panel.csv` has ~29k rows (333 codes × 44 years × 2 universes, minus empty cells) and only aggregate columns.

- [ ] **Step 9: [KEY-GATED] Document the seeds convention and commit**

In `CLAUDE.md`, after the `seeds/cps_occupation_panel.csv` paragraph, add:

```markdown
**`seeds/cps_detailed_occupation_panel.csv`, `seeds/cps_detailed_occ_crosstab.csv` and `seeds/dws_detailed_panel.csv` are built locally from IPUMS CPS microdata and never in CI.** They are Phase 2 of the deep history extension (`docs/superpowers/specs/2026-09-23-deep-history-phase-2-design.md`). `download_ipums_cps.py` fetches the extracts (needs `IPUMS_API_KEY` and `uv sync --group ipums`); `cps_detailed_panel.py build` / `dws_detailed_panel.py build` tabulate them into `data/output/*_rebuilt.csv` and a gate record; `promote` copies them to `seeds/` **only if every gate in the record passed** — G1/G2/G5/G6 for the employment panel, G3 for the displacement panel. The gate record is committed beside each seed (`seeds/cps_detailed_gates.csv`, `seeds/dws_detailed_gates.csv`). The seeds hold aggregates only, because IPUMS terms prohibit redistributing microdata. `release.yml` has nothing to promote for these: CI can never rebuild them, so they change only through a local rebuild and a deliberate commit. The spine is IPUMS `OCC1990` mapped to Dorn's `occ1990dd` (333 codes), and the demand-type labels reach it through `occ1990dd_soc_bridge.py`'s published-crosswalk chain, whose error gate G4 measures in the pipeline for 2003–2026 — a lower bound for 1983–2002, where no direct route to SOC exists.
```

```bash
git add seeds/cps_detailed_occupation_panel.csv seeds/cps_detailed_occ_crosstab.csv seeds/cps_detailed_gates.csv CLAUDE.md
PATH="$PWD/.venv/bin:$PATH" git commit -m "Commit the detailed CPS panel seeds, all build gates passing

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 9: Pipeline measurement — trends, eligibility, reliability, seams

No key needed. Everything the pipeline derives from the committed panel before any model score is involved (spec § Reliability, § Seams, § Analysis choices, 2a).

**Files:**
- Create: `cps_detailed_measurement.py`
- Test: `tests/test_cps_detailed_measurement.py`

**Interfaces:**
- Consumes: `cps_detailed_panel.SEED_PATH` (Task 8); `analyze_bls.attach_growth_columns`; `composition_era_validation.discover_period_columns`, `period_key`.
- Produces: `HEADLINE_UNIVERSE = "all_employed"`, `SEAM_PERIODS`, `HEADLINE_EXCLUDED_SEAM_PERIODS`, `load_detailed_panel(seed_path) -> DataFrame | None`, `wide_by_year(panel_df, universe, value_column) -> DataFrame` (index `occ1990dd`, int year columns), `build_detailed_trends(panel_df, universe) -> DataFrame` (`occ1990dd`, `TOT_EMP_yyyy`, growth columns), `relative_standard_errors(panel_df, universe) -> DataFrame`, `growth_frame(panel_df, start_year, end_year, universe) -> DataFrame[growth, growth_variance, end_employment]`, `eligible_for_period(rse_df, start_year, end_year, cutoff: float | None) -> pd.Index`, `fixed_set_units(rse_df, cutoff) -> pd.Index`, `reliability_for_units(panel_df, start_year, end_year, units, universe) -> float`, `period_reliability(panel_df, trends_df, cutoff, universe) -> DataFrame`, `measure_vintage_seams(trends_df) -> DataFrame[period, occ1990dd, emp_growth, is_seam_period]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cps_detailed_measurement.py`:

```python
"""Tests for cps_detailed_measurement.py — trends, eligibility, reliability and seams on a synthetic panel."""

import numpy as np
import pandas as pd
import pytest

from cps_detailed_measurement import (
    build_detailed_trends,
    eligible_for_period,
    fixed_set_units,
    growth_frame,
    measure_vintage_seams,
    period_reliability,
    relative_standard_errors,
    reliability_for_units,
)


def panel_rows(cells):
    """cells: (year, occ1990dd, employed_thousands, sampling_variance) in the all_employed universe."""
    return pd.DataFrame(
        [
            {
                "year": year,
                "occ1990dd": code,
                "universe": "all_employed",
                "employed_thousands": employed,
                "person_months": 100,
                "distinct_households": 40.0,
                "months_observed": 12,
                "sampling_variance": variance,
            }
            for year, code, employed, variance in cells
        ]
    )


class TestTrends:
    def test_growth_columns_follow_the_shared_naming(self):
        trends_df = build_detailed_trends(panel_rows([(2021, 4, 100.0, 1.0), (2022, 4, 110.0, 1.0), (2023, 4, 121.0, 1.0)]))
        assert trends_df.loc[0, "hist_emp_growth_2021_2022"] == pytest.approx(0.10)
        assert trends_df.loc[0, "emp_growth_2022_2023"] == pytest.approx(0.10)


class TestRelativeStandardErrors:
    def test_rse_is_the_standard_error_over_the_level(self):
        rse_df = relative_standard_errors(panel_rows([(2010, 4, 100.0, 400.0)]))
        assert rse_df.loc[4, 2010] == pytest.approx(0.20)


class TestGrowthVariance:
    def test_delta_method_growth_variance(self):
        # g = E1/E0 - 1 = 0.1; Var(g) = (E1/E0)^2 * (V1/E1^2 + V0/E0^2) = 1.21 * (1/121 + 1/100)
        growth_df = growth_frame(panel_rows([(2010, 4, 100.0, 1.0), (2011, 4, 110.0, 1.0)]), 2010, 2011)
        assert growth_df.loc[4, "growth"] == pytest.approx(0.1)
        assert growth_df.loc[4, "growth_variance"] == pytest.approx(1.21 * (1 / 12100 + 1 / 10000))


class TestEligibility:
    """The headline rule keeps a shrinking occupation until it is genuinely unmeasurable.

    Mutation-proof: occupation 8 shrinks from precise to imprecise. Per-period
    eligibility must keep it in 2010->2011 (both ends precise) and drop it in
    2011->2012 (end imprecise); the fixed-set sensitivity must drop it everywhere.
    Inverting either rule fails at least one assertion.
    """

    @pytest.fixture
    def shrinking_panel(self):
        return panel_rows(
            [
                (2010, 4, 100.0, 4.0),
                (2011, 4, 100.0, 4.0),
                (2012, 4, 100.0, 4.0),
                (2010, 8, 100.0, 4.0),  # RSE 0.02
                (2011, 8, 50.0, 25.0),  # RSE 0.10
                (2012, 8, 5.0, 4.0),  # RSE 0.40 — shrank below measurability
            ]
        )

    def test_per_period_eligibility_keeps_the_occupation_while_both_ends_are_measurable(self, shrinking_panel):
        rse_df = relative_standard_errors(shrinking_panel)
        assert set(eligible_for_period(rse_df, 2010, 2011, 0.20)) == {4, 8}
        assert set(eligible_for_period(rse_df, 2011, 2012, 0.20)) == {4}

    def test_fixed_set_drops_the_occupation_from_every_period(self, shrinking_panel):
        assert set(fixed_set_units(relative_standard_errors(shrinking_panel), 0.20)) == {4}

    def test_no_cutoff_keeps_every_unit_with_both_endpoints(self, shrinking_panel):
        assert set(eligible_for_period(relative_standard_errors(shrinking_panel), 2011, 2012, None)) == {4, 8}


class TestReliability:
    def test_reliability_is_one_minus_noise_share(self):
        # Growth 0.0, 0.2, 0.4, 0.6: observed variance 0.0666...; each unit's sampling variance is chosen to be 0.02.
        levels = [100.0, 100.0, 100.0, 100.0]
        endings = [100.0, 120.0, 140.0, 160.0]
        cells = []
        for code, (start, end) in enumerate(zip(levels, endings), start=1):
            ratio = end / start
            # Var(g) = ratio^2 * (V1/E1^2 + V0/E0^2) with V1 = V0 = V: solve for V giving 0.02.
            variance = 0.02 / (ratio**2 * (1 / end**2 + 1 / start**2))
            cells += [(2010, code, start, variance), (2011, code, end, variance)]
        panel_df = panel_rows(cells)
        observed_variance = np.var([0.0, 0.2, 0.4, 0.6], ddof=1)
        expected = 1 - 0.02 / observed_variance
        assert reliability_for_units(panel_df, 2010, 2011, pd.Index([1, 2, 3, 4])) == pytest.approx(expected)

    def test_period_table_reports_coverage(self):
        # Years span 2022 because attach_growth_columns anchors its pre-AI composite there, as the real panel does.
        panel_df = panel_rows([(2021, 4, 90.0, 4.0), (2022, 4, 100.0, 4.0), (2021, 8, 10.0, 25.0), (2022, 8, 10.0, 25.0)])
        reliability_df = period_reliability(panel_df, build_detailed_trends(panel_df), cutoff=0.20)
        row = reliability_df.iloc[0]
        assert row["n_eligible"] == 1  # occupation 8 has RSE 0.5
        assert row["employment_share_covered"] == pytest.approx(100.0 / 110.0)


class TestSeams:
    def test_seam_periods_are_flagged_and_ordinary_periods_kept(self):
        trends_df = build_detailed_trends(
            panel_rows([(2001, 4, 100.0, 1.0), (2002, 4, 100.0, 1.0), (2003, 4, 150.0, 1.0), (2022, 4, 150.0, 1.0)])
        )
        seam_df = measure_vintage_seams(trends_df).set_index("period")
        assert bool(seam_df.loc["2002_2003", "is_seam_period"])
        assert not bool(seam_df.loc["2001_2002", "is_seam_period"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_cps_detailed_measurement.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cps_detailed_measurement'`.

- [ ] **Step 3: Create `cps_detailed_measurement.py`**

```python
"""
cps_detailed_measurement.py
───────────────────────────
Pipeline-side measurement of the committed detailed CPS panel (Phase 2 of the
deep history extension): the occ1990dd trend table, each cell's relative
standard error, the sampling variance of each year-over-year growth rate,
per-period eligibility and its fixed-set sensitivity, per-period reliability,
and growth across the coding-vintage seams.

No model score enters here. These are properties of the measurement, computed
before any correlation so no choice below can be tuned toward a result.

Reliability (spec § Reliability), over a period's eligible units:
    reliability = 1 − mean(sampling variance of growth) / variance(observed growth)
Growth variance uses the delta method with adjacent years treated as
independent. Half the sample carries over between years, so this overstates the
noise — conservative, and documented.

Inputs:
  • seeds/cps_detailed_occupation_panel.csv
Outputs: none directly — cps_detailed_validation.run() writes
  cps_detailed_occupation_panel.csv, cps_detailed_trends.csv,
  cps_detailed_reliability.csv and cps_detailed_seam_breaks.csv from these.
"""

import os

import numpy as np
import pandas as pd

from analyze_bls import attach_growth_columns
from composition_era_validation import discover_period_columns, period_key
from cps_detailed_panel import SEED_PATH

HEADLINE_UNIVERSE = "all_employed"
RELIABILITY_CUTOFF = 0.20
SEAM_PERIODS = ("1991_1992", "1993_1994", "2002_2003", "2010_2011", "2019_2020")
# 2019_2020 is already excluded as COVID; the headline excludes the other four.
HEADLINE_EXCLUDED_SEAM_PERIODS = ("1991_1992", "1993_1994", "2002_2003", "2010_2011")


def load_detailed_panel(seed_path: str = SEED_PATH) -> pd.DataFrame | None:
    """The committed panel, or None when the seed has not been built yet."""
    return pd.read_csv(seed_path) if os.path.exists(seed_path) else None


def wide_by_year(panel_df: pd.DataFrame, universe: str, value_column: str) -> pd.DataFrame:
    """One universe's values as occ1990dd x integer year."""
    universe_df = panel_df[panel_df["universe"] == universe]
    wide_df = universe_df.pivot(index="occ1990dd", columns="year", values=value_column)
    wide_df.columns = [int(year) for year in wide_df.columns]
    return wide_df.sort_index(axis=1)


def build_detailed_trends(panel_df: pd.DataFrame, universe: str = HEADLINE_UNIVERSE) -> pd.DataFrame:
    """Trend table keyed by occ1990dd, in the shared TOT_EMP / growth-column layout."""
    employment_df = wide_by_year(panel_df, universe, "employed_thousands")
    available_years = [str(year) for year in employment_df.columns]
    employment_df.columns = [f"TOT_EMP_{year}" for year in available_years]
    return attach_growth_columns(employment_df.reset_index(), available_years)


def relative_standard_errors(panel_df: pd.DataFrame, universe: str = HEADLINE_UNIVERSE) -> pd.DataFrame:
    """Each cell's standard error over its level, occ1990dd x year."""
    return np.sqrt(wide_by_year(panel_df, universe, "sampling_variance")) / wide_by_year(panel_df, universe, "employed_thousands")


def growth_frame(panel_df: pd.DataFrame, start_year: int, end_year: int, universe: str = HEADLINE_UNIVERSE) -> pd.DataFrame:
    """Per unit: growth over the period, its delta-method sampling variance, and end-year employment."""
    employment_df = wide_by_year(panel_df, universe, "employed_thousands")
    variance_df = wide_by_year(panel_df, universe, "sampling_variance")
    if start_year not in employment_df.columns or end_year not in employment_df.columns:
        return pd.DataFrame(columns=["growth", "growth_variance", "end_employment"])
    start_level, end_level = employment_df[start_year], employment_df[end_year]
    level_ratio = end_level / start_level
    growth_variance = level_ratio**2 * (variance_df[end_year] / end_level**2 + variance_df[start_year] / start_level**2)
    return pd.DataFrame({"growth": level_ratio - 1, "growth_variance": growth_variance, "end_employment": end_level}).dropna()


def eligible_for_period(rse_df: pd.DataFrame, start_year: int, end_year: int, cutoff: float | None) -> pd.Index:
    """Headline eligibility: RSE at or below the cutoff in BOTH endpoint years (spec § Analysis choices)."""
    if start_year not in rse_df.columns or end_year not in rse_df.columns:
        return pd.Index([])
    endpoint_rse_df = rse_df[[start_year, end_year]].dropna()
    if cutoff is None:
        return endpoint_rse_df.index
    return endpoint_rse_df.index[(endpoint_rse_df[start_year] <= cutoff) & (endpoint_rse_df[end_year] <= cutoff)]


def fixed_set_units(rse_df: pd.DataFrame, cutoff: float) -> pd.Index:
    """Sensitivity: units at or below the cutoff in EVERY year. Selects on the outcome; never the headline."""
    return rse_df.index[(rse_df <= cutoff).all(axis=1)]


def reliability_for_units(
    panel_df: pd.DataFrame, start_year: int, end_year: int, units: pd.Index, universe: str = HEADLINE_UNIVERSE
) -> float:
    """1 − mean sampling variance of growth / observed variance of growth, over the given units."""
    units_df = growth_frame(panel_df, start_year, end_year, universe).reindex(units).dropna()
    if len(units_df) < 2:
        return float("nan")
    observed_variance = units_df["growth"].var(ddof=1)
    if not observed_variance > 0:
        return float("nan")
    return float(1 - units_df["growth_variance"].mean() / observed_variance)


def period_reliability(
    panel_df: pd.DataFrame, trends_df: pd.DataFrame, cutoff: float | None = RELIABILITY_CUTOFF, universe: str = HEADLINE_UNIVERSE
) -> pd.DataFrame:
    """One row per growth period: eligible units, employment they cover, noise, observed spread, reliability."""
    rse_df = relative_standard_errors(panel_df, universe)
    reliability_rows = []
    for growth_column in discover_period_columns(trends_df):
        period = period_key(growth_column)
        start_year, end_year = (int(part) for part in period.split("_"))
        units = eligible_for_period(rse_df, start_year, end_year, cutoff)
        period_growth_df = growth_frame(panel_df, start_year, end_year, universe)
        eligible_growth_df = period_growth_df.reindex(units).dropna()
        total_end_employment = period_growth_df["end_employment"].sum()
        reliability_rows.append(
            {
                "period": period,
                "n_eligible": len(eligible_growth_df),
                "employment_share_covered": float(eligible_growth_df["end_employment"].sum() / total_end_employment)
                if total_end_employment
                else np.nan,
                "mean_growth_sampling_variance": float(eligible_growth_df["growth_variance"].mean()) if len(eligible_growth_df) else np.nan,
                "observed_growth_variance": float(eligible_growth_df["growth"].var(ddof=1)) if len(eligible_growth_df) > 1 else np.nan,
                "reliability": reliability_for_units(panel_df, start_year, end_year, units, universe),
            }
        )
    return pd.DataFrame(reliability_rows)


def measure_vintage_seams(trends_df: pd.DataFrame) -> pd.DataFrame:
    """Per code, growth in every period with the coding-vintage seams flagged — measured, never patched."""
    seam_frames = []
    for growth_column in discover_period_columns(trends_df):
        period = period_key(growth_column)
        seam_frames.append(
            pd.DataFrame(
                {
                    "period": period,
                    "occ1990dd": trends_df["occ1990dd"],
                    "emp_growth": trends_df[growth_column],
                    "is_seam_period": period in SEAM_PERIODS,
                }
            )
        )
    return (
        pd.concat(seam_frames, ignore_index=True)
        if seam_frames
        else pd.DataFrame(columns=["period", "occ1990dd", "emp_growth", "is_seam_period"])
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_cps_detailed_measurement.py -v`
Expected: all PASS.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/ruff format cps_detailed_measurement.py tests/test_cps_detailed_measurement.py
.venv/bin/ruff check --fix cps_detailed_measurement.py tests/test_cps_detailed_measurement.py
git add cps_detailed_measurement.py tests/test_cps_detailed_measurement.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "Measure eligibility, reliability and coding seams on the detailed panel

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 10: The bridge check (gate G4)

No key needed. Scores every unit a second way, through the raw Census codes CPS actually used in 2003–2026, and compares that with the chain (spec § Bridge check).

**Files:**
- Modify: `occ1990dd_soc_bridge.py`
- Test: `tests/test_occ1990dd_soc_bridge.py`

**Interfaces:**
- Consumes: `census_code_members`, `equal_division_weights`, `score_units`, `LABEL_SCORE_COLUMN` (Tasks 4–5); `cps_detailed_panel.CODING_BLOCKS` (Task 6); crosstab shape `coding_block, occ1990dd, census_code, employed_thousands` (Task 8).
- Produces: `G4_MINIMUM_R = 0.8`, `census_scores_by_block(soc_scores_df, score_columns, anchor_employment, soc_tables=None) -> dict[str, DataFrame]`, `direct_unit_scores(crosstab_df, census_scores: dict[str, DataFrame], score_columns) -> DataFrame[coding_block, occ1990dd, *score_columns]`, `bridge_check(chained_scores_df, direct_scores_df, score_column=LABEL_SCORE_COLUMN) -> DataFrame[coding_block, occ1990dd, chained_score, direct_score, gap, block_pearson_r, threshold, block_gate_passed]`, `g4_passed(check_df) -> bool`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_occ1990dd_soc_bridge.py`:

```python
from occ1990dd_soc_bridge import G4_MINIMUM_R, bridge_check, direct_unit_scores, g4_passed  # noqa: E402

ALL_BLOCKS = ("2003_2010", "2011_2019", "2020_2026")


class TestDirectUnitScores:
    def test_direct_score_is_the_cps_employment_weighted_mean_of_census_code_scores(self):
        crosstab_df = pd.DataFrame(
            {"coding_block": ["2003_2010"] * 2, "occ1990dd": [4, 4], "census_code": [10, 20], "employed_thousands": [3.0, 1.0]}
        )
        census_scores = {"2003_2010": pd.DataFrame({"census_code": [10, 20], "composition_net_change": [0.2, 0.6]})}
        direct_df = direct_unit_scores(crosstab_df, census_scores, ["composition_net_change"])
        assert direct_df.loc[0, "composition_net_change"] == pytest.approx(0.3)


def _check_inputs(direct_values_by_block):
    chained_df = pd.DataFrame({"occ1990dd": [1, 2, 3, 4], "composition_net_change": [0.1, 0.2, 0.3, 0.4]})
    direct_rows = [
        {"coding_block": block, "occ1990dd": code, "composition_net_change": value}
        for block, values in direct_values_by_block.items()
        for code, value in zip([1, 2, 3, 4], values)
    ]
    return chained_df, pd.DataFrame(direct_rows)


class TestBridgeCheck:
    def test_every_block_tracking_the_chain_passes(self):
        chained_df, direct_df = _check_inputs({block: [0.11, 0.19, 0.31, 0.42] for block in ALL_BLOCKS})
        check_df = bridge_check(chained_df, direct_df)
        assert (check_df["block_pearson_r"] >= G4_MINIMUM_R).all()
        assert g4_passed(check_df)

    def test_one_block_that_disagrees_fails_the_gate(self):
        values = {block: [0.11, 0.19, 0.31, 0.42] for block in ALL_BLOCKS}
        values["2020_2026"] = [0.4, 0.1, 0.3, 0.2]
        assert not g4_passed(bridge_check(*_check_inputs(values)))

    def test_a_missing_block_fails_rather_than_passing_vacuously(self):
        values = {block: [0.11, 0.19, 0.31, 0.42] for block in ALL_BLOCKS[:2]}
        assert not g4_passed(bridge_check(*_check_inputs(values)))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_occ1990dd_soc_bridge.py -v`
Expected: FAIL — `ImportError: cannot import name 'G4_MINIMUM_R'`.

- [ ] **Step 3: Implement**

Add to the imports of `occ1990dd_soc_bridge.py`:

```python
from scipy import stats

from cps_detailed_panel import CODING_BLOCKS
```

Append:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_occ1990dd_soc_bridge.py -v`
Expected: all PASS.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/ruff format occ1990dd_soc_bridge.py tests/test_occ1990dd_soc_bridge.py
.venv/bin/ruff check --fix occ1990dd_soc_bridge.py tests/test_occ1990dd_soc_bridge.py
git add occ1990dd_soc_bridge.py tests/test_occ1990dd_soc_bridge.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "Measure the chain's error against direct Census-code scoring (gate G4)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 11: Detailed-level era and cycle tests

No key needed; tested on synthetic panels. Runs every view spec § Analysis choices pinned for 2a, through the existing `summarise_eras` / `decompose_fit_strength` machinery.

**Files:**
- Create: `cps_detailed_validation.py`
- Modify: `composition_era_validation.py` (`plot_signal_over_time` gains two levels; two chart-name constants)
- Modify: `CLAUDE.md` (Outputs Reference rows for this task's outputs)
- Test: `tests/test_cps_detailed_validation.py`

**Interfaces:**
- Consumes: `cps_detailed_measurement.HEADLINE_UNIVERSE`, `HEADLINE_EXCLUDED_SEAM_PERIODS`, `relative_standard_errors`, `eligible_for_period`, `fixed_set_units`, `reliability_for_units`, `build_detailed_trends` (Task 9); `cps_detailed_panel.CODING_BLOCKS` (Task 6); `composition_era_validation.discover_period_columns`, `period_key`, `is_ai_era`, `COVID_PERIODS`, `MINIMUM_UNITS`, `summarise_eras`, `decompose_fit_strength`, `unemployment_change_by_period`, `print_era_summary`, `print_cycle_decomposition`, `plot_signal_over_time`.
- Produces: `RSE_CUTOFF = 0.20`, `SWEEP_CUTOFFS = (0.10, 0.20, 0.30, None)`, `MINIMUM_LABELED_SHARE = 0.8`, `PERIOD_COLUMNS`, `labeled_units(unit_scores_df) -> pd.Index`, `corrected_correlation(raw_r, reliability) -> float`, `detailed_period_correlations(unit_scores_df, trends_df, panel_df, score_columns, labeled, cutoff=RSE_CUTOFF, fixed_units=None, periods=None) -> DataFrame[PERIOD_COLUMNS]`, `direct_period_correlations(direct_scores_df, trends_df, panel_df, score_columns, labeled) -> DataFrame`, `run_views(period_df, fixed_period_df, direct_period_df) -> dict[str, DataFrame]`, `summarise_views(views, unemployment_change) -> tuple[DataFrame, DataFrame]`, `eligibility_sweep(unit_scores_df, trends_df, panel_df, score_columns, labeled, fixed_period_df) -> DataFrame`, `run_detailed_level(unit_scores_df, direct_scores_df, panel_df, trends_df, score_columns, output_dir) -> DataFrame`; in `composition_era_validation`: `CPS_DETAILED_CHART_NAME`, `CPS_MAJOR_CHART_NAME`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cps_detailed_validation.py`:

```python
"""Tests for cps_detailed_validation.py — the detailed-level and 22-major-rollup era tests, on synthetic panels."""

import os

import numpy as np
import pandas as pd
import pytest

import composition_era_validation
from cps_detailed_measurement import build_detailed_trends
from cps_detailed_validation import (
    corrected_correlation,
    detailed_period_correlations,
    labeled_units,
    run_views,
)


def panel_rows(cells):
    return pd.DataFrame(
        [
            {
                "year": year,
                "occ1990dd": code,
                "universe": "all_employed",
                "employed_thousands": employed,
                "person_months": 100,
                "distinct_households": 40.0,
                "months_observed": 12,
                "sampling_variance": variance,
            }
            for year, code, employed, variance in cells
        ]
    )


def synthetic_inputs(years=(2021, 2022, 2023), unit_count=30, slope=0.05, variance=0.01, unlabeled_units=()):
    """Growth rises with the score, plus a small deterministic wobble, so r is positive but below 1."""
    cells, score_rows = [], []
    for unit in range(1, unit_count + 1):
        score = unit / unit_count
        level = 1000.0
        for year in years:
            cells.append((year, unit, level, variance))
            level *= 1 + slope * score + 0.002 * ((unit * 7) % 5)
        score_rows.append({"occ1990dd": unit, "composition_net_change": score, "labeled_share": 0.5 if unit in unlabeled_units else 1.0})
    return panel_rows(cells), pd.DataFrame(score_rows)


class TestCorrectedCorrelation:
    @pytest.mark.parametrize(
        ("raw_r", "reliability", "expected"),
        [(0.3, 0.25, 0.6), (0.3, 0.0, np.nan), (0.3, np.nan, np.nan), (0.9, 0.5, np.nan)],  # last: |corrected| >= 1 is undefined
    )
    def test_rule(self, raw_r, reliability, expected):
        result = corrected_correlation(raw_r, reliability)
        assert (np.isnan(result) and np.isnan(expected)) or result == pytest.approx(expected)


class TestDetailedPeriodCorrelations:
    def test_one_row_per_period_and_score_with_a_positive_fit(self):
        panel_df, unit_scores_df = synthetic_inputs()
        period_df = detailed_period_correlations(
            unit_scores_df, build_detailed_trends(panel_df), panel_df, ["composition_net_change"], labeled_units(unit_scores_df)
        )
        assert set(period_df["period"]) == {"2021_2022", "2022_2023"}
        assert (period_df["fit_r"] > 0.5).all()
        assert period_df.set_index("period").loc["2022_2023", "era"] == "ai"

    def test_units_below_the_labeled_share_floor_are_excluded(self):
        panel_df, unit_scores_df = synthetic_inputs(unlabeled_units=range(1, 6))
        period_df = detailed_period_correlations(
            unit_scores_df, build_detailed_trends(panel_df), panel_df, ["composition_net_change"], labeled_units(unit_scores_df)
        )
        assert (period_df["n_units"] == 25).all()

    def test_seam_periods_are_flagged(self):
        panel_df, unit_scores_df = synthetic_inputs(years=(2010, 2011, 2022))
        period_df = detailed_period_correlations(
            unit_scores_df, build_detailed_trends(panel_df), panel_df, ["composition_net_change"], labeled_units(unit_scores_df)
        )
        assert period_df.set_index("period")["is_seam"].to_dict() == {"2010_2011": True, "2011_2022": False}


class TestRunViews:
    def test_headline_drops_seams_and_corrected_swaps_in_corrected_r(self):
        period_df = pd.DataFrame(
            {
                "period": ["2010_2011", "2012_2013"],
                "score": ["composition_net_change"] * 2,
                "fit_r": [0.1, 0.2],
                "fit_p": [0.5, 0.4],
                "n_units": [100, 100],
                "era": ["pre_ai"] * 2,
                "is_covid": [False, False],
                "is_seam": [True, False],
                "reliability": [0.25, 0.25],
                "fit_r_corrected": [0.2, 0.4],
            }
        )
        views = run_views(period_df, period_df, None)
        assert views["headline"]["period"].tolist() == ["2012_2013"]
        assert views["noise_corrected"]["fit_r"].tolist() == [0.4]
        assert views["seams_included"]["period"].tolist() == ["2010_2011", "2012_2013"]
        assert "direct_scores_diagnostic" not in views


class TestChartLevels:
    @pytest.mark.parametrize(
        ("level", "chart_name"),
        [
            ("cps_detailed", composition_era_validation.CPS_DETAILED_CHART_NAME),
            ("cps_major", composition_era_validation.CPS_MAJOR_CHART_NAME),
        ],
    )
    def test_new_levels_write_their_own_chart(self, tmp_path, level, chart_name):
        period_df = pd.DataFrame(
            {
                "period": ["2020_2021", "2021_2022", "2022_2023"],
                "score": ["composition_net_change"] * 3,
                "fit_r": [0.1, 0.2, 0.15],
                "fit_p": [0.3, 0.01, 0.2],
                "n_units": [250, 260, 255],
                "era": ["pre_ai", "pre_ai", "ai"],
                "is_covid": [True, False, False],
            }
        )
        composition_era_validation.plot_signal_over_time(period_df, str(tmp_path), level=level)
        assert os.path.exists(tmp_path / chart_name)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_cps_detailed_validation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cps_detailed_validation'`.

- [ ] **Step 3: Add the two chart levels to `composition_era_validation.py`**

After the line `CPS_CHART_NAME = "composition_model_signal_over_time_cps.png"`, add:

```python
# Phase 2 levels, drawn by cps_detailed_validation.py through plot_signal_over_time.
CPS_DETAILED_CHART_NAME = "composition_model_signal_over_time_cps_detailed.png"
CPS_MAJOR_CHART_NAME = "composition_model_signal_over_time_cps_major.png"
PHASE_2_LEVEL_UNIT_NOUNS = {"cps_detailed": "CPS occ1990dd occupations", "cps_major": "SOC major groups (CPS rollup)"}
```

In `plot_signal_over_time`, add a branch **between** the `elif is_occupation_level and not unit_counts.empty:` branch and the `elif is_cps_level:` branch:

```python
    elif level in PHASE_2_LEVEL_UNIT_NOUNS and not unit_counts.empty:
        unit_label = f"n={int(unit_counts.min())}-{int(unit_counts.max())} {PHASE_2_LEVEL_UNIT_NOUNS[level]}"
```

Replace the `level_word = ...` line with:

```python
    level_word = {
        "occupation": "Occupation",
        "cps_group": "CPS group",
        "cps_detailed": "CPS detailed-occupation",
        "cps_major": "CPS SOC-major",
    }.get(level, "Sector")
```

In the footnote, after the `if is_occupation_level else ""` conditional's closing parenthesis, add a second conditional so the whole argument reads:

```python
"Demand-type labels come from 2025 O*NET task statements applied backwards; earlier periods are more anachronistic."

"Red bands are COVID periods, excluded from the era comparison."
+(
    " The composition score is a function of demand-type mix alone, so many units share one value; "
    "Pearson r is bounded by that tie structure."
    if is_occupation_level
    else ""
)
(
    +(
        " Year-over-year growth at this grain is mostly sampling noise (cps_detailed_reliability.csv), "
        "so raw r is biased toward zero; coding-seam periods are excluded."
        if level == "cps_detailed"
        else ""
    ),
)
```

Replace the `chart_name = ...` line with:

```python
    chart_name = {
        "occupation": OCCUPATION_CHART_NAME,
        "cps_group": CPS_CHART_NAME,
        "cps_detailed": CPS_DETAILED_CHART_NAME,
        "cps_major": CPS_MAJOR_CHART_NAME,
    }.get(level, CHART_NAME)
```

Existing levels take exactly the branches they took before, so their charts are unchanged; Task 13 verifies this byte for byte.

- [ ] **Step 4: Create `cps_detailed_validation.py`**

```python
"""
cps_detailed_validation.py
──────────────────────────
Phase 2 of the deep history extension: the demand composition era test and
cycle decomposition at two new levels built from IPUMS CPS microdata, 1983–2026 —
~330 detailed occ1990dd occupations, and the 22 SOC major groups rolled up from
them.

Every choice below was pinned in the spec before any seed existed
(docs/superpowers/specs/2026-09-23-deep-history-phase-2-design.md § Analysis
choices). The views computed, all written, none chosen after the fact:

  headline                  per-period eligibility (RSE ≤ 20% at both ends), labeled
                            share ≥ 0.8, seam periods excluded, raw r
  noise_corrected           the same periods, r / sqrt(reliability)
  seams_included            the headline with the four seam periods put back
  fixed_set                 units at RSE ≤ 20% in every year — selects on the outcome
  direct_scores_diagnostic  2003–2026 only, direct Census-code scores in place of chained

An era difference counts only if raw and noise-corrected r agree in sign. Raw r is
biased toward zero and corrected r away from it, because the bootstrap
overstates noise; the two bracket the truth. Year-over-year growth at this grain
is known, and accepted by decision, to be mostly sampling noise.

Inputs:
  • seeds/cps_detailed_occupation_panel.csv, seeds/cps_detailed_occ_crosstab.csv
  • data/output/occupation_composition_model_report.csv, occupation_dynamic_model_report.csv
  • data/output/bls_trends.csv, bls_sector_trends.csv, seeds/cps_occupation_panel.csv
Outputs:
  • data/output/cps_detailed_period_correlations.csv
  • data/output/composition_model_era_comparison_cps_detailed.csv
  • data/output/composition_cycle_decomposition_cps_detailed.csv
  • data/output/cps_detailed_eligibility_sweep.csv
  • data/output/visualizations/composition_model_signal_over_time_cps_detailed.png
  (Tasks 12–13 add the rollup and the measurement outputs.)
"""

import os

import numpy as np
import pandas as pd
from scipy import stats

import composition_era_validation as era_validation
from cps_detailed_measurement import (
    HEADLINE_EXCLUDED_SEAM_PERIODS,
    HEADLINE_UNIVERSE,
    eligible_for_period,
    fixed_set_units,
    relative_standard_errors,
    reliability_for_units,
)
from cps_detailed_panel import CODING_BLOCKS

RSE_CUTOFF = 0.20
SWEEP_CUTOFFS = (0.10, 0.20, 0.30, None)
MINIMUM_LABELED_SHARE = 0.8

PERIOD_OUTPUT_PATH = "data/output/cps_detailed_period_correlations.csv"
ERA_OUTPUT_PATH = "data/output/composition_model_era_comparison_cps_detailed.csv"
CYCLE_OUTPUT_PATH = "data/output/composition_cycle_decomposition_cps_detailed.csv"
SWEEP_OUTPUT_PATH = "data/output/cps_detailed_eligibility_sweep.csv"

PERIOD_COLUMNS = ["period", "score", "fit_r", "fit_p", "n_units", "era", "is_covid", "is_seam", "reliability", "fit_r_corrected"]


def labeled_units(unit_scores_df: pd.DataFrame) -> pd.Index:
    """Units whose chained score rests on at least 80% labeled SOC weight."""
    return pd.Index(unit_scores_df.loc[unit_scores_df["labeled_share"] >= MINIMUM_LABELED_SHARE, "occ1990dd"])


def corrected_correlation(raw_r: float, reliability: float) -> float:
    """r / sqrt(reliability); undefined (NaN) when reliability ≤ 0 or the result reaches ±1."""
    if not reliability > 0:
        return float("nan")
    corrected = raw_r / np.sqrt(reliability)
    return float(corrected) if abs(corrected) < 1 else float("nan")


def detailed_period_correlations(
    unit_scores_df: pd.DataFrame,
    trends_df: pd.DataFrame,
    panel_df: pd.DataFrame,
    score_columns: list[str],
    labeled: pd.Index,
    cutoff: float | None = RSE_CUTOFF,
    fixed_units: pd.Index | None = None,
    periods: set[str] | None = None,
) -> pd.DataFrame:
    """One row per (period, score): raw r over eligible labeled units, plus reliability and corrected r.

    Shares the frame shape summarise_eras and decompose_fit_strength read, with
    `is_seam`, `reliability` and `fit_r_corrected` added.
    """
    rse_df = relative_standard_errors(panel_df, HEADLINE_UNIVERSE)
    scores_df = unit_scores_df.set_index("occ1990dd")
    growth_by_unit = trends_df.set_index("occ1990dd")
    correlation_rows = []
    for growth_column in era_validation.discover_period_columns(trends_df):
        period = era_validation.period_key(growth_column)
        if periods is not None and period not in periods:
            continue
        start_year, end_year = (int(part) for part in period.split("_"))
        units = fixed_units if fixed_units is not None else eligible_for_period(rse_df, start_year, end_year, cutoff)
        units = pd.Index(units).intersection(labeled)
        reliability = reliability_for_units(panel_df, start_year, end_year, units, HEADLINE_UNIVERSE)
        for score_column in score_columns:
            if score_column not in scores_df.columns:
                continue
            paired_df = pd.DataFrame(
                {"score": scores_df[score_column].reindex(units), "growth": growth_by_unit[growth_column].reindex(units)}
            ).dropna()
            if len(paired_df) < era_validation.MINIMUM_UNITS or paired_df["score"].nunique() < 2 or paired_df["growth"].nunique() < 2:
                continue
            correlation, p_value = stats.pearsonr(paired_df["score"], paired_df["growth"])
            correlation_rows.append(
                {
                    "period": period,
                    "score": score_column,
                    "fit_r": float(correlation),
                    "fit_p": float(p_value),
                    "n_units": len(paired_df),
                    "era": "ai" if era_validation.is_ai_era(growth_column) else "pre_ai",
                    "is_covid": period in era_validation.COVID_PERIODS,
                    "is_seam": period in HEADLINE_EXCLUDED_SEAM_PERIODS,
                    "reliability": reliability,
                    "fit_r_corrected": corrected_correlation(float(correlation), reliability),
                }
            )
    return pd.DataFrame(correlation_rows, columns=PERIOD_COLUMNS)


def direct_period_correlations(
    direct_scores_df: pd.DataFrame, trends_df: pd.DataFrame, panel_df: pd.DataFrame, score_columns: list[str], labeled: pd.Index
) -> pd.DataFrame:
    """The headline computation with direct scores, for periods lying inside one coding block. Diagnostic only."""
    all_periods = {era_validation.period_key(column) for column in era_validation.discover_period_columns(trends_df)}
    block_frames = []
    for coding_block, (first_year, last_year, _) in CODING_BLOCKS.items():
        block_periods = {
            period for period in all_periods if first_year <= int(period.split("_")[0]) and int(period.split("_")[1]) <= last_year
        }
        block_scores_df = direct_scores_df[direct_scores_df["coding_block"] == coding_block]
        if block_periods and not block_scores_df.empty:
            block_frames.append(
                detailed_period_correlations(block_scores_df, trends_df, panel_df, score_columns, labeled, periods=block_periods)
            )
    return pd.concat(block_frames, ignore_index=True) if block_frames else pd.DataFrame(columns=PERIOD_COLUMNS)


def run_views(period_df: pd.DataFrame, fixed_period_df: pd.DataFrame, direct_period_df: pd.DataFrame | None) -> dict[str, pd.DataFrame]:
    """The five pre-specified views of the detailed-level result."""
    headline_df = period_df[~period_df["is_seam"]]
    views = {
        "headline": headline_df,
        "noise_corrected": headline_df.assign(fit_r=headline_df["fit_r_corrected"]).dropna(subset=["fit_r"]),
        "seams_included": period_df,
        "fixed_set": fixed_period_df[~fixed_period_df["is_seam"]],
    }
    if direct_period_df is not None and not direct_period_df.empty:
        views["direct_scores_diagnostic"] = direct_period_df[~direct_period_df["is_seam"]]
    return views


def summarise_views(views: dict[str, pd.DataFrame], unemployment_change: pd.Series | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Era comparison and cycle decomposition for every view, each row labelled with its view."""
    era_frames, cycle_frames = [], []
    for view_name, view_df in views.items():
        if view_df.empty:
            continue
        era_frames.append(era_validation.summarise_eras(view_df).assign(run=view_name))
        if unemployment_change is not None:
            cycle_frames.append(era_validation.decompose_fit_strength(view_df, unemployment_change).assign(run=view_name))
    era_df = pd.concat(era_frames, ignore_index=True) if era_frames else pd.DataFrame()
    cycle_df = pd.concat(cycle_frames, ignore_index=True) if cycle_frames else pd.DataFrame()
    for summary_df in (era_df, cycle_df):
        if "run" in summary_df.columns:
            summary_df.insert(0, "run", summary_df.pop("run"))
    return era_df, cycle_df


def _cutoff_label(cutoff: float | None) -> str:
    return "none" if cutoff is None else f"{cutoff:.2f}"


def eligibility_sweep(
    unit_scores_df: pd.DataFrame,
    trends_df: pd.DataFrame,
    panel_df: pd.DataFrame,
    score_columns: list[str],
    labeled: pd.Index,
    fixed_period_df: pd.DataFrame,
) -> pd.DataFrame:
    """The headline era comparison at every pinned cutoff, plus the fixed-set run, with mean units per era."""
    sweep_inputs = [
        (_cutoff_label(cutoff), detailed_period_correlations(unit_scores_df, trends_df, panel_df, score_columns, labeled, cutoff=cutoff))
        for cutoff in SWEEP_CUTOFFS
    ]
    sweep_inputs.append((f"fixed_{RSE_CUTOFF:.2f}", fixed_period_df))
    sweep_frames = []
    for cutoff_label, period_df in sweep_inputs:
        headline_df = period_df[~period_df["is_seam"]]
        if headline_df.empty:
            continue
        mean_units = headline_df[~headline_df["is_covid"]].groupby(["score", "era"])["n_units"].mean().rename("mean_n_units")
        era_df = era_validation.summarise_eras(headline_df).merge(mean_units.reset_index(), on=["score", "era"], how="left")
        era_df.insert(0, "cutoff", cutoff_label)
        sweep_frames.append(era_df)
    return pd.concat(sweep_frames, ignore_index=True) if sweep_frames else pd.DataFrame()


def _write(frame: pd.DataFrame, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    frame.to_csv(path, index=False)
    print(f"  ✓ {path}")


def run_detailed_level(
    unit_scores_df: pd.DataFrame,
    direct_scores_df: pd.DataFrame | None,
    panel_df: pd.DataFrame,
    trends_df: pd.DataFrame,
    score_columns: list[str],
    output_dir: str,
) -> pd.DataFrame:
    """Every pre-specified view at detailed level: period rows, era and cycle summaries, the sweep, the chart."""
    print("\n── Demand composition model, CPS detailed-occupation level (occ1990dd, 1983–2026) ──")
    labeled = labeled_units(unit_scores_df)
    period_df = detailed_period_correlations(unit_scores_df, trends_df, panel_df, score_columns, labeled)
    fixed_period_df = detailed_period_correlations(
        unit_scores_df,
        trends_df,
        panel_df,
        score_columns,
        labeled,
        fixed_units=fixed_set_units(relative_standard_errors(panel_df), RSE_CUTOFF),
    )
    direct_period_df = (
        direct_period_correlations(direct_scores_df, trends_df, panel_df, score_columns, labeled) if direct_scores_df is not None else None
    )
    views = run_views(period_df, fixed_period_df, direct_period_df)

    _write(pd.concat([view_df.assign(run=view_name) for view_name, view_df in views.items()], ignore_index=True), PERIOD_OUTPUT_PATH)
    unemployment_change = era_validation.unemployment_change_by_period(sorted(period_df["period"].unique()))
    era_df, cycle_df = summarise_views(views, unemployment_change)
    _write(era_df, ERA_OUTPUT_PATH)
    if not cycle_df.empty:
        _write(cycle_df, CYCLE_OUTPUT_PATH)

    for view_name in ("headline", "noise_corrected"):
        print(f"\n  View: {view_name}")
        era_validation.print_era_summary(era_df[era_df["run"] == view_name].drop(columns="run"))
    undefined_count = int(period_df["fit_r_corrected"].isna().sum())
    print(f"  {undefined_count} period/score rows have undefined corrected r (reliability ≤ 0 or |corrected r| ≥ 1).")
    if not cycle_df.empty:
        era_validation.print_cycle_decomposition(cycle_df[cycle_df["run"] == "headline"].drop(columns="run"))

    _write(eligibility_sweep(unit_scores_df, trends_df, panel_df, score_columns, labeled, fixed_period_df), SWEEP_OUTPUT_PATH)
    era_validation.plot_signal_over_time(views["headline"], output_dir, level="cps_detailed")
    return era_df
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_cps_detailed_validation.py tests/test_composition_era_validation.py -v`
Expected: all PASS, including every pre-existing era-validation test.

- [ ] **Step 6: Add Outputs Reference rows**

In `CLAUDE.md`'s data-file table, add after the `composition_cycle_decomposition_cps.csv` row:

```markdown
| `cps_detailed_period_correlations.csv` | `cps_detailed_validation.py` | Every period × score row at the CPS detailed-occupation level (occ1990dd, 1983–2026), one row per pre-specified view (`run`: headline, noise_corrected, seams_included, fixed_set, direct_scores_diagnostic), with `n_units`, `is_seam`, `reliability` and `fit_r_corrected`. The source of every detailed-level summary. See `docs/superpowers/specs/2026-09-23-deep-history-phase-2-design.md` § Analysis choices. |
| `composition_model_era_comparison_cps_detailed.csv` | `cps_detailed_validation.py` | Era comparison at the CPS detailed-occupation level, one block of rows per view (`run`). `run == "headline"` is the headline; an era difference counts only if `headline` and `noise_corrected` agree in sign. Year-over-year growth at this grain is mostly sampling noise, accepted by decision; see `cps_detailed_reliability.csv`. |
| `composition_cycle_decomposition_cps_detailed.csv` | `cps_detailed_validation.py` | Cycle decomposition at the CPS detailed-occupation level, per view (`run`), same specification as the sector level. |
| `cps_detailed_eligibility_sweep.csv` | `cps_detailed_validation.py` | The headline era comparison re-run at RSE cutoffs 0.10, 0.20, 0.30 and none, plus the fixed-set run (`fixed_0.20`), with mean eligible units per era. Shows whether any detailed-level conclusion depends on the 20% cutoff. |
```

In the visualizations table, after the `composition_model_signal_over_time_cps.png` row:

```markdown
| `composition_model_signal_over_time_cps_detailed.png` | `cps_detailed_validation.py` | Same layout and four scores as the other signal-over-time charts, at the CPS detailed-occupation level (occ1990dd, 1983–2026), headline view. Coding-seam periods excluded. n is per-period eligible units. See `docs/charts/composition_model_signal_over_time_cps_detailed.md`. |
```

- [ ] **Step 7: Lint and commit**

```bash
.venv/bin/ruff format cps_detailed_validation.py composition_era_validation.py tests/test_cps_detailed_validation.py
.venv/bin/ruff check --fix cps_detailed_validation.py composition_era_validation.py tests/test_cps_detailed_validation.py
git add cps_detailed_validation.py composition_era_validation.py tests/test_cps_detailed_validation.py CLAUDE.md
PATH="$PWD/.venv/bin:$PATH" git commit -m "Run the era and cycle tests at the CPS detailed-occupation level

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 12: The 22-SOC-major rollup to 1983

No key needed. Spec P2-D6: allocate detailed employment to SOC major groups through the bridge's split weights (over **all** SOC constituents, so `labeled_share` does not apply), then run the sector-level era and cycle specification at n=22. Also writes the two reported-only comparisons: the rollup against OEWS sectors (`wage_salary`, 1999–2025) and against Phase 1's published ten-group series (all years).

**Files:**
- Modify: `cps_detailed_validation.py`
- Modify: `CLAUDE.md` (Outputs Reference rows)
- Test: `tests/test_cps_detailed_validation.py`

**Interfaces:**
- Consumes: `analyze_bls.attach_growth_columns`; `cps_historical_panel.compare_with_oews(cps_trends_df, oews_sector_trends_df, soc_major_to_group)`; `composition_displacement_validation.soc_major_to_dws_group()`; `composition_era_validation.load_scored_occupations()` (returns `scored_df` with `OCC_CODE`, scores and `TOT_EMP_*`; the latest employment column; the sector table; the present score columns).
- Produces: `MINIMUM_ROLLUP_MAJORS = 20`, `rollup_to_majors(panel_df, bridge_weights_df, universe) -> DataFrame[year, soc_major, employed_thousands]`, `build_rollup_trends(rollup_df) -> DataFrame` (keyed `soc_major`), `major_scores(scored_df, employment_column, score_columns) -> DataFrame[soc_major, *scores]`, `major_period_correlations(major_scores_df, rollup_trends_df, score_columns) -> DataFrame` (shared period shape plus `is_seam`), `oews_major_agreement(wage_salary_trends_df, sector_trends_df) -> DataFrame`, `published_ten_group_agreement(rollup_df, published_panel_df) -> DataFrame`, `run_major_level(panel_df, bridge_weights_df, output_dir) -> DataFrame | None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cps_detailed_validation.py`:

```python
from cps_detailed_validation import (  # noqa: E402
    MINIMUM_ROLLUP_MAJORS,
    build_rollup_trends,
    major_period_correlations,
    major_scores,
    oews_major_agreement,
    published_ten_group_agreement,
    rollup_to_majors,
)


class TestRollupToMajors:
    def test_detailed_employment_is_split_by_bridge_weight(self):
        panel_df = panel_rows([(2010, 4, 100.0, 1.0)])
        bridge_weights_df = pd.DataFrame(
            {"occ1990dd": [4, 4, 4], "soc_2018_code": ["11-1011", "11-1021", "13-1011"], "weight": [0.5, 0.25, 0.25]}
        )
        rollup_df = rollup_to_majors(panel_df, bridge_weights_df).set_index("soc_major")
        assert rollup_df.loc["11", "employed_thousands"] == pytest.approx(75.0)
        assert rollup_df.loc["13", "employed_thousands"] == pytest.approx(25.0)

    def test_the_trend_table_carries_the_shared_growth_columns(self):
        rollup_df = pd.DataFrame({"year": [2021, 2022, 2023], "soc_major": ["11"] * 3, "employed_thousands": [100.0, 110.0, 121.0]})
        trends_df = build_rollup_trends(rollup_df)
        assert trends_df.loc[0, "emp_growth_2022_2023"] == pytest.approx(0.10)


def _major_inputs(slope):
    majors = [f"{code:02d}" for code in range(11, 55, 2)]  # 22 two-digit majors
    scored_df = pd.DataFrame(
        {"OCC_CODE": [f"{major}-1011" for major in majors], "composition_net_change": np.linspace(0, 1, 22), "TOT_EMP_2025": 1000.0}
    )
    rollup_df = pd.DataFrame(
        [
            {"year": year, "soc_major": major, "employed_thousands": 100.0 * (1 + slope * score + 0.003 * (index % 3)) ** (year - 2021)}
            for index, (major, score) in enumerate(zip(majors, np.linspace(0, 1, 22)))
            for year in (2021, 2022, 2023)
        ]
    )
    return scored_df, build_rollup_trends(rollup_df)


class TestMajorPeriodCorrelations:
    def test_positive_fit_at_n_22(self):
        scored_df, trends_df = _major_inputs(slope=0.05)
        period_df = major_period_correlations(
            major_scores(scored_df, "TOT_EMP_2025", ["composition_net_change"]), trends_df, ["composition_net_change"]
        )
        assert (period_df["n_units"] == 22).all()
        assert (period_df["fit_r"] > 0.5).all()

    def test_fewer_than_twenty_majors_gives_no_row(self):
        scored_df, trends_df = _major_inputs(slope=0.05)
        thin_scores_df = major_scores(scored_df.head(MINIMUM_ROLLUP_MAJORS - 1), "TOT_EMP_2025", ["composition_net_change"])
        assert major_period_correlations(thin_scores_df, trends_df, ["composition_net_change"]).empty


class TestAgreementReports:
    def test_oews_agreement_pairs_each_major_with_itself(self):
        wage_salary_trends_df = build_rollup_trends(
            pd.DataFrame({"year": [2021, 2022], "soc_major": ["11", "11"], "employed_thousands": [100.0, 110.0]})
        )
        sector_trends_df = pd.DataFrame({"soc_major": ["11"], "TOT_EMP_2021": [200.0], "TOT_EMP_2022": [210.0]})
        agreement_df = oews_major_agreement(wage_salary_trends_df, sector_trends_df)
        assert agreement_df.loc[0, "soc_major"] == "11"
        assert agreement_df.loc[0, "oews_growth"] == pytest.approx(0.05)
        assert agreement_df.loc[0, "cps_growth"] == pytest.approx(0.10)

    def test_published_agreement_labels_the_reconstruction_segments(self):
        rollup_df = pd.DataFrame({"year": [1990, 2001, 2010], "soc_major": ["41"] * 3, "employed_thousands": [110.0, 100.0, 99.0]})
        published_df = pd.DataFrame(
            {"year": [1990, 2001, 2010], "cps_group": ["sales and related occupations"] * 3, "employed_thousands": [100.0, 100.0, 100.0]}
        )
        agreement_df = published_ten_group_agreement(rollup_df, published_df).set_index("year")
        assert agreement_df.loc[1990, "segment"] == "reconstruction_1983_1999"
        assert agreement_df.loc[2001, "segment"] == "bridge_2000_2002"
        assert agreement_df.loc[2010, "segment"] == "published_2003_on"
        assert agreement_df.loc[1990, "relative_difference"] == pytest.approx(0.10)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_cps_detailed_validation.py -v`
Expected: FAIL — `ImportError: cannot import name 'MINIMUM_ROLLUP_MAJORS'`.

- [ ] **Step 3: Implement**

Add to the imports of `cps_detailed_validation.py`:

```python
from analyze_bls import attach_growth_columns
from composition_displacement_validation import soc_major_to_dws_group
from cps_historical_panel import compare_with_oews
from cps_detailed_measurement import SEAM_PERIODS
```

(`SEAM_PERIODS` joins the existing `from cps_detailed_measurement import (...)` block.) Append:

```python
ROLLUP_TRENDS_OUTPUT_PATH = "data/output/cps_major_rollup_trends.csv"
MAJOR_ERA_OUTPUT_PATH = "data/output/composition_model_era_comparison_cps_major.csv"
MAJOR_CYCLE_OUTPUT_PATH = "data/output/composition_cycle_decomposition_cps_major.csv"
MAJOR_OEWS_AGREEMENT_OUTPUT_PATH = "data/output/cps_major_oews_agreement.csv"
PUBLISHED_AGREEMENT_OUTPUT_PATH = "data/output/cps_detailed_published_agreement.csv"
PUBLISHED_TEN_GROUP_PANEL_PATH = "seeds/cps_occupation_panel.csv"
SECTOR_TRENDS_PATH = "data/output/bls_sector_trends.csv"
# The ten-group level's 8-of-10 convention, at 22.
MINIMUM_ROLLUP_MAJORS = 20


def rollup_to_majors(panel_df: pd.DataFrame, bridge_weights_df: pd.DataFrame, universe: str = HEADLINE_UNIVERSE) -> pd.DataFrame:
    """Allocate each occ1990dd unit's employment to SOC major groups by its bridge weights.

    Uses every SOC constituent, labeled or not — employment allocation needs no
    demand-type label. Units the chain does not reach drop out; run_major_level
    prints how much employment that costs.
    """
    major_weights_df = (
        bridge_weights_df.assign(soc_major=bridge_weights_df["soc_2018_code"].str[:2])
        .groupby(["occ1990dd", "soc_major"], as_index=False)["weight"]
        .sum()
    )
    universe_df = panel_df.loc[panel_df["universe"] == universe, ["year", "occ1990dd", "employed_thousands"]]
    allocated_df = universe_df.merge(major_weights_df, on="occ1990dd", how="inner")
    allocated_df["employed_thousands"] = allocated_df["employed_thousands"] * allocated_df["weight"]
    return allocated_df.groupby(["year", "soc_major"], as_index=False)["employed_thousands"].sum()


def build_rollup_trends(rollup_df: pd.DataFrame) -> pd.DataFrame:
    """The rollup in bls_sector_trends.csv's layout, keyed by soc_major."""
    wide_df = rollup_df.pivot(index="soc_major", columns="year", values="employed_thousands")
    available_years = [str(int(year)) for year in sorted(wide_df.columns)]
    wide_df = wide_df[sorted(wide_df.columns)]
    wide_df.columns = [f"TOT_EMP_{year}" for year in available_years]
    return attach_growth_columns(wide_df.reset_index(), available_years)


def major_scores(scored_df: pd.DataFrame, employment_column: str, score_columns: list[str]) -> pd.DataFrame:
    """Employment-weighted mean score per SOC major, as cps_group_correlation aggregates to the ten groups."""
    base_df = scored_df.dropna(subset=[employment_column]).assign(soc_major=scored_df["OCC_CODE"].astype(str).str[:2])
    score_frames = []
    for score_column in score_columns:
        scored_rows_df = base_df.dropna(subset=[score_column])
        weighted = (scored_rows_df[score_column] * scored_rows_df[employment_column]).groupby(scored_rows_df["soc_major"]).sum()
        score_frames.append((weighted / scored_rows_df.groupby("soc_major")[employment_column].sum()).rename(score_column))
    return pd.concat(score_frames, axis=1).reset_index()


def major_period_correlations(major_scores_df: pd.DataFrame, rollup_trends_df: pd.DataFrame, score_columns: list[str]) -> pd.DataFrame:
    """Pearson r per (period, score) across SOC majors — the sector specification, seams flagged but kept."""
    correlation_rows = []
    for growth_column in era_validation.discover_period_columns(rollup_trends_df):
        period = era_validation.period_key(growth_column)
        for score_column in score_columns:
            paired_df = (
                major_scores_df[["soc_major", score_column]].merge(rollup_trends_df[["soc_major", growth_column]], on="soc_major").dropna()
            )
            if len(paired_df) < MINIMUM_ROLLUP_MAJORS or paired_df[score_column].nunique() < 2 or paired_df[growth_column].nunique() < 2:
                continue
            correlation, p_value = stats.pearsonr(paired_df[score_column], paired_df[growth_column])
            correlation_rows.append(
                {
                    "period": period,
                    "score": score_column,
                    "fit_r": float(correlation),
                    "fit_p": float(p_value),
                    "n_units": len(paired_df),
                    "era": "ai" if era_validation.is_ai_era(growth_column) else "pre_ai",
                    "is_covid": period in era_validation.COVID_PERIODS,
                    "is_seam": period in SEAM_PERIODS,
                }
            )
    return pd.DataFrame(correlation_rows, columns=["period", "score", "fit_r", "fit_p", "n_units", "era", "is_covid", "is_seam"])


def oews_major_agreement(wage_salary_trends_df: pd.DataFrame, sector_trends_df: pd.DataFrame) -> pd.DataFrame:
    """Rollup (wage and salary) against OEWS sector growth, 1999–2025. Reported, never reconciled (Phase 1 D3)."""
    renamed_df = wage_salary_trends_df.rename(columns={"soc_major": "cps_group"})
    identity_lookup = {major: major for major in renamed_df["cps_group"]}
    return compare_with_oews(renamed_df, sector_trends_df, identity_lookup).rename(columns={"cps_group": "soc_major"})


def published_ten_group_agreement(rollup_df: pd.DataFrame, published_panel_df: pd.DataFrame) -> pd.DataFrame:
    """Rollup summed to the ten Phase 1 groups against the published series, every year. Reported only."""
    group_lookup = soc_major_to_dws_group()
    grouped_df = (
        rollup_df.assign(cps_group=rollup_df["soc_major"].map(group_lookup))
        .dropna(subset=["cps_group"])
        .groupby(["year", "cps_group"], as_index=False)["employed_thousands"]
        .sum()
        .rename(columns={"employed_thousands": "rollup_thousands"})
    )
    published_df = published_panel_df.rename(columns={"employed_thousands": "published_thousands"})[
        ["year", "cps_group", "published_thousands"]
    ]
    agreement_df = grouped_df.merge(published_df, on=["year", "cps_group"], how="inner")
    agreement_df["relative_difference"] = agreement_df["rollup_thousands"] / agreement_df["published_thousands"] - 1
    agreement_df["segment"] = np.select(
        [agreement_df["year"] <= 1999, agreement_df["year"] <= 2002], ["reconstruction_1983_1999", "bridge_2000_2002"], "published_2003_on"
    )
    return agreement_df


def run_major_level(panel_df: pd.DataFrame, bridge_weights_df: pd.DataFrame, output_dir: str) -> pd.DataFrame | None:
    """The 22-major rollup: trends, era and cycle tests, chart, and both agreement reports."""
    print("\n── Demand composition model, CPS 22-SOC-major rollup (1983–2026) ──")
    rollup_df = rollup_to_majors(panel_df, bridge_weights_df)
    universe_totals = panel_df[panel_df["universe"] == HEADLINE_UNIVERSE].groupby("year")["employed_thousands"].sum()
    coverage = rollup_df.groupby("year")["employed_thousands"].sum() / universe_totals
    print(f"  Employment the chain reaches: {coverage.min():.4f}-{coverage.max():.4f} of the panel, by year")
    rollup_trends_df = build_rollup_trends(rollup_df)
    _write(rollup_trends_df, ROLLUP_TRENDS_OUTPUT_PATH)

    scored_df, employment_column, _, score_columns = era_validation.load_scored_occupations()
    period_df = major_period_correlations(major_scores(scored_df, employment_column, score_columns), rollup_trends_df, score_columns)
    if period_df.empty:
        print("  ⚠ No 22-major period correlations could be computed.")
        return None
    era_df = era_validation.summarise_eras(period_df)
    _write(era_df, MAJOR_ERA_OUTPUT_PATH)
    era_validation.print_era_summary(era_df)
    unemployment_change = era_validation.unemployment_change_by_period(sorted(period_df["period"].unique()))
    if unemployment_change is not None:
        cycle_df = era_validation.decompose_fit_strength(period_df, unemployment_change)
        _write(cycle_df, MAJOR_CYCLE_OUTPUT_PATH)
        era_validation.print_cycle_decomposition(cycle_df)
    era_validation.plot_signal_over_time(period_df, output_dir, level="cps_major")

    if os.path.exists(SECTOR_TRENDS_PATH):
        wage_salary_trends_df = build_rollup_trends(rollup_to_majors(panel_df, bridge_weights_df, "wage_salary"))
        agreement_df = oews_major_agreement(wage_salary_trends_df, pd.read_csv(SECTOR_TRENDS_PATH, dtype={"soc_major": str}))
        _write(agreement_df, MAJOR_OEWS_AGREEMENT_OUTPUT_PATH)
        if len(agreement_df) > 2:
            agreement_r = stats.pearsonr(agreement_df["cps_growth"], agreement_df["oews_growth"])[0]
            print(f"  Rollup vs OEWS sector growth (wage and salary): r = {agreement_r:+.3f}, n = {len(agreement_df)}")
            print("  Reported, never reconciled (Phase 1 D3).")
    _write(published_ten_group_agreement(rollup_df, pd.read_csv(PUBLISHED_TEN_GROUP_PANEL_PATH)), PUBLISHED_AGREEMENT_OUTPUT_PATH)
    return era_df
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_cps_detailed_validation.py -v`
Expected: all PASS.

- [ ] **Step 5: Add Outputs Reference rows**

In `CLAUDE.md`'s data-file table, after the rows Task 11 added:

```markdown
| `cps_major_rollup_trends.csv` | `cps_detailed_validation.py` | Detailed CPS employment (occ1990dd, `all_employed`) allocated to the 22 SOC major groups through the bridge's split weights over all SOC constituents, 1983–2026, in `bls_sector_trends.csv`'s layout. Puts the n=22 sector test back to 1983 with three downturns. |
| `composition_model_era_comparison_cps_major.csv` | `cps_detailed_validation.py` | Era comparison on the 22-major rollup, 1983–2026, same specification as the sector level (spec P2-D6). Seam periods are not excluded, matching the sector level; aggregation to 22 groups damps them. |
| `composition_cycle_decomposition_cps_major.csv` | `cps_detailed_validation.py` | Cycle decomposition on the 22-major rollup, 1983–2026. |
| `cps_major_oews_agreement.csv` | `cps_detailed_validation.py` | The rollup's `wage_salary` universe against OEWS sector growth per period, 1999–2025 — the universe-aligned overlap check. Reported, never reconciled. |
| `cps_detailed_published_agreement.csv` | `cps_detailed_validation.py` | The rollup summed to Phase 1's ten groups against `seeds/cps_occupation_panel.csv`, every year, with `segment` marking BLS's 1983–1999 reconstruction, the 2000–2002 bridge, and published data from 2003. Reported only; gate G1 is the build-time check. |
```

In the visualizations table:

```markdown
| `composition_model_signal_over_time_cps_major.png` | `cps_detailed_validation.py` | Same layout and four scores, on the 22-SOC-major rollup of the detailed CPS panel, 1983–2026. See `docs/charts/composition_model_signal_over_time_cps_major.md`. |
```

- [ ] **Step 6: Lint and commit**

```bash
.venv/bin/ruff format cps_detailed_validation.py tests/test_cps_detailed_validation.py
.venv/bin/ruff check --fix cps_detailed_validation.py tests/test_cps_detailed_validation.py
git add cps_detailed_validation.py tests/test_cps_detailed_validation.py CLAUDE.md
PATH="$PWD/.venv/bin:$PATH" git commit -m "Roll the detailed CPS panel up to 22 SOC majors back to 1983

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 13: The pipeline entry point, the G4 withholding rule, and wiring

No key needed to build and test. With no seed present the new level warns and skips, so this task's byte-identity check runs today. It runs again in Task 17 once real seeds exist.

**Files:**
- Modify: `cps_detailed_validation.py` (add `run()`)
- Modify: `synthesize_composition.py` (`run_stage`)
- Modify: `CLAUDE.md` (Outputs Reference rows)
- Test: `tests/test_cps_detailed_validation.py`

**Interfaces:**
- Consumes: everything from Tasks 4–12. `occ1990dd_soc_bridge`: `load_soc_scores`, `load_anchor_employment`, `load_soc_tables`, `build_bridge_weights`, `score_units`, `DISPLACEMENT_SCORE_COLUMNS`, `occ1990dd_composition_stability`, `census_scores_by_block`, `direct_unit_scores`, `bridge_check`, `g4_passed`, `COMPOSITION_REPORT_PATH`. `cps_detailed_measurement`: `load_detailed_panel`, `build_detailed_trends`, `period_reliability`, `measure_vintage_seams`. `cps_detailed_panel`: `SEED_PATH`, `CROSSTAB_SEED_PATH`.
- Produces: `cps_detailed_validation.run(output_dir="data/output/visualizations", seed_path=SEED_PATH, crosstab_seed_path=CROSSTAB_SEED_PATH) -> DataFrame | None`; `BRIDGE_CHECK_OUTPUT_PATH` (Task 16 reads it).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cps_detailed_validation.py`:

```python
import cps_detailed_validation  # noqa: E402


class TestRun:
    def test_a_missing_seed_warns_and_skips(self, tmp_path):
        with pytest.warns(UserWarning, match="IPUMS"):
            assert cps_detailed_validation.run(output_dir=str(tmp_path), seed_path=str(tmp_path / "absent.csv")) is None

    def test_a_failed_g4_withholds_both_detailed_levels(self, tmp_path, monkeypatch):
        panel_df, unit_scores_df = synthetic_inputs()
        seed_path, crosstab_path = tmp_path / "panel.csv", tmp_path / "crosstab.csv"
        panel_df.to_csv(seed_path, index=False)
        pd.DataFrame({"coding_block": ["2003_2010"], "occ1990dd": [1], "census_code": [10], "employed_thousands": [1.0]}).to_csv(
            crosstab_path, index=False
        )

        for output_name in (
            "PANEL_OUTPUT_PATH",
            "TRENDS_OUTPUT_PATH",
            "RELIABILITY_OUTPUT_PATH",
            "SEAM_BREAKS_OUTPUT_PATH",
            "UNIT_SCORES_OUTPUT_PATH",
            "STABILITY_OUTPUT_PATH",
            "BRIDGE_CHECK_OUTPUT_PATH",
        ):
            monkeypatch.setattr(cps_detailed_validation, output_name, str(tmp_path / f"{output_name}.csv"))
        monkeypatch.setattr(cps_detailed_validation, "COMPOSITION_REPORT_PATH", str(seed_path))  # any existing file
        monkeypatch.setattr(
            cps_detailed_validation, "load_soc_scores", lambda: (pd.DataFrame({"OCC_CODE": []}), ["composition_net_change"])
        )
        monkeypatch.setattr(cps_detailed_validation, "load_anchor_employment", lambda: pd.Series(dtype=float))
        monkeypatch.setattr(cps_detailed_validation, "load_soc_tables", lambda: None)
        monkeypatch.setattr(
            cps_detailed_validation,
            "build_bridge_weights",
            lambda anchor, tables: pd.DataFrame({"occ1990dd": [1], "soc_2018_code": ["A"], "weight": [1.0]}),
        )
        monkeypatch.setattr(cps_detailed_validation, "score_units", lambda *arguments: unit_scores_df)
        monkeypatch.setattr(cps_detailed_validation, "occ1990dd_composition_stability", lambda *arguments: pd.DataFrame())
        monkeypatch.setattr(cps_detailed_validation, "OCCUPATION_TRENDS_PATH", str(seed_path))
        monkeypatch.setattr(cps_detailed_validation, "census_scores_by_block", lambda *arguments: {})
        monkeypatch.setattr(cps_detailed_validation, "direct_unit_scores", lambda *arguments: pd.DataFrame())
        monkeypatch.setattr(
            cps_detailed_validation,
            "bridge_check",
            lambda *arguments: pd.DataFrame({"coding_block": ["2003_2010"], "block_pearson_r": [0.3], "block_gate_passed": [False]}),
        )

        def must_not_run(*arguments, **keyword_arguments):
            raise AssertionError("a detailed level ran despite a failed G4")

        monkeypatch.setattr(cps_detailed_validation, "run_detailed_level", must_not_run)
        monkeypatch.setattr(cps_detailed_validation, "run_major_level", must_not_run)
        with pytest.warns(UserWarning, match="G4"):
            assert (
                cps_detailed_validation.run(output_dir=str(tmp_path), seed_path=str(seed_path), crosstab_seed_path=str(crosstab_path))
                is None
            )
        assert os.path.exists(tmp_path / "BRIDGE_CHECK_OUTPUT_PATH.csv")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_cps_detailed_validation.py::TestRun -v`
Expected: FAIL — `AttributeError: module 'cps_detailed_validation' has no attribute 'run'`.

- [ ] **Step 3: Implement `run()`**

Add to the imports of `cps_detailed_validation.py`:

```python
import warnings

from cps_detailed_measurement import build_detailed_trends, load_detailed_panel, measure_vintage_seams, period_reliability
from cps_detailed_panel import CROSSTAB_SEED_PATH, SEED_PATH
from occ1990dd_soc_bridge import (
    COMPOSITION_REPORT_PATH,
    DISPLACEMENT_SCORE_COLUMNS,
    bridge_check,
    build_bridge_weights,
    census_scores_by_block,
    direct_unit_scores,
    g4_passed,
    load_anchor_employment,
    load_soc_scores,
    load_soc_tables,
    occ1990dd_composition_stability,
    score_units,
)
```

(`build_detailed_trends` and the others join the existing `from cps_detailed_measurement import (...)` block; `CODING_BLOCKS` stays in the `cps_detailed_panel` import.) Append:

```python
PANEL_OUTPUT_PATH = "data/output/cps_detailed_occupation_panel.csv"
TRENDS_OUTPUT_PATH = "data/output/cps_detailed_trends.csv"
RELIABILITY_OUTPUT_PATH = "data/output/cps_detailed_reliability.csv"
SEAM_BREAKS_OUTPUT_PATH = "data/output/cps_detailed_seam_breaks.csv"
UNIT_SCORES_OUTPUT_PATH = "data/output/occ1990dd_scores.csv"
STABILITY_OUTPUT_PATH = "data/output/occ1990dd_composition_stability.csv"
BRIDGE_CHECK_OUTPUT_PATH = "data/output/occ1990dd_bridge_check.csv"
OCCUPATION_TRENDS_PATH = "data/output/bls_trends.csv"


def _print_seam_summary(seam_df: pd.DataFrame) -> None:
    absolute_growth = seam_df.assign(absolute_growth=seam_df["emp_growth"].abs()).dropna(subset=["absolute_growth"])
    ordinary_growth = absolute_growth.loc[~absolute_growth["is_seam_period"], "absolute_growth"]
    print(f"  Ordinary periods: median |growth| {ordinary_growth.median():.4f}, 95th percentile {ordinary_growth.quantile(0.95):.4f}")
    for period, period_df in absolute_growth[absolute_growth["is_seam_period"]].groupby("period"):
        print(f"  Seam {period}: median |growth| {period_df['absolute_growth'].median():.4f}, max {period_df['absolute_growth'].max():.4f}")


def run(
    output_dir: str = "data/output/visualizations", seed_path: str = SEED_PATH, crosstab_seed_path: str = CROSSTAB_SEED_PATH
) -> pd.DataFrame | None:
    """Phase 2 pipeline entry: measurement tables, bridge scores, gate G4, then both detailed levels.

    A missing seed warns and skips, like every other seed-backed instrument here.
    A failed G4 still writes the bridge check but withholds every detailed-level
    and rollup result: a result resting on an unfit bridge is not published.
    """
    panel_df = load_detailed_panel(seed_path)
    if panel_df is None:
        warnings.warn(
            f"{seed_path} absent — it is built locally from IPUMS microdata (cps_detailed_panel.py); detailed CPS levels skipped",
            stacklevel=2,
        )
        return None
    if not os.path.exists(COMPOSITION_REPORT_PATH):
        warnings.warn(f"{COMPOSITION_REPORT_PATH} absent; run the composition stage first — detailed CPS levels skipped", stacklevel=2)
        return None

    print("\n── CPS detailed-occupation panel (IPUMS, occ1990dd) ──")
    _write(panel_df, PANEL_OUTPUT_PATH)
    trends_df = build_detailed_trends(panel_df)
    _write(trends_df, TRENDS_OUTPUT_PATH)
    reliability_df = period_reliability(panel_df, trends_df)
    _write(reliability_df, RELIABILITY_OUTPUT_PATH)
    print(
        f"  Reliability of year-over-year growth: median {reliability_df['reliability'].median():.3f} across {len(reliability_df)} periods"
    )
    seam_df = measure_vintage_seams(trends_df)
    _write(seam_df, SEAM_BREAKS_OUTPUT_PATH)
    _print_seam_summary(seam_df)

    soc_scores_df, score_columns = load_soc_scores()
    anchor_employment = load_anchor_employment()
    soc_tables = load_soc_tables()
    bridge_weights_df = build_bridge_weights(anchor_employment, soc_tables)
    unit_scores_df = score_units(bridge_weights_df, "occ1990dd", soc_scores_df, score_columns + DISPLACEMENT_SCORE_COLUMNS)
    _write(unit_scores_df, UNIT_SCORES_OUTPUT_PATH)
    _write(occ1990dd_composition_stability(bridge_weights_df, pd.read_csv(OCCUPATION_TRENDS_PATH)), STABILITY_OUTPUT_PATH)

    if not os.path.exists(crosstab_seed_path):
        warnings.warn(f"{crosstab_seed_path} absent, so gate G4 cannot run — detailed CPS levels withheld", stacklevel=2)
        return None
    direct_scores_df = direct_unit_scores(
        pd.read_csv(crosstab_seed_path), census_scores_by_block(soc_scores_df, score_columns, anchor_employment, soc_tables), score_columns
    )
    check_df = bridge_check(unit_scores_df, direct_scores_df)
    _write(check_df, BRIDGE_CHECK_OUTPUT_PATH)
    for coding_block, block_r in check_df.groupby("coding_block")["block_pearson_r"].first().items():
        print(f"  G4 {coding_block}: chained vs direct r = {block_r:+.3f}")
    if not g4_passed(check_df):
        warnings.warn(
            "Gate G4 failed: the chained bridge does not track direct Census-code scoring in every coding block. "
            "Detailed-level and 22-major results are withheld; the design returns for review.",
            stacklevel=2,
        )
        return None

    era_df = run_detailed_level(unit_scores_df, direct_scores_df, panel_df, trends_df, score_columns, output_dir)
    run_major_level(panel_df, bridge_weights_df, output_dir)
    return era_df
```

- [ ] **Step 4: Wire it into the composition stage**

In `synthesize_composition.py`'s `run_stage`, add `import cps_detailed_validation` to the function-local imports, and call it directly after `composition_era_validation.run()`:

```python
    composition_era_validation.run()
    # Phase 2: detailed CPS levels from the IPUMS seeds. Skips with a warning when the
    # seeds have not been built, which is always the case in CI before the first local build.
    cps_detailed_validation.run()
    composition_displacement_validation.run()
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_cps_detailed_validation.py tests/test_composition_model.py -v`
Expected: all PASS.

- [ ] **Step 6: Verify every existing output is byte-identical**

Run the composition stage and compare against the baseline taken in § "Before Task 1":

```bash
.venv/bin/python main.py composition
(cd data/output && sha256sum --check --quiet ../phase2_baseline_hashes.txt) && echo "BYTE-IDENTICAL"
```

Expected: `BYTE-IDENTICAL`, plus a `UserWarning` that the detailed seed is absent (unless Task 8 has run). `--check` verifies only the files listed at baseline, so this task's new outputs are ignored. If a file differs, find the cause before going on. Task 11's chart change is the likeliest suspect, since it touched the one shared function. The other possibility is not code at all: the composition stage refetches CPS series, so a BLS month published since the baseline changes `cps_occupation_panel.csv` and everything downstream of it. Confirm that by rerunning the baseline procedure on the pre-plan commit in a scratch worktree.

- [ ] **Step 7: Add Outputs Reference rows**

In `CLAUDE.md`'s data-file table, before the rows Task 11 added:

```markdown
| `cps_detailed_occupation_panel.csv` | `cps_detailed_validation.py` (from `seeds/cps_detailed_occupation_panel.csv`) | Annual CPS employment (thousands) per `occ1990dd` code (333 codes), 1983–2026, in two universes (`all_employed`, `wage_salary`), with `person_months`, `distinct_households`, `months_observed` and a household-bootstrap `sampling_variance`. Tabulated locally from IPUMS basic-monthly microdata by `cps_detailed_panel.py`, never in CI; a missing seed warns and skips the detailed levels. |
| `cps_detailed_trends.csv` | `cps_detailed_validation.py` | `all_employed` trend table keyed by `occ1990dd`, `attach_growth_columns` layout. |
| `cps_detailed_reliability.csv` | `cps_detailed_validation.py` (via `cps_detailed_measurement.period_reliability`) | Per period: eligible units (RSE ≤ 20% at both ends), employment share they cover, mean sampling variance of growth, observed variance of growth, and reliability = 1 − noise / observed. Measures the known, accepted problem that year-over-year growth at this grain is mostly sampling noise. |
| `cps_detailed_seam_breaks.csv` | `cps_detailed_validation.py` (via `cps_detailed_measurement.measure_vintage_seams`) | Per code, growth in every period with the coding-vintage seams flagged (1991→92, 1993→94, 2002→03, 2010→11, 2019→20). Measured, never patched. |
| `occ1990dd_scores.csv` | `cps_detailed_validation.py` (via `occ1990dd_soc_bridge.score_units`) | Every model score per `occ1990dd` code through the published-crosswalk chain, with `labeled_share`, blended `pct_*`, and `dominant_demand` re-derived after aggregation. |
| `occ1990dd_composition_stability.csv` | `cps_detailed_validation.py` | Per `occ1990dd` code, the share of its bridge weight on SOC codes OEWS already published in 1999 — the detailed-grain composition-stability proxy. |
| `occ1990dd_bridge_check.csv` | `cps_detailed_validation.py` (via `occ1990dd_soc_bridge.bridge_check`) | Gate G4: chained vs direct (raw Census-code) score per code and coding block, 2003–2026, with each block's Pearson r and verdict (r ≥ 0.8 required in every block). If any block fails, every detailed-level and rollup result is withheld. A lower bound on the chain's error for 1983–2002, where no direct route exists. |
```

- [ ] **Step 8: Lint and commit**

```bash
.venv/bin/ruff format cps_detailed_validation.py synthesize_composition.py tests/test_cps_detailed_validation.py
.venv/bin/ruff check --fix cps_detailed_validation.py synthesize_composition.py tests/test_cps_detailed_validation.py
git add cps_detailed_validation.py synthesize_composition.py tests/test_cps_detailed_validation.py CLAUDE.md
PATH="$PWD/.venv/bin:$PATH" git commit -m "Wire the detailed CPS levels into the composition stage behind gate G4

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 14: Tabulating the Displaced Worker Supplement onto the Dorn partition

No key needed; tested on synthetic records. Spec § Displacement (2b). **Skip Tasks 14–16 entirely if Task 2 Step 6 stopped 2b**, because no raw lost-job occupation exists.

**Files:**
- Modify: `occ1990dd_reference.py` (add `load_census_2002_to_2010`)
- Create: `dws_detailed_panel.py`
- Test: `tests/test_occ1990dd_reference.py`, `tests/test_dws_detailed_panel.py`

**Interfaces:**
- Consumes: `cps_detailed_panel.GATE_COLUMNS`, `all_gates_pass`, `promote_rebuilt`, `bootstrap_group_variance`, `census_code_ten_group_lookup`, `spine_lookup`, `_as_bool` (Tasks 6–8); `occ1990dd_reference` loaders (Task 3); `ipums_cps_variables.DWS_*` (Tasks 1–2); `download_ipums_cps.read_extract`, `extract_is_downloaded`, `RAW_DIR`.
- Produces: `occ1990dd_reference.load_census_2002_to_2010() -> DataFrame[census_2002, census_2010]`; in `dws_detailed_panel`: `TENURE_CLASSES`, `PANEL_COLUMNS`, `SEED_PATH`, `GATES_SEED_PATH`, `lost_job_raw_vintage(survey_year) -> str`, `lost_job_edges(survey_year) -> DataFrame[raw_code, occ1990dd, share]`, `select_displaced(person_df)`, `is_long_tenured(frame) -> pd.Series`, `attach_lost_job_occ1990dd(displaced_df, survey_year) -> tuple[DataFrame, float]`, `tabulate_survey(mapped_df, survey_year, groups_df) -> DataFrame[PANEL_COLUMNS]`, `ten_group_long_tenured_direct(displaced_df, survey_year) -> DataFrame[survey_year, cps_group, displaced_thousands]`, `gate_g3(direct_df, published_panel_df) -> DataFrame`, `gate_g6d(unmapped_by_survey) -> DataFrame`, `build_rebuilt_panel(survey_years=None, ...) -> DataFrame`.

**Gate G6D, added by this plan:** the displacement twin of G6. Lost-job weight that reaches no `occ1990dd` code must be **≤ 1% in every survey**. It is pinned here, before any DWS seed exists, because the fallback route below splits and drops codes at every Census revision.

**Lost-job occupation routes.** If Task 2 found a harmonized lost-job `OCC1990`, it goes through the same spine as 2a. Otherwise, each raw code maps through the coding vintage of its survey year:

| Surveys | Raw codes | Route to `occ1990dd` |
|---|---|---|
| 1984–1992 | 1980 Census | Dorn `occ1980` |
| 1994–2002 | 1990 Census | Dorn `occ1990` |
| 2004–2010 | 2002 Census (4-digit) | Census 2002→2010 crosswalk, then Dorn `occ2010` |
| 2012–2018 | 2010 Census | Dorn `occ2010` |
| 2020 onward | 2018 Census | Census 2018→2010 crosswalk, then Dorn `occ2010` |

When one raw code reaches *k* distinct `occ1990dd` codes, each receives 1/*k* of its weight.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_occ1990dd_reference.py`:

```python
from occ1990dd_reference import load_census_2002_to_2010  # noqa: E402


def test_2002_to_2010_covers_nearly_every_2002_code():
    crosswalk_df = load_census_2002_to_2010()
    codes_2002 = set(load_census_code_list("2002")["census_code"])
    # Five 2002 codes (0210, 3130, 4550, 8230, 8240) have no 2010 successor in the Census sheet.
    assert len(codes_2002 - set(crosswalk_df["census_2002"])) == 5
```

Create `tests/test_dws_detailed_panel.py`:

```python
"""Tests for dws_detailed_panel.py — the detailed Displaced Worker Supplement build, on synthetic records."""

import pandas as pd
import pytest

import dws_detailed_panel
import ipums_cps_variables as ipums_variables
from dws_detailed_panel import (
    attach_lost_job_occ1990dd,
    gate_g3,
    gate_g6d,
    is_long_tenured,
    lost_job_edges,
    lost_job_raw_vintage,
    select_displaced,
    tabulate_survey,
)


@pytest.fixture(autouse=True)
def pinned_dws_variables(monkeypatch):
    monkeypatch.setattr(ipums_variables, "DWS_DISPLACED_REASON_CODES", (1, 2, 3))
    monkeypatch.setattr(ipums_variables, "DWS_LOST_JOB_OCC1990_VARIABLE", None)


def displaced_records(rows):
    defaults = {
        "YEAR": 2024,
        "SERIAL": 1,
        "AGE": 45,
        ipums_variables.DWS_WEIGHT_VARIABLE: 2000.0,
        ipums_variables.DWS_REASON_VARIABLE: 1,
        ipums_variables.DWS_TENURE_VARIABLE: 5.0,
        ipums_variables.DWS_LOST_JOB_OCC_VARIABLE: 4700,
    }
    return pd.DataFrame([{**defaults, **row} for row in rows])


class TestVintages:
    @pytest.mark.parametrize(
        ("survey_year", "vintage"),
        [(1984, "1980"), (1992, "1980"), (1994, "1990"), (2002, "1990"), (2004, "2002"), (2012, "2010"), (2020, "2018")],
    )
    def test_survey_year_to_raw_code_vintage(self, survey_year, vintage):
        assert lost_job_raw_vintage(survey_year) == vintage

    @pytest.mark.parametrize("survey_year", [1986, 1996, 2006, 2014, 2024])
    def test_shares_never_exceed_one_per_raw_code(self, survey_year):
        edges_df = lost_job_edges(survey_year)
        assert (edges_df.groupby("raw_code")["share"].sum() <= 1.0 + 1e-9).all()
        assert not edges_df.empty


class TestSelection:
    def test_keeps_adults_displaced_for_a_bls_reason_with_positive_weight(self):
        person_df = displaced_records(
            [{}, {"AGE": 19}, {ipums_variables.DWS_REASON_VARIABLE: 5}, {ipums_variables.DWS_WEIGHT_VARIABLE: 0.0}]
        )
        assert len(select_displaced(person_df)) == 1

    def test_long_tenure_is_three_or_more_valid_years(self):
        tenure = ipums_variables.DWS_TENURE_VARIABLE
        person_df = displaced_records([{tenure: 2.9}, {tenure: 3.0}, {tenure: 99.0}])
        assert is_long_tenured(person_df).tolist() == [False, True, False]


class TestMapping:
    def test_a_split_raw_code_divides_its_weight(self, monkeypatch):
        monkeypatch.setattr(
            dws_detailed_panel,
            "lost_job_edges",
            lambda survey_year: pd.DataFrame({"raw_code": [4700, 4700], "occ1990dd": [243, 274], "share": [0.5, 0.5]}),
        )
        mapped_df, unmapped_share = attach_lost_job_occ1990dd(displaced_records([{}]), 2024)
        assert mapped_df["allocated_weight"].tolist() == [1000.0, 1000.0]
        assert unmapped_share == pytest.approx(0.0)

    def test_an_unmapped_raw_code_is_reported_for_g6d(self, monkeypatch):
        monkeypatch.setattr(
            dws_detailed_panel, "lost_job_edges", lambda survey_year: pd.DataFrame({"raw_code": [4700], "occ1990dd": [274], "share": [1.0]})
        )
        _, unmapped_share = attach_lost_job_occ1990dd(displaced_records([{}, {ipums_variables.DWS_LOST_JOB_OCC_VARIABLE: 1}]), 2024)
        assert unmapped_share == pytest.approx(0.5)


class TestTabulateSurvey:
    def test_counts_per_group_and_tenure_class(self):
        mapped_df = pd.DataFrame(
            {
                "occ1990dd": [274, 274, 4],
                "allocated_weight": [2000.0, 2000.0, 1000.0],
                "SERIAL": [1, 2, 3],
                ipums_variables.DWS_TENURE_VARIABLE: [5.0, 1.0, 10.0],
            }
        )
        groups_df = pd.DataFrame({"occ1990dd": [274, 4], "dorn_group": ["retsales", "exec"]})
        panel_df = tabulate_survey(mapped_df, 2024, groups_df).set_index(["dorn_group", "tenure_class"])
        assert panel_df.loc[("retsales", "all_tenures"), "displaced_thousands"] == pytest.approx(4.0)
        assert panel_df.loc[("retsales", "long_tenured"), "displaced_thousands"] == pytest.approx(2.0)
        assert panel_df.loc[("retsales", "all_tenures"), "unweighted_count"] == 2


class TestGates:
    def test_g3_allows_published_rounding_on_small_groups(self):
        direct_df = pd.DataFrame(
            {
                "survey_year": [2024, 2024],
                "cps_group": ["sales and related occupations", "farming, fishing, and forestry occupations"],
                "displaced_thousands": [1010.0, 4.4],
            }
        )
        published_df = pd.DataFrame(
            {
                "survey_year": [2024, 2024],
                "source_table": ["table_5_occupation"] * 2,
                "measurement_basis": ["count_thousands"] * 2,
                "group_name": ["Sales and related occupations", "Farming, fishing, and forestry occupations"],
                "displaced_thousands": [1000.0, 4.0],
            }
        )
        gate_df = gate_g3(direct_df, published_df)
        # 1% off on the large group passes; 10% off on the 4k group passes only because 0.4k < 0.5k rounding.
        assert gate_df["passed"].tolist() == [True, True]

    def test_g3_fails_a_real_gap(self):
        direct_df = pd.DataFrame({"survey_year": [2024], "cps_group": ["sales and related occupations"], "displaced_thousands": [1100.0]})
        published_df = pd.DataFrame(
            {
                "survey_year": [2024],
                "source_table": ["table_5_occupation"],
                "measurement_basis": ["count_thousands"],
                "group_name": ["Sales and related occupations"],
                "displaced_thousands": [1000.0],
            }
        )
        assert gate_g3(direct_df, published_df)["passed"].tolist() == [False]

    def test_g6d_gates_every_survey_at_one_percent(self):
        assert gate_g6d(pd.Series({2022: 0.002, 2024: 0.05}))["passed"].tolist() == [True, False]


def test_the_build_refuses_until_task_2_has_verified_ipums(monkeypatch):
    monkeypatch.setattr(ipums_variables, "VERIFICATION_STATUS", "unverified")
    with pytest.raises(RuntimeError, match="Task 2"):
        dws_detailed_panel.build_rebuilt_panel([2024])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_dws_detailed_panel.py tests/test_occ1990dd_reference.py -v`
Expected: FAIL — `ImportError: cannot import name 'load_census_2002_to_2010'`.

- [ ] **Step 3: Add the 2002→2010 loader to `occ1990dd_reference.py`**

Add the constant next to `CENSUS_2018_TO_2010_SHEET`:

```python
CENSUS_2002_TO_2010_SHEET = "2002to2010xwalk"
```

Append:

```python
def load_census_2002_to_2010(code_list_dir: str = CENSUS_CODE_LIST_DIR) -> pd.DataFrame:
    """2002 Census codes paired with every 2010 Census code each became, from the 2010 file's crosswalk sheet.

    Continuation rows leave the 2002 column blank, so it is forward-filled. 23
    codes split into several 2010 codes; five have no 2010 successor at all.
    """
    file_name, _ = CENSUS_CODE_LISTS["2010"]
    raw_df = pd.read_excel(os.path.join(code_list_dir, file_name), sheet_name=CENSUS_2002_TO_2010_SHEET, header=None, dtype=str)
    census_2002 = raw_df[1].where(_is_four_digit(raw_df[1]).fillna(False)).ffill()
    census_2010 = raw_df[4].where(_is_four_digit(raw_df[4]).fillna(False))
    pairs_df = pd.DataFrame({"census_2002": census_2002, "census_2010": census_2010}).dropna()
    return pairs_df.astype(int).drop_duplicates().reset_index(drop=True)
```

- [ ] **Step 4: Create `dws_detailed_panel.py`**

```python
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
    """The Census occupation-code vintage CPS used in a survey's January."""
    if survey_year <= 1992:
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
    """Supplement respondents aged 20+ displaced for one of BLS's three reasons."""
    weights = person_df[ipums_variables.DWS_WEIGHT_VARIABLE].astype(float)
    displaced_mask = (
        (weights > 0)
        & (person_df["AGE"] >= ipums_variables.DWS_MINIMUM_AGE)
        & person_df[ipums_variables.DWS_REASON_VARIABLE].isin(ipums_variables.DWS_DISPLACED_REASON_CODES)
    )
    return person_df[displaced_mask].copy()


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
    unmapped_share = float(1 - mapped_df["allocated_weight"].sum() / total_weight) if total_weight > 0 else 0.0
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
        print(f"  {survey_year}: {len(displaced_df)} displaced records, unmapped share {unmapped_by_survey[survey_year]:.4f}")

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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_dws_detailed_panel.py tests/test_occ1990dd_reference.py -v`
Expected: all PASS.

- [ ] **Step 6: Lint and commit**

```bash
.venv/bin/ruff format dws_detailed_panel.py occ1990dd_reference.py tests/test_dws_detailed_panel.py tests/test_occ1990dd_reference.py
.venv/bin/ruff check --fix dws_detailed_panel.py occ1990dd_reference.py tests/test_dws_detailed_panel.py tests/test_occ1990dd_reference.py
git add dws_detailed_panel.py occ1990dd_reference.py tests/test_dws_detailed_panel.py tests/test_occ1990dd_reference.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "Tabulate displaced workers onto the Dorn partition behind gates G3 and G6D

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: Build and promote the DWS seed [KEY-GATED]

Every step needs the key, Task 2 passed, and 2b not stopped in Task 2 Step 6.

**Files:**
- Create: `seeds/dws_detailed_panel.csv`, `seeds/dws_detailed_gates.csv`

- [ ] **Step 1: Download every survey**

Run: `.venv/bin/python download_ipums_cps.py dws`
Expected: one line per survey year in `DWS_SURVEY_YEARS`, each naming a directory or `no published sample`. Record which years are absent, 2002 and 2004 especially, for Task 17's docs.

- [ ] **Step 2: Build and read the gates**

Run: `.venv/bin/python dws_detailed_panel.py build`
Expected: one line per survey, then `Gates: ALL PASS`.

**If G3 or G6D fails, STOP.** Never loosen the thresholds. Report the failing rows to the user. The likeliest G3 causes are a displaced-reason code set or a tenure cut that does not match BLS's Table 5 universe, or a coding-vintage boundary in `lost_job_raw_vintage`. A G6D failure means the fallback route loses weight; list the unmapped raw codes and their weight before reporting.

- [ ] **Step 3: Promote and commit**

```bash
.venv/bin/python dws_detailed_panel.py promote
git add seeds/dws_detailed_panel.csv seeds/dws_detailed_gates.csv
PATH="$PWD/.venv/bin:$PATH" git commit -m "Commit the detailed DWS panel seed, gates G3 and G6D passing

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

The CLAUDE.md seeds paragraph added in Task 8 Step 9 already covers this seed.

---
### Task 16: Displacement validation at the Dorn-group level

No key needed to build and test. Spec § Analysis choices, 2b: one correlation per survey, never pooled; headline all-tenures share, with long-tenured and rate as sensitivities.

**Files:**
- Create: `dws_detailed_validation.py`
- Modify: `synthesize_composition.py` (`run_stage`), `CLAUDE.md`
- Test: `tests/test_dws_detailed_validation.py`

**Interfaces:**
- Consumes: `composition_displacement_validation.correlate_with_leave_one_out`, `MINIMUM_GROUPS`; `cps_detailed_measurement.load_detailed_panel`, `HEADLINE_UNIVERSE`; `cps_detailed_validation.UNIT_SCORES_OUTPUT_PATH`, `BRIDGE_CHECK_OUTPUT_PATH` (Task 13); `dws_detailed_panel.SEED_PATH`; `occ1990dd_reference.load_occ1990dd_groups`; `occ1990dd_soc_bridge.g4_passed`.
- Produces: `latest_complete_employment(panel_df) -> pd.Series`, `group_employment(panel_df, groups_df, year) -> pd.Series`, `predicted_by_group(unit_scores_df, unit_employment, groups_df, rate_column) -> DataFrame[dorn_group, predicted_displaced, employment, predicted_rate]`, `build_detailed_displacement_comparison(dws_panel_df, unit_scores_df, panel_df, groups_df) -> DataFrame[OUTPUT_COLUMNS]`, `run(...) -> DataFrame | None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dws_detailed_validation.py`:

```python
"""Tests for dws_detailed_validation.py — per-survey displacement validation at Dorn-group level."""

import pandas as pd
import pytest

from dws_detailed_validation import build_detailed_displacement_comparison, latest_complete_employment, predicted_by_group

GROUPS = ["exec", "prof", "cleric", "retsales", "product", "operator"]


def _inputs(observed_multiplier):
    groups_df = pd.DataFrame({"occ1990dd": range(1, 7), "dorn_group": GROUPS})
    unit_scores_df = pd.DataFrame(
        {
            "occ1990dd": range(1, 7),
            "composition_gross_displacement": [0.01, 0.02, 0.03, 0.04, 0.05, 0.06],
            "dynamic_gross_displacement": 0.02,
        }
    )
    panel_df = pd.DataFrame(
        [
            {"year": year, "occ1990dd": code, "universe": "all_employed", "employed_thousands": 1000.0, "months_observed": months}
            for year, months in ((2022, 12), (2023, 12), (2024, 12), (2025, 12), (2026, 8))
            for code in range(1, 7)
        ]
    )
    dws_panel_df = pd.DataFrame(
        [
            {"survey_year": 2024, "dorn_group": group, "tenure_class": "all_tenures", "displaced_thousands": observed_multiplier(index)}
            for index, group in enumerate(GROUPS)
        ]
    )
    return dws_panel_df, unit_scores_df, panel_df, groups_df


def test_latest_complete_year_ignores_a_partial_year():
    _, _, panel_df, _ = _inputs(lambda index: 1.0)
    assert latest_complete_employment(panel_df).index.name == "occ1990dd"
    assert len(latest_complete_employment(panel_df)) == 6


def test_predicted_displacement_is_rate_times_employment_summed_per_group():
    _, unit_scores_df, panel_df, groups_df = _inputs(lambda index: 1.0)
    predicted_df = predicted_by_group(
        unit_scores_df, latest_complete_employment(panel_df), groups_df, "composition_gross_displacement"
    ).set_index("dorn_group")
    assert predicted_df.loc["cleric", "predicted_displaced"] == pytest.approx(30.0)
    assert predicted_df.loc["cleric", "predicted_rate"] == pytest.approx(0.03)


def test_observed_proportional_to_predicted_gives_a_perfect_share_correlation():
    comparison_df = build_detailed_displacement_comparison(*_inputs(lambda index: 5.0 * (index + 1)))
    headline = comparison_df[(comparison_df["model"] == "composition") & (comparison_df["measure"] == "share")]
    assert headline["pearson_r"].iloc[0] == pytest.approx(1.0)
    assert headline["n_groups"].iloc[0] == 6


def test_a_constant_prediction_gives_no_correlation_row():
    comparison_df = build_detailed_displacement_comparison(*_inputs(lambda index: 5.0 * (index + 1)))
    assert comparison_df[comparison_df["model"] == "dynamic"].empty
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_dws_detailed_validation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dws_detailed_validation'`.

- [ ] **Step 3: Create `dws_detailed_validation.py`**

```python
"""
dws_detailed_validation.py
──────────────────────────
Phase 2b of the deep history extension: each model's predicted displacement
against measured displacement per Dorn occupation group (~25 groups), one
correlation per Displaced Worker Supplement survey — the ten-group comparison in
composition_displacement_validation.py at 2.5 times the resolution.

Pinned choices (spec § Analysis choices, 2b): the headline is all-tenures
displacement as a share per group; long-tenured and the rate form are
sensitivities. Surveys are never pooled. The predicted vector — each unit's
per-occupation displacement rate through the label bridge, times its CPS
employment in the latest complete year — is identical across surveys, so a
consistent sign across surveys is not independent evidence and is never turned
into a sign test or an averaged r. At n≈25 a single survey needs r ≈ 0.40 to be
individually significant.

The rate form divides each group's displaced count by its CPS employment in the
year before the survey. The recall window covers three to five years, so this is
an approximation, which is why the rate is a sensitivity and not the headline.

Withheld, like both detailed CPS levels, when gate G4 failed: the predictions
travel through the same bridge.

Inputs:
  • seeds/dws_detailed_panel.csv, seeds/cps_detailed_occupation_panel.csv, seeds/occ1990dd_groups.csv
  • data/output/occ1990dd_scores.csv, data/output/occ1990dd_bridge_check.csv (cps_detailed_validation.py)
Outputs:
  • data/output/composition_model_displacement_validation_detailed.csv
"""

import os
import warnings

import pandas as pd
from scipy import stats

from composition_displacement_validation import MINIMUM_GROUPS, correlate_with_leave_one_out
from cps_detailed_measurement import HEADLINE_UNIVERSE, load_detailed_panel
from cps_detailed_validation import BRIDGE_CHECK_OUTPUT_PATH, UNIT_SCORES_OUTPUT_PATH
from dws_detailed_panel import SEED_PATH as DWS_SEED_PATH
from occ1990dd_reference import load_occ1990dd_groups
from occ1990dd_soc_bridge import g4_passed

OUTPUT_PATH = "data/output/composition_model_displacement_validation_detailed.csv"
OUTPUT_COLUMNS = ["survey_year", "model", "tenure_class", "measure", "pearson_r", "pearson_p", "spearman_r", "spearman_p", "n_groups"]
MODEL_RATE_COLUMNS = {"composition": "composition_gross_displacement", "dynamic": "dynamic_gross_displacement"}
HEADLINE_TENURE_CLASS = "all_tenures"
HEADLINE_MEASURE = "share"
COMPLETE_YEAR_MONTHS = 12


def latest_complete_employment(panel_df: pd.DataFrame) -> pd.Series:
    """Each unit's CPS employment in the latest year with all twelve months."""
    complete_df = panel_df[(panel_df["universe"] == HEADLINE_UNIVERSE) & (panel_df["months_observed"] == COMPLETE_YEAR_MONTHS)]
    latest_df = complete_df[complete_df["year"] == complete_df["year"].max()]
    return latest_df.set_index("occ1990dd")["employed_thousands"]


def group_employment(panel_df: pd.DataFrame, groups_df: pd.DataFrame, year: int) -> pd.Series:
    """CPS employment per Dorn group in one year."""
    year_df = panel_df[(panel_df["universe"] == HEADLINE_UNIVERSE) & (panel_df["year"] == year)].merge(
        groups_df, on="occ1990dd", how="inner"
    )
    return year_df.groupby("dorn_group")["employed_thousands"].sum()


def predicted_by_group(unit_scores_df: pd.DataFrame, unit_employment: pd.Series, groups_df: pd.DataFrame, rate_column: str) -> pd.DataFrame:
    """A model's per-unit displacement rate times unit employment, summed per Dorn group, plus the implied group rate."""
    unit_df = unit_scores_df[["occ1990dd", rate_column]].dropna().merge(groups_df, on="occ1990dd", how="inner")
    unit_df = unit_df.assign(employment=unit_df["occ1990dd"].map(unit_employment)).dropna(subset=["employment"])
    unit_df["predicted_displaced"] = unit_df[rate_column] * unit_df["employment"]
    grouped_df = unit_df.groupby("dorn_group", as_index=False).agg(
        predicted_displaced=("predicted_displaced", "sum"), employment=("employment", "sum")
    )
    grouped_df["predicted_rate"] = grouped_df["predicted_displaced"] / grouped_df["employment"]
    return grouped_df


def _share_correlation(observed_df: pd.DataFrame, predicted_df: pd.DataFrame) -> dict[str, float] | None:
    merged_df = observed_df.merge(predicted_df, on="dorn_group", how="inner")
    if merged_df["predicted_displaced"].nunique() < 2:
        return None
    merged_df["observed_share"] = merged_df["displaced_thousands"] / merged_df["displaced_thousands"].sum()
    merged_df["predicted_share"] = merged_df["predicted_displaced"] / merged_df["predicted_displaced"].sum()
    return correlate_with_leave_one_out(merged_df.rename(columns={"dorn_group": "dws_group"}), "predicted_share")


def _rate_correlation(observed_df: pd.DataFrame, predicted_df: pd.DataFrame, employment_by_group: pd.Series) -> dict[str, float] | None:
    merged_df = observed_df.merge(predicted_df[["dorn_group", "predicted_rate"]], on="dorn_group", how="inner")
    merged_df["observed_rate"] = merged_df["displaced_thousands"] / merged_df["dorn_group"].map(employment_by_group)
    merged_df = merged_df.dropna(subset=["observed_rate", "predicted_rate"])
    if len(merged_df) < MINIMUM_GROUPS or merged_df["predicted_rate"].nunique() < 2:
        return None
    pearson_r, pearson_p = stats.pearsonr(merged_df["predicted_rate"], merged_df["observed_rate"])
    spearman_r, spearman_p = stats.spearmanr(merged_df["predicted_rate"], merged_df["observed_rate"])
    return {"pearson_r": pearson_r, "pearson_p": pearson_p, "spearman_r": spearman_r, "spearman_p": spearman_p, "n_groups": len(merged_df)}


def build_detailed_displacement_comparison(
    dws_panel_df: pd.DataFrame, unit_scores_df: pd.DataFrame, panel_df: pd.DataFrame, groups_df: pd.DataFrame
) -> pd.DataFrame:
    """One row per (survey, model, tenure class, measure) with Pearson and Spearman r."""
    unit_employment = latest_complete_employment(panel_df)
    predictions = {
        model: predicted_by_group(unit_scores_df, unit_employment, groups_df, rate_column)
        for model, rate_column in MODEL_RATE_COLUMNS.items()
        if rate_column in unit_scores_df.columns
    }
    comparison_rows = []
    for (survey_year, tenure_class), observed_df in dws_panel_df.groupby(["survey_year", "tenure_class"]):
        observed_df = observed_df[["dorn_group", "displaced_thousands"]]
        employment_by_group = group_employment(panel_df, groups_df, int(survey_year) - 1)
        for model, predicted_df in predictions.items():
            for measure, correlations in (
                ("share", _share_correlation(observed_df, predicted_df)),
                ("rate", _rate_correlation(observed_df, predicted_df, employment_by_group)),
            ):
                if correlations is None:
                    continue
                comparison_rows.append(
                    {"survey_year": int(survey_year), "model": model, "tenure_class": tenure_class, "measure": measure}
                    | {column: correlations[column] for column in ("pearson_r", "pearson_p", "spearman_r", "spearman_p", "n_groups")}
                )
    return pd.DataFrame(comparison_rows, columns=OUTPUT_COLUMNS)


def run(dws_seed_path: str = DWS_SEED_PATH) -> pd.DataFrame | None:
    """Score both models' displacement against every DWS survey at Dorn-group level."""
    if not os.path.exists(dws_seed_path):
        warnings.warn(
            f"{dws_seed_path} absent — built locally from IPUMS (dws_detailed_panel.py); detailed DWS validation skipped", stacklevel=2
        )
        return None
    panel_df = load_detailed_panel()
    if panel_df is None or not os.path.exists(UNIT_SCORES_OUTPUT_PATH):
        warnings.warn("The detailed CPS panel or occ1990dd scores are absent; detailed DWS validation skipped", stacklevel=2)
        return None
    if not os.path.exists(BRIDGE_CHECK_OUTPUT_PATH) or not g4_passed(pd.read_csv(BRIDGE_CHECK_OUTPUT_PATH)):
        warnings.warn(
            "Gate G4 has not passed; detailed DWS validation withheld, since its predictions travel through the bridge", stacklevel=2
        )
        return None

    comparison_df = build_detailed_displacement_comparison(
        pd.read_csv(dws_seed_path), pd.read_csv(UNIT_SCORES_OUTPUT_PATH), panel_df, load_occ1990dd_groups()
    )
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    comparison_df.to_csv(OUTPUT_PATH, index=False)

    print("\n── Predicted vs measured displacement, Dorn occupation groups, every DWS survey ──")
    headline_df = comparison_df[(comparison_df["tenure_class"] == HEADLINE_TENURE_CLASS) & (comparison_df["measure"] == HEADLINE_MEASURE)]
    for model, model_df in headline_df.groupby("model"):
        print(
            f"  {model:<12} Pearson r {model_df['pearson_r'].min():+.3f} to {model_df['pearson_r'].max():+.3f} "
            f"(median {model_df['pearson_r'].median():+.3f}) across {len(model_df)} surveys; "
            f"{int((model_df['pearson_p'] < 0.05).sum())} individually significant; n≈{int(model_df['n_groups'].median())} needs r≈0.40"
        )
    print("  Surveys share one predicted vector, so a consistent sign is not independent evidence and is not pooled.")
    print(f"  ✓ {OUTPUT_PATH}")
    return comparison_df
```

- [ ] **Step 4: Wire it into the composition stage**

In `synthesize_composition.py`'s `run_stage`, add `import dws_detailed_validation` to the function-local imports and call it last:

```python
    composition_displacement_validation.run()
    # Phase 2b: Dorn-group displacement validation from the IPUMS seeds; skips when absent.
    dws_detailed_validation.run()
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_dws_detailed_validation.py tests/test_composition_model.py -v`
Expected: all PASS.

- [ ] **Step 6: Add the Outputs Reference row**

In `CLAUDE.md`'s data-file table, after the `composition_model_displacement_validation_panel.csv` row:

```markdown
| `composition_model_displacement_validation_detailed.csv` | `dws_detailed_validation.py` | Predicted vs measured displacement per Dorn occupation group (~25 groups, `seeds/occ1990dd_groups.csv`), one row per (survey_year, model, tenure_class, measure). Headline: `tenure_class == "all_tenures"`, `measure == "share"`; long-tenured and the rate form are sensitivities. n≈25 needs r≈0.40 per survey. The predicted vector is identical across surveys, so sign consistency is not pooled. Tabulated from IPUMS microdata by `dws_detailed_panel.py`; withheld if gate G4 failed. |
```

- [ ] **Step 7: Lint and commit**

```bash
.venv/bin/ruff format dws_detailed_validation.py synthesize_composition.py tests/test_dws_detailed_validation.py
.venv/bin/ruff check --fix dws_detailed_validation.py synthesize_composition.py tests/test_dws_detailed_validation.py
git add dws_detailed_validation.py synthesize_composition.py tests/test_dws_detailed_validation.py CLAUDE.md
PATH="$PWD/.venv/bin:$PATH" git commit -m "Validate predicted displacement per Dorn group against every DWS survey

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 17: Documentation and final verification

Steps 1–2 need no key. Steps 3–6 need the seeds from Tasks 8 and 15.

**Files:**
- Modify: `README.md`, `docs/framework.md`, `CLAUDE.md`, `docs/superpowers/specs/2026-09-23-deep-history-phase-2-design.md` (status line)
- Create: `docs/charts/composition_model_signal_over_time_cps_detailed.md`, `docs/charts/composition_model_signal_over_time_cps_major.md`

- [ ] **Step 1: README — the optional local build**

In `README.md`, after the section describing the CPS historical instrument, add:

```markdown
### Detailed occupations from IPUMS CPS (optional, local only)

The detailed CPS levels (~330 `occ1990dd` occupations and a 22-SOC-major rollup, 1983–2026) and the Dorn-group displacement validation are built from IPUMS CPS microdata. CI never builds them; it reads the committed seeds. To rebuild:

1. Register for IPUMS CPS at https://cps.ipums.org and create an API key at https://account.ipums.org/api_keys.
2. Add `IPUMS_API_KEY=...` to `.env`.
3. `uv sync --group ipums`
4. `uv run download_ipums_cps.py basic 1983 2026` and `uv run download_ipums_cps.py dws` (hours; resumable).
5. `uv run cps_detailed_panel.py build 1983 2026` and `uv run dws_detailed_panel.py build`. Read the gate records in `data/output/*_gates_rebuilt.csv`.
6. `uv run cps_detailed_panel.py promote` and `uv run dws_detailed_panel.py promote`. Both refuse unless every gate passed.

IPUMS terms prohibit redistributing microdata; only aggregate tables are committed. Please cite IPUMS CPS and Autor & Dorn (2013) when using these outputs.
```

- [ ] **Step 2: framework.md — the method, before any result**

In `docs/framework.md`, at the end of § Demand Composition Model, add a subsection `### Detailed occupations (deep history, Phase 2)`. It must say, in the spec's terms:
- the two levels and the DWS resolution;
- the published-crosswalk chain, and that G4's measured error is a **lower bound** for 1983–2002;
- that year-over-year growth at this grain is known to be mostly sampling noise and was **accepted by decision**, with the raw/corrected bracket as the only handling;
- the per-period eligibility rule and why the fixed set is only a sensitivity (it selects on the outcome);
- the asymmetric reading rule, strengthened at detailed grain;
- the pre-written outcome readings from the spec's § Expected outcomes.

Leave a `#### Results` heading whose body is written in Step 4. Commit Steps 1–2 together:

```bash
git add README.md docs/framework.md
PATH="$PWD/.venv/bin:$PATH" git commit -m "Document the detailed-occupation method and its local build

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 3: [SEED-GATED] Run the pipeline stage and read the results**

Run: `.venv/bin/python main.py composition`
Expected: the detailed panel section prints reliability, seam summaries and G4 per block. If G4 passes, both detailed levels print their era summaries, and the DWS section prints its per-survey ranges. If G4 fails, **stop**: the design returns for review (spec § Gates). Report the per-block r values to the user.

- [ ] **Step 4: [SEED-GATED] Write results into the docs, reading the pre-written rules first**

Before writing a sentence, reread the spec's § Expected outcomes and apply those readings to the numbers, not new ones. Then:
- Fill `docs/framework.md` § Detailed occupations → Results: headline and noise-corrected era means, the cycle-decomposition intercept, the sweep's range, G4's three block r values, median reliability, and the DWS headline range and count of significant surveys.
- Write `docs/charts/composition_model_signal_over_time_cps_detailed.md` and `..._cps_major.md` in the style of `docs/charts/composition_model_signal_over_time_cps.md`: what the chart shows, n per period, the headline numbers, what they license and what they do not.
- Append the measured headline figures to the CLAUDE.md rows for `composition_model_era_comparison_cps_detailed.csv`, `composition_cycle_decomposition_cps_detailed.csv`, `composition_model_era_comparison_cps_major.csv`, `cps_detailed_reliability.csv`, `occ1990dd_bridge_check.csv` and `composition_model_displacement_validation_detailed.csv`, the way the existing CPS rows carry theirs.
- Set the spec's status line to `**Status: implemented** — see docs/superpowers/plans/2026-09-23-deep-history-phase-2.md.`

- [ ] **Step 5: Full verification**

```bash
.venv/bin/python -m pytest tests/ -q
.venv/bin/ruff check . && .venv/bin/ruff format --check .
(cd data/output && sha256sum --check --quiet ../phase2_baseline_hashes.txt) && echo "BYTE-IDENTICAL"
```

Expected: every test passes (459 + this plan's), ruff clean, and `BYTE-IDENTICAL`. Every pre-existing output is unchanged with the new levels live.

- [ ] **Step 6: Commit**

```bash
git add docs/framework.md docs/charts/composition_model_signal_over_time_cps_detailed.md docs/charts/composition_model_signal_over_time_cps_major.md CLAUDE.md docs/superpowers/specs/2026-09-23-deep-history-phase-2-design.md
PATH="$PWD/.venv/bin:$PATH" git commit -m "Record the detailed-occupation results against the pre-written readings

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Deviations log

Record any change to a pinned choice made after a seed exists: the date, what changed, why, and the commit. Empty at plan time.

| Date | Change | Reason | Commit |
|---|---|---|---|
| 2026-09-24 | `select_displaced` now excludes all self-employed lost-job workers via the new `DWCLASS` variable (`DWS_SELF_EMPLOYED_CLASS_CODES = (4,)`), keeping missing/NIU records rather than guessing at them. G3's per-cell direct-route totals were bit-identical before and after (40/90 unchanged), because self-employed records already carried NIU `DWOCC`/`DWYEARS` in the raw microdata for every year G3 tests — this falsified the diagnosis report's leading hypothesis for G3's overcount even though the fix itself is correct and now in place. | BLS's published Table 5 population excludes all self-employed lost-job workers, incorporated and unincorporated alike; the prior selection had no such filter. See `.superpowers/sdd/2026-09-23-deep-history-phase-2/dws-selfemp-report.md`. | 50841bd |
| 2026-09-24 | G6D redefined to measure crosswalk loss only, among displaced records whose lost-job occupation was reported (`DWOCC1990 != 999` on the harmonized route; the raw fallback route's equivalent nonresponse code), at the unchanged 1% threshold. Occupation nonresponse itself (`DWOCC1990 == 999`) is now reported per survey alongside as gate "G6D-nonresponse", ungated (`gated=False`, `passed=NA`), and can never fail `all_gates_pass`. Proportional (missing-at-random) allocation of nonresponse is applied only to `dws_detailed_validation.py`'s secondary rate measure (`allocate_nonresponse_for_rate`, scaling each survey's observed group counts up by 1/(1 − that survey's nonresponse share) before dividing by employment); the headline share measure and gate G3 stay unallocated. The nonresponse share is carried forward via the gate record (`dws_detailed_panel.nonresponse_share_by_survey`, reading gate "G6D-nonresponse" rows) rather than a new panel column. | The prior G6D folded survey nonresponse and genuine crosswalk loss into one unmapped share, so a high-nonresponse survey could fail a gate meant to catch a broken crosswalk, or a low-nonresponse survey could mask real crosswalk loss. User-approved 2026-09-24 (see `.superpowers/sdd/2026-09-23-deep-history-phase-2/g6d-brief.md`). | 8b350e2 |
| 2026-09-24 | `select_displaced(person_df, survey_year)` now also excludes layoffs where the respondent expected recall to the same job within six months (`DWRECALL == 2`, kept for NIU/refused/don't-know/no-response) and lost jobs outside the survey's own reference window (`DWLASTWRK` outside 1-3 years for 1994+, 1-5 years for 1984-1992, via `ipums_variables.dws_lastwrk_window`). `DWRECALL` and `DWLASTWRK` were added to `ipums_cps_variables.DWS_VARIABLES`, with `dws_variables_for_year` (mirroring `variables_for_year`) omitting `DWRECALL` before the 1994 survey, the first year IPUMS publishes it; `download_ipums_cps.fetch_dws_survey` now requests that year-filtered list instead of the flat one. All 21 DWS extracts were moved to `data/raw/ipums/dws_before_recall` and re-downloaded. This closed G3 from 40/90 to 90/90 (see `g3-diagnosis2-report.md`) and reproduces BLS Table 8's all-tenures total to within 0.5k in every 2008-2024 survey. DWRECALL does not exist before 1994, so the recall exclusion is an unmeasured (disclosed, not patched) break at the 1992->1994 boundary; `measure_recall_rule_impact` sizes it for the 1994 and 1996 surveys — measured 2026-09-24: the recall rule removes 4.24% of the recall-included all-tenures weight in 1994 and 4.66% in 1996 (see `dws-definition-report.md` for the full computation). | BLS's published Table 5/8 population excludes both groups; the prior selection excluded neither, which is what made G3 fail on occupation-skewed cells (construction, farming, production — where seasonal/temporary recall-expecting layoffs concentrate) even after the self-employment and G6D fixes above. User-approved 2026-09-24 (see `.superpowers/sdd/2026-09-23-deep-history-phase-2/dws-definition-brief.md`). | 700362d |
| 2026-09-24 | Interpretation of the displacement validations now leads with the size-free rate measure, and every share result is shown beside a group-size-only benchmark, because a group's share of measured displacement turns out to be predicted about as well by its share of employment alone as by either model's predicted share (Dorn groups, newest survey: median r 0.905 for employment share vs 0.899 for the composition model's predicted share, `composition_model_displacement_validation_detailed.csv`; ten-group newest survey: 0.656 vs 0.220, `composition_model_displacement_size_benchmark.csv`). `dws_detailed_validation.py` gained a `model == "employment_size_benchmark"` row set and prints the rate summary before the share summary; `composition_displacement_validation.py` gained `build_displacement_size_benchmark_panel`, writing the new file by joining the composition/dynamic share r already in `composition_model_displacement_validation_panel.csv` rather than recomputing them. No pinned computation or existing output file changed — `composition_model_displacement_validation.csv` and `composition_model_displacement_validation_panel.csv` remain byte-identical to `data/phase2_baseline_hashes.txt`. User-approved 2026-09-24 (see `.superpowers/sdd/2026-09-23-deep-history-phase-2/size-benchmark-brief.md`). | pending |
