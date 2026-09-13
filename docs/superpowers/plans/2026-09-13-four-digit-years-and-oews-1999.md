# Four-Digit Years and OEWS to 1999 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the pipeline's year keys from two digits to four, then extend the OEWS series back to 1999 — six additional years, a second non-COVID downturn, and the prerequisite for the CPS deep-history work.

**Architecture:** The migration is mechanical: four-digit zero-padded year strings compare and sort lexicographically the same way they compare numerically, so the existing string comparisons in `attach_growth_columns` become correct without logic changes. Only constants, format strings, and hardcoded period keys move. The OEWS extension then adds six files whose structure was verified identical to 2005 apart from a banner-row offset and two column-name variants.

**Tech Stack:** Python 3.12, pandas, pytest, ruff. Node/Puppeteer for the download script. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-13-deep-history-extension-design.md`

## Global Constraints

- **No generic abbreviations.** Never `df`, `res`, `tmp`, `val`. Use `trend_df`, `oews_year_frame`, `header_row_index`. Convention only — no linter enforces it.
- **Domain terminology in names.** `year_key`, `period_key`, `major_group_rows`.
- **Module docstrings required** on every Python file — ruff `D100`.
- Ruff line length **140**. Selected rules: `E`, `W`, `F`, `I`, `N`, `D100`.
- Lint with `.venv/bin/ruff check <files>` and `.venv/bin/ruff format <files>` on **the specific files touched**, never `.` — a protected path under `.claude/` breaks a repo-wide format run.
- Tests: `.venv/bin/python -m pytest tests/ -q`.
- Run Python through `.venv/bin/python`, not `uv run`.
- **Never modify** `data/raw/`, `seeds/classified_all_tasks.csv`, `seeds/cps_a19_panel.csv`, `seeds/dws_displacement_panel.csv`, or `seeds/soc_crosswalks/`.
- Every new or changed pipeline output gets its `CLAUDE.md` "Outputs Reference" row updated in the same commit that changes it.
- Commit with `PATH="$PWD/.venv/bin:$PATH"` so the pre-commit hook finds ruff.
- Commit message trailers, exactly:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01XmW2c1TmZUtMwrc9wXueCi
  ```

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `analyze_bls.py` | Modify | `COMPOSITE_ANCHOR_YEAR`, `YEAR_CONFIGS`, OEWS sheet reading, major-group row selection |
| `harmonize_soc.py` | Modify | `GENERATION_BY_YEAR` keys |
| `validate_bls.py` | Modify | `_label`, period tick labels, hardcoded COVID columns |
| `composition_era_validation.py` | Modify | `AI_ERA_FIRST_PERIOD`, `COVID_PERIODS`, `_period_sort_key` sentinel, tick labels |
| `cps_panel.py` | Modify | `oews_reference_month` year parsing |
| `download_bls.js` | Modify | Six additional URLs |
| `tests/test_year_keys.py` | Create | Century-boundary regression tests |
| `tests/test_oews_historical_files.py` | Create | Banner-row detection, column variants, `00-0000` exclusion |
| `tests/test_harmonize_soc.py`, `tests/test_cps.py`, `tests/test_composition_era_validation.py`, `tests/test_composition_model.py`, `tests/test_composition_displacement_validation.py` | Modify | Four-digit fixtures |

---

## Verified facts this plan depends on

Checked against the real files on 2026-09-12 and 2026-09-13. Do not re-derive; do not assume differently.

| File | Header row | Group column | `major` rows | Title column |
|---|---:|---|---:|---|
| `national_1999_dl.xls` | 39 | `GROUP` | 22 | `OCC_TITLE` |
| `national_2000_dl.xls` | 38 | `GROUP` | 22 | **`OCC_TITL`** |
| `national_2001_dl.xls` | 0 | `GROUP` | 22 | `OCC_TITLE` |
| `national_2002_dl.xls` | 0 | `GROUP` | **23** | **`OCC_TITL`** |
| `national_may2003_dl.xls` | 0 | `GROUP` | 22 | `OCC_TITLE` |
| `national_may2004_dl.xls` | 0 | `GROUP` | 22 | `OCC_TITLE` |

All six carry `TOT_EMP` and `A_MEDIAN`. The 2002 file's 23rd "major" row is `00-0000` (All Occupations), which `select_major_group_rows` would turn into a bogus `soc_major = "00"`.

Download URLs (all under `https://www.bls.gov/oes/special-requests/`), note the naming change at 2003:

```
oes99nat.zip  oes00nat.zip  oes01nat.zip  oes02nat.zip  oesm03nat.zip  oesm04nat.zip
```

The century bug, executed on 2026-09-12 against the current code:

```
year "83":  classified as (current)   ← should be hist_
sorted periods: ['05_06', '22_23', '83_84', '99_00', 'composite']
_period_sort_key("99_00") == _period_sort_key("composite"):  True
```

---

### Task 1: Capture the pre-migration baseline

The migration must not change any number, only names. That claim is only checkable against a baseline captured first.

**Files:**
- Create: `/tmp/oews-baseline/` (scratch, not committed)

- [ ] **Step 1: Run the pipeline on the current code**

```bash
cd /workspaces/ai-exposure
.venv/bin/python main.py analyze synthesize validate composition
```

Expected: completes without error, writes `data/output/*.csv`.

- [ ] **Step 2: Snapshot every output CSV**

```bash
mkdir -p /tmp/oews-baseline
cp data/output/*.csv /tmp/oews-baseline/
ls /tmp/oews-baseline/ | wc -l
```

Expected: a non-zero count including `bls_trends.csv`, `bls_sector_trends.csv`, `occupation_dynamic_model_report.csv`, `composition_model_era_comparison.csv`.

- [ ] **Step 3: Record the baseline in the task notes**

