# CPS Monthly Backfill and Seasonally Adjusted Forecast Start Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill the CPS A-19 panel with every month from 2020-01 via the BLS API, cross-check it against the A-19 page, and run the CPS composition forecast from both the raw latest month and a seasonally adjusted latest month.

**Architecture:** `download_cps_history.py` pulls the 22 A-19-equivalent `LNU` series from the BLS API in one batched request and writes `data/raw/cps/a19_api_history.csv`. `cps_panel.load_cps_panel` merges seed → API history → A-19 page, with the page used only as a cross-check on shared months. `cps_panel.seasonal_factors` computes classical ratio-to-moving-average factors; `forecast_composition` projects CPS from a `raw` and a `seasonally_adjusted` start, tagged by a new `start_basis` column, and `forecast_charts` adds one chart comparing them.

**Tech Stack:** Python 3, pandas, numpy, requests, matplotlib via `chart_manifest.save_figure`, pytest.

**Spec:** `docs/superpowers/specs/2026-10-02-cps-monthly-backfill-design.md`

## Global Constraints

- Backfill starts at **2020-01**; seasonal factors use months from **2022** onward; a factor resting on fewer than **3** years raises `ValueError`.
- October 2025 has no CPS observation (federal shutdown). It stays missing — never interpolated, never zero.
- Seasonal method: centred 2×12 moving average (weights 1/24, 1/12 ×11, 1/24); factor = mean ratio per calendar month, scaled so the twelve average exactly 1.
- The raw start is primary: the six existing forecast charts show `start_basis == "raw"` only.
- The A-19 page is a cross-check only: any shared `(month, soc_major)` whose value differs from the API raises `ValueError`.
- Series IDs: 11–39 are `LNU02032453`–`LNU02032467` in `CPS_TO_SOC_MAJOR` order; 41 `LNU02032206`, 43 `LNU02032207`, 45 `LNU02032209`, 47 `LNU02032210`, 49 `LNU02032211`, 51 `LNU02032213`, 53 `LNU02032214`.
- Under CI a failed fetch warns and exits 0; locally it exits non-zero.
- `model_signal_over_time`'s CPS panel plots only endpoints whose year-earlier month is at or after the OEWS reference month.
- Every chart goes through `chart_manifest.save_figure`; every new output gets a `docs/outputs.md` row in the same commit; every new chart gets `docs/charts/<name>.md`. A documented chart must have a committed image in the same commit (the pytest link gate).
- Coding standards: no generic abbreviations (`df`, `res`, `tmp`, `val`), domain names, a module docstring on every new file (ruff `D100`).
- Imports go in the file's top import block, never mid-file (ruff `E402`/`I`).
- Run Python as `uv run …`; if `uv` cannot write its cache in the sandbox, `.venv/bin/python …` is equivalent. Anything that reaches `api.bls.gov` or launches headless Chrome must run outside the Bash sandbox.
- Tick each task's boxes in this file in the same commit as that task's code; record any departure in the Deviations log at the end.

## Review Focus

1. **The API returns a month with fewer than 22 groups** (a series discontinued or published late) — expected: `parse_api_payload` raises naming the month, never writes a partial month whose shares would be distorted. *(Test: Task 1 `test_raises_when_a_month_lacks_a_group`.)*
2. **A developer machine already has `data/raw/cps/a19_api_history.csv`** — expected: `load_cps_panel` tests stay hermetic because every test passes an explicit `api_history_path`; none reads the real default. *(Task 2 Step 1 updates the existing tests.)*
3. **The A-19 page fails to parse while API history is present** — expected: warn and keep the API history, not raise and not drop to the seed. *(Test: Task 2 `test_unparseable_release_keeps_the_api_history`.)*
4. **The BLS API is down when a current-year cache file has expired** — expected: warn and use the stale cache rather than return nothing. *(Test: Task 3 `test_falls_back_to_a_stale_cache_when_the_request_fails`.)*
5. **The seed is too short for seasonal factors** (a reverted seed, or CI before promotion) — expected: the forecast stage warns and projects the raw start only. *(Test: Task 5 `test_short_panel_projects_raw_only`.)*

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `cps_panel.py` | A-19 panel: series mapping, merge, cross-check, seasonal factors, YoY pairs | Modify |
| `download_cps_history.py` | Batched BLS API fetch of the 22 series → `data/raw/cps/a19_api_history.csv` | Create |
| `historical_displacement.py` | BLS API fetch + cache; current-year cache expiry | Modify |
| `forecast_composition.py` | `start_basis` plumbing, seasonally adjusted start, derived CPS exclusion | Modify |
| `forecast_charts.py` | Existing charts filter to raw; new `forecast_cps_start_basis.png` | Modify |
| `validate_bls.py` | Signal-panel endpoint filter | Modify |
| `Makefile`, `.github/workflows/release.yml` | Run `download_cps_history.py` before `download_cps.js` | Modify |
| `tests/test_cps.py`, `tests/test_download_cps_history.py`, `tests/test_historical_displacement.py`, `tests/test_forecast_composition.py`, `tests/test_forecast_charts.py` | Tests | Modify / Create |
| `.claude/skills/update-cps-monthly/SKILL.md` | Monthly update procedure | Create |
| Docs (listed per task) | Outputs, seeds, framework, chart pages | Modify |

---

### Task 1: Series mapping and the API history downloader

**Files:**
- Modify: `cps_panel.py` (constants after `OUTPUT_PANEL_PATH`, ~line 82)
- Create: `download_cps_history.py`
- Create: `tests/test_download_cps_history.py`
- Modify: `Makefile` (`download-data`), `.github/workflows/release.yml` (new step before "Download CPS Table A-19 via Puppeteer"), `download_data.py` (docstring line naming the BLS scripts)
- `docs/outputs.md` is not touched: it records `data/output/` products, and `a19_api_history.csv` is a raw input under `data/raw/`.

**Interfaces:**
- Produces: `cps_panel.A19_SERIES_BY_SOC_MAJOR: dict[str, str]`, `cps_panel.OCCUPATION_BY_SOC_MAJOR: dict[str, str]`, `cps_panel.API_HISTORY_PATH = "data/raw/cps/a19_api_history.csv"`, `cps_panel.PANEL_DTYPES: dict[str, type]`, `download_cps_history.HISTORY_START_YEAR = 2020`, `download_cps_history.parse_api_payload(payload: dict) -> pd.DataFrame` (columns `PANEL_COLUMNS`, `employed_thousands` int64).

- [x] **Step 1: Write the failing tests**

Create `tests/test_download_cps_history.py`:

```python
"""
test_download_cps_history.py
────────────────────────────
Tests for download_cps_history.py and the A-19 series mapping in cps_panel.py.
Payloads are built inline, so nothing here reaches the BLS API.
"""

import pandas as pd
import pytest

from cps_panel import A19_SERIES_BY_SOC_MAJOR, CPS_TO_SOC_MAJOR, OCCUPATION_BY_SOC_MAJOR, PANEL_COLUMNS
from download_cps_history import parse_api_payload


def _payload(months_by_soc_major: dict[str, list[tuple[str, str, str]]], status: str = "REQUEST_SUCCEEDED") -> dict:
    """A BLS API response: per SOC major group, (year, period, value) observations."""
    return {
        "status": status,
        "message": [],
        "Results": {
            "series": [
                {"seriesID": A19_SERIES_BY_SOC_MAJOR[soc_major], "data": [{"year": y, "period": p, "value": v} for y, p, v in observations]}
                for soc_major, observations in months_by_soc_major.items()
            ]
        },
    }


def _every_group(observations: list[tuple[str, str, str]]) -> dict[str, list[tuple[str, str, str]]]:
    return {soc_major: observations for soc_major in A19_SERIES_BY_SOC_MAJOR}


class TestSeriesMapping:
    def test_covers_every_major_group_with_a_unique_series(self):
        assert set(A19_SERIES_BY_SOC_MAJOR) == set(CPS_TO_SOC_MAJOR.values())
        assert len(set(A19_SERIES_BY_SOC_MAJOR.values())) == 22

    def test_occupation_names_match_a19_wording(self):
        assert OCCUPATION_BY_SOC_MAJOR["19"] == "Life, physical, and social science occupations"
        assert OCCUPATION_BY_SOC_MAJOR["53"] == "Transportation and material moving occupations"


class TestParseApiPayload:
    def test_returns_panel_schema_with_integer_levels(self):
        history_df = parse_api_payload(_payload(_every_group([("2026", "M09", "21,631"), ("2026", "M08", "21318")])))
        assert list(history_df.columns) == PANEL_COLUMNS
        assert history_df["employed_thousands"].dtype == "int64"
        assert history_df.loc[history_df["month"] == "2026-09", "employed_thousands"].iloc[0] == 21631

    def test_drops_the_annual_average_period(self):
        history_df = parse_api_payload(_payload(_every_group([("2025", "M13", "999"), ("2025", "M12", "100")])))
        assert sorted(history_df["month"].unique()) == ["2025-12"]

    def test_leaves_a_month_bls_did_not_collect_absent_rather_than_zero(self):
        """October 2025 was never collected; the API reports it as '-'."""
        history_df = parse_api_payload(_payload(_every_group([("2025", "M11", "100"), ("2025", "M10", "-"), ("2025", "M09", "100")])))
        assert sorted(history_df["month"].unique()) == ["2025-09", "2025-11"]

    def test_stamps_the_latest_month_as_the_source_reference(self):
        history_df = parse_api_payload(_payload(_every_group([("2026", "M09", "1"), ("2025", "M01", "1")])))
        assert set(history_df["source_reference_month"]) == {"2026-09"}

    def test_raises_when_a_month_lacks_a_group(self):
        observations = _every_group([("2026", "M09", "100")])
        observations["15"] = [("2026", "M08", "100")]
        with pytest.raises(ValueError, match="2026-08|2026-09"):
            parse_api_payload(_payload(observations))

    def test_raises_when_the_api_refuses_the_request(self):
        with pytest.raises(ValueError, match="REQUEST_NOT_PROCESSED"):
            parse_api_payload(_payload({}, status="REQUEST_NOT_PROCESSED"))

    def test_rejects_a_fractional_level(self):
        with pytest.raises(ValueError, match="whole thousands"):
            parse_api_payload(_payload(_every_group([("2026", "M09", "100.5")])))
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_download_cps_history.py -v`
Expected: FAIL — `ImportError: cannot import name 'A19_SERIES_BY_SOC_MAJOR'`.

