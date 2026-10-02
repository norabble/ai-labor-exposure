# Decomposed-Slope Composition Forecast Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Project sector (and, by allocation, occupation) employment composition from the latest OEWS and CPS data to 2030, using the dynamic model's score unchanged and a slope decomposition `β_t = β_structural + β_cycle·ΔU_t + β_AI·A_t` estimated from history.

**Architecture:** `btos_adoption.py` owns the Census BTOS AI-use series (fetch, seed merge, spliced growth fits). `forecast_composition.py` owns the four estimation/projection stages and writes every CSV. `forecast_charts.py` draws the six charts from those frames. A new `forecast` pipeline stage runs after `composition`.

**Tech Stack:** Python 3, pandas, numpy, scipy (`stats`, `optimize.curve_fit`), matplotlib via `chart_manifest.save_figure`, pytest, requests.

**Spec:** `docs/superpowers/specs/2026-10-02-decomposed-slope-forecast-design.md`

## Global Constraints

- The dynamic model is not modified; the score is `net_employment_change` from `data/output/occupation_dynamic_model_report.csv`.
- Composition only: total employment held at its start-date level; no total-employment forecast, no sector trend extrapolation.
- COVID periods are `composition_era_validation.COVID_PERIODS` as is (`2019_2020`, `2020_2021`).
- OEWS SOC-revision periods `2009_2010` and `2018_2019` are excluded from the main Stage 2 fit and included in a sensitivity row.
- CPS period `2025_2026` is excluded (2026 averages Jan–Aug only).
- `A_t = 0` for every period ending in 2022 or earlier; Stage 2 uses the **logistic** fit's annual mean, with every other accepted fit as a sensitivity row.
- Unemployment scenarios: **steady** = 0 every year; **mild recession** = +1.5 pp in 2027, −0.75 pp in 2028 and 2029, 0 in 2030.
- Bootstrap: 2,000 replicates, band = 5th–95th percentile.
- Occupation output is an **allocation** and is labelled as one everywhere.
- Every chart goes through `chart_manifest.save_figure`; every new output gets a `docs/outputs.md` row in the same commit; every new chart gets `docs/charts/<name>.md`.
- Coding standards: no generic abbreviations (`df`, `res`, `tmp`, `val`), domain names, a module docstring on every new file (ruff `D100`).
- When a step says "append" and its snippet starts with `import`/`from … import` lines, those lines go into the file's top import block (merged with existing imports), not mid-file — ruff `E402`/`I` would reject them.
- Run Python as `uv run …` (if `uv` cannot write its cache in a sandbox, `.venv/bin/python …` is equivalent).
- Tick each task's boxes in this file in the same commit as that task's code; record any departure in the Deviations log at the end.

## Review Focus

1. **Sector codes read as integers in one table and strings in another** — `bls_sector_trends.csv` reads `soc_major` as int, the report's `OCC_CODE[:2]` is a string; a join must not silently produce NaN scores. Expected: every table is normalised through `sector_code()`, and a sector with no score raises. *(Test: Task 3 `test_align_sectors_raises_on_missing_score`, `test_sector_code_normalises_ints_and_strings`.)*
2. **The next OEWS release renames `TOT_EMP_2025` to `TOT_EMP_2026`** — expected: the report's employment column is detected, not hard-coded, and two candidate columns raise. *(Test: Task 3 `test_report_employment_column_detects_year`.)*
3. **The BLS API is unreachable, so ΔU is unavailable** — expected: the stage warns and skips, like `composition_era_validation.run`, never crashes the pipeline. *(Test: Task 5 `test_run_stage_skips_without_unemployment`.)*
4. **A bootstrap replicate draws no AI-era period** — the AI term is then unidentified. Expected: the replicate is skipped and counted, not crashed on and not silently fitted with a zero AI term. *(Test: Task 8 `test_bootstrap_skips_rank_deficient_replicates`.)*
5. **The latest A-19 month is missing a sector** — expected: raise, never renormalise over 21 sectors as if that were the economy. *(Test: Task 7 `test_cps_start_shares_requires_every_sector`.)*

---

### Task 1: BTOS AI-use series — parse, merge, fetch, seed

**Files:**
- Create: `btos_adoption.py`
- Create: `seeds/btos_ai_use.csv`
- Create: `tests/test_btos_adoption.py`
- Modify: `Makefile` (target `download-data`)
- Modify: `.github/workflows/release.yml` (download steps, after "Download O*NET, Anthropic, and Eloundou source data")

**Interfaces:**
- Produces: `parse_percent(cell) -> float`, `wording_of(question_text: str) -> str`, `parse_btos_workbook(workbook_path) -> pd.DataFrame` (columns `SERIES_COLUMNS = ["smpdt", "ref_end", "wording", "ai_use", "std_error"]`; `ai_use`/`std_error` are fractions), `merge_with_seed(seed_df, fetched_df) -> pd.DataFrame`, `load_series() -> pd.DataFrame`, `write_seed(workbook_paths: list[str]) -> pd.DataFrame`, `download_workbook() -> None`; constants `WORDING_PRODUCTION = "production"`, `WORDING_ANY_FUNCTION = "any_function"`, `SEED_PATH`, `RAW_WORKBOOK_PATH`, `SERIES_OUTPUT_PATH`.

- [x] **Step 1: Write the failing tests**

```python
"""
test_btos_adoption.py
─────────────────────
Tests for btos_adoption.py — the Census BTOS AI-use series that supplies the
forecast's adoption driver A_t, and its spliced growth fits.

Parsing is tested against small synthetic workbooks written with the same sheet
and column layout as census.gov's National.xlsx, so no network is needed.
"""

import numpy as np
import pandas as pd
import pytest

import btos_adoption
from btos_adoption import (
    SERIES_COLUMNS,
    WORDING_ANY_FUNCTION,
    WORDING_PRODUCTION,
    merge_with_seed,
    parse_btos_workbook,
    parse_percent,
    wording_of,
)

OLD_QUESTION = "In the last two weeks, did this business use Artificial Intelligence (AI) in producing goods or services?"
NEW_QUESTION = "In the last two weeks, did this business use Artificial Intelligence (AI) in any of its business functions?"


def write_workbook(path, question_text, values_by_smpdt, errors_by_smpdt, ref_end_by_smpdt):
    """Write a minimal BTOS-shaped workbook: three sheets, smpdt as column headers."""
    smpdt_columns = list(values_by_smpdt)
    estimates_df = pd.DataFrame(
        [
            {"Question ID": "6", "Question": "Hours?", "Answer ID": "1", "Answer": "Yes", **{c: "50.0%" for c in smpdt_columns}},
            {"Question ID": "7", "Question": question_text, "Answer ID": "1", "Answer": "Yes", **values_by_smpdt},
            {"Question ID": "7", "Question": question_text, "Answer ID": "2", "Answer": "No", **{c: "80.0%" for c in smpdt_columns}},
        ]
    )
    errors_df = estimates_df.copy()
    for column in smpdt_columns:
        errors_df.loc[1, column] = errors_by_smpdt[column]
    dates_df = pd.DataFrame({"Smpdt": list(ref_end_by_smpdt), "Ref End": list(ref_end_by_smpdt.values())})
    with pd.ExcelWriter(path) as writer:
        estimates_df.to_excel(writer, sheet_name="Response Estimates", index=False)
        errors_df.to_excel(writer, sheet_name="Response Standard Errors", index=False)
        dates_df.to_excel(writer, sheet_name="Collection and Reference Dates", index=False)


class TestParsing:
    def test_parse_percent_converts_and_blanks(self):
        assert parse_percent("9.7%") == pytest.approx(0.097)
        assert np.isnan(parse_percent("."))
        assert np.isnan(parse_percent(np.nan))

    def test_wording_of_labels_both_wordings(self):
        assert wording_of(OLD_QUESTION) == WORDING_PRODUCTION
        assert wording_of(NEW_QUESTION) == WORDING_ANY_FUNCTION

    def test_wording_of_raises_on_unknown(self):
        with pytest.raises(ValueError, match="Unrecognised BTOS AI-use wording"):
            wording_of("Did this business use robots?")

    def test_parse_workbook_reads_yes_row_with_dates(self, tmp_path):
        workbook_path = tmp_path / "btos.xlsx"
        write_workbook(
            workbook_path,
            NEW_QUESTION,
            {"202602": "18.2%", "202601": "17.7%", "202526": "."},
            {"202602": "0.30%", "202601": "0.25%", "202526": "."},
            {"202526": "12/14/2025", "202601": "12/28/2025", "202602": "01/11/2026"},
        )
        series_df = parse_btos_workbook(workbook_path)
        assert list(series_df.columns) == SERIES_COLUMNS
        assert list(series_df["smpdt"]) == ["202601", "202602"]  # "." dropped, sorted by date
        assert series_df["ai_use"].tolist() == pytest.approx([0.177, 0.182])
        assert series_df["std_error"].tolist() == pytest.approx([0.0025, 0.0030])
        assert (series_df["wording"] == WORDING_ANY_FUNCTION).all()
        assert series_df["ref_end"].iloc[0] == pd.Timestamp("2025-12-28")

    def test_parse_workbook_raises_when_a_date_is_missing(self, tmp_path):
        workbook_path = tmp_path / "btos.xlsx"
        write_workbook(workbook_path, NEW_QUESTION, {"202602": "18.2%"}, {"202602": "0.30%"}, {"202601": "12/28/2025"})
        with pytest.raises(ValueError, match="no reference date"):
            parse_btos_workbook(workbook_path)


class TestMerge:
    def test_fetched_rows_replace_seed_rows_and_new_rows_append(self):
        seed_df = pd.DataFrame(
            {
                "smpdt": ["202517", "202601"],
                "ref_end": pd.to_datetime(["2025-08-17", "2025-12-28"]),
                "wording": [WORDING_PRODUCTION, WORDING_ANY_FUNCTION],
                "ai_use": [0.097, 0.170],
                "std_error": [0.0016, 0.0025],
            }
        )
        fetched_df = pd.DataFrame(
            {
                "smpdt": ["202601", "202602"],
                "ref_end": pd.to_datetime(["2025-12-28", "2026-01-11"]),
                "wording": [WORDING_ANY_FUNCTION, WORDING_ANY_FUNCTION],
                "ai_use": [0.177, 0.182],
                "std_error": [0.0025, 0.0030],
            }
        )
        merged_df = merge_with_seed(seed_df, fetched_df)
        assert list(merged_df["smpdt"]) == ["202517", "202601", "202602"]
        assert merged_df.loc[merged_df["smpdt"] == "202601", "ai_use"].item() == pytest.approx(0.177)

    def test_committed_seed_has_both_wordings(self):
        seed_df = pd.read_csv(btos_adoption.SEED_PATH, dtype={"smpdt": str})
        assert set(seed_df["wording"]) == {WORDING_PRODUCTION, WORDING_ANY_FUNCTION}
        assert seed_df["ai_use"].between(0, 1).all()
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_btos_adoption.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'btos_adoption'`

- [x] **Step 3: Write `btos_adoption.py` (parsing, merge, fetch)**

```python
"""
btos_adoption.py
────────────────
Census Business Trends and Outlook Survey (BTOS) AI-use series and its growth
fits — the adoption driver A_t in the decomposed-slope composition forecast
(docs/superpowers/specs/2026-10-02-decomposed-slope-forecast-design.md).

BTOS asks a panel of firms every two weeks whether they used AI in the last two
weeks (Question ID 7). The question changed wording at the end of 2025:

  production    "…use AI in producing goods or services?"   2023 cycle 19 → 2025 cycle 17
  any_function  "…use AI in any of its business functions?" 2025 cycle 24 → latest

census.gov's live National.xlsx carries only the new wording, so the old-wording
history lives in the committed seed (seeds/btos_ai_use.csv), first built from the
copy Anthropic republished in Anthropic/EconomicIndex
release_2025_09_15/data/input/BTOS_National.xlsx. Every run merges the latest
fetch onto the seed; promotion of new points back to seeds/ is by hand (cp).

The growth fits place the old wording on the new wording's scale with a fitted
multiplicative splice parameter, rather than assuming one.

Inputs:
  • data/raw/btos_national.xlsx — fetched by `python btos_adoption.py`
  • seeds/btos_ai_use.csv       — committed series, both wordings
Outputs:
  • data/output/btos_ai_use.csv
  • data/output/btos_adoption_fits.csv
"""

import os
import sys

import numpy as np
import pandas as pd
import requests

BTOS_URL = "https://www.census.gov/hfp/btos/downloads/National.xlsx"
RAW_WORKBOOK_PATH = "data/raw/btos_national.xlsx"
SEED_PATH = "seeds/btos_ai_use.csv"
SERIES_OUTPUT_PATH = "data/output/btos_ai_use.csv"
FITS_OUTPUT_PATH = "data/output/btos_adoption_fits.csv"

AI_USE_QUESTION_ID = "7"
WORDING_PRODUCTION = "production"
WORDING_ANY_FUNCTION = "any_function"
SERIES_COLUMNS = ["smpdt", "ref_end", "wording", "ai_use", "std_error"]


def parse_percent(cell) -> float:
    """'9.7%' → 0.097. BTOS writes '.' for a period a question was not asked; that becomes NaN."""
    text = str(cell).strip()
    if not text.endswith("%"):
        return np.nan
    return float(text.rstrip("%")) / 100.0


def wording_of(question_text: str) -> str:
    """Label which of the two AI-use wordings a question row carries; anything else raises."""
    lowered = question_text.lower()
    if "producing goods or services" in lowered:
        return WORDING_PRODUCTION
    if "any of its business functions" in lowered:
        return WORDING_ANY_FUNCTION
    raise ValueError(f"Unrecognised BTOS AI-use wording: {question_text!r}")


def _integer_code(value) -> str | None:
    """'7', 7, 7.0 and '202517' all normalise to their integer string; footer text becomes None."""
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return None


def _ai_use_yes_row(sheet_df: pd.DataFrame) -> pd.Series:
    is_ai_use = sheet_df["Question ID"].map(_integer_code) == AI_USE_QUESTION_ID
    is_yes = sheet_df["Answer"].astype(str).str.strip() == "Yes"
    matching_rows = sheet_df[is_ai_use & is_yes]
    if len(matching_rows) != 1:
        raise ValueError(f"Expected exactly one BTOS AI-use 'Yes' row, found {len(matching_rows)}")
    return matching_rows.iloc[0]


def parse_btos_workbook(workbook_path) -> pd.DataFrame:
    """Read the AI-use 'Yes' share, its standard error, and each period's reference end date."""
    estimates_df = pd.read_excel(workbook_path, sheet_name="Response Estimates", dtype=str)
    errors_df = pd.read_excel(workbook_path, sheet_name="Response Standard Errors", dtype=str)
    dates_df = pd.read_excel(workbook_path, sheet_name="Collection and Reference Dates")

    estimate_row = _ai_use_yes_row(estimates_df)
    error_row = _ai_use_yes_row(errors_df)
    wording = wording_of(estimate_row["Question"])

    dates_df = dates_df.assign(smpdt=dates_df["Smpdt"].map(_integer_code)).dropna(subset=["smpdt"])
    ref_end_by_smpdt = dict(zip(dates_df["smpdt"], pd.to_datetime(dates_df["Ref End"], format="mixed")))

    smpdt_columns = [column for column in estimates_df.columns if (code := _integer_code(column)) and len(code) == 6]
    series_rows = [
        {
            "smpdt": _integer_code(column),
            "ref_end": ref_end_by_smpdt.get(_integer_code(column), pd.NaT),
            "wording": wording,
            "ai_use": parse_percent(estimate_row[column]),
            "std_error": parse_percent(error_row.get(column, np.nan)),
        }
        for column in smpdt_columns
    ]
    series_df = pd.DataFrame(series_rows, columns=SERIES_COLUMNS).dropna(subset=["ai_use"])

    undated = series_df.loc[series_df["ref_end"].isna(), "smpdt"].tolist()
    if undated:
        raise ValueError(f"BTOS sample period(s) {undated} have an estimate but no reference date")
    return series_df.sort_values("ref_end").reset_index(drop=True)


def merge_with_seed(seed_df: pd.DataFrame, fetched_df: pd.DataFrame) -> pd.DataFrame:
    """Union the seed and a fresh fetch; a fetched row replaces the seed's row for the same period and wording."""
    combined_df = pd.concat([seed_df, fetched_df], ignore_index=True)
    combined_df["ref_end"] = pd.to_datetime(combined_df["ref_end"])
    combined_df["smpdt"] = combined_df["smpdt"].astype(str)
    combined_df = combined_df.drop_duplicates(subset=["smpdt", "wording"], keep="last")
    return combined_df.sort_values(["ref_end", "wording"]).reset_index(drop=True)[SERIES_COLUMNS]


def load_series() -> pd.DataFrame:
    """The committed seed merged with the latest fetched workbook, if one was downloaded."""
    seed_df = pd.read_csv(SEED_PATH, dtype={"smpdt": str}, parse_dates=["ref_end"])
    if not os.path.exists(RAW_WORKBOOK_PATH):
        print(f"  ⚠ {RAW_WORKBOOK_PATH} not found; using the committed BTOS seed alone.")
        return merge_with_seed(seed_df, seed_df.iloc[0:0])
    return merge_with_seed(seed_df, parse_btos_workbook(RAW_WORKBOOK_PATH))


def write_seed(workbook_paths: list[str]) -> pd.DataFrame:
    """Build seeds/btos_ai_use.csv from one or more workbooks (one-off, local; see docs/seeds.md)."""
    seed_df = pd.DataFrame(columns=SERIES_COLUMNS)
    for workbook_path in workbook_paths:
        seed_df = merge_with_seed(seed_df, parse_btos_workbook(workbook_path))
    seed_df.to_csv(SEED_PATH, index=False, date_format="%Y-%m-%d")
    return seed_df


def download_workbook() -> None:
    """Fetch census.gov's National.xlsx, failing soft under CI like the BLS fetchers."""
    os.makedirs(os.path.dirname(RAW_WORKBOOK_PATH), exist_ok=True)
    print("Downloading Census BTOS national estimates...")
    try:
        response = requests.get(BTOS_URL, timeout=60)
        response.raise_for_status()
    except requests.RequestException as request_error:
        message = f"Could not fetch BTOS: {request_error}"
        if os.environ.get("CI"):
            print(f"  ⚠ {message} Continuing from the committed seed.")
            return
        print(f"  ✗ {message}")
        sys.exit(1)
    with open(RAW_WORKBOOK_PATH, "wb") as workbook_file:
        workbook_file.write(response.content)
    print(f"  ✓ {RAW_WORKBOOK_PATH}")


if __name__ == "__main__":
    download_workbook()
```