No commit — this is scratch state used by Task 6. If the shell is lost, re-run Steps 1–2 on a clean checkout of `HEAD` before the migration commits.

---

### Task 2: Four-digit year keys in `analyze_bls.py`

**Files:**
- Modify: `analyze_bls.py:68-93` (`YEAR_CONFIGS`), `analyze_bls.py:94` (`COMPOSITE_ANCHOR_YEAR`), `analyze_bls.py:28-40` (docstring)
- Test: `tests/test_year_keys.py`

**Interfaces:**
- Produces: `COMPOSITE_ANCHOR_YEAR == "2022"`; `YEAR_CONFIGS` entries keyed `"2005"`…`"2025"`; `attach_growth_columns(trend_df, ["1999", "2000", ...])` emitting `hist_emp_growth_1999_2000` and `emp_growth_2022_2023`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_year_keys.py`:

```python
"""Tests for four-digit year keys — the century boundary that two-digit keys got wrong."""

import pandas as pd

from analyze_bls import COMPOSITE_ANCHOR_YEAR, attach_growth_columns


def _trend_frame(year_keys: list[str]) -> pd.DataFrame:
    columns = {"OCC_CODE": ["11-1011"]}
    for offset, year_key in enumerate(year_keys):
        columns[f"TOT_EMP_{year_key}"] = [100.0 + offset * 10]
        columns[f"A_MEDIAN_{year_key}"] = [50_000.0 + offset * 1_000]
    return pd.DataFrame(columns)


class TestCenturyBoundary:
    def test_anchor_year_is_four_digits(self):
        assert COMPOSITE_ANCHOR_YEAR == "2022"

    def test_twentieth_century_periods_carry_the_hist_prefix(self):
        year_keys = ["1999", "2000", "2022", "2023"]
        trend_df = attach_growth_columns(_trend_frame(year_keys), year_keys)
        assert "hist_emp_growth_1999_2000" in trend_df.columns
        assert "emp_growth_1999_2000" not in trend_df.columns

    def test_ai_era_periods_do_not_carry_the_hist_prefix(self):
        year_keys = ["1999", "2000", "2022", "2023"]
        trend_df = attach_growth_columns(_trend_frame(year_keys), year_keys)
        assert "emp_growth_2022_2023" in trend_df.columns
        assert "hist_emp_growth_2022_2023" not in trend_df.columns

    def test_pre_ai_composite_spans_from_the_earliest_year(self):
        year_keys = ["1999", "2000", "2022", "2023"]
        trend_df = attach_growth_columns(_trend_frame(year_keys), year_keys)
        pre_ai_columns = [column for column in trend_df.columns if "pre_ai" in column]
        assert pre_ai_columns, "expected a pre-AI composite column"

    def test_year_keys_sort_chronologically_as_strings(self):
        assert sorted(["2000", "1999", "2022", "1983"]) == ["1983", "1999", "2000", "2022"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_year_keys.py -v`

Expected: FAIL — `test_anchor_year_is_four_digits` asserts `"22" == "2022"`, and the `hist_` tests fail because `"1999" <= "22"` is True under string comparison, so *every* period gets the prefix.

- [ ] **Step 3: Change the constants**

In `analyze_bls.py`, line 94:

```python
COMPOSITE_ANCHOR_YEAR = "2022"
```

Rewrite `YEAR_CONFIGS` (lines 68-93) with four-digit keys, leaving paths untouched:

```python
YEAR_CONFIGS = [
    ("2005", "data/raw/bls/oesm05nat.zip"),
    ("2006", "data/raw/bls/oesm06nat.zip"),
    ("2007", "data/raw/bls/oesm07nat.zip"),
    ("2008", "data/raw/bls/oesm08nat.zip"),
    ("2009", "data/raw/bls/oesm09nat.zip"),
    ("2010", "data/raw/bls/oesm10nat.zip"),
    ("2011", "data/raw/bls/oesm11nat.zip"),
    ("2012", "data/raw/bls/oesm12nat.zip"),
    ("2013", "data/raw/bls/oesm13nat.zip"),
    ("2014", "data/raw/bls/oesm14nat.zip"),
    ("2015", "data/raw/bls/oesm15nat.zip"),
    ("2016", "data/raw/bls/oesm16nat.zip"),
    ("2017", "data/raw/bls/oesm17nat.zip"),
    ("2018", "data/raw/bls/oesm18nat.zip"),
    ("2019", "data/raw/bls/oesm19nat.zip"),
    ("2020", "data/raw/bls/oesm20nat.zip"),
    ("2021", "data/raw/bls/oesm21nat.zip"),
    ("2022", "data/raw/bls/oesm22nat.zip"),
    ("2023", "data/raw/bls/oesm23nat.zip"),
    ("2024", "data/raw/bls/oesm24all.zip"),
    ("2025", "data/raw/bls/oesm25all.zip"),
]
```

The 2024 and 2025 paths use the all-areas files (`oesm24all.zip`, `oesm25all.zip`) while every earlier year is national-only; both are already correct above.

In the module docstring (lines 28-40), replace every `{yy}` with `{yyyy}` and every example such as `emp_growth_{yy}_{yy}` with `emp_growth_{yyyy}_{yyyy}`.

- [ ] **Step 4: Fix the SOC-revision boundary labels in `main`**

`analyze_bls.py` prints a revision flag using two-digit period keys. Change:

```python
boundary_flag = "  ← SOC revision" if report_row["period"] in ("2009_2010", "2018_2019", "2020_2021") else ""
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_year_keys.py -v`

Expected: PASS, 5 tests.

- [ ] **Step 6: Lint and commit**

```bash
.venv/bin/ruff check analyze_bls.py tests/test_year_keys.py
.venv/bin/ruff format analyze_bls.py tests/test_year_keys.py
git add analyze_bls.py tests/test_year_keys.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "$(cat <<'EOF'
Key OEWS years by four digits rather than two

Two-digit keys compared and sorted as strings, so "1983" <= "2022" was
false and every twentieth-century period would have been emitted without
the hist_ prefix, landing in the AI-era grid charts. Four-digit
zero-padded keys compare lexicographically the same way they compare
numerically, so the existing comparisons become correct unchanged.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XmW2c1TmZUtMwrc9wXueCi
EOF
)"
```

---

### Task 3: Four-digit year keys in `harmonize_soc.py`

**Files:**
- Modify: `harmonize_soc.py:127-130` (`GENERATION_BY_YEAR`)
- Test: `tests/test_harmonize_soc.py`

**Interfaces:**
- Consumes: `COMPOSITE_ANCHOR_YEAR` from Task 2.
- Produces: `GENERATION_BY_YEAR` keyed `"2005"`…`"2025"`, values unchanged (`"soc2000"`, `"soc2010"`, `"hybrid"`, `"soc2018"`).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_harmonize_soc.py`:

