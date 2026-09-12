# Demand Composition Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: experimental.** This is a research probe that is expected to be iterated on or discarded. Every artifact it adds is additive and separable — new modules, new stage, new outputs, new seed. No existing model output changes. Tearing it out should mean deleting files and one `STAGES` entry, not unpicking edits.

**Goal:** Test whether the Bounded/Unbounded/Adversarial taxonomy is a *general* theory of how productivity shocks route into labor demand, rather than an AI-specific one, by building a third model that keeps the dynamic model's demand-composition machinery and replaces its AI-penetration input with an economy-wide historical displacement rate.

**Architecture:** A new `synthesize_composition.py` computes `gross_displacement` from demand-type composition alone, scaled by a single economy-wide scalar `D`, and routes it through the existing equilibrium functions in `synthesize_dynamic.py`. A new `historical_displacement.py` estimates `D` per year from the BLS Displaced Worker Supplement and labor productivity. A new `download_dws.py` fetches and accumulates the DWS tables into a committed seed panel. Validation runs on two fronts: the existing employment-growth machinery across 2005→2025, and a new independent test of predicted displacement against *measured* displacement from DWS Table 5.

**Tech Stack:** Python 3.12, pandas, scipy, requests (already a dependency via `download_data.py`). No new dependencies. No Puppeteer — unlike OEWS, both the BLS public API and the DWS news-release HTML answer plain HTTP with a User-Agent header (verified 2026-09-11).

---

## Why this model exists

`docs/model_vs_observed_exposure.md` § "Confound: pre-existing sector composition" already records the observation this model is built to test:

> the dynamic model's sector-level r was already elevated **before AI**: +0.40 to +0.50 in 2006→09 and +0.37 in 2017→18… The AI-era values (+0.53 in 2023→24, +0.48 in 2024→25) sit inside that pre-AI range, not above it.

That is currently filed as a threat to AI attribution. If the taxonomy is a general theory of productivity-shock pass-through, it is instead the expected result. This model makes that claim testable by removing AI data from the predictor entirely.

`docs/framework.md` § "Classifier Note" proposes validating the taxonomy against historical demand dynamics and leaves it unimplemented; § "Future investigation: the business cycle" observes anecdotally that the composition fits sector growth best when unemployment is rising. This plan implements the first and makes the second measurable.

## The model

```
gross_displacement_o   = D · [(1 − BOUNDED_REBOUND)·pct_bounded_o
                            + (1 − ADVERSARIAL_REBOUND)·pct_adversarial_o]
absorption_capacity_o  = pct_unbounded_o + pct_adversarial_o          (unchanged)
K                      = Σ E·gross_displacement / Σ E·absorption_capacity
net_employment_change_o = K·absorption_capacity_o − gross_displacement_o
```

This is the dynamic model with per-task penetration `p_t` replaced by a uniform economy-wide rate `D`. The rebound constants are reused unchanged from `synthesize_impacts.py`, so the Adversarial residual-displacement term survives. The predictor contains **no technology-exposure information of any kind** — it is a strictly harder test than the AI model faces.

### Two properties that must hold, and are the basis of the tests

**1. `D` cancels from every cross-sectional correlation.** Because `K = D·κ` where `κ = Σ E·pct_bounded_weighted / Σ E·absorption_capacity` is pure composition, `net_o = D·(κ·absorption_capacity_o − displacement_shape_o)`. The whole vector scales with `D`, and Pearson r is scale-invariant. Verified numerically: corr(D=0.05, D=0.42) = 1.0 to 12 decimal places, conservation residual < 1e-8 at both.

This is what makes the design non-circular. A single economy-wide scalar cannot manufacture a cross-sectional pattern across 22 sectors or 770 occupations — `D` sets the amplitude, the taxonomy sets the shape, and only the shape is tested.

**2. It is a distinct model, not a relabel.** Against the existing AI-penetration score across 770 occupations: Pearson r = 0.759, Spearman ρ = 0.803. Related but substantially reordered, because stripping penetration lets occupations AI has not yet touched re-enter with their full compositional weight (Chief Executives has `bounded_exposure_contribution` = 0.0 despite `pct_bounded` = 0.28).

### What `D` is actually for

Since `D` cancels from r, it is **not** needed for the cross-sectional validation. It is needed for exactly two things:

- **Amplitude** — `net_employment_change_workers` in levels, testable against measured displacement counts.
- **Time variation** — whether per-period fit strength tracks `D_t`.

Implementers should not be surprised that Task 4's correlations are identical for any positive `D`. That is the design working.

## Choosing D: what was measured and rejected

Four candidates were evaluated against BLS data 2005–2024 (n=20) before this plan was written. Recorded so the choice is not relitigated:

| Candidate | r vs U level | r vs ΔU | CV | Verdict |
|---|---:|---:|---:|---|
| CPS permanent job losers (`LNS13025699`) | **0.944** (p<1e-4) | 0.257 | 0.50 | **Rejected.** Is the business cycle. Purging U leaves 11% of variance — too thin at n=20 |
| BED gross job loss rate (`BDS…04RQ5`) | 0.383 | **0.860** | 0.12 | Rejected. Cyclical in the derivative; ~23%/yr is ordinary churn, not displacement |
| BED excess reallocation | 0.170 | 0.531 | **0.055** | Rejected as a driver. Least cyclical but nearly constant (11.40–13.55 over 20 years); its only trend is declining business dynamism |
| Labor productivity growth (`PRS85006092`) | **0.220** | 0.782 | **1.07** | **Secondary.** Correct theory — x% output/hour ⇒ x% of hours redundant at constant output — but volatile and **negative in 2 of 20 years**, and D<0 inverts the model. Requires 3-year centered moving average |
| **DWS displacement rate** | — | — | — | **Primary.** The only candidate that isolates structural displacement *by definition* rather than by statistical purging |

The DWS breaks displacement into plant closing / insufficient work / **position or shift abolished**. That third category is technological and organizational displacement with the cyclical and demand-shock categories already removed — no regression, no residualization, no variance destroyed. Magnitude sanity check: the current release reports 3,324k long-tenured displaced over three years against ~160M employed ≈ 0.7%/yr, landing in the same range as smoothed productivity growth (~2%/yr) by a fully independent route.

Its weaknesses are real and must be stated in the docs: biennial (~10 observations 2005–2025), overlapping 3-year lookback windows so consecutive observations are not independent, and a headline rate covering long-tenured (3+ years) workers only.

---

## Global Constraints

- Coding standards from `CLAUDE.md`: no generic abbreviations (`df`, `res`, `tmp`, `val` forbidden — use `displacement_panel_df`, `composition_model_df`); names carry domain meaning; every module has a docstring naming purpose, inputs, outputs (ruff `D100`).
- Lint: `.venv/bin/ruff check <files>` and `.venv/bin/ruff format <files>`. Line length 140. Run on the specific files touched, not `.` (a protected path under `.claude/` breaks a repo-wide format run).
- Tests: `.venv/bin/python -m pytest tests/ -q`. New tests go in `tests/test_composition_model.py`. Note `synthesize_dynamic.py` currently has **zero** test coverage — do not assume existing tests will catch a regression in the functions this plan reuses.
- Run Python through `.venv/bin/python`, not `uv run`.
- **Never modify** `data/raw/`, `seeds/classified_all_tasks.csv`, `seeds/cps_a19_panel.csv`, or `seeds/soc_crosswalks/`.
- **Existing outputs must not change.** `occupation_dynamic_model_report.csv`, `occupation_exposure_report.csv`, `equilibration_sensitivity.csv`, `sector_jackknife.csv` and every existing PNG must be byte-identical after this work. Task 3 includes an explicit regression check.
- Every new output gets a row in the `CLAUDE.md` "Outputs Reference" table before the task creating it is committed. The new seed gets a sentence in the "Release Pipeline" section following the `seeds/cps_a19_panel.csv` convention.
- Commit message trailers, exactly:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_013bEiSHHYq2qvHPVxwvFAbt
  ```
  Commit with `PATH="$PWD/.venv/bin:$PATH"` so the pre-commit hook finds ruff.

---

### Task 1: DWS acquisition and seed panel

- [ ] Create `download_dws.py`. Fetch the Worker Displacement news release tables with `requests` and a descriptive User-Agent. Verified reachable 2026-09-11:
  - `https://www.bls.gov/news.release/disp.toc.htm` — table index
  - `https://www.bls.gov/news.release/disp.t02.htm` — reason for job loss (isolates "position or shift abolished")
  - `https://www.bls.gov/news.release/disp.t05.htm` — **displaced workers by occupation of lost job**
  - `https://www.bls.gov/news.release/disp.t08.htm` — total displaced (all tenures)
