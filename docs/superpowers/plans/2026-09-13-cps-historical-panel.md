# CPS Historical Panel (1983→2026) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a second, independent employment instrument covering **1983→2026** — 43 years and five recessions — from the BLS public API alone, and run the demand-composition era test against it.

**Architecture:** BLS publishes CPS employment by occupation group as monthly series that span 1983 to the present under one series ID, because it reconstructed 1983–99 onto the 2002 Census/SOC classification. Ten of those series are the leaf occupation groups, and their names are byte-identical to the `DWS_TO_SOC_MAJOR` keys the repo already maps to SOC. So this plan needs no microdata, no IPUMS account, and no Puppeteer: fetch ten series, annualise, and reuse `attach_growth_columns` to get a trend table in the exact layout the validation modules already read.

**Tech Stack:** Python 3.12, pandas, scipy, requests. No new dependencies. Reuses `historical_displacement.fetch_annual_means` (chunking + on-disk caching), `analyze_bls.attach_growth_columns`, and `composition_displacement_validation.soc_major_to_dws_group`.

**Spec:** `docs/superpowers/specs/2026-09-13-deep-history-extension-design.md`

## Global Constraints

- **No generic abbreviations.** Never `df`, `res`, `tmp`, `val`. Use `cps_panel_df`, `group_employment_series`, `year_key`.
- **Domain terminology in names**: `cps_group`, `employed_thousands`, `period_key`.
- **Module docstrings required** on every Python file — ruff `D100`.
- Ruff line length **140**; rules `E`, `W`, `F`, `I`, `N`, `D100`. Run ruff only on files you touch, never on `.`.
- Tests: `.venv/bin/python -m pytest tests/ -q`. Currently **268 passed, 6 skipped, 1 xfailed**.
- Run Python through `.venv/bin/python`, not `uv run`.
- **Never modify** `data/raw/`, `seeds/classified_all_tasks.csv`, `seeds/cps_a19_panel.csv`, `seeds/dws_displacement_panel.csv`, `seeds/soc_crosswalks/`.
- **Existing outputs must not change.** Every file under `data/output/` that exists today must be byte-identical afterwards except the ones this plan adds. Task 9 verifies this.
- Every new pipeline output gets a `CLAUDE.md` "Outputs Reference" row in the commit that creates it.
- Tests must not hit the network. The BLS fetch is cached under `data/raw/bls_api/`; tests use fixtures or monkeypatch.
- Commit with `PATH="$PWD/.venv/bin:$PATH"`. Stage explicit paths — **never `git add -A`**, this repo has ~20 untracked files in its root.
- Commit message trailers, exactly:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01XmW2c1TmZUtMwrc9wXueCi
  ```

---

## Verified facts this plan depends on

Checked against BLS on 2026-09-13. Do not re-derive; do not assume differently.

| Check | Result |
|---|---|
| `LNU02034561`, 1983–1999, via `api.bls.gov` POST | `REQUEST_SUCCEEDED`, **204 monthly observations, 1983–1999** |
| `LNU02032201`, 1983–1990 | `REQUEST_SUCCEEDED`, 96 observations |
| `LNU02032201`, 2020–2026 | `REQUEST_SUCCEEDED`, 80 observations |
| `BLS_API_KEY` in `.env` | present (registered: 20-year cap per request) |
| `fetch_annual_means` chunking | already chunks to the cap and caches under `data/raw/bls_api/` |
| `DWS_TO_SOC_MAJOR` keys vs constio leaf-group names | **byte-identical for all ten**, covering all 22 SOC majors exactly once |

**The same series ID spans 1983→2026.** BLS back-filled these series using conversion factors derived from dual-coded 2000–02 microdata, so there is no splice to perform — but there is a documented comparability break at January 2003 and a second at January 2000, and pre-1998 data is uncomposited so it will not sum to published totals. Task 3 measures and discloses this; it is not a defect to fix.

**The ten leaf occupation-group series (not seasonally adjusted, both sexes):**

| `cps_group` | Series ID |
|---|---|
| management, business, and financial operations occupations | `LNU02032202` |
| professional and related occupations | `LNU02032203` |
| service occupations | `LNU02032204` |
| sales and related occupations | `LNU02032206` |
| office and administrative support occupations | `LNU02032207` |
| farming, fishing, and forestry occupations | `LNU02032209` |
| construction and extraction occupations | `LNU02032210` |
| installation, maintenance, and repair occupations | `LNU02032211` |
| production occupations | `LNU02032213` |
| transportation and material moving occupations | `LNU02032214` |

These are leaves. Do **not** also fetch the aggregate rows (`LNU02032201` management/professional/related, `LNU02032205` sales and office, `LNU02032208` natural resources/construction/maintenance, `LNU02032212` production/transportation/material moving) — summing leaves and aggregates together double-counts.

---

## Why this is not the plan the spec described

The spec's D1 chose IPUMS CPS microdata, with the BLS published series as a *validation target only*, because it assumed the published reconstruction offered "8 major occupation groups" — too coarse to test at. Two things turned out differently on inspection:

- The published series resolve to **ten leaf groups**, not eight, and they map onto all 22 SOC majors through a lookup the repo already has and already tests.
- They need **no IPUMS account**, which this environment does not have (`ipumspy` is not installed and no key is set), so the microdata route is blocked on a credential the published route does not need.

So this plan delivers the 1983 floor at ten groups now, and the IPUMS work becomes a **successor plan** whose only remaining job is raising sector granularity from ten groups to 22. That is a real gain — n=10 needs r≈0.63 for p<0.05 while n=22 needs r≈0.42, and the composition model's observed sector r values sit between — but it is an upgrade to a working test rather than a prerequisite for having one.

### Three consequences of that deviation, also recorded

Each of these follows from choosing the published series over IPUMS microdata. None
was a silent drop, but none was written down until after execution:

- **The spec's D6 — extending `D` and the DWS panel back to 1984 — is untouched by
  this plan.** The spec ranks it *above* the employment extension in scientific
  value, because it feeds the project's only structurally non-circular validation.
  It belongs to the successor plan, not to this one.
- **The spec's chart section asks for OEWS and CPS as separate lines in one axes,
  with the 1999–2025 overlap shaded.** This plan produced a separate chart file
  instead. That satisfies D3 (never splice) more conservatively — two instruments
  that disagree by construction are harder to misread when they are not sharing an
  axis — but it is not what the spec described.
- **The spec's architecture section asks for `sector_growth_series` to gain an
  instrument argument, with `validate_bls.py` and `synthesize_dynamic.py` looping
  over instruments.** That design presumed the CPS side would be 22 `soc_major`
  keys. It is ten named groups, so the looping design does not apply and the CPS
  path lives in `composition_era_validation.py` alone.

**This is a deviation from the spec and is recorded as such.** The spec's D2 (`OCC1990` spine), the allocation matrix, and validation gates 1–3 all belong to the successor plan. D3 (never splice CPS onto OEWS) and the anachronism rule bind this plan unchanged.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `cps_historical_panel.py` | Create | Fetch the ten series, annualise, merge into the seed, build the trend table |
| `seeds/cps_occupation_panel.csv` | Create | Committed annual panel: `year, cps_group, employed_thousands` |
| `data/output/cps_group_trends.csv` | Create (output) | Wide trend table keyed by `cps_group`, same growth-column layout as `bls_sector_trends.csv` |
| `composition_era_validation.py` | Modify | Third level `cps_group`: correlation function, period builder, wire into `run()` |
| `tests/test_cps_historical_panel.py` | Create | Panel parsing, annualisation, seed merge, break measurement |
| `tests/test_composition_era_validation.py` | Modify | `cps_group_correlation` tests |
| `docs/charts/composition_model_signal_over_time_cps.md` | Create | Chart doc |
| `CLAUDE.md`, `docs/framework.md` | Modify | Outputs Reference rows; instrument-divergence note |

---

### Task 1: Fetch the ten series and build the committed seed panel

**Files:**
- Create: `cps_historical_panel.py`
- Create: `seeds/cps_occupation_panel.csv`
- Test: `tests/test_cps_historical_panel.py`

**Interfaces:**
- Consumes: `historical_displacement.fetch_annual_means(series_id: str, start_year: int, end_year: int) -> pd.Series | None`
- Produces:
  - `CPS_GROUP_SERIES: dict[str, str]` — group name → series ID
  - `fetch_cps_group_employment(start_year: int = 1983, end_year: int = 2026) -> pd.DataFrame` — long form `year, cps_group, employed_thousands`
  - `merge_into_seed(fetched_df: pd.DataFrame, seed_path: str = SEED_PATH) -> pd.DataFrame`
  - `SEED_PATH = "seeds/cps_occupation_panel.csv"`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cps_historical_panel.py`:

```python
"""Tests for cps_historical_panel.py — the ten-group CPS employment panel, 1983 onward."""

import pandas as pd
import pytest

import cps_historical_panel
from cps_historical_panel import CPS_GROUP_SERIES, fetch_cps_group_employment, merge_into_seed


class TestSeriesMapping:
    def test_exactly_ten_leaf_groups(self):
        assert len(CPS_GROUP_SERIES) == 10

    def test_group_names_match_the_dws_soc_mapping(self):
        from dws_panel import DWS_TO_SOC_MAJOR

        assert set(CPS_GROUP_SERIES) == set(DWS_TO_SOC_MAJOR)

    def test_no_aggregate_series_included(self):
        """Aggregates would double-count against their own leaves."""
        aggregates = {"LNU02032201", "LNU02032205", "LNU02032208", "LNU02032212"}
        assert not (set(CPS_GROUP_SERIES.values()) & aggregates)


class TestFetch:
    def test_annual_means_are_assembled_into_long_form(self, monkeypatch):
        def fake_fetch(series_id, start_year, end_year):
            return pd.Series({1983: 100.0, 1984: 110.0}, name=series_id)

        monkeypatch.setattr(cps_historical_panel, "fetch_annual_means", fake_fetch)
        panel_df = fetch_cps_group_employment(1983, 1984)
        assert set(panel_df.columns) == {"year", "cps_group", "employed_thousands"}
        assert len(panel_df) == 20  # 10 groups x 2 years
        assert panel_df["employed_thousands"].iloc[0] == pytest.approx(100.0)

    def test_a_failed_series_is_skipped_not_fatal(self, monkeypatch):
        def fake_fetch(series_id, start_year, end_year):
            if series_id == CPS_GROUP_SERIES["service occupations"]:
                return None
            return pd.Series({1983: 100.0}, name=series_id)

        monkeypatch.setattr(cps_historical_panel, "fetch_annual_means", fake_fetch)
        with pytest.warns(UserWarning):
            panel_df = fetch_cps_group_employment(1983, 1983)
        assert "service occupations" not in set(panel_df["cps_group"])
        assert len(panel_df) == 9


class TestSeedMerge:
    def test_fetched_rows_override_seed_rows_for_the_same_year_and_group(self, tmp_path):
        seed_path = tmp_path / "seed.csv"
        pd.DataFrame([{"year": 1983, "cps_group": "service occupations", "employed_thousands": 1.0}]).to_csv(seed_path, index=False)
        fetched_df = pd.DataFrame([{"year": 1983, "cps_group": "service occupations", "employed_thousands": 2.0}])
        merged_df = merge_into_seed(fetched_df, str(seed_path))
        assert len(merged_df) == 1
        assert merged_df["employed_thousands"].iloc[0] == pytest.approx(2.0)

    def test_seed_rows_absent_from_the_fetch_survive(self, tmp_path):
        seed_path = tmp_path / "seed.csv"
        pd.DataFrame([{"year": 1975, "cps_group": "service occupations", "employed_thousands": 5.0}]).to_csv(seed_path, index=False)
        fetched_df = pd.DataFrame([{"year": 1983, "cps_group": "service occupations", "employed_thousands": 2.0}])
        merged_df = merge_into_seed(fetched_df, str(seed_path))
        assert set(merged_df["year"]) == {1975, 1983}

    def test_missing_seed_returns_the_fetch_unchanged(self, tmp_path):
        fetched_df = pd.DataFrame([{"year": 1983, "cps_group": "service occupations", "employed_thousands": 2.0}])
        merged_df = merge_into_seed(fetched_df, str(tmp_path / "absent.csv"))
        assert len(merged_df) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_cps_historical_panel.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cps_historical_panel'`.

- [ ] **Step 3: Write the module**

Create `cps_historical_panel.py`:

```python
"""
cps_historical_panel.py
───────────────────────
Build a CPS employment panel by occupation group covering 1983 onward — a second,
independent employment instrument alongside OEWS.

BLS reconstructed CPS employment for 1983-99 onto the 2002 Census / SOC 2000
classification and publishes it under the same series IDs as current data, so one
series ID spans 1983 to the present. Ten of those series are the leaf occupation
groups; their names match the DWS group names the project already maps to SOC
major codes, so no new crosswalk is needed.

Inputs:
  • https://api.bls.gov/publicAPI/v2/timeseries/data/ (ten LNU series, cached)
  • seeds/cps_occupation_panel.csv (committed history)

Outputs:
  • data/output/cps_occupation_panel.csv — merged annual panel
  • data/output/cps_group_trends.csv     — wide trend table with growth columns

Two comparability breaks live inside these series and are disclosed rather than
patched: January 2003 (the classification change the reconstruction bridges) and
January 2000 (where the reconstructed segment meets published data). Data before
1998 is uncomposited and will not sum to published totals.
"""

import os
import warnings

import pandas as pd

from analyze_bls import attach_growth_columns
from historical_displacement import fetch_annual_means

SEED_PATH = "seeds/cps_occupation_panel.csv"
PANEL_OUTPUT_PATH = "data/output/cps_occupation_panel.csv"
TRENDS_OUTPUT_PATH = "data/output/cps_group_trends.csv"

# Leaf occupation groups only. The aggregate rows (LNU02032201, LNU02032205,
# LNU02032208, LNU02032212) are deliberately excluded: summing them alongside
# their own leaves would double-count.
CPS_GROUP_SERIES: dict[str, str] = {
    "management, business, and financial operations occupations": "LNU02032202",
    "professional and related occupations": "LNU02032203",
    "service occupations": "LNU02032204",
    "sales and related occupations": "LNU02032206",
    "office and administrative support occupations": "LNU02032207",
    "farming, fishing, and forestry occupations": "LNU02032209",
    "construction and extraction occupations": "LNU02032210",
    "installation, maintenance, and repair occupations": "LNU02032211",
    "production occupations": "LNU02032213",
    "transportation and material moving occupations": "LNU02032214",
}

PANEL_COLUMNS = ["year", "cps_group", "employed_thousands"]


def fetch_cps_group_employment(start_year: int = 1983, end_year: int = 2026) -> pd.DataFrame:
    """Annual mean employment per occupation group, in long form.

    The published series are monthly and not seasonally adjusted;
    fetch_annual_means collapses them to annual means, which is what BLS's own
    annual averages are. A series that cannot be fetched is warned about and
    skipped rather than failing the whole panel.
    """
    panel_rows = []
    for cps_group, series_id in CPS_GROUP_SERIES.items():
        annual_means = fetch_annual_means(series_id, start_year, end_year)
        if annual_means is None:
            warnings.warn(f"CPS series {series_id} ({cps_group}) unavailable; skipping", stacklevel=2)
            continue
        for year, employed_thousands in annual_means.items():
            panel_rows.append({"year": int(year), "cps_group": cps_group, "employed_thousands": float(employed_thousands)})
    return pd.DataFrame(panel_rows, columns=PANEL_COLUMNS)


def merge_into_seed(fetched_df: pd.DataFrame, seed_path: str = SEED_PATH) -> pd.DataFrame:
    """Merge a fetch into the committed panel, the fetch winning on collisions.

    Follows the seeds/cps_a19_panel.csv convention: history accumulates in the
    committed file, and a run that cannot reach BLS still renders from the seed.
    """
    if not os.path.exists(seed_path):
        return fetched_df.sort_values(["year", "cps_group"]).reset_index(drop=True)
    seed_df = pd.read_csv(seed_path)
    combined_df = pd.concat([seed_df, fetched_df], ignore_index=True)
    combined_df = combined_df.drop_duplicates(subset=["year", "cps_group"], keep="last")
    return combined_df.sort_values(["year", "cps_group"]).reset_index(drop=True)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_cps_historical_panel.py -v`
Expected: PASS, 8 tests.

- [ ] **Step 5: Do the real fetch and write the seed**

```bash
cd /workspaces/ai-exposure
.venv/bin/python -c "
from cps_historical_panel import fetch_cps_group_employment, merge_into_seed, SEED_PATH
fetched_df = fetch_cps_group_employment()
merged_df = merge_into_seed(fetched_df)
merged_df.to_csv(SEED_PATH, index=False)
print('rows:', len(merged_df), '| years:', merged_df.year.min(), '-', merged_df.year.max(), '| groups:', merged_df.cps_group.nunique())
"
```

Expected: 10 groups, years 1983–2026, roughly 440 rows. A group count below 10 means a series failed — investigate before continuing.

- [ ] **Step 6: Sanity-check the levels against a known total**

```bash
.venv/bin/python -c "
import pandas as pd
panel_df = pd.read_csv('seeds/cps_occupation_panel.csv')
for year in (1983, 1999, 2000, 2010, 2025):
    total = panel_df[panel_df.year == year].employed_thousands.sum()
    print(year, f'{total/1000:,.1f}M')
"
```

Expected: roughly 100M in 1983 rising to roughly 160M in 2025. CPS counts the self-employed and agriculture, so these are legitimately **higher** than the OEWS sector sums (127M–130M in that era) — that difference is the instrument divergence this plan exists to expose, not an error.

- [ ] **Step 7: Lint and commit**

```bash
.venv/bin/ruff check cps_historical_panel.py tests/test_cps_historical_panel.py
.venv/bin/ruff format cps_historical_panel.py tests/test_cps_historical_panel.py
git add cps_historical_panel.py tests/test_cps_historical_panel.py seeds/cps_occupation_panel.csv
PATH="$PWD/.venv/bin:$PATH" git commit -m "$(cat <<'EOF'
Add the CPS occupation-group employment panel, 1983 onward

BLS reconstructed CPS employment for 1983-99 onto the 2002 Census/SOC
classification and publishes it under the same series IDs as current data,
so ten leaf occupation-group series span 1983-2026 with no splice. Their
names match DWS_TO_SOC_MAJOR exactly, so no new crosswalk is needed.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XmW2c1TmZUtMwrc9wXueCi
EOF
)"
```

---

### Task 2: Build the wide trend table

**Files:**
- Modify: `cps_historical_panel.py`
- Test: `tests/test_cps_historical_panel.py`

**Interfaces:**
- Consumes: `analyze_bls.attach_growth_columns(trend_df: pd.DataFrame, available_years: list[str]) -> pd.DataFrame`
- Produces: `build_cps_group_trends(panel_df: pd.DataFrame) -> pd.DataFrame` — one row per `cps_group`, columns `TOT_EMP_{yyyy}` plus the growth columns `attach_growth_columns` adds.