```python
class TestGenerationYearKeys:
    def test_generation_keys_are_four_digit_years(self):
        assert all(len(year_key) == 4 and year_key.isdigit() for year_key in GENERATION_BY_YEAR)

    def test_soc_generation_boundaries_are_unchanged(self):
        assert GENERATION_BY_YEAR["2009"] == "soc2000"
        assert GENERATION_BY_YEAR["2010"] == "soc2010"
        assert GENERATION_BY_YEAR["2019"] == "hybrid"
        assert GENERATION_BY_YEAR["2021"] == "soc2018"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_harmonize_soc.py::TestGenerationYearKeys -v`

Expected: FAIL with `KeyError: '2009'`.

- [ ] **Step 3: Rewrite the mapping**

In `harmonize_soc.py`, lines 127-130:

```python
GENERATION_BY_YEAR = {
    **{year_key: "soc2000" for year_key in ("2005", "2006", "2007", "2008", "2009")},
    **{year_key: "soc2010" for year_key in ("2010", "2011", "2012", "2013", "2014", "2015", "2016", "2017", "2018")},
    **{year_key: "hybrid" for year_key in ("2019", "2020")},
    **{year_key: "soc2018" for year_key in ("2021", "2022", "2023", "2024", "2025")},
}
```

Rename the loop variable `year_suffix` to `year_key` throughout `harmonize_soc.py` for consistency with the new vocabulary — it is a pure rename, no behaviour change.

- [ ] **Step 4: Run the full harmonization test suite**

Run: `.venv/bin/python -m pytest tests/test_harmonize_soc.py -v`

Expected: PASS. Tests gated on `RAW_BLS_PRESENT` will skip if `data/raw/bls/oesm22nat.zip` is absent; that is fine.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/ruff check harmonize_soc.py tests/test_harmonize_soc.py
.venv/bin/ruff format harmonize_soc.py tests/test_harmonize_soc.py
git add harmonize_soc.py tests/test_harmonize_soc.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "$(cat <<'EOF'
Key SOC generations by four-digit years

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XmW2c1TmZUtMwrc9wXueCi
EOF
)"
```

---

### Task 4: Four-digit period keys in the validation and chart modules

**Files:**
- Modify: `validate_bls.py:74-79` (`_label`), `validate_bls.py:437`, `validate_bls.py:734` (tick labels), `validate_bls.py:498` (COVID columns)
- Modify: `composition_era_validation.py:96` (`AI_ERA_FIRST_PERIOD`), `:101` (`COVID_PERIODS`), `:122-127` (`_period_sort_key`), `:506` (tick labels)
- Modify: `cps_panel.py:271-281` (`oews_reference_month`)
- Test: `tests/test_composition_era_validation.py`, `tests/test_cps.py`

**Interfaces:**
- Consumes: four-digit column names produced by Task 2.
- Produces: `_label("2022_2023") == "2022→2023"`; `AI_ERA_FIRST_PERIOD == "2022_2023"`; `COVID_PERIODS == ("2019_2020", "2020_2021")`; `oews_reference_month([...]) == "2025-05"` from a `TOT_EMP_2025` column.

- [ ] **Step 1: Write the failing tests**

`tests/test_composition_era_validation.py` carries 40+ two-digit period literals across lines 40–242 (every one of them a 20xx year). Convert them mechanically, then add the new class below:

```bash
sed -i -E 's/_([0-9]{2})_([0-9]{2})\b/_20\1_20\2/g; s/"([0-9]{2})_([0-9]{2})"/"20\1_20\2"/g; s/TOT_EMP_25\b/TOT_EMP_2025/g' tests/test_composition_era_validation.py
grep -nE "\"[0-9]{2}_[0-9]{2}\"|growth_[0-9]{2}_[0-9]{2}|TOT_EMP_[0-9]{2}([^0-9]|$)" tests/test_composition_era_validation.py
```

The two sed rules are disjoint — the first requires an underscore before the first pair (`emp_growth_22_23`), the second requires a quote (`"05_06"`) — so neither can re-match the other's output. The `grep` must print nothing; any hit is a literal the rules missed, to be fixed by hand.

Then add:

```python
class TestFourDigitPeriods:
    def test_ai_era_boundary_is_four_digits(self):
        assert AI_ERA_FIRST_PERIOD == "2022_2023"

    def test_covid_periods_are_four_digits(self):
        assert COVID_PERIODS == ("2019_2020", "2020_2021")

    def test_period_key_strips_both_prefixes(self):
        assert period_key("hist_emp_growth_2007_2008") == "2007_2008"
        assert period_key("emp_growth_2023_2024") == "2023_2024"

    def test_century_spanning_period_does_not_collide_with_the_composite_sentinel(self):
        assert _period_sort_key("hist_emp_growth_1999_2000") != _period_sort_key("emp_growth_composite")

    def test_periods_sort_chronologically_across_the_century(self):
        columns = [
            "emp_growth_composite",
            "emp_growth_2022_2023",
            "hist_emp_growth_1999_2000",
            "hist_emp_growth_1983_1984",
        ]
        assert sorted(columns, key=_period_sort_key) == [
            "hist_emp_growth_1983_1984",
            "hist_emp_growth_1999_2000",
            "emp_growth_2022_2023",
            "emp_growth_composite",
        ]
