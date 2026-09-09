# Model Signal Over Time: Occupation-Level Baseline (2005→2025)

**File:** `model_signal_over_time_occupation.png`

![Model Signal Over Time — Occupation Level](images/model_signal_over_time_occupation.png)

## What this chart shows

Occupation-level Pearson r between each model score and YoY BLS employment growth,
plotted as a time series spanning 2005→2025. Unlike the sector-level version
(`model_signal_over_time.png`), no sector aggregation step is applied — each
harmonized SOC unit is one data point. n is annotated along the bottom of the
chart and is now close to constant across periods (see *Harmonized units* below).

| Line | Score | Correct sign | Direction |
|------|-------|:------------:|-----------|
| Rebound-adjusted (blue) | `occupation_exposure` (≥ 0) | negative | More structural exposure → less growth |
| Dynamic net change (orange) | `net_employment_change` (signed) | positive | Predicted gainers actually grow |
| Observed AI coverage (green) | `observed_exposure` (≥ 0) | negative | Higher AI task usage → less growth |

Red shading marks COVID-disrupted periods (2019→20, 2020→21); blue shading marks
the AI era (2022→23 onward); significant periods (p < 0.05) are annotated with r, p, and n.

## Relationship to the sector-level chart

The sector-level chart (`model_signal_over_time.png`) aggregates occupations to 22
SOC major groups first and correlates those 22 group means. That version has low
power (n=22) but suppresses within-group noise by averaging. This chart operates on
harmonized occupation units (n ≈ 695 in every period), giving much higher statistical
power — a much smaller |r| is detectable — but also more noise from individual
occupation volatility.

The two charts are complementary:
- Occupation-level: higher power, noisier, picks up fine-grained structural variation
- Sector-level: lower power, cleaner signal, more interpretable for policy discussion

## What the chart shows

**The dynamic model's occupation-level signal is less clean than at sector level.**
Individual occupation employment growth is driven by many idiosyncratic factors
(firm-specific hiring, licensing changes, local demand shocks) that cancel at the
sector level but add noise at the occupation level. The pre-AI positive r for the
dynamic model (visible in 2005–2009 at sector level) is weaker and less consistent
here, as the sector-composition effect dilutes across hundreds of individually noisy
occupations.

**The rebound-adjusted model shows a consistent negative r in the AI era** (2022→25),
broadly consistent with the sector-level finding. The occupation-level r values are
smaller in magnitude than sector-level because noise dominates within-sector
variation, but the negative direction is persistent.

**COVID disruption (2019→20, 2020→21):** Same pattern as sector level — lockdown
concentration in low-exposure physical occupations temporarily pushes gross models
toward negative r regardless of mechanism.

## Harmonized units

Each point in a period's correlation is a **harmonized unit**, not a raw BLS
occupation code. A unit is a connected component of the published BLS SOC
crosswalks (SOC 2000 → SOC 2010 → SOC 2018) plus the OEWS hybrid structure,
built by `harmonize_soc.py` and written to
`data/output/soc_harmonization_units.csv`. Where a revision split one
occupation into three, or merged three into one, all of those codes land in the
same unit, so the unit means the same thing in 2005 as it does in 2025.

**Why this is necessary.** Anchoring on the 2022 code set and left-joining
earlier years keeps only the codes that happened to survive each revision —
about 82% for 2005–2009 and 83–87% for 2010–2018 overall, but very uneven by
sector. SOC 2018 renumbered every computer code, so Computer and Mathematical
kept four maths occupations, roughly 3% of its employment, before 2019. Pre-2019
points computed that way silently under-represented exactly the sectors the
models care most about. Correlating on units removes that selection: the same
occupation definitions carry the whole 2005→2025 span.

**What n is.** The unit file holds 751 units. A unit enters the chart when at
least one of its 2022 OEWS member codes carries a model score — 706 do — and
drops out of a period only when its growth for that period is NaN, leaving
n ≈ 695 in every period. Before harmonization the pre-2019 n sat around 650–690
and dipped unevenly by sector; it is now essentially flat, so movement in the
lines is signal rather than a changing sample.

A unit's score is the 2025-employment-weighted mean over its scored 2022
members, with weights renormalised over the members that actually have the
score; its growth comes from `data/output/bls_harmonized_trends.csv`, which sums
each unit's member employment per year before differencing.

**Where a unit is still NaN.** A unit's year is NaN — never 0 — when its
membership for that year is incomplete: a member code OEWS publishes was
suppressed or absent from that year's file. Summing the members that remain
would read as a collapse in employment rather than as the missing observation
it is. That is what keeps n a few units short of 706 rather than exactly equal.

**The one approximation is residual pruning.** Crosswalk edges that run between
a residual "All Other" catch-all and a named occupation are dropped before the
components are cut — left in, the catch-alls chain unrelated occupations
together until most of a major group fuses into a single unit. 62 edges are
pruned, and every one is listed in
`data/output/soc_harmonization_pruned_edges.csv` with its source and target
code and title, so the approximation is auditable rather than implicit.
