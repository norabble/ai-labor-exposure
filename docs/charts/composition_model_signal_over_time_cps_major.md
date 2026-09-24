# Composition Model Signal Over Time — CPS 22-Major Rollup (1983→2026)

`data/output/visualizations/composition_model_signal_over_time_cps_major.png`,
produced by `composition_era_validation.py` (via `cps_detailed_validation.py`).

Same layout and the same four score lines as
[`composition_model_signal_over_time.md`](composition_model_signal_over_time.md),
built from the **same IPUMS CPS microdata** as
[`composition_model_signal_over_time_cps_detailed.md`](composition_model_signal_over_time_cps_detailed.md),
rolled up from 333 `occ1990dd` codes to the same **22 SOC-major groups** the
OEWS sector-level chart uses, reaching that grouping back to 1983 instead of
OEWS's 1999 floor. Each point is a group-level Pearson r between a model
score and year-over-year employment growth, one point per period. This is
`composition_cycle_decomposition_cps_major.csv` and
`composition_model_era_comparison_cps_major.csv` — see `docs/framework.md`
§ Detailed occupations → Results for the full numbers.

| Line | Score | Correct sign |
|---|---|---|
| Purple diamonds | `composition_net_change` — demand composition only, no technology data | + |
| Orange squares | `net_employment_change` — dynamic model on AI penetration | + |
| Blue circles | `occupation_exposure` — rebound-adjusted | − |
| Green triangles | `observed_exposure` — Anthropic observed task coverage | − |

## n=22, fixed, unlike the detailed chart

Every period plots all 22 SOC-major groups — n does not vary by period the
way it does in the detailed chart, because aggregating 333 `occ1990dd` codes
into 22 stable major groups keeps every group populated even in periods where
individual detailed codes are too small to be reliably measured. 41 of the 43
possible 1983→2026 periods are plotted; only the two COVID periods (2019→20,
2020→21) are excluded, matching the sector-level treatment. **Coding-vintage
seam periods are not excluded here**, unlike the detailed chart's four —
aggregation to 22 groups damps the seam effect enough that it is not treated
as a separate exclusion at this grain (see `CLAUDE.md`'s row for this file).

## What this chart shows

**The cycle decomposition intercept is larger than at detailed grain, from
the same underlying data.** `composition_net_change` has an intercept of
**+0.277** (p = 8.2e-8, n=41 periods), a cyclical term (`unemployment_change`)
of −0.002 (p = 0.96, not significant), and an AI-era term of −0.134
(p = 0.32, not significant). The intercept is roughly 3.5x the detailed
chart's +0.078, built from identical microdata and identical demand-type
labels — the expected direction, not a contradiction: rolling up to 22
groups averages away occupation-level idiosyncratic sampling noise, which
raises r without adding information. Read the two intercepts as the same
signal measured at two resolutions, one noisier than the other, not as two
different results.

**The era comparison is null.** Pre-AI mean r = +0.271 (n=37 periods, 11
individually significant), AI-era mean r = +0.142 (n=4 periods, 0
significant), difference −0.129, Welch p = 0.35 — not distinguishable from
zero. Both era differences are null (Welch p = 0.81 detailed, 0.35 rollup),
and they are opposite in sign (+0.009 detailed, −0.129 rollup), so neither
grain shows an era effect. As at every other grain in this phase, the AI era
contributes only 4 periods, so no AI-specific claim is made from this result
regardless of sign.

**Neither grain returned the null the spec's "detailed null, rollup
positive" contingency describes.** Both the detailed chart and this one show
a significant, positive, non-cyclical intercept — the rollup does not stand
apart from the detailed result as evidence that the signal is purely
between-sector composition; instead the two agree in direction, at different
resolutions of the same underlying mechanism.

## Agreement with published OEWS, where they overlap

`cps_major_oews_agreement.csv` pairs this rollup's group-level growth against
the group's summed OEWS employment-level growth for every period both cover
(1999–2025): **572 paired observations, Pearson r = +0.373**. This is weaker
than the ten-group CPS instrument's agreement with OEWS (r = +0.547,
`cps_oews_agreement.csv`) — expected, since finer partitions are individually
noisier — and is reported here as a bound on cross-instrument agreement, not
reconciled or spliced into either series. As with every other CPS-vs-OEWS
comparison in this project, the two are drawn as, and remain, separate series.

## Related

- `docs/framework.md` § Detailed occupations (deep history, Phase 2) → Results
  — the full numbers and the pre-written readings they are checked against
- `docs/charts/composition_model_signal_over_time_cps_detailed.md` — the same
  microdata at 333 `occ1990dd` occupations rather than 22 major groups
- `docs/charts/composition_model_signal_over_time.md` — the OEWS sector-level
  chart (22 groups, 1999→2025) this rollup extends back to 1983
- `docs/charts/composition_model_signal_over_time_cps.md` — the published
  ten-group CPS instrument, for comparison of cross-instrument agreement