```

Import `_period_sort_key` alongside the existing imports in that test file.

In `tests/test_cps.py`, line 141, change the fixture to four-digit columns:

```python
assert oews_reference_month(["OCC_CODE", "TOT_EMP_2023", "TOT_EMP_2025", "TOT_EMP_2024"]) == "2025-05"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_composition_era_validation.py tests/test_cps.py -v`

Expected: FAIL — `AI_ERA_FIRST_PERIOD` is `"22_23"`, and `oews_reference_month` returns `"202025-05"` because it prepends `"20"` to an already-four-digit suffix.

- [ ] **Step 3: Update `composition_era_validation.py`**

```python
AI_ERA_FIRST_PERIOD = "2022_2023"
COVID_PERIODS = ("2019_2020", "2020_2021")
```

Make the sentinel unambiguous and out of the range of real years, and tolerate a span-carrying pre-AI key:

```python
def _period_sort_key(growth_column: str) -> tuple[int, int]:
    key = period_key(growth_column)
    if key == "composite" or key.startswith("pre_ai"):
        return (9999, 9999)
    start_year, end_year = key.split("_")
    return (int(start_year), int(end_year))
```

At line 506, drop the hardcoded century prefix:

```python
axis.set_xticklabels([f"{p.split('_')[0]}→\n{p.split('_')[1]}" for p in ordered_periods], fontsize=8)
```

- [ ] **Step 4: Update `validate_bls.py`**

`_label` (lines 74-79):

```python
def _label(period: str) -> str:
    """Convert a period key like '2022_2023' or 'composite' to a readable label."""
    if period == "composite":
        return "Composite"
    parts = period.split("_")
    return f"{parts[0]}→{parts[1]}"
```

At lines 437 and 734, both instances:

```python
period_labels.append(f"{parts[0]}→\n{parts[1]}")
```

At line 498:

```python
covid_cols = ["hist_emp_growth_2019_2020", "hist_emp_growth_2020_2021"]
```

- [ ] **Step 5: Update `cps_panel.py`**

```python
def oews_reference_month(bls_trends_columns: list[str]) -> str:
    """
    Derive the OEWS reference month from the latest TOT_EMP_* column.

    OEWS estimates always carry a May reference month, so TOT_EMP_2025 means May 2025.
    """
    employment_columns = sorted(column for column in bls_trends_columns if column.startswith("TOT_EMP_"))
    if not employment_columns:
        raise ValueError("No TOT_EMP_* column found; cannot determine the OEWS reference month.")
    latest_year_key = employment_columns[-1].removeprefix("TOT_EMP_")
    return f"{latest_year_key}-05"
```

- [ ] **Step 6: Update the remaining two-digit test fixtures**

In `tests/test_composition_model.py`, line 42: `EMPLOYMENT_COLUMN = "TOT_EMP_2025"`.

In `tests/test_composition_displacement_validation.py`, replace every `TOT_EMP_25` literal with `TOT_EMP_2025` (lines 63, 64, 123, 129, 135, 139).

- [ ] **Step 7: Run the full test suite**

Run: `.venv/bin/python -m pytest tests/ -q`

Expected: all PASS.

- [ ] **Step 8: Lint and commit**

```bash
.venv/bin/ruff check validate_bls.py composition_era_validation.py cps_panel.py tests/
.venv/bin/ruff format validate_bls.py composition_era_validation.py cps_panel.py tests/
git add validate_bls.py composition_era_validation.py cps_panel.py tests/
PATH="$PWD/.venv/bin:$PATH" git commit -m "$(cat <<'EOF'
Key validation periods by four digits and fix the composite sentinel

