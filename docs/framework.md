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

## Demand Composition Model (experimental)

A third model output, added to test whether the Bounded/Unbounded/Adversarial
taxonomy is a *general* theory of how productivity shocks route into labor
demand, rather than an AI-specific one.

`docs/model_vs_observed_exposure.md` § "Confound: pre-existing sector
composition" records that the dynamic model's sector-level correlation was
already +0.40 to +0.50 in 2006–09, before AI, and files that as a threat to AI
attribution. If the taxonomy describes a general mechanism, that is instead the
expected result. This model makes the question testable by removing AI data from
the predictor entirely.

### Computation

```
gross_displacement_o  = D · [(1 − BOUNDED_REBOUND)·pct_bounded_o
                           + (1 − ADVERSARIAL_REBOUND)·pct_adversarial_o]
absorption_capacity_o = pct_unbounded_o + pct_adversarial_o
K                     = Σ E·gross_displacement / Σ E·absorption_capacity
net_employment_change_o = K·absorption_capacity_o − gross_displacement_o
```

This is the dynamic model with the per-task penetration score `p_t` replaced by a
single economy-wide displacement rate `D`. The rebound constants are unchanged,
so the Adversarial residual-displacement term survives. The predictor contains no
technology-exposure information of any kind, which makes it a strictly harder
test than the AI model faces.

`D` comes from `historical_displacement.py`, primarily from the BLS Displaced
Worker Supplement — the only candidate that isolates structural displacement by
definition rather than by statistical purging, because its "position or shift
abolished" category separates technological and organisational displacement from
plant closings and insufficient work at the survey instrument. That category is
44.4% of long-tenured displacement in the January 2026 release, the largest of
the three reasons. Alternatives were measured and rejected: CPS permanent job
losers correlate 0.944 with the unemployment rate, BED gross job losses 0.860
with its change, and labor productivity growth is negative in 2 of 20 years,
which would invert the model's sign.

### Why D cancels, and why that matters

Because `K = D·κ` where `κ` is a pure composition constant, `net_o = D·(κ·c_o −
g_o)`: the whole score vector scales with `D`, and Pearson r is scale-invariant.
So **D drops out of every cross-sectional correlation.**

This is what makes the design non-circular. The obvious hazard in measuring
displacement from employment data and then validating against employment growth
is that the model predicts its own input. A single economy-wide scalar cannot
manufacture a cross-sectional pattern across 22 sectors or 770 occupations: `D`
sets the amplitude, the taxonomy sets the shape, and only the shape is tested.
`tests/test_composition_model.py` asserts the invariance directly, so it fails
loudly if `D` ever begins carrying cross-sectional information.

`D` therefore governs two things only: the model's amplitude in worker counts,
and its time variation.

### Result: the signal is general, cyclical, and AI adds to it

Sector-level Pearson r against year-over-year employment growth, n = 22 sectors,
averaged in Fisher-z space, COVID periods excluded:

| Model | pre-2022 (21 periods) | AI era (3 periods) | difference | Welch p |
|---|---:|---:|---:|---:|
| Demand composition only | +0.206 | +0.348 | +0.142 | 0.010 |
| Dynamic, AI penetration | +0.199 | +0.455 | +0.256 | 0.033 |
| Rebound-adjusted | −0.029 | −0.274 | −0.245 | 0.132 |
| Observed AI coverage | +0.076 | −0.212 | −0.288 | 0.100 |

The composition-only model has a pre-AI signal, and pre-2022 it is
indistinguishable from the full AI model (+0.206 against +0.199) — unsurprising,
since AI penetration is anachronistic in that era and can add nothing. Its
strongest periods are 2006→07, 2007→08 and 2008→09 (+0.61, +0.66, +0.54, all
individually significant), which is the financial crisis.

That concentration is the confound the era comparison cannot settle on its own: a
pre-AI signal could mean the taxonomy describes a general mechanism, or it could
mean it is picking up cyclical sorting, since Bounded and clerical work is shed
in downturns and rehired in recoveries. `decompose_fit_strength` separates them
by regressing Fisher-z fit strength on the change in unemployment plus an AI-era
indicator (n = 24 periods, COVID excluded):

| Term | Composition only | Dynamic, AI penetration |
|---|---|---|
| intercept (signal at zero cyclical movement) | **+0.224, p < 0.0001** | +0.208, p < 0.0001 |
| change in unemployment | **+0.137, p = 0.0020** | +0.057, p = 0.062 |
| AI era | +0.112, p = 0.349 | **+0.272, p = 0.0052** |
| R² | 0.403 | 0.417 |

Three findings follow.

**The taxonomy has a general, non-cyclical baseline.** The intercept is +0.224
(p < 0.0001) — a real sector-level signal at zero cyclical movement, from a
predictor containing no technology data at all. This is the direct evidence that
the Bounded/Unbounded/Adversarial framework applies before AI.