Reusing `attach_growth_columns` is what makes the CPS table readable by the existing period machinery: it produces exactly the same `hist_emp_growth_{yyyy}_{yyyy}` / `emp_growth_{yyyy}_{yyyy}` / `emp_growth_composite` names as `bls_sector_trends.csv`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cps_historical_panel.py`:

```python
class TestTrendTable:
    @staticmethod
    def _panel(years, groups=("service occupations", "production occupations")):
        return pd.DataFrame(
            [
                {"year": year, "cps_group": group, "employed_thousands": 100.0 + index * 10}
                for index, year in enumerate(years)
                for group in groups
            ]
        )

    def test_one_row_per_group(self):
        from cps_historical_panel import build_cps_group_trends

        trends_df = build_cps_group_trends(self._panel([2021, 2022, 2023]))
        assert len(trends_df) == 2
        assert "cps_group" in trends_df.columns

    def test_employment_columns_are_four_digit_year_keyed(self):
        from cps_historical_panel import build_cps_group_trends

        trends_df = build_cps_group_trends(self._panel([2021, 2022, 2023]))
        assert "TOT_EMP_1983" not in trends_df.columns
        assert "TOT_EMP_2022" in trends_df.columns

    def test_growth_columns_use_the_shared_naming(self):
        from cps_historical_panel import build_cps_group_trends

        trends_df = build_cps_group_trends(self._panel([2021, 2022, 2023]))
        assert "hist_emp_growth_2021_2022" in trends_df.columns
        assert "emp_growth_2022_2023" in trends_df.columns

    def test_growth_values_are_correct(self):
        from cps_historical_panel import build_cps_group_trends

        panel_df = pd.DataFrame(
            [
                {"year": 2022, "cps_group": "service occupations", "employed_thousands": 100.0},
                {"year": 2023, "cps_group": "service occupations", "employed_thousands": 110.0},
            ]
        )
        trends_df = build_cps_group_trends(panel_df)
        assert trends_df["emp_growth_2022_2023"].iloc[0] == pytest.approx(0.10)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_cps_historical_panel.py::TestTrendTable -v`
Expected: FAIL with `ImportError: cannot import name 'build_cps_group_trends'`.

- [ ] **Step 3: Implement**

Append to `cps_historical_panel.py`:

```python
def build_cps_group_trends(panel_df: pd.DataFrame) -> pd.DataFrame:
    """Pivot the long panel to one row per group with TOT_EMP_{yyyy} and growth columns.

    attach_growth_columns is reused rather than reimplemented so the CPS table
    carries byte-identical growth-column names to bls_sector_trends.csv, which is
    what lets the existing period-discovery machinery read it unchanged.
    """
    wide_df = panel_df.pivot(index="cps_group", columns="year", values="employed_thousands")
    wide_df.columns = [f"TOT_EMP_{int(year)}" for year in wide_df.columns]
    wide_df = wide_df.reset_index()

    available_years = sorted(str(int(year)) for year in panel_df["year"].unique())
    return attach_growth_columns(wide_df, available_years)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_cps_historical_panel.py -v`
Expected: PASS, 12 tests.

- [ ] **Step 5: Write the real trend table and inspect it**

```bash
.venv/bin/python -c "
import pandas as pd
from cps_historical_panel import build_cps_group_trends, TRENDS_OUTPUT_PATH, PANEL_OUTPUT_PATH
panel_df = pd.read_csv('seeds/cps_occupation_panel.csv')
panel_df.to_csv(PANEL_OUTPUT_PATH, index=False)
trends_df = build_cps_group_trends(panel_df)
trends_df.to_csv(TRENDS_OUTPUT_PATH, index=False)
periods = [c for c in trends_df.columns if 'emp_growth_' in c and 'composite' not in c and 'pre_ai' not in c]
print('rows:', len(trends_df), '| periods:', len(periods))
print('first:', sorted(periods)[0], '| last:', sorted(periods)[-1])
"
```

Expected: 10 rows and **43 periods**, first `hist_emp_growth_1983_1984`, last `emp_growth_2025_2026`.

- [ ] **Step 6: Lint and commit**

```bash
.venv/bin/ruff check cps_historical_panel.py tests/test_cps_historical_panel.py
.venv/bin/ruff format cps_historical_panel.py tests/test_cps_historical_panel.py
git add cps_historical_panel.py tests/test_cps_historical_panel.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "$(cat <<'EOF'
Build the CPS group trend table on the shared growth-column layout

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XmW2c1TmZUtMwrc9wXueCi
EOF
)"
```

---

### Task 3: Measure the two comparability breaks

The series carry a break at January 2000 (reconstructed segment meeting published data) and another the reconstruction bridges at January 2003. A reader must be able to see how large they are before trusting a period that crosses them. This task measures rather than patches.

**Files:**
- Modify: `cps_historical_panel.py`
- Test: `tests/test_cps_historical_panel.py`

**Interfaces:**
- Produces: `measure_comparability_breaks(trends_df: pd.DataFrame, break_periods: tuple[str, ...] = ("1999_2000", "2002_2003")) -> pd.DataFrame` — columns `period, cps_group, emp_growth, is_break_period`.

- [ ] **Step 1: Write the failing test**

```python
class TestComparabilityBreaks:
    def test_break_periods_are_flagged(self):
        from cps_historical_panel import measure_comparability_breaks

        trends_df = pd.DataFrame(
            [
                {
                    "cps_group": "service occupations",
                    "hist_emp_growth_1999_2000": 0.20,
                    "hist_emp_growth_2001_2002": 0.01,
                }
            ]
        )
        break_df = measure_comparability_breaks(trends_df, ("1999_2000",))
        flagged = break_df[break_df["is_break_period"]]
        assert set(flagged["period"]) == {"1999_2000"}
        assert flagged["emp_growth"].iloc[0] == pytest.approx(0.20)

    def test_non_break_periods_are_retained_for_comparison(self):
        from cps_historical_panel import measure_comparability_breaks

        trends_df = pd.DataFrame(
            [
                {
                    "cps_group": "service occupations",
                    "hist_emp_growth_1999_2000": 0.20,
                    "hist_emp_growth_2001_2002": 0.01,
                }
            ]
        )
        break_df = measure_comparability_breaks(trends_df, ("1999_2000",))
        assert set(break_df["period"]) == {"1999_2000", "2001_2002"}
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_cps_historical_panel.py::TestComparabilityBreaks -v`
Expected: FAIL with `ImportError: cannot import name 'measure_comparability_breaks'`.

- [ ] **Step 3: Implement**

```python
COMPARABILITY_BREAK_PERIODS = ("1999_2000", "2002_2003")


def measure_comparability_breaks(
    trends_df: pd.DataFrame,
    break_periods: tuple[str, ...] = COMPARABILITY_BREAK_PERIODS,
) -> pd.DataFrame:
    """Per-group growth in every period, with the known comparability breaks flagged.

    The point is comparison: a break period whose growth sits inside the ordinary
    spread is a break the data survived, and one far outside it is a break that
    contaminates any span crossing it. Neither is patched here.
    """
    growth_rows = []
    for column in trends_df.columns:
        if "emp_growth_" not in column or "composite" in column or "pre_ai" in column:
            continue
        period = column.replace("hist_emp_growth_", "").replace("emp_growth_", "")
        for _, group_row in trends_df.iterrows():
            growth_rows.append(
                {
                    "period": period,
                    "cps_group": group_row["cps_group"],
                    "emp_growth": group_row[column],
                    "is_break_period": period in break_periods,
                }
            )
    return pd.DataFrame(growth_rows)
```

- [ ] **Step 4: Run to verify passing**

Run: `.venv/bin/python -m pytest tests/test_cps_historical_panel.py -v`
Expected: PASS, 14 tests.

- [ ] **Step 5: Measure the real breaks and record the numbers**

```bash
.venv/bin/python -c "
import pandas as pd
from cps_historical_panel import measure_comparability_breaks, TRENDS_OUTPUT_PATH
break_df = measure_comparability_breaks(pd.read_csv(TRENDS_OUTPUT_PATH))
ordinary = break_df[~break_df.is_break_period].emp_growth.abs()
print('ordinary |growth|: median %.3f, 95th pct %.3f' % (ordinary.median(), ordinary.quantile(0.95)))
for period, rows in break_df[break_df.is_break_period].groupby('period'):
    print(period, '| median |growth| %.3f | max %.3f' % (rows.emp_growth.abs().median(), rows.emp_growth.abs().max()))
"
```

Record the output in the commit message. If a break period's median absolute growth exceeds the 95th percentile of ordinary periods, say so explicitly — that is the finding, and Task 7's docs must carry it.

- [ ] **Step 6: Lint and commit**

```bash
.venv/bin/ruff check cps_historical_panel.py tests/test_cps_historical_panel.py
.venv/bin/ruff format cps_historical_panel.py tests/test_cps_historical_panel.py
git add cps_historical_panel.py tests/test_cps_historical_panel.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "$(cat <<'EOF'
Measure the CPS comparability breaks rather than patching them

