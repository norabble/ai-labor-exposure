# Sector-Level Validation

**File:** `sector_level_validation.png`

![Sector-Level Validation](images/sector_level_validation.png)

## What this chart shows

Each bubble is one of the 22 BLS major occupational groups (e.g., "Healthcare Practitioners," "Computer and Mathematical"). The x-axis is the sector's employment-weighted mean model impact score; the y-axis is its composite employment or wage growth. Bubble size scales with total employment in the sector.

## Why sector aggregation strengthens the test

Individual occupation-level validation is noisy: a single occupation's growth can swing due to idiosyncratic events (a regulation change, a wave of retirements) that have nothing to do with AI. When 50–300 occupations are averaged together into a sector, most of that noise cancels out and the structural signal becomes clearer.

## What the correlation statistics mean

**Employment panel (left):** r = 0.283, p = 0.202. The model's sector-level employment predictions point in the right direction but do not reach statistical significance. This is consistent with the broader picture across all validation charts: AI-driven employment effects are not yet detectable in BLS data through 2025. This could mean the effects are still ahead of us, or that the model's employment predictions are wrong.

**Wage panel (right):** r = −0.485, p = 0.022. Sectors where the model predicts negative net impact (Bounded-dominated sectors) show relatively lower composite wage growth; sectors with positive predicted impact (Unbounded/Adversarial-dominated) show higher wage growth. The negative sign reflects the direction of the impact score: negative impact = more Bounded = weaker wages.

This is the strongest statistical signal in the entire validation suite. One interpretation: even if headcounts haven't changed yet, the wage data may be picking up early signals of structural pressure — Bounded-sector workers seeing less wage growth, Unbounded/Adversarial workers seeing a productivity premium. Another interpretation: the wage pattern reflects pre-existing sector dynamics that happen to correlate with our classifications, rather than AI effects specifically.

## Jackknife robustness

The wage result (r = −0.485, p = 0.022) was tested with leave-one-out jackknife resampling: the correlation was re-computed 22 times, each time dropping a different sector. In all 22 cases the p-value remained below 0.05 — the result is not driven by any single sector. This is notable given n = 22 and a 3-year observation window.
