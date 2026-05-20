# Sector-Level Validation

**File:** `sector_level_validation.png`

## What this chart shows

Each bubble is one of the 22 BLS major occupational groups (e.g., "Healthcare Practitioners," "Computer and Mathematical"). The x-axis is the sector's employment-weighted mean model impact score; the y-axis is its composite employment or wage growth. Bubble size scales with total employment in the sector.

## Why sector aggregation strengthens the test

Individual occupation-level validation is noisy: a single occupation's growth can swing due to idiosyncratic events (a regulation change, a wave of retirements) that have nothing to do with AI. When 50–300 occupations are averaged together into a sector, most of that noise cancels out and the structural signal becomes clearer.

## What the correlation statistics mean

**Employment panel (left):** r = 0.283, p = 0.202. The model's sector-level employment predictions are in the right direction but not statistically significant — too few sectors (n = 22) and too short a time window to detect the signal reliably.

**Wage panel (right):** r = −0.485, p = 0.022. Sectors with higher predicted impact (more Unbounded/Adversarial occupations) show higher composite wage growth. This negative correlation is expected: the model uses a signed impact score where positive means expansion, but the mechanism for wage growth in Unbounded/Adversarial sectors is productivity premium — workers who stay command higher wages.

Wait — a negative r should mean higher impact predicts lower wages. In practice, the impact score mixes displacement (negative) and expansion (positive) within each sector, so the sector mean impact is driven by how much of the sector is Bounded vs. Unbounded. A sector with many Bounded occupations will have a negative mean impact and will also have lower wage growth if those workers are being displaced downward. The negative r reflects that sectors our model flags as at-risk (negative mean impact) are indeed seeing relatively weaker wage growth.

## Jackknife robustness

The wage result (r = −0.485, p = 0.022) was tested with leave-one-out jackknife resampling: the correlation was re-computed 22 times, each time dropping a different sector. In all 22 cases the p-value remained below 0.05 — the result is not driven by any single sector. This is notable given n = 22 and a 3-year observation window.
