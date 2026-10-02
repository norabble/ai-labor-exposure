# CPS Monthly Backfill and Seasonally Adjusted Forecast Start — Design

**Status: approved design, not yet planned.** Implements Option B of
`docs/cps_data_expansion.md` (steps 1–4), with the A-19 page kept as a cross-check.

**Goal:** give the CPS A-19 panel every month from January 2020 onward instead of the
scattered months the rolling A-19 page happened to show when it was fetched, and use
that history to run the CPS composition forecast from two starts — the raw latest
month and the same month seasonally adjusted — side by side. Add a project skill that
walks through each monthly update.

---

## Why

- `seeds/cps_a19_panel.csv` holds 2025-04, -06, -08, -09 and 2026-04, -06, -08, -09.
  A-19 shows only the latest month and the same month a year earlier, so May, July
  and every month before April were never captured.
- The CPS forecast starts from the latest A-19 month's sector shares. A-19 is not
  seasonally adjusted, and the start moves every month. Moving it from August to
  September 2026 raised Education, Training, and Library's starting share by
  0.57 pp; the same August→September step in 2025 raised it by 0.39 pp. That is
  the school year, not the labor market, and it carries through to the 2030 level.
- Anchoring to a fixed calendar month would remove the seasonality but discard the
  recent months that make CPS worth having. A seasonally adjusted latest month keeps
  both. The raw start stays alongside it so the unadjusted data remains visible and
  the adjustment's effect is always measurable.

---

## Decisions

| Question | Decision |
|---|---|
| Second forecast start | Seasonally adjusted latest month, reported **alongside** the raw latest month; raw stays primary |
| Monthly source | BLS public API is the source; the A-19 page is fetched only to cross-check it |
| Backfill depth | 2020-01 onward (post 2018-Census occupation coding); seasonal factors from 2022 onward |
| Seasonal method | Classical ratio-to-centred-moving-average, no new dependency |
| `model_signal_over_time` CPS endpoints | Only endpoints whose year-earlier month is at or after the OEWS reference month |

---

## Verified facts this design rests on

Checked against the BLS API on 2026-10-02.

- **Series IDs.** 15 groups are `LNU02032453`–`LNU02032467`, in `CPS_TO_SOC_MAJOR`
  order from Management (11) to Personal Care and Service (39). The other seven are
  the leaf series `cps_historical_panel.py` already uses: Sales 41 `LNU02032206`,
  Office 43 `LNU02032207`, Farming 45 `LNU02032209`, Construction 47 `LNU02032210`,
  Installation 49 `LNU02032211`, Production 51 `LNU02032213`, Transportation 53
  `LNU02032214`.
- **Agreement.** All 176 rows of the current seed equal the API values exactly.
- **October 2025 does not exist.** CPS was not collected during the federal shutdown;
  the API returns no observation. It stays missing — never interpolated.
- **API key.** `BLS_API_KEY` is set in `.env` and as a CI secret, so registered
  limits apply. One request carries all 22 series.

---

## §1 Data source and panel

**New `download_cps_history.py`.** Pulls the 22 series from 2020-01 through the
current year in one batched POST to the BLS API, sending `BLS_API_KEY` when set,
and writes `data/raw/cps/a19_api_history.csv` in the panel schema
(`month, soc_major, occupation, employed_thousands, source_reference_month`), with
`source_reference_month` set to the latest month in the response. The `M13` annual
average period is excluded. Under CI a failed fetch warns and exits 0; locally it
exits non-zero, matching `download_cps.js`. It runs from `make download-data`, before
`download_cps.js`.

**Series-ID mapping** lives in `cps_panel.py` as `A19_SERIES_BY_SOC_MAJOR`, next to
`CPS_TO_SOC_MAJOR`.

**`cps_panel.load_cps_panel` merge order:** seed → API history → A-19 page.
- API history wins over the seed on collisions (it is the source).
- The A-19 page is a **cross-check**: for every `(month, soc_major)` it shares with
  the API history, the values must be equal or `load_cps_panel` raises `ValueError`
  naming the differing rows. Months the page has and the API history lacks (a run
  where the API was blocked) are merged as today.
- With neither fetch present it uses the seed alone, as today.

**Seed.** Grows from 176 rows to roughly 1,500. Promotion is unchanged — the release
PR, or `cp data/output/cps_a19_panel.csv seeds/` after a local run.

**Since-OEWS window.** `since_anchor` already picks the last panel month at or before
the OEWS reference month; with May 2025 present it becomes May 2025 with no code
change.

## §2 Seasonal factors and the two CPS starts

**`cps_panel.seasonal_factors(panel_df, first_year=2022) -> DataFrame`**, one row per
`(soc_major, calendar_month)` with `factor` and `n_years`:

1. Per group, reindex to a complete monthly range so gaps are explicit `NaN`.
2. Centred 2×12 moving average (a 12-month mean, then a 2-term mean to centre it).
   A window touching any missing month yields `NaN`; no `min_periods` relaxation.