Replace this line with the Step 5 output: the ordinary median and 95th
percentile absolute growth, and each break period's median and max.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XmW2c1TmZUtMwrc9wXueCi
EOF
)"
```

---

### Task 4: Correlate model scores against the CPS instrument

**Files:**
- Modify: `composition_era_validation.py`
- Test: `tests/test_composition_era_validation.py`

**Interfaces:**
- Consumes: `composition_displacement_validation.soc_major_to_dws_group() -> dict[str, str]`; the trend table from Task 2.
- Produces:
  - `CPS_GROUP_TRENDS_PATH = "data/output/cps_group_trends.csv"`
  - `MINIMUM_CPS_GROUPS = 8`
  - `cps_group_correlation(scored_df, score_col, growth_col, employment_col, cps_trends_df) -> tuple[float, float, int] | None`
  - `build_cps_period_correlations(scored_df, employment_col, cps_trends_df, score_columns) -> pd.DataFrame` — same frame shape as `build_period_correlations` (`period, score, fit_r, fit_p, n_units, era, is_covid`)

The frame shape matters: `summarise_eras`, `decompose_fit_strength`, `correlate_with_displacement_rate` and `plot_signal_over_time` already consume it for the sector and occupation levels and must consume this one unchanged.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_composition_era_validation.py`:

```python
class TestCpsGroupCorrelation:
    @staticmethod
    def _scored_frame():
        """Two occupations per DWS group, scores rising with the group's index."""
        from composition_displacement_validation import soc_major_to_dws_group

        lookup = soc_major_to_dws_group()
        rows = []
        for index, (soc_major, group) in enumerate(sorted(lookup.items())):
            for suffix in ("1001", "1002"):
                rows.append(
                    {
                        "OCC_CODE": f"{soc_major}-{suffix}",
                        COMPOSITION_SCORE_COLUMN: index / 100.0,
                        "TOT_EMP_2025": 1000.0,
                    }
                )
        return pd.DataFrame(rows)

    @staticmethod
    def _cps_trends(growth_col, slope):
        from composition_displacement_validation import soc_major_to_dws_group

        groups = sorted(set(soc_major_to_dws_group().values()))
        return pd.DataFrame([{"cps_group": group, growth_col: slope * index} for index, group in enumerate(groups)])

    def test_positive_relationship_is_recovered(self):
        result = cps_group_correlation(
            self._scored_frame(),
            COMPOSITION_SCORE_COLUMN,
            "emp_growth_2022_2023",
            "TOT_EMP_2025",
            self._cps_trends("emp_growth_2022_2023", 0.01),
        )
        assert result is not None
        correlation, _, n_groups = result
        assert correlation > 0.9
        assert n_groups == 10

    def test_missing_growth_column_returns_none(self):
        result = cps_group_correlation(
            self._scored_frame(),
            COMPOSITION_SCORE_COLUMN,
            "emp_growth_1983_1984",
            "TOT_EMP_2025",
            self._cps_trends("emp_growth_2022_2023", 0.01),
        )
        assert result is None

    def test_reported_n_counts_groups_not_occupations(self):
        result = cps_group_correlation(
            self._scored_frame(),
            COMPOSITION_SCORE_COLUMN,
            "emp_growth_2022_2023",
            "TOT_EMP_2025",
            self._cps_trends("emp_growth_2022_2023", 0.01),
        )
        assert result[2] == 10  # not 44 occupations
```

Add `cps_group_correlation` to the module's import list in that test file.

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_composition_era_validation.py::TestCpsGroupCorrelation -v`
Expected: FAIL with `ImportError: cannot import name 'cps_group_correlation'`.

- [ ] **Step 3: Implement**

Add to `composition_era_validation.py`, beside `occupation_correlation`:

```python
CPS_GROUP_TRENDS_PATH = "data/output/cps_group_trends.csv"
# Ten groups total; require most of them present before a correlation means anything.
MINIMUM_CPS_GROUPS = 8


def cps_group_correlation(
    scored_df: pd.DataFrame,
    score_col: str,
    growth_col: str,
    employment_col: str,
    cps_trends_df: pd.DataFrame,
) -> tuple[float, float, int] | None:
    """Pearson r between a model score and CPS growth across the ten occupation groups.

    Model scores are aggregated to the CPS groups employment-weighted, using the
    same SOC-major lookup the DWS displacement validation uses, so the taxonomy is
    shared rather than re-derived. Returns None when fewer than MINIMUM_CPS_GROUPS
    groups carry both a score and a growth value.
    """
    from composition_displacement_validation import soc_major_to_dws_group

    if growth_col not in cps_trends_df.columns:
        return None

    group_lookup = soc_major_to_dws_group()
    aggregation_df = scored_df.dropna(subset=[score_col, employment_col]).copy()
    aggregation_df["cps_group"] = aggregation_df["OCC_CODE"].astype(str).str[:2].map(group_lookup)
    aggregation_df = aggregation_df.dropna(subset=["cps_group"])
    if aggregation_df.empty:
        return None

    weighted_df = aggregation_df.assign(weighted_score=aggregation_df[score_col] * aggregation_df[employment_col])
    group_scores_df = (
        weighted_df.groupby("cps_group")
        .agg(weighted_score=("weighted_score", "sum"), group_employment=(employment_col, "sum"))
        .reset_index()
    )
    group_scores_df["group_score"] = group_scores_df["weighted_score"] / group_scores_df["group_employment"]

    paired_df = group_scores_df.merge(cps_trends_df[["cps_group", growth_col]], on="cps_group", how="inner")
    paired_df = paired_df[["group_score", growth_col]].dropna()
    if len(paired_df) < MINIMUM_CPS_GROUPS:
        return None
    if paired_df["group_score"].nunique() < 2 or paired_df[growth_col].nunique() < 2:
        return None

    correlation, p_value = stats.pearsonr(paired_df["group_score"], paired_df[growth_col])
    return correlation, p_value, len(paired_df)


def build_cps_period_correlations(
    scored_df: pd.DataFrame,
    employment_col: str,
    cps_trends_df: pd.DataFrame,
    score_columns: list[str],
) -> pd.DataFrame:
    """One row per (period, score) on the CPS instrument, in the shared frame shape."""
    correlation_rows = []
    for growth_col in discover_period_columns(cps_trends_df):
        for score_col in score_columns:
            result = cps_group_correlation(scored_df, score_col, growth_col, employment_col, cps_trends_df)
            if result is None:
                continue
            correlation, p_value, n_groups = result
            correlation_rows.append(
                {
                    "period": period_key(growth_col),
                    "score": score_col,
                    "fit_r": correlation,
                    "fit_p": p_value,
                    "n_units": n_groups,
                    "era": "ai" if is_ai_era(growth_col) else "pre_ai",
                    "is_covid": period_key(growth_col) in COVID_PERIODS,
                }
            )
    return pd.DataFrame(correlation_rows)
```

- [ ] **Step 4: Run to verify passing**

Run: `.venv/bin/python -m pytest tests/test_composition_era_validation.py -v`
Expected: PASS.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/ruff check composition_era_validation.py tests/test_composition_era_validation.py
.venv/bin/ruff format composition_era_validation.py tests/test_composition_era_validation.py
git add composition_era_validation.py tests/test_composition_era_validation.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "$(cat <<'EOF'
Correlate model scores against the CPS instrument

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XmW2c1TmZUtMwrc9wXueCi
EOF
)"
```

