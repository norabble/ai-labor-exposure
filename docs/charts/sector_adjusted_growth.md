# Sector-Adjusted Employment and Wage Growth

**Files:** `sector_adjusted_employment_growth.png`, `sector_adjusted_wage_growth.png`

## What these charts show

These are the same layout as `model_vs_actual_employment_growth.png` and `model_vs_actual_wage_growth.png`, but the y-axis has been adjusted to remove sector-level trends before plotting.

## Why sector adjustment matters

Observed employment and wage growth are driven by three layered forces:

1. **National business cycle** — the whole economy growing or contracting
2. **Sector-level trends** — e.g., healthcare expanding post-pandemic regardless of AI
3. **Occupation-specific effects** — the signal this model is trying to predict

The raw validation charts test the model against (1 + 2 + 3) combined. The sector-adjusted charts strip out the sector component, leaving a residual that is a cleaner test of occupation-specific prediction.

## How the adjustment is computed

For each occupation, the sector mean growth is the employment-weighted average growth of all occupations in the same 2-digit SOC major group (e.g., "Healthcare Practitioners and Technical"). The residual plotted here is:

```
residual = occupation_growth − employment_weighted_sector_mean_growth
```

A positive residual means the occupation outperformed its sector peers; a negative residual means it underperformed. If the model's impact score predicts anything real at the occupation level, it should predict these residuals better than it predicts raw growth.

## Interpreting the correlation statistics

Each subplot shows a Pearson r and p-value for the model impact score vs. the growth residual in that period. A small r (close to zero) with a high p-value means the model's occupation-specific signal is weak in that window — which is expected given how short the BLS data series is. The sector-level validation (`sector_level_validation.png`) aggregates to 22 sectors and finds a statistically significant wage correlation.