3. Ratio = level ÷ moving average, kept for months from `first_year` onward.
4. Factor = mean ratio per calendar month; `n_years` = how many ratios went in.
5. Scale the twelve factors per group so they average exactly 1.

Any factor with `n_years < 3` raises `ValueError`. Written to
`data/output/cps_seasonal_factors.csv` and printed as a 22 × 12 table.

**Starts.** `forecast_composition.cps_start_shares` gains a `start_basis` argument.
`raw` is today's behaviour. `seasonally_adjusted` divides each group's latest-month
level by its factor for that calendar month; the projection renormalises to shares,
and employment totals use the raw month's total so both starts describe the same
workforce.

**Outputs.** `forecast_sector_paths.csv` and `forecast_sector_stability.csv` gain a
`start_basis` column: `raw` and `seasonally_adjusted` for CPS, `raw` for OEWS (annual
May data, no adjustment). Both CPS starts share coefficients, scenarios, steps,
bootstrap replicates and leave-one-period-out refits; only the start shares differ.
The occupation allocation is OEWS-only and unchanged.

**Charts.** The six existing forecast charts filter to `start_basis == "raw"` and are
otherwise unchanged. One new chart, `forecast_cps_start_basis.png`: per sector, the
2030 change under the reference scenario from each start, side by side, with the
start month's seasonal factor annotated. It has a `docs/charts/` page and an
`outputs.md` row.

**Excluded-period label.** `CPS_EXCLUDED_PERIODS` stops hardcoding "Jan–Aug"; the
reason string is built from the months present for the terminal year.

## §3 Knock-on changes

**`model_signal_over_time` CPS side panel.** Plots one year-over-year endpoint per
panel month whose year-earlier month is at or after the OEWS reference month —
currently May–September 2026. The April 2026 endpoint drawn today is dropped: its
window starts in April 2025, which OEWS already covers. The range advances on its own
as months arrive.

**BLS API cache** (`historical_displacement.fetch_bls_series`). A cache file whose
range includes the current year expires after 24 hours; past-only ranges stay cached
forever. This is what returned August data for the CPS occupation panel after
September was published.

**Update skill**, `.claude/skills/update-cps-monthly/SKILL.md`, for use after each
Employment Situation release (first Friday of the month, sometimes the second):

1. Confirm the new month is in the API.
2. Run `uv run main.py validate composition forecast`. The A-19 cross-check's headless
   Chrome must run unsandboxed.
3. Promote `cps_a19_panel.csv` and `cps_occupation_panel.csv` to `seeds/`.
4. Run `check_charts.py`; copy stale images and the manifest.
5. Update dated figures with the `record-measured-result` skill; gate with the
   `claims-auditor` agent.
6. Commit.

**Docs**, in the same commits as the code: `docs/cps_data_expansion.md` marked
implemented for steps 1–4; `docs/seeds.md` and the CLAUDE.md seeds table;
`docs/outputs.md` rows for `cps_seasonal_factors.csv`, `forecast_cps_start_basis.png`
and the `start_basis` column; `docs/framework.md` § Composition Forecast reports both
starts; the CPS chart pages (`cps_2026_direction.md`, `cps_model_vs_actual.md`,
`composition_model_signal_over_time_cps.md`) for the May 2025 anchor and endpoints.

## Error handling

| Condition | Behaviour |
|---|---|
| A-19 page disagrees with API on a shared month | `ValueError` |
| A start is missing any of the 22 sectors | `ValueError` (unchanged) |
| A seasonal factor rests on fewer than 3 years | `ValueError` |
| API or A-19 fetch blocked, under CI | Warn, exit 0, fall back to seed |
| API or A-19 fetch blocked, locally | Non-zero exit |

## Testing

- Series mapping: 22 unique IDs, keys equal to `CPS_TO_SOC_MAJOR`'s values (offline).
- `download_cps_history` parsing from a recorded API payload: schema, `M13` dropped,
  missing October 2025 absent rather than zero.
- `seasonal_factors`: recovers known factors from a synthetic series; a gap removes
  only the ratios whose window touches it; factors average 1; `n_years < 3` raises.
- `load_cps_panel`: API wins over seed; A-19 mismatch raises; A-19-only months merge.
- `cps_start_shares`: seasonally adjusted shares equal raw ÷ factor, renormalised.
- Forecast outputs carry both `start_basis` values for CPS and only `raw` for OEWS.
- Signal panel endpoint selection excludes endpoints whose year-earlier month
  precedes the OEWS reference month.
- Cache: a current-year file older than 24 hours is refetched; a past-only file is not.

## Out of scope

- Unemployment rate by occupation (`docs/cps_data_expansion.md` step 5).
- Pre-2020 history and the 2020 coding break.
- Seasonally adjusting the since-OEWS validation window; it keeps its disclosed
  caveat, and the year-over-year window remains the seasonally clean comparison.
