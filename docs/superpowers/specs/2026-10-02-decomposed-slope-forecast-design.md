# Decomposed-Slope Composition Forecast to 2030 — Design

**Status: approved design, not yet planned.** Supersedes
`docs/superpowers/specs/2026-09-30-ai-composition-forecast-design.md` (see § Why the
earlier design was dropped).

**Goal:** project how the sector — and, by allocation, occupation — composition of
employment would shift from the latest data to 2030, using the dynamic labor
equilibrium model's score unchanged and a forecast built only from relationships
this project has measured. Two versions: OEWS (start May 2025) and CPS (start at the
latest A-19 month, currently August 2026).

This is a conditional projection under stated scenarios, not a displacement
prediction. CLAUDE.md's project goal still holds and the chart docs say so.

---

## Why the earlier design was dropped

The 2026-09-30 design paced the model's one-shot equilibrium with a task-coverage
index built from the Anthropic Economic Index. Prototyping it on all seven
observations (Jan 2025 → May 2026) showed the index is flat: importance-weighted
coverage at a 2e-4 share floor read 0.047, 0.047, 0.039, 0.042, 0.043, 0.039, 0.041.
Each release samples ~1M conversations and reports normalized shares above a fixed
15-conversation privacy floor, so breadth measures usage concentration, not adoption
volume. Every growth fit would have saturated by 2025 and forecast no change — an
artifact of the measure. The rethink also recognised that the evidence available is
a cross-sectional relationship whose strength varies over time, and the forecast
should be built from that directly.

---

## What the evidence supports

- **Sector level only.** n = 22. Dynamic-score correlation with annual employment
  growth averages about +0.20 pre-AI (21 periods) and +0.45 in the AI era (3 periods)
  — `docs/framework.md` § Result.
- **The strength decomposes.** `decompose_fit_strength` (Fisher-z units, dynamic
  score): intercept +0.208 (p < 0.0001), change in unemployment +0.057 (p = 0.062),
  AI era +0.272 (p = 0.0052).
- **No occupation-level signal** is detectable in current BLS data.

A correlation has no magnitude; a forecast needs one. This design moves the existing
decomposition from correlation units to **slope units**.

---

## Constraints

- **The dynamic model is not modified.** The score is
  `occupation_dynamic_model_report.csv`'s `net_employment_change`, as written by
  `validate`.
- **Composition only.** Total employment is held at its start-date level; only
  shares move. No total-employment forecast and no sector trend extrapolation.
- **Scenarios, not forecasts, for exogenous drivers.** The unemployment path and the
  adoption path are stated assumptions, each shown in more than one variant.

---

## Stage 1 — Cross-sectional slope per historical period

For each consecutive year pair *t* and the 22 SOC major sectors *s*:

```
relative_growth_s,t = α_t + β_t · score_s + ε_s,t
relative_growth_s,t = growth_s,t − total_growth_t
score_s             = employment-weighted mean of net_employment_change_o within s
                      (OEWS 2025 weights)
```

Ordinary least squares, unweighted across sectors (matching the existing sector
correlations, which are unweighted). Per period, record `β_t`, its standard error,
and the residual standard deviation `σ_t`.

**Histories** — each instrument is estimated on its own history and drives its own
forecast:

| Instrument | Source | Periods | Notes |
|---|---|---|---|
| OEWS | `bls_sector_trends.csv` major-group totals | 1999→2000 … 2024→2025 | 2009→2010 and 2018→2019 are SOC-revision level breaks — excluded |
| CPS | `cps_major_rollup_trends.csv` | 1983→1984 … 2024→2025 | 2025→2026 excluded: 2026 averages Jan–Aug only |

COVID periods are excluded from the Stage 2 regression using
`composition_era_validation.COVID_PERIODS` as is (`2019_2020`, `2020_2021`), matching
`decompose_fit_strength`; their `β_t` is still recorded and charted.

Excluding the two OEWS SOC-revision periods is a **departure** from
`decompose_fit_strength`, which keeps them: a level break moves occupations between
sectors, which shows up as relative growth the score did not cause. Stage 2 is also
run with them included and reported as a sensitivity row, so the departure's effect
is visible.

---

## Stage 2 — Decompose the slope over time

```
β_t = β_structural + β_cycle · ΔU_t + β_AI · A_t + ν_t
```

- `ΔU_t` — change in the annual mean unemployment rate across the period, from
  `unemployment_change_by_period` (`LNS14000000`), reused unchanged.
- `A_t` — AI adoption level at the period's end year (annual mean), from Census BTOS
  (Component: Adoption below). `A_t = 0` for every period ending before 2023.
- Weighted least squares with weights `1 / se(β_t)²`.

Recorded per instrument: the three coefficients, standard errors, p-values, R², n.