- [ ] Parse to long form. Table 5 publishes 10 leaf occupation groups nested under 5 broad ones — take the **leaf** rows only (Management/business/financial, Professional and related, Service, Sales and related, Office and administrative support, Farming/fishing/forestry, Construction and extraction, Installation/maintenance/repair, Production, Transportation and material moving). Dashes mean suppressed (base < 75,000); parse to NaN, never 0.
- [ ] Add `DWS_TO_SOC_MAJOR: dict[str, list[str]]` mapping each leaf group to its SOC major codes. Follow the shape of `CPS_TO_SOC_MAJOR` in `cps_panel.py:~30` (lowercased key lookup), but note this is a **many-to-many** mapping — "Professional and related occupations" spans SOC 15, 17, 19, 21, 23, 25, 27, 29 — so it cannot reuse that dict.
- [ ] Write `seeds/dws_displacement_panel.csv`, accumulating across releases exactly as `seeds/cps_a19_panel.csv` does. Columns: `survey_year, table, group_name, soc_majors, displaced_thousands, reason, tenure_class`.
- [ ] **Risk — archive discovery.** The release page rolls; `https://www.bls.gov/news.release/archives/disp_08282024.htm` returned 404, so the archive URL pattern is unknown. Spend a bounded effort locating prior releases (check `disp.toc.htm` for archive links, and `https://www.bls.gov/schedule/news_release/disp.htm`). **If only the current release is reachable, proceed with a single survey year** — `D` cancels from every cross-sectional correlation, so partial coverage degrades only Task 6's time-variation test, not the headline result. Record what was reachable in the module docstring.
- [ ] `download_dws.py` must warn and `exit 0` under CI when the fetch fails, matching `download_cps.js`, so the pipeline still renders from the seed alone.
- [ ] Add `uv run download_dws.py` to the Makefile `download-data` target, after `download_cps.js`.
- [ ] Tests: parsing a committed HTML fixture yields the expected 10 leaf groups; suppressed dashes become NaN; the SOC mapping covers all 22 majors exactly once.

### Task 2: Estimate D

- [ ] Create `historical_displacement.py`. Public surface:
  ```python
  def load_dws_panel(seed_path: str = "seeds/dws_displacement_panel.csv") -> pd.DataFrame | None
  def dws_displacement_rate(displacement_panel_df, employment_by_year, reason: str | None = None) -> pd.Series
  def productivity_displacement_rate(smoothing_years: int = 3) -> pd.Series
  def economy_displacement_rate(source: str = "dws") -> pd.Series
  ```
- [ ] `dws_displacement_rate` returns `displaced_thousands / employment_thousands / 3` (the 3-year lookback annualized), indexed by year. Passing `reason="position or shift abolished"` restricts to the structural category.
- [ ] `productivity_displacement_rate` fetches `PRS85006092` from `https://api.bls.gov/publicAPI/v2/timeseries/data/` (POST, JSON, no key required — verified) and applies a centered moving average. **Must clip at zero and warn**: raw annual values were −1.3% (2022) and −0.3% (2011), and a negative `D` inverts every prediction.
- [ ] The unregistered API caps at 10 years and 25 series per request; chunk the year range.
- [ ] Cache the API response under `data/raw/bls_api/` so re-runs do not re-fetch. Fall back to the cache when the network is unavailable.
- [ ] Write `data/output/historical_displacement_rate.csv` — columns `year, displacement_rate, source, n_observations`.
- [ ] Tests: a negative productivity input is clipped and warned, not propagated; DWS rate arithmetic against a hand-computed fixture; loaders return `None` with a warning rather than raising when files are absent (match `load_sector_growth_table` in `validate_bls.py:1076`).

### Task 3: The composition model