- [x] **Step 3: Add the mapping to `cps_panel.py`**

After `OUTPUT_PANEL_PATH = ...`, add:

```python
API_HISTORY_PATH = "data/raw/cps/a19_api_history.csv"
PANEL_DTYPES = {"month": str, "soc_major": str, "source_reference_month": str}

# BLS LN series carrying A-19's employment level for each SOC major group, verified
# equal to every published A-19 value on 2026-10-02. 11–39 are a contiguous block;
# 41–53 are the leaf series cps_historical_panel.py already uses.
A19_SERIES_BY_SOC_MAJOR: dict[str, str] = {
    **{
        soc_major: f"LNU02032{453 + offset}"
        for offset, soc_major in enumerate(["11", "13", "15", "17", "19", "21", "23", "25", "27", "29", "31", "33", "35", "37", "39"])
    },
    "41": "LNU02032206",
    "43": "LNU02032207",
    "45": "LNU02032209",
    "47": "LNU02032210",
    "49": "LNU02032211",
    "51": "LNU02032213",
    "53": "LNU02032214",
}
# A-19 writes group names in sentence case; CPS_TO_SOC_MAJOR's keys are those names lowercased.
OCCUPATION_BY_SOC_MAJOR: dict[str, str] = {soc_major: name.capitalize() for name, soc_major in CPS_TO_SOC_MAJOR.items()}
```

Run `uv run ruff format cps_panel.py` so the long comprehension is wrapped.

- [x] **Step 4: Create `download_cps_history.py`**

```python
"""
download_cps_history.py
───────────────────────
Fetches monthly CPS employment for the 22 SOC major groups of Table A-19 from the
BLS public API and writes it in the A-19 panel schema, so cps_panel.py can merge it
with no structural change. One batched request carries all 22 series.

The API is the panel's source; the A-19 page that download_cps.js fetches is kept
only as a cross-check (cps_panel.check_release_against_history). Unlike www.bls.gov,
api.bls.gov answers plain HTTP, so no browser is needed.

October 2025 has no observation — CPS was not collected during the federal
shutdown — and is left absent, never filled.

Inputs:
  • BLS_API_KEY (optional, .env or environment) — raises the API's request limits
Outputs:
  • data/raw/cps/a19_api_history.csv — month, soc_major, occupation,
    employed_thousands, source_reference_month; 2020-01 onward

Like download_cps.js, this warns and exits 0 under CI when the fetch fails, so the
pipeline still renders from seeds/cps_a19_panel.csv; locally it exits non-zero.
"""

import os
import sys
from datetime import date

import pandas as pd
import requests

from cps_panel import A19_SERIES_BY_SOC_MAJOR, API_HISTORY_PATH, OCCUPATION_BY_SOC_MAJOR, PANEL_COLUMNS, SEED_PANEL_PATH
from historical_displacement import BLS_API_URL, REQUEST_TIMEOUT_SECONDS, _api_key

# CPS adopted the 2018 Census occupation coding in January 2020; earlier months are
# not comparable and are deliberately not fetched.
HISTORY_START_YEAR = 2020
ANNUAL_AVERAGE_PERIOD = "M13"


def fetch_history_payload(start_year: int = HISTORY_START_YEAR, end_year: int | None = None) -> dict:
    """One POST for all 22 series; raises on an HTTP or JSON failure."""
    request_body: dict[str, object] = {
        "seriesid": list(A19_SERIES_BY_SOC_MAJOR.values()),
        "startyear": str(start_year),
        "endyear": str(end_year or date.today().year),
    }
    if _api_key():
        request_body["registrationkey"] = _api_key()
    response = requests.post(BLS_API_URL, json=request_body, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def parse_api_payload(payload: dict) -> pd.DataFrame:
    """API response → panel rows. Raises if BLS refused the request or any month lacks a group."""
    if payload.get("status") != "REQUEST_SUCCEEDED":
        raise ValueError(f"BLS API returned {payload.get('status')}: {payload.get('message')}")

    soc_major_by_series = {series_id: soc_major for soc_major, series_id in A19_SERIES_BY_SOC_MAJOR.items()}
    history_rows = []
    for series in payload.get("Results", {}).get("series", []):
        soc_major = soc_major_by_series[series["seriesID"]]
        for observation in series.get("data", []):
            period = observation["period"]
            if not period.startswith("M") or period == ANNUAL_AVERAGE_PERIOD:
                continue
            employed_thousands = pd.to_numeric(str(observation["value"]).replace(",", ""), errors="coerce")
            if pd.isna(employed_thousands):
                continue
            if employed_thousands != int(employed_thousands):
                raise ValueError(f"{series['seriesID']} {observation['year']}-{period[1:]} is {employed_thousands}, not whole thousands")
            history_rows.append(
                {
                    "month": f"{observation['year']}-{period[1:]}",
                    "soc_major": soc_major,
                    "occupation": OCCUPATION_BY_SOC_MAJOR[soc_major],
                    "employed_thousands": int(employed_thousands),
                }
            )

    history_df = pd.DataFrame(history_rows, columns=["month", "soc_major", "occupation", "employed_thousands"])
    groups_per_month = history_df.groupby("month")["soc_major"].nunique()
    incomplete_months = sorted(groups_per_month[groups_per_month != len(A19_SERIES_BY_SOC_MAJOR)].index)
    if history_df.empty or incomplete_months:
        raise ValueError(
            f"BLS API history is missing groups for month(s) {incomplete_months or 'all'}; a partial month would distort shares"
        )

    history_df["employed_thousands"] = history_df["employed_thousands"].astype("int64")
    history_df["source_reference_month"] = history_df["month"].max()
    return history_df.sort_values(["month", "soc_major"]).reset_index(drop=True)[PANEL_COLUMNS]


def main() -> None:
    try:
        history_df = parse_api_payload(fetch_history_payload())
    except (requests.RequestException, ValueError, KeyError) as fetch_error:
        message = f"Could not fetch CPS A-19 history from the BLS API: {fetch_error}"
        if os.environ.get("CI"):
            print(f"WARNING: {message} — the pipeline will use {SEED_PANEL_PATH}.")
            return
        sys.exit(message)

    os.makedirs(os.path.dirname(API_HISTORY_PATH), exist_ok=True)
    history_df.to_csv(API_HISTORY_PATH, index=False)
    print(f"Saved {API_HISTORY_PATH} ({history_df['month'].nunique()} months, {history_df['month'].min()} → {history_df['month'].max()})")


if __name__ == "__main__":
    main()
```

- [x] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_download_cps_history.py -v`
Expected: PASS (9 tests).

- [x] **Step 6: Wire it into the downloads**

In `Makefile`, `download-data`, add `uv run download_cps_history.py` on the line before `node download_cps.js`, and extend the comment above the target: `download_cps_history.py runs before download_cps.js so the A-19 cross-check has API history to compare against.`

In `.github/workflows/release.yml`, insert before the "Download CPS Table A-19 via Puppeteer" step:

```yaml
      # The BLS API is the A-19 panel's source; the Puppeteer step after it only
      # cross-checks the page against this history. Warns rather than fails under CI.
      - name: Download CPS A-19 history from the BLS API
        env:
          BLS_API_KEY: ${{ secrets.BLS_API_KEY }}
        run: uv run download_cps_history.py
```

In `download_data.py`'s docstring, change "and CPS Table A-19 from download_cps.js, both via Puppeteer." to "CPS Table A-19 from download_cps.js, both via Puppeteer, and the A-19 monthly history from download_cps_history.py via the BLS API."

- [x] **Step 7: Run it for real (outside the sandbox)**

Run: `uv run download_cps_history.py`
Expected: `Saved data/raw/cps/a19_api_history.csv (80 months, 2020-01 → 2026-09)` — 81 calendar months less October 2025. Fewer months, or a different latest month, is a finding to record in the Deviations log, not to paper over.

- [x] **Step 8: Lint and commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add cps_panel.py download_cps_history.py tests/test_download_cps_history.py Makefile .github/workflows/release.yml download_data.py docs/superpowers/plans/2026-10-02-cps-monthly-backfill.md
git commit -m "Fetch the A-19 monthly history for all 22 groups from the BLS API"
```

---

### Task 2: Merge the API history and cross-check the A-19 page

**Files:**
- Modify: `cps_panel.py` — `load_cps_panel` (~line 230), new `check_release_against_history`, module docstring Inputs
- Modify: `tests/test_cps.py` — `TestLoadCpsPanel`

**Interfaces:**
- Consumes: `API_HISTORY_PATH`, `PANEL_DTYPES` (Task 1).
- Produces: `load_cps_panel(seed_path=SEED_PANEL_PATH, release_html_path=LATEST_RELEASE_HTML_PATH, output_path=OUTPUT_PANEL_PATH, api_history_path=API_HISTORY_PATH) -> pd.DataFrame | None`; `check_release_against_history(release_df: pd.DataFrame, api_history_df: pd.DataFrame) -> None` (raises `ValueError`).

- [x] **Step 1: Make the existing tests hermetic**

Every existing call in `TestLoadCpsPanel` passes three positional arguments. Add a fourth, an absent API history path, to each — e.g.:

```python
panel_df = load_cps_panel(str(seed_path), str(tmp_path / "absent.html"), None, str(tmp_path / "absent_api.csv"))
```

Apply the same change to all six existing tests in the class. Run `uv run pytest tests/test_cps.py -v` — expected: FAIL with `TypeError: load_cps_panel() takes from 0 to 3 positional arguments` (the parameter does not exist yet).

- [x] **Step 2: Write the new failing tests**

Add `check_release_against_history` and `parse_a19_release` to the `from cps_panel import (...)` block if not already present, then append to `TestLoadCpsPanel`:

```python
    def test_api_history_wins_over_the_seed(self, tmp_path):
        seed_path, api_path = tmp_path / "seed.csv", tmp_path / "api.csv"
        _panel([("2025-04", "15", 1)]).to_csv(seed_path, index=False)
        _panel([("2025-04", "15", 6643), ("2025-05", "15", 6700)]).to_csv(api_path, index=False)
        panel_df = load_cps_panel(str(seed_path), str(tmp_path / "absent.html"), None, str(api_path))
        by_month = panel_df.set_index("month")["employed_thousands"]
        assert by_month["2025-04"] == 6643
        assert by_month["2025-05"] == 6700

    def test_release_matching_the_api_merges_its_extra_months(self, tmp_path):
        """Months only the page has (a run where the API was blocked earlier) still arrive."""
        api_path = tmp_path / "api.csv"
        release_df = parse_a19_release(FIXTURE_PATH)
        release_df[release_df["month"] == "2025-04"].to_csv(api_path, index=False)
        panel_df = load_cps_panel(str(tmp_path / "absent.csv"), FIXTURE_PATH, None, str(api_path))
        assert sorted(panel_df["month"].unique()) == ["2025-04", "2025-06", "2026-04", "2026-06"]

    def test_release_disagreeing_with_the_api_raises(self, tmp_path):
        api_path = tmp_path / "api.csv"
        api_history_df = parse_a19_release(FIXTURE_PATH)
        api_history_df.loc[0, "employed_thousands"] += 1
        api_history_df.to_csv(api_path, index=False)
        with pytest.raises(ValueError, match="disagrees with the BLS API"):
            load_cps_panel(str(tmp_path / "absent.csv"), FIXTURE_PATH, None, str(api_path))

    def test_unparseable_release_keeps_the_api_history(self, tmp_path):
        api_path = tmp_path / "api.csv"
        _panel([("2025-05", "15", 6700), ("2026-05", "15", 6900)]).to_csv(api_path, index=False)
        broken_release = tmp_path / "broken.html"
        broken_release.write_text(open(FIXTURE_PATH, encoding="utf-8").read().replace(">Total<", ">Grand total<"), encoding="utf-8")
        panel_df = load_cps_panel(str(tmp_path / "absent.csv"), str(broken_release), None, str(api_path))
        assert sorted(panel_df["month"].unique()) == ["2025-05", "2026-05"]


class TestCheckReleaseAgainstHistory:
    def test_passes_when_shared_months_agree(self):
        release_df = parse_a19_release(FIXTURE_PATH)
        check_release_against_history(release_df, release_df.copy())

    def test_ignores_months_the_api_history_lacks(self):
        release_df = parse_a19_release(FIXTURE_PATH)
        check_release_against_history(release_df, release_df[release_df["month"] == "2025-04"])
```

- [x] **Step 3: Implement**

In `cps_panel.py`, add above `load_cps_panel`:

```python
def check_release_against_history(release_df: pd.DataFrame, api_history_df: pd.DataFrame) -> None:
    """
    Raise if the A-19 page and the API history disagree on any month they share.

    The API is the panel's source and the page is the check on it: a disagreement
    means a series ID now points at a different group, or BLS revised one product
    and not the other. Either way a silent merge would mislabel a sector.
    """
    keys = ["month", "soc_major"]
    compared_df = release_df.merge(api_history_df, on=keys, suffixes=("_release", "_api"))
    differing_df = compared_df[
        compared_df["employed_thousands_release"].astype(float) != compared_df["employed_thousands_api"].astype(float)
    ]
    if not differing_df.empty:
        examples = differing_df[[*keys, "employed_thousands_release", "employed_thousands_api"]].head(5).to_dict("records")
        raise ValueError(f"The A-19 page disagrees with the BLS API on {len(differing_df)} row(s), e.g. {examples}")
```

Replace `load_cps_panel` with:

```python
def load_cps_panel(
    seed_path: str = SEED_PANEL_PATH,
    release_html_path: str = LATEST_RELEASE_HTML_PATH,
    output_path: str | None = OUTPUT_PANEL_PATH,
    api_history_path: str = API_HISTORY_PATH,
) -> pd.DataFrame | None:
    """
    Build the working panel: the committed seed, then the API history, then the A-19 page.

    The API history (download_cps_history.py) is the source and wins over the seed.
    The A-19 page is a cross-check: a month it shares with the API history must
    agree exactly or this raises; a month only the page has is merged. Returns None
    only when no source is available. A missing or unparseable page is not fatal —
    the parse error is surfaced loudly, but the seed and API history still yield
    correctly labelled charts.
    """
    panel_df = pd.DataFrame(columns=PANEL_COLUMNS)
    if os.path.exists(seed_path):
        panel_df = pd.read_csv(seed_path, dtype=PANEL_DTYPES)

    api_history_df = None
    if os.path.exists(api_history_path):
        api_history_df = pd.read_csv(api_history_path, dtype=PANEL_DTYPES)
        panel_df = merge_panel(panel_df, api_history_df)

    release_df = None
    if os.path.exists(release_html_path):
        try:
            release_df = parse_a19_release(release_html_path)
        except (ValueError, IndexError) as parse_error:
            print(f"  WARNING: could not parse {release_html_path} — {parse_error}")
            print("  Falling back to the committed CPS panel seed and API history; the A-19 cross-check did not run.")
    else:
        print(f"  Note: {release_html_path} not found — the A-19 cross-check did not run.")

    if release_df is not None:
        if api_history_df is not None:
            check_release_against_history(release_df, api_history_df)
        panel_df = merge_panel(panel_df, release_df)

    if panel_df.empty:
        return None

    if output_path is not None:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        panel_df.to_csv(output_path, index=False)

    return panel_df
```

Update the module docstring's Inputs block to list `data/raw/cps/a19_api_history.csv (optional — monthly history from download_cps_history.py; the panel's source)` above the A-19 line, and rewrite the second paragraph to say the API history now supplies every month from 2020-01 and the page is a cross-check.

- [x] **Step 4: Run the tests**

Run: `uv run pytest tests/test_cps.py -v`
Expected: PASS, including the six updated and six new tests.

- [x] **Step 5: Commit**

```bash
git add cps_panel.py tests/test_cps.py docs/superpowers/plans/2026-10-02-cps-monthly-backfill.md
git commit -m "Merge the API history into the A-19 panel and cross-check the page against it"
```

---

### Task 3: Expire current-year BLS API cache entries

**Files:**
- Modify: `historical_displacement.py` — `fetch_bls_series` (~line 219), new `_cache_is_fresh`, `_request_series`; imports; module docstring cache line (~line 24)
- Modify: `tests/test_historical_displacement.py` — new `TestFetchBlsSeriesCache`

**Interfaces:**
- Produces: `historical_displacement.CURRENT_YEAR_CACHE_MAX_AGE_SECONDS = 86400`; `fetch_bls_series` signature unchanged.

- [x] **Step 1: Write the failing tests**

Append to `tests/test_historical_displacement.py` (add `import json`, `import time`, `from datetime import date` to the top import block):

```python
def _series_payload(value: str) -> dict:
    return {
        "status": "REQUEST_SUCCEEDED",
        "Results": {"series": [{"seriesID": "X", "data": [{"year": "2026", "period": "M01", "value": value}]}]},
    }


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class TestFetchBlsSeriesCache:
    @pytest.fixture
    def cache_dir(self, monkeypatch, tmp_path):
        monkeypatch.setattr(historical_displacement, "API_CACHE_DIR", str(tmp_path))
        monkeypatch.setattr(historical_displacement, "_api_key", lambda: "")
        return tmp_path

    def _write_cache(self, cache_dir, start_year, end_year, value, age_seconds):
        cache_path = cache_dir / f"X_{start_year}_{end_year}.json"
        cache_path.write_text(json.dumps(_series_payload(value)), encoding="utf-8")
        stale_time = time.time() - age_seconds
        os.utime(cache_path, (stale_time, stale_time))

    def test_refetches_an_expired_current_year_cache(self, cache_dir, monkeypatch):
        this_year = date.today().year
        self._write_cache(cache_dir, this_year, this_year, "1", age_seconds=2 * 86400)
        monkeypatch.setattr(historical_displacement.requests, "post", lambda *args, **kwargs: _FakeResponse(_series_payload("2")))
        series_df = historical_displacement.fetch_bls_series("X", this_year, this_year)
        assert series_df["value"].tolist() == [2.0]

    def test_keeps_a_fresh_current_year_cache(self, cache_dir, monkeypatch):
        this_year = date.today().year
        self._write_cache(cache_dir, this_year, this_year, "1", age_seconds=60)
        monkeypatch.setattr(historical_displacement.requests, "post", lambda *args, **kwargs: pytest.fail("fresh cache was refetched"))
        assert historical_displacement.fetch_bls_series("X", this_year, this_year)["value"].tolist() == [1.0]

    def test_never_expires_a_past_only_cache(self, cache_dir, monkeypatch):
        past_year = date.today().year - 2
        self._write_cache(cache_dir, past_year, past_year, "1", age_seconds=400 * 86400)
        monkeypatch.setattr(historical_displacement.requests, "post", lambda *args, **kwargs: pytest.fail("past cache was refetched"))
        assert historical_displacement.fetch_bls_series("X", past_year, past_year)["value"].tolist() == [1.0]

    def test_falls_back_to_a_stale_cache_when_the_request_fails(self, cache_dir, monkeypatch):
        this_year = date.today().year
        self._write_cache(cache_dir, this_year, this_year, "1", age_seconds=2 * 86400)

        def _refuse(*args, **kwargs):
            raise historical_displacement.requests.ConnectionError("offline")

        monkeypatch.setattr(historical_displacement.requests, "post", _refuse)
        with pytest.warns(UserWarning, match="stale"):
            series_df = historical_displacement.fetch_bls_series("X", this_year, this_year)
        assert series_df["value"].tolist() == [1.0]
```

(`os` is already imported at the top of that test file.)

- [x] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_historical_displacement.py::TestFetchBlsSeriesCache -v`
Expected: `test_refetches_an_expired_current_year_cache` and `test_falls_back_to_a_stale_cache_when_the_request_fails` FAIL (the cache is always used); the other two pass.

