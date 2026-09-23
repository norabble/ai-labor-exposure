# Model Predictive Value vs. Observed AI Exposure

## What this document is

This compares **three** predictors of BLS employment and wage growth, asking
whether the demand-type machinery in this project adds value over simply knowing
how much AI coverage an occupation already has:

1. **Rebound-adjusted exposure score** (`occupation_exposure`) — the static
   model's demand-type-adjusted score, `penetration × (1 − rebound_fraction)`
   per task, rolled up to occupation level. **Gross, non-negative.**
2. **Observed AI task coverage** — Anthropic's empirical measure of what fraction
   of an occupation's O\*NET tasks appear in actual Claude conversation logs
   (`anthropic_job_exposure.csv`). **Gross, non-negative.**
3. **Dynamic net employment change** (`net_employment_change`) — the dynamic
   labor equilibrium model's signed redistribution score, summing to zero
   economy-wide (see `framework.md` § Dynamic Labor Equilibrium Model). **Signed.**

### Read the sign before the magnitude

The three predictors do **not** validate in the same direction, because they do
not mean the same thing:

| Predictor | Output | "Model is correct" means |
|-----------|--------|--------------------------|
| Rebound-adjusted exposure | gross pressure (≥ 0) | **negative** r with growth (more exposure → less growth) |
| Observed coverage | gross coverage (≥ 0) | **negative** r with growth |
| Dynamic net change | signed (gainer/loser) | **positive** r with growth (predicted gainers grow) |

A reader who lines up rebound's −0.18 next to dynamic's +0.15 and concludes they
"disagree" has misread both — both point the *same* way once the sign convention
is applied. The tables below are therefore split by predictor, never pooled into
a single magnitude column.

## Rebound parameters used

- `BOUNDED_REBOUND = 0.1`
- `UNBOUNDED_REBOUND = 0.7`
- `ADVERSARIAL_REBOUND = 0.9`

---

## Occupation level: all three predictors are weak

At the individual-occupation level, none of the three predictors explains much
variance in annual employment growth. This is expected — AI's effect on
occupation-level headcount is not cleanly detectable in 2022–2025 BLS data. The
comparison is about *relative* strength, not absolute predictive power.

### Employment — rebound-adjusted vs. observed coverage

Both are gross measures, so the correct sign is **negative**.

**All occupations (n ≈ 754):**

| Period | Rebound-adjusted r | Observed coverage r |
|--------|-------------------:|--------------------:|
| 2022→2023 | −0.026 | −0.031 |
| 2023→2024 | −0.051 | −0.058 |
| **2024→2025** | **−0.085*** | −0.072* |
| Composite | **−0.081*** | −0.077* |

**Occupations with non-zero AI penetration only (n ≈ 397):**

| Period | Rebound-adjusted r | Observed coverage r |
|--------|-------------------:|--------------------:|
| 2022→2023 | −0.051 | −0.058 |
| 2023→2024 | −0.082 | −0.093 |
| **2024→2025** | **−0.219*** | **−0.175*** |
| Composite | **−0.179*** | −0.158** |

`*` p < 0.05, `**` p < 0.01, `***` p < 0.001

The rebound-adjusted model's advantage over raw coverage is largest in
2024→2025 (r = −0.219 vs. −0.175). The gap is demand type doing real work: an
Unbounded or Adversarial occupation with the same raw coverage as a Bounded one
receives a lower exposure score, and that discount turns out to be predictively
correct — those occupations are not shedding employment at the same rate.

### Employment — dynamic net change

The dynamic score is **signed**, so the correct sign is **positive** (predicted
gainers should grow). Computed on the 770-occupation merge between
`occupation_dynamic_model_report.csv` and `bls_trends.csv`:

| Period | Dynamic r (all, n = 770) | Dynamic r (displaced subset, n = 306) |
|--------|-------------------------:|--------------------------------------:|
| 2022→2023 | +0.076* | +0.079 |
| 2023→2024 | +0.135*** | +0.203*** |
| 2024→2025 | +0.105** | +0.167** |
| Composite | **+0.166*** | **+0.222*** |

(The displaced subset restricts to occupations with `gross_displacement > 0`,
i.e. those with Bounded/Adversarial exposure that the model actually redistributes.)

The dynamic model is the only one of the three with the *right sign for its
semantics* and statistical significance at the occupation level — but the
magnitudes are still modest. Its real strength is not here.

## The 2024→2025 signal is strengthening over time

