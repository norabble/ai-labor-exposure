# Model Signal Over Time: Historical Baseline (2005→2025)

**File:** `model_signal_over_time.png`

![Model Signal Over Time](images/model_signal_over_time.png)

## What this chart shows

Sector-level Pearson r between each model score and YoY BLS employment growth,
plotted as a time series spanning 2005→2025. Each data point is a correlation
across n=22 SOC major sectors (employment-weighted means). Three model lines are
shown:

| Line | Score | Correct sign | Direction |
|------|-------|:------------:|-----------|
| Rebound-adjusted (blue) | `occupation_exposure` (≥ 0) | negative | More structural exposure → less growth |
| Dynamic net change (orange) | `net_employment_change` (signed) | positive | Predicted gainers actually grow |
| Observed AI coverage (green) | `observed_exposure` (≥ 0) | negative | Higher AI task usage → less growth |

Red shading marks COVID-disrupted periods (2019→20, 2020→21); blue shading marks
the AI era (2022→23 onward); significant periods (p < 0.05) are annotated.

## Purpose

This chart answers the primary confound question: **is the AI-era sector signal
pre-existing, or does it emerge post-2022?** A pre-existing structural trend
would show consistent model correlations throughout 2005–2025. An AI-specific
effect would show a weak or absent pre-AI signal and a strengthening post-2022.

## What the chart shows

**The dynamic model tracks a pre-existing structural trend.** The dynamic
`net_employment_change` score shows significant positive r ≈ +0.43–0.48 in
2005→06 and 2006→07, well before any AI adoption. Sectors that the dynamic model
predicts to gain workers (high Unbounded composition) were already growing faster
in the pre-AI economy. This is the long-running secular transition from Bounded
(supply-constrained) work toward Unbounded (demand-elastic) work that
industrialization and technology have driven for decades.

**The AI era amplifies the pre-existing dynamic signal.** In 2023→24 and
2024→25, the dynamic model's r rises to +0.54 (p < 0.01) — above the pre-AI
peaks of +0.43–0.48. The signal was already there; AI strengthens it. This is
consistent with AI accelerating the redistribution of labor toward Unbounded
sectors rather than creating an entirely new structural break.

**The rebound-adjusted model shows NO consistent pre-AI signal.** The blue line
fluctuates near zero or positive throughout 2005–2021 — the wrong sign for a
gross displacement measure. A pre-existing negative relationship between
rebound-adjusted exposure and sector employment growth would require occupations
to be shedding headcount proportional to their exposure score, which only becomes
visible once AI adoption is substantial. The AI-era negative signal (r ≈ −0.4
in 2024→25) is genuinely new: the demand-type discount is doing work that
pre-AI structural factors alone could not produce.

**The financial crisis (2007→09)** disrupts both models, as expected from a
demand shock concentrated in financial, construction, and related sectors. The
dynamic model flips to weakly negative during this period and recovers gradually.

**COVID disruption (2019→20, 2020→21):** Extreme values from lockdown-induced
sector shocks. Physical sectors (Building/Grounds, Food Prep, Construction)
were hit hardest, temporarily pushing both gross models toward large negative r
because those sectors have low AI exposure scores. These periods are uninformative
for AI trend detection.

## What this means for model interpretation

The **dynamic model** is partly tracking a structural property of the economy
(Unbounded sectors have long grown faster) and partly tracking an AI-amplified
version of that trend in 2023–25. The pre-AI signal at r ≈ +0.43–0.48 is a
partial confound: if Unbounded sectors were already growing, the model would
appear predictive even without AI. The AI-era signal at r ≈ +0.54 is modestly
above that baseline, suggesting a real incremental contribution from AI adoption
on top of the existing structural tendency — but not a clean separation.

The **rebound-adjusted model** is not subject to this confound in the same way.
Its negative AI-era signal (r ≈ −0.40 in 2024→25) has no pre-AI analog,
suggesting it is more specifically measuring an AI-driven displacement effect
rather than a pre-existing composition trend.

The **observed AI coverage** model shows weakly positive pre-AI r and small
negative AI-era r — behaving like the rebound-adjusted model without the
demand-type discount. Its pre-AI positive values reflect the same composition
effect as the dynamic model (knowledge-work sectors that eventually attract heavy
AI usage were already growing). Its AI-era negative values are weaker than the
rebound-adjusted model's, consistent with the demand-type classification adding
genuine predictive value beyond raw coverage alone.

## Survivorship note

All joins are left-joins anchored at the 2022 occupation set (830 occupations).
Survivorship against 2022: ~82% for 2005–2009 (SOC 2000 codes), ~83–87% for
2010–2018 (SOC 2010 codes). Each period's sector correlation is computed on the
occupations with non-NaN values for both years in that pair; sectors with
insufficient data are excluded. The sector-level aggregation (n=22 sectors,
hundreds of occupations each) is robust to the ~13–18% occupation attrition from
code changes.