- [x] **Step 3: Implement**

Add `import time` and `from datetime import date` to the top imports. Add near `_cache_path`:

```python
# A cache file covering the current year goes stale as BLS publishes new months;
# one covering only past years never changes. 24 hours is shorter than the gap
# between monthly releases and long enough that a day's re-runs stay offline.
CURRENT_YEAR_CACHE_MAX_AGE_SECONDS = 24 * 60 * 60


def _cache_is_fresh(cache_path: str, end_year: int) -> bool:
    if not os.path.exists(cache_path):
        return False
    if end_year < date.today().year:
        return True
    return time.time() - os.path.getmtime(cache_path) < CURRENT_YEAR_CACHE_MAX_AGE_SECONDS


def _request_series(series_id: str, start_year: int, end_year: int) -> dict | None:
    """One API request; warns and returns None on any failure."""
    request_body: dict[str, object] = {"seriesid": [series_id], "startyear": str(start_year), "endyear": str(end_year)}
    if _api_key():
        request_body["registrationkey"] = _api_key()
    try:
        response = requests.post(BLS_API_URL, json=request_body, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as request_error:
        warnings.warn(f"Could not fetch BLS series {series_id}: {request_error}", stacklevel=3)
        return None
    if payload.get("status") != "REQUEST_SUCCEEDED":
        warnings.warn(f"BLS API refused series {series_id}: {payload.get('message')}", stacklevel=3)
        return None
    return payload
```

Replace the cache/request block at the top of `fetch_bls_series` (from `payload = None` through the cache write) with:

```python
    if _cache_is_fresh(cache_path, end_year):
        with open(cache_path, encoding="utf-8") as cache_file:
            payload = json.load(cache_file)
    else:
        payload = _request_series(series_id, start_year, end_year)
        if payload is None:
            if not os.path.exists(cache_path):
                return None
            warnings.warn(f"Using a stale cached copy of BLS series {series_id}; newer months may be missing", stacklevel=2)
            with open(cache_path, encoding="utf-8") as cache_file:
                payload = json.load(cache_file)
        else:
            with open(cache_path, "w", encoding="utf-8") as cache_file:
                json.dump(payload, cache_file)
```

Update the docstring line `data/raw/bls_api/<series_id>_<start>_<end>.json  (fetch cache)` to `(fetch cache; ranges covering the current year expire after 24 hours)`.

- [x] **Step 4: Run the tests**

Run: `uv run pytest tests/test_historical_displacement.py -v`
Expected: PASS, all classes.

- [ ] **Step 5: Commit**

```bash
git add historical_displacement.py tests/test_historical_displacement.py docs/superpowers/plans/2026-10-02-cps-monthly-backfill.md
git commit -m "Expire BLS API cache entries that cover the current year after a day"
```

---

### Task 4: Seasonal factors

**Files:**
- Modify: `cps_panel.py` — new `seasonal_factors` and constants; add `import numpy as np`; module docstring
- Modify: `tests/test_cps.py` — new `TestSeasonalFactors`

**Interfaces:**
- Consumes: panel frames in `PANEL_COLUMNS` schema.
- Produces: `cps_panel.seasonal_factors(panel_df: pd.DataFrame, first_year: int = SEASONAL_FACTOR_FIRST_YEAR) -> pd.DataFrame` with columns `soc_major` (str), `calendar_month` (int 1–12), `factor` (float), `n_years` (int); `SEASONAL_FACTOR_FIRST_YEAR = 2022`; `MINIMUM_SEASONAL_YEARS = 3`.

- [x] **Step 1: Write the failing tests**

Add `seasonal_factors` to the `from cps_panel import (...)` block and `import numpy as np` to the top of `tests/test_cps.py`, then append:

```python
SEASONAL_PATTERN = np.array([0.97, 0.98, 0.99, 1.00, 1.01, 1.02, 1.03, 1.02, 1.01, 1.00, 0.99, 0.98])
SEASONAL_PATTERN = SEASONAL_PATTERN / SEASONAL_PATTERN.mean()


def _seasonal_panel(first_month="2020-01", last_month="2026-09", missing_months=(), groups=("11", "25")):
    """Constant level × a known seasonal pattern, so each true factor is SEASONAL_PATTERN[month - 1]."""
    rows = [
        (str(month), soc_major, 1000.0 * (index + 1) * SEASONAL_PATTERN[month.month - 1])
        for month in pd.period_range(first_month, last_month, freq="M")
        if str(month) not in missing_months
        for index, soc_major in enumerate(groups)
    ]
    return _panel(rows)


class TestSeasonalFactors:
    def test_recovers_a_known_pattern(self):
        factors_df = seasonal_factors(_seasonal_panel())
        for row in factors_df.itertuples():
            assert row.factor == pytest.approx(SEASONAL_PATTERN[row.calendar_month - 1], abs=1e-9)

    def test_factors_average_one_per_group(self):
        factors_df = seasonal_factors(_seasonal_panel())
        assert factors_df.groupby("soc_major")["factor"].mean().tolist() == pytest.approx([1.0, 1.0])
        assert len(factors_df) == 24

    def test_a_missing_month_removes_only_the_ratios_whose_window_touches_it(self):
        """October 2025's gap removes April 2025 – April 2026; the pattern is still recovered."""
        factors_df = seasonal_factors(_seasonal_panel(missing_months=("2025-10",)))
        years_by_month = factors_df[factors_df["soc_major"] == "11"].set_index("calendar_month")["n_years"]
        assert years_by_month[1] == 4  # 2022–2025
        assert years_by_month[10] == 3  # 2022–2024
        assert years_by_month[9] == 3  # 2025-09's window reaches the gap; 2026-09 has no forward window
        for row in factors_df.itertuples():
            assert row.factor == pytest.approx(SEASONAL_PATTERN[row.calendar_month - 1], abs=1e-9)

    def test_raises_when_a_factor_rests_on_too_few_years(self):
        with pytest.raises(ValueError, match="fewer than 3"):
            seasonal_factors(_seasonal_panel(first_month="2021-01", last_month="2024-06"))

    def test_ignores_ratios_before_the_first_year(self):
        """Unbroken 2020-01 → 2026-09: January ratios exist 2022–2026, so moving first_year drops one."""
        january_years = lambda factors_df: factors_df.set_index(["soc_major", "calendar_month"]).loc[("11", 1), "n_years"]
        assert january_years(seasonal_factors(_seasonal_panel())) == 5
        assert january_years(seasonal_factors(_seasonal_panel(), first_year=2023)) == 4
```

- [x] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_cps.py::TestSeasonalFactors -v`
Expected: FAIL — `ImportError: cannot import name 'seasonal_factors'`.

- [x] **Step 3: Implement**

Add `import numpy as np` to `cps_panel.py`'s imports. Add after `PANEL_COLUMNS`:

```python
SEASONAL_FACTOR_FIRST_YEAR = 2022  # excludes the 2020–21 COVID swings
MINIMUM_SEASONAL_YEARS = 3
# Centred 2×12 moving average: the two months six away share one weight, so each
# calendar month counts exactly once and a pure seasonal pattern averages to 1.
CENTRED_MOVING_AVERAGE_WEIGHTS = np.array([0.5, *[1.0] * 11, 0.5]) / 12
```

Add after `build_growth_frame`:

```python
def seasonal_factors(panel_df: pd.DataFrame, first_year: int = SEASONAL_FACTOR_FIRST_YEAR) -> pd.DataFrame:
    """
    Classical ratio-to-moving-average seasonal factors per SOC major group and calendar month.

    A-19 is not seasonally adjusted. Each group's level is divided by its centred
    2×12 moving average; the factor is the mean of those ratios for one calendar
    month across years from `first_year`, scaled so the twelve average exactly 1.
    A moving-average window touching a missing month (October 2025 was never
    collected) yields no ratio rather than a filled one. Raises when any factor
    rests on fewer than MINIMUM_SEASONAL_YEARS years.
    """
    factor_frames = []
    for soc_major, group_df in panel_df.groupby("soc_major"):
        levels = group_df.set_index(pd.PeriodIndex(group_df["month"], freq="M"))["employed_thousands"].astype(float).sort_index()
        levels = levels.reindex(pd.period_range(levels.index.min(), levels.index.max(), freq="M"))
        moving_average = levels.rolling(len(CENTRED_MOVING_AVERAGE_WEIGHTS), center=True).apply(
            lambda window: float(np.dot(window, CENTRED_MOVING_AVERAGE_WEIGHTS)), raw=True
        )
        ratios = (levels / moving_average).dropna()
        ratios = ratios[ratios.index.year >= first_year]
        by_calendar_month = ratios.groupby(ratios.index.month).agg(["mean", "count"]).reindex(range(1, 13))
        thin_months = by_calendar_month.index[by_calendar_month["count"].fillna(0) < MINIMUM_SEASONAL_YEARS].tolist()
        if thin_months:
            raise ValueError(
                f"Seasonal factor for SOC {soc_major} calendar month(s) {thin_months} rests on fewer than "
                f"{MINIMUM_SEASONAL_YEARS} years from {first_year}"
            )
        factor_frames.append(
            pd.DataFrame(
                {
                    "soc_major": str(soc_major),
                    "calendar_month": range(1, 13),
                    "factor": (by_calendar_month["mean"] / by_calendar_month["mean"].mean()).to_numpy(),
                    "n_years": by_calendar_month["count"].astype(int).to_numpy(),
                }
            )
        )
    return pd.concat(factor_frames, ignore_index=True)
