# Dynamic Model: Sector-Level Wage Validation (Per Year)

**File:** `dynamic_sector_level_wage_validation.png`

![Dynamic Sector-Level Wage Validation by Period](images/dynamic_sector_level_wage_validation.png)

## What this chart shows

Same layout as `dynamic_sector_level_employment_validation.png` but with sector mean wage growth on the y-axis. Four panels: 2022→23, 2023→24, 2024→25, composite.

## Correlation by period

| Period | r | p |
|--------|---|---|
| 2022→2023 | −0.180 | 0.422 |
| 2023→2024 | −0.213 | 0.342 |
| 2024→2025 | +0.163 | 0.469 |
| Composite | −0.163 | 0.468 |

## Key observations

**No wage signal at any level.** All four periods produce small r values of mixed sign that are far from statistical significance. The dynamic model, which has strong predictive content for sector-level employment growth, has essentially no relationship with sector-level wage growth.

**The direction contrast with employment is striking.** The employment validation shows r ≈ +0.57 (p < 0.01) in recent periods; the wage validation shows |r| ≤ 0.21 (p > 0.3) in all periods. The same model that tracks labor flows between sectors does not track how those flows affect wages within sectors. This suggests that sector-level wage growth is determined by factors orthogonal to AI-driven labor reallocation — tight labor markets, minimum wage changes, sector-specific bargaining dynamics — rather than by the mix of demand types in that sector.

**Why wage and employment diverge.** Under the dynamic model's conservation assumption, displaced workers move from Bounded sectors to those with Unbounded or Adversarial capacity. If this reallocation is happening in reality, those sectors should see both higher employment and potentially wage pressure in either direction (wages could rise with demand or fall as labor supply increases). The absence of a wage signal suggests that wage-setting mechanisms in absorbing sectors are not closely coupled to labor inflows from Bounded sectors — at least not over a 3-year window.

## Comparison to the rebound model

The rebound model's sector wage correlations (`sector_level_wage_validation.png`) are also non-significant, in the +0.09–+0.25 range. Neither model has detectable sector-level wage signal. Both models agree on employment at the sector level while both fail to explain wage growth.
