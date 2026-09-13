# Composition Model Signal Over Time — Occupation Level (1999→2025)

`data/output/visualizations/composition_model_signal_over_time_occupation.png`,
produced by `composition_era_validation.py`.

The occupation-level twin of
[`composition_model_signal_over_time.md`](composition_model_signal_over_time.md).
Identical layout, identical four score lines, identical COVID bands and 2022
boundary — the only difference is the unit of observation. Each point is a
Pearson r across **harmonized SOC units** rather than across 22 major groups, so
n rises from 22 into the hundreds and the same occupation definitions carry every
period instead of moving with SOC survivorship.

Unit scores are the employment-weighted mean over a unit's 2022 OEWS members
(`build_unit_scores` in `validate_bls.py`); unit growth comes from
`bls_harmonized_trends.csv`. Both are the same inputs
`model_signal_over_time_occupation.png` already uses.

## What it shows

**The general, non-cyclical baseline survives at occupation level.** The
composition-only intercept is +0.131 (p < 0.0001) with a cyclical term of +0.066
(p < 0.0001), from a predictor carrying no technology data at all. The sector-level
result is not an artifact of aggregating to 22 groups.

**The AI-specific increment does not.** This is the important disagreement between
the two levels, and it runs in the direction the project already documents:

| Score | sector `ai_era` | occupation `ai_era` |
|---|---:|---:|
| `composition_net_change` | +0.112 (p = 0.349) | −0.038 (p = 0.330) |
| `net_employment_change` | **+0.272 (p = 0.0052)** | +0.011 (p = 0.651) |
| `occupation_exposure` | −0.271 (p = 0.0057) | −0.069 (p = 0.0385) |
| `observed_exposure` | −0.304 (p = 0.0027) | −0.088 (p = 0.0044) |

The dynamic redistribution model's AI-era premium — the strongest AI-specific
result in the project at sector level — **is absent at occupation level**
(+0.011, p = 0.651). The two gross exposure measures keep theirs, at the correct
negative sign and reduced magnitude.

That pattern corroborates a limitation `docs/framework.md` already records under
[Scope and limitations](../framework.md#scope-and-limitations): absorption is
routed proportionally to headcount rather than skill adjacency, so the dynamic
model "is better understood as identifying *which sectors absorb displaced labor*
than as predicting *occupation-specific flows*." This chart is the direct
measurement of that sentence. It is evidence about where the model's mechanism
operates, not evidence against the mechanism.

**Magnitudes are uniformly smaller than at sector level.** Expected: sector means
average away idiosyncratic occupation-level noise, which raises r without adding
information. Compare within a level, never across.

## Reading cautions

**The composition score ties heavily.** It is a function of demand-type mix
alone, so occupations with identical Bounded/Unbounded/Adversarial composition
get identical scores — **239 of 770 occupations (31%) share one value**, and there
are only 513 distinct scores across 770 occupations. Pearson r is bounded by that
tie structure in a way it is not at sector level, where employment-weighted
aggregation hides it. Read the composition line's *magnitude* with that in mind;
its significance and sign are unaffected.

**Higher n is not proportionally higher power.** Units within a sector are
correlated, so the effective sample is well below the nominal unit count.

**The demand-type labels are from 2025 O\*NET task statements applied backwards**,
and are more anachronistic the further back a period sits — as everywhere in this
project.

**The COVID periods are plotted but excluded from every statistic**, matching the
sector chart.

## Related

- `docs/charts/composition_model_signal_over_time.md` — the sector-level original
- `docs/charts/model_signal_over_time_occupation.md` — the same unit of
  observation for the AI-era models, without the composition line
- `docs/framework.md` § Demand Composition Model — the model and its full result
  tables