```

Add a paragraph to the module docstring: seasonal factors are derived from the panel by `seasonal_factors` for the forecast stage's seasonally adjusted start; the comparison windows remain unadjusted.

- [x] **Step 4: Run the tests**

Run: `uv run pytest tests/test_cps.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add cps_panel.py tests/test_cps.py docs/superpowers/plans/2026-10-02-cps-monthly-backfill.md
git commit -m "Derive A-19 seasonal factors by ratio to a centred moving average"
```

---

### Task 5: Project CPS from raw and seasonally adjusted starts

**Files:**
- Modify: `forecast_composition.py` — constants (~lines 52–80), `cps_excluded_periods` (new), `run_estimation` (~line 386), `cps_start_shares` (~line 493), `project_scenarios`, `project_both_instruments`, `bootstrap_bands`, `add_sector_noise`, `leave_one_period_out`, `run_stage`; module docstring Outputs
- Modify: `tests/test_forecast_composition.py`
- Modify: `docs/outputs.md` — new row `cps_seasonal_factors.csv`; `forecast_sector_paths.csv` and `forecast_sector_stability.csv` rows gain `start_basis`
- Modify: `docs/superpowers/plans/2026-10-02-decomposed-slope-forecast.md` is **not** touched (completed plan)

**Interfaces:**
- Consumes: `cps_panel.seasonal_factors` (Task 4); `cps_detailed_panel.SEED_PATH`.
- Produces: `START_BASES = ("raw", "seasonally_adjusted")`; `SEASONAL_FACTORS_OUTPUT_PATH = "data/output/cps_seasonal_factors.csv"`; `SECTOR_PATH_COLUMNS = ["instrument", "start_basis", "unemployment_scenario", "adoption_fit", "as_of", "soc_major", "share", "employment"]`; `cps_excluded_periods(detailed_panel_df: pd.DataFrame) -> dict[str, str]`; `cps_start_shares(a19_panel_df, factors_df: pd.DataFrame | None = None) -> tuple[str, pd.Series]`; `project_scenarios(..., coefficients=None, start_basis: str = "raw")`; `project_both_instruments(...) -> tuple[pd.DataFrame, dict[tuple[str, str], tuple]]` — starts keyed by `(instrument, start_basis)`; `bootstrap_bands(estimate, start, adoption_fits, coefficient_draws, start_basis="raw")`; `leave_one_period_out(estimate, start, adoption_fits, start_basis="raw")` output gains `start_basis`.

- [x] **Step 1: Write the failing tests**

In `tests/test_forecast_composition.py` add `cps_excluded_periods` and `add_sector_noise` to the import block, and `from cps_panel import seasonal_factors`. Update `test_projection_runs_oews_alone_without_reading_a19`'s last assertion to `assert set(starts) == {("oews", "raw")}` and add `assert set(sector_paths_df["start_basis"]) == {"raw"}`. Then add:

```python
SEASONAL_PATTERN = np.array([0.97, 0.98, 0.99, 1.00, 1.01, 1.02, 1.03, 1.02, 1.01, 1.00, 0.99, 0.98])


def synthetic_a19_panel(first_month="2020-01", last_month="2026-09") -> pd.DataFrame:
    """22 sectors, level rising with sector index, × a seasonal pattern that differs by sector parity."""
    rows = []
    for month in pd.period_range(first_month, last_month, freq="M"):
        for index, sector in enumerate(SECTORS):
            pattern = SEASONAL_PATTERN if index % 2 == 0 else SEASONAL_PATTERN[::-1]
            employed_thousands = (100.0 + index) * pattern[month.month - 1] / pattern.mean()
            rows.append(
                {
                    "month": str(month),
                    "soc_major": sector,
                    "occupation": sector,
                    "employed_thousands": employed_thousands,
                    "source_reference_month": last_month,
                }
            )
    return pd.DataFrame(rows)


def cps_estimate(scores) -> "forecast_composition.InstrumentEstimate":
    return forecast_composition.InstrumentEstimate(
        instrument="cps",
        scores=scores,
        panel_df=synthetic_panel({}, scores, years=range(2020, 2026)),
        driven_df=pd.DataFrame(),
        stage2_df=pd.DataFrame({"residual_sd": [0.01, 0.01]}),
        decomposition_df=pd.DataFrame(),
        coefficients={"structural": 0.01, "cycle": 0.0, "ai": 0.0},
    )


class TestStartBasis:
    def test_seasonally_adjusted_start_divides_by_the_month_factor_and_keeps_the_total(self):
        a19_df = synthetic_a19_panel()
        factors_df = seasonal_factors(a19_df)
        _, raw_employment = cps_start_shares(a19_df)
        label, adjusted_employment = cps_start_shares(a19_df, factors_df)
        september = factors_df[factors_df["calendar_month"] == 9].set_index("soc_major")["factor"]
        expected = raw_employment / september.reindex(raw_employment.index)
        expected = expected * raw_employment.sum() / expected.sum()
        assert label == "2026-09"
        assert adjusted_employment.to_numpy() == pytest.approx(expected.to_numpy())
        assert adjusted_employment.sum() == pytest.approx(raw_employment.sum())
        # the synthetic levels are trend-free, so adjustment removes all seasonal distortion
        assert (adjusted_employment / adjusted_employment.sum()).to_numpy() == pytest.approx(
            (np.arange(22) + 100.0) / (np.arange(22) + 100.0).sum(), abs=1e-6
        )

    def test_seasonally_adjusted_start_raises_without_a_factor_for_every_sector(self):
        a19_df = synthetic_a19_panel()
        factors_df = seasonal_factors(a19_df)
        with pytest.raises(ValueError, match="seasonal factor"):
            cps_start_shares(a19_df, factors_df[factors_df["soc_major"] != SECTORS[0]])

    def test_cps_projects_both_bases_and_oews_raw_only(self, monkeypatch, tmp_path, scores):
        a19_path = tmp_path / "a19.csv"
        synthetic_a19_panel().to_csv(a19_path, index=False)
        monkeypatch.setattr(forecast_composition, "CPS_A19_PANEL_PATH", str(a19_path))
        monkeypatch.setattr(forecast_composition, "SEASONAL_FACTORS_OUTPUT_PATH", str(tmp_path / "factors.csv"))
        oews = dataclasses.replace(cps_estimate(scores), instrument="oews")
        fits = {"linear": AdoptionFit("linear", (0.1, 0.0), 0.5, True)}
        sector_paths_df, starts = forecast_composition.project_both_instruments({"oews": oews, "cps": cps_estimate(scores)}, fits)
        bases = sector_paths_df.groupby("instrument")["start_basis"].unique().map(set).to_dict()
        assert bases == {"oews": {"raw"}, "cps": {"raw", "seasonally_adjusted"}}
        assert set(starts) == {("oews", "raw"), ("cps", "raw"), ("cps", "seasonally_adjusted")}
        assert (tmp_path / "factors.csv").exists()

    def test_short_panel_projects_raw_only(self, monkeypatch, tmp_path, scores, capsys):
        a19_path = tmp_path / "a19.csv"
        synthetic_a19_panel(first_month="2025-04").to_csv(a19_path, index=False)
        monkeypatch.setattr(forecast_composition, "CPS_A19_PANEL_PATH", str(a19_path))
        monkeypatch.setattr(forecast_composition, "SEASONAL_FACTORS_OUTPUT_PATH", str(tmp_path / "factors.csv"))
        fits = {"linear": AdoptionFit("linear", (0.1, 0.0), 0.5, True)}
        sector_paths_df, starts = forecast_composition.project_both_instruments({"cps": cps_estimate(scores)}, fits)
        assert set(sector_paths_df["start_basis"]) == {"raw"}
        assert set(starts) == {("cps", "raw")}
        assert "seasonally adjusted start skipped" in capsys.readouterr().out

    def test_sector_noise_handles_both_bases(self, monkeypatch, tmp_path, scores):
        a19_path = tmp_path / "a19.csv"
        synthetic_a19_panel().to_csv(a19_path, index=False)
        monkeypatch.setattr(forecast_composition, "CPS_A19_PANEL_PATH", str(a19_path))
        monkeypatch.setattr(forecast_composition, "SEASONAL_FACTORS_OUTPUT_PATH", str(tmp_path / "factors.csv"))
        estimates = {"cps": cps_estimate(scores)}
        fits = {"linear": AdoptionFit("linear", (0.1, 0.0), 0.5, True)}
        sector_paths_df, starts = forecast_composition.project_both_instruments(estimates, fits)
        noisy_df = add_sector_noise(sector_paths_df, estimates, starts)
        assert noisy_df[["noise_low", "noise_high"]].notna().all().all()
        assert len(noisy_df) == len(sector_paths_df)


class TestCpsExcludedPeriods:
    def test_excludes_a_partial_terminal_year_with_its_month_count(self):
        detailed_df = pd.DataFrame({"year": [2025, 2026, 2026], "months_observed": [11, 8, 8]})
        assert cps_excluded_periods(detailed_df) == {"2025_2026": "partial year (2026 averages 8 months)"}

    def test_excludes_nothing_when_the_terminal_year_is_complete(self):
        assert cps_excluded_periods(pd.DataFrame({"year": [2025, 2026], "months_observed": [11, 12]})) == {}
```

Add `import dataclasses` to the test file's imports (`InstrumentEstimate` is a plain `@dataclass`).

- [x] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_forecast_composition.py -v`
Expected: the new tests FAIL (`ImportError: cannot import name 'cps_excluded_periods'`).

- [x] **Step 3: Derive the CPS exclusion**

Add `from cps_detailed_panel import SEED_PATH as CPS_DETAILED_PANEL_PATH` and `from cps_panel import seasonal_factors` to the imports. Replace the `CPS_EXCLUDED_PERIODS` constant and its comment with:

```python
COMPLETE_YEAR_MONTHS = 12


def cps_excluded_periods(detailed_panel_df: pd.DataFrame) -> dict[str, str]:
    """Exclude the CPS rollup's terminal period when its last year averages fewer than 12 months.

    The rollup (cps_major_rollup_trends.csv) is built from the IPUMS detailed panel,
    not from A-19, so its month count comes from that panel's months_observed.
    """
    months_by_year = detailed_panel_df.groupby("year")["months_observed"].max()
    terminal_year = int(months_by_year.index.max())
    months_observed = int(months_by_year[terminal_year])
    if months_observed >= COMPLETE_YEAR_MONTHS:
        return {}
    return {f"{terminal_year - 1}_{terminal_year}": f"partial year ({terminal_year} averages {months_observed} months)"}
```