**Checkpoint (blocking).** The AI-era increment is significant in correlation units;
it is not guaranteed in slope units. After Stage 2 is first run on real data, the
implementation stops and reports `β_AI` with its p-value for both instruments. If
`β_AI` is not positive with p < 0.10 on at least one instrument, the human partner
decides whether to continue with a structural + cycle forecast only, change the
specification, or stop. The plan must place this as its own task with no code after
it until the decision is recorded in the plan's Deviations log.

---

## Component: Adoption `A_t` (Census BTOS)

**Source.** `https://www.census.gov/hfp/btos/downloads/National.xlsx`, sheet
`Response Estimates`, Question ID 7, answer `Yes`; dates from sheet
`Collection and Reference Dates`. Verified fetchable without a browser on
2026-10-01.

**Two wordings.** BTOS changed the question at the end of 2025:

| Wording | Periods | Range |
|---|---|---|
| "…use AI in producing goods or services?" | 2023 cycle 19 → 2025 cycle 17 (biweekly) | 3.8% → 9.7% |
| "…use AI in any of its business functions?" | 2025 cycle 24 → latest (2026 cycle 19 at verification) | 17.2% → 23.8% |

The live file carries only the new wording. The old-wording series is taken from the
copy Anthropic republished in `Anthropic/EconomicIndex`
`release_2025_09_15/data/input/BTOS_National.xlsx`, and committed as an aggregate
seed, `seeds/btos_ai_use.csv` (date, wording, percent, standard error). The new
wording is refreshed from census.gov each run and merged with the seed.

**Splice.** Each growth fit includes a multiplicative level parameter `m` applied to
the old-wording points, so the old series is placed on the new wording's scale by
the fit itself, not by a separate assumption. `m` is reported.

**Growth fits**, on biweekly points, `0 ≤ A ≤ 1`, via `scipy.optimize.curve_fit` with
bounds:

| Fit | Form |
|---|---|
| Linear | `a + b·t`, clipped to [0, 1] |
| Logistic | `L / (1 + e^{−b(t − t0)})`, `L ≤ 1` |
| Gompertz | `L · e^{−β e^{−b t}}`, `L ≤ 1` |
| Exponential | `a · e^{b t}` — included only if it stays ≤ 1 through 2030; otherwise reported as rejected |

A fit that fails to converge is reported and omitted, never silently replaced.

**Which `A_t` goes into Stage 2.** Stage 2 needs `A_t` for the AI-era periods,
including 2022→2023, which predates BTOS. The value used is the **logistic** fit's
annual mean, on the new-wording scale — chosen because it is the only fit that is
both bounded and has a plausible pre-2023 tail. The Stage 2 fit is re-run with each
of the other fits' backcasts and reported as a sensitivity row. In the forecast,
every fit is carried through as its own adoption scenario.

---

## Stage 3 — Scenarios to 2030

| Driver | Values |
|---|---|
| `β_structural`, `β_cycle`, `β_AI` | Stage 2 estimates |
| `ΔU_y` | **steady**: 0 every year · **mild recession**: +1.5 pp in 2027, −0.75 pp in 2028 and 2029, 0 in 2030 |
| `A_y` | each surviving BTOS fit's annual mean, 2026–2030 |

```
β_y = β_structural + β_cycle · ΔU_y + β_AI · A_y
```

---

## Stage 4 — Projection

Annual steps from the start year to 2030:

```
share_s(y+1) = share_s(y) · (1 + β_y · score_s)
share_s(y+1) ← share_s(y+1) / Σ_s share_s(y+1)
employment_s(y) = share_s(y) · total_employment(start)
```

The multiplicative update keeps shares positive; renormalisation is required
because `Σ share_s · score_s` is not zero in general — the score's employment
weighting is at occupation level, the update at sector level. The constant `α`
from Stage 1 is absorbed by that renormalisation.

- **OEWS version** — start: OEWS May 2025 sector totals; steps 2025 → 2030.
- **CPS version** — start: the latest A-19 month's sector levels; first step is a
  partial year (the start month to December, `β_y` scaled by the fraction of the year
  remaining), then annual to 2030.

**Uncertainty, kept as two separate layers:**

1. **Parameter uncertainty** — 2,000 bootstrap replicates resampling Stage 1 periods
   with replacement, re-running Stage 2 and the projection each time. Reported as
   the 5th–95th percentile band of each sector's 2030 share.
2. **Sector noise** — a prediction interval adding `σ` (median of Stage 1 `σ_t`)
   per year, accumulated as a random walk in relative growth. Shown only on the
   sector-change chart, labelled as such.

**Stability check** — leave-one-period-out: re-estimate Stage 2 dropping each
historical period in turn and record the range of each sector's 2030 share change.
This measures how much a single year moves the result, not forecast accuracy.

