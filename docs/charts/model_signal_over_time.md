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

A **separate right-hand panel** covers 2025→2026 from BLS CPS Table A-19. It is
not part of the line. See [The CPS panel](#the-cps-panel-2025-2026) below.

## Purpose

This chart answers the primary confound question: **is the AI-era sector signal
pre-existing, or does it emerge post-2022?** A pre-existing structural trend
would show consistent model correlations throughout 2005–2025. An AI-specific
effect would show a weak or absent pre-AI signal and a strengthening post-2022.

## What the chart shows

**The dynamic model tracks a pre-existing structural trend.** The dynamic
`net_employment_change` score shows positive r of +0.40 to +0.50 in 2006→09
(significant in 2007→08, p = 0.016) and +0.37 in 2017→18, well before any AI
adoption. Sectors that the dynamic model predicts to gain workers (high
Unbounded and Adversarial composition) were already growing faster in the pre-AI
economy. This is the long-running secular transition from Bounded
(supply-constrained) work toward demand-elastic work that industrialization and
technology have driven for decades — and it is what the demand-type
classification, as a general theory of labor-saving disruption, should show for
earlier waves of automation too.

**The AI era sits inside the pre-AI range.** In 2023→24 and 2024→25 the dynamic
model's r is +0.53 (p = 0.011) and +0.48 (p = 0.023) — comparable to the 2007→08
peak of +0.50, not above it. The signal was already there. Whether AI is
accelerating it is a question three post-2022 years cannot answer; what can be
said is that the AI-era readings are the two most consistent consecutive
significant years in the series, where the pre-AI peaks were single years.

**The rebound-adjusted model has a weaker pre-AI analog in the same direction.**
The blue line is near zero or weakly positive through 2005→16, then turns
negative — the correct sign for a gross displacement measure — at −0.15 to
−0.27 in 2016→19, when Office and Administrative Support employment was already
falling. The AI-era reading (r = −0.43 in 2023→24, p = 0.047, the model's only
significant sector-level period) is the same displacement, larger. The
penetration-weighted term identifies clerical work, and clerical work was
shrinking before generative AI.

**The financial crisis (2007→09)** disrupts both models, as expected from a
demand shock concentrated in financial, construction, and related sectors. The
dynamic model flips to weakly negative during this period and recovers gradually.

**COVID disruption (2019→20, 2020→21):** Extreme values from lockdown-induced
sector shocks. Physical sectors (Building/Grounds, Food Prep, Construction)
were hit hardest, temporarily pushing both gross models toward large negative r
because those sectors have low AI exposure scores. These periods are uninformative
for AI trend detection.

## What this means for model interpretation

The **dynamic model** is tracking a structural property of the economy —
demand-elastic sectors have long grown faster — that the AI era continues at
about the same strength. The pre-AI signal (+0.40 to +0.50 in 2006→09) means
the model would appear predictive even without AI; the AI-era values (+0.53,
+0.48) do not rise above that baseline, so the data so far support
"continuation" and cannot yet distinguish "acceleration". That is the expected
shape for a general theory of labor-saving disruption; the AI-specific claim
rests on acceleration, which needs more post-2022 years to test.

The **rebound-adjusted model** shows the same shape at smaller magnitude: a
pre-AI analog in 2016→19 (−0.15 to −0.27) and a larger AI-era reading (−0.43 in
2023→24). It is the clerical-displacement term, visible before and after
generative AI. Two caveats: only 2023→24 reaches significance, and the CPS panel
puts the same model at the *opposite* sign for 2025→2026 (see
[The CPS panel](#the-cps-panel-2025-2026)), though the CPS values are not
significant, so they do not overturn the OEWS result.

The **observed AI coverage** model shows weakly positive pre-AI r and small
negative AI-era r — behaving like the rebound-adjusted model without the
demand-type discount. Its pre-AI positive values reflect the same composition
effect as the dynamic model (knowledge-work sectors that eventually attract heavy
AI usage were already growing). Its AI-era negative values are weaker than the
rebound-adjusted model's, consistent with the demand-type classification adding
genuine predictive value beyond raw coverage alone.

## The CPS panel (2025→2026)

OEWS stops at a May 2025 reference month, so the main line cannot reach the most
recent year. The right-hand panel fills that span using CPS Table A-19, the same
household survey behind [cps_model_vs_actual.md](cps_model_vs_actual.md).

**It is drawn as a separate panel, not as more points on the line, and that is
deliberate.** Three things make a spliced series misleading:

1. **Different survey.** OEWS is an employer establishment survey (~1.1M records,
   occupation coded by the employer). CPS is a household survey (~60k interviews,
   occupation self-reported). The two disagree on both levels and changes for
   reasons unrelated to AI.
2. **Different growth statistic.** An OEWS sector point is the employment-weighted
   mean of *occupation-level* growth rates among model-matched occupations in that
   sector. A CPS sector point is the growth of the *major-group total*, covering
   every occupation in the group including those the model never scored. The model
   score on the x-axis is built identically in both cases — an employment-weighted
   mean over occupations, weighted by `TOT_EMP_25` — so only the y-variable
   differs, but that is enough.
3. **No overlapping period exists to calibrate them.** The panel's earliest month
   is Apr 2025 and OEWS's last reference month is May 2025. There is no span both
   surveys measure, so the offset between them cannot be estimated and removed.
   Any apparent jump from the last OEWS point to the CPS panel is of unknown
   composition — part survey difference, part real change.

**The panel's x-axis is the endpoint month, not time.** A-19 hands over the latest
month and the same month a year earlier in one release, so each fetch contributes
one year-over-year pair. The panel currently holds three (Apr, Jun, Aug), and all
three measure *the same 12-month 2025→2026 span* from endpoints two months apart.
The points are drawn hollow and deliberately **unconnected**: their vertical
spread is endpoint sensitivity, not a trend. Reading the three as a rising or
falling sequence is the specific misreading this layout exists to prevent.

### What the panel currently shows

| Model | Apr | Jun | Aug | Spread |
|-------|----:|----:|----:|-------:|
| Rebound-adjusted (−r = correct) | +0.28 | +0.09 | +0.12 | 0.19 |
| Dynamic net change (+r = correct) | −0.03 | +0.13 | +0.18 | 0.22 |
| Observed AI coverage (−r = correct) | +0.08 | +0.07 | +0.03 | 0.05 |

**The dynamic model does not reproduce on CPS.** Two of three endpoints are
weakly positive and none approaches significance, well below its AI-era OEWS
values (+0.53, +0.48). This changed when Adversarial share was added to absorption
capacity: the previous model version read +0.24, +0.37 and +0.48 (p = 0.023)
here, and the Adversarial-heavy sectors whose scores rose — Legal, Sales,
Protective Service, Management — fit their 2022→2025 OEWS growth better but
their 2025→2026 CPS growth worse. See `cps_model_vs_actual.md` for the
discussion. The cross-survey replication is an open question.

**The rebound-adjusted model disagrees with itself across surveys.** Its OEWS
AI-era values are clearly negative (−0.41 in 2023→24, −0.35 in 2024→25), which is
the correct sign. All three CPS endpoints are positive, which is the wrong one.
None of the CPS values approach significance (the largest, +0.28, is far from it),
so this is a failure to reproduce rather than a contradiction — but it is a
caution against treating the OEWS-era negative signal as established. Which of the
three explanations above accounts for the flip is not determinable from the data
on hand.

**Observed AI coverage is flat and slightly wrong-signed** on employment,
consistent with its weak employment showing throughout. (Its sector-level
*wage* signal is a different matter — see
`anthropic_observed_sector_level_wage_validation.md`.)

### Why CPS is absent from the occupation-level chart

[model_signal_over_time_occupation.md](model_signal_over_time_occupation.md) has
no CPS panel. A-19 publishes 22 major groups and no occupation detail, so there is
nothing to correlate at the occupation level. Adding CPS there would require the
detailed-occupation CPS route sketched in
[cps_data_expansion.md](../cps_data_expansion.md), which is unimplemented.

## How sector growth is measured

The model score on the x-axis of every point is the 2025-employment-weighted
mean over the scored occupations in each sector. Sector *growth* is **not** the
weighted mean of those occupations' growth rates. It is the change in the
sector's total employment, read from the major-group summary row of each year's
OEWS file (`data/output/bls_sector_trends.csv`).

The distinction matters before 2019. Detailed-occupation joins are anchored at
the 2022 code set, and the SOC 2018 revision renumbered whole blocks: Computer
and Mathematical retains four small mathematics occupations, 3% of its
employment, in every year before 2019, so a survivor-based sector growth rate
for that sector would have been the growth of actuaries and statisticians
standing in for software developers. Major-group codes are the same across SOC
2000, 2010 and 2018, so the totals series is complete for all 22 sectors in all
20 periods. Switching to it lowered several pre-AI points — the dynamic model's
2009→10 r fell from +0.35 to +0.02 and the rebound-adjusted 2016→19 values
roughly halved — while the AI-era points moved little.

Two level breaks remain even at major-group level, because the SOC revisions
moved some occupations between groups: 2009→2010 and 2018→2019 (Office and
Administrative Support drops from 21.8M to 19.5M across the latter). Those two
periods should be read with that in mind.

The occupation-level chart (`model_signal_over_time_occupation.png`) solves the
same survivorship problem at finer grain, correlating on harmonized SOC units
rather than major-group totals — see *Harmonized units* in
[model_signal_over_time_occupation.md](model_signal_over_time_occupation.md).
