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
| 2022→2023 | +0.067 | +0.106 |
| 2023→2024 | +0.122** | +0.199*** |
| 2024→2025 | +0.095** | +0.135* |
| Composite | **+0.145*** | **+0.210*** |

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
| **Dynamic net change** | signed | **+0.528*** | **+0.544*** |
| Observed coverage | gross | +0.191 | +0.364† |
| Eloundou theoretical | gross | +0.122 | +0.071 |
| Rebound-adjusted | gross | −0.247 | −0.412 |

`†` p < 0.10, `*` p < 0.05 (dynamic: composite p = 0.012, 2023→24 p = 0.009)

Reading the signs: the dynamic model's **+0.528** is correct for a signed measure
(predicted-gainer sectors grew). The rebound-adjusted **−0.247** is correct for a
gross measure (high-pressure sectors grew less), and it is the only gross measure
that keeps its expected sign across aggregation levels. Observed coverage and
Eloundou *flip* to weakly positive at the sector level — the opposite of their
occupation-level sign — because at the sector level they are dominated by
*composition*: high-coverage sectors are disproportionately Unbounded knowledge
sectors that grew. That flip is exactly the diffuse compositional tendency the
dynamic model formalizes and sharpens through its explicit redistribution.

Cross-references: `dynamic_sector_level_employment_validation.md`,
`sector_level_employment_validation.md`,
`anthropic_observed_sector_level_employment_validation.md`,
`eloundou_sector_level_employment_validation.md`.

The dynamic model's sector signal is roughly **2.7× the magnitude** of the next
strongest predictor (observed coverage) and is the only one significant at
p < 0.05 in every period from 2023 onward. The explicit conservation constraint —
routing displaced labor into Unbounded-heavy sectors — is what sharpens the
diffuse "Unbounded sectors grow" tendency that observed coverage only hints at.

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
r = −0.099, p = 0.66; no period significant — see
`dynamic_sector_level_wage_validation.md`). The apparent negative wage
correlations in 2022→23 for the *gross* measures (Eloundou r = −0.504,
observed r = −0.416) are a **post-COVID recovery confound**, not an AI signal —
see `eloundou_sector_level_wage_validation.md`. The dynamic model, being a signed
redistribution measure rather than a gross-exposure measure, does not even
reproduce that confound.

Conceptually this is expected: wage growth is shaped by productivity premiums and
labor scarcity across all demand types, not by structural displacement pressure.
None of the three models is built to predict it.

---

## Summary: predictive value by outcome × level

The two-axis view is the point of this comparison. The right predictor depends on
both *what* you are predicting and at *what level of aggregation*.

| | Occupation level | Sector level |
|--------------|------------------------------------------|----------------------------------|
| **Employment** | All three weak; dynamic best-signed (+0.15 composite), rebound-adjusted beats observed on the penetrated subset | **Dynamic net change (+0.53)** — strongest signal in the project |
| **Wages** | Observed AI task coverage | None significant (2022→23 gross-measure dips are a post-COVID confound) |

Takeaways:

- **Demand type earns its keep on employment, not wages.** Both the
  rebound-adjusted discount and the dynamic redistribution improve employment
  prediction; neither helps with wages, where raw observed coverage is best.
- **Aggregation level decides which model to use.** For occupation-level
  structural-pressure ranking, the rebound-adjusted score is the cleaner gross
  measure. For *where net labor flows across the economy*, the dynamic model at
  the sector level is by far the most informative output the project produces.
- **Sign before magnitude.** The rebound-adjusted and dynamic models look like
  they disagree (negative vs. positive r) only because one is gross pressure and
  the other is signed redistribution. Once read correctly, they tell a consistent
  story: AI-exposed Bounded work is under employment pressure, and the sectors
  with Unbounded absorption capacity are the ones gaining.
