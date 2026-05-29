# Eloundou Theoretical Exposure: Sector-Level Wage Validation

**File:** `eloundou_sector_level_wage_validation.png`

![Eloundou Sector-Level Wage Validation](images/eloundou_sector_level_wage_validation.png)

## What this chart shows

Same layout as `eloundou_sector_level_employment_validation.png` but with sector mean wage growth on the y-axis. Four panels: 2022→23, 2023→24, 2024→25, composite.

## Correlation by period

| Period | r | p |
|--------|---|---|
| 2022→2023 | −0.504 | **0.017** |
| 2023→2024 | +0.228 | 0.307 |
| 2024→2025 | +0.380 | 0.081 |
| Composite | +0.245 | 0.272 |

## Key observation: a significant negative wage signal in 2022→23

**r = −0.504, p = 0.017** in 2022→23 is the strongest single-period wage correlation among all four sector-level models. Sectors with higher theoretical AI exposure had *lower* wage growth in 2022→23. This is the expected direction under a displacement model: if AI capability is concentrated in high-exposure sectors and is beginning to reduce labor demand there, wage growth in those sectors should lag.

This is also the only statistically significant wage result at the sector level across any model in any period.

## The sign flip: negative in 2022→23, positive afterward

The correlation is negative in 2022→23 (r = −0.504), near zero in 2023→24 (r = +0.228), and trending positive in 2024→25 (r = +0.380, p = 0.081). The composite (r = +0.245) averages across the reversal and reaches no significance.

Several interpretations are plausible:

**Productivity-wage cycle:** AI tools first compress wages in exposed sectors as labor demand softens (2022→23), but once productivity gains are internalized, firms share the surplus with workers — wage growth in exposed sectors recovers or exceeds the baseline (2023→24 onward).

**Sector-level noise:** With n = 22 sectors, any single influential data point can flip the correlation. Office and Administrative Support — the highest-exposure sector — is the dominant influence; its wage trajectory could explain most of the sign flip without any structural mechanism.

**Lag structure:** The 2022→23 negative signal may reflect anticipatory wage moderation in AI-exposed sectors before AI adoption actually scaled. Later periods reflect a different equilibrium.

## Comparison to Anthropic observed model

The Anthropic observed exposure model (`anthropic_observed_sector_level_wage_validation.md`) shows a nearly identical pattern: r = −0.416 (p = 0.054) in 2022→23, then positive in later years. Both capability-based (Eloundou) and usage-based (Anthropic) measures agree on the direction and approximate timing of the wage signal, lending credibility to the 2022→23 finding — it is not an artifact of a single measurement approach.
