# Dynamic Model: Sector-Level Validation

**File:** `dynamic_sector_level_validation.png`

![Dynamic Model Sector-Level Validation](images/dynamic_sector_level_validation.png)

## What this chart shows

Each bubble is one of the 22 BLS major occupational groups. The x-axis is the sector's employment-weighted mean `net_employment_change` from the dynamic model. The y-axis is the sector's composite employment growth (left panel) or composite median-wage growth (right panel), read from the major-group summary row of each OEWS file (`bls_sector_trends.csv`) — the change in the whole sector's total, not the mean of the scored occupations. Bubble size scales with total sector employment.

This is the direct analog of `sector_level_validation.png` for the dynamic model.

## Composite correlation results

**Employment (left panel):** r = +0.509, p = 0.015, n = 22. Leave-one-sector-out range +0.344 to +0.591 — see [Which sector carries it](#which-sector-carries-it).

This is the strongest sector-level validation result in the pipeline. Higher dynamic model net employment change predicts higher actual composite employment growth across BLS major groups, and the relationship is statistically significant. The positive slope is clearly visible in the chart: sectors in the upper-right (high net change, strong growth) are the Unbounded-dominant ones; sectors in the lower-left (negative net change, weaker growth) are Bounded-dominant.

**Wage (right panel):** r = −0.222, p = 0.320, n = 22.

No relationship with wage growth. The model has no wage signal at any aggregation level.

## Per-year breakdown

The composite masks variation across years. See `dynamic_sector_level_employment_validation.png` and `dynamic_sector_level_wage_validation.png` for the full per-period grids.

![Dynamic Sector-Level Employment Validation by Period](images/dynamic_sector_level_employment_validation.png)

![Dynamic Sector-Level Wage Validation by Period](images/dynamic_sector_level_wage_validation.png)

### Employment correlations by period

| Period | r | p |
|--------|---|---|
| 2022→2023 | +0.343 | 0.119 |
| 2023→2024 | +0.530 | 0.011 |
| 2024→2025 | +0.482 | 0.023 |
| Composite | +0.509 | 0.015 |

The signal is positive in all four periods and statistically significant in three of four. The strengthening from 2022→23 (r = +0.343, p = 0.119) to 2023→24 (r = +0.530, p = 0.011) is consistent with AI adoption having an increasing effect on sector-level employment outcomes — but see the confound note below before treating this as specifically AI-attributable.

### Wage correlations by period

| Period | r | p |
|--------|---|---|
| 2022→2023 | −0.379 | 0.082 |
| 2023→2024 | −0.087 | 0.702 |
| 2024→2025 | +0.169 | 0.451 |
| Composite | −0.222 | 0.320 |

Small, mixed in sign, and never significant. See `dynamic_sector_level_wage_validation.md` for interpretation.

## Comparison to the rebound-adjusted model

| Period | Rebound emp r | p | Dynamic emp r | p |
|--------|--------------|---|---------------|---|
| 2022→2023 | −0.089 | 0.695 | +0.343 | 0.119 |
| 2023→2024 | −0.428 | 0.047 | +0.530 | 0.011 |
| 2024→2025 | −0.288 | 0.193 | +0.482 | 0.023 |
| Composite | −0.290 | 0.191 | +0.509 | 0.015 |

The dynamic model outperforms the rebound model at the sector level in every period. The sign reversal in 2023→24 and 2024→25 is particularly striking: the rebound model predicts that high-exposure sectors (Bounded-dominant) grow less, while the dynamic model predicts that net-gaining sectors (Unbounded-dominant) grow more. The BLS data consistently supports the dynamic model's direction.

## What drives the positive employment correlation

The key sectors populating the upper-right of the employment panels are:

- **Computer and Mathematical** (large bubble): High `pct_unbounded`, low Bounded displacement → large positive net change; actual growth was among the highest across all periods.
- **Healthcare Practitioners and Technical**: Similar structure. Healthcare grew steadily through the period.
- **Community and Social Service**, **Life, Physical, and Social Science**, **Architecture and Engineering**: All Unbounded-dominant, all showing positive actual growth.

Sectors in the lower-left include:

- **Office and Administrative Support** (large bubble, negative net change): The largest single source of Bounded displacement in the model. It grew modestly in BLS data but at a lower rate than Unbounded sectors — appearing consistently below the regression line.
- **Arts, Design, Entertainment, Sports, and Media**: Adversarial-dominant, near-zero net change; mixed actual growth performance.
- **Farming, Fishing, and Forestry**: Bounded, small negative net change; weak actual growth.

**Office and Administrative Support** is not an outlier but the anchor of the result. The model assigns it the most negative sector score in the economy (about −19%), and it is one of only three sectors with negative composite employment growth (−4.9%, from 18.67M workers in 2022 to 17.75M in 2025; 21.8M in 2018 before the SOC 2018 revision moved some occupations out of the group). It sits alone in the lower-left, which is what gives the fitted line most of its slope.

## Which sector carries it

`compute_sector_jackknife` drops each sector in turn and recomputes the composite correlation (`data/output/sector_jackknife.csv`):

| Dropped sector | r | p |
|---|---:|---:|
| Office and Administrative Support | +0.344 | 0.126 |
| Community and Social Service | +0.462 | 0.035 |
| Life, Physical, and Social Science | +0.482 | 0.027 |
| Sales and Related | +0.495 | 0.023 |
| *(17 others)* | +0.50 to +0.55 | ≤ 0.021 |
| Arts, Design, Entertainment, Sports, and Media | +0.591 | 0.005 |

Removing Office and Administrative Support is the only single deletion that takes the result above p = 0.05. A correlation on 22 points with one point far from the rest is partly a measurement of that point, so the headline r should be quoted with its jackknife range beside it. That said, clerical work is exactly where the model's mechanism is most visible — high penetration, almost entirely Bounded, employment falling since 2016 — so its influence is the finding, not a nuisance.

## Relationship to occupation-level null

The sector-level r = +0.509 coexists with occupation-level sector-adjusted r ≈ 0.03–0.06 (see `dynamic_model_growth_validation.md`). This combination means: the model correctly identifies which sectors gained or lost labor, but within any sector it cannot distinguish which specific occupations outperformed their peers. The sector-level signal is real; the occupation-level signal is not yet detectable.

This is the expected pattern for a model that redistributes labor via sector-level absorption capacity rather than occupation-specific adjacency. Strengthening the occupation-level prediction would require a more granular absorption mechanism that routes displaced workers toward skill-adjacent Unbounded occupations rather than all Unbounded occupations proportionally.

## The result does not rest on the conservation constraint

A natural objection to r = +0.509 is that it is an artifact of assuming total
employment is conserved. It is not. The conservation constraint reduces to a
single scalar multiplying `absorption_capacity`, and re-running this correlation across
a range of equilibration rates shows the result holds anywhere from a quarter to
ten times the conserved value (all p < 0.05). The worst point is multiplier 0 —
the no-equilibrium model in which displaced labor vanishes, which drops to
r = +0.351 (p = 0.109).

That is the comparison the dynamic model exists to make, so it is worth stating
directly: **the naive no-equilibrium assumption is the worst-fitting point on the
curve, and the only one that loses significance.** See `framework.md`
§ Robustness to the equilibration rate for the full sweep, and
`data/output/equilibration_sensitivity.csv` for the generated table.

## Confound: pre-existing sector composition

Extending the BLS baseline to 2005 (see `model_signal_over_time.md`) reveals that the dynamic model's sector-level r was already +0.40 to +0.50 in 2006→09 and +0.37 in 2017→18, well before meaningful AI adoption. Sectors with Unbounded and Adversarial demand — Computer and Mathematical, Healthcare, Life Sciences, Legal, Management — have grown faster than Bounded sectors as part of a long-running secular shift in the economy. The model, which assigns positive `net_employment_change` to those sectors, therefore captures a pre-existing structural tendency.

The AI-era values (+0.53 in 2023→24, +0.48 in 2024→25) sit inside that pre-AI range rather than above it. That is the expected shape for a general theory of labor-saving disruption — earlier waves of automation should leave the same signature — but it means three post-AI years cannot distinguish AI accelerating the pattern from AI continuing it. The AI-specific claim rests on acceleration and needs more post-2022 data.

**The rebound-adjusted model has a smaller pre-AI analog in the same direction.** Its r is near zero or weakly positive through 2005→16, then negative at −0.15 to −0.27 in 2016→19 as Office and Administrative Support employment was already falling, before the AI-era −0.43 in 2023→24. The displacement term identifies clerical work, which was shrinking before generative AI.