Delete `EXCLUDED_PERIODS_BY_INSTRUMENT`. In `run_estimation`, before the `for instrument, panel_df in panels.items():` loop, add:

```python
    excluded_periods_by_instrument = {"oews": OEWS_EXCLUDED_PERIODS}
    if "cps" in panels:
        excluded_periods_by_instrument["cps"] = cps_excluded_periods(pd.read_csv(CPS_DETAILED_PANEL_PATH, usecols=["year", "months_observed"]))
```

and pass `excluded_periods_by_instrument[instrument]` in place of `EXCLUDED_PERIODS_BY_INSTRUMENT[instrument]`.

- [x] **Step 4: Add the seasonally adjusted start and `start_basis`**

Constants: add `START_BASES = ("raw", "seasonally_adjusted")` and `SEASONAL_FACTORS_OUTPUT_PATH = "data/output/cps_seasonal_factors.csv"`; set `SECTOR_PATH_COLUMNS` to the list in Interfaces.

Replace `cps_start_shares`:

```python
def cps_start_shares(a19_panel_df: pd.DataFrame, factors_df: pd.DataFrame | None = None) -> tuple[str, pd.Series]:
    """Latest A-19 month's sector levels, raw or divided by that calendar month's seasonal factor.

    The adjusted levels are rescaled to the raw month's total, so both starts describe
    the same workforce and differ only in how it is split across sectors.
    """
    latest_month = str(a19_panel_df["month"].max())
    month_df = a19_panel_df[a19_panel_df["month"].astype(str) == latest_month]
    employment = month_df.set_index(month_df["soc_major"].map(sector_code))["employed_thousands"].astype(float)
    if employment.index.nunique() != REQUIRED_SECTOR_COUNT:
        raise ValueError(f"A-19 {latest_month} has {employment.index.nunique()} sectors; a missing sector would distort every share")
    if factors_df is None:
        return latest_month, employment.sort_index()
    month_factors_df = factors_df[factors_df["calendar_month"] == int(latest_month[5:7])]
    month_factors = month_factors_df.set_index(month_factors_df["soc_major"].map(sector_code))["factor"].reindex(employment.index)
    if month_factors.isna().any():
        raise ValueError(f"No seasonal factor for sector(s) {sorted(month_factors[month_factors.isna()].index)}")
    adjusted_employment = employment / month_factors
    return latest_month, (adjusted_employment * employment.sum() / adjusted_employment.sum()).sort_index()


def cps_seasonal_factors_or_none(a19_panel_df: pd.DataFrame) -> pd.DataFrame | None:
    """Seasonal factors, written and printed; None (with a warning) when the panel cannot support them."""
    try:
        factors_df = seasonal_factors(a19_panel_df)
    except ValueError as factor_error:
        print(f"  ⚠ {factor_error}; seasonally adjusted start skipped, CPS projects from the raw start only.")
        return None
    factors_df.to_csv(SEASONAL_FACTORS_OUTPUT_PATH, index=False)
    print(f"  ✓ {SEASONAL_FACTORS_OUTPUT_PATH}")
    print(factors_df.pivot(index="soc_major", columns="calendar_month", values="factor").round(3).to_string())
    return factors_df
```

`project_scenarios`: add keyword parameter `start_basis: str = "raw"` after `coefficients`, and change the `assign` to `long_df.assign(instrument=estimate.instrument, start_basis=start_basis, unemployment_scenario=scenario_name, adoption_fit=fit_name)`.

Replace `project_both_instruments`:

```python
def project_both_instruments(estimates: dict[str, InstrumentEstimate], adoption_fits: dict[str, AdoptionFit]) -> tuple[pd.DataFrame, dict]:
    """Point projections per (instrument, start_basis); returns the paths and each start's (label, employment, steps)."""
    starts = {}
    if "oews" in estimates:
        oews_label, oews_year, oews_employment = oews_start(estimates["oews"].panel_df)
        starts[("oews", "raw")] = (oews_label, oews_employment, oews_steps(oews_year))
    if "cps" in estimates:
        a19_panel_df = pd.read_csv(CPS_A19_PANEL_PATH, dtype={"month": str, "soc_major": str})
        cps_label, cps_employment = cps_start_shares(a19_panel_df)
        starts[("cps", "raw")] = (cps_label, cps_employment, cps_steps(cps_label))
        factors_df = cps_seasonal_factors_or_none(a19_panel_df)
        if factors_df is not None:
            _, adjusted_employment = cps_start_shares(a19_panel_df, factors_df)
            starts[("cps", "seasonally_adjusted")] = (cps_label, adjusted_employment, cps_steps(cps_label))
    path_frames = [
        project_scenarios(estimates[instrument], *starts[(instrument, start_basis)], adoption_fits, start_basis=start_basis)
        for instrument, start_basis in starts
    ]
    return pd.concat(path_frames, ignore_index=True), starts
```

`bootstrap_bands`: add `start_basis: str = "raw"`; pass `start_basis=start_basis` to `project_scenarios`; set `keys = ["instrument", "start_basis", "unemployment_scenario", "adoption_fit", "as_of", "soc_major"]`.

`add_sector_noise`: iterate `for (instrument, start_basis), instrument_df in sector_paths_df.groupby(["instrument", "start_basis"]):` and read `_, _, steps = starts[(instrument, start_basis)]`.

`leave_one_period_out`: add `start_basis: str = "raw"`; pass it to `project_scenarios`; add `"start_basis": start_basis,` after `"instrument"` in the returned frame.

`run_stage`: replace the band/stability loop and `keys` with:

```python
    for instrument, estimate in estimates.items():
        terms = tuple(estimate.decomposition_df["term"])
        coefficient_draws, skipped = bootstrap_coefficients(estimate.stage2_df, BOOTSTRAP_REPLICATES, rng, terms)
        print(f"  {instrument}: {len(coefficient_draws)} bootstrap replicates used, {skipped} skipped as rank-deficient")
        # Both CPS starts share one set of draws, so their bands differ only by start shares.
        for start_key in [key for key in starts if key[0] == instrument]:
            band_frames.append(bootstrap_bands(estimate, starts[start_key], adoption_fits, coefficient_draws, start_basis=start_key[1]))
            stability_frames.append(leave_one_period_out(estimate, starts[start_key], adoption_fits, start_basis=start_key[1]))

    keys = ["instrument", "start_basis", "unemployment_scenario", "adoption_fit", "as_of", "soc_major"]
```

`allocate_to_occupations` needs no change — OEWS has only the raw start.

Module docstring Outputs: add `• data/output/cps_seasonal_factors.csv`, and a sentence that CPS projects from a raw and a seasonally adjusted latest-month start (`start_basis`).

- [x] **Step 5: Run the tests**

Run: `uv run pytest tests/test_forecast_composition.py -v`
Expected: PASS.

- [x] **Step 6: Document the outputs**

In `docs/outputs.md`: add a row for `cps_seasonal_factors.csv` (`forecast_composition.py`, `cps_seasonal_factors_or_none` via `cps_panel.seasonal_factors`) — one row per SOC major group × calendar month with `factor` and `n_years`; ratio to a centred 2×12 moving average over 2022 onward, scaled to average 1; absent when any factor rests on fewer than 3 years, in which case CPS projects from the raw start only. In the `forecast_sector_paths.csv` and `forecast_sector_stability.csv` rows, add that a `start_basis` column distinguishes CPS's `raw` latest-month start from its `seasonally_adjusted` one (OEWS is always `raw`).

- [x] **Step 7: Commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add forecast_composition.py tests/test_forecast_composition.py docs/outputs.md docs/superpowers/plans/2026-10-02-cps-monthly-backfill.md
git commit -m "Project CPS from both a raw and a seasonally adjusted latest-month start"
```

---

### Task 6: Charts — filter to raw, and the start-basis comparison

**Files:**
- Modify: `forecast_charts.py` — `CHART_NAMES`, new `plot_cps_start_basis`, `draw_all`; docstring
- Modify: `forecast_composition.py` — `run_stage`'s `draw_all` call
- Modify: `tests/test_forecast_charts.py`

**Interfaces:**
- Consumes: `start_basis` column (Task 5); `cps_seasonal_factors.csv` schema (Task 4/5).
- Produces: `CHART_NAMES` gains `"forecast_cps_start_basis.png"` (7 entries); `draw_all(period_slopes_df, decomposition_df, btos_series_df, adoption_fits_df, sector_paths_df, demand_shares_df, seasonal_factors_df=None, output_dir=...) -> list[str]` — returns only charts actually written.

- [ ] **Step 1: Update and add tests**

In `tests/test_forecast_charts.py`, inside `synthetic_inputs`, replace the whole `path_rows = []` loop (through `sector_paths = pd.DataFrame(path_rows)`) so CPS gets both bases and OEWS only raw:

```python
    path_rows = []
    for instrument, labels, bases in (
        ("oews", ["2025-05", "2030-05"], ("raw",)),
        ("cps", ["2026-09", "2030-12"], ("raw", "seasonally_adjusted")),
    ):
        for start_basis in bases:
            basis_shift = 0.002 if start_basis == "seasonally_adjusted" else 0.0
            for scenario in ("steady", "mild_recession"):
                for fit in ("linear", "logistic"):
                    for label_index, label in enumerate(labels):
                        for sector_index, sector in enumerate(SECTORS):
                            share = 0.25 + (label_index * 0.01 + basis_shift) * (sector_index - 1.5)
                            path_rows.append(
                                {
                                    "instrument": instrument,
                                    "start_basis": start_basis,
                                    "unemployment_scenario": scenario,
                                    "adoption_fit": fit,
                                    "as_of": label,
                                    "soc_major": sector,
                                    "share": share,
                                    "employment": share * 1000,
                                    "share_p5": share - 0.005,
                                    "share_p95": share + 0.005,
                                    "noise_low": share - 0.01,
                                    "noise_high": share + 0.01,
                                }
                            )
    sector_paths = pd.DataFrame(path_rows)