- [x] **Step 4: Build the seed from both workbooks**

```bash
uv run btos_adoption.py
curl -sL "https://huggingface.co/datasets/Anthropic/EconomicIndex/resolve/main/release_2025_09_15/data/input/BTOS_National.xlsx" -o "$TMPDIR/btos_production_wording.xlsx"
uv run python -c "import btos_adoption as b; s = b.write_seed(['$TMPDIR/btos_production_wording.xlsx', b.RAW_WORKBOOK_PATH]); print(s.groupby('wording')['ai_use'].agg(['count','min','max']))"
```

Expected: two wordings — `production` ≈ 51 rows, 0.038–0.097; `any_function` ≥ 22 rows, 0.172 upward.

- [x] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_btos_adoption.py -v`
Expected: PASS (7 tests)

- [x] **Step 6: Wire the fetch into `make download-data` and `release.yml`**

In `Makefile`, add the line after `uv run download_data.py`:

```makefile
	uv run btos_adoption.py
```

In `.github/workflows/release.yml`, add after the "Download O*NET, Anthropic, and Eloundou source data" step:

```yaml
      # Census BTOS AI-use series for the forecast stage. Warns rather than fails
      # under CI; seeds/btos_ai_use.csv still carries both question wordings.
      - name: Download Census BTOS AI-use estimates
        run: uv run btos_adoption.py
```

- [x] **Step 7: Commit**

```bash
git add btos_adoption.py seeds/btos_ai_use.csv tests/test_btos_adoption.py Makefile .github/workflows/release.yml docs/superpowers/plans/2026-10-02-decomposed-slope-forecast.md
git commit -m "Add the Census BTOS AI-use series with a two-wording seed"
```

---

### Task 2: Spliced adoption growth fits

**Files:**
- Modify: `btos_adoption.py` (append)
- Modify: `tests/test_btos_adoption.py` (append)

**Interfaces:**
- Consumes: `SERIES_COLUMNS`, `WORDING_PRODUCTION`, `load_series()` (Task 1).
- Produces: `@dataclass AdoptionFit(name: str, parameters: tuple[float, ...], splice_multiplier: float, accepted: bool, rejection_reason: str = "")`; `decimal_years(dates) -> np.ndarray`; `fit_adoption(series_df) -> dict[str, AdoptionFit]`; `evaluate_fit(fit, dates) -> np.ndarray`; `annual_mean_adoption(fit, years: list[int]) -> pd.Series` (index int year); `accepted_fits(fits) -> dict[str, AdoptionFit]`; `fits_table(fits) -> pd.DataFrame`; `run_adoption() -> tuple[pd.DataFrame, dict[str, AdoptionFit]]`; constants `GROWTH_FORMS`, `FORECAST_HORIZON_END = pd.Timestamp("2030-12-01")`.

- [x] **Step 1: Write the failing tests** (append to `tests/test_btos_adoption.py`)

```python
from btos_adoption import AdoptionFit, annual_mean_adoption, evaluate_fit, fit_adoption, fits_table


