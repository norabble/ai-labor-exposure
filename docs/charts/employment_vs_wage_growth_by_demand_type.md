# Composite Employment vs. Wage Growth by Demand Type

**File:** `employment_vs_wage_growth_by_demand_type.png`

## What this chart shows

Each dot is one occupation, plotted by its composite employment growth (x-axis) against its composite wage growth (y-axis), both measured from 2022 to the latest available BLS data. Dots are colored by dominant demand type.

The chart tests two theoretical predictions about how different types of AI-exposed work should behave in the labor market:

**Bounded (red):** AI completes tasks to a fixed endpoint — demand falls once the backlog clears. The model predicts employment contraction. In the chart, Bounded occupations should cluster toward the left.

**Unbounded (orange):** AI reduces the cost of a task, freeing time that gets reinvested in doing more of the same work or adjacent work. Both employment and wages may grow. The model predicts a "productivity premium" — wages rising because workers who stay are more valuable per hour. Look for orange dots in the upper-right quadrant.

**Adversarial (green):** Work defined by a counterparty that escalates in response to any gain (fraud detection, cybersecurity, compliance). AI capability on both sides raises the stakes and volume of work. Both employment and wages should grow. Look for green dots in the upper-right quadrant.

## Why this test is noisy

The composite period (2022–2025) spans the post-pandemic labor market, which had strong tailwinds for many occupations independent of AI. Macroeconomic effects dominate occupation-level AI effects in short windows, which is why the dots are dispersed rather than clearly separated. The sector-adjusted charts (`sector_adjusted_employment_growth.png`, `sector_adjusted_wage_growth.png`) remove some of this noise by subtracting each occupation's sector mean before plotting.