This holds for both gross and dynamic measures. Among penetrated occupations,
the rebound-adjusted employment correlation grows consistently:

| Period | Rebound-adjusted r | p-value |
|--------|-------------------:|--------:|
| 2022→2023 | −0.058 | 0.244 |
| 2023→2024 | −0.088 | 0.079 |
| 2024→2025 | −0.219 | < 0.001 |

Consistent with AI adoption effects accumulating: displacement undetectable in
2022–2023 aggregate data is beginning to appear in 2024–2025. The highest-impact-
quartile occupations with the worst 2024→2025 employment drops include Computer
Programmers (−16%), Desktop Publishers (−16%), Statistical Assistants (−20%),
Bioinformatics Technicians (−20%), and Technical Writers (−18%).

---

## Sector level: the dynamic model wins decisively

Aggregating to the 22 SOC major groups (employment-weighted means, n = 22) is
where the three predictors separate. The dynamic model's redistribution signal,
washed out by occupation-level noise, emerges as the **strongest employment
signal in the entire project**.

### Employment, sector level

| Predictor | Type | Composite r | 2023→24 r |
|-----------|------|------------:|----------:|
| **Dynamic net change** | signed | **+0.509*** | **+0.530*** |
| Rebound-adjusted | gross | −0.290 | −0.428* |
| Observed coverage | gross | −0.223 | −0.373† |
| Eloundou theoretical | gross | +0.018 | −0.140 |

`†` p < 0.10, `*` p < 0.05 (dynamic: composite p = 0.015, 2023→24 p = 0.011; leave-one-sector-out range +0.34 to +0.59). Sector growth is the BLS major-group total, not the mean of scored occupations.

Reading the signs: the dynamic model's **+0.509** is correct for a signed measure
(predicted-gainer sectors grew). The rebound-adjusted **−0.290** and observed
coverage's **−0.223** are correct for gross measures (high-pressure sectors grew
less); Eloundou is flat. Measured on major-group totals, the two gross measures
keep their expected sign at the sector level — an earlier version of this table,
built on the growth of surviving detailed occupations, had them flipping to
weakly positive, which turned out to be a survivorship artefact of the SOC code
revisions rather than a composition effect.

Cross-references: `dynamic_sector_level_employment_validation.md`,
`sector_level_employment_validation.md`,
`anthropic_observed_sector_level_employment_validation.md`,
`eloundou_sector_level_employment_validation.md`.

The dynamic model's sector signal is roughly **1.8× the magnitude** of the next
strongest predictor (rebound-adjusted) and is the only one significant at
p < 0.05 in every period from 2023 onward. The explicit conservation constraint —
routing displaced labor into sectors with Unbounded or Adversarial capacity — is
what sharpens the diffuse "Unbounded sectors grow" tendency that observed
coverage only hints at. One sector carries much of it: dropping Office and
Administrative Support leaves r = +0.344 (p = 0.126).

### Confound: pre-existing sector composition

Extending the historical BLS baseline back to 2005 (see `model_signal_over_time.md`)
reveals that the dynamic model's sector-level r was already elevated **before AI**:
+0.40 to +0.50 in 2006→09 and +0.37 in 2017→18, well before meaningful AI
adoption. Sectors with Unbounded and Adversarial demand — Computer and
Mathematical, Healthcare, Life Sciences, Legal, Management — have grown faster
than Bounded sectors for decades as part of a long-running secular transition in
the labour market. The dynamic model formalises this tendency and is therefore
partly tracking a structural property of the economy, not purely an AI-era effect.

The AI-era values (+0.53 in 2023→24, +0.48 in 2024→25) sit inside that pre-AI
range, not above it. This is not a defect: the demand-type classification is a
general theory of how labor-saving disruption shows up in employment
composition, and earlier waves — conventional software, business-process
automation — should produce the same signature. What is specific to AI is the
expectation that it will accelerate the pattern, and three post-2022 years
cannot yet distinguish acceleration from continuation.

**The rebound-adjusted model has a pre-AI analog too, in the same direction.**
Its AI-era signal (r = −0.43 in 2023→24, the only significant sector-level
period for that model) is preceded by −0.15 to −0.27 in 2016→19, when Office
and Administrative Support employment was already falling. The
penetration-weighted displacement term identifies clerical work, and clerical
work was shrinking before generative AI; the AI-era reading is best described
as the same displacement, larger.