_period_sort_key returned (99, 0) for both "99_00" and the composite
column, so the 1999-2000 period would have collided with the composite
sentinel. The sentinel moves out of the range of real years.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XmW2c1TmZUtMwrc9wXueCi
EOF
)"
```

---

### Task 5: Rename the pre-AI composite to carry its span

`hist_emp_growth_pre_ai` currently means 2005→2022. Once 1999 data lands it silently means 1999→2022. The name must carry the span.

**Files:**
- Modify: `analyze_bls.py:236-244` (`attach_growth_columns`)
- Test: `tests/test_year_keys.py`

**Interfaces:**
- Produces: `hist_emp_growth_pre_ai_{earliest_year}_2022` and `hist_wage_growth_pre_ai_{earliest_year}_2022`.

The `pre_ai` token must stay in the name: `discover_period_columns` in both `validate_bls.py` and `composition_era_validation.py` excludes historical columns with `"_pre_ai" not in column`, and a name like `hist_emp_growth_1999_2022` would otherwise be picked up as a year-over-year period.

- [ ] **Step 1: Write the failing test**

Replace `test_pre_ai_composite_spans_from_the_earliest_year` in `tests/test_year_keys.py`:

```python
class TestPreAiComposite:
    """Replaces test_pre_ai_composite_spans_from_the_earliest_year in TestCenturyBoundary."""

    def test_pre_ai_composite_name_carries_its_span(self):
        year_keys = ["1999", "2000", "2022", "2023"]
        trend_df = attach_growth_columns(_trend_frame(year_keys), year_keys)
        assert "hist_emp_growth_pre_ai_1999_2022" in trend_df.columns
        assert "hist_wage_growth_pre_ai_1999_2022" in trend_df.columns

    def test_pre_ai_composite_is_not_discovered_as_a_period(self):
        from composition_era_validation import discover_period_columns

        year_keys = ["1999", "2000", "2022", "2023"]
        trend_df = attach_growth_columns(_trend_frame(year_keys), year_keys)
        discovered = discover_period_columns(trend_df)
        assert not any("pre_ai" in column for column in discovered)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_year_keys.py -v`

Expected: FAIL — the column is still named `hist_emp_growth_pre_ai`.

- [ ] **Step 3: Rename the columns**

In `analyze_bls.py`, lines 236-244, replace the two literal column names:

```python
    earliest_year = available_years[0]
    if earliest_year < COMPOSITE_ANCHOR_YEAR and f"TOT_EMP_{earliest_year}" in trend_df.columns:
        pre_ai_span = f"pre_ai_{earliest_year}_{COMPOSITE_ANCHOR_YEAR}"
        trend_df[f"hist_emp_growth_{pre_ai_span}"] = (
            trend_df[f"TOT_EMP_{COMPOSITE_ANCHOR_YEAR}"] - trend_df[f"TOT_EMP_{earliest_year}"]
        ) / trend_df[f"TOT_EMP_{earliest_year}"]
        if f"A_MEDIAN_{earliest_year}" in trend_df.columns and f"A_MEDIAN_{COMPOSITE_ANCHOR_YEAR}" in trend_df.columns:
            trend_df[f"hist_wage_growth_{pre_ai_span}"] = (
                trend_df[f"A_MEDIAN_{COMPOSITE_ANCHOR_YEAR}"] - trend_df[f"A_MEDIAN_{earliest_year}"]
            ) / trend_df[f"A_MEDIAN_{earliest_year}"]
```

- [ ] **Step 4: Find and update every consumer**

```bash
grep -rn "pre_ai" --include="*.py" --include="*.md" . | grep -v "^./docs/superpowers/"
```

Update each hit. Names ending in an exact `"pre_ai"` string comparison must become prefix checks (`.startswith("pre_ai")` or `"_pre_ai" in column`, which already holds).

- [ ] **Step 5: Run the full test suite**

Run: `.venv/bin/python -m pytest tests/ -q`

Expected: all PASS.

- [ ] **Step 6: Lint and commit**

```bash
.venv/bin/ruff check analyze_bls.py tests/test_year_keys.py
.venv/bin/ruff format analyze_bls.py tests/test_year_keys.py
git add -A
PATH="$PWD/.venv/bin:$PATH" git commit -m "$(cat <<'EOF'
Name the pre-AI composite with its span

The column meant 2005->2022 and would have silently meant 1999->2022
once the older OEWS files land. The pre_ai token stays in the name so
discover_period_columns keeps excluding it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XmW2c1TmZUtMwrc9wXueCi
EOF
)"
```

---

### Task 6: Prove the migration changed names, not numbers

**Files:**
- Create: `/tmp/oews-baseline-check.py` (scratch, not committed)

**Interfaces:**
- Consumes: the baseline captured in Task 1.

- [ ] **Step 1: Re-run the pipeline on the migrated code**

```bash
cd /workspaces/ai-exposure
.venv/bin/python main.py analyze synthesize validate composition
```

Expected: completes without error.

- [ ] **Step 2: Write the comparison script**

```python
"""Compare post-migration outputs against the pre-migration baseline, ignoring year-key renames."""

import glob
import os
import re

import pandas as pd

BASELINE_DIR = "/tmp/oews-baseline"


def to_two_digit(column_name: str) -> str:
    """Rewrite four-digit year tokens back to two digits so baseline and current names line up."""
    column_name = re.sub(r"(?<![0-9])(?:19|20)(\d\d)(?![0-9])", r"\1", column_name)
    return column_name.replace("pre_ai_99_22", "pre_ai").replace("pre_ai_05_22", "pre_ai")


for baseline_path in sorted(glob.glob(f"{BASELINE_DIR}/*.csv")):
    name = os.path.basename(baseline_path)
    current_path = f"data/output/{name}"
    if not os.path.exists(current_path):
        print(f"{name}: MISSING from current output")
        continue
    baseline_df = pd.read_csv(baseline_path)
    current_df = pd.read_csv(current_path)
    current_df.columns = [to_two_digit(c) for c in current_df.columns]
    shared = [c for c in baseline_df.columns if c in current_df.columns]
    missing = [c for c in baseline_df.columns if c not in current_df.columns]
    if len(baseline_df) != len(current_df):
        print(f"{name}: ROW COUNT {len(baseline_df)} -> {len(current_df)}")
        continue
    numeric = [c for c in shared if pd.api.types.is_numeric_dtype(baseline_df[c])]
    diffs = [c for c in numeric if not baseline_df[c].equals(current_df[c])]
    status = "OK" if not diffs and not missing else "DIFF"
    print(f"{name}: {status} shared={len(shared)} unmatched={missing[:5]} numeric_diffs={diffs[:5]}")
```

- [ ] **Step 3: Run it**

Run: `.venv/bin/python /tmp/oews-baseline-check.py`

Expected: every file reports `OK`. Any `numeric_diffs` is a migration bug — the migration renames columns and must not move a single number. Investigate and fix before proceeding; do not rationalise a difference.

- [ ] **Step 4: No commit**

This task produces evidence, not code.

---

### Task 7: Read OEWS files that carry banner rows and column-name variants

**Files:**
- Modify: `analyze_bls.py` — `load_bls_year`, `select_major_group_rows`
- Test: `tests/test_oews_historical_files.py`

**Interfaces:**
- Produces: `detect_header_row(raw_frame) -> int`; `load_bls_year` normalising `OCC_TITL` to `OCC_TITLE`; `select_major_group_rows` excluding `00-0000`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_oews_historical_files.py`:

```python
"""Tests for reading the 1999-2004 OEWS national files: banner rows, column variants, and the 00-0000 row."""

import zipfile

import pandas as pd

from analyze_bls import detect_header_row, load_bls_year, select_major_group_rows


def _write_oews_zip(zip_path, header_row_offset: int, title_column: str, include_all_occupations: bool):
    """Build a small OEWS-shaped workbook with `header_row_offset` banner rows above the header."""
    rows = [
        {"occ_code": "11-0000", "group": "major", title_column: "Management Occupations", "tot_emp": 7_000_000, "a_median": 67_000},
        {"occ_code": "11-1011", "group": None, title_column: "Chief Executives", "tot_emp": 500_000, "a_median": 140_000},
        {"occ_code": "15-0000", "group": "major", title_column: "Computer Occupations", "tot_emp": 3_000_000, "a_median": 80_000},
    ]
    if include_all_occupations:
        rows.insert(
            0, {"occ_code": "00-0000", "group": "major", title_column: "All Occupations", "tot_emp": 127_000_000, "a_median": 30_000}
        )
    data_df = pd.DataFrame(rows)

    banner = pd.DataFrame([[f"banner line {i}"] + [None] * (len(data_df.columns) - 1) for i in range(header_row_offset)])
    excel_path = str(zip_path).replace(".zip", ".xlsx")
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        banner.to_excel(writer, index=False, header=False, startrow=0)
        data_df.to_excel(writer, index=False, header=True, startrow=header_row_offset)
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.write(excel_path, arcname="national_dl.xlsx")
    return zip_path


class TestHeaderDetection:
    def test_header_on_first_row_is_found(self):
        raw_df = pd.DataFrame([["occ_code", "group"], ["11-0000", "major"]])
        assert detect_header_row(raw_df) == 0

    def test_header_below_banner_rows_is_found(self):
        raw_df = pd.DataFrame([["1999 National OES Estimates", None], [None, None], ["occ_code", "group"]])
        assert detect_header_row(raw_df) == 2

    def test_missing_header_falls_back_to_row_zero(self):
        raw_df = pd.DataFrame([["nothing", "useful"], ["still", "nothing"]])
        assert detect_header_row(raw_df) == 0


class TestHistoricalFileShapes:
    def test_banner_rows_are_skipped(self, tmp_path):
        zip_path = _write_oews_zip(tmp_path / "oes99nat.zip", header_row_offset=39, title_column="occ_title", include_all_occupations=False)
        year_frame = load_bls_year(str(zip_path))
        assert "OCC_CODE" in year_frame.columns
        assert "OCC_TITLE" in year_frame.columns

    def test_occ_titl_variant_is_normalised(self, tmp_path):
        zip_path = _write_oews_zip(tmp_path / "oes00nat.zip", header_row_offset=38, title_column="occ_titl", include_all_occupations=False)
        year_frame = load_bls_year(str(zip_path))
        assert "OCC_TITLE" in year_frame.columns
        assert "OCC_TITL" not in year_frame.columns

    def test_all_occupations_row_is_not_a_major_group(self, tmp_path):
        zip_path = _write_oews_zip(tmp_path / "oes02nat.zip", header_row_offset=0, title_column="occ_titl", include_all_occupations=True)
        major_rows = select_major_group_rows(load_bls_year(str(zip_path)))
        assert "00" not in set(major_rows["soc_major"])
        assert set(major_rows["soc_major"]) == {"11", "15"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_oews_historical_files.py -v`

Expected: FAIL with `ImportError: cannot import name 'detect_header_row'`.

- [ ] **Step 3: Add header detection to `analyze_bls.py`**

Insert above `load_bls_year`:

```python
OEWS_HEADER_SCAN_ROWS = 60


def detect_header_row(raw_frame: pd.DataFrame) -> int:
    """
    Row index of the OEWS column header, which sits below a title banner in the 1997-2000 files.

    The 1999 and 2000 national files open with ~38 rows of survey description
    before the header; 2001 onward start at row 0. Falls back to 0 when no
    occ_code cell is found, which keeps the modern files on their existing path.
    """
    for row_index in range(min(OEWS_HEADER_SCAN_ROWS, len(raw_frame))):
        cells = [str(cell).strip().lower() for cell in raw_frame.iloc[row_index].tolist()]
        if "occ_code" in cells:
            return row_index
    return 0
```

- [ ] **Step 4: Use it in `load_bls_year` and normalise the title column**

Replace the single `pd.read_excel(excel_file)` call and the column-uppercasing line:

```python
        with zip_file.open(xls_files[0]) as excel_file:
            excel_bytes = io.BytesIO(excel_file.read())
        header_row_index = detect_header_row(pd.read_excel(excel_bytes, header=None, nrows=OEWS_HEADER_SCAN_ROWS))
        excel_bytes.seek(0)
        bls_dataframe = pd.read_excel(excel_bytes, header=header_row_index)

    bls_dataframe.columns = [str(c).upper().strip() for c in bls_dataframe.columns]
    # The 2000 and 2002 national files spell the title column occ_titl.
    bls_dataframe = bls_dataframe.rename(columns={"OCC_TITL": "OCC_TITLE"})
```

Add `import io` to the imports at the top of the module. The file must be read into a buffer because the zip member stream cannot be rewound for the second `read_excel` call.

- [ ] **Step 5: Exclude `00-0000` from the major-group rows**

In `select_major_group_rows`, after the `major_rows` filter:

```python
    major_rows = bls_dataframe[bls_dataframe[group_column] == "major"].copy()
    # The 2002 national file flags All Occupations (00-0000) as a major group; it is a total, not a sector.
    major_rows = major_rows[major_rows["OCC_CODE"].astype(str) != "00-0000"]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_oews_historical_files.py -v`

Expected: PASS, 6 tests.

