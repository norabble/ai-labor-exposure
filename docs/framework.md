# Conceptual Framework

This document defines the terminology and model assumptions for the AI labor
exposure analysis. It is the authoritative reference for how key terms are used
across the codebase, documentation, and outputs.

## Project Goal

This project produces a **structural exposure score** — a current snapshot of
which occupations are most exposed to AI-driven demand change, stratified by
the type of demand response expected. It is *not* a displacement prediction.

The distinction matters:

- A **structural exposure score** describes the economic character of an
  occupation's AI-exposed work right now. It does not assert that employment
  will fall by a specific amount or on a specific timeline.
- A **displacement prediction** would require a much stronger model: one that
  accounts for adoption rates, complementary skill adjustments, wage
  equilibration, policy responses, and macroeconomic context.

The model is tested against BLS employment data as an ongoing confidence check:
does the structural categorization correlate with real-world outcomes at all? A
null result is expected and not damaging — the effects of AI on labor markets
may not yet be detectable in aggregate annual data. A non-null correlation is
fortuitous evidence that the structural categories are tracking something real.

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

This is the primary output of this model (`occupation_exposure` in the codebase).

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

## Naming Conventions (Pending)

The current codebase uses `occupation_exposure` and narrative labels like "High
Displacement Risk" that imply prediction rather than structural description.
Renaming to better reflect the structural exposure framing (e.g., "High
Structural Exposure") is under consideration. This document will be updated when
that decision is made.