```

Then make `synthetic_inputs` also return `seasonal_factors` (replacing its `return` line):

```python
seasonal_factors = pd.DataFrame(
    [
        {"soc_major": sector, "calendar_month": month, "factor": 1.0 + 0.01 * (month - 6.5) / 6, "n_years": 3}
        for sector in SECTORS
        for month in range(1, 13)
    ]
)
return periods, decomposition, btos_series, fits, sector_paths, demand_shares, seasonal_factors
```

Update the two existing tests and add one:

```python
def test_draw_all_writes_every_chart(tmp_path):
    written = draw_all(*synthetic_inputs(), output_dir=str(tmp_path))
    assert sorted(written) == sorted(CHART_NAMES)
    for chart_name in CHART_NAMES:
        assert (tmp_path / chart_name).stat().st_size > 0
    assert (tmp_path / "chart_manifest.json").exists()


def test_draw_all_handles_oews_only(tmp_path):
    periods, decomposition, btos_series, fits, sector_paths, demand_shares, seasonal_factors = synthetic_inputs()
    oews_only = [frame[frame["instrument"] == "oews"] for frame in (periods, decomposition, sector_paths)]
    written = draw_all(oews_only[0], oews_only[1], btos_series, fits, oews_only[2], demand_shares, None, output_dir=str(tmp_path))
    assert sorted(written) == sorted(name for name in CHART_NAMES if name != "forecast_cps_start_basis.png")


def test_existing_charts_ignore_the_adjusted_start(tmp_path):
    """Dropping the adjusted rows must not change any of the six original charts."""
    inputs = list(synthetic_inputs())
    with_adjusted = draw_all(*inputs, output_dir=str(tmp_path / "with"))
    inputs[4] = inputs[4][inputs[4]["start_basis"] == "raw"]
    without_adjusted = draw_all(*inputs[:6], None, output_dir=str(tmp_path / "without"))
    for chart_name in without_adjusted:
        assert (tmp_path / "with" / chart_name).read_bytes() == (tmp_path / "without" / chart_name).read_bytes()
    assert "forecast_cps_start_basis.png" in with_adjusted
```

If the byte comparison is flaky because matplotlib embeds a timestamp, compare `chart_manifest.json` fingerprints for the six names instead (read both manifests with `json.load` and compare the entries).

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_forecast_charts.py -v`
Expected: FAIL — `draw_all` takes no `seasonal_factors_df`; `CHART_NAMES` lacks the new chart.

- [ ] **Step 3: Implement**

In `forecast_charts.py`: append `"forecast_cps_start_basis.png"` to `CHART_NAMES`; add

```python
START_BASIS_LABELS = {"raw": "Raw latest month", "seasonally_adjusted": "Seasonally adjusted latest month"}
START_BASIS_COLORS = {"raw": "#2a78d6", "seasonally_adjusted": "#eb6834"}  # categorical slots 1 and 2
```

and the chart:

```python
def plot_cps_start_basis(sector_paths_df, seasonal_factors_df, output_dir):
    """Per sector, the 2030 change from the raw and from the seasonally adjusted CPS start."""
    scenario, fit = REFERENCE_SCENARIO
    cps_df = sector_paths_df[sector_paths_df["instrument"] == "cps"]
    changes = {basis: _final_change(cps_df[cps_df["start_basis"] == basis], "cps", scenario, fit)["change"] for basis in START_BASIS_LABELS}
    order = changes["raw"].sort_values().index
    positions = np.arange(len(order))
    start_label, end_label = _start_and_end(cps_df)
    month_factors_df = seasonal_factors_df[seasonal_factors_df["calendar_month"] == int(start_label[5:7])]
    month_factors = month_factors_df.set_index(month_factors_df["soc_major"].astype(str).str.zfill(2))["factor"]

    figure, axis = plt.subplots(figsize=(10, 9))
    for basis, offset in (("raw", -0.18), ("seasonally_adjusted", 0.18)):
        axis.barh(
            positions + offset, changes[basis].reindex(order), height=0.34, color=START_BASIS_COLORS[basis], label=START_BASIS_LABELS[basis]
        )
    axis.set_yticks(positions, [f"{_sector_label(code)}  (factor {month_factors.get(code, np.nan):.3f})" for code in order])
    axis.axvline(0, color="#999999", linewidth=0.8)
    axis.set_xlabel(f"Change in employment share, {start_label} → {end_label} (percentage points)")
    axis.legend(fontsize=8, loc="lower right")
    start_month_name = pd.Period(start_label, freq="M").strftime("%B")
    axis.set_title(
        f"CPS projection: raw vs seasonally adjusted {start_label} start — steady unemployment, logistic adoption\n"
        f"Factor = the sector's {start_month_name} seasonal factor; above 1 means {start_month_name} runs seasonally high.\n{PROJECTION_NOTE}",
        fontsize=10,
    )
    figure.tight_layout()
    save_figure(figure, os.path.join(output_dir, CHART_NAMES[6]), dpi=150)
    plt.close(figure)
```

Replace `draw_all`:

```python
def draw_all(
    period_slopes_df,
    decomposition_df,
    btos_series_df,
    adoption_fits_df,
    sector_paths_df,
    demand_shares_df,
    seasonal_factors_df=None,
    output_dir="data/output/visualizations",
) -> list[str]:
    """Draw every forecast chart; returns the file names written.

    The six original charts show the raw start only. The start-basis comparison is
    drawn only when a seasonally adjusted CPS start exists.
    """
    os.makedirs(output_dir, exist_ok=True)
    raw_paths_df = sector_paths_df[sector_paths_df["start_basis"] == "raw"]
    plot_slope_history(period_slopes_df, decomposition_df, output_dir)
    plot_btos_adoption(btos_series_df, adoption_fits_df, output_dir)
    plot_sector_change_2030(raw_paths_df, output_dir)
    plot_sector_paths(raw_paths_df, output_dir)
    plot_demand_type_shares(demand_shares_df, output_dir)
    plot_scenario_comparison(raw_paths_df, output_dir)
    written = list(CHART_NAMES[:6])
    if seasonal_factors_df is not None and (sector_paths_df["start_basis"] == "seasonally_adjusted").any():
        plot_cps_start_basis(sector_paths_df, seasonal_factors_df, output_dir)
        written.append(CHART_NAMES[6])
    return written
```

Update the module docstring: "The seven charts …", noting the six show the raw start and the seventh compares starts.

In `forecast_composition.run_stage`, pass the factors to `draw_all` after `demand_type_shares(allocation_df)`:

```python
(pd.read_csv(SEASONAL_FACTORS_OUTPUT_PATH, dtype={"soc_major": str}) if ("cps", "seasonally_adjusted") in starts else None,)
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_forecast_charts.py tests/test_forecast_composition.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

The chart's docs page and committed image land in Task 8 together, because the link gate fails on a documented chart with no image.

```bash
git add forecast_charts.py forecast_composition.py tests/test_forecast_charts.py docs/superpowers/plans/2026-10-02-cps-monthly-backfill.md
git commit -m "Chart the raw and seasonally adjusted CPS starts side by side"
```

---

### Task 7: Signal panel endpoints from the OEWS handoff

**Files:**
- Modify: `cps_panel.py` — `year_over_year_month_pairs`
- Modify: `validate_bls.py` — `plot_model_signal_over_time` (~line 463 and its docstring ~line 355)
- Modify: `tests/test_cps.py` — `TestYearOverYearMonthPairs`

**Interfaces:**
- Produces: `year_over_year_month_pairs(panel_df: pd.DataFrame, earliest_year_ago_month: str | None = None) -> list[tuple[str, str]]`.

- [ ] **Step 1: Write the failing test**

Append to `TestYearOverYearMonthPairs`:

```python
    def test_keeps_only_pairs_starting_at_or_after_the_oews_handoff(self):
        rows = [(str(month), "15", 100) for month in pd.period_range("2025-01", "2026-09", freq="M")]
        pairs = year_over_year_month_pairs(_panel(rows), earliest_year_ago_month="2025-05")
        assert [latest for _, latest in pairs] == ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]
        assert all(year_ago >= "2025-05" for year_ago, _ in pairs)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_cps.py::TestYearOverYearMonthPairs -v`
Expected: FAIL — unexpected keyword argument `earliest_year_ago_month`.

- [ ] **Step 3: Implement**

Replace `year_over_year_month_pairs`:

```python
def year_over_year_month_pairs(panel_df: pd.DataFrame, earliest_year_ago_month: str | None = None) -> list[tuple[str, str]]:
    """
    Every (year_ago_month, latest_month) pair the panel can support, oldest first.

    With `earliest_year_ago_month` set to the OEWS reference month, only pairs whose
    window starts at or after the OEWS handoff are kept — a window starting earlier
    overlaps a period OEWS already covers. The surviving pairs measure overlapping
    12-month spans from consecutive endpoints, which is why they are the
    endpoint-sensitivity check in model_signal_over_time.png rather than periods of
    a time series.
    """
    available_months = sorted(panel_df["month"].unique())
    available_month_set = set(available_months)
    return [
        (str(pd.Period(month, freq="M") - 12), month)
        for month in available_months
        if str(pd.Period(month, freq="M") - 12) in available_month_set
        and (earliest_year_ago_month is None or str(pd.Period(month, freq="M") - 12) >= earliest_year_ago_month)
    ]
