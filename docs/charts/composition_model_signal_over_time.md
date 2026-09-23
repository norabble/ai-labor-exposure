# Composition Model Signal Over Time (2005→2025)

`data/output/visualizations/composition_model_signal_over_time.png`, produced by
`composition_era_validation.py`.

Sector-level Pearson r between each model score and year-over-year employment
growth, one point per period, n = 22 sectors throughout. Ringed markers are
individually significant at p < 0.05. Red bands are the COVID periods (2019→20,
2020→21); the dashed blue line and shaded region mark the AI era from 2022→23.

Four lines, with different sign conventions — the redistribution models validate
with positive r (more net change → more growth), the gross exposure measures with
negative r (more exposure → less growth):

| Line | Score | Correct sign |
|---|---|---|
| Purple diamonds | `composition_net_change` — demand composition only, no technology data | + |
| Orange squares | `net_employment_change` — dynamic model on AI penetration | + |
| Blue circles | `occupation_exposure` — rebound-adjusted | − |
| Green triangles | `observed_exposure` — Anthropic observed task coverage | − |

## What it shows

**The composition-only line has a pre-AI signal.** It is significant in three
consecutive pre-AI periods — 2006→07 (+0.61), 2007→08 (+0.66), 2008→09 (+0.54) —
from a predictor containing no technology-exposure information at all. Its AI-era
values (+0.34, +0.34, +0.37) sit *inside* that pre-AI range rather than above it.

**Its strongest periods are the financial crisis.** That is the chart's most
important feature and the reason the era comparison cannot be read on its own: a
pre-AI signal is consistent both with the taxonomy describing a general mechanism
and with it picking up cyclical sorting, since Bounded and clerical work is shed
in downturns and rehired in recoveries. `composition_cycle_decomposition.csv`
separates the two — the signal survives at zero cyclical movement (intercept
+0.238, p = 0.0004) but gains +0.160 per percentage point of rising unemployment
(p = 0.0024).

**The AI-penetration line pulls ahead only after 2022.** Pre-2022 the two
redistribution lines track each other closely (Fisher-z means +0.218 against
+0.202), which is expected — penetration is anachronistic in that era and can add
nothing. After 2022 the orange line rises above the purple one (+0.53 and +0.48
against +0.34 and +0.37), and the cycle decomposition confirms the gap is an
AI-era effect rather than a cyclical one (+0.238, p = 0.021).

## Reading cautions

**The demand-type labels are from 2025 O\*NET task statements applied backwards.**
Earlier periods are more anachronistic; `docs/framework.md` flags this for every
historical test in the project.

**Sector growth is the major-group total**, from `bls_sector_trends.csv` via
`sector_growth_series` — never the mean growth of the surviving detailed
occupations, which lose 97% of Computer and Mathematical employment before 2019.
See `docs/charts/model_signal_over_time.md` § How sector growth is measured.

**The COVID periods are plotted but excluded from every statistic.** 2019→20 and
2020→21 are shutdown and rehiring rather than any mechanism these models
describe, and they dominate the cycle term if left in. Note that composition-only
reaches +0.45 and is significant in 2019→20, which is consistent with the cyclical
reading and is precisely why it is excluded.

**n = 22 sectors needs r ≈ 0.42 for p < 0.05.** The composition model's AI-era
points are not individually significant despite a mean of +0.348; that is a power
limit, not an absence of signal.

## Related

- `docs/framework.md` § Demand Composition Model — the model, the D-invariance
  property that makes this test non-circular, and the full result tables
- `docs/charts/model_signal_over_time.md` — the same layout for the AI-era models
  alone, without the composition line
- `docs/model_vs_observed_exposure.md` § Confound: pre-existing sector
  composition — the observation this chart exists to test