- [ ] Make one **backward-compatible** change to `synthesize_dynamic.py:137-139`, which currently hardcodes the displacement sum. Add a parameter with a default that preserves today's behavior exactly:
  ```python
  def compute_dynamic_equilibrium(
      merged_occupation_df: pd.DataFrame,
      employment_col: str,
      displacement_components: tuple[str, ...] = ("bounded_exposure_contribution", "adversarial_exposure_contribution"),
  ) -> pd.DataFrame:
  ```
  This is the only edit to existing model code in the plan. Do **not** alias the new columns to the AI column names — `CLAUDE.md` forbids misleading names.
- [ ] Create `synthesize_composition.py`:
  ```python
  def compute_composition_displacement(occupation_df, displacement_rate: float) -> pd.DataFrame
  def build_composition_model(occupation_df, employment_col, displacement_rate) -> pd.DataFrame
  ```
  `compute_composition_displacement` adds `composition_bounded_displacement` and `composition_adversarial_displacement` using `BOUNDED_REBOUND` / `ADVERSARIAL_REBOUND` imported from `synthesize_impacts.py` — do not redefine the constants.
- [ ] `build_composition_model` calls `attach_absorption_capacity` (`synthesize_dynamic.py:83`) then `compute_dynamic_equilibrium` with `displacement_components=("composition_bounded_displacement", "composition_adversarial_displacement")`.
- [ ] Do not hardcode the employment column. It is selected dynamically at `validate_bls.py:1323` as `sorted(c for c in ... if c.startswith("TOT_EMP_"))[-1]` and changes with data vintage.
- [ ] Write `data/output/occupation_composition_model_report.csv`.
- [ ] **Regression check (blocking):** re-run `validate` and confirm `occupation_dynamic_model_report.csv`, `equilibration_sensitivity.csv` and `sector_jackknife.csv` are byte-identical to their pre-change state. Capture checksums before editing.
- [ ] Tests in `tests/test_composition_model.py`:
  - `test_score_is_scale_invariant_in_displacement_rate` — shapes at D=0.05 and D=0.42 correlate to 1.0 within 1e-12. This is the non-circularity guarantee; it must be an assertion, not a comment.
  - `test_conservation_holds_at_any_displacement_rate` — employment-weighted sum of `net_employment_change` ≈ 0 for several D.
  - `test_default_displacement_components_preserve_dynamic_model` — calling `compute_dynamic_equilibrium` without the new parameter reproduces the existing result.
  - `test_negative_displacement_rate_is_rejected` — raise `ValueError`, do not silently invert.

### Task 4: Era validation — the headline test

The deliverable is this 2×2, plus whether the difference between rows is statistically distinguishable:

| | pre-2022 | post-2022 |
|---|---|---|
| AI-penetration dynamic model | documented +0.40 to +0.50 | +0.53, +0.48 |
| **composition-only model** | ? | ? |

- [ ] Add the composition score to the signal-over-time charts. `plot_model_signal_over_time` (`validate_bls.py:313`) and `plot_model_signal_over_time_occupation` (`validate_bls.py:641`) already walk all 19 YoY periods 2005→2025, parse both `hist_emp_growth_*` and `emp_growth_*`, and shade COVID and the AI era. Add a fourth line; do not rebuild the traversal.
- [ ] Occupation-level scores reach the harmonized units through `build_unit_scores` (`validate_bls.py:1106`) — reuse it, do not re-derive unit membership.
- [ ] Sector growth must come from `sector_growth_series` / `bls_sector_trends.csv`, never from the survivor mean (`CLAUDE.md` is explicit; detailed pre-2019 codes lose 97% of Computer and Mathematical).
- [ ] Test whether pre-2022 and post-2022 mean r differ, and report the result honestly whichever way it falls. All three outcomes are publishable: era-invariant fit supports the general-theory thesis; AI model pulling ahead only post-2022 isolates a real AI-specific increment; AI model never pulling ahead weakens the AI-specific claim.
- [ ] Write `data/output/composition_model_era_comparison.csv` and `composition_model_signal_over_time.png`.
- [ ] Anachronism caveat, stated in every doc this touches: the demand-type labels come from **2025** O*NET task statements applied backwards. `framework.md:434` already flags this. Reaching further back trades construct validity for statistical power.

### Task 5: Independent displacement validation against DWS

This test never touches employment growth, so circularity is structurally impossible rather than merely avoided. It also isolates the two halves of the model — displacement against DWS, absorption against employment growth — which the existing design cannot do.