---

### Task 5: Run the CPS level through the era and cycle machinery

**Files:**
- Modify: `composition_era_validation.py`
- Test: `tests/test_composition_era_validation.py`

**Interfaces:**
- Consumes: `_summarise_one_level(period_correlation_df, output_dir, level, era_output_path, cycle_output_path) -> pd.DataFrame`
- Produces: `data/output/composition_model_era_comparison_cps.csv`, `data/output/composition_cycle_decomposition_cps.csv`, `data/output/visualizations/composition_model_signal_over_time_cps.png`

- [ ] **Step 1: Add the output paths**

```python
CPS_OUTPUT_PATH = "data/output/composition_model_era_comparison_cps.csv"
CPS_CYCLE_OUTPUT_PATH = "data/output/composition_cycle_decomposition_cps.csv"
CPS_CHART_NAME = "composition_model_signal_over_time_cps.png"
```

- [ ] **Step 2: Teach the plot the third level**

In `plot_signal_over_time`, the level currently switches between `"sector"` and `"occupation"`. Extend the chart-name and label selection to handle `"cps_group"`:

```python
    is_occupation_level = level == "occupation"
    is_cps_level = level == "cps_group"
    unit_counts = period_correlation_df["n_units"].dropna()
    if is_cps_level:
        unit_label = "n=10 CPS occupation groups"
    elif is_occupation_level and not unit_counts.empty:
        unit_label = f"n={int(unit_counts.min())}-{int(unit_counts.max())} harmonized units"
    else:
        unit_label = "n=22 sectors"
```

and the chart-name selection:

```python
    chart_name = {"occupation": OCCUPATION_CHART_NAME, "cps_group": CPS_CHART_NAME}.get(level, CHART_NAME)
```

and the axis label, replacing the two-way conditional:

```python
    level_word = {"occupation": "Occupation", "cps_group": "CPS group"}.get(level, "Sector")
    axis.set_ylabel(f"{level_word}-level Pearson r vs. employment growth")
```

Apply the same `level_word` in `set_title`.

- [ ] **Step 3: Wire the third pass into `run()`**

After the occupation-level block:

```python
    if os.path.exists(CPS_GROUP_TRENDS_PATH):
        cps_trends_df = pd.read_csv(CPS_GROUP_TRENDS_PATH)
        cps_correlation_df = build_cps_period_correlations(scored_df, employment_col, cps_trends_df, score_columns)
        if cps_correlation_df.empty:
            print("  ⚠ No CPS-level period correlations could be computed.")
        else:
            _summarise_one_level(cps_correlation_df, output_dir, "cps_group", CPS_OUTPUT_PATH, CPS_CYCLE_OUTPUT_PATH)
    else:
        warnings.warn(f"{CPS_GROUP_TRENDS_PATH} absent; CPS level skipped", stacklevel=2)
```

- [ ] **Step 4: Write the failing test for the level plumbing**

```python
class TestCpsLevelPlumbing:
    def test_cps_chart_name_is_selected_for_the_cps_level(self):
        from composition_era_validation import CPS_CHART_NAME, CHART_NAME, OCCUPATION_CHART_NAME

        names = {"occupation": OCCUPATION_CHART_NAME, "cps_group": CPS_CHART_NAME}
        assert names.get("cps_group") == CPS_CHART_NAME
        assert names.get("sector", CHART_NAME) == CHART_NAME

    def test_cps_correlation_frame_has_the_shared_shape(self):
        from composition_era_validation import build_cps_period_correlations

        scored_df = TestCpsGroupCorrelation._scored_frame()
        cps_trends_df = TestCpsGroupCorrelation._cps_trends("emp_growth_2022_2023", 0.01)
        frame = build_cps_period_correlations(scored_df, "TOT_EMP_2025", cps_trends_df, [COMPOSITION_SCORE_COLUMN])
        assert set(frame.columns) == {"period", "score", "fit_r", "fit_p", "n_units", "era", "is_covid"}
```

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all PASS.

- [ ] **Step 6: Run the stage and report the numbers**

```bash
MPLCONFIGDIR=/tmp/claude-1000/mpl .venv/bin/python main.py composition > /tmp/claude-1000/cps.log 2>&1; echo "exit: $?"
sed -n '/cps_group level/,$p' /tmp/claude-1000/cps.log | head -45
```

Report the era comparison and cycle decomposition for the CPS level. **Report them plainly.** The project's asymmetric reading rule applies: a positive result is strong because the 2025-derived labels are anachronistic and work against it; a null is uninformative rather than disconfirming. Do not spin either.

- [ ] **Step 7: Lint and commit**

```bash
.venv/bin/ruff check composition_era_validation.py tests/test_composition_era_validation.py
.venv/bin/ruff format composition_era_validation.py tests/test_composition_era_validation.py
git add composition_era_validation.py tests/test_composition_era_validation.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "$(cat <<'EOF'
Run the era and cycle tests on the CPS instrument, 1983-2026

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XmW2c1TmZUtMwrc9wXueCi
EOF
)"
```

---

### Task 6: Report CPS-vs-OEWS agreement over the overlap, without reconciling it

Spec D3: the two instruments run in parallel and are never spliced. The overlap is where a reader learns how much to trust the CPS-only stretch.

**Files:**
- Modify: `cps_historical_panel.py`
- Test: `tests/test_cps_historical_panel.py`

**Interfaces:**
- Produces: `compare_with_oews(cps_trends_df, oews_sector_trends_df, soc_major_to_group: dict[str, str]) -> pd.DataFrame` — columns `period, cps_group, cps_growth, oews_growth, difference`.

- [ ] **Step 1: Write the failing test**

```python
class TestInstrumentAgreement:
    def test_matching_periods_are_paired_by_group(self):
        from cps_historical_panel import compare_with_oews

        cps_trends_df = pd.DataFrame([{"cps_group": "production occupations", "emp_growth_2022_2023": 0.05}])
        oews_trends_df = pd.DataFrame([{"soc_major": "51", "emp_growth_2022_2023": 0.03}])
        comparison_df = compare_with_oews(cps_trends_df, oews_trends_df, {"51": "production occupations"})
        assert len(comparison_df) == 1
        assert comparison_df["difference"].iloc[0] == pytest.approx(0.02)

    def test_periods_absent_from_oews_are_dropped(self):
        from cps_historical_panel import compare_with_oews

        cps_trends_df = pd.DataFrame(
            [{"cps_group": "production occupations", "hist_emp_growth_1983_1984": 0.05, "emp_growth_2022_2023": 0.05}]
        )
        oews_trends_df = pd.DataFrame([{"soc_major": "51", "emp_growth_2022_2023": 0.03}])
        comparison_df = compare_with_oews(cps_trends_df, oews_trends_df, {"51": "production occupations"})
        assert set(comparison_df["period"]) == {"2022_2023"}
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_cps_historical_panel.py::TestInstrumentAgreement -v`
Expected: FAIL with `ImportError: cannot import name 'compare_with_oews'`.

- [ ] **Step 3: Implement**

