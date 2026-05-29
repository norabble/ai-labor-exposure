# Sector-Level Wage Validation (Per Year)

**File:** `sector_level_wage_validation.png`

![Sector-Level Wage Validation by Period](images/sector_level_wage_validation.png)

## What this chart shows

Same layout as `sector_level_employment_validation.png` but with sector mean wage growth on the y-axis. Four panels: 2022→23, 2023→24, 2024→25, composite.

## Correlation by period

| Period | r | p |
|--------|---|---|
| 2022→2023 | +0.249 | 0.264 |
| 2023→2024 | +0.097 | 0.668 |
| 2024→2025 | +0.218 | 0.329 |
| Composite | +0.087 | 0.700 |

## Key observations

**The sign is consistently positive but never significant.** This is an unexpected direction: higher rebound-adjusted exposure (more structural displacement pressure) is weakly associated with *higher* wage growth, not lower. This seems counterintuitive for a displacement model.

**Why the positive sign?** Office and Administrative Support — the sector with the highest rebound-adjusted exposure — had above-average wage growth in several periods despite slow employment growth. The BLS data is consistent with the pattern of "labor-saving AI increases productivity wages in Bounded occupations even as headcount stagnates." The rebound model's exposure score is not designed to predict wage direction: it measures structural exposure pressure, which could manifest as either wage suppression (if supply exceeds demand) or wage growth (if remaining workers capture productivity gains). The positive sign is therefore ambiguous rather than directionally wrong.

**No period approaches significance.** The strongest single-period result is 2022→23 at r = +0.249 (p = 0.264), which is well above conventional thresholds. The wage signal is absent at the sector level for the rebound model.

## Comparison to the dynamic model

The dynamic model's sector wage correlations (`dynamic_sector_level_wage_validation.png`) are also consistently positive and non-significant (r ≈ +0.08–+0.12). Both models have no detectable sector-level wage signal. This is consistent with wage growth being driven by factors orthogonal to AI task exposure over this observation window.