- [ ] **Step 7: Confirm the modern files still load identically**

Run: `.venv/bin/python -m pytest tests/ -q` then re-run the Task 6 comparison script.

Expected: all tests PASS and every file still reports `OK`.

- [ ] **Step 8: Lint and commit**

```bash
.venv/bin/ruff check analyze_bls.py tests/test_oews_historical_files.py
.venv/bin/ruff format analyze_bls.py tests/test_oews_historical_files.py
git add analyze_bls.py tests/test_oews_historical_files.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "$(cat <<'EOF'
Read OEWS files with banner rows and occ_titl column variants

The 1999 and 2000 national files carry ~38 rows of survey description
above the header, the 2000 and 2002 files spell the title column
occ_titl, and the 2002 file flags 00-0000 as a major group, which would
have produced a bogus soc_major of "00".

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XmW2c1TmZUtMwrc9wXueCi
EOF
)"
```

---

### Task 8: Download and wire in OEWS 1999-2004

**Files:**
- Modify: `download_bls.js:29-51` (URL list)
- Modify: `analyze_bls.py` (`YEAR_CONFIGS`, module docstring)
- Modify: `harmonize_soc.py` (`GENERATION_BY_YEAR`)
- Test: `tests/test_year_keys.py`

**Interfaces:**
- Consumes: `detect_header_row` and the title-column normalisation from Task 7.
- Produces: `YEAR_CONFIGS` entries for `"1999"`…`"2004"`; `GENERATION_BY_YEAR` covering those years as `"soc2000"`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_year_keys.py`:

```python
class TestHistoricalYearCoverage:
    def test_year_configs_reach_1999(self):
        from analyze_bls import YEAR_CONFIGS

        configured_years = [year_key for year_key, _ in YEAR_CONFIGS]
        assert configured_years[0] == "1999"
        assert configured_years == sorted(configured_years)

    def test_every_configured_year_has_a_soc_generation(self):
        from analyze_bls import YEAR_CONFIGS
        from harmonize_soc import GENERATION_BY_YEAR

        for year_key, _ in YEAR_CONFIGS:
            assert year_key in GENERATION_BY_YEAR, f"{year_key} has no SOC generation"

    def test_pre_2005_years_are_soc_2000(self):
        from harmonize_soc import GENERATION_BY_YEAR

        for year_key in ("1999", "2000", "2001", "2002", "2003", "2004"):
            assert GENERATION_BY_YEAR[year_key] == "soc2000"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_year_keys.py::TestHistoricalYearCoverage -v`

Expected: FAIL — the first configured year is `"2005"`.

- [ ] **Step 3: Add the six URLs to `download_bls.js`**

Append to the `urls` array, after the 2005 entry. Note the naming change at 2003 — 1999-2002 have no `m`:

```javascript
    'https://www.bls.gov/oes/special-requests/oesm04nat.zip',
    'https://www.bls.gov/oes/special-requests/oesm03nat.zip',
    'https://www.bls.gov/oes/special-requests/oes02nat.zip',
    'https://www.bls.gov/oes/special-requests/oes01nat.zip',
    'https://www.bls.gov/oes/special-requests/oes00nat.zip',
    'https://www.bls.gov/oes/special-requests/oes99nat.zip',
```

Update the comment above the array:

```javascript
  // SOC 2018 codes: 2019+. SOC 2010 codes: 2010-2018. SOC 2000 codes: 1999-2009.
  // 1999-2002 are annual estimates; 2003 onward carry a May reference month, so
  // the 2002->2003 interval is not a clean twelve months. 1997-1998 are omitted:
  // they use the pre-SOC five-digit OES coding system with div/maj group headers.
```

- [ ] **Step 4: Add the six years to `YEAR_CONFIGS`**

Prepend six entries to `YEAR_CONFIGS` in `analyze_bls.py`, ahead of the existing `"2005"` row. The head of the list becomes:

```python
YEAR_CONFIGS = [
    ("1999", "data/raw/bls/oes99nat.zip"),
    ("2000", "data/raw/bls/oes00nat.zip"),
    ("2001", "data/raw/bls/oes01nat.zip"),
    ("2002", "data/raw/bls/oes02nat.zip"),
    ("2003", "data/raw/bls/oesm03nat.zip"),
    ("2004", "data/raw/bls/oesm04nat.zip"),
    ("2005", "data/raw/bls/oesm05nat.zip"),
    # ... 2006-2025 unchanged from Task 2
]
```

- [ ] **Step 5: Add the six years to `GENERATION_BY_YEAR`**

```python
    **{year_key: "soc2000" for year_key in ("1999", "2000", "2001", "2002", "2003", "2004", "2005", "2006", "2007", "2008", "2009")},
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_year_keys.py -v`

Expected: PASS.

- [ ] **Step 7: Download the files and run the pipeline**

```bash
node download_bls.js
ls -la data/raw/bls/oes99nat.zip data/raw/bls/oesm04nat.zip
.venv/bin/python main.py analyze
```

Expected: the two listed files exist and are non-empty. `analyze` prints `Building trends for years: ['1999', '2000', ..., '2025']` and writes `bls_sector_trends.csv` with 22 rows.

- [ ] **Step 8: Verify the sector series is complete for every new year**

```bash
.venv/bin/python -c "
import pandas as pd
sector_trends_df = pd.read_csv('data/output/bls_sector_trends.csv')
print('rows:', len(sector_trends_df))
for year_key in ('1999','2000','2001','2002','2003','2004'):
    column = f'TOT_EMP_{year_key}'
    print(year_key, 'present' if column in sector_trends_df.columns else 'MISSING',
          int(sector_trends_df[column].notna().sum()) if column in sector_trends_df.columns else 0)