Definitive attribution of either signal to AI specifically would require
OEWS 2025→2026 annual data (not yet available) and, more fundamentally, a
longer pre-AI baseline against which an acceleration could be measured.

**This confound is now tested directly** — see `docs/framework.md` § Demand
Composition Model. Stripping every trace of AI data from the predictor, leaving
demand-type composition alone, leaves a general non-cyclical signal (intercept
+0.238, p = 0.0004) whose strength is strongly cycle-dependent (+0.160 per
percentage point of rising unemployment, p = 0.0024) and which shows *no* AI-era
premium once the cycle is controlled (+0.093, p = 0.476). The AI-penetration
model, run through the same decomposition, does show one (+0.238, p = 0.021). So
the pre-existing elevation recorded above is real and is largely cyclical, and an
AI-specific increment survives it.

---

## Wages: the dynamic model adds nothing

For wage growth, the conclusion from earlier versions of this document is
unchanged, and the dynamic model does **not** improve it.

### Occupation level

Observed coverage remains the strongest wage predictor; the rebound-adjusted
model gets the sign wrong in 2022→2023 among penetrated occupations.

| Metric | Rebound-adjusted r | Observed coverage r |
|--------|-------------------:|--------------------:|
| Wage 2023→2024 (all) | **−0.154*** | −0.125*** |
| Wage composite (all) | −0.097** | **−0.131*** |
| Wage 2022→2023 (penetrated) | **+0.019** (wrong sign) | **−0.101*** |
| Wage composite (penetrated) | −0.087 | **−0.145*** |

The **dynamic net change** score is essentially uncorrelated with wage growth at
the occupation level (composite r = −0.007, n.s.; no period exceeds |r| = 0.07).

### Sector level

The dynamic model shows no wage signal at the sector level either (composite
r = −0.222, p = 0.32; no period significant — see
`dynamic_sector_level_wage_validation.md`), and neither does the rebound-adjusted
model (composite r = −0.218, p = 0.33). Measured against each major group's own
median wage, though, **observed coverage does**: composite r = −0.502
(p = 0.017), negative in 2022→23 (r = −0.442, p = 0.040) and 2023→24
(r = −0.484, p = 0.022), and negative on every leave-one-sector-out subsample.
High-coverage knowledge sectors — Computer and Mathematical, Business and
Financial, Legal, Arts and Media, Sales — had the weakest median-wage growth of
any sectors over 2022→25. Part of that is the post-COVID catch-up in physical
and care sectors, but excluding the six recovery sectors leaves r = −0.42, so it
is not only that. See `anthropic_observed_sector_level_wage_validation.md`.
Eloundou's earlier apparent 2022→23 wage result is not significant on the
totals series (r = −0.394, p = 0.070).

The demand-type models do not reproduce this: a sector's median wage growth
tracks how much of its work AI already covers, not the model's structural
pressure or redistribution score. Conceptually that is expected — wage growth
is shaped by productivity premiums and labor scarcity across all demand types,
and neither model is built to predict it — but it does mean raw coverage
carries wage information the demand-type discount throws away.

---

## Summary: predictive value by outcome × level

The two-axis view is the point of this comparison. The right predictor depends on
both *what* you are predicting and at *what level of aggregation*.

| | Occupation level | Sector level |
|--------------|------------------------------------------|----------------------------------|
| **Employment** | All three weak; dynamic best-signed (+0.17 composite), rebound-adjusted beats observed on the penetrated subset | **Dynamic net change (+0.51)** — strongest signal in the project; one-sector dependent |
| **Wages** | Observed AI task coverage | Observed AI task coverage (composite r = −0.50, p = 0.017); demand-type models null |

Takeaways:

- **Demand type earns its keep on employment, not wages.** Both the
  rebound-adjusted discount and the dynamic redistribution improve employment
  prediction; neither helps with wages, where raw observed coverage is best at
  both levels.
- **Aggregation level decides which model to use.** For occupation-level
  structural-pressure ranking, the rebound-adjusted score is the cleaner gross
  measure. For *where net labor flows across the economy*, the dynamic model at
  the sector level is by far the most informative output the project produces.
- **Sign before magnitude.** The rebound-adjusted and dynamic models look like
  they disagree (negative vs. positive r) only because one is gross pressure and
  the other is signed redistribution. Once read correctly, they tell a consistent
  story: AI-exposed Bounded work is under employment pressure, and the sectors
  with Unbounded or Adversarial absorption capacity are the ones gaining.
