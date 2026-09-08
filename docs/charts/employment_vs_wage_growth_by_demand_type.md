# Composite Employment vs. Wage Growth by Demand Type

**File:** `employment_vs_wage_growth_by_demand_type.png`

![Composite Employment vs. Wage Growth by Demand Type](images/employment_vs_wage_growth_by_demand_type.png)

## What this chart shows

Each dot is one occupation, plotted by its composite employment growth (x-axis) against its composite wage growth (y-axis), both measured from 2022 to the latest available BLS data. Dots are colored by dominant demand type.

The chart tests two theoretical predictions about how different types of AI-exposed work should behave in the labor market:

**Bounded (red):** AI completes tasks to a fixed endpoint — demand falls once the backlog clears. The model predicts employment contraction. In the chart, Bounded occupations should cluster toward the left.

**Unbounded (orange):** AI reduces the cost of a task, freeing time that gets reinvested in doing more of the same work or adjacent work. Both employment and wages may grow. The model predicts a "productivity premium" — wages rising because workers who stay are more valuable per hour. Look for orange dots in the upper-right quadrant.

**Adversarial (green):** Work defined by a counterparty that escalates in response to any gain (fraud detection, cybersecurity, compliance). AI capability on both sides raises the stakes and volume of work. Both employment and wages should grow. Look for green dots in the upper-right quadrant.

## What the dispersed pattern means

The dots show no clear separation by demand type — Bounded, Unbounded, and Adversarial occupations overlap throughout the chart. There are several honest interpretations:

**AI-driven effects may not have materialized yet.** Widespread workforce restructuring takes time. Employers in Bounded occupations may be absorbing AI productivity gains without reducing headcount — at least through 2025. The predicted divergence between demand types may be a future signal, not a present one.

**Observed AI usage has been concentrated outside Bounded work.** The `usage_by_demand_type.png` chart shows Claude conversation volume is heavily skewed toward Unbounded occupations. If Bounded workers aren't yet adopting AI at scale, there's no mechanism yet for the displacement prediction to show up in employment data.

**The model or classifications may be wrong.** The demand type assignment relies on classifying each O\*NET task statement as Bounded, Unbounded, or Adversarial. If those labels are systematically off — particularly for large occupations that drive aggregate patterns — the model's predictions could be structurally incorrect rather than just early.

The sector-adjusted charts (`sector_adjusted_employment_growth.png`, `sector_adjusted_wage_growth.png`) strip out macroeconomic and sector-cycle noise, but the occupation-level signal remains absent in those views as well. The rebound-adjusted model's own sector-level validation (`sector_level_validation.png`) likewise finds no statistically significant correlation (composite employment r = −0.247, p = 0.267).

**The null here is specific to this chart's framing, not to the project as a whole.** What is absent is an occupation-level separation *by demand type* in raw employment and wage growth. The dynamic equilibrium model does find a significant employment signal once occupations are aggregated to SOC major groups: composite r = +0.528 (p = 0.012), rising to r ≈ +0.53–0.54 (p < 0.02) in 2023→24 and 2024→25 — see [dynamic_sector_level_employment_validation.md](dynamic_sector_level_employment_validation.md). Two caveats keep that from overturning the reading above. The signal disappears under sector adjustment ([dynamic_model_growth_validation.md](dynamic_model_growth_validation.md)), so it is a statement about sector composition rather than about individual occupations. And the same sector correlation was already r ≈ +0.43–0.48 before AI adoption ([model_signal_over_time.md](model_signal_over_time.md)), so it is not cleanly AI-attributable. The honest summary is that demand-type composition tracks sector employment growth, while the occupation-level dispersion this chart plots stays undifferentiated.