```python
def compare_with_oews(
    cps_trends_df: pd.DataFrame,
    oews_sector_trends_df: pd.DataFrame,
    soc_major_to_group: dict[str, str],
) -> pd.DataFrame:
    """Per-period growth from both instruments, aggregated to the CPS groups.

    Reported, never reconciled. CPS counts the self-employed and agriculture and
    OEWS does not, so the two disagree by construction; the size of the
    disagreement over the 1999-2025 overlap is what bounds confidence in the
    CPS-only stretch before 1999.
    """
    oews_df = oews_sector_trends_df.copy()
    oews_df["cps_group"] = oews_df["soc_major"].astype(str).str.zfill(2).map(soc_major_to_group)
    oews_df = oews_df.dropna(subset=["cps_group"])

    comparison_rows = []
    for column in cps_trends_df.columns:
        if "emp_growth_" not in column or "composite" in column or "pre_ai" in column:
            continue
        if column not in oews_df.columns:
            continue
        period = column.replace("hist_emp_growth_", "").replace("emp_growth_", "")
        oews_group_growth = oews_df.groupby("cps_group")[column].mean()
        for _, cps_row in cps_trends_df.iterrows():
            group = cps_row["cps_group"]
            if group not in oews_group_growth.index:
                continue
            comparison_rows.append(
                {
                    "period": period,
                    "cps_group": group,
                    "cps_growth": cps_row[column],
                    "oews_growth": oews_group_growth[group],
                    "difference": cps_row[column] - oews_group_growth[group],
                }
            )
    return pd.DataFrame(comparison_rows)
```

- [ ] **Step 4: Run to verify passing**

Run: `.venv/bin/python -m pytest tests/test_cps_historical_panel.py -v`
Expected: PASS.

- [ ] **Step 5: Measure the real overlap and record it**

```bash
.venv/bin/python -c "
import pandas as pd
from cps_historical_panel import compare_with_oews, TRENDS_OUTPUT_PATH
from composition_displacement_validation import soc_major_to_dws_group
comparison_df = compare_with_oews(
    pd.read_csv(TRENDS_OUTPUT_PATH),
    pd.read_csv('data/output/bls_sector_trends.csv', dtype={'soc_major': str}),
    soc_major_to_dws_group(),
)
comparison_df.to_csv('data/output/cps_oews_agreement.csv', index=False)
print('paired observations:', len(comparison_df), '| periods:', comparison_df.period.nunique())
print('correlation of the two instruments: %.3f' % comparison_df[['cps_growth','oews_growth']].corr().iloc[0,1])
print('mean |difference|: %.4f' % comparison_df.difference.abs().mean())
"
```

Record these numbers in the commit message and in Task 7's docs. A high correlation means the CPS-only stretch inherits credibility from the overlap; a low one is a finding to state, not a bug to fix.

- [ ] **Step 6: Lint and commit**

```bash
.venv/bin/ruff check cps_historical_panel.py tests/test_cps_historical_panel.py
.venv/bin/ruff format cps_historical_panel.py tests/test_cps_historical_panel.py
git add cps_historical_panel.py tests/test_cps_historical_panel.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "$(cat <<'EOF'
Report CPS-vs-OEWS agreement over the 1999-2025 overlap

Replace this line with the Step 5 output: paired observation count, period
count, the correlation between the two instruments, and mean |difference|.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XmW2c1TmZUtMwrc9wXueCi
EOF
)"
```

---

### Task 7: Composition-stability proxy

The spec requires this and neither plan has carried it: a bound on *where* the 2025 O\*NET labels are most suspect. It does not measure task-content drift — nothing available does — but it says which sectors are most rebuilt since the start of the series, and the deep-history result is then reported with and without the least stable.

**Files:**
- Modify: `cps_historical_panel.py`
- Test: `tests/test_cps_historical_panel.py`

**Interfaces:**
- Produces:
  - `STABILITY_OUTPUT_PATH = "data/output/sector_composition_stability.csv"`
  - `sector_composition_stability(occupation_trends_df: pd.DataFrame, earliest_year: str = "1999", anchor_year: str = "2022") -> pd.DataFrame` — columns `soc_major, anchor_employment, antecedent_employment, stable_share`

- [ ] **Step 1: Write the failing test**

```python
class TestCompositionStability:
    def test_share_is_employment_weighted_not_row_counted(self):
        from cps_historical_panel import sector_composition_stability

        occupation_trends_df = pd.DataFrame(
            [
                {"OCC_CODE": "11-1011", "TOT_EMP_1999": 10.0, "TOT_EMP_2022": 900.0},
                {"OCC_CODE": "11-1021", "TOT_EMP_1999": None, "TOT_EMP_2022": 100.0},
            ]
        )
        stability_df = sector_composition_stability(occupation_trends_df)
        assert stability_df["stable_share"].iloc[0] == pytest.approx(0.9)

    def test_a_sector_with_no_antecedents_scores_zero(self):
        from cps_historical_panel import sector_composition_stability

        occupation_trends_df = pd.DataFrame([{"OCC_CODE": "15-1211", "TOT_EMP_1999": None, "TOT_EMP_2022": 500.0}])
        stability_df = sector_composition_stability(occupation_trends_df)
        assert stability_df["stable_share"].iloc[0] == pytest.approx(0.0)

    def test_one_row_per_soc_major(self):
        from cps_historical_panel import sector_composition_stability

        occupation_trends_df = pd.DataFrame(
            [
                {"OCC_CODE": "11-1011", "TOT_EMP_1999": 10.0, "TOT_EMP_2022": 100.0},
                {"OCC_CODE": "15-1211", "TOT_EMP_1999": 10.0, "TOT_EMP_2022": 100.0},
            ]
        )
        stability_df = sector_composition_stability(occupation_trends_df)
        assert set(stability_df["soc_major"]) == {"11", "15"}
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_cps_historical_panel.py::TestCompositionStability -v`
Expected: FAIL with `ImportError: cannot import name 'sector_composition_stability'`.

- [ ] **Step 3: Implement**

```python
STABILITY_OUTPUT_PATH = "data/output/sector_composition_stability.csv"


def sector_composition_stability(
    occupation_trends_df: pd.DataFrame,
    earliest_year: str = "1999",
    anchor_year: str = "2022",
) -> pd.DataFrame:
    """Share of each sector's anchor-year employment in occupations that existed at the series start.

    A bound on where the 2025 O*NET demand-type labels are most anachronistic: a
    sector largely composed of occupations OEWS did not publish in 1999 has been
    rebuilt since, so carrying today's labels back through it is the least safe.
    This is a proxy for composition churn, not a measure of task-content drift.
    """
    anchor_col, earliest_col = f"TOT_EMP_{anchor_year}", f"TOT_EMP_{earliest_year}"
    stability_df = occupation_trends_df.dropna(subset=[anchor_col]).copy()
    stability_df["soc_major"] = stability_df["OCC_CODE"].astype(str).str[:2]
    stability_df["antecedent_employment"] = stability_df[anchor_col].where(stability_df[earliest_col].notna(), 0.0)

    grouped_df = (
        stability_df.groupby("soc_major")
        .agg(anchor_employment=(anchor_col, "sum"), antecedent_employment=("antecedent_employment", "sum"))
        .reset_index()
    )
    grouped_df["stable_share"] = grouped_df["antecedent_employment"] / grouped_df["anchor_employment"]
    return grouped_df.sort_values("stable_share").reset_index(drop=True)
```

