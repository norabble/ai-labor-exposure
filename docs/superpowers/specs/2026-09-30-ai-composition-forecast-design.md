# AI Composition Forecast to 2030 — Design

**Status: superseded** by `docs/superpowers/specs/2026-10-02-decomposed-slope-forecast-design.md`. Prototyping showed the Economic Index coverage index is flat Jan 2025 → May 2026, so this design would forecast no change by construction; see that spec § Why the earlier design was dropped.

**Goal:** project how occupational employment *composition* would shift from the
most recent data to 2030 if the dynamic labor equilibrium model
(`synthesize_dynamic.py`) is taken as is and the only thing that moves over time is
observed AI exposure. Two versions: one starting from OEWS May 2025 (occupation
level), one starting from the latest monthly CPS A-19 observation (sector level).

This is a conditional projection — "if the model is right and exposure grows along
this curve" — not a displacement prediction. The project goal in CLAUDE.md
(structural exposure score, not a displacement forecast) still holds; the charts
and their docs say so.

---

## Constraints from the request

- **The dynamic model is not modified.** `compute_dynamic_equilibrium` and its
  `net_employment_change` per occupation are consumed unchanged.
- **No general employment trends.** No sector trend extrapolation, no macro
  forecast. Total employment is held at its start-date level; only shares move.
  This matches the dynamic model's own conservation normalization.
- **Time enters only through observed AI exposure**, which is given a fitted growth
  curve, and a calibrated rate that converts exposure into realized composition
  shift.
- **Several growth-function fits are shown**, not one chosen curve.

---

## Why the model needs a time axis

`net_employment_change_o` is a single signed equilibrium shift per occupation. It
says nothing about *how fast* that shift is realized. The forecast supplies the pace
from two measured quantities:

1. **Coverage index `C(t)`** — how widely AI usage has spread across the model's
   tasks at time *t*.
2. **Calibration rate `k`** — how much observed sector composition shift has
   occurred per unit of the equilibrium shift, per unit of coverage, since 2022.

---

## Component 1 — Coverage index `C(t)`

**Source.** The Anthropic Economic Index on Hugging Face
(`Anthropic/EconomicIndex`) publishes task-level Claude usage in six releases,
verified by listing the dataset tree on 2026-09-30:

| Release | Task-level file | Observation window |
|---|---|---|
| `release_2025_02_10` | `onet_task_mappings.csv` | Dec 2024–Jan 2025 |
| `release_2025_03_27` | `task_pct_v2.csv` | ~Feb–Mar 2025 |
| `release_2025_09_15` | `data/output/aei_enriched_claude_ai_2025-08-04_to_2025-08-11.csv` (`onet_task` facet) | Aug 2025 |
| `release_2026_01_15` | `data/intermediate/aei_raw_claude_ai_2025-11-13_to_2025-11-20.csv` | Nov 2025 |
| `release_2026_03_24` | `data/aei_raw_claude_ai_2026-02-05_to_2026-02-12.csv` | Feb 2026 |
| `release_2026_06_26` | `data/aei_claude_ai_2026-06-26.csv` (`onet` category, carries task IDs) | May 2026 |

The four later windows come from the file names and `date_start`/`date_end` columns.
The first two releases' READMEs do not state a window; the values above are from the
accompanying Economic Index reports, and the implementation plan's first task
confirms them and records the source beside each date in `ai_coverage_panel.csv`.

Each release reports a **share** of conversations per task (normalized to 100%), so
volume growth is not observable. What *is* observable and can grow is breadth.

**Definition.** For release *r*:

```
C(r) = Σ_tasks importance_t · 1[usage_share_t(r) ≥ FLOOR]  /  Σ_tasks importance_t
```

over the model's O\*NET tasks (the same task set and importance weights that
`synthesize_impacts.py` uses). `FLOOR` is a module constant, held fixed across
releases. Global geography only (`geo_id` / `geography` = global/`GLOBAL`), Claude.ai
only (the 1P API files are excluded so the population is consistent across all six
releases, the first two of which have no API data).

**Task matching.** Lowercased exact text match, the same rule as
`synthesize_impacts.py`, for releases that carry only task text; task-ID match for
`release_2026_06_26`, with text as fallback. The per-release match rate is written to
the output panel; a release whose match rate falls below the others by more than 10
points raises rather than silently producing a low `C`.

**Anchor.** `C = 0` at 2022-11-30 (ChatGPT public release). This is an assumption,
not a measurement, stated in the chart doc. It gives the curve fits a starting point
the six 2025–26 observations alone cannot pin down.

**Sensitivity.** `C(r)` is also computed at two further floors (half and double the
chosen `FLOOR`) and written to the panel. The main charts use the central floor.

**Downloads.** A new `download_economic_index.py` fetches only the six task-level
files (the 2026 raw files are 90–220 MB; only the `onet`/`onet_task` rows for the
global geography are kept on read). Saved under `data/raw/economic_index/`. In CI the
fetch follows the existing BLS-fetcher convention: warn and exit 0, and the stage
renders from a committed seed.

**Seed.** `seeds/ai_coverage_panel.csv` — one row per release × floor with the
observation date, `C`, and match rate. Aggregates only. Promoted by hand after a
local run (`cp`), recorded in the CLAUDE.md Seeds table and `docs/seeds.md`.

---

## Component 2 — Growth fits

Fit `C(t)` over the anchor plus six releases with four common growth functions, all
constrained to `0 ≤ C ≤ 1`:

| Fit | Form | Notes |
|---|---|---|
| Linear | `a + b·t` | clipped at 1 |
| Exponential | `a·e^{b·t}` | clipped at 1 |
| Logistic | `L / (1 + e^{−b(t − t0)})`, `L ≤ 1` | saturating |
| Gompertz | `L · e^{−β e^{−b t}}`, `L ≤ 1` | saturating, asymmetric |

Fitted with `scipy.optimize.curve_fit` with bounds. A fit that fails to converge is
reported and omitted from the charts, never silently replaced. Each fit is
evaluated monthly from its instrument's start date to 2030-12.

With seven points the four families cannot be statistically separated. **The spread
across fits is the result**; no fit is labelled "central".

---

## Component 3 — Calibration rate `k`

Per instrument, at sector level (22 SOC major groups):

```
relative_growth_s = (share_s(end) − share_s(2022)) / share_s(2022)
predicted_s       = C(end) · net_employment_change_s
relative_growth_s ≈ k · predicted_s            (OLS through the origin)
```

where `net_employment_change_s` is the employment-weighted mean of
`net_employment_change_o` within sector *s*, and `C(end)` is the fitted `C` at the
instrument's end date (read from each fit, so `k` is fit-specific).

- **OEWS:** shares from `bls_sector_trends.csv`, 2022 → 2025.
- **CPS:** shares from `cps_a19_panel.csv` / `cps_occupation_panel.csv` major-group
  series, 2022 annual average → latest 12-month average ending at the latest month
  (avoids seasonality in a single month).

Reported per instrument and fit: `k`, its 95% CI, and the leave-one-sector-out range
(same jackknife convention as `compute_sector_jackknife`). The projection uses `k`
and also its CI bounds, so the charts show calibration uncertainty separately from
growth-fit uncertainty.

Known confound, stated in the chart doc: 2022 → 2025 sector growth includes
post-COVID recovery, which the model does not represent.

---

## Component 4 — Projection

With the model output untouched:

```
raw_share_o(t) = share_o(start) · (1 + k · [C(t) − C(start)] · net_employment_change_o)
share_o(t)     = raw_share_o(t) / Σ raw_share(t)
employment_o(t) = share_o(t) · total_employment(start)
```

- **OEWS version** — start May 2025, the 770 occupations in
  `occupation_dynamic_model_report.csv`, `TOT_EMP_2025` as start employment. Rolled up
  to 22 sectors and to `dominant_demand` (the label is carried from the model report,
  never re-derived from projected shares — projection changes employment, not task
  composition).
- **CPS version** — start at the latest A-19 month (currently 2026-08), 22 sectors,
  `net_employment_change_s` rolled up from the model report by employment weight
  using OEWS 2025 weights. Monthly path.

Grid: {4 growth fits} × {k, k_low, k_high} × {OEWS, CPS}.

**Output CSVs** (`data/output/`):
- `ai_coverage_panel.csv` — observed `C` per release and floor.
- `ai_coverage_fits.csv` — monthly fitted `C(t)` per fit, 2022-11 → 2030-12, plus fit
  parameters.
- `forecast_calibration.csv` — `k`, CI, jackknife range per instrument × fit.
- `forecast_occupation_2030.csv` — OEWS version, per occupation × fit × k-bound:
  start and 2030 employment and share.
- `forecast_sector_path.csv` — per instrument × sector × fit × k-bound × month.

---

## Component 5 — Charts

All saved through `chart_manifest.save_figure`, each with a row in
`docs/outputs.md` and its own `docs/charts/<name>.md` (the existing one-doc-per-chart
convention):

1. `forecast_coverage_fits` — six observed releases plus the anchor, four fitted
   curves to 2030, floor-sensitivity band.
2. `forecast_calibration` — sector relative growth vs `C(end)·net_employment_change`,
   one panel per instrument, fitted slope `k`.
3. `forecast_sector_change_2030` — share-point change by 2030 per sector, one marker
   per growth fit, `k` CI as whiskers; OEWS and CPS side by side.
4. `forecast_demand_type_shares` — employment share by `dominant_demand`, 2025 →
   2030, one line per fit (OEWS).
5. `forecast_occupation_movers` — top 15 gaining and losing occupations by 2030
   share change (OEWS), range across fits.
6. `forecast_cps_sector_paths` — monthly sector-share paths from the latest CPS
   month to 2030-12, small multiples of the largest-moving sectors.

---

## Pipeline integration

- New module `forecast_composition.py` (docstring per D100), new stage `forecast`
  appended to `STAGES` in `main.py` after `composition`. It reads
  `occupation_dynamic_model_report.csv`, written by `validate`.
- `download_economic_index.py` wired into `make download-data` and `release.yml`'s
  download step.
- Measured figures (`k`, fitted `C(2030)`, headline sector shifts) go into a new
  `docs/framework.md` § AI Composition Forecast via the `record-measured-result`
  skill, and are checked by `claims-auditor` and `inference-reviewer` before commit.

---

## Testing

In `tests/test_forecast_composition.py`:
- Coverage index on a synthetic task set: floor inclusion, importance weighting,
  match-rate guard raises.
- Each growth fit: monotone non-decreasing and within [0, 1] over 2022–2030 on
  synthetic points.
- Projection: shares sum to 1 at every month; `k = 0` and `C(t) = C(start)` both
  reproduce the start composition exactly; sign of share change matches sign of
  `net_employment_change` relative to the employment-weighted mean.
- Calibration: recovers a known `k` from synthetic sector data.

---

## Out of scope

- Any change to `synthesize_dynamic.py`, the rebound constants, or classification.
- Total-employment forecasting and any use of general employment trends.
- Occupation-level CPS projection (A-19 is sector-level only; IPUMS detailed panels
  are annual and not refreshed in CI).
- Choosing a single "best" fit.