```

In `validate_bls.plot_model_signal_over_time`, change the pairs line to:

```python
cps_month_pairs = (
    year_over_year_month_pairs(cps_panel_df, oews_reference_month(list(merged_validation_df.columns))) if cps_panel_df is not None else []
)
```

and in its docstring replace "all three points measure the same 12-month span from endpoints two months apart" with "each point is a 12-month window ending in a later month, starting no earlier than the OEWS reference month, so their spread is endpoint sensitivity, not a trend".

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_cps.py tests/test_validate_bls.py -v` (skip the second path if that file does not exist).
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cps_panel.py validate_bls.py tests/test_cps.py docs/superpowers/plans/2026-10-02-cps-monthly-backfill.md
git commit -m "Start the CPS signal endpoints at the OEWS handoff month"
```

---

### Task 8: Backfill run, seed promotion, and the new chart's page

**Files:**
- Modify: `seeds/cps_a19_panel.csv`
- Create: `docs/charts/forecast_cps_start_basis.md`
- Modify: `docs/outputs.md` (row for `forecast_cps_start_basis.png`), `docs/charts/images/*` (stale images + `chart_manifest.json`)

- [ ] **Step 1: Fetch** (outside the sandbox — network and headless Chrome)

```bash
uv run download_cps_history.py
node download_cps.js
```

Expected: `80 months, 2020-01 → 2026-09`, then `Saved .../table_a19.html`.

- [ ] **Step 2: Run the pipeline** (outside the sandbox)

```bash
uv run main.py 2>&1 | tee "$TMPDIR/pipeline_run.txt"
```

Expected: exit 0; the forecast stage prints the 22 × 12 factor table and writes `cps_seasonal_factors.csv`; no "A-19 page disagrees" error; no "seasonally adjusted start skipped".

- [ ] **Step 3: Verify and promote the seed**

```bash
uv run python - <<'EOF'
import pandas as pd
from cps_panel import PANEL_DTYPES
new = pd.read_csv("data/output/cps_a19_panel.csv", dtype=PANEL_DTYPES)
old = pd.read_csv("seeds/cps_a19_panel.csv", dtype=PANEL_DTYPES)
print(len(new), new["month"].min(), new["month"].max(), "2025-10" in set(new["month"]))
joined = old.merge(new, on=["month", "soc_major"], suffixes=("_old", "_new"))
assert len(joined) == len(old) and (joined["employed_thousands_old"] == joined["employed_thousands_new"]).all()
EOF
cp data/output/cps_a19_panel.csv seeds/
```

Expected: `1760 2020-01 2026-09 False`, and no assertion error (every previously committed value unchanged).

- [ ] **Step 4: Refresh charts**

Run: `uv run check_charts.py`. For each `stale image` it lists, and for `forecast_cps_start_basis.png`:
`cp data/output/visualizations/<chart>.png docs/charts/images/` then `cp data/output/visualizations/chart_manifest.json docs/charts/images/`.

- [ ] **Step 5: Write the chart page and outputs row**

Use the `record-measured-result` skill for every figure. Create `docs/charts/forecast_cps_start_basis.md` following the structure of `docs/charts/forecast_sector_change_2030.md`: what it shows (two bars per sector, reference scenario, start month), how to read the factor in each label, the measured result (the largest raw-vs-adjusted gaps and whether any sector changes sign, from `forecast_sector_paths.csv` filtered to `as_of == "2030-12"`), and that the raw start remains primary. Add the `docs/outputs.md` row for `forecast_cps_start_basis.png`.

- [ ] **Step 6: Gate and commit**

Run: `uv run check_charts.py` — expected: no stale, missing, undocumented or broken-link errors. Run: `uv run pytest tests/ -q` — expected: all pass. Dispatch the `claims-auditor` agent on `docs/charts/forecast_cps_start_basis.md`; fix every mismatch it reports.

```bash
git add seeds/cps_a19_panel.csv docs/charts/forecast_cps_start_basis.md docs/outputs.md docs/charts/images docs/superpowers/plans/2026-10-02-cps-monthly-backfill.md
git commit -m "Backfill the A-19 seed to 2020-01 and document the start-basis chart"
```

---

### Task 9: Bring the results docs up to date

**Files:**
- Modify: `docs/framework.md` (§ Composition Forecast, ~lines 1170–1260), `docs/charts/forecast_sector_change_2030.md`, `docs/charts/cps_model_vs_actual.md`, `docs/charts/cps_2026_direction.md`, `docs/charts/composition_model_signal_over_time_cps.md`, `docs/outputs.md` (`cps_occupation_panel.csv` row's "2026 currently holds 8 months"; `cps_a19_panel.csv` row), `docs/seeds.md` (cps_a19 paragraph), `CLAUDE.md` (BLS downloads paragraph and seeds table row), `docs/cps_data_expansion.md` (status line)

- [ ] **Step 1: Find every stale figure**

Run: `grep -rn -E "Aug(ust)? 2026|2026-08|Apr 2025|Jan–Aug|8 months|six months|two months" docs/*.md docs/charts/*.md README.md CLAUDE.md`
Every hit is either updated in Step 2 or left with a reason recorded in the Deviations log (some, such as the IPUMS rollup's 8 months, are still true).

- [ ] **Step 2: Update the prose**

Use the `record-measured-result` skill for every number. Content to carry:
- `framework.md` § Composition Forecast: the CPS start is September 2026; report both starts in the 2030 table (raw primary, adjusted alongside) and state the largest raw-vs-adjusted difference; the CPS excluded period reads "2026 averages 8 months" and comes from the IPUMS panel.
- `cps_model_vs_actual.md`, `cps_2026_direction.md`: since-OEWS window is now May 2025 → Sep 2026; year-over-year Sep 2025 → Sep 2026; new r/p values from the run log.
- `composition_model_signal_over_time_cps.md`: CPS endpoints are May–Sep 2026; April dropped and why.
- `docs/seeds.md` and `CLAUDE.md`: the A-19 seed is built from the BLS API (`download_cps_history.py`, 2020-01 onward, October 2025 absent), the page is a cross-check; `download_cps.js` is still needed for that check. Update the seeds-table row's "Refreshed by" to `every run (BLS API history + A-19 page cross-check)`.
- `docs/cps_data_expansion.md`: status line → "Steps 1–4 implemented (2026-10-02, `docs/superpowers/plans/2026-10-02-cps-monthly-backfill.md`); step 5 (unemployment by occupation) not started." Leave the analysis intact.

- [ ] **Step 3: Gate**

Dispatch the `claims-auditor` agent on every file changed in Step 2, and the `inference-reviewer` agent on the `framework.md` section and the CPS chart pages. Fix every finding. Run `uv run check_charts.py` and `uv run pytest tests/ -q`.

- [ ] **Step 4: Commit**

```bash
git add docs CLAUDE.md README.md docs/superpowers/plans/2026-10-02-cps-monthly-backfill.md
git commit -m "Update CPS results and data-source docs for the backfilled panel"
```

---

### Task 10: The monthly update skill

**Files:**
- Create: `.claude/skills/update-cps-monthly/SKILL.md` (the Bash sandbox denies writes under `.claude/skills`; use the Write tool)

- [ ] **Step 1: Write the skill**

```markdown
---
name: update-cps-monthly
description: Use after a BLS Employment Situation release (first Friday of the month, sometimes the second) to pull the new CPS month into the A-19 panel and the ten-group occupation panel, re-run the CPS-dependent stages, promote the seeds, and update every dated figure — or when asked whether new monthly CPS data is out.
---

# Monthly CPS update

The CPS forecast and validation charts move forward one month per Employment
Situation release. This is the whole routine; skipping a step leaves seeds, charts
and prose describing different months.

## 1. Is the month out?

The release lands at 8:30 ET on the first Friday (second when the first falls too
early in the month). Check the API directly — it is the source:

    uv run python -c "from download_cps_history import fetch_history_payload, parse_api_payload; print(parse_api_payload(fetch_history_payload())['month'].max())"

Compare with `tail -1 seeds/cps_a19_panel.csv`. Same month → stop; nothing to do.
Must run outside the Bash sandbox (api.bls.gov).

## 2. Fetch

Outside the sandbox — headless Chrome crashes inside it (crashpad socket error):

    uv run download_cps_history.py
    node download_cps.js

A `ValueError` saying the A-19 page disagrees with the BLS API is a real finding:
a series ID moved or one product was revised. Stop and report it; never bypass it.

## 3. Re-run

    uv run main.py validate composition forecast

`composition` re-fetches the ten-group occupation series. Its BLS API cache expires
current-year entries after 24 hours, so a run the same day as an earlier one can
still serve the previous month: if `cps_occupation_panel.csv`'s latest year reports
one month fewer than the A-19 panel, delete `data/raw/bls_api/*_<this year>.json`
and re-run `composition forecast`.

## 4. Promote the seeds

    cp data/output/cps_a19_panel.csv seeds/

`seeds/cps_occupation_panel.csv` is three columns (`year, cps_group,
employed_thousands`); `data/output/cps_occupation_panel.csv` adds
`months_observed`. Replace only the current year's ten rows in the seed — copying
the whole file rewrites every row.

Verify both diffs touch only the new month / current year.

## 5. Charts

    uv run check_charts.py

Copy each stale image and `chart_manifest.json` from
`data/output/visualizations/` to `docs/charts/images/`.

## 6. Dated figures

    grep -rn -E "<previous month name> 20[0-9]{2}|<previous YYYY-MM>" docs README.md

Update each with the `record-measured-result` skill — the CPS chart pages, the
`docs/framework.md` § Composition Forecast table (both `start_basis` rows), and the
`docs/outputs.md` month counts. Then dispatch `claims-auditor` on every changed doc,
and `inference-reviewer` if a sign or significance verdict changed.

## 7. Commit

One commit for seeds, one for charts and docs. `uv run pytest tests/ -q` first.

## What does not move

The CPS slope is fitted on `cps_major_rollup_trends.csv`, built from the IPUMS
detailed panel — a local-only build. Monthly A-19 data never reaches it, so the
decomposition coefficients and the excluded-period label ("2026 averages N months")
stay put until the IPUMS panel is rebuilt. A change there in a monthly update is a
bug.
```

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/update-cps-monthly/SKILL.md docs/superpowers/plans/2026-10-02-cps-monthly-backfill.md
git commit -m "Add the monthly CPS update skill"
```

---

## Deviations log

**Task 1, Step 6 (fix round 1):** `uv run download_cps_history.py` placed LAST in the Makefile `download-data` recipe (after `uv run download_dws.py`) instead of before `node download_cps.js`. Reason: the plan's ordering caused a local API failure to abort later downloads (`node download_cps.js` and `uv run download_dws.py`), breaking the entire download-data target; moving it to the end preserves both fetchers' ability to run. The cross-check (A-19 page against API history) happens in the pipeline (`cps_panel.load_cps_panel`), not in the download stage, so download order is irrelevant.