**Its strength is strongly cyclical.** Each percentage point of rising
unemployment adds +0.137 to composition-only fit strength (p = 0.0020). This
confirms, as a measurement, the hypothesis recorded under
[Future investigation: the business cycle](#future-investigation-the-business-cycle):
the composition fits sector growth best when unemployment is rising. The
mechanism is plausible — labor-saving reorganisation is implemented under
pressure, and recoveries return Bounded jobs the model assumes do not come back
— but the cyclical term is roughly twice the size of the AI model's, whose own
cyclical term no longer clears significance (+0.057, p = 0.062), so composition
alone is the more cycle-dependent measure.

**AI penetration adds a real, separable increment.** Composition-only shows no
AI-era premium once the cycle is controlled (+0.112, p = 0.349), while the
AI-penetration model does (+0.272, p = 0.0052). So the AI-era signal is not
merely the general mechanism running in a particular decade: penetration data
carries information beyond composition, specifically after 2022.

Together these support both claims at once. The framework is general, and AI is
a distinguishable instance of it — which resolves the pre-existing-composition
confound in the AI model's favour rather than against it.

### Two further tests

**Predicted displacement against measured displacement.** The growth-based tests
above score `net_employment_change`, which is `K·absorption_capacity −
gross_displacement` — both halves at once, so a failure cannot be attributed.
`composition_displacement_validation.py` tests the displacement half alone, against
Displaced Worker Supplement Table 5's count of workers who actually lost a job by
occupation group. Employment growth never enters, so circularity is structurally
impossible rather than merely avoided.

The result is null at n = 10: composition Pearson +0.220 (p = 0.541), Spearman
+0.600 (p = 0.067); the AI model +0.261 and +0.491. Both point the right way. The
per-group misses are systematic and more informative than the correlation — the
composition model under-predicts management and professional displacement by 17.8
and 9.9 percentage points while over-predicting service by 15.7, and the AI model
places 49% of all displacement in Office and administrative support against a
measured 9.6%.

Two things bound it. The DWS publishes no occupation × reason cross-tab, so the
test runs on all-reasons displacement, of which only 44.4% is "position or shift
abolished"; the rest is plant closings and insufficient work, which fall heavily
on management and professional staff and plausibly explain much of the largest
miss. And n = 10 groups. This comparison uses the single newest survey as its
headline, but the panel now holds ten biennial surveys (2008–2026), and the same
comparison repeated against every one of them
(`composition_model_displacement_validation_panel.csv`) gives composition
Pearson +0.220 to +0.645 (median +0.387) and dynamic +0.261 to +0.618 (median
+0.567) — ten of ten positive for both models, only 1/10 individually
significant at n=10. That uniform sign is not ten independent confirmations: the
predicted vector is identical across every survey (it is 2025-derived), only the
observed side varies, and consecutive biennial releases share overlapping
three-year recall windows, so a sign test or an averaged r would be bogus. The
consistent direction is noted as suggestive, not pooled into a claim of
significance — this remains a null result under this project's asymmetric
reading rule. See `docs/charts/dws_observed_vs_predicted_displacement.md`.

**Does fit strength track the displacement rate itself?** The cycle decomposition
uses the change in unemployment; the more direct question is whether periods of
greater economy-wide displacement show stronger demand-type sorting. Three D
sources now have enough annual variation to test this
(`historical_displacement.DISPLACEMENT_SOURCES`), and `correlate_with_displacement_rate`
in `composition_era_validation.py` is parameterised over all three rather than
hardcoded to one:

This table is at sector level; `correlate_with_displacement_rate` is run at all
three levels (sector, occupation, and the CPS instrument's ten groups), and each
source is fetched from its own coverage floor — 1997 for `productivity` (widened
past its 1947 start, for the centered-window reason given further below) and
`DEFAULT_START_YEAR` (1981) for the other two, so `mlr_long_tenured`'s own
1981–2000 coverage is never truncated (see the note after the table for why this
matters and what an earlier version of this function got wrong).

| Source | Coverage | `composition_net_change` fit strength |
|---|---|---|
| `productivity` | 1947–2025 (smoothed) | +0.298, p = 0.158, n = 24 |
| `dws_long_tenured` | 2005–2025 (annual, from the ten-survey DWS panel) | +0.629, p = 0.004, n = 19 |
| `mlr_long_tenured` | 1981–2000 (MLR articles' economy-wide rate) | skipped at sector and occupation level — only 1-2 usable periods overlap the OEWS-derived series, which starts in 1999; see below for the CPS level, where seventeen periods overlap |

`dws_long_tenured` is significant at the sector level, and in the same direction
for every model score tested (`net_employment_change` +0.226 p = 0.353,
`occupation_exposure` +0.656 p = 0.002, `observed_exposure` +0.696 p = 0.001).
That agreement across all four scores does not strengthen the finding — it
undermines it. `observed_exposure` is raw Anthropic AI task coverage: it carries
no demand-composition content at all, and it produces the *strongest* correlation
of the four (+0.696, ahead of the composition score's own +0.629). If displacement
sorting by demand type were driving this, the composition score should lead a
measure that has no demand-type information in it, not trail it. Four unrelated
scores moving together points to a shared confound in the test, not to
displacement driving demand-type sorting — and `displacement_rate_time_trend`
(`composition_era_validation.py`, printed by `correlate_with_displacement_rate`
for every source) measures two confounds large enough to be that shared cause:

- **The regressor has only 10 distinct values across the 21 years it spans.**
  `dws_long_tenured` repeats each survey's rate across its whole 2-3-year window,
  so the reported `n = 19` periods carry roughly 10 independent readings, not 19 —
  the p-values above are correspondingly overstated versus what an effective n of
  roughly 10 would justify. That is a direction, not a multiplier: a Pearson
  p-value is a nonlinear function of n, so "overstated" does not mean overstated
  by any fixed factor.
- **`dws_long_tenured` is itself substantially a declining time trend.** Correlated
  against calendar year alone: r = −0.684 (p = 0.0006) over 2005–2025, r = −0.772
  (p = 0.0002) restricted to 2008–2025. A source this collinear with time cannot be
  distinguished, by this test alone, from any other quantity that also moved over
  2005–2025 — including each score's own fit strength, whatever drives it.
- **The AI era sits in the low part of D's range, adjacent to its minimum.** From
  `composition_model_era_comparison.csv`, `occupation_exposure`'s mean sector-level
  fit strength goes −0.029 (pre-2022) to −0.274 (AI era) and `observed_exposure`'s
  goes +0.076 to −0.212 — both flip negative in the AI era. `dws_long_tenured`'s
  value for every AI-era period (2023–2025, one repeated survey window) is 0.69%,
  the 4th-lowest of the source's 10 distinct values; the series' true minimum,
  0.56%, falls in 2021–2022, the last pre-AI period immediately before it. D is
  low precisely where these two scores' fit strength is also low (both negative),
  so a positive D-tracking correlation for `occupation_exposure` and
  `observed_exposure` substantially re-expresses the AI-era sign flip documented
  elsewhere in this section, rather than being independent evidence that
  displacement drives sorting strength.

Put together: the correlation is real as computed, but between the collinearity
with calendar year and the effective n of roughly 10, this test cannot currently
distinguish "fit strength tracks displacement" from "fit strength changed over
2005–2025 for some other reason, and displacement happens to have moved over the
same span." It is reported, with these confounds attached, as a hypothesis check
that the data on hand cannot settle — not as evidence for or against the
displacement mechanism specifically.

`mlr_long_tenured` cannot be tested at the sector or occupation level at all: it
ends in 2000, a year before those OEWS-derived YoY series begin (1999→2000 is
the first period, mapping to displacement year 2000, so at most one or two
periods overlap — below the 5-period floor `correlate_with_displacement_rate`
requires before reporting a source). That skip is a genuine coverage gap at
those two levels, not evidence either way.

At CPS level, where the ten occupation groups reach back to 1983, it is not a
coverage gap: seventeen periods overlap `mlr_long_tenured`'s 1981–2000 coverage,
comfortably above the 5-period floor. The result is a clean null:
`composition_net_change` Pearson −0.170 (p = 0.513, n = 17),
`net_employment_change` −0.212 (p = 0.414), `occupation_exposure` +0.138
(p = 0.596), `observed_exposure` +0.060 (p = 0.818) — nothing reaches
significance in either direction. Per this project's asymmetric reading rule
this is uninformative, not disconfirming, in exactly the same way the
sector-level `productivity` null above is. `mlr_long_tenured` also carries only
6 distinct annual values across the 20 years it spans — thinner even than
`dws_long_tenured`'s 10-in-21 — and is itself a declining time trend against
calendar year (r = −0.490, p = 0.0283): the same two confounds discussed above
for `dws_long_tenured` apply here too, for the same reason, so this null is
additionally uninformative rather than a clean rejection.

An earlier version of `correlate_with_displacement_rate` hardcoded
`start_year=1997` for every source regardless of level. Since 1997 postdates
`mlr_long_tenured`'s own 1981 floor, that genuinely truncated its usable range to
four years at every level — not merely insufficient overlap — so the CPS-level
result above was never computed rather than computed and found small; an earlier
version of this document also described the skip as a coverage gap without
qualifying it as sector/occupation-specific. Both corrected 2026-09-15.

### Limitations

**2025 labels applied backwards.** The demand-type classifications come from
2025 O\*NET task statements. Occupational task content genuinely changed over
2005–2025, so earlier periods carry more anachronism; reaching further back buys
power at the cost of construct validity.

**The era test is under-powered.** Three AI-era periods against fifteen pre-AI,
autocorrelated. The Welch comparison is descriptive; the cycle decomposition,
with 18 periods and a continuous regressor, is the stronger of the two and should
carry the interpretation.

**Uniform technology exposure.** The model asserts that technology touches every
task equally, which is false — 1990s software hit routine tasks hardest. It is
the minimal assumption that keeps the test clean. Where it shows: scores are a
function of composition alone, so 239 of 770 occupations are exactly 100% Bounded
and tie on one floor value. Drywall and Ceiling Tile Installers and Procurement
Clerks score identically, because the model cannot know software reaches the
second and not the first. Any claim from this model about a specific occupation
is really a claim about its composition class. Relaxing this — plausibly by
weighting with a Routine Task Intensity index built from the O\*NET data already
on disk — is the first thing to try next.

**The DWS panel reaches 2008 as counts, not the spec's 1984 floor — extended back
to 1981-82 as rates.** An earlier note here claimed BLS published no archive of
prior Displaced Worker Supplement releases, so the panel held only the single
January 2026 survey; that claim was wrong — see the correction in `CLAUDE.md`
under `seeds/dws_displacement_panel.csv` — and the panel now holds ten biennial
surveys, 2008–2026, as counts. The archive itself is the hard floor for that
route: no BLS news-release archive exists for 2000–2006, so 2008 is as far back
as counted releases go. Pre-2008 history instead comes from the Displaced Worker
Supplement results BLS published in *Monthly Labor Review* articles rather than
news releases — as displacement *rates* on the 1980-census occupational
taxonomy, not counts, crosswalked to the ten modern DWS groups
(`seeds/mlr_occupation_crosswalk.csv`, `mlr_displacement.py`). Two crosswalk rows
sit below `high` confidence: `Handlers, equipment cleaners, helpers, and
laborers` is flagged low-confidence because it genuinely splits across the
modern production and transportation/material-moving groups, and the crosswalk
sends the whole 1980-census bucket to one side as a judgement call, not a fact;
`Other precision production occupations` is flagged medium-confidence for the
same kind of reason, less severely — the 1980-census precision-production
bucket does not map cleanly onto one modern group either. Combined coverage is 1981-82
through 2023-25, with a hole at 2001-04: BLS published neither a news-release
archive nor an MLR article for the 2002 or 2004 surveys. Because rates cannot be
summed with counts, the two bases are kept distinguishable in the panel
(`measurement_basis`, `source` columns) rather than blended, and every consumer
that aggregates `displaced_thousands` filters to counts only — so this extension
adds history without changing any existing correlation.

That panel extension folds MLR rates in at the occupation level
(`mlr_rows_for_panel`), but the panel itself was not, on its own, a route to a
new *economy-wide* D: `dws_displacement_rate` filters to `measurement_basis ==
"count_thousands"` and so never reads those rate rows. `historical_displacement.py`
now reaches D back to 1981 by a second, independent path: `mlr_long_tenured`
parses Table 2's own economy-wide "Total, 20 years and older" row directly out of
the three MLR article PDFs (`mlr_displacement.parse_total_displacement_rate`,
`historical_displacement.mlr_displacement_rate`) rather than going through the
panel at all. Its annual values run 1.20%–1.95% over 1981–2000 — higher than
`dws_long_tenured`'s 0.56–1.69%, because the two divide by different
denominators (long-tenured workers *employed* for the MLR rate, versus *total*
employment for the count-derived rate) and are two different quantities that
happen to share units, not one series with a level break. `mlr_long_tenured` is
therefore its own entry in `DISPLACEMENT_SOURCES`, never spliced onto
`dws_long_tenured` or `dws_structural_long_tenured` — the same rule the project
already applies to CPS-versus-OEWS employment. `DEFAULT_START_YEAR` moved from
1984 to 1981 to match: `mlr_long_tenured` is now the binding floor on how far
back D's time variation reaches, not the DWS count panel. The cross-sectional
correlations remain invariant to which `D` source is chosen either way, since D
is a scalar that cancels out of them; only D's amplitude and time variation
differ by source.

### Future investigation: the business cycle

Recorded so the observation is not lost; the first half of it is now measured by
`decompose_fit_strength` (see [Result: the signal is general, cyclical, and AI
adds to it](#result-the-signal-is-general-cyclical-and-ai-adds-to-it) above), and
the within-sector premium below remains untested. Pairing each 1999→2025
period with the change in national unemployment suggests the demand-type
composition fits sector growth best when unemployment is *rising* and worst in
recoveries (2010→13, 2020→22), when cyclical rehiring returns Bounded jobs the
model assumes do not come back. Within sector, the Unbounded growth premium is
counter-cyclical (large in downturns, near zero in recoveries) while the
Adversarial premium is roughly steady through the cycle and persists in
recoveries. A plausible mechanism is that Adversarial spending — sales, legal,
security — is defensive within the firm and needs no capital investment,
whereas labor-saving adoption does. This now rests on nine rising-unemployment
periods — the 2001 recession contributes 2000→01, 2001→02 and 2002→03, tripling
the cyclical identification the earlier 2005-start series allowed — but still on
2025 task labels applied backwards, so it remains a hypothesis.
The crosswalk harmonization in `harmonize_soc.py` covers exactly this kind
of code churn for 1999→2025 at occupation level. 1999 is a hard floor for OEWS:
the 1997 and 1998 files use the pre-SOC five-digit OES coding system, and before
1997 the survey was industry-based with no wage data. Reaching further back means
switching instrument to the CPS — see
`docs/superpowers/specs/2026-09-13-deep-history-extension-design.md`, which works
the question through to a 1983 floor and records why 1960 is not defensible:
per-year task reclassification against the occupational definitions of that era
would still be required, and the decennial-only data before 1962 cannot support
year-over-year periods at all.

### A second instrument: CPS, 1983→2026

The OEWS floor above has since been worked around, not lifted: `cps_historical_panel.py`
adds annual CPS occupation-group employment — the ten `LNU0203220x` series fetched
directly from the BLS historical timeseries API, the same underlying classification
Table A-19 also draws from, but not the Table A-19 page itself, which this project
already uses for a different, more recent chart (see `docs/cps_data_expansion.md`) —
as a second, independent employment instrument covering ten occupation groups from
1983 to 2026 — 43 year-over-year periods, more than double OEWS's 1999→2025 span. It
is a separate instrument from OEWS, drawn as a separate series and never spliced onto
it: CPS is a
household survey that counts the self-employed and agriculture, so its totals
(~101M in 1983 rising to ~163M in 2025) legitimately run above OEWS's 127–130M
for the same years. Over the years both instruments cover, they agree only
moderately (260 paired group-periods, Pearson r = 0.547, mean |difference| =
0.0215) — enough to say the pre-1999 CPS-only stretch is not contradicted by
the one check available, not enough to call it validated to OEWS precision. Ten
groups also means less power than 22 sectors: significance needs |r| ≈ 0.63
here against ≈ 0.42 at sector level, so figures at the two levels are not
comparable in magnitude.

Run through the same era comparison and cycle decomposition as the sector-level
result above, `composition_net_change` on the CPS instrument is a null: the
AI-era mean r (+0.256, n=4 periods) is not distinguishable from the pre-2022
mean (+0.425, n=37 periods; Welch p = 0.445), and the cycle decomposition's
`ai_era` term is negative and non-significant (n=41 periods, R² = 0.023). Under
this project's anachronism rule — 2025 O\*NET labels are strong evidence when
they still produce a positive result, but uninformative rather than
disconfirming when they do not — this null says nothing against the taxonomy.
One divergence is worth flagging rather than burying: the business-cycle term
that is significant at sector level (+0.137, p = 0.002) vanishes at CPS level
(+0.030, p = 0.692), and the data on hand do not distinguish between candidate
explanations (ten-group aggregation, genuinely different pre-1999 cyclical
behaviour, and instrument differences). Full numbers, the two internal
comparability breaks the CPS series carries, and the composition-stability
sensitivity check are in `docs/charts/composition_model_signal_over_time_cps.md`.

### Detailed occupations (deep history, Phase 2)

The CPS instrument above runs at ten occupation groups. Phase 2 raises the
cross-sectional n by tabulating IPUMS CPS microdata directly, rather than the
published ten-series route above, onto two finer grains — **333 `occ1990dd`
occupations** (Autor and Dorn's time-consistent spine, chosen because Phase 1
already pinned it and because a detailed 1983–2002 Census→SOC crosswalk does
not exist published), excluding the unclassified code 999, and a
**22-SOC-major rollup**, both 1983–2026 — plus a Displaced Worker Supplement
validation at the coarser **Dorn partition, ~25 occupation groups per
survey**, the finest resolution DWS cell sizes can support. The
published-crosswalk chain (below) reaches only **328 of the 333** codes; the
remaining five exist solely in pre-2010 Census vintages with no route to a
modern SOC code at all. Of the 328 the chain reaches, only **307 meet the 0.8
labeled-share floor** with the model's real scores (measured 2026-09-23) —
the rest are diluted below that floor by unlabeled SOC constituents. Neither
grain replaces the ten-group CPS instrument above; each level
writes its own files (`cps_detailed_*`, `occ1990dd_*`, `cps_major_*`,
`dws_detailed_*`), and none carries a `level` column. CI never tabulates this
level; `cps_detailed_panel.py` and `dws_detailed_panel.py` run only locally,
against IPUMS microdata, and write committed aggregate seeds — see the
README's IPUMS section for the rebuild procedure.

**The label bridge is a published crosswalk chain, with its own error
measured.** Demand-type labels live on SOC 2018 codes; the panel lives on
`occ1990dd`. `occ1990dd_soc_bridge.py` chains each `occ1990dd` code through
Dorn's own occ2010 crosswalk to a 2010 Census code, then through the
Census/BLS code list to SOC 2010, then through `seeds/soc_crosswalks` to SOC
2018 — anchored on 2010 because that is the newest vintage Dorn's crosswalks
reach. Where one `occ1990dd` code splits across several SOC codes, 2022 OEWS
employment sets the split weights, the same anchor the harmonized SOC units
already use. A unit's score is the weighted mean over its *labeled* SOC
constituents only (`labeled_share` records how much weight those carry), and
`dominant_demand` is re-derived after aggregation rather than carried, per the
Chief Executives failure mode documented in `CLAUDE.md`. Gate **G4** checks
this chain's fitness for 2003–2026 by scoring each `occ1990dd` code a second,
direct way — straight from the raw CPS `OCC` code for that year's vintage to
SOC, bypassing the chain entirely — and requiring the two score vectors to
correlate at r ≥ 0.8 in every coding block (2003–10, 2011–19, 2020–26). Below
that, the bridge is unfit: no detailed-level or rollup result file is written,
and the design returns for review. **This measured error is a lower bound for
1983–2002 only** — no direct route exists from the 1980 or 1990 Census
occupation vintages to SOC, so the compounded error in exactly the stretch
Phase 2 buys (the 1983–2002 span, spanning the 1990–91 downturn) cannot itself
be measured and is not claimed to be bounded by the 2003+ figure.

**Every build-time and pipeline-time gate, and what promotes a seed.** A
seed is written only if every gate its build's gate record depends on
passed — `promote_rebuilt` in `cps_detailed_panel.py` and
`dws_detailed_panel.py` refuses to promote otherwise:

| Gate | Check | Threshold | Runs in |
|---|---|---|---|
| **G1** | Microdata mapped to Phase 1's ten CPS groups through raw `OCC`, bypassing the bridge, against Phase 1's published series | Within 1% per group-year, `COMPWT`, gated from 2003 onward (`G1_TOLERANCE = 0.01`, `G1_FIRST_GATED_YEAR = 2003`); reported only before 2003 | Build (`cps_detailed_panel.py`) |
| **G2** | Economy-wide civilian employment against the published CPS annual mean (`LNU02000000`) | Within 1% from 1998 (`G2_TOLERANCE = 0.01`), `COMPWT`; reported only before 1998 | Build (`cps_detailed_panel.py`) |
| **G3** | Long-tenured displacement by Phase 1's ten groups against published Table 5 rows | Within 3% of the published figure or half a published thousand, whichever is looser (`G3_TOLERANCE = 0.03`, `G3_ROUNDING_THOUSANDS = 0.5`) | Build (`dws_detailed_panel.py`) |
| **G4** | Chained vs. direct `occ1990dd` scores, correlated across units | r ≥ 0.8 in every coding block (`G4_MINIMUM_R = 0.8`); below it, no detailed-level or rollup result file is written and the design returns for review | Pipeline (`occ1990dd_soc_bridge.py`, from the committed crosstab seed) |
| **G5** | Every `occ1990dd` code carrying employment falls in exactly one Dorn group | Structural — the partition must be exhaustive and non-overlapping | Build (`cps_detailed_panel.py`) and test |
| **G6** | Civilian employment carrying an `OCC1990` code Dorn's table cannot map to any `occ1990dd` code | At most 1% of civilian employment, every year (`G6_MAXIMUM_UNMAPPED_SHARE = 0.01`) — added by the implementation plan, beyond the original design's gate list | Build (`cps_detailed_panel.py`) |
| **G6D** | Lost-job weight in the DWS supplement reaching no `occ1990dd` code | At most 1% of lost-job weight, every survey (`G6D_MAXIMUM_UNMAPPED_SHARE = 0.01`) — added by the implementation plan | Build (`dws_detailed_panel.py`) |

G1, G2, G5 and G6 gate `cps_detailed_panel.py`'s promotion
(`REQUIRED_GATES = ("G1", "G2", "G5", "G6")`); G3 and G6D gate
`dws_detailed_panel.py`'s (`REQUIRED_GATES = ("G3", "G6D")`) — two separate
gate records, since the two builds promote independently. G4 alone runs in
the pipeline rather than the build, because it needs the model's current
scores, which change with every re-synthesis; it is checked fresh on every
`main.py composition` run rather than once at build time.

**Year-over-year noise at this grain is accepted by decision, not corrected.**
A median-size `occ1990dd` occupation (~90k workers) carries a level relative
standard error near 15%, so its year-over-year growth carries a standard error
of roughly 15–20% against genuine cross-occupation growth differences of only
a few percent — estimated reliability **~0.1–0.2**, measured per period in
`cps_detailed_reliability.csv`. Multi-year growth windows would fix this by
letting real change accumulate while endpoint noise stays fixed, and were
considered; they were declined because they would cut the detailed test from
37 usable periods to roughly 9–12, and the decision was to run year-over-year
and see how it turns out. The only noise handling is therefore a bracket:
`reliability = 1 − mean(sampling variance of growth) / variance(observed
growth)`, and `r_corrected = r_raw / sqrt(reliability)` where reliability is
positive. Raw r is biased toward zero; the household-cluster bootstrap behind
the sampling-variance estimate treats adjacent years as independent when half
the sample actually carries over, which overstates growth noise and biases
corrected r away from zero. The two bracket the true value rather than pinning
it — and where measured reliability is near the low end of the estimated
range, the two can diverge widely. If a result later motivates a move to
multi-year windows, that move is recorded as a named deviation, not a quiet
change.

**Eligibility is chosen per period, and the fixed alternative is a
sensitivity only.** A code enters a given year-over-year period's test if its
employment relative standard error is ≤ 20% in *both* endpoint years — not a
single set of codes held fixed across the whole span. A fixed set would drop
every occupation that was small at either end of 1983–2026: typists, word
processors, and telephone operators on the way down; computer occupations on
the way up. Those are exactly the occupations that changed most, so a fixed
set selects on the outcome and hides the strongest cases. Per-period
eligibility keeps a code until it is genuinely unmeasurable, at the cost that
eras compare somewhat different occupation mixes — bounded by reporting each
period's eligible count and employment share, and by the fixed-set and
10%/20%/30%/no-cutoff sweep in `cps_detailed_eligibility_sweep.csv`. Four
known seam periods (1991→92, 1993→94, 2002→03, 2010→11 — coding-vintage and
survey-design breaks, not method artifacts) are excluded from the headline the
same way Phase 1 excludes COVID periods, and measured, not patched, in
`cps_detailed_seam_breaks.csv`.

**The asymmetric reading rule applies here more strongly than at any other
grain.** A positive result at detailed occupation level is strong evidence,
because 2025 O\*NET demand-type labels applied to 1990-vintage occupation
categories across 1983–2026 is the hardest test this project runs — if the
taxonomy still shows through that much anachronism and that much sampling
noise, it is not an artifact of convenient aggregation. A null result proves
nothing: task content drifts more for an individual occupation than for a
sector aggregate, `occ1990dd` forces modern occupations into categories built
for 1990, and estimated reliability of ~0.1–0.2 means most of a null's
variance could be sampling noise rather than absence of signal. The
composition-stability proxy from the ten-group CPS instrument
(`sector_composition_stability.csv`) is recomputed at this grain, so the
least-stable occupations can be named directly rather than inferred from
sector shares.

**Pre-written readings, in the spec's own terms, before any result was
seen:**

- Expected magnitude: the harmonized-SOC occupation-level composition r
  averages +0.123 pre-AI; CPS sampling noise attenuates further, so per-period
  raw r in roughly **+0.05 to +0.15**, possibly lower, is an expectation, not
  a threshold.
- A positive, significant intercept in the detailed cycle decomposition across
  1983–2026 (three downturns) means the general mechanism holds at occupation
  grain, not only at sector aggregation.
- A detailed-level null alongside a positive 22-major rollup result, from the
  *same* microdata, would mean the signal is between-sector composition
  rather than within-sector occupational sorting — informative despite the
  reliability caveats, because anachronism alone cannot explain a gap between
  two grains built from identical source data.
- An era difference whose sign flips between raw and corrected r is
  attributed to noise, not reported as an era effect.
- The AI era contributes only 4 periods at this grain (2022→23 through
  2025→26); no AI-specific claim is made from it, whatever the result.
- At the Dorn partition (n≈25), a per-survey displacement correlation above
  roughly r = 0.40 is individually significant. As with the ten-group DWS
  panel, a uniform sign across surveys is noted but never pooled into a
  significance claim — the predicted vector is identical across surveys, so a
  sign test or averaged r would be bogus.

One resolution choice narrowed after the original design: the 1990 Census
occupational subheadings sensitivity for the DWS validation is not run,
because no such code list exists in the Census documentation directory the
plan checked — the Dorn ~25-group partition is the DWS headline with no
finer-grained sensitivity available.

#### Results

Measured against the pre-written readings above, from the first local IPUMS
build (2026-09-24). Every deviation made while building this — the DWS
self-employment and recall-rule fixes, the redefined G6D, and the
rate-measure-leads-share-measure interpretation decision — is recorded with
its reasoning and commit in the Deviations log of
`docs/superpowers/plans/2026-09-23-deep-history-phase-2.md`; the numbers below
are computed under those corrected definitions, not the ones the plan started
with.

**Gate G4 passed in every coding block**
(`occ1990dd_bridge_check.csv`): chained-vs-direct score correlation is
r = 0.993 (2003–2010, n=315 codes), r = 0.994 (2011–2019, n=315), and
r = 0.997 (2020–2026, n=293) — all comfortably above the 0.8 threshold, so
every detailed-level and rollup file below was written. **This is a lower
bound on the chain's error for 1983–2002 only**: no direct CPS-to-SOC route
exists for the 1980/1990 Census occupation vintages, so the bridge's fitness
for the 1983–2002 span — which is exactly the stretch this phase exists to
reach, including the 1990–91 downturn — is unmeasured, not merely
unfavorable.

**Detailed occupations (`occ1990dd`, 333 codes, 1983–2026).** The cycle
decomposition (`composition_cycle_decomposition_cps_detailed.csv`, `run ==
"headline"`, n=37 periods) gives `composition_net_change` an intercept of
+0.078 (p = 5.0e-6, well under 0.0001), `unemployment_change` +0.022
(p = 0.148, not significant), and `ai_era` +0.001 (p = 0.984, not
significant). Per the spec's pre-written reading, **a positive, significant
intercept across 1983–2026 means the general demand-type mechanism holds at
occupation grain, across the three downturns this span covers, not only at
sector or ten-group aggregation** — with the reliability caveat below
attached to how much confidence that intercept can carry. The cyclical and
AI-era terms are indistinguishable from zero at this grain and power.

The era comparison (`composition_model_era_comparison_cps_detailed.csv`,
`run == "headline"`, `composition_net_change`): pre-AI mean r = +0.073
(n=33 periods, 11 individually significant), AI-era mean r = +0.082 (n=4
periods, 0 significant), difference +0.009, Welch p = 0.810 — not
distinguishable from zero. The pre-AI mean falls at the bottom of the spec's
expected +0.05 to +0.15 range, consistent with the expected-magnitude
reading. The `noise_corrected` view cannot arbitrate the era difference the
way the spec's "sign differs between raw and corrected r" rule anticipates:
correcting for sampling noise leaves only 1 AI-era period with a defined
corrected r (−0.012, against a pre-AI corrected mean of +0.223 over 14
periods) — too thin to compare against the raw view rather than
contradicting it, so this AI-era result is read the same way the spec
already requires independent of any raw/corrected disagreement: **4 periods,
no AI-specific claim at this level, whatever the sign.**

Neither grain returned the null the "detailed null, rollup positive" reading
anticipates — the detailed intercept above is itself significant and
positive — so that specific contingency does not apply here; instead both
grains agree in direction, which is a milder form of the same result
(below).

**22-major rollup, same microdata, 1983–2026.** Cycle decomposition
(`composition_cycle_decomposition_cps_major.csv`, n=41 periods):
`composition_net_change` intercept +0.277 (p = 8.2e-8), `unemployment_change`
−0.002 (p = 0.961), `ai_era` −0.134 (p = 0.316). Era comparison
(`composition_model_era_comparison_cps_major.csv`): pre-AI mean r = +0.271
(n=37, 11 significant), AI-era mean r = +0.142 (n=4, 0 significant),
difference −0.129, Welch p = 0.346 — again not distinguishable from zero.
The rollup's intercept is roughly 3.5x the detailed intercept (+0.277 vs.
+0.078) built from the *same* microdata and the same demand-type labels —
consistent with `docs/charts/composition_model_signal_over_time_occupation.md`'s
already-documented pattern that sector- or group-level aggregation raises r
by averaging away occupation-level idiosyncratic noise rather than by adding
information. Read the two intercepts as confirming the same mechanism at two
resolutions, not as a contradiction.

**Reliability is far below the spec's own estimate, and the noise-handling
bracket is mostly unavailable as a result.** Median reliability across all 43
periods is **0.005** (`cps_detailed_reliability.csv`), against the spec's
pre-written estimate of ~0.1–0.2 — meaning essentially all of the measured
year-over-year growth variance at `occ1990dd` grain is sampling noise, not
signal. Because `r_corrected = r_raw / sqrt(reliability)` is undefined for
reliability ≤ 0, 89 of the 172 period/score rows in the full (`seams_included`)
view have no corrected r at all — the raw/corrected bracket the spec named as
the only noise handling is available for just over half of this grain's
results. This was accepted by decision before any data existed (see the
"Year-over-year noise at this grain is accepted by decision" paragraph
above), not discovered as a problem now.

The eligibility-cutoff sweep (`cps_detailed_eligibility_sweep.csv`,
`composition_net_change`, pre-AI mean r) ranges from **+0.053** (no cutoff)
to **+0.112** (10% RSE cutoff), with the headline 20% cutoff at +0.073 and
the fixed-set sensitivity at +0.077 — all inside the spec's expected +0.05
to +0.15 band, and none reversing sign.

**Seams.** Only one of the four excluded seam periods actually stands out
(`cps_detailed_seam_breaks.csv`): the 2002→2003 classification-change seam
carries a median |growth| of 0.169 against an ordinary-period median of
0.067 — a real, disclosed break. The other three measure indistinguishably
from an ordinary period — 1991→92 at 0.065, 1993→94 at 0.065, and 2010→11 at
0.070 — but all four stay excluded per the pre-pinned choice rather than
being reinstated on the strength of this measurement, the same treatment
Phase 1 gives COVID periods.

**Displaced Worker Supplement at the Dorn partition (~25 groups, 21 surveys,
1984–2024).** Per the user's decision, interpretation leads with the
size-free rate measure rather than the share measure
(`composition_model_displacement_validation_detailed.csv`,
`tenure_class == "all_tenures"`, `measure == "rate"`): the composition
model's per-survey Pearson r has a median of **+0.319** (range +0.218 to
+0.401), positive in all 21 surveys, 1 of 21 individually significant against
the spec's n≈25 threshold of r ≈ 0.40. The dynamic model's rate correlation
has a median of **−0.036** and is positive in only 7 of 21 surveys. Per the
spec's rule, uniform positive sign across the composition model's 21 surveys
is noted, not pooled into a significance claim — the predicted vector is
identical across surveys.

The share measure tells a different story once checked against a
group-size-only benchmark added during execution (see the Deviations log):
composition's share correlation (median r = +0.899) is essentially
indistinguishable from the benchmark of a group's plain employment share
alone predicting its displacement share (median r = +0.905) — **the share
test at this partition mostly measures group size, not the demand-type
model.** The same comparison at the coarser ten-group DWS partition
(`composition_model_displacement_size_benchmark.csv`) shows the model
trailing the size benchmark by more here (composition 0.387 vs 0.752) than
at the Dorn partition above (0.899 vs 0.905), which is why the rate measure,
where the benchmark does not apply, is the informative test here rather than
the share result.

One definitional break is disclosed rather than patched: the DWRECALL
recall-expectation exclusion (added to fix gate G3) does not exist before the
1994 survey, so the 1992→1994 boundary carries a method change that cannot be
applied before 1994. It is sized for the first two surveys with DWRECALL:
`measure_recall_rule_impact` shows the rule removes 4.24% of recall-included
all-tenures weight in 1994 and 4.66% in 1996, about 2.5x the all-tenures
total's sampling RSE (~1.7–1.8%, computed from `seeds/dws_detailed_panel.csv`).
The removal concentrates in construction, farming and production (see the
Deviations log in `docs/superpowers/plans/2026-09-23-deep-history-phase-2.md`),
so pre-1994 surveys' group mix is not strictly comparable. Per-survey
correlations are never pooled, which limits the effect but does not remove
it.

**Composition-stability proxy at this grain** is in
`occ1990dd_composition_stability.csv`, following the same method as the
ten-group instrument's `sector_composition_stability.csv`, naming the
`occ1990dd` codes where carrying 2025 O\*NET labels back to 1983 is least
defensible directly, rather than inferring it from sector shares. 41 of the
328 mapped codes carry a `stable_share` of exactly zero — none of their 2022
OEWS-anchored SOC weight sits in a detailed occupation OEWS already
published in 1999. These concentrate in occupations created or redefined
well after 1999: computer occupations (`occ1990dd` 64 — database
administrators, computer systems analysts, web developers, and the other
titles the ~3% SOC-2018 computer-code renumbering survivorship figure above
already documents independently), physicians and surgeons (84), registered
nurses and nurse practitioners (95), and dentists (85) among them — the same
occupations flagged as least stable at sector grain (SOC 15 Computer and
Mathematical, SOC 29 Healthcare Practitioners and Technical), now named
individually rather than only bounded by sector share.

**Bottom line, read against the asymmetric rule strengthened for this grain:**
the detailed-occupation cycle decomposition returns a significant, positive,
non-cyclical intercept across three downturns and 43 years of the most
anachronism- and noise-exposed test this project runs — read as evidence the
general mechanism is not an artifact of sector aggregation, tempered
immediately by the reliability figure above. The era and AI-specific results
at both detailed and rollup grain are null (Welch p = 0.81 and 0.35), which
under this project's asymmetric rule is uninformative, not disconfirming — at
n=4 AI-era periods, no result at this grain could have supported an
AI-specific claim regardless of sign. The displacement validation, led by the
rate measure, shows a uniformly positive but individually mostly
non-significant composition signal (median +0.319 across 21 surveys) against
a materially weaker dynamic-model signal (median −0.036) — the clearest
directional separation between the two models in this phase — while the
share measure at the same partition is shown to mostly recover group size
rather than the model. Because the predicted vector is the same model score
applied to every survey year, the 21 surveys are one comparison repeated
against 21 independent measurements, not 21 independent tests of the model —
the uniform sign is corroborating, but it cannot be pooled into a stronger
significance claim than any single survey already carries.