**Occupations** — each sector's projected share change is allocated to its
occupations in proportion to their start-date (OEWS 2025) employment. Output columns
and chart labels call this an allocation. No occupation-specific slope is applied.

---

## Outputs

**CSVs** (`data/output/`):

| File | Contents |
|---|---|
| `forecast_period_slopes.csv` | Stage 1: instrument, period, β_t, se, σ_t, n, ΔU_t, A_t, is_covid, excluded_reason |
| `forecast_slope_decomposition.csv` | Stage 2: instrument, term, coefficient, se, p, R², n, adoption_backcast (logistic plus sensitivity rows) |
| `btos_ai_use.csv` | merged old + new wording biweekly series |
| `btos_adoption_fits.csv` | fit parameters (including splice `m`) and monthly fitted `A(t)` 2022-01 → 2030-12, per fit |
| `forecast_sector_paths.csv` | instrument × scenario (ΔU path × adoption fit) × sector × year: share, employment, bootstrap p5/p95 |
| `forecast_sector_stability.csv` | instrument × sector: leave-one-period-out min/max 2030 share change |
| `forecast_occupation_allocation_2030.csv` | OEWS: occupation × scenario: start and 2030 allocated employment |

**Charts** — all via `chart_manifest.save_figure`, each with a `docs/outputs.md` row
and its own `docs/charts/<name>.md`:

1. `forecast_slope_history` — β_t by period for both instruments, COVID and
   excluded periods marked, fitted Stage 2 line overlaid.
2. `forecast_btos_adoption` — both wordings, spliced points, every fit to 2030.
3. `forecast_sector_change_2030` — 2030 share-point change by sector, steady-state
   logistic scenario as the marker, bootstrap band, sector-noise interval, OEWS and
   CPS side by side.
4. `forecast_sector_paths` — share paths start → 2030 for the eight largest-moving
   sectors, one panel per ΔU scenario, one line per adoption fit.
5. `forecast_demand_type_shares` — employment share by `dominant_demand` (sector
   allocation rolled up through occupations), start → 2030.
6. `forecast_scenario_comparison` — for the six largest-moving sectors, 2030 change
   under each ΔU × adoption combination.

**Measured figures** (Stage 2 coefficients, the checkpoint result, headline 2030
shifts) go into a new `docs/framework.md` § Composition Forecast via the
`record-measured-result` skill, checked by `claims-auditor` and `inference-reviewer`
before commit.

---

## Pipeline integration

- New module `forecast_composition.py` (Stages 1–4, charts) and
  `btos_adoption.py` (fetch, seed merge, splice-aware fits). Both carry a D100
  module docstring.
- New stage `forecast` appended to `STAGES` in `main.py`, after `composition`. It
  reads `occupation_dynamic_model_report.csv` (written by `validate`),
  `bls_sector_trends.csv`, `cps_major_rollup_trends.csv` (written by
  `cps_detailed_validation.run()`, called from the `composition` stage) and
  `cps_a19_panel.csv`.
- BTOS fetch follows the existing BLS-fetcher convention: warn and exit 0 under CI,
  render from the seed alone. New-wording points from a successful fetch are written
  to `data/output/btos_ai_use.csv`; promotion of new points to the seed is by hand
  (`cp`), recorded in CLAUDE.md's Seeds table and `docs/seeds.md`.

---

## Testing

`tests/test_forecast_composition.py` and `tests/test_btos_adoption.py`:

- Stage 1 recovers a known slope from synthetic sector data; excluded periods are
  absent from Stage 2 input but present in the period table.
- Stage 2 recovers known coefficients from synthetic `β_t`; with every period
  pre-2023 it warns and omits `β_AI` rather than raising (mirrors
  `decompose_fit_strength`'s rank check).
- BTOS parsing: `.` becomes missing, percent strings become fractions, both wordings
  are labelled; the splice parameter recovers a known `m` from synthetic data.
- Each growth fit stays within [0, 1] and is non-decreasing over 2022–2030; an
  exponential that exceeds 1 by 2030 is rejected.
- Projection: shares sum to 1 every year and stay positive; `β_y = 0` reproduces the
  start shares exactly; a sector with above-average score gains share when `β_y > 0`.
- CPS partial first year: a start in December gives a first step of 1/12 of a year.
- Occupation allocation sums to the sector total in every sector.

---

## Out of scope

- Any change to `synthesize_dynamic.py`, the rebound constants, or classification.
- Total-employment forecasting; sector trend extrapolation.
- Occupation-specific forecast signal (allocation only).
- A rolling-origin backtest against naive baselines — considered (Option 3) and
  deferred; the leave-one-period-out check is the only stability measure here.
- Updating the score as the penetration pattern changes.
