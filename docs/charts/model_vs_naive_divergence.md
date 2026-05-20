# Where the Model Diverges Most from the Naive Exposure Baseline

**File:** `model_vs_naive_divergence.png`

## What this chart shows

These are the five occupations where this model's prediction departs most from what you'd expect if AI exposure always caused displacement.

The bar length is the **divergence score**: model impact + Eloundou et al. exposure estimate. Under the naive assumption (impact = −exposure), this sum would be zero for every occupation. A large positive divergence means the model predicts strong expansion for an occupation that prior literature rates as highly exposed to AI.

Each bar is annotated with both the model's impact score and the raw exposure estimate, so you can see how large the departure is in absolute terms.

## How divergence is computed

```
divergence = occupation_impact + eloundou_exposure_mid
```

`occupation_impact` is this model's net labor demand prediction (positive = expansion, negative = displacement). `eloundou_exposure_mid` is the Eloundou et al. estimate of how exposed the occupation's tasks are to LLMs. Their paper implicitly assumes exposure leads to displacement; adding the two quantities together measures how far this model departs from that assumption.

## Why these occupations show up here

All five are Unbounded or Adversarial demand types. For example:

- **Market Research Analysts:** High exposure (54%) because many analysis tasks are AI-amenable, but the demand for market insight is open-ended — time saved on one analysis immediately fills with the next. Model predicts +60%.
- **Computer Programmers:** Very high exposure (82%) in the literature, but programming demand has historically expanded with productivity tools rather than contracting. Model predicts +28%.
- **Writers and Authors:** Similar dynamic — exposure is high (84%) because writing is LLM-amenable, but content demand is elastic. Model predicts +23%.

The chart is intentionally limited to five occupations to highlight the clearest signal; see `prior_exposure_vs_model_impact.png` for the full distribution.
