# Anthropic Observed Exposure: Sector-Level Wage Validation

**File:** `anthropic_observed_sector_level_wage_validation.png`

![Anthropic Observed Sector-Level Wage Validation](images/anthropic_observed_sector_level_wage_validation.png)

## What this chart shows

Same layout as `anthropic_observed_sector_level_employment_validation.png` but with sector mean wage growth on the y-axis. Four panels: 2022→23, 2023→24, 2024→25, composite.

## Correlation by period

| Period | r | p |
|--------|---|---|
| 2022→2023 | −0.416 | 0.054 |
| 2023→2024 | −0.315 | 0.154 |
| 2024→2025 | +0.321 | 0.145 |
| Composite | +0.299 | 0.177 |

## The 2022→23 negative correlation is a post-COVID confound

**r = −0.416, p = 0.054** in 2022→23 appears borderline significant, but it reflects the same post-COVID wage recovery confound identified in the Eloundou model (see `eloundou_sector_level_wage_validation.md`).

The sectors with the highest observed AI task coverage are knowledge-work sectors (Computer and Mathematical at ~30–35%, Business/Financial at ~25–30%) that were insulated from COVID labor shortages and posted moderate wage growth in 2022→23. The sectors with the lowest observed AI coverage are physical and care occupations (Building/Grounds at ~2–3%, Food Prep at ~3–5%, Construction at ~3–5%) that experienced severe COVID labor shortages and posted above-average catch-up wage growth in 2022→23.

For the Eloundou model, excluding the 6 most obvious post-COVID recovery sectors drops the 2022→23 wage correlation from r = −0.507 to r = −0.287 (p = 0.282), losing all significance. The same pattern almost certainly applies here — both measures assign low scores to physical sectors, so both pick up the same confound.

## The cross-model agreement does not rescue the finding

The fact that both Eloundou and Anthropic observed show negative 2022→23 wage correlations was initially interpreted as strengthening the case for a real AI wage signal. However, both measures share the same structural property: they assign low scores to physical, site-dependent sectors. The agreement simply reflects that both measures are correlated with the post-COVID recovery confound in the same direction. It is not independent evidence of an AI mechanism.

| Period | Eloundou wage r | Anthropic observed wage r |
|--------|----------------|--------------------------|
| 2022→2023 | −0.504 * | −0.416 † |
| 2023→2024 | +0.228 | −0.315 |
| 2024→2025 | +0.380 | +0.321 |
| Composite | +0.245 | +0.299 |

(* p<0.05, † p<0.10)

## What this means for the wage validation

There is no credible AI-driven wage signal in 2022→23 from either model. The 2024→25 positive trending (r ≈ +0.30–+0.38) across both models is more interesting — if it holds in future BLS releases, it would be consistent with a genuine AI productivity-to-wage transmission in exposed sectors — but with n = 22 it remains inconclusive.
