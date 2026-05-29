# Dynamic Model: Sector-Level Wage Validation (Per Year)

**File:** `dynamic_sector_level_wage_validation.png`

![Dynamic Sector-Level Wage Validation by Period](images/dynamic_sector_level_wage_validation.png)

## What this chart shows

Same layout as `dynamic_sector_level_employment_validation.png` but with sector mean wage growth on the y-axis. Four panels: 2022→23, 2023→24, 2024→25, composite.

## Correlation by period

| Period | r | p |
|--------|---|---|
| 2022→2023 | +0.118 | 0.602 |
| 2023→2024 | +0.124 | 0.613 |
| 2024→2025 | +0.109 | 0.625 |
| Composite | +0.084 | 0.710 |

## Key observations

**No wage signal at any level.** All four periods produce small positive r values that are far from statistical significance. The dynamic model, which has strong predictive content for sector-level employment growth, has essentially no relationship with sector-level wage growth.

**The direction contrast with employment is striking.** The employment validation shows r ≈ +0.53 (p < 0.02) in recent periods; the wage validation shows r ≈ +0.10 (p > 0.6) in all periods. The same model that tracks labor flows between sectors does not track how those flows affect wages within sectors. This suggests that sector-level wage growth is determined by factors orthogonal to AI-driven labor reallocation — tight labor markets, minimum wage changes, sector-specific bargaining dynamics — rather than by the mix of demand types in that sector.

**Why wage and employment diverge.** Under the dynamic model's conservation assumption, displaced workers move from Bounded to Unbounded sectors. If this reallocation is happening in reality, Unbounded sectors should see both higher employment and potentially wage pressure in either direction (wages could rise with demand or fall as labor supply increases). The absence of a wage signal suggests that wage-setting mechanisms in Unbounded sectors are not closely coupled to labor inflows from Bounded sectors — at least not over a 3-year window.

## Comparison to the rebound model

The rebound model's sector wage correlations (`sector_level_wage_validation.png`) are also non-significant and in the same +0.09–+0.25 range. Neither model has detectable sector-level wage signal. Both models agree on employment at the sector level while both fail to explain wage growth.