- [ ] Aggregate predicted `gross_displacement` to the 10 DWS leaf groups, employment-weighted, using `DWS_TO_SOC_MAJOR`.
- [ ] Compare against observed `displaced_thousands / group employment` from DWS Table 5.
- [ ] Report Pearson and Spearman. **n = 10 — report Spearman alongside Pearson and quote the leave-one-out range**, following the jackknife discipline already established for the n=22 sector results. Do not report a bare r.
- [ ] Run twice: all reasons, and "position or shift abolished" only. The framework predicts the structural-only variant fits better.
- [ ] Write `data/output/composition_model_displacement_validation.csv` and `dws_observed_vs_predicted_displacement.png`.
- [ ] If `seeds/dws_displacement_panel.csv` is absent or covers one year, skip with a warning rather than failing the stage.

### Task 6: Time variation

- [ ] Correlate the per-period sector r series from Task 4 against `D_t`. The prediction — from `framework.md` § "Future investigation: the business cycle" — is that periods of higher economy-wide displacement show stronger demand-type sorting.
- [ ] Use smoothed productivity for `D_t`; DWS is too coarse in time for this test.
- [ ] This test is under-powered (~19 periods, autocorrelated). Report it as a hypothesis check, not a result, and say so in the chart doc.

### Task 7: Wiring and documentation

- [ ] Add a `composition` stage to `main.py` — `STAGES` list and the `runners` dict at `main.py:23-31`, plus the docstring and `--help` epilog. Place it after `synthesize`. Keep it a **separate stage** so the experiment can be run, skipped, or removed independently.
- [ ] Add rows to the `CLAUDE.md` "Outputs Reference" tables for all four new CSVs and all three new PNGs.
- [ ] Add `seeds/dws_displacement_panel.csv` to the "Release Pipeline" section, following the `seeds/cps_a19_panel.csv` wording — the DWS release rolls, so history exists only in the committed panel and a release run must promote it.
- [ ] Add a `docs/framework.md` section: "Demand Composition Model (experimental)". Cover the model, the D-invariance property and why it makes the design non-circular, the D selection evidence table, and the limitations — biennial DWS, n=10 on the displacement test, 2025 labels applied backwards, and the uniform-technology-exposure assumption (the model asserts technology touches all tasks equally, which is false but deliberately minimal).
- [ ] Update `docs/model_vs_observed_exposure.md` § "Confound: pre-existing sector composition" to point at this model as the test of that confound.
- [ ] Add chart docs under `docs/charts/` for each new PNG, matching the existing format.

---

## Verification

```bash
.venv/bin/python -m pytest tests/ -q
.venv/bin/ruff check historical_displacement.py synthesize_composition.py download_dws.py synthesize_dynamic.py main.py tests/test_composition_model.py
.venv/bin/ruff format --check <same files>

# regression: existing outputs unchanged
md5sum data/output/occupation_dynamic_model_report.csv data/output/equilibration_sensitivity.csv data/output/sector_jackknife.csv > /tmp/before.md5
.venv/bin/python main.py synthesize composition validate
md5sum -c /tmp/before.md5

node --check download_cps.js download_bls.js
```

End-to-end: `.venv/bin/python main.py composition` produces `occupation_composition_model_report.csv` with a conservation residual < 1.0 worker and 770 rows; `main.py validate` adds the composition line to both signal-over-time charts.

**Acceptance:** the 2×2 in Task 4 is filled in with real numbers and reported whichever way it falls; existing outputs are byte-identical; the scale-invariance test passes.

## Known risks

1. **DWS archive coverage** (Task 1) — the single riskiest step. Mitigated by `D` cancelling from r: partial coverage costs only Tasks 5 and 6.
2. **n = 10 on the displacement test** (Task 5). Real, unavoidable, must be disclosed rather than engineered around.
3. **Uniform technology exposure.** The model asserts technology touches every task equally — clearly false (1990s software hit routine tasks hardest). It is the deliberately minimal assumption that keeps the test clean. If the model fails, this is the first thing to relax, plausibly by weighting with a Routine Task Intensity index built from the O*NET data already on disk.
4. **The result may weaken the AI-specific claim.** If composition-only fits the AI era as well as the penetration-weighted model, the honest conclusion is that this was always a general theory and AI is one instance. That is a legitimate outcome of the experiment, not a failure of it.
