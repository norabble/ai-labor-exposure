# Composition Model Signal Over Time — CPS Detailed Occupations (1983→2026)

`data/output/visualizations/composition_model_signal_over_time_cps_detailed.png`,
produced by `composition_era_validation.py` (via `cps_detailed_validation.py`).

Same layout and the same four score lines as
[`composition_model_signal_over_time.md`](composition_model_signal_over_time.md)
and [`composition_model_signal_over_time_cps.md`](composition_model_signal_over_time_cps.md),
run at a third, finer-grained instrument: **333 `occ1990dd` occupations**
(Autor and Dorn's time-consistent occupation spine), tabulated directly from
IPUMS CPS microdata rather than the published ten-series route the other CPS
chart uses. Each point is an occupation-level Pearson r between a model score
and year-over-year employment growth, one point per period, 1983→2026. This
is the `run == "headline"` view of `composition_cycle_decomposition_cps_detailed.csv`
and `composition_model_era_comparison_cps_detailed.csv` — see
`docs/framework.md` § Detailed occupations → Results for the full numbers.

| Line | Score | Correct sign |
|---|---|---|
| Purple diamonds | `composition_net_change` — demand composition only, no technology data | + |
| Orange squares | `net_employment_change` — dynamic model on AI penetration | + |
| Blue circles | `occupation_exposure` — rebound-adjusted | − |
| Green triangles | `observed_exposure` — Anthropic observed task coverage | − |

As with the sector-level and ten-group CPS charts, `composition_net_change` is
the line this chart exists to test: it carries no AI data at all, so a result
here is a genuine second measurement of the demand-type mechanism, built at
the finest occupation grain this project reaches and reaching back to 1983.

## n per period, and why it moves

Unlike the sector-level chart (fixed n=22) and the ten-group CPS chart (fixed
n=10), n here varies by period: it is however many of the 333 `occ1990dd`
codes have an employment relative standard error ≤ 20% in **both** endpoint
years of that period (`build_eligible_codes` in `cps_detailed_measurement.py`).
Across the 39 plotted periods (43 year-over-year periods minus the four
excluded coding-vintage seams — see below), n ranges from **232 to 298**
(median 274) out of 333 possible codes. This is a deliberate choice, not
missing data: a single fixed set held across the whole 1983–2026 span would
drop every occupation that was small at either end — typists and telephone
operators on the way down, computer occupations on the way up — which are
exactly the occupations that changed most, so a fixed set would select on the
outcome. `cps_detailed_eligibility_sweep.csv` reports the alternative cutoffs
(10%, 30%, no cutoff, and a fixed 20% set) as a sensitivity, not as a
candidate replacement for the headline.

## Four seam periods are excluded, not patched

1991→92, 1993→94, 2002→03, and 2010→11 are coding-vintage and survey-design
breaks (CPS occupation coding revisions and classification changes), not
artifacts of this project's method. `cps_detailed_seam_breaks.csv` measures
rather than assumes their size: the 2002→2003 break carries a median
`|growth|` of **0.169** against an ordinary period's median of **0.067** —
more than double, and large enough at that one seam to swamp genuine signal.
All four seams are excluded from every headline number here, the same way
Phase 1 excludes COVID periods (2019→20 and 2020→21, still present in the
underlying data and marked with the usual red bands, but excluded from the
era-comparison and cycle-decomposition means).

## Reliability: the headline caveat at this grain

A median `occ1990dd` occupation carries roughly 90,000 workers, thin enough
that year-over-year growth is dominated by CPS sampling noise rather than
real change. `cps_detailed_reliability.csv` measures this directly: median
reliability across all 43 periods is **0.005** — far below the spec's
pre-registered estimate of 0.1–0.2, meaning essentially none of the measured
variance in period-to-period growth at this grain is real signal by this
estimator. This has a direct consequence for the noise-correction bracket
that is the project's only handling for it: `r_corrected = r_raw /
sqrt(reliability)` is undefined whenever reliability ≤ 0, which happens for
89 of the 172 period/score rows in the full (seam-inclusive) view — the
bracket is available for well under half this grain's results. Read every
raw r on this chart as attenuated toward zero by unmeasured amounts, per
period, rather than as a clean effect size.

## What this chart shows

**The cycle decomposition intercept is positive and significant**:
`composition_net_change` has an intercept of **+0.078** (p = 5.0e-6, n=37
periods), against a cyclical term (`unemployment_change`) of +0.022
(p = 0.15, not significant) and an AI-era term of +0.001 (p = 0.98, not
significant). Per the spec's pre-written reading, a positive, significant
intercept spanning three downturns (early 1990s, early 2000s, 2008–09) across
1983–2026 means the general demand-type mechanism holds at occupation grain,
not only when aggregated to sectors or ten groups — read alongside the
reliability caveat above, since that intercept is estimated from year-over-year
data known to be mostly noise.

**The era comparison is null.** Pre-AI mean r = +0.073 (n=33 periods, 11
individually significant), AI-era mean r = +0.082 (n=4 periods, 0
significant), difference +0.009, Welch p = 0.81 — not distinguishable from
zero. The pre-AI mean sits at the bottom of the spec's expected +0.05 to
+0.15 band. Per the spec, the AI era contributes only 4 periods at this
grain, so **no AI-specific claim is made from this result, whatever its
sign.**

**Magnitudes here are smaller than at sector or ten-group level, expected and
by design.** Aggregating to sectors or groups averages away
occupation-specific idiosyncratic noise, which raises r without adding
information — the reverse is true here. Compare this chart only against
other occupation-level results (`model_signal_over_time_occupation.png`,
`composition_model_signal_over_time_occupation.md`), never directly against
`composition_model_signal_over_time.png` or
`composition_model_signal_over_time_cps.png`.

## Related

- `docs/framework.md` § Detailed occupations (deep history, Phase 2) → Results
  — the full numbers and the pre-written readings they are checked against
- `docs/charts/composition_model_signal_over_time_cps_major.md` — the same
  microdata rolled up to 22 SOC-major groups instead of 333 occupations
- `docs/charts/composition_model_signal_over_time_occupation.md` — the
  OEWS-based occupation-level chart (harmonized SOC units, 1999→2025) this
  chart extends back to 1983
- `docs/charts/composition_model_signal_over_time_cps.md` — the published
  ten-group CPS instrument this detailed tabulation supersedes in
  cross-sectional n, but not in scope