- [ ] **Step 4: Run to verify passing**

Run: `.venv/bin/python -m pytest tests/test_cps_historical_panel.py -v`
Expected: PASS.

- [ ] **Step 5: Compute the real proxy and the sensitivity**

```bash
.venv/bin/python -c "
import pandas as pd
from cps_historical_panel import sector_composition_stability, STABILITY_OUTPUT_PATH
stability_df = sector_composition_stability(pd.read_csv('data/output/bls_trends.csv'))
stability_df.to_csv(STABILITY_OUTPUT_PATH, index=False)
print(stability_df.head(6).to_string(index=False))
print('...')
print(stability_df.tail(3).to_string(index=False))
"
```

Expect Computer and Mathematical (`15`) near the bottom — the SOC 2018 revision renumbered every computer code, which `CLAUDE.md` already records. Report the three least-stable sectors.

- [ ] **Step 6: Re-run the CPS era test excluding the least-stable groups**

Map the three least-stable SOC majors to their CPS groups via `soc_major_to_dws_group()`, drop those groups from `cps_group_correlation`'s input, and re-run Task 5's stage. Report the era and cycle numbers with and without them, side by side. If dropping them changes the sign or significance of any headline, that is the finding and Task 8's docs must say so.

- [ ] **Step 7: Lint and commit**

```bash
.venv/bin/ruff check cps_historical_panel.py tests/test_cps_historical_panel.py
.venv/bin/ruff format cps_historical_panel.py tests/test_cps_historical_panel.py
git add cps_historical_panel.py tests/test_cps_historical_panel.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "$(cat <<'EOF'
Bound where the 2025 demand-type labels are most anachronistic

Replace this line with the Step 5 three least-stable sectors and the Step 6
with/without sensitivity.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XmW2c1TmZUtMwrc9wXueCi
EOF
)"
```

---

### Task 8: Documentation

**Files:**
- Create: `docs/charts/composition_model_signal_over_time_cps.md`
- Modify: `CLAUDE.md` — Outputs Reference rows for `cps_occupation_panel.csv`, `cps_group_trends.csv`, `cps_oews_agreement.csv`, `composition_model_era_comparison_cps.csv`, `composition_cycle_decomposition_cps.csv`, `composition_model_signal_over_time_cps.png`; plus a `seeds/cps_occupation_panel.csv` sentence in the Release Pipeline section following the `seeds/cps_a19_panel.csv` convention
- Modify: `docs/framework.md` — a short subsection under the Demand Composition Model recording that a second instrument now covers 1983→2026 and what it says
- Modify: `CLAUDE.md` — Outputs Reference row for `sector_composition_stability.csv` from Task 7

- [ ] **Step 1: Write the chart doc**

It must state, with the real measured numbers from Tasks 3, 5, 6 and 7:
- the span (1983→2026) and n=10 groups, and that n=10 needs r ≈ 0.63 for p < 0.05 — weaker than the n=22 sector test, and why that is the price of reaching 1983
- that CPS and OEWS are separate instruments drawn as separate series and never spliced (spec D3), with the overlap agreement number from Task 6
- the two comparability breaks and their measured size from Task 3
- the anachronism rule: 2025 O\*NET labels applied to 1983 occupations, so a positive result is strong and a null is uninformative, together with the Task 7 stability numbers and the with/without-least-stable sensitivity
- that the CPS series counts the self-employed and agriculture while OEWS does not

- [ ] **Step 2: Add the six Outputs Reference rows and the seed convention sentence**

- [ ] **Step 3: Add the framework.md subsection**

Keep it to one short subsection reporting what the CPS instrument says about the era and cycle tests, cross-linked to the chart doc. Do not restate the sector results.

- [ ] **Step 4: Verify no doc claims the project's employment history starts at 1999**

```bash
grep -rnE "1999→2025|1999-2025|back to 1999" --include="*.md" . | grep -v "^./docs/superpowers" | head -20
```

Every hit that describes the *project's* history rather than the *OEWS* series specifically needs qualifying: OEWS starts at 1999, the CPS instrument starts at 1983.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/
PATH="$PWD/.venv/bin:$PATH" git commit -m "$(cat <<'EOF'
Document the CPS historical instrument

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XmW2c1TmZUtMwrc9wXueCi
EOF
)"
```

---

### Task 9: Prove no existing output changed

**Files:** none — verification only, no commit.

- [ ] **Step 1: Snapshot before you start**

This must run on `HEAD` **before Task 1's commit**. If you are reading this after starting, check out the pre-Task-1 commit into a scratch worktree and run the pipeline there.

```bash
mkdir -p /tmp/claude-1000/cps-baseline
cp data/output/*.csv /tmp/claude-1000/cps-baseline/
```

- [ ] **Step 2: Re-run the full pipeline**

```bash
MPLCONFIGDIR=/tmp/claude-1000/mpl .venv/bin/python main.py analyze synthesize plot validate composition > /tmp/claude-1000/cps-full.log 2>&1; echo "exit: $?"
```

- [ ] **Step 3: Compare**

```bash
.venv/bin/python -c "
import glob, os, pandas as pd
for baseline_path in sorted(glob.glob('/tmp/claude-1000/cps-baseline/*.csv')):
    name = os.path.basename(baseline_path)
    current_path = f'data/output/{name}'
    if not os.path.exists(current_path):
        print(f'{name}: MISSING'); continue
    baseline_df, current_df = pd.read_csv(baseline_path), pd.read_csv(current_path)
    if baseline_df.shape != current_df.shape:
        print(f'{name}: SHAPE {baseline_df.shape} -> {current_df.shape}'); continue
    numeric = [c for c in baseline_df.columns if pd.api.types.is_numeric_dtype(baseline_df[c]) and c in current_df.columns]
    diffs = [c for c in numeric if not baseline_df[c].equals(current_df[c])]
    print(f'{name}: {\"OK\" if not diffs else \"DIFF \" + str(diffs[:4])}')
"
```

Expected: every pre-existing file reports `OK`. This plan adds outputs; it must change none. A `DIFF` means the CPS work leaked into an existing computation — report it precisely and do not rationalise it.

- [ ] **Step 4: Report**

Summarise: the CPS span and period count, the instrument-agreement number, the comparability-break sizes, what the CPS-level era and cycle tests say, and confirmation that every pre-existing output is unchanged.

---

## Out of scope for this plan

- **IPUMS CPS microdata and the 22-group panel** — the successor plan. Its only remaining job is raising granularity from ten groups to 22; it needs an IPUMS account and API key, neither of which exists in this environment.
- The `OCC1990` spine, the allocation matrix, and spec validation gates 1–3 — all belong to that successor plan.
- Wages before 1999, monthly CPS resolution, detailed-occupation deep history, DOT-1991 era-appropriate labels.
- Unemployment-rate-by-occupation as a leading indicator (`docs/cps_data_expansion.md` Option B, step 5).
