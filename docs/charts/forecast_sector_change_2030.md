# Composition Projection: Sector Share Change by 2030

**File:** `forecast_sector_change_2030.png`

![Projected sector share change to 2030](images/forecast_sector_change_2030.png)

## What this chart shows

**The two panels project opposite moves.** OEWS and CPS estimate the AI-era change in the score's slope with opposite signs, so they project the same sectors moving in opposite directions. Both apply that AI term at about four times the highest adoption it was estimated on.

This is each sector's projected change in employment share, in percentage points, from the start date to 2030. It uses the reference scenario: steady unemployment and logistic AI adoption. Sectors are ordered by the OEWS projection, and the two panels share that order.

- **OEWS:** May 2025 → May 2030, from OEWS sector totals.
- **CPS:** August 2026 → December 2030, from CPS Table A-19. A-19 is a different CPS product from the 22-sector rollup the CPS slope is estimated on. Their 2025 sector shares differ by 0.14 pp on average and at most 0.37 pp (measured 2026-10-02).

Each sector shows:
- **Dot:** the projected change, blue for a gain and red for a loss.
- **Blue band:** the 5th–95th percentile across 2,000 bootstrap resamples of the historical periods. The 95 (OEWS) and 91 (CPS) replicates that could not identify the AI term were skipped, which narrows the band.
- **Grey band:** sector noise, the typical yearly scatter of a sector around the fitted slope, accumulated over the horizon.

It is a conditional projection, not a forecast of employment levels. Total employment is held at its start level, so only shares move.

## Reading

Measured 2026-10-02 from `forecast_sector_paths.csv` (filter `unemployment_scenario == "steady"` and `adoption_fit == "logistic"`, n = 22 sectors) and `forecast_sector_stability.csv`.

| Sector | OEWS change (band; LOO) | CPS change (band; LOO) |
|---|---|---|
| Office and Administrative Support | −3.26 (−5.83, −2.66; −4.45 to −2.93) | +3.47 (−1.10, +5.59; +0.70 to +4.35) |
| Healthcare Practitioners and Technical | +0.99 (+0.79, +2.02; +0.88 to +1.43) | −0.88 (−1.34, +0.32; −1.08 to −0.19) |
| Management | +0.69 (+0.56, +1.34; +0.62 to +0.98) | −1.10 (−1.72, +0.38; −1.37 to −0.24) |
| Sales and Related | −0.40 (−0.89, −0.32; −0.61 to −0.36) | +0.42 (−0.18, +0.61; +0.10 to +0.51) |

LOO is the range across leave-one-period-out refits.

**Only the signs are comparable across the panels, not the magnitudes.** The horizons differ (60 against about 52 months), the employment bases differ, and CPS reaches SOC sectors through a crosswalk.

**The bands show one result repeated, not 22 independent ones.** Every sector's projection is the same slope path multiplied by that sector's fixed score. The OEWS band excludes zero for 21 of 22 sectors; the exception, Farming, Fishing, and Forestry, has a score at the employment-weighted mean. The CPS band excludes zero for 1 of 22. OEWS's narrower bands reflect its smaller β_AI standard error (0.18 against 0.50). They do not show that OEWS is the right instrument, and neither band covers the disagreement between instruments.

**Leave-one-period-out refits keep every tabled sector's sign, but CPS sizes depend on single periods.** Office and Administrative Support's CPS projection ranges from +0.70 to +4.35 pp when one period is dropped.

## Limitations

- The AI term rests on three periods per instrument and is extrapolated well beyond its adoption range (see `forecast_btos_adoption.md`). The projected 2030 slopes lie outside the historical range on both instruments.
- The bands exclude model-specification uncertainty.
