# Conceptual Framework

This document defines the terminology and model assumptions for the AI labor
exposure analysis. It is the authoritative reference for how key terms are used
across the codebase, documentation, and outputs.

## Project Goal

This project produces two complementary model outputs:

1. **Structural exposure score** (`occupation_exposure`) — a cross-sectional
   snapshot of which occupations are most exposed to AI-driven demand change,
   stratified by demand type. It is *not* a displacement prediction.

2. **Dynamic net employment change** (`net_employment_change`) — a macro-level
   redistribution model that holds total employment constant and routes displaced
   labor into occupations with Unbounded or Adversarial capacity. Produces a signed score per
   occupation summing to zero economy-wide.

The distinction between exposure and prediction matters:

- A **structural exposure score** describes the economic character of an
  occupation's AI-exposed work right now. It does not assert that employment
  will fall by a specific amount or on a specific timeline.
- A **displacement prediction** would require a much stronger model: one that
  accounts for adoption rates, complementary skill adjustments, wage
  equilibration, policy responses, and macroeconomic context.

Both models are tested against BLS employment data as ongoing confidence
checks. A null result at the occupation level is expected and not damaging —
the effects of AI on labor markets may not yet be detectable in annual
occupation-level data. The dynamic model does show a significant sector-level
employment signal (r = +0.53 and +0.48, p < 0.05, in 2023→24 and 2024→25), which
constitutes evidence that the sector-level demand-type composition is tracking
something real. That signal rests heavily on one sector — see [Leave-one-sector-out
jackknife](#leave-one-sector-out-jackknife).

## Exposure Type Taxonomy

Three distinct types of AI exposure appear in this project. They differ in what
they are grounded in, their temporal orientation, and their known limitations.

### Theoretical Exposure

**Definition:** An estimate of whether a task *could theoretically* be
accomplished or accelerated by 50% or more using an LLM, based on human or LLM
judgment.

**Example:** Eloundou et al. (2024), *GPTs are GPTs*
([Science](https://www.science.org/doi/10.1126/science.adj0998)).

**Properties:**
- Grounded in capability judgment, not direct demonstration
- Not tied to a specific time period — could reflect past, present, or future
  capability; likely influenced by current capabilities even when estimating
  future potential
- An informed guess, not an observation

**Limitations:**
- Guesses are shaped by the imagination of the rater, which is anchored to
  current capabilities even when explicitly asked to consider future ones
- Different raters, prompts, or models produce different estimates

### Observed Exposure

**Definition:** An empirically measured fraction of an occupation's O\*NET tasks
that appear in actual AI usage logs (e.g., Claude conversation data).

**Example:** Anthropic's task penetration dataset (`anthropic_task_penetration.csv`).

**Properties:**
- Grounded in demonstrated behavior, not capability estimates
- Tied to a specific observation window — becomes outdated as capabilities and
  usage patterns change
- Reflects where AI adoption has already occurred

**Limitations:**
- **Time-bound:** A snapshot; does not reflect future adoption or capability
- **Depth-unquantified:** A task appearing in logs could mean 5% of instances
  are AI-assisted or 95%; the penetration score doesn't distinguish
- **No rebound signal:** Demonstrates feasibility and current usage; says
  nothing about whether demand for the task's output will expand to absorb the
  productivity gain
- **Granularity:** An O\*NET task statement may bundle sub-tasks where only some
  are exposed, or the exposed portion is not the economically load-bearing one

### Rebound-Adjusted Exposure

**Definition:** Observed exposure discounted by the demand type's expected
rebound fraction:

```
rebound_adjusted_exposure = observed_penetration × (1 − rebound_fraction)
```

This is the primary output of the static model (`occupation_exposure` in the
codebase).

**Properties:**
- Addresses the *rebound signal* gap in observed exposure by applying a
  structural prior about whether demand will absorb the productivity gain
- Inherits the time-bound and depth limitations of its observed exposure input
- The rebound fractions are structural priors, not empirically estimated; they
  should be treated as research parameters subject to future calibration

**Relationship to elasticity:** Demand elasticity (estimated from historical
price/demand data) and rebound target the same underlying mechanism — how much
does demand respond to productivity changes? The key difference is that
elasticity is backward-looking through pre-AI data, while rebound is a
structural prior designed for a post-regime-change scenario. Historical
elasticity can serve as a validation signal and eventual calibration source for
rebound fractions, but cannot be the primary input because the rules of demand
are changing. See the OpenAI AI Jobs Transition Framework for an elasticity-
based approach to the same problem.

## Demand Type Definitions

Tasks are classified into three demand types. The classification is a judgment
about how the task's demand responds to AI-driven productivity changes.

### Bounded

**Definition:** The task's own productivity gain does not feed back into demand
for that task. Completing the task faster or cheaper does not generate more of
the same task.

**Economic character:** Near-zero demand elasticity with respect to own
productivity. Demand for the task is set by external factors, not by the task's
cost or speed.

**Example:** Ordering office supplies. If AI enables faster ordering, you don't
order more supplies. The number of offices (an external factor) determines
demand. If more offices open — driven by factors unrelated to supply-ordering
efficiency — demand rises, but that is a side effect of another variable, not a
feedback from the task's own productivity.

**Rebound expectation:** Low. Most of the productivity gain translates to
reduced human labor demand for that task, since demand doesn't expand to absorb
it.

### Unbounded

**Definition:** The task's productivity gain does feed back into demand for that
task, and the resulting demand growth is non-zero-sum. Cheaper or faster
execution generates more of the same work; the total value created by that work
grows.

**Economic character:** Positive demand elasticity with respect to own
productivity. Falling cost or rising speed expands how much of the work gets
done.

**Example:** Writing summaries. If AI makes summarization cheap, more documents
get summarized, and there is always more to summarize. The demand for summaries
expands with the supply of cheap summarization.

**Rebound expectation:** High. Much of the productivity gain is absorbed by
expanding demand.

### Adversarial

**Definition:** A subset of Unbounded in which demand growth is zero-sum. A
counterparty responds to any capability gain by escalating, so the work volume
expands but the net value created is neutral — it is an arms race, not net
expansion.

**Relationship to Unbounded:** Adversarial is not a third parallel category; it
is a carve-out from Unbounded. The demand-growth mechanism is the same
(productivity feeds back into demand), but the escalation dynamic means the
expansion cancels itself out.

**Example:** Fraud detection. Better fraud detection → more sophisticated fraud
→ more fraud detection needed. Employment in fraud detection holds or grows, but
the net social value of the additional work is approximately zero — it is
restoring a status quo disrupted by the adversary's response.

**Rebound expectation:** Very high. The zero-sum escalation means nearly all of
the productivity gain is absorbed by the arms race.

## Classifier Note

The Bounded/Unbounded/Adversarial classification is applied to one-sentence
O\*NET task descriptions by an LLM (Gemini via Vertex AI). This requires the
classifier to reason about the demand structure of a task's output — whether
its productivity feeds back into demand — from minimal text context. Classifier
reliability has not been formally validated.

A proposed validation path: compare classifications against historical demand
elasticity data. In tasks where AI has not yet significantly disrupted demand
dynamics, we would expect Bounded tasks to show low historical elasticity and
Unbounded/Adversarial tasks to show high elasticity. Outliers would split into
two interpretable types: classification errors, or genuine regime changes where
the pre-AI demand dynamics are no longer informative.

## Rebound Fractions

Current values (tunable in `synthesize_impacts.py`):

| Demand Type | Rebound | Net exposure fraction |
|-------------|--------:|----------------------:|
| Bounded | 0.1 | 0.9 |
| Unbounded | 0.7 | 0.3 |
| Adversarial | 0.9 | 0.1 |

These are structural priors set by judgment. They represent the fraction of
observed penetration expected to be absorbed by demand rebound, leaving the
remainder as persistent structural exposure. They are intentionally exposed as
tunable research parameters and should be calibrated against elasticity data
when that becomes available.

## Dynamic Labor Equilibrium Model

The dynamic model is a second output layer that builds on the rebound-adjusted
exposure inputs to model economy-wide labor redistribution.

### What conservation is for — and what it is not

The naive exposure models this project is arguing against share an implicit
assumption: that AI capability over a task removes the labor doing it, full
stop. Displaced work simply disappears from the accounting, and no equilibrating
response is modeled. That is not a neutral baseline — it is the strong claim
that the reabsorption rate is exactly zero.

The dynamic model's conservation constraint is the device for stating the
opposite: displaced labor goes *somewhere*, and where it goes is a function of
which occupations have demand that can expand to receive it. Holding total
employment fixed is the simplest way to write that down. It is a normalization
that makes the redistribution question askable, not an empirical claim.

**In particular, the model does not assert that total employment is constant,
that headcount is conserved economy-wide, or that occupational employment
fractions are fixed.** Any of those would be a strong and probably false claim
about the labor market. What the model asserts is weaker and more defensible:
*some* equilibrating response exists, and its direction is toward Unbounded
capacity.

The distinction matters because the results turn out to be insensitive to the
constraint holding exactly — see [Robustness to the equilibration
rate](#robustness-to-the-equilibration-rate) below. The conservation constraint
picks one defensible point on a wide plateau, and the finding survives anywhere
on it. Reading conservation as a load-bearing assumption overstates what the
model needs.

### Redistribution rule

Displaced labor is routed into occupations whose demand can expand to receive
it, in proportion to each occupation's share of total economy-wide
capacity-weighted employment. **Absorption capacity** is the share of an
occupation's task importance that is Unbounded *or* Adversarial. Adversarial is
a carve-out from Unbounded — the productivity-to-demand feedback is the same,
only the expansion is zero-sum — so it receives displaced labor on the same
footing. Treating Adversarial as pure displacement with no capacity, as an
earlier version of the model did, contradicted the taxonomy above and scored
Legal and Sales and Related as net losers while both grew.

### Computation

For each occupation *o*, the rebound-adjusted exposure contributions are already
decomposed by demand type:

```
gross_displacement_o = bounded_exposure_contribution_o
                     + adversarial_exposure_contribution_o

total_displaced = Σ_o(employment_o × gross_displacement_o) / Σ_o(employment_o)

absorption_capacity_o = pct_unbounded_o + pct_adversarial_o

absorption_o = (absorption_capacity_o / economy_weighted_avg_absorption_capacity)
             × total_displaced

net_employment_change_o = absorption_o − gross_displacement_o
```

The employment-weighted sum of `net_employment_change` is zero by construction
(verified by assertion at runtime). Occupations with above-average absorption
capacity gain workers; Bounded-heavy occupations lose them.

Because `total_displaced`, `total_employment`, and the capacity total are all
economy-wide scalars, the absorption step collapses to a single global constant
— the **absorption scalar** — times each occupation's `absorption_capacity`:

```
absorption_o = absorption_scalar × absorption_capacity_o

  where absorption_scalar = Σ_o(employment_o × gross_displacement_o)
                          / Σ_o(employment_o × absorption_capacity_o)

net_employment_change_o = absorption_scalar × absorption_capacity_o
                        − gross_displacement_o
```

This is an identity, not an approximation (asserted in `tests/test_pipeline.py`).
It is what makes the robustness check below possible: the absorption scalar is
the model's entire equilibration assumption reduced to one number, so varying it
sweeps the model across equilibration rates. At the current parameters the
conservation-pinned value is **0.1578**.

### Robustness to the equilibration rate

`compute_equilibration_sensitivity` in `synthesize_dynamic.py` re-runs the
sector-level employment validation with the absorption scalar scaled to
fractions and multiples of its conservation-pinned value. Multiplier 0 is the
no-equilibrium model — displaced labor vanishes and the score is pure
displacement pressure. Large multipliers approach the opposite limit, where
reabsorption dominates and the score is pure absorption-capacity composition.

Sector-level Pearson r against composite BLS employment growth, n = 22:

| × conservation value | absorption scalar | sector r | p |
|---------------------:|------------------:|---------:|------:|
| 0 (no equilibrium) | 0.0000 | +0.351 | 0.109 |
| 0.10 | 0.0158 | +0.389 | 0.073 |
| 0.25 | 0.0395 | +0.435 | 0.043 |
| 0.50 | 0.0789 | +0.483 | 0.023 |
| 0.75 | 0.1184 | +0.503 | 0.017 |
| **1.00 (conservation-pinned)** | **0.1578** | **+0.509** | **0.015** |
| 1.50 | 0.2367 | +0.504 | 0.017 |
| 2.00 | 0.3156 | +0.492 | 0.020 |
| 5.00 | 0.7890 | +0.448 | 0.037 |
| 10.00 | 1.5781 | +0.425 | 0.048 |
| 100.00 | 15.7805 | +0.401 | 0.064 |

Sector growth here and in every other sector-level test is the change in each
major group's total employment from the OEWS file's own summary row
(`bls_sector_trends.csv`), not the mean growth of the scored occupations — see
`docs/charts/model_signal_over_time.md` § How sector growth is measured.

Three things follow.

**The no-equilibrium assumption is the worst-performing point on the curve.**
At multiplier 0 the correlation falls to +0.351 and loses significance
(p = 0.109). This is the model's central claim stated as a measurement:
assuming displaced labor simply disappears fits the BLS sector data worse than
assuming it goes somewhere.

**The result does not depend on conservation holding exactly.** Every
equilibration rate from 25% to 1,000% of the conservation-pinned value clears
p < 0.05; the pure-composition limit at 100× just misses (p = 0.064). The
finding sits on a broad plateau rather than a knife-edge, so a reader who
rejects strict labor conservation — reasonably — does not thereby lose the
result. It survives at a quarter of the reabsorption rate and at ten times it.

**Conservation lands near the optimum, but not meaningfully so.** The curve
peaks at r = +0.509 at the pinned value. That is a favorable coincidence rather
than evidence: at n = 22 the difference between +0.509 and the +0.40 asymptote
is not statistically distinguishable (Steiger's test on the dependent
correlations gives p = 0.42). The plateau is the finding; its peak is not.

Written to `data/output/equilibration_sensitivity.csv` and printed during
`validate`.

### Leave-one-sector-out jackknife

A Pearson r over 22 sector means can be carried by a single sector far from the
others. `compute_sector_jackknife` in `synthesize_dynamic.py` drops each sector
in turn and recomputes the composite employment correlation. Written to
`data/output/sector_jackknife.csv` and summarised during `validate`.

| Dropped sector | sector r | p |
|---|---:|---:|
| Office and Administrative Support | +0.344 | 0.126 |
| Community and Social Service | +0.462 | 0.035 |
| Life, Physical, and Social Science | +0.482 | 0.027 |
| Sales and Related | +0.495 | 0.023 |
| *(17 others)* | +0.50 to +0.55 | ≤ 0.021 |
| Arts, Design, Entertainment, Sports, and Media | +0.591 | 0.005 |

Office and Administrative Support is the one sector whose removal takes the
result above p = 0.05. It sits alone in the lower-left of the scatter: the most
negative sector score by a wide margin, the largest employment weight, and the
only large sector with negative composite growth. It should be read as the core
of the finding rather than as an outlier — clerical work is where the model's
mechanism (high penetration, almost entirely Bounded, employment falling since
2016) is most visible — but the headline r should always be quoted with its
jackknife range, +0.34 to +0.59, beside it.

### Relationship to the rebound-adjusted model

The two models are complementary:

| Property | Rebound-adjusted | Dynamic |
|----------|-----------------|---------|
| Output range | ≥ 0 (structural pressure) | signed (redistribution) |
| Unbounded treatment | Small positive exposure (0.3×penetration) | Absorption sink |
| Adversarial treatment | Near-zero exposure (0.1×penetration) | Absorption sink alongside Unbounded; its 0.1×penetration still counts as displacement |
| Conservation | None | Sums to zero — a normalization, not an assumption |
| Validated at sector level | 2023→24 only (r = −0.43, p = 0.047) | r = +0.53 and +0.48, p < 0.05 (2023→25); jackknife range +0.34 to +0.59 |

The rebound-adjusted model identifies *which occupations are under structural
pressure*; the dynamic model identifies *where net labor flows* under a
conservation constraint.

### Scope and limitations

**Scope:** The model operates on the ~770 BLS-matched occupations. Conservation
holds within this subset, not the full labor force — which is a statement about
the normalization, not a limitation of the result, since the sector-level
finding holds across two orders of magnitude of equilibration rate (see
[Robustness to the equilibration rate](#robustness-to-the-equilibration-rate)).

**Absorption proportional to headcount, not skill adjacency.** The current
absorption formula routes displaced workers to all Unbounded and Adversarial
occupations proportionally to `absorption_capacity × employment`. This means a
displaced medical records specialist is modeled as partially flowing into
Cardiologists — occupations with high absorption capacity and large employment. This is
economically incoherent over any near-to-medium-term horizon: workers cannot
retrain into high-credential professions in a single market cycle.

The model is better understood as identifying *which sectors absorb displaced
labor* (the sector-level signal is real) than as predicting *occupation-specific
flows* (the occupation-level signal is not detectable in current BLS data). A
future version of the model would weight absorption by occupational adjacency or
retraining feasibility, which would shift predicted gains from high-credential
Unbounded occupations (Surgeons, Cardiologists) toward lower-credential Unbounded
occupations that are more accessible to displaced workers.

**Static penetration data.** The `bounded_exposure_contribution` inputs come
from time-averaged AI penetration scores. They capture the accumulated state of
AI adoption rather than a real-time flow signal, limiting the model's ability to
predict near-term occupation-specific dynamics.

### Future investigation: the business cycle

Not pursued; recorded so the observation is not lost. Pairing each 2005→2025
period with the change in national unemployment suggests the demand-type
composition fits sector growth best when unemployment is *rising* and worst in
recoveries (2010→13, 2020→22), when cyclical rehiring returns Bounded jobs the
model assumes do not come back. Within sector, the Unbounded growth premium is
counter-cyclical (large in downturns, near zero in recoveries) while the
Adversarial premium is roughly steady through the cycle and persists in
recoveries. A plausible mechanism is that Adversarial spending — sales, legal,
security — is defensive within the firm and needs no capital investment,
whereas labor-saving adoption does. This rests on three rising-unemployment
periods and 2025 task labels applied backwards, so it is a hypothesis only.
The crosswalk harmonization now in `harmonize_soc.py` covers exactly this kind
of code churn for 2005→2025 at occupation level; testing the hypothesis back to
1960 would need the same treatment applied to the pre-2000 SOC classifications,
plus per-year task reclassification against the occupational definitions of
that era.
