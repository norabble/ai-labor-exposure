# Model Predictive Value vs. Observed AI Exposure

## What this document is

This compares two predictors of BLS employment and wage growth:

1. **Rebound-adjusted exposure score** (`occupation_exposure`) — this model's demand-type-adjusted rebound-adjusted exposure score, computed as `penetration × (1 − rebound_fraction)` per task, rolled up to occupation level.
2. **Observed AI task coverage** — Anthropic's empirical measure of what fraction of an occupation's O\*NET tasks appear in actual Claude conversation logs (`anthropic_job_exposure.csv`).

The question: does classifying demand type (Bounded / Unbounded / Adversarial) add predictive value over simply knowing how much AI coverage an occupation already has?

## Rebound parameters used

Results below were produced with:
- `BOUNDED_REBOUND = 0.1`
- `UNBOUNDED_REBOUND = 0.7`
- `ADVERSARIAL_REBOUND = 0.9`

## Employment: model is stronger

For employment growth — the outcome the model is designed to predict — the demand-type adjustment adds value over raw coverage.

### All occupations (n ≈ 754)

| Period | Model r | Obs. Coverage r |
|--------|--------:|----------------:|
| 2022→2023 | −0.026 | −0.031 |
| 2023→2024 | −0.051 | −0.058 |
| **2024→2025** | **−0.085*** | −0.072* |
| Composite | **−0.081*** | −0.077* |

### Occupations with non-zero AI penetration only (n ≈ 397)

Restricting to occupations with actual Anthropic task coverage sharpens the signal considerably.

| Period | Model r | Obs. Coverage r |
|--------|--------:|----------------:|
| 2022→2023 | −0.051 | −0.058 |
| 2023→2024 | −0.082 | −0.093 |
| **2024→2025** | **−0.219*** | **−0.175*** |
| Composite | **−0.179*** | −0.158** |

`*` p < 0.05, `**` p < 0.01, `***` p < 0.001

The model's advantage is largest in 2024→2025, where r = −0.219 vs. −0.175 for raw coverage. The gap reflects demand type doing real work: an Unbounded or Adversarial occupation with the same raw coverage as a Bounded one receives a lower exposure score, and that discount turns out to be predictively correct — those occupations are not losing employment at the same rate.

## The 2024→2025 signal is strengthening over time

Among occupations with non-zero penetration, the employment correlation has grown consistently:

| Period | Model r | p-value |
|--------|--------:|--------:|
| 2022→2023 | −0.058 | 0.244 |
| 2023→2024 | −0.088 | 0.079 |
| 2024→2025 | −0.219 | < 0.001 |

This is consistent with AI adoption effects accumulating: displacement that could not be detected in 2022–2023 aggregate data is beginning to appear in 2024–2025. The occupations in the highest impact quartile showing the worst 2024→2025 employment drops include Computer Programmers (−16%), Desktop Publishers (−16%), Statistical Assistants (−20%), Bioinformatics Technicians (−20%), and Technical Writers (−18%).

## Wages: observed coverage is stronger

For wage growth, the model does not add value over raw coverage and in some cases underperforms.

### All occupations

| Metric | Model r | Obs. Coverage r |
|--------|--------:|----------------:|
| Wage 2023→2024 | **−0.154*** | −0.125*** |
| Wage composite | −0.097** | **−0.131*** |

### Non-zero penetration only

| Metric | Model r | Obs. Coverage r |
|--------|--------:|----------------:|
| Wage 2022→2023 | **+0.019** (wrong sign) | **−0.101*** |
| Wage 2023→2024 | −0.081 | −0.040 |
| Wage composite | −0.087 | **−0.145*** |

Raw observed coverage is the stronger wage predictor, and the model gets the sign wrong in 2022→2023 among penetrated occupations. This makes conceptual sense: wage growth is shaped by productivity premiums and labor scarcity across all demand types, not just structural exposure pressure. The model discounts Adversarial and Unbounded coverage toward zero — but workers in those roles may be seeing wage gains precisely *because* of that coverage. Stripping it out hurts wage prediction.

## Summary

| Outcome | Better predictor |
|---------|-----------------|
| Employment growth (especially 2024→2025) | **Rebound-adjusted exposure score** |
| Wage growth | **Observed AI task coverage** |

The model adds predictive value specifically where it is designed to — structural exposure pressure on employment — by using demand type to distinguish coverage that will reduce headcount from coverage that will be absorbed. For wages, the raw signal from observed AI usage is more informative than the rebound-adjusted exposure score.