"
```

Expected: 22 rows, and all six years present with 22 non-null values each. A count of 23 means the `00-0000` exclusion from Task 7 regressed.

- [ ] **Step 9: Lint and commit**

```bash
.venv/bin/ruff check analyze_bls.py harmonize_soc.py tests/test_year_keys.py
.venv/bin/ruff format analyze_bls.py harmonize_soc.py tests/test_year_keys.py
node --check download_bls.js
git add analyze_bls.py harmonize_soc.py download_bls.js tests/test_year_keys.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "$(cat <<'EOF'
Extend the OEWS series back to 1999

Adds six national files, verified to carry SOC 2000 codes and 22
major-group summary rows - structurally the same file as 2005. Stops at
1999: the 1997 and 1998 files use the pre-SOC five-digit OES coding
system, for which BLS publishes no clean crosswalk.

Widens the series from 20 year-over-year periods to 26 and brings the
2001 recession inside the window.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XmW2c1TmZUtMwrc9wXueCi
EOF
)"
```

---

### Task 9: Documentation

**Files:**
- Modify: `CLAUDE.md` — "Key Design Decisions" § BLS downloads, "Outputs Reference" rows for `bls_trends.csv`, `bls_sector_trends.csv`, `bls_harmonized_trends.csv`
- Modify: `analyze_bls.py` module docstring
- Modify: `docs/charts/model_signal_over_time.md`, `docs/charts/composition_model_signal_over_time.md`

- [ ] **Step 1: Update the `CLAUDE.md` BLS paragraph**

The paragraph beginning "**BLS downloads require Node.js.**" states "SOC code generations: SOC 2000 (2005–2009)". Change to "SOC 2000 (1999–2009)" and add:

```
The series starts at 1999, the first OEWS year coded on SOC 2000 with 22
major-group summary rows; 1997 and 1998 use the pre-SOC five-digit OES coding
system with div/maj group headers and are deliberately excluded. Files
1999–2000 carry ~38 banner rows above the column header, 2000 and 2002 spell
the title column `occ_titl`, and 2002 flags `00-0000` as a major group —
`load_bls_year` and `select_major_group_rows` handle all three. 1999–2002 are
annual estimates while 2003 onward carry a May reference month, so the
2002→2003 interval is not a clean twelve months.
```

- [ ] **Step 2: Update the Outputs Reference rows**

In the `bls_trends.csv` row, change "2005–2025" to "1999–2025" and `hist_` column examples to four-digit form. Do the same for `bls_sector_trends.csv` ("Complete for all 22 sectors in every year 2005–2025" → "1999–2025") and `bls_harmonized_trends.csv`.

- [ ] **Step 3: Update the `analyze_bls.py` docstring input list**

Add the six new files to the "Inputs" block:

```
  • oes99nat.zip – oes02nat.zip — annual-reference national files (1999–2002)
  • oesm03nat.zip, oesm04nat.zip — May-reference national files (2003–2004)
```

- [ ] **Step 4: Update the two chart docs**

Both docs name the span in their title and body ("2005→2025", "(2015→2025)"). Update to the new span, and add one sentence to each noting that periods before 2005 come from OEWS files with an annual rather than May reference period before 2003.

- [ ] **Step 5: Verify no stale two-digit period keys remain in docs**

```bash
grep -rnE "emp_growth_[0-9]{2}_[0-9]{2}|TOT_EMP_[0-9]{2}([^0-9]|$)" --include="*.md" . | grep -v "^./docs/superpowers/"
```

Expected: no output. Any hit is a stale reference to fix.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md analyze_bls.py docs/
PATH="$PWD/.venv/bin:$PATH" git commit -m "$(cat <<'EOF'
Document the 1999 series start and four-digit year keys

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XmW2c1TmZUtMwrc9wXueCi
EOF
)"
```

---

### Task 10: Full pipeline run and result review

**Files:** none — verification only.

- [ ] **Step 1: Run the whole pipeline**

```bash
.venv/bin/python main.py analyze synthesize plot validate composition
```

Expected: completes without error.

- [ ] **Step 2: Confirm the period count grew**

```bash
.venv/bin/python -c "
import pandas as pd
from composition_era_validation import discover_period_columns
sector_trends_df = pd.read_csv('data/output/bls_sector_trends.csv')
periods = discover_period_columns(sector_trends_df)
print('periods:', len(periods))
print('first:', periods[0], '| last:', periods[-1])
"
```

Expected: 26 periods, first `hist_emp_growth_1999_2000`, last `emp_growth_2024_2025`.

- [ ] **Step 3: Confirm the AI-era results did not move**

Re-run the Task 6 comparison script, restricted to the AI-era outputs:

```bash
.venv/bin/python /tmp/oews-baseline-check.py | grep -E "dynamic_model_report|exposure_report|equilibration|jackknife"
```

Expected: `OK` for each. These are cross-sectional over 2022–2025 and must be unaffected by adding pre-2005 history. A `DIFF` here means a historical year leaked into an AI-era computation — investigate before continuing.

- [ ] **Step 4: Review the new era-comparison output**

```bash
cat data/output/composition_model_era_comparison.csv
cat data/output/composition_cycle_decomposition.csv
```

Read the numbers against the spec's asymmetric interpretation rule — a positive result is strong, a null is uninformative. Report both, and do not reinterpret either.

- [ ] **Step 5: Report completion**

Summarise: number of periods before and after, whether the AI-era regression check passed, and what the era comparison and cycle decomposition now say with three downturns rather than one.

---

## Out of scope for this plan

- The CPS 1983 panel, the `OCC1990` allocation matrix, and the IPUMS tooling — **Plan B**.
- `D` and the DWS panel back to 1984 — **Plan C**.
- OEWS 1997–1998 (pre-SOC five-digit coding, no clean crosswalk).
- Wages before 1999, monthly CPS resolution, detailed-occupation deep history, DOT-1991 labels.