def synthetic_series(splice_multiplier=0.55):
    """Logistic adoption on the new-wording scale; old-wording points scaled down by the splice."""
    old_dates = pd.date_range("2023-09-10", "2025-08-17", freq="14D")
    new_dates = pd.date_range("2025-11-30", "2026-09-20", freq="14D")
    rows = []
    for dates, wording, multiplier in ((old_dates, WORDING_PRODUCTION, splice_multiplier), (new_dates, WORDING_ANY_FUNCTION, 1.0)):
        years = btos_adoption.decimal_years(pd.Series(dates))
        adoption = 0.7 / (1 + np.exp(-0.6 * (years - 6.0)))
        rows.append(
            pd.DataFrame(
                {
                    "smpdt": [str(i) for i in range(len(dates))],
                    "ref_end": dates,
                    "wording": wording,
                    "ai_use": adoption * multiplier,
                    "std_error": 0.002,
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


class TestGrowthFits:
    def test_logistic_fit_recovers_the_splice(self):
        fits = fit_adoption(synthetic_series(splice_multiplier=0.55))
        assert fits["logistic"].accepted
        assert fits["logistic"].splice_multiplier == pytest.approx(0.55, abs=0.03)

    def test_accepted_fits_are_bounded_and_non_decreasing(self):
        fits = fit_adoption(synthetic_series())
        monthly = pd.Series(pd.date_range("2022-01-01", "2030-12-01", freq="MS"))
        for fit in fits.values():
            if not fit.accepted:
                continue
            adoption = evaluate_fit(fit, monthly)
            assert ((adoption >= 0) & (adoption <= 1)).all(), fit.name
            assert (np.diff(adoption) >= -1e-12).all(), fit.name

    def test_exponential_exceeding_full_adoption_is_rejected(self):
        fast_series = synthetic_series()
        years = btos_adoption.decimal_years(fast_series["ref_end"])
        fast_series["ai_use"] = 0.01 * np.exp(0.9 * years)  # passes 100% well before 2030
        fits = fit_adoption(fast_series)
        assert not fits["exponential"].accepted
        assert "exceeds 100%" in fits["exponential"].rejection_reason

    def test_annual_mean_and_table(self):
        fits = fit_adoption(synthetic_series())
        annual = annual_mean_adoption(fits["logistic"], [2024, 2030])
        assert annual[2030] > annual[2024]
        table = fits_table(fits)
        assert {"fit", "accepted", "splice_multiplier", "month", "adoption"} <= set(table.columns)
        assert table.loc[table["fit"] == "logistic", "month"].max() == pd.Timestamp("2030-12-01")

    def test_failed_fit_is_reported_not_replaced(self, monkeypatch):
        def failing_curve_fit(*args, **kwargs):
            raise RuntimeError("Optimal parameters not found")

        monkeypatch.setattr(btos_adoption, "curve_fit", failing_curve_fit)
        fits = fit_adoption(synthetic_series())
        assert all(not fit.accepted and "did not converge" in fit.rejection_reason for fit in fits.values())
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_btos_adoption.py::TestGrowthFits -v`
Expected: FAIL — `ImportError: cannot import name 'AdoptionFit'`

- [x] **Step 3: Append the fits to `btos_adoption.py`**

Add `from dataclasses import dataclass` and `from scipy.optimize import curve_fit` to the imports, then append:

```python
# ── Growth fits ────────────────────────────────────────────────────────────────

ADOPTION_EPOCH = pd.Timestamp("2022-01-01")
FORECAST_HORIZON_END = pd.Timestamp("2030-12-01")


def decimal_years(dates) -> np.ndarray:
    """Years since 2022-01-01 — the growth forms' time axis."""
    return ((pd.to_datetime(pd.Series(dates)) - ADOPTION_EPOCH).dt.days / 365.25).to_numpy(float)


def linear_form(years, intercept, slope):
    return intercept + slope * years


def logistic_form(years, ceiling, rate, midpoint):
    return ceiling / (1.0 + np.exp(-rate * (years - midpoint)))


def gompertz_form(years, ceiling, displacement, rate):
    return ceiling * np.exp(-displacement * np.exp(-rate * years))


def exponential_form(years, scale, rate):
    return scale * np.exp(rate * years)


# name → (form, initial guess, (lower bounds, upper bounds)). Every bound keeps the
# form non-decreasing (slope, rate ≥ 0) and every ceiling ≤ 1.
GROWTH_FORMS = {
    "linear": (linear_form, [0.0, 0.05], ([-1.0, 0.0], [1.0, 1.0])),
    "logistic": (logistic_form, [0.6, 0.6, 7.0], ([0.0, 0.0, -10.0], [1.0, 5.0, 40.0])),
    "gompertz": (gompertz_form, [0.6, 3.0, 0.2], ([0.0, 0.0, 0.0], [1.0, 50.0, 5.0])),
    "exponential": (exponential_form, [0.05, 0.3], ([0.0, 0.0], [1.0, 5.0])),
}
# The old wording ("producing goods or services") is narrower, so its multiplier onto
# the new wording's scale is expected below 1.
SPLICE_INITIAL = 0.6
SPLICE_BOUNDS = (0.1, 2.0)


@dataclass
class AdoptionFit:
    name: str
    parameters: tuple[float, ...]
    splice_multiplier: float
    accepted: bool
    rejection_reason: str = ""


def fit_adoption(series_df: pd.DataFrame) -> dict[str, AdoptionFit]:
    """Fit every growth form to both wordings at once, with the splice multiplier as a free parameter."""
    years = decimal_years(series_df["ref_end"])
    is_production_wording = (series_df["wording"] == WORDING_PRODUCTION).to_numpy(float)
    observed_adoption = series_df["ai_use"].to_numpy(float)
    horizon_years = decimal_years([FORECAST_HORIZON_END])[0]

    adoption_fits = {}
    for name, (form, initial, (lower, upper)) in GROWTH_FORMS.items():

        def spliced_form(stacked, *parameters, form=form):
            fit_years, production_flag = stacked
            multiplier = np.where(production_flag == 1.0, parameters[-1], 1.0)
            return form(fit_years, *parameters[:-1]) * multiplier

        try:
            fitted_parameters, _ = curve_fit(
                spliced_form,
                np.vstack([years, is_production_wording]),
                observed_adoption,
                p0=[*initial, SPLICE_INITIAL],
                bounds=([*lower, SPLICE_BOUNDS[0]], [*upper, SPLICE_BOUNDS[1]]),
                maxfev=20000,
            )
        except (RuntimeError, ValueError) as fit_error:
            adoption_fits[name] = AdoptionFit(name, (), np.nan, False, f"did not converge: {fit_error}")
            continue

        adoption_fit = AdoptionFit(name, tuple(float(p) for p in fitted_parameters[:-1]), float(fitted_parameters[-1]), True)
        horizon_adoption = float(form(horizon_years, *adoption_fit.parameters))
        if name == "exponential" and horizon_adoption > 1.0:
            adoption_fit.accepted = False
            adoption_fit.rejection_reason = f"exceeds 100% adoption by {FORECAST_HORIZON_END:%Y-%m} ({horizon_adoption:.2f})"
        adoption_fits[name] = adoption_fit
    return adoption_fits


def accepted_fits(adoption_fits: dict[str, AdoptionFit]) -> dict[str, AdoptionFit]:
    return {name: adoption_fit for name, adoption_fit in adoption_fits.items() if adoption_fit.accepted}


def evaluate_fit(adoption_fit: AdoptionFit, dates) -> np.ndarray:
    """Fitted adoption on the new-wording scale, clipped to [0, 1]."""
    form = GROWTH_FORMS[adoption_fit.name][0]
    return np.clip(form(decimal_years(dates), *adoption_fit.parameters), 0.0, 1.0)


def annual_mean_adoption(adoption_fit: AdoptionFit, years: list[int]) -> pd.Series:
    """Mean of the twelve mid-month fitted values in each calendar year."""
    annual_means = {}
    for year in years:
        mid_months = pd.date_range(f"{year}-01-15", periods=12, freq=pd.DateOffset(months=1))
        annual_means[year] = float(evaluate_fit(adoption_fit, mid_months).mean())
    return pd.Series(annual_means, name=f"adoption_{adoption_fit.name}")


def fits_table(adoption_fits: dict[str, AdoptionFit]) -> pd.DataFrame:
    """Parameters plus monthly fitted adoption 2022-01 → 2030-12 per fit; a rejected fit gets one row, month blank."""
    months = pd.Series(pd.date_range(ADOPTION_EPOCH, FORECAST_HORIZON_END, freq="MS"))
    table_frames = []
    for adoption_fit in adoption_fits.values():
        base = {
            "fit": adoption_fit.name,
            "accepted": adoption_fit.accepted,
            "rejection_reason": adoption_fit.rejection_reason,
            "parameters": ";".join(f"{value:.6g}" for value in adoption_fit.parameters),
            "splice_multiplier": adoption_fit.splice_multiplier,
        }
        if adoption_fit.accepted:
            table_frames.append(pd.DataFrame({**base, "month": months, "adoption": evaluate_fit(adoption_fit, months)}))
        else:
            table_frames.append(pd.DataFrame([{**base, "month": pd.NaT, "adoption": np.nan}]))
    return pd.concat(table_frames, ignore_index=True)


def run_adoption() -> tuple[pd.DataFrame, dict[str, AdoptionFit]]:
    """Load the merged series, fit every form, and write both outputs."""
    series_df = load_series()
    series_df.to_csv(SERIES_OUTPUT_PATH, index=False, date_format="%Y-%m-%d")
    adoption_fits = fit_adoption(series_df)
    fits_table(adoption_fits).to_csv(FITS_OUTPUT_PATH, index=False, date_format="%Y-%m-%d")
    for adoption_fit in adoption_fits.values():
        status = "accepted" if adoption_fit.accepted else f"rejected — {adoption_fit.rejection_reason}"
        print(f"  {adoption_fit.name:<12} splice ×{adoption_fit.splice_multiplier:.3f}  {status}")
    return series_df, adoption_fits
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_btos_adoption.py -v`
Expected: PASS (12 tests)

- [x] **Step 5: Smoke-run on the real series**

Run: `uv run python -c "import btos_adoption as b; b.run_adoption()"`
Expected: four lines, logistic/gompertz/linear accepted with splice multipliers between 0.1 and 2.0; `data/output/btos_adoption_fits.csv` written. Record the four splice multipliers in this task's commit message.

- [x] **Step 6: Commit**

```bash
git add btos_adoption.py tests/test_btos_adoption.py docs/superpowers/plans/2026-10-02-decomposed-slope-forecast.md
git commit -m "Fit spliced growth curves to the BTOS AI-use series"
```

---

### Task 3: Stage 1 — sector scores, employment panels, period slopes

**Files:**
- Create: `forecast_composition.py`
- Create: `tests/test_forecast_composition.py`

**Interfaces:**
- Produces: `sector_code(value) -> str`; `report_employment_column(dynamic_report_df) -> str`; `sector_scores(dynamic_report_df) -> pd.Series` (index 2-char sector code, name `"score"`); `sector_employment_panel(sector_trends_df) -> pd.DataFrame` (index sector code, int year columns); `align_sectors(panel_df, scores) -> pd.Series`; `estimate_period_slopes(panel_df, scores, instrument: str, excluded_periods: dict[str, str]) -> pd.DataFrame` with columns `PERIOD_SLOPE_COLUMNS = ["instrument", "period", "start_year", "end_year", "slope", "std_error", "residual_sd", "n_sectors", "is_covid", "excluded_reason"]`; constants `OEWS_EXCLUDED_PERIODS`, `CPS_EXCLUDED_PERIODS`, path constants.

- [x] **Step 1: Write the failing tests**

```python
"""
test_forecast_composition.py
────────────────────────────
Tests for forecast_composition.py — the decomposed-slope composition forecast.

Every statistic is tested against synthetic sectors with a known answer, so a
change in the real data cannot make a broken estimator look right.
"""

import numpy as np
import pandas as pd
import pytest

import forecast_composition
from forecast_composition import (
    align_sectors,
    estimate_period_slopes,
    report_employment_column,
    sector_code,
    sector_employment_panel,
    sector_scores,
)

SECTORS = [f"{code:02d}" for code in range(11, 55, 2)]  # 22 two-digit codes


def synthetic_panel(slope_by_period: dict[int, float], scores: pd.Series, years=range(2000, 2006), noise=0.0, seed=0) -> pd.DataFrame:
    """Sector employment whose relative growth is slope × (score − weighted mean score) each year, plus optional noise.

    Relative growth subtracts total growth, which removes the common 2% and the
    weighted-mean score term, so the Stage 1 OLS slope equals `slope` exactly when noise is 0.
    """
    rng = np.random.default_rng(seed)
    employment = pd.Series(1000.0, index=scores.index)
    columns = {}
    for year in years:
        columns[year] = employment.copy()
        slope = slope_by_period.get(year + 1, 0.0)
        employment = employment * (1.0 + 0.02 + slope * scores + rng.normal(0.0, noise, len(scores)))
    return pd.DataFrame(columns)


@pytest.fixture
def scores():
    return pd.Series(np.linspace(-0.2, 0.2, len(SECTORS)), index=SECTORS, name="score")


class TestStageOneInputs:
    def test_sector_code_normalises_ints_and_strings(self):
        assert sector_code(11) == "11"
        assert sector_code("11") == "11"
        assert sector_code(11.0) == "11"

    def test_report_employment_column_detects_year(self):
        assert report_employment_column(pd.DataFrame(columns=["OCC_CODE", "TOT_EMP_2026"])) == "TOT_EMP_2026"
        with pytest.raises(ValueError, match="exactly one"):
            report_employment_column(pd.DataFrame(columns=["TOT_EMP_2025", "TOT_EMP_2026"]))

    def test_sector_scores_are_employment_weighted(self):
        report_df = pd.DataFrame(
            {
                "OCC_CODE": ["43-1011", "43-9061", "15-1252"],
                "TOT_EMP_2025": [100.0, 300.0, 50.0],
                "net_employment_change": [-0.4, 0.0, 0.16],
            }
        )
        scores = sector_scores(report_df)
        assert scores["43"] == pytest.approx(-0.1)
        assert scores["15"] == pytest.approx(0.16)

    def test_sector_employment_panel_reads_year_columns(self):
        trends_df = pd.DataFrame(
            {"soc_major": [11, 13], "TOT_EMP_2023": [10, 20], "TOT_EMP_2022": [9, 19], "emp_growth_2022_2023": [0.1, 0.05]}
        )
        panel_df = sector_employment_panel(trends_df)
        assert list(panel_df.index) == ["11", "13"]
        assert list(panel_df.columns) == [2022, 2023]

    def test_align_sectors_raises_on_missing_score(self, scores):
        panel_df = pd.DataFrame({2024: 1.0, 2025: 1.0}, index=[*SECTORS, "55"])
        with pytest.raises(ValueError, match="No dynamic-model score"):
            align_sectors(panel_df, scores)


class TestPeriodSlopes:
    def test_recovers_known_slopes(self, scores):
        panel_df = synthetic_panel({2002: 0.05, 2004: -0.03}, scores)
        slopes_df = estimate_period_slopes(panel_df, scores, "oews", {})
        by_period = slopes_df.set_index("period")["slope"]
        assert by_period["2001_2002"] == pytest.approx(0.05, abs=1e-9)
        assert by_period["2003_2004"] == pytest.approx(-0.03, abs=1e-9)
        assert by_period["2000_2001"] == pytest.approx(0.0, abs=1e-9)

    def test_excluded_and_covid_periods_are_flagged_not_dropped(self, scores):
        panel_df = synthetic_panel({}, scores, years=range(2018, 2022))
        slopes_df = estimate_period_slopes(panel_df, scores, "oews", {"2018_2019": "SOC revision level break"})
        flags = slopes_df.set_index("period")
        assert flags.loc["2018_2019", "excluded_reason"] == "SOC revision level break"
        assert bool(flags.loc["2019_2020", "is_covid"])
        assert len(slopes_df) == 3

    def test_skips_non_consecutive_years(self, scores):
        panel_df = synthetic_panel({}, scores, years=range(2000, 2003)).drop(columns=[2001])
        assert estimate_period_slopes(panel_df, scores, "oews", {}).empty
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_forecast_composition.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'forecast_composition'`

- [x] **Step 3: Write `forecast_composition.py` (Stage 1)**

```python
"""
forecast_composition.py
───────────────────────
Decomposed-slope composition forecast to 2030
(docs/superpowers/specs/2026-10-02-decomposed-slope-forecast-design.md).

The dynamic model's sector score is used unchanged. The forecast is built from how
strongly that score has sorted sector employment shares in each historical year:

  Stage 1  relative_growth_s,t = α_t + β_t · score_s           per period, 22 sectors
  Stage 2  β_t = β_structural + β_cycle · ΔU_t + β_AI · A_t     across periods (WLS)
  Stage 3  β_y for 2026–2030 under unemployment and adoption scenarios
  Stage 4  share_s(y+1) = share_s(y) · (1 + β_y · score_s), renormalised

Total employment is held at its start level; only shares move. Each instrument
(OEWS, CPS) is estimated on its own history and drives its own projection. The
occupation output is an allocation of each sector's projected change in proportion
to start-date employment — there is no occupation-level signal to forecast from.

Inputs:
  • data/output/occupation_dynamic_model_report.csv (validate stage)
  • data/output/bls_sector_trends.csv              (analyze stage)
  • data/output/cps_major_rollup_trends.csv        (composition stage)
  • data/output/cps_a19_panel.csv                  (validate stage)
  • BTOS series and fits                           (btos_adoption.py)
  • unemployment rate LNS14000000                  (BLS API, via composition_era_validation)
Outputs:
  • data/output/forecast_period_slopes.csv
  • data/output/forecast_slope_decomposition.csv
  • data/output/forecast_sector_paths.csv
  • data/output/forecast_sector_stability.csv
  • data/output/forecast_occupation_allocation_2030.csv
  • six charts via forecast_charts.py
"""

import re

import numpy as np
import pandas as pd
import scipy.stats as stats

from composition_era_validation import COVID_PERIODS

DYNAMIC_REPORT_PATH = "data/output/occupation_dynamic_model_report.csv"
OEWS_SECTOR_TRENDS_PATH = "data/output/bls_sector_trends.csv"
CPS_SECTOR_TRENDS_PATH = "data/output/cps_major_rollup_trends.csv"
CPS_A19_PANEL_PATH = "data/output/cps_a19_panel.csv"

PERIOD_SLOPES_OUTPUT_PATH = "data/output/forecast_period_slopes.csv"
DECOMPOSITION_OUTPUT_PATH = "data/output/forecast_slope_decomposition.csv"
SECTOR_PATHS_OUTPUT_PATH = "data/output/forecast_sector_paths.csv"
STABILITY_OUTPUT_PATH = "data/output/forecast_sector_stability.csv"
OCCUPATION_OUTPUT_PATH = "data/output/forecast_occupation_allocation_2030.csv"

# SOC revisions move occupations between major groups, which shows up as relative
# growth the score did not cause. Excluded from the main Stage 2 fit, kept in a
# sensitivity row. decompose_fit_strength keeps them — a deliberate departure.
OEWS_EXCLUDED_PERIODS = {"2009_2010": "SOC 2010 revision level break", "2018_2019": "SOC 2018 revision level break"}
# cps_major_rollup_trends.csv's 2026 averages Jan–Aug only.
CPS_EXCLUDED_PERIODS = {"2025_2026": "partial year (2026 averages Jan–Aug)"}

PERIOD_SLOPE_COLUMNS = [
    "instrument",
    "period",
    "start_year",
    "end_year",
    "slope",
    "std_error",
    "residual_sd",
    "n_sectors",
    "is_covid",
    "excluded_reason",
]
EMPLOYMENT_YEAR_COLUMN = re.compile(r"TOT_EMP_(\d{4})")


def sector_code(value) -> str:
    """11, 11.0 and '11' all become '11', so sector joins never silently miss."""
    return f"{int(float(value)):02d}"


def report_employment_column(dynamic_report_df: pd.DataFrame) -> str:
    """The report's single TOT_EMP_<year> column, so a new OEWS vintage needs no code change."""
    employment_columns = [column for column in dynamic_report_df.columns if EMPLOYMENT_YEAR_COLUMN.fullmatch(column)]
    if len(employment_columns) != 1:
        raise ValueError(f"Expected exactly one TOT_EMP_<year> column in the dynamic report, found {employment_columns}")
    return employment_columns[0]


def sector_scores(dynamic_report_df: pd.DataFrame) -> pd.Series:
    """Employment-weighted mean net_employment_change per SOC major group."""
    employment_column = report_employment_column(dynamic_report_df)
    scored_df = dynamic_report_df.dropna(subset=[employment_column, "net_employment_change"]).copy()
    scored_df["soc_major"] = scored_df["OCC_CODE"].astype(str).str[:2].map(sector_code)
    weighted_change = (scored_df["net_employment_change"] * scored_df[employment_column]).groupby(scored_df["soc_major"]).sum()
    sector_employment = scored_df.groupby("soc_major")[employment_column].sum()
    return (weighted_change / sector_employment).rename("score")


def sector_employment_panel(sector_trends_df: pd.DataFrame) -> pd.DataFrame:
    """Sector × year employment from a TOT_EMP_<year> table (bls_sector_trends or cps_major_rollup_trends)."""
    year_by_column = {
        column: int(match.group(1)) for column in sector_trends_df.columns if (match := EMPLOYMENT_YEAR_COLUMN.fullmatch(column))
    }
    panel_df = sector_trends_df[list(year_by_column)].astype(float)
    panel_df.index = sector_trends_df["soc_major"].map(sector_code)
    panel_df.columns = [year_by_column[column] for column in year_by_column]
    return panel_df.sort_index(axis=1)


def align_sectors(panel_df: pd.DataFrame, scores: pd.Series) -> pd.Series:
    """Scores in the panel's sector order; a sector with employment but no score raises."""
    missing_sectors = sorted(set(panel_df.index) - set(scores.index))
    if missing_sectors:
        raise ValueError(f"No dynamic-model score for sector(s) {missing_sectors}")
    return scores.reindex(panel_df.index)


def estimate_period_slopes(panel_df: pd.DataFrame, scores: pd.Series, instrument: str, excluded_periods: dict[str, str]) -> pd.DataFrame:
    """Stage 1: OLS slope of relative share growth on score for every consecutive year pair."""
    aligned_scores = align_sectors(panel_df, scores)
    years = sorted(panel_df.columns)
    slope_rows = []
    for start_year, end_year in zip(years, years[1:]):
        if end_year != start_year + 1:
            continue
        period = f"{start_year}_{end_year}"
        pair_df = panel_df[[start_year, end_year]].dropna()
        if len(pair_df) < 3:
            continue
        sector_growth = pair_df[end_year] / pair_df[start_year] - 1.0
        total_growth = pair_df[end_year].sum() / pair_df[start_year].sum() - 1.0
        relative_growth = sector_growth - total_growth
        period_scores = aligned_scores[pair_df.index]
        regression = stats.linregress(period_scores, relative_growth)
        residuals = relative_growth - (regression.intercept + regression.slope * period_scores)
        slope_rows.append(
            {
                "instrument": instrument,
                "period": period,
                "start_year": start_year,
                "end_year": end_year,
                "slope": regression.slope,
                "std_error": regression.stderr,
                "residual_sd": float(np.std(residuals, ddof=2)),
                "n_sectors": len(pair_df),
                "is_covid": period in COVID_PERIODS,
                "excluded_reason": excluded_periods.get(period, ""),
            }
        )
    return pd.DataFrame(slope_rows, columns=PERIOD_SLOPE_COLUMNS)
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_forecast_composition.py -v`
Expected: PASS (8 tests)

- [x] **Step 5: Commit**

```bash
git add forecast_composition.py tests/test_forecast_composition.py docs/superpowers/plans/2026-10-02-decomposed-slope-forecast.md
git commit -m "Add Stage 1 of the composition forecast: per-period sector slopes"
```

---

### Task 4: Stage 2 — slope decomposition

**Files:**
- Modify: `forecast_composition.py` (append)
- Modify: `tests/test_forecast_composition.py` (append)

**Interfaces:**
- Consumes: `PERIOD_SLOPE_COLUMNS` frames from Task 3; `annual_mean_adoption` from Task 2.
- Produces: `PRE_ADOPTION_LAST_YEAR = 2022`; `DECOMPOSITION_TERMS = ("structural", "cycle", "ai")`; `attach_drivers(period_slopes_df, unemployment_change: pd.Series, adoption_by_year: pd.Series) -> pd.DataFrame` (adds `unemployment_change`, `adoption`); `stage2_input(driven_df, include_excluded: bool = False) -> pd.DataFrame`; `fit_coefficients(stage2_df, terms=DECOMPOSITION_TERMS) -> dict[str, float] | None`; `decompose_slopes(stage2_df) -> pd.DataFrame` with columns `DECOMPOSITION_COLUMNS = ["term", "coefficient", "std_error", "t_statistic", "p_value", "r_squared", "n_periods"]`; `coefficients_from(decomposition_df) -> dict[str, float]` (missing `ai` → 0.0).

- [x] **Step 1: Write the failing tests** (append)

```python
from forecast_composition import (
    attach_drivers,
    coefficients_from,
    decompose_slopes,
    fit_coefficients,
    stage2_input,
)


def synthetic_period_slopes(structural=0.02, cycle=0.01, ai=0.08, noise=0.0, ai_periods=4, seed=0):
    """Periods 2000→2025 whose slopes follow the decomposition exactly (plus optional noise)."""
    rng = np.random.default_rng(seed)
    end_years = np.arange(2001, 2026)
    unemployment = rng.normal(0, 1, len(end_years))
    adoption = np.where(end_years > 2025 - ai_periods, np.linspace(0.05, 0.25, len(end_years)), 0.0)
    slopes = structural + cycle * unemployment + ai * adoption + rng.normal(0, noise, len(end_years))
    periods = [f"{year - 1}_{year}" for year in end_years]
    return pd.DataFrame(
        {
            "instrument": "oews",
            "period": periods,
            "start_year": end_years - 1,
            "end_year": end_years,
            "slope": slopes,
            "std_error": 0.01,
            "residual_sd": 0.02,
            "n_sectors": 22,
            "is_covid": False,
            "excluded_reason": "",
            "unemployment_change": unemployment,
            "adoption": adoption,
        }
    )


class TestStageTwo:
    def test_attach_drivers_zeroes_adoption_through_2022(self):
        slopes_df = pd.DataFrame({"period": ["2021_2022", "2022_2023"], "end_year": [2022, 2023]})
        driven_df = attach_drivers(slopes_df, pd.Series({"2021_2022": -1.0, "2022_2023": -0.3}), pd.Series({2023: 0.12}))
        assert driven_df["adoption"].tolist() == [0.0, 0.12]
        assert driven_df["unemployment_change"].tolist() == [-1.0, -0.3]

    def test_stage2_input_drops_covid_excluded_and_undriven(self):
        driven_df = synthetic_period_slopes()
        driven_df.loc[0, "is_covid"] = True
        driven_df.loc[1, "excluded_reason"] = "SOC revision level break"
        driven_df.loc[2, "unemployment_change"] = np.nan
        assert len(stage2_input(driven_df)) == len(driven_df) - 3
        assert len(stage2_input(driven_df, include_excluded=True)) == len(driven_df) - 2

    def test_recovers_known_coefficients(self):
        coefficients = coefficients_from(decompose_slopes(synthetic_period_slopes(noise=0.0)))
        assert coefficients["structural"] == pytest.approx(0.02, abs=1e-9)
        assert coefficients["cycle"] == pytest.approx(0.01, abs=1e-9)
        assert coefficients["ai"] == pytest.approx(0.08, abs=1e-9)

    def test_without_ai_periods_warns_and_omits_ai(self):
        pre_ai_df = synthetic_period_slopes(ai_periods=0)
        with pytest.warns(UserWarning, match="AI term is not identified"):
            decomposition_df = decompose_slopes(pre_ai_df)
        assert "ai" not in set(decomposition_df["term"])
        assert coefficients_from(decomposition_df)["ai"] == 0.0

    def test_fit_coefficients_returns_none_when_rank_deficient(self):
        assert fit_coefficients(synthetic_period_slopes(ai_periods=0)) is None
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_forecast_composition.py::TestStageTwo -v`
Expected: FAIL — `ImportError: cannot import name 'attach_drivers'`

- [x] **Step 3: Append Stage 2 to `forecast_composition.py`**

Add `import warnings` to the imports, then append:

```python
# ── Stage 2: decompose the slope over time ─────────────────────────────────────

PRE_ADOPTION_LAST_YEAR = 2022
DECOMPOSITION_TERMS = ("structural", "cycle", "ai")
DECOMPOSITION_COLUMNS = ["term", "coefficient", "std_error", "t_statistic", "p_value", "r_squared", "n_periods"]


def attach_drivers(period_slopes_df: pd.DataFrame, unemployment_change: pd.Series, adoption_by_year: pd.Series) -> pd.DataFrame:
    """Add ΔU_t and A_t; A_t is 0 for any period ending in 2022 or earlier."""
    driven_df = period_slopes_df.copy()
    driven_df["unemployment_change"] = driven_df["period"].map(unemployment_change)
    driven_df["adoption"] = [
        0.0 if end_year <= PRE_ADOPTION_LAST_YEAR else adoption_by_year.get(end_year, np.nan) for end_year in driven_df["end_year"]
    ]
    return driven_df


def stage2_input(driven_df: pd.DataFrame, include_excluded: bool = False) -> pd.DataFrame:
    """Periods eligible for Stage 2: never COVID, excluded periods only on request, drivers present."""
    eligible = ~driven_df["is_covid"].astype(bool)
    if not include_excluded:
        eligible &= driven_df["excluded_reason"].fillna("") == ""
    eligible &= driven_df[["unemployment_change", "adoption", "slope", "std_error"]].notna().all(axis=1)
    return driven_df[eligible].reset_index(drop=True)


def _design_matrix(stage2_df: pd.DataFrame, terms) -> np.ndarray:
    columns = {
        "structural": np.ones(len(stage2_df)),
        "cycle": stage2_df["unemployment_change"].to_numpy(float),
        "ai": stage2_df["adoption"].to_numpy(float),
    }
    return np.column_stack([columns[term] for term in terms])


def _weighted_least_squares(design_matrix: np.ndarray, slopes: np.ndarray, weights: np.ndarray) -> np.ndarray:
    root_weights = np.sqrt(weights)
    coefficients, *_ = np.linalg.lstsq(design_matrix * root_weights[:, None], slopes * root_weights, rcond=None)
    return coefficients


def fit_coefficients(stage2_df: pd.DataFrame, terms=DECOMPOSITION_TERMS) -> dict[str, float] | None:
    """Coefficients only, or None when the design is rank-deficient — the bootstrap's fast path."""
    design_matrix = _design_matrix(stage2_df, terms)
    if len(stage2_df) <= len(terms) or np.linalg.matrix_rank(design_matrix) < len(terms):
        return None
    weights = 1.0 / stage2_df["std_error"].to_numpy(float) ** 2
    coefficients = _weighted_least_squares(design_matrix, stage2_df["slope"].to_numpy(float), weights)
    return dict(zip(terms, coefficients))


def decompose_slopes(stage2_df: pd.DataFrame) -> pd.DataFrame:
    """Stage 2: WLS of β_t on (1, ΔU_t, A_t), weights 1/se². Drops the AI term with a warning if unidentified."""
    nonpositive_periods = stage2_df.loc[stage2_df["std_error"] <= 0, "period"].tolist()
    if nonpositive_periods:
        raise ValueError(f"Period(s) {nonpositive_periods} have a non-positive standard error; their WLS weight would be infinite")
    terms = list(DECOMPOSITION_TERMS)
    if np.linalg.matrix_rank(_design_matrix(stage2_df, terms)) < len(terms):
        warnings.warn(
            "The AI term is not identified (no period with nonzero adoption, or adoption collinear with the "
            "other terms); fitting structural + cycle only.",
            stacklevel=2,
        )
        terms = terms[:2]

    design_matrix = _design_matrix(stage2_df, terms)
    slopes = stage2_df["slope"].to_numpy(float)
    weights = 1.0 / stage2_df["std_error"].to_numpy(float) ** 2
    degrees_of_freedom = len(stage2_df) - len(terms)
    if degrees_of_freedom <= 0:
        raise ValueError(f"Stage 2 needs more than {len(terms)} periods, got {len(stage2_df)}")

    coefficients = _weighted_least_squares(design_matrix, slopes, weights)
    residuals = slopes - design_matrix @ coefficients
    residual_variance = np.sum(weights * residuals**2) / degrees_of_freedom
    covariance = residual_variance * np.linalg.inv(design_matrix.T @ (design_matrix * weights[:, None]))
    std_errors = np.sqrt(np.diag(covariance))
    with np.errstate(divide="ignore", invalid="ignore"):
        t_statistics = coefficients / std_errors
    p_values = 2.0 * stats.t.sf(np.abs(t_statistics), degrees_of_freedom)
    weighted_mean = np.average(slopes, weights=weights)
    total_sum_of_squares = np.sum(weights * (slopes - weighted_mean) ** 2)
    r_squared = 1.0 - np.sum(weights * residuals**2) / total_sum_of_squares if total_sum_of_squares > 0 else np.nan

    return pd.DataFrame(
        {
            "term": terms,
            "coefficient": coefficients,
            "std_error": std_errors,
            "t_statistic": t_statistics,
            "p_value": p_values,
            "r_squared": r_squared,
            "n_periods": len(stage2_df),
        },
        columns=DECOMPOSITION_COLUMNS,
    )


def coefficients_from(decomposition_df: pd.DataFrame) -> dict[str, float]:
    """{term: coefficient} with every term present; an omitted AI term contributes 0."""
    coefficients = dict.fromkeys(DECOMPOSITION_TERMS, 0.0)
    coefficients.update(dict(zip(decomposition_df["term"], decomposition_df["coefficient"])))
    return coefficients
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_forecast_composition.py -v`
Expected: PASS (13 tests)

- [x] **Step 5: Commit**

```bash
git add forecast_composition.py tests/test_forecast_composition.py docs/superpowers/plans/2026-10-02-decomposed-slope-forecast.md
git commit -m "Add Stage 2 of the composition forecast: WLS slope decomposition"
```

---

### Task 5: Estimation stage entry point and pipeline wiring

**Files:**
- Modify: `forecast_composition.py` (append)
- Modify: `main.py` (imports, `STAGES`, `runners`, epilog, module docstring)
- Modify: `tests/test_forecast_composition.py` (append)

**Interfaces:**
- Consumes: Tasks 2–4; `composition_era_validation.unemployment_change_by_period(period_keys) -> pd.Series | None`.
- Produces: `@dataclass InstrumentEstimate(instrument: str, scores: pd.Series, panel_df: pd.DataFrame, driven_df: pd.DataFrame, stage2_df: pd.DataFrame, decomposition_df: pd.DataFrame, coefficients: dict[str, float])`; `estimate_instrument(instrument, panel_df, scores, excluded_periods, unemployment_change, adoption_fits) -> tuple[InstrumentEstimate, pd.DataFrame]` (second item: all decomposition rows incl. sensitivity, with `instrument` and `specification` columns); `run_estimation() -> tuple[dict[str, InstrumentEstimate], dict[str, AdoptionFit]] | None`; `run_stage() -> None`; constant `STAGE2_ADOPTION_FIT = "logistic"`.

- [x] **Step 1: Write the failing tests** (append)

```python
from btos_adoption import AdoptionFit
from forecast_composition import estimate_instrument


class TestEstimationEntryPoint:
    def test_estimate_instrument_writes_main_and_sensitivity_rows(self, scores):
        # Noise keeps every Stage 1 standard error positive; WLS weights are 1/se².
        panel_df = synthetic_panel({year: 0.01 for year in range(2001, 2026)}, scores, years=range(2000, 2026), noise=0.002)
        period_keys = [f"{year}_{year + 1}" for year in range(2000, 2025)]
        unemployment_change = pd.Series(np.random.default_rng(1).normal(0, 1, len(period_keys)), index=period_keys)
        adoption_fits = {
            "logistic": AdoptionFit("logistic", (0.6, 0.6, 5.0), 0.55, True),
            "linear": AdoptionFit("linear", (0.0, 0.04), 0.55, True),
        }
        estimate, decomposition_rows = estimate_instrument(
            "oews", panel_df, scores, {"2009_2010": "SOC 2010 revision level break"}, unemployment_change, adoption_fits
        )
        assert set(decomposition_rows["specification"]) == {"main", "with_excluded_periods", "backcast_linear"}
        assert (decomposition_rows["instrument"] == "oews").all()
        assert "2009_2010" not in set(estimate.stage2_df["period"])

    def test_decompose_rejects_zero_standard_error(self):
        zero_error_df = synthetic_period_slopes()
        zero_error_df.loc[0, "std_error"] = 0.0
        with pytest.raises(ValueError, match="non-positive standard error"):
            decompose_slopes(zero_error_df)

    def test_run_stage_skips_without_unemployment(self, monkeypatch, capsys):
        monkeypatch.setattr(forecast_composition, "unemployment_change_by_period", lambda period_keys: None)
        monkeypatch.setattr(forecast_composition, "_load_inputs", lambda: (pd.DataFrame(), {"oews": pd.DataFrame()}))
        monkeypatch.setattr(forecast_composition, "run_adoption", lambda: (pd.DataFrame(), {}))
        assert forecast_composition.run_estimation() is None
        assert "No unemployment series available" in capsys.readouterr().out
```

Delete the unused `constant_fit` helper before committing if nothing references it.

- [x] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_forecast_composition.py::TestEstimationEntryPoint -v`
Expected: FAIL — `ImportError: cannot import name 'estimate_instrument'`

- [x] **Step 3: Append the entry point to `forecast_composition.py`**

Add to the imports: `from dataclasses import dataclass`, `from btos_adoption import AdoptionFit, accepted_fits, annual_mean_adoption, run_adoption`, and extend the `composition_era_validation` import to `from composition_era_validation import COVID_PERIODS, unemployment_change_by_period`. Then append:

```python
# ── Estimation entry point ─────────────────────────────────────────────────────

STAGE2_ADOPTION_FIT = "logistic"


@dataclass
class InstrumentEstimate:
    instrument: str
    scores: pd.Series
    panel_df: pd.DataFrame
    driven_df: pd.DataFrame
    stage2_df: pd.DataFrame
    decomposition_df: pd.DataFrame
    coefficients: dict[str, float]


def _labelled(decomposition_df: pd.DataFrame, instrument: str, specification: str) -> pd.DataFrame:
    return decomposition_df.assign(instrument=instrument, specification=specification)


def estimate_instrument(
    instrument: str,
    panel_df: pd.DataFrame,
    scores: pd.Series,
    excluded_periods: dict[str, str],
    unemployment_change: pd.Series,
    adoption_fits: dict[str, AdoptionFit],
) -> tuple[InstrumentEstimate, pd.DataFrame]:
    """Stages 1–2 for one instrument, plus the excluded-period and adoption-backcast sensitivity rows."""
    period_slopes_df = estimate_period_slopes(panel_df, scores, instrument, excluded_periods)
    adoption_years = sorted(period_slopes_df["end_year"].loc[lambda end_years: end_years > PRE_ADOPTION_LAST_YEAR])

    main_adoption = annual_mean_adoption(adoption_fits[STAGE2_ADOPTION_FIT], adoption_years)
    driven_df = attach_drivers(period_slopes_df, unemployment_change, main_adoption)
    main_stage2_df = stage2_input(driven_df)
    main_decomposition_df = decompose_slopes(main_stage2_df)

    decomposition_frames = [_labelled(main_decomposition_df, instrument, "main")]
    if excluded_periods:
        decomposition_frames.append(
            _labelled(decompose_slopes(stage2_input(driven_df, include_excluded=True)), instrument, "with_excluded_periods")
        )
    for fit_name, adoption_fit in adoption_fits.items():
        if fit_name == STAGE2_ADOPTION_FIT:
            continue
        backcast_driven_df = attach_drivers(period_slopes_df, unemployment_change, annual_mean_adoption(adoption_fit, adoption_years))
        decomposition_frames.append(_labelled(decompose_slopes(stage2_input(backcast_driven_df)), instrument, f"backcast_{fit_name}"))

    estimate = InstrumentEstimate(
        instrument=instrument,
        scores=align_sectors(panel_df, scores),
        panel_df=panel_df,
        driven_df=driven_df,
        stage2_df=main_stage2_df,
        decomposition_df=main_decomposition_df,
        coefficients=coefficients_from(main_decomposition_df),
    )
    return estimate, pd.concat(decomposition_frames, ignore_index=True)


def _load_inputs() -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """The dynamic report and each instrument's sector employment panel."""
    dynamic_report_df = pd.read_csv(DYNAMIC_REPORT_PATH, dtype={"OCC_CODE": str})
    panels = {
        "oews": sector_employment_panel(pd.read_csv(OEWS_SECTOR_TRENDS_PATH)),
        "cps": sector_employment_panel(pd.read_csv(CPS_SECTOR_TRENDS_PATH)),
    }
    return dynamic_report_df, panels


EXCLUDED_PERIODS_BY_INSTRUMENT = {"oews": OEWS_EXCLUDED_PERIODS, "cps": CPS_EXCLUDED_PERIODS}


def print_checkpoint(estimates: dict[str, InstrumentEstimate]) -> None:
    """The Stage 2 result the plan's checkpoint task reads: β_AI and its p-value per instrument."""
    print("\n  Stage 2 — β_t = β_structural + β_cycle·ΔU + β_AI·A  (main specification)")
    for instrument, estimate in estimates.items():
        for row in estimate.decomposition_df.itertuples():
            print(
                f"    {instrument:<5} {row.term:<11} {row.coefficient:+.5f}  se {row.std_error:.5f}  p = {row.p_value:.4f}  (n = {row.n_periods}, R² = {row.r_squared:.3f})"
            )


def run_estimation() -> tuple[dict[str, InstrumentEstimate], dict[str, AdoptionFit]] | None:
    """Stages 1–2 for both instruments; writes the period-slope and decomposition CSVs."""
    _, adoption_fits = run_adoption()
    dynamic_report_df, panels = _load_inputs()

    all_period_keys = sorted({f"{year}_{year + 1}" for panel_df in panels.values() for year in panel_df.columns})
    unemployment_change = unemployment_change_by_period(all_period_keys)
    if unemployment_change is None:
        print("  ⚠ No unemployment series available; skipping the composition forecast.")
        return None

    usable_fits = accepted_fits(adoption_fits)
    if STAGE2_ADOPTION_FIT not in usable_fits:
        print(f"  ⚠ The {STAGE2_ADOPTION_FIT} adoption fit was rejected; skipping the composition forecast.")
        return None

    scores = sector_scores(dynamic_report_df)
    estimates, slope_frames, decomposition_frames = {}, [], []
    for instrument, panel_df in panels.items():
        estimate, decomposition_rows = estimate_instrument(
            instrument, panel_df, scores, EXCLUDED_PERIODS_BY_INSTRUMENT[instrument], unemployment_change, usable_fits
        )
        estimates[instrument] = estimate
        slope_frames.append(estimate.driven_df)
        decomposition_frames.append(decomposition_rows)

    pd.concat(slope_frames, ignore_index=True).to_csv(PERIOD_SLOPES_OUTPUT_PATH, index=False)
    pd.concat(decomposition_frames, ignore_index=True).to_csv(DECOMPOSITION_OUTPUT_PATH, index=False)
    print(f"  ✓ {PERIOD_SLOPES_OUTPUT_PATH}\n  ✓ {DECOMPOSITION_OUTPUT_PATH}")
    print_checkpoint(estimates)
    return estimates, usable_fits


def run_stage() -> None:
    """The `forecast` pipeline stage."""
    run_estimation()


if __name__ == "__main__":
    run_stage()
```

- [x] **Step 4: Wire the stage into `main.py`**

Add `from forecast_composition import run_stage as forecast_composition` to the imports. Change the stage list and its comment:

```python
# composition runs after validate: its era comparison scores the demand composition
# model beside the AI dynamic model, whose report the validate stage writes.
# forecast runs last: it reads the dynamic report and composition's CPS rollup.
STAGES = ["analyze", "synthesize", "plot", "validate", "composition", "forecast"]
```

Add `"forecast": ("Composition Forecast to 2030", forecast_composition),` to `runners`, `  forecast    Decomposed-slope composition forecast to 2030` to the epilog, and `  forecast   — Project sector composition to 2030 → data/output/forecast_*.csv` to the module docstring.

- [x] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_forecast_composition.py -v`
Expected: PASS (16 tests)

- [x] **Step 6: Commit**

```bash
git add forecast_composition.py main.py tests/test_forecast_composition.py docs/superpowers/plans/2026-10-02-decomposed-slope-forecast.md
git commit -m "Add the forecast stage's estimation entry point and wire it into main.py"
```

---

### Task 6: CHECKPOINT — is β_AI there in slope units?

**Files:**
- Modify: `docs/superpowers/plans/2026-10-02-decomposed-slope-forecast.md` (Deviations log)

No code in this task. **Nothing after this task starts until the human partner's decision is recorded.**

- [x] **Step 1: Run the estimation on real data**

Run: `uv run main.py forecast`
Expected: the BTOS fit lines, two `✓` CSV lines, and the Stage 2 table printed by `print_checkpoint` — three terms per instrument.

- [x] **Step 2: Report to the human partner**

Report, for each instrument: `β_structural`, `β_cycle`, `β_AI` with standard errors, p-values, n and R²; the `with_excluded_periods` and every `backcast_*` row's `β_AI` from `data/output/forecast_slope_decomposition.csv`; the four splice multipliers. State plainly whether `β_AI` is positive with p < 0.10 on at least one instrument.

- [x] **Step 3: Stop and wait for the decision**

Options to offer: continue as specified; continue with structural + cycle only; change the specification; stop.

- [x] **Step 4: Record the decision**

Add a Deviations log entry (even if the decision is "continue as specified") with the Stage 2 numbers and the decision, then commit:

```bash
git add docs/superpowers/plans/2026-10-02-decomposed-slope-forecast.md
git commit -m "Record the Stage 2 checkpoint result and decision"
```

---

### Task 7: Stages 3–4 — scenario slopes and share projection

**Files:**
- Modify: `forecast_composition.py` (append; replace `run_stage`)
- Modify: `tests/test_forecast_composition.py` (append)

**Interfaces:**
- Consumes: `InstrumentEstimate`, `run_estimation()` (Task 5); `annual_mean_adoption` (Task 2).
- Produces: `FORECAST_END_YEAR = 2030`; `UNEMPLOYMENT_SCENARIOS: dict[str, dict[int, float]]`; `@dataclass(frozen=True) ProjectionStep(as_of: str, driver_year: int, year_fraction: float)`; `oews_steps(start_year: int) -> list[ProjectionStep]`; `cps_steps(start_month: str) -> list[ProjectionStep]`; `slope_path(coefficients, unemployment_path, adoption_by_year, driver_years) -> dict[int, float]`; `step_shares(shares, scores, slope, year_fraction=1.0) -> pd.Series`; `project_shares(start_shares, scores, start_label, steps, slope_by_year) -> pd.DataFrame` (index `as_of`, columns sectors); `oews_start(panel_df) -> tuple[str, int, pd.Series]` (label, year, employment); `cps_start_shares(a19_panel_df) -> tuple[str, pd.Series]` (month label, employment); `project_scenarios(estimate, start_label, start_employment, steps, adoption_fits, coefficients=None) -> pd.DataFrame` with columns `SECTOR_PATH_COLUMNS = ["instrument", "unemployment_scenario", "adoption_fit", "as_of", "soc_major", "share", "employment"]`.

- [x] **Step 1: Write the failing tests** (append)

```python
from forecast_composition import (
    ProjectionStep,
    cps_start_shares,
    cps_steps,
    oews_steps,
    project_shares,
    slope_path,
    step_shares,
)


class TestProjection:
    def test_oews_steps_are_annual_to_2030(self):
        steps = oews_steps(2025)
        assert [step.as_of for step in steps] == ["2026-05", "2027-05", "2028-05", "2029-05", "2030-05"]
        assert all(step.year_fraction == 1.0 for step in steps)

    def test_cps_partial_first_step(self):
        june = cps_steps("2026-06")
        assert june[0] == ProjectionStep("2026-12", 2026, 0.5)
        assert [step.as_of for step in june[1:]] == ["2027-12", "2028-12", "2029-12", "2030-12"]
        december = cps_steps("2026-12")
        assert december[0] == ProjectionStep("2027-12", 2027, 1.0)

    def test_slope_path_combines_terms(self):
        path = slope_path({"structural": 0.02, "cycle": 0.01, "ai": 0.1}, {2027: 1.5}, pd.Series({2026: 0.2, 2027: 0.3}), [2026, 2027])
        assert path[2026] == pytest.approx(0.02 + 0.1 * 0.2)
        assert path[2027] == pytest.approx(0.02 + 0.015 + 0.1 * 0.3)

    def test_shares_sum_to_one_and_zero_slope_is_identity(self, scores):
        start = pd.Series(np.arange(1, len(SECTORS) + 1, dtype=float), index=SECTORS)
        steps = oews_steps(2025)
        flat = project_shares(start, scores, "2025-05", steps, dict.fromkeys(range(2026, 2031), 0.0))
        assert np.allclose(flat.sum(axis=1), 1.0)
        assert np.allclose(flat.loc["2030-05"], start / start.sum())

    def test_positive_slope_moves_share_toward_high_scores(self, scores):
        start = pd.Series(1.0, index=SECTORS)
        path = project_shares(start, scores, "2025-05", oews_steps(2025), dict.fromkeys(range(2026, 2031), 0.05))
        change = path.loc["2030-05"] - path.loc["2025-05"]
        assert change[scores.idxmax()] > 0 > change[scores.idxmin()]

    def test_step_shares_rejects_nonpositive_share(self, scores):
        with pytest.raises(ValueError, match="non-positive share"):
            step_shares(pd.Series(1.0 / len(SECTORS), index=SECTORS), scores, slope=-10.0)

    def test_cps_start_shares_requires_every_sector(self):
        a19_df = pd.DataFrame({"month": "2026-08", "soc_major": SECTORS[:-1], "employed_thousands": 100.0})
        with pytest.raises(ValueError, match="missing sector"):
            cps_start_shares(a19_df)

    def test_cps_start_uses_latest_month(self):
        a19_df = pd.concat(
            [
                pd.DataFrame({"month": "2026-06", "soc_major": SECTORS, "employed_thousands": 50.0}),
                pd.DataFrame({"month": "2026-08", "soc_major": SECTORS, "employed_thousands": 100.0}),
            ]
        )
        label, employment = cps_start_shares(a19_df)
        assert label == "2026-08"
        assert (employment == 100.0).all()
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_forecast_composition.py::TestProjection -v`
Expected: FAIL — `ImportError: cannot import name 'ProjectionStep'`

- [x] **Step 3: Append Stages 3–4 to `forecast_composition.py`**

```python
# ── Stages 3–4: scenario slopes and share projection ───────────────────────────

FORECAST_END_YEAR = 2030
# ΔU for the period ending in each year; a year not listed is 0.
UNEMPLOYMENT_SCENARIOS = {
    "steady": {},
    "mild_recession": {2027: 1.5, 2028: -0.75, 2029: -0.75},
}
SECTOR_PATH_COLUMNS = ["instrument", "unemployment_scenario", "adoption_fit", "as_of", "soc_major", "share", "employment"]
REQUIRED_SECTOR_COUNT = 22


@dataclass(frozen=True)
class ProjectionStep:
    as_of: str
    driver_year: int
    year_fraction: float


def oews_steps(start_year: int) -> list[ProjectionStep]:
    """OEWS is a May reference month: one full-year step per May to 2030."""
    return [ProjectionStep(f"{year}-05", year, 1.0) for year in range(start_year + 1, FORECAST_END_YEAR + 1)]


def cps_steps(start_month: str) -> list[ProjectionStep]:
    """From the start month to December (partial), then full calendar years to 2030."""
    start_year, month = (int(part) for part in start_month.split("-"))
    remaining_fraction = (12 - month) / 12
    steps = [ProjectionStep(f"{start_year}-12", start_year, remaining_fraction)] if remaining_fraction > 0 else []
    return steps + [ProjectionStep(f"{year}-12", year, 1.0) for year in range(start_year + 1, FORECAST_END_YEAR + 1)]


def slope_path(
    coefficients: dict[str, float], unemployment_path: dict[int, float], adoption_by_year: pd.Series, driver_years
) -> dict[int, float]:
    """Stage 3: β_y = β_structural + β_cycle·ΔU_y + β_AI·A_y."""
    return {
        year: coefficients["structural"]
        + coefficients["cycle"] * unemployment_path.get(year, 0.0)
        + coefficients.get("ai", 0.0) * float(adoption_by_year[year])
        for year in driver_years
    }


def step_shares(shares: pd.Series, scores: pd.Series, slope: float, year_fraction: float = 1.0) -> pd.Series:
    """One multiplicative step, renormalised. Raises rather than clipping a share at or below zero."""
    updated_shares = shares * (1.0 + slope * year_fraction * scores.reindex(shares.index))
    if updated_shares.isna().any() or (updated_shares <= 0).any():
        raise ValueError(f"Projection produced a non-positive share (slope {slope:+.4f}); the scenario is outside the model's range")
    return updated_shares / updated_shares.sum()


def project_shares(
    start_shares: pd.Series, scores: pd.Series, start_label: str, steps: list[ProjectionStep], slope_by_year: dict[int, float]
) -> pd.DataFrame:
    """Stage 4: share path, one row per as_of label (start first), one column per sector."""
    shares = start_shares / start_shares.sum()
    path = {start_label: shares}
    for step in steps:
        shares = step_shares(shares, scores, slope_by_year[step.driver_year], step.year_fraction)
        path[step.as_of] = shares
    return pd.DataFrame(path).T


def oews_start(panel_df: pd.DataFrame) -> tuple[str, int, pd.Series]:
    """Latest OEWS year's sector totals; label uses OEWS's May reference month."""
    start_year = max(panel_df.columns)
    return f"{start_year}-05", start_year, panel_df[start_year].dropna()


def cps_start_shares(a19_panel_df: pd.DataFrame) -> tuple[str, pd.Series]:
    """Latest A-19 month's sector levels; every one of the 22 sectors must be present."""
    latest_month = str(a19_panel_df["month"].max())
    month_df = a19_panel_df[a19_panel_df["month"].astype(str) == latest_month]
    employment = month_df.set_index(month_df["soc_major"].map(sector_code))["employed_thousands"].astype(float)
    if employment.index.nunique() != REQUIRED_SECTOR_COUNT:
        raise ValueError(f"A-19 {latest_month} has {employment.index.nunique()} sectors; a missing sector would distort every share")
    return latest_month, employment.sort_index()


def project_scenarios(
    estimate: InstrumentEstimate,
    start_label: str,
    start_employment: pd.Series,
    steps: list[ProjectionStep],
    adoption_fits: dict[str, AdoptionFit],
    coefficients: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Every ΔU scenario × adoption fit for one instrument, as long-form share and employment paths."""
    coefficients = coefficients or estimate.coefficients
    driver_years = [step.driver_year for step in steps]
    total_employment = start_employment.sum()
    scores = estimate.scores.reindex(start_employment.index)
    path_frames = []
    for scenario_name, unemployment_path in UNEMPLOYMENT_SCENARIOS.items():
        for fit_name, adoption_fit in adoption_fits.items():
            slope_by_year = slope_path(coefficients, unemployment_path, annual_mean_adoption(adoption_fit, driver_years), driver_years)
            share_path = project_shares(start_employment, scores, start_label, steps, slope_by_year)
            long_df = share_path.rename_axis("as_of").reset_index().melt(id_vars="as_of", var_name="soc_major", value_name="share")
            long_df["employment"] = long_df["share"] * total_employment
            path_frames.append(long_df.assign(instrument=estimate.instrument, unemployment_scenario=scenario_name, adoption_fit=fit_name))
    return pd.concat(path_frames, ignore_index=True)[SECTOR_PATH_COLUMNS]
```

Replace `run_stage` with:

```python
def project_both_instruments(estimates: dict[str, InstrumentEstimate], adoption_fits: dict[str, AdoptionFit]) -> tuple[pd.DataFrame, dict]:
    """Point projections for OEWS and CPS; returns the paths and each instrument's (label, employment, steps)."""
    oews_label, oews_year, oews_employment = oews_start(estimates["oews"].panel_df)
    cps_label, cps_employment = cps_start_shares(pd.read_csv(CPS_A19_PANEL_PATH, dtype={"month": str}))
    starts = {
        "oews": (oews_label, oews_employment, oews_steps(oews_year)),
        "cps": (cps_label, cps_employment, cps_steps(cps_label)),
    }
    path_frames = [project_scenarios(estimates[instrument], *starts[instrument], adoption_fits) for instrument in ("oews", "cps")]
    return pd.concat(path_frames, ignore_index=True), starts


def run_stage() -> None:
    """The `forecast` pipeline stage."""
    estimation = run_estimation()
    if estimation is None:
        return
    estimates, adoption_fits = estimation
    sector_paths_df, _ = project_both_instruments(estimates, adoption_fits)
    sector_paths_df.to_csv(SECTOR_PATHS_OUTPUT_PATH, index=False)
    print(f"  ✓ {SECTOR_PATHS_OUTPUT_PATH}")
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_forecast_composition.py -v`
Expected: PASS (24 tests)

- [x] **Step 5: Run the stage on real data**

Run: `uv run main.py forecast`
Expected: `✓ data/output/forecast_sector_paths.csv`; spot-check that shares sum to 1 per (instrument, scenario, fit, as_of):
`uv run python -c "import pandas as p; d=p.read_csv('data/output/forecast_sector_paths.csv'); print(d.groupby(['instrument','unemployment_scenario','adoption_fit','as_of'])['share'].sum().agg(['min','max']))"`

- [x] **Step 6: Commit**

```bash
git add forecast_composition.py tests/test_forecast_composition.py docs/superpowers/plans/2026-10-02-decomposed-slope-forecast.md
git commit -m "Project sector shares to 2030 under unemployment and adoption scenarios"
```

---

### Task 8: Uncertainty — bootstrap bands, sector noise, leave-one-period-out

**Files:**
- Modify: `forecast_composition.py` (append; replace `run_stage`)
- Modify: `tests/test_forecast_composition.py` (append)

**Interfaces:**
- Consumes: Tasks 5 and 7.
- Produces: `BOOTSTRAP_REPLICATES = 2000`, `BOOTSTRAP_SEED = 20261002`, `REFERENCE_SCENARIO = ("steady", "logistic")`; `bootstrap_coefficients(stage2_df, replicates, rng, terms) -> tuple[pd.DataFrame, int]` (frame of coefficient dicts, skipped count); `bootstrap_bands(estimate, start, adoption_fits, coefficient_draws) -> pd.DataFrame` (columns `instrument, unemployment_scenario, adoption_fit, as_of, soc_major, share_p5, share_p95`); `add_sector_noise(sector_paths_df, estimates, starts) -> pd.DataFrame` (adds `noise_low`, `noise_high`); `leave_one_period_out(estimate, start, adoption_fits) -> pd.DataFrame` (columns `instrument, soc_major, change_min, change_max, n_refits`).

- [x] **Step 1: Write the failing tests** (append)

```python
from forecast_composition import bootstrap_coefficients


class TestUncertainty:
    def test_bootstrap_recovers_coefficients_on_noiseless_data(self):
        draws, skipped = bootstrap_coefficients(
            synthetic_period_slopes(noise=0.0, ai_periods=10), 50, np.random.default_rng(0), ("structural", "cycle", "ai")
        )
        assert skipped == 0
        assert draws["ai"].to_numpy() == pytest.approx(0.08, abs=1e-9)

    def test_bootstrap_skips_rank_deficient_replicates(self):
        # Only two AI-era periods out of 25: many resamples draw neither and cannot identify β_AI.
        draws, skipped = bootstrap_coefficients(
            synthetic_period_slopes(noise=0.001, ai_periods=2), 200, np.random.default_rng(0), ("structural", "cycle", "ai")
        )
        assert skipped > 0
        assert len(draws) + skipped == 200
        assert draws["ai"].notna().all()
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_forecast_composition.py::TestUncertainty -v`
Expected: FAIL — `ImportError: cannot import name 'bootstrap_coefficients'`

- [x] **Step 3: Append the uncertainty layers**

```python
# ── Uncertainty ────────────────────────────────────────────────────────────────

BOOTSTRAP_REPLICATES = 2000
BOOTSTRAP_SEED = 20261002
REFERENCE_SCENARIO = ("steady", "logistic")
NINETY_PERCENT_Z = 1.645


def bootstrap_coefficients(stage2_df: pd.DataFrame, replicates: int, rng: np.random.Generator, terms) -> tuple[pd.DataFrame, int]:
    """Resample Stage 2 periods with replacement; a rank-deficient replicate is skipped and counted, never zero-filled."""
    coefficient_draws, skipped = [], 0
    for _ in range(replicates):
        resampled_df = stage2_df.iloc[rng.integers(0, len(stage2_df), len(stage2_df))]
        coefficients = fit_coefficients(resampled_df, terms)
        if coefficients is None:
            skipped += 1
            continue
        coefficient_draws.append(coefficients)
    return pd.DataFrame(coefficient_draws, columns=list(terms)), skipped


def bootstrap_bands(
    estimate: InstrumentEstimate, start: tuple, adoption_fits: dict[str, AdoptionFit], coefficient_draws: pd.DataFrame
) -> pd.DataFrame:
    """5th–95th percentile of each sector's share path across bootstrap coefficient draws."""
    draw_frames = []
    for draw_index, draw in enumerate(coefficient_draws.to_dict("records")):
        draw_coefficients = {**dict.fromkeys(DECOMPOSITION_TERMS, 0.0), **draw}
        draw_frames.append(project_scenarios(estimate, *start, adoption_fits, coefficients=draw_coefficients).assign(draw=draw_index))
    draws_df = pd.concat(draw_frames, ignore_index=True)
    keys = ["instrument", "unemployment_scenario", "adoption_fit", "as_of", "soc_major"]
    return (
        draws_df.groupby(keys)["share"].quantile([0.05, 0.95]).unstack().rename(columns={0.05: "share_p5", 0.95: "share_p95"}).reset_index()
    )


def add_sector_noise(sector_paths_df: pd.DataFrame, estimates: dict[str, InstrumentEstimate], starts: dict) -> pd.DataFrame:
    """Sector-noise interval: median Stage 1 residual SD per year, accumulated as a random walk in relative growth."""
    noisy_frames = []
    for instrument, instrument_df in sector_paths_df.groupby("instrument"):
        residual_sd = float(estimates[instrument].stage2_df["residual_sd"].median())
        _, _, steps = starts[instrument]
        elapsed_years = dict(zip([step.as_of for step in steps], np.cumsum([step.year_fraction for step in steps])))
        horizon = instrument_df["as_of"].map(elapsed_years).fillna(0.0)
        half_width = NINETY_PERCENT_Z * residual_sd * np.sqrt(horizon)
        noisy_frames.append(
            instrument_df.assign(noise_low=instrument_df["share"] * (1 - half_width), noise_high=instrument_df["share"] * (1 + half_width))
        )
    return pd.concat(noisy_frames, ignore_index=True)


def leave_one_period_out(estimate: InstrumentEstimate, start: tuple, adoption_fits: dict[str, AdoptionFit]) -> pd.DataFrame:
    """Range of each sector's start→2030 share change when each Stage 2 period is dropped in turn (reference scenario)."""
    scenario_name, fit_name = REFERENCE_SCENARIO
    terms = tuple(estimate.decomposition_df["term"])
    final_changes = []
    for dropped_index in range(len(estimate.stage2_df)):
        refit = fit_coefficients(estimate.stage2_df.drop(index=dropped_index), terms)
        if refit is None:
            continue
        refit_coefficients = {**dict.fromkeys(DECOMPOSITION_TERMS, 0.0), **refit}
        paths_df = project_scenarios(estimate, *start, {fit_name: adoption_fits[fit_name]}, coefficients=refit_coefficients)
        paths_df = paths_df[paths_df["unemployment_scenario"] == scenario_name]
        share_by_label = paths_df.pivot(index="as_of", columns="soc_major", values="share")
        final_changes.append(share_by_label.iloc[-1] - share_by_label.iloc[0])
    changes_df = pd.DataFrame(final_changes)
    return pd.DataFrame(
        {
            "instrument": estimate.instrument,
            "soc_major": changes_df.columns,
            "change_min": changes_df.min().to_numpy(),
            "change_max": changes_df.max().to_numpy(),
            "n_refits": len(changes_df),
        }
    )
```

`project_shares` sorts `as_of` labels in insertion order, so `iloc[0]` is the start and `iloc[-1]` is the 2030 step; the pivot sorts labels lexically, which is also chronological for `YYYY-MM`.

Replace `run_stage` with:

```python
def run_stage() -> None:
    """The `forecast` pipeline stage."""
    estimation = run_estimation()
    if estimation is None:
        return
    estimates, adoption_fits = estimation
    sector_paths_df, starts = project_both_instruments(estimates, adoption_fits)

    rng = np.random.default_rng(BOOTSTRAP_SEED)
    band_frames, stability_frames = [], []
    for instrument, estimate in estimates.items():
        terms = tuple(estimate.decomposition_df["term"])
        coefficient_draws, skipped = bootstrap_coefficients(estimate.stage2_df, BOOTSTRAP_REPLICATES, rng, terms)
        print(f"  {instrument}: {len(coefficient_draws)} bootstrap replicates used, {skipped} skipped as rank-deficient")
        band_frames.append(bootstrap_bands(estimate, starts[instrument], adoption_fits, coefficient_draws))
        stability_frames.append(leave_one_period_out(estimate, starts[instrument], adoption_fits))

    keys = ["instrument", "unemployment_scenario", "adoption_fit", "as_of", "soc_major"]
    sector_paths_df = add_sector_noise(
        sector_paths_df.merge(pd.concat(band_frames), on=keys, how="left", validate="one_to_one"), estimates, starts
    )
    sector_paths_df.to_csv(SECTOR_PATHS_OUTPUT_PATH, index=False)
    pd.concat(stability_frames, ignore_index=True).to_csv(STABILITY_OUTPUT_PATH, index=False)
    print(f"  ✓ {SECTOR_PATHS_OUTPUT_PATH}\n  ✓ {STABILITY_OUTPUT_PATH}")
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_forecast_composition.py -v`
Expected: PASS (26 tests)

- [x] **Step 5: Run the stage on real data and time it**

Run: `time uv run main.py forecast`
Expected: both `✓` lines; bootstrap skip counts printed. If the stage takes over 5 minutes, record that in the Deviations log and reduce nothing without the human partner's agreement.

- [x] **Step 6: Commit**

```bash
git add forecast_composition.py tests/test_forecast_composition.py docs/superpowers/plans/2026-10-02-decomposed-slope-forecast.md
git commit -m "Add bootstrap bands, sector noise and leave-one-period-out stability"
```

---

### Task 9: Occupation allocation and demand-type rollup

**Files:**
- Modify: `forecast_composition.py` (append; extend `run_stage`)
- Modify: `tests/test_forecast_composition.py` (append)

**Interfaces:**
- Consumes: `sector_paths_df` (Task 8), `report_employment_column` (Task 3).
- Produces: `allocate_to_occupations(dynamic_report_df, sector_paths_df) -> pd.DataFrame` — OEWS only, every as_of, columns `OCC_CODE, Title, soc_major, dominant_demand, unemployment_scenario, adoption_fit, as_of, start_employment, allocated_employment`; `demand_type_shares(allocation_df) -> pd.DataFrame` — columns `unemployment_scenario, adoption_fit, as_of, dominant_demand, share`.

- [x] **Step 1: Write the failing tests** (append)

```python
from forecast_composition import allocate_to_occupations, demand_type_shares


def sector_paths_for(growth_by_sector: dict[str, float]):
    rows = []
    for soc_major, growth in growth_by_sector.items():
        rows += [
            {
                "instrument": "oews",
                "unemployment_scenario": "steady",
                "adoption_fit": "logistic",
                "as_of": "2025-05",
                "soc_major": soc_major,
                "employment": 100.0,
            },
            {
                "instrument": "oews",
                "unemployment_scenario": "steady",
                "adoption_fit": "logistic",
                "as_of": "2030-05",
                "soc_major": soc_major,
                "employment": 100.0 * (1 + growth),
            },
        ]
    return pd.DataFrame(rows)


class TestAllocation:
    def test_every_occupation_gets_its_sector_growth(self):
        report_df = pd.DataFrame(
            {
                "OCC_CODE": ["43-1011", "43-9061", "15-1252"],
                "Title": ["Supervisors", "Office Clerks", "Software Developers"],
                "dominant_demand": ["Bounded", "Bounded", "Unbounded"],
                "TOT_EMP_2025": [40.0, 60.0, 80.0],
            }
        )
        allocation_df = allocate_to_occupations(report_df, sector_paths_for({"43": -0.10, "15": 0.05}))
        final_df = allocation_df[allocation_df["as_of"] == "2030-05"].set_index("OCC_CODE")
        assert final_df.loc["43-1011", "allocated_employment"] == pytest.approx(36.0)
        assert final_df.loc["43-9061", "allocated_employment"] == pytest.approx(54.0)
        assert final_df.loc["15-1252", "allocated_employment"] == pytest.approx(84.0)

    def test_demand_type_shares_sum_to_one(self):
        report_df = pd.DataFrame(
            {
                "OCC_CODE": ["43-1011", "15-1252"],
                "Title": ["A", "B"],
                "dominant_demand": ["Bounded", "Unbounded"],
                "TOT_EMP_2025": [50.0, 50.0],
            }
        )
        shares_df = demand_type_shares(allocate_to_occupations(report_df, sector_paths_for({"43": -0.10, "15": 0.10})))
        final = shares_df[shares_df["as_of"] == "2030-05"].set_index("dominant_demand")["share"]
        assert final.sum() == pytest.approx(1.0)
        assert final["Unbounded"] == pytest.approx(55.0 / 100.0)
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_forecast_composition.py::TestAllocation -v`
Expected: FAIL — `ImportError: cannot import name 'allocate_to_occupations'`

- [x] **Step 3: Append the allocation**

```python
# ── Occupation allocation ──────────────────────────────────────────────────────


def allocate_to_occupations(dynamic_report_df: pd.DataFrame, sector_paths_df: pd.DataFrame) -> pd.DataFrame:
    """OEWS only: each occupation takes its sector's projected growth — an allocation, not an occupation forecast."""
    employment_column = report_employment_column(dynamic_report_df)
    occupation_df = dynamic_report_df.dropna(subset=[employment_column])[["OCC_CODE", "Title", "dominant_demand", employment_column]].copy()
    occupation_df = occupation_df.rename(columns={employment_column: "start_employment"})
    occupation_df["soc_major"] = occupation_df["OCC_CODE"].astype(str).str[:2].map(sector_code)

    oews_paths_df = sector_paths_df[sector_paths_df["instrument"] == "oews"].copy()
    oews_paths_df["soc_major"] = oews_paths_df["soc_major"].map(sector_code)
    start_label = oews_paths_df["as_of"].min()
    start_employment = (
        oews_paths_df[oews_paths_df["as_of"] == start_label]
        .groupby(["unemployment_scenario", "adoption_fit", "soc_major"])["employment"]
        .first()
    )
    oews_paths_df["sector_growth_factor"] = (
        oews_paths_df["employment"].to_numpy()
        / start_employment.reindex(
            pd.MultiIndex.from_frame(oews_paths_df[["unemployment_scenario", "adoption_fit", "soc_major"]])
        ).to_numpy()
    )

    allocation_df = occupation_df.merge(
        oews_paths_df[["soc_major", "unemployment_scenario", "adoption_fit", "as_of", "sector_growth_factor"]], on="soc_major", how="inner"
    )
    allocation_df["allocated_employment"] = allocation_df["start_employment"] * allocation_df["sector_growth_factor"]
    return allocation_df.drop(columns="sector_growth_factor")


def demand_type_shares(allocation_df: pd.DataFrame) -> pd.DataFrame:
    """Share of allocated employment by dominant_demand, per scenario and as_of."""
    keys = ["unemployment_scenario", "adoption_fit", "as_of"]
    by_type = allocation_df.groupby([*keys, "dominant_demand"])["allocated_employment"].sum().rename("employment").reset_index()
    by_type["share"] = by_type["employment"] / by_type.groupby(keys)["employment"].transform("sum")
    return by_type.drop(columns="employment")
```

Extend `run_stage` — after writing the stability CSV, add:

```python
    dynamic_report_df, _ = _load_inputs()
    allocation_df = allocate_to_occupations(dynamic_report_df, sector_paths_df)
    final_label = allocation_df["as_of"].max()
    allocation_df[allocation_df["as_of"] == final_label].to_csv(OCCUPATION_OUTPUT_PATH, index=False)
    print(f"  ✓ {OCCUPATION_OUTPUT_PATH}")
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_forecast_composition.py -v`
Expected: PASS (28 tests)

- [x] **Step 5: Commit**

```bash
git add forecast_composition.py tests/test_forecast_composition.py docs/superpowers/plans/2026-10-02-decomposed-slope-forecast.md
git commit -m "Allocate projected sector change to occupations and roll up by demand type"
```

---

### Task 10: Charts

**Files:**
- Create: `forecast_charts.py`
- Create: `tests/test_forecast_charts.py`
- Modify: `forecast_composition.py` (`run_stage` calls `draw_all`)

**Interfaces:**
- Consumes: `period_slopes_df` (Task 5 `driven_df` frames), decomposition rows, `btos series_df` + `fits_table`, `sector_paths_df` (Task 8 columns incl. `share_p5`, `share_p95`, `noise_low`, `noise_high`), `demand_type_shares` output.
- Produces: `CHART_NAMES` tuple of six PNG names; `draw_all(period_slopes_df, decomposition_df, btos_series_df, adoption_fits_df, sector_paths_df, demand_shares_df, output_dir) -> list[str]`.

Load the `dataviz` skill before writing this task's code; follow its colour and mark guidance within the repo's existing `DEMAND_PALETTE` and `SOC_MAJOR_GROUPS`.

- [x] **Step 1: Write the failing smoke test**

```python
"""
test_forecast_charts.py
───────────────────────
Smoke test for forecast_charts.py: every chart is drawn from small synthetic
frames and saved through chart_manifest, so a renamed column fails here rather
than in a release run.
"""

import numpy as np
import pandas as pd

from forecast_charts import CHART_NAMES, draw_all

SECTORS = ["11", "15", "43", "53"]


def synthetic_inputs():
    periods = pd.DataFrame(
        {
            "instrument": ["oews"] * 4 + ["cps"] * 4,
            "period": ["2019_2020", "2022_2023", "2023_2024", "2024_2025"] * 2,
            "end_year": [2020, 2023, 2024, 2025] * 2,
            "slope": [0.01, 0.03, 0.04, 0.05] * 2,
            "std_error": 0.01,
            "is_covid": [True, False, False, False] * 2,
            "excluded_reason": "",
            "unemployment_change": [3.0, -0.3, 0.2, 0.1] * 2,
            "adoption": [0.0, 0.1, 0.15, 0.2] * 2,
        }
    )
    decomposition = pd.DataFrame(
        {
            "instrument": ["oews"] * 3 + ["cps"] * 3,
            "specification": "main",
            "term": ["structural", "cycle", "ai"] * 2,
            "coefficient": [0.01, 0.005, 0.1] * 2,
            "p_value": [0.01, 0.2, 0.05] * 2,
        }
    )
    btos_series = pd.DataFrame(
        {
            "ref_end": pd.date_range("2023-09-10", periods=6, freq="90D"),
            "wording": ["production"] * 3 + ["any_function"] * 3,
            "ai_use": [0.04, 0.06, 0.08, 0.17, 0.19, 0.22],
        }
    )
    months = pd.date_range("2022-01-01", "2030-12-01", freq="MS")
    fits = pd.concat(
        [
            pd.DataFrame(
                {"fit": name, "accepted": True, "splice_multiplier": 0.55, "month": months, "adoption": np.linspace(0.02, top, len(months))}
            )
            for name, top in (("linear", 0.6), ("logistic", 0.5))
        ]
    )
    path_rows = []
    for instrument, labels in (("oews", ["2025-05", "2030-05"]), ("cps", ["2026-08", "2030-12"])):
        for scenario in ("steady", "mild_recession"):
            for fit in ("linear", "logistic"):
                for label_index, label in enumerate(labels):
                    for sector_index, sector in enumerate(SECTORS):
                        share = 0.25 + label_index * (sector_index - 1.5) * 0.01
                        path_rows.append(
                            {
                                "instrument": instrument,
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
    demand_shares = pd.DataFrame(
        [
            {"unemployment_scenario": s, "adoption_fit": f, "as_of": a, "dominant_demand": d, "share": v}
            for s in ("steady", "mild_recession")
            for f in ("linear", "logistic")
            for a, shift in (("2025-05", 0.0), ("2030-05", 0.01))
            for d, v in (("Bounded", 0.7 - shift), ("Unbounded", 0.2 + shift), ("Adversarial", 0.1))
        ]
    )
    return periods, decomposition, btos_series, fits, sector_paths, demand_shares


def test_draw_all_writes_every_chart(tmp_path):
    written = draw_all(*synthetic_inputs(), output_dir=str(tmp_path))
    assert sorted(written) == sorted(CHART_NAMES)
    for chart_name in CHART_NAMES:
        assert (tmp_path / chart_name).stat().st_size > 0
    assert (tmp_path / "chart_manifest.json").exists()
```

- [x] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_forecast_charts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'forecast_charts'`

- [x] **Step 3: Write `forecast_charts.py`**

```python
"""
forecast_charts.py
──────────────────
The six charts of the decomposed-slope composition forecast
(docs/superpowers/specs/2026-10-02-decomposed-slope-forecast-design.md § Component 5).

Every chart is saved through chart_manifest.save_figure. The sector-change and
occupation views are labelled as conditional projections; occupation numbers are
an allocation of sector change, never an occupation-level forecast.

Inputs:  frames produced by forecast_composition.py and btos_adoption.py
Outputs: data/output/visualizations/forecast_*.png
"""

import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from chart_manifest import save_figure
from plot_constants import DEMAND_PALETTE, SOC_MAJOR_GROUPS

CHART_NAMES = (
    "forecast_slope_history.png",
    "forecast_btos_adoption.png",
    "forecast_sector_change_2030.png",
    "forecast_sector_paths.png",
    "forecast_demand_type_shares.png",
    "forecast_scenario_comparison.png",
)
INSTRUMENT_LABELS = {"oews": "OEWS (start May 2025)", "cps": "CPS A-19 (start latest month)"}
FIT_COLORS = {"linear": "#4c72b0", "logistic": "#dd8452", "gompertz": "#55a868", "exponential": "#8172b3"}
SCENARIO_LABELS = {"steady": "Steady unemployment", "mild_recession": "Mild recession (+1.5 pp in 2027)"}
REFERENCE_SCENARIO = ("steady", "logistic")
PROJECTION_NOTE = "Conditional projection: dynamic-model score unchanged, total employment held at start level."


def _sector_label(soc_major: str) -> str:
    return SOC_MAJOR_GROUPS.get(str(soc_major).zfill(2), str(soc_major))


def _start_and_end(instrument_df: pd.DataFrame) -> tuple[str, str]:
    labels = sorted(instrument_df["as_of"].unique())
    return labels[0], labels[-1]


def _final_change(sector_paths_df: pd.DataFrame, instrument: str, scenario: str, fit: str) -> pd.DataFrame:
    """Start → final share change (percentage points) with band and noise edges, per sector."""
    scenario_df = sector_paths_df[
        (sector_paths_df["instrument"] == instrument)
        & (sector_paths_df["unemployment_scenario"] == scenario)
        & (sector_paths_df["adoption_fit"] == fit)
    ]
    start_label, end_label = _start_and_end(scenario_df)
    start = scenario_df[scenario_df["as_of"] == start_label].set_index("soc_major")
    end = scenario_df[scenario_df["as_of"] == end_label].set_index("soc_major")
    change = pd.DataFrame({"change": end["share"] - start["share"]})
    for column in ("share_p5", "share_p95", "noise_low", "noise_high"):
        if column in end:
            change[column] = end[column] - start["share"]
    return change * 100


def plot_slope_history(period_slopes_df, decomposition_df, output_dir):
    figure, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
    for axis, instrument in zip(axes, ("oews", "cps")):
        instrument_df = period_slopes_df[period_slopes_df["instrument"] == instrument].sort_values("end_year")
        included = ~instrument_df["is_covid"].astype(bool) & (instrument_df["excluded_reason"].fillna("") == "")
        axis.errorbar(
            instrument_df.loc[included, "end_year"],
            instrument_df.loc[included, "slope"],
            yerr=1.96 * instrument_df.loc[included, "std_error"],
            fmt="o",
            color="#333333",
            label="β_t (95% CI)",
        )
        axis.scatter(
            instrument_df.loc[~included, "end_year"],
            instrument_df.loc[~included, "slope"],
            marker="x",
            color="#999999",
            label="COVID or excluded period",
        )
        coefficients = decomposition_df[
            (decomposition_df["instrument"] == instrument) & (decomposition_df["specification"] == "main")
        ].set_index("term")["coefficient"]
        fitted = (
            coefficients.get("structural", 0)
            + coefficients.get("cycle", 0) * instrument_df["unemployment_change"]
            + coefficients.get("ai", 0) * instrument_df["adoption"]
        )
        axis.plot(instrument_df["end_year"], fitted, color="#dd8452", label="Fitted β_structural + β_cycle·ΔU + β_AI·A")
        axis.axhline(0, color="#cccccc", linewidth=0.8)
        axis.set_title(INSTRUMENT_LABELS[instrument])
        axis.set_xlabel("Period end year")
    axes[0].set_ylabel("Slope of relative share growth on sector score")
    axes[0].legend(fontsize=8, loc="upper left")
    figure.suptitle("How strongly the dynamic-model score sorted sector shares, by year")
    figure.tight_layout()
    save_figure(figure, os.path.join(output_dir, CHART_NAMES[0]), dpi=150)
    plt.close(figure)


def plot_btos_adoption(btos_series_df, adoption_fits_df, output_dir):
    figure, axis = plt.subplots(figsize=(10, 5.5))
    accepted_df = adoption_fits_df[adoption_fits_df["accepted"].astype(bool)]
    for fit_name, fit_df in accepted_df.groupby("fit"):
        axis.plot(
            pd.to_datetime(fit_df["month"]), fit_df["adoption"] * 100, color=FIT_COLORS.get(fit_name, "#555555"), label=f"{fit_name} fit"
        )
    for wording, marker, label in (
        ("production", "o", "Observed: 'producing goods or services'"),
        ("any_function", "s", "Observed: 'any business function'"),
    ):
        wording_df = btos_series_df[btos_series_df["wording"] == wording]
        axis.scatter(
            pd.to_datetime(wording_df["ref_end"]), wording_df["ai_use"] * 100, marker=marker, s=14, color="#333333", alpha=0.7, label=label
        )
    if not accepted_df.empty:
        splice = accepted_df.groupby("fit")["splice_multiplier"].first()
        axis.text(
            0.01,
            0.97,
            "Splice (old → new wording): " + ", ".join(f"{name} ×{value:.2f}" for name, value in splice.items()),
            transform=axis.transAxes,
            fontsize=8,
            va="top",
        )
    axis.set_ylabel("Firms using AI (%), new-wording scale")
    axis.set_title("Census BTOS AI adoption and growth fits to 2030")
    axis.legend(fontsize=8, loc="lower right")
    figure.tight_layout()
    save_figure(figure, os.path.join(output_dir, CHART_NAMES[1]), dpi=150)
    plt.close(figure)


def plot_sector_change_2030(sector_paths_df, output_dir):
    scenario, fit = REFERENCE_SCENARIO
    figure, axes = plt.subplots(1, 2, figsize=(14, 9), sharey=True)
    order = _final_change(sector_paths_df, "oews", scenario, fit)["change"].sort_values().index
    positions = np.arange(len(order))
    for axis, instrument in zip(axes, ("oews", "cps")):
        change = _final_change(sector_paths_df, instrument, scenario, fit).reindex(order)
        axis.hlines(positions, change["noise_low"], change["noise_high"], color="#dddddd", linewidth=6, label="Sector-noise 90% interval")
        axis.hlines(
            positions, change["share_p5"], change["share_p95"], color="#8fa8c8", linewidth=3, label="Parameter 90% band (bootstrap)"
        )
        axis.scatter(
            change["change"], positions, color=np.where(change["change"] >= 0, "#1a9850", "#d73027"), zorder=3, label="Projected change"
        )
        axis.axvline(0, color="#999999", linewidth=0.8)
        axis.set_title(INSTRUMENT_LABELS[instrument])
        axis.set_xlabel("Change in employment share by 2030 (percentage points)")
    axes[0].set_yticks(positions, [_sector_label(code) for code in order])
    axes[0].legend(fontsize=8, loc="lower right")
    figure.suptitle(f"Projected sector share change to 2030 — steady unemployment, logistic adoption\n{PROJECTION_NOTE}", fontsize=11)
    figure.tight_layout()
    save_figure(figure, os.path.join(output_dir, CHART_NAMES[2]), dpi=150)
    plt.close(figure)


def plot_sector_paths(sector_paths_df, output_dir):
    oews_df = sector_paths_df[sector_paths_df["instrument"] == "oews"]
    reference_change = _final_change(sector_paths_df, "oews", *REFERENCE_SCENARIO)["change"]
    movers = reference_change.abs().sort_values(ascending=False).index[:8]
    figure, axes = plt.subplots(len(movers), 2, figsize=(12, 2.0 * len(movers)), sharex=True)
    axes = np.atleast_2d(axes)
    for row_index, sector in enumerate(movers):
        for column_index, scenario in enumerate(SCENARIO_LABELS):
            axis = axes[row_index, column_index]
            for fit_name, fit_df in oews_df[(oews_df["soc_major"] == sector) & (oews_df["unemployment_scenario"] == scenario)].groupby(
                "adoption_fit"
            ):
                fit_df = fit_df.sort_values("as_of")
                axis.plot(fit_df["as_of"], fit_df["share"] * 100, color=FIT_COLORS.get(fit_name, "#555555"), label=fit_name)
            if row_index == 0:
                axis.set_title(SCENARIO_LABELS[scenario])
            if column_index == 0:
                axis.set_ylabel(_sector_label(sector), fontsize=8, rotation=0, ha="right")
    axes[0, 1].legend(fontsize=7, loc="upper right")
    figure.suptitle(f"Employment share paths (%), eight largest-moving sectors, OEWS start\n{PROJECTION_NOTE}", fontsize=10)
    figure.tight_layout()
    save_figure(figure, os.path.join(output_dir, CHART_NAMES[3]), dpi=150)
    plt.close(figure)


def plot_demand_type_shares(demand_shares_df, output_dir):
    figure, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    for axis, demand_type in zip(axes, ("Bounded", "Unbounded", "Adversarial")):
        type_df = demand_shares_df[demand_shares_df["dominant_demand"] == demand_type]
        for (scenario, fit_name), path_df in type_df.groupby(["unemployment_scenario", "adoption_fit"]):
            path_df = path_df.sort_values("as_of")
            axis.plot(
                path_df["as_of"],
                path_df["share"] * 100,
                color=FIT_COLORS.get(fit_name, "#555555"),
                linestyle="-" if scenario == "steady" else "--",
                label=f"{fit_name}, {scenario.replace('_', ' ')}",
            )
        axis.set_title(demand_type, color=DEMAND_PALETTE[demand_type])
        axis.set_ylabel("Share of scored employment (%)")
        axis.tick_params(axis="x", rotation=45)
    axes[0].legend(fontsize=7)
    figure.suptitle("Employment share by dominant demand type (sector change allocated to occupations), OEWS start", fontsize=11)
    figure.tight_layout()
    save_figure(figure, os.path.join(output_dir, CHART_NAMES[4]), dpi=150)
    plt.close(figure)


def plot_scenario_comparison(sector_paths_df, output_dir):
    reference_change = _final_change(sector_paths_df, "oews", *REFERENCE_SCENARIO)["change"]
    movers = list(reference_change.abs().sort_values(ascending=False).index[:6])
    combinations = (
        sector_paths_df[sector_paths_df["instrument"] == "oews"][["unemployment_scenario", "adoption_fit"]]
        .drop_duplicates()
        .sort_values(["unemployment_scenario", "adoption_fit"])
    )
    figure, axis = plt.subplots(figsize=(12, 6))
    bar_width = 0.8 / len(combinations)
    for combination_index, combination in enumerate(combinations.itertuples(index=False)):
        change = _final_change(sector_paths_df, "oews", combination.unemployment_scenario, combination.adoption_fit)["change"].reindex(
            movers
        )
        axis.bar(
            np.arange(len(movers)) + combination_index * bar_width,
            change,
            width=bar_width,
            color=FIT_COLORS.get(combination.adoption_fit, "#555555"),
            hatch="" if combination.unemployment_scenario == "steady" else "//",
            edgecolor="white",
            label=f"{combination.adoption_fit}, {SCENARIO_LABELS[combination.unemployment_scenario]}",
        )
    axis.set_xticks(
        np.arange(len(movers)) + 0.4 - bar_width / 2, [_sector_label(code) for code in movers], rotation=20, ha="right", fontsize=8
    )
    axis.axhline(0, color="#999999", linewidth=0.8)
    axis.set_ylabel("Change in employment share by 2030 (pp)")
    axis.set_title(f"2030 share change under each scenario, six largest-moving sectors (OEWS start)\n{PROJECTION_NOTE}", fontsize=10)
    axis.legend(fontsize=7)
    figure.tight_layout()
    save_figure(figure, os.path.join(output_dir, CHART_NAMES[5]), dpi=150)
    plt.close(figure)


def draw_all(
    period_slopes_df,
    decomposition_df,
    btos_series_df,
    adoption_fits_df,
    sector_paths_df,
    demand_shares_df,
    output_dir="data/output/visualizations",
) -> list[str]:
    """Draw every forecast chart; returns the file names written."""
    os.makedirs(output_dir, exist_ok=True)
    plot_slope_history(period_slopes_df, decomposition_df, output_dir)
    plot_btos_adoption(btos_series_df, adoption_fits_df, output_dir)
    plot_sector_change_2030(sector_paths_df, output_dir)
    plot_sector_paths(sector_paths_df, output_dir)
    plot_demand_type_shares(demand_shares_df, output_dir)
    plot_scenario_comparison(sector_paths_df, output_dir)
    return list(CHART_NAMES)
```

- [x] **Step 4: Call the charts from `run_stage`**

Add `import btos_adoption` and `import forecast_charts` to the module imports of `forecast_composition.py`, then append to `run_stage`:

```python
    written_charts = forecast_charts.draw_all(
        pd.read_csv(PERIOD_SLOPES_OUTPUT_PATH),
        pd.read_csv(DECOMPOSITION_OUTPUT_PATH),
        pd.read_csv(btos_adoption.SERIES_OUTPUT_PATH, parse_dates=["ref_end"]),
        pd.read_csv(btos_adoption.FITS_OUTPUT_PATH, parse_dates=["month"]),
        pd.read_csv(SECTOR_PATHS_OUTPUT_PATH, dtype={"soc_major": str}),
        demand_type_shares(allocation_df),
    )
    for chart_name in written_charts:
        print(f"  ✓ data/output/visualizations/{chart_name}")
```

- [x] **Step 5: Run the tests, then the stage, and look at every chart**

Run: `uv run pytest tests/test_forecast_charts.py tests/test_forecast_composition.py -v` — Expected: PASS.
Run: `uv run main.py forecast` — Expected: six chart `✓` lines.
Open each PNG with the Read tool and check: labels legible, no overlapping tick text, both instruments present, the conditional-projection note visible. Fix layout problems before committing.

- [x] **Step 6: Commit**

```bash
git add forecast_charts.py tests/test_forecast_charts.py forecast_composition.py docs/superpowers/plans/2026-10-02-decomposed-slope-forecast.md
git commit -m "Draw the six composition forecast charts"
```

---

### Task 11: Documentation, measured results, committed images

**Files:**
- Modify: `docs/outputs.md` (Data files table: 7 rows; Visualizations table: 6 rows)
- Create: `docs/charts/forecast_slope_history.md`, `docs/charts/forecast_btos_adoption.md`, `docs/charts/forecast_sector_change_2030.md`, `docs/charts/forecast_sector_paths.md`, `docs/charts/forecast_demand_type_shares.md`, `docs/charts/forecast_scenario_comparison.md`
- Modify: `docs/framework.md` (new § Composition Forecast)
- Modify: `CLAUDE.md` (Phase 2 stage list item 6; Seeds table row for `btos_ai_use.csv`)
- Modify: `docs/seeds.md` (paragraph for `seeds/btos_ai_use.csv`)
- Copy: `data/output/visualizations/forecast_*.png` and `chart_manifest.json` → `docs/charts/images/`
- Modify: this plan (Status line)

- [x] **Step 1: Add the `docs/outputs.md` rows**

Data files table:

```markdown
| `btos_ai_use.csv` | `btos_adoption.py` (via the `forecast` stage) | Census BTOS share of firms using AI, biweekly, both question wordings (`production` 2023–2025 from the seed, `any_function` from the latest census.gov fetch). The adoption driver's raw series. |
| `btos_adoption_fits.csv` | `btos_adoption.py` | Linear, logistic, Gompertz and exponential fits to the spliced BTOS series: parameters, fitted splice multiplier, accepted/rejected with reason, and monthly fitted adoption 2022-01 → 2030-12. |
| `forecast_period_slopes.csv` | `forecast_composition.py` | Stage 1: per instrument and year pair, the slope of sector relative share growth on the dynamic-model sector score, its standard error, residual SD, the period's ΔU and adoption, and COVID/exclusion flags. |
| `forecast_slope_decomposition.csv` | `forecast_composition.py` | Stage 2: β_structural, β_cycle, β_AI per instrument, with the `with_excluded_periods` and `backcast_<fit>` sensitivity specifications. See `docs/framework.md` § Composition Forecast. |
| `forecast_sector_paths.csv` | `forecast_composition.py` | Projected share and employment per instrument × unemployment scenario × adoption fit × sector × step to 2030, with bootstrap 5th/95th percentiles and the sector-noise interval. Conditional projection; total employment held at start level. |
| `forecast_sector_stability.csv` | `forecast_composition.py` | Leave-one-period-out range of each sector's projected share change to 2030 (steady unemployment, logistic adoption). Stability, not accuracy. |
| `forecast_occupation_allocation_2030.csv` | `forecast_composition.py` | OEWS occupations' 2030 employment under each scenario, obtained by applying the sector's projected growth to each occupation — an allocation, not an occupation-level forecast. |
```

Visualizations table:

```markdown
| `forecast_slope_history.png` | `forecast_charts.py` | Per-year slope of sector share growth on the dynamic score for OEWS and CPS, with COVID/excluded periods marked and the Stage 2 fitted line. See `docs/charts/forecast_slope_history.md`. |
| `forecast_btos_adoption.png` | `forecast_charts.py` | BTOS AI adoption, both wordings, and every accepted growth fit to 2030 with the fitted splice. See `docs/charts/forecast_btos_adoption.md`. |
| `forecast_sector_change_2030.png` | `forecast_charts.py` | Projected 2030 share change by sector (steady unemployment, logistic adoption) with bootstrap and sector-noise intervals, OEWS and CPS side by side. See `docs/charts/forecast_sector_change_2030.md`. |
| `forecast_sector_paths.png` | `forecast_charts.py` | Share paths to 2030 for the eight largest-moving sectors, one panel per unemployment scenario, one line per adoption fit. See `docs/charts/forecast_sector_paths.md`. |
| `forecast_demand_type_shares.png` | `forecast_charts.py` | Employment share by dominant demand type to 2030 under every scenario, from the occupation allocation. See `docs/charts/forecast_demand_type_shares.md`. |
| `forecast_scenario_comparison.png` | `forecast_charts.py` | 2030 share change for the six largest-moving sectors under each unemployment × adoption combination. See `docs/charts/forecast_scenario_comparison.md`. |
```

- [x] **Step 2: Write the six chart docs**

Each follows the existing chart-doc shape (`docs/charts/dynamic_model_winners_losers.md`): title, `**File:**`, an image link to the chart under `images/`, "What this chart shows", the reading, and a limitations section. Every doc states that the projection is conditional and composition-only; `forecast_demand_type_shares.md` and any occupation reference state the allocation caveat. Measured figures in them go through Step 3's skill.

- [x] **Step 3: Record measured results**

Invoke the `record-measured-result` skill. Add `docs/framework.md` § Composition Forecast (after § Demand Composition Model) with: the method in four stages; the Stage 2 table per instrument (main + sensitivity rows) from `forecast_slope_decomposition.csv`; the Task 6 checkpoint decision; the splice multipliers; headline 2030 sector shifts under the reference scenario with bootstrap bands; bootstrap skip counts; the leave-one-period-out ranges; the weaknesses from the spec in order. Every number comes from `data/output/*.csv` of the latest run.

- [x] **Step 4: Update CLAUDE.md and docs/seeds.md**

CLAUDE.md Phase 2 list, after item 5:

```markdown
6. `forecast_composition` — projects sector composition to 2030 from a decomposition of how strongly the dynamic score has sorted sector shares each year (structural + unemployment cycle + BTOS AI adoption), under unemployment and adoption scenarios; occupations receive an allocation of their sector's change. Runs last. See `docs/framework.md` § Composition Forecast.
```

CLAUDE.md Seeds table row:

```markdown
| `btos_ai_use.csv` | every run (census.gov `National.xlsx`, new wording only) | `cp data/output/btos_ai_use.csv seeds/` by hand — `release.yml` does not promote it |
```

`docs/seeds.md` paragraph: the two wordings, why the old wording exists only in the seed (census.gov's live file drops it; first built from Anthropic's republished copy in `Anthropic/EconomicIndex` `release_2025_09_15/data/input/BTOS_National.xlsx`), the merge rule (fetched row wins per `smpdt` × wording), CI fail-soft, and hand promotion.

- [x] **Step 5: Audit the prose**

Dispatch the `claims-auditor` agent on `docs/framework.md`, the six new chart docs and `docs/outputs.md`; dispatch the `inference-reviewer` agent on the same files. Fix every confirmed finding; record any finding you disagree with, and why, in the Deviations log.

- [x] **Step 6: Commit the images and verify**

```bash
cp data/output/visualizations/forecast_*.png docs/charts/images/
cp data/output/visualizations/chart_manifest.json docs/charts/images/
uv run check_charts.py
uv run pytest tests/
uv run ruff check . && uv run ruff format --check .
```

Expected: `check_charts.py` exits 0; all tests pass; ruff clean. If `check_charts.py` reports other charts stale because the local run differs from the committed manifest, report them rather than committing their images in this branch.

- [ ] **Step 7: Mark the plan complete and commit**

Add `**Status:** complete — PR #<n>` under this plan's title once the PR is open, then:

```bash
git add docs/ CLAUDE.md docs/charts/images/ docs/superpowers/plans/2026-10-02-decomposed-slope-forecast.md
git commit -m "Document the composition forecast, its measured results and charts"
```

---

## Deviations log

*(Entries added during execution: what changed from the plan, why, and which task.)*

- **Task 6 checkpoint (2026-10-02) — instruments disagree on β_AI; decision: continue, show both.**
  Main specification, logistic adoption backcast:

  | Instrument | β_structural | β_cycle | β_AI | n | R² |
  |---|---|---|---|---|---|
  | OEWS 1999–2025 | +0.0652 (se 0.0068, p < 0.0001) | +0.0523 (se 0.0079, p < 0.0001) | **+0.6666** (se 0.1812, p = 0.0016) | 22 | 0.797 |
  | CPS rollup 1983–2025 | +0.0918 (se 0.0134, p < 0.0001) | +0.0127 (se 0.0182, p = 0.49) | **−1.0684** (se 0.5001, p = 0.039) | 40 | 0.112 |

  β_AI sensitivity: OEWS +0.598 to +0.672 across `with_excluded_periods` and the linear/Gompertz backcasts (all p ≤ 0.002); CPS −1.020 to −1.065 across backcasts (p ≤ 0.04), but −0.341 (p = 0.19) with the partial-year 2025→26 period included. Mean period slope pre-2023 vs AI era: OEWS 0.064 → 0.153; CPS 0.091 → 0.003. Splice multipliers: linear 0.560, logistic 0.631, Gompertz 0.613; exponential rejected (159% by 2030-12).
  The spec's continue condition (β_AI positive, p < 0.10, on at least one instrument) was met by OEWS. It did not anticipate CPS being significant in the opposite direction. The human partner chose to continue as specified, with each instrument driving its own forecast and the disagreement shown side by side. Docs must lead with the disagreement and with the extrapolation caveat: adoption reaches 0.14 in the estimation periods but 0.58 (logistic) by December 2030.
