# Deep History Extension, Phase 2 — Detailed Occupations — Design

**Status: implemented** — see docs/superpowers/plans/2026-09-23-deep-history-phase-2.md.

**Goal:** raise the deep-history validation from ten CPS occupation groups to
**~380 detailed `occ1990dd` occupations, 1983–2026**, and raise the Displaced
Worker Supplement validation from ten groups to **~25 occupation groups per
survey**, both from IPUMS CPS microdata.

**Predecessor:** `docs/superpowers/specs/2026-09-13-deep-history-extension-design.md`
(Phase 1), which deferred detailed occupations to "Phase 2, own spec." Phase 1
shipped through the *published-series* route — ten leaf-group LNU series, no
microdata — rather than the IPUMS route its D1 chose, because no IPUMS
credential existed (`docs/superpowers/plans/2026-09-13-cps-historical-panel.md`,
"Why this is not the plan the spec described"). Phase 2 is the microdata route.

---

## Why this phase exists

Every deep-history test currently runs at n=10:

| Test | Now | Needs r for p < 0.05 |
|---|---|---|
| CPS era comparison / cycle decomposition, 1983–2026 | 10 groups | ≈ 0.63 |
| DWS displacement validation, per survey | 10 groups | ≈ 0.63 |

The composition model's observed correlations sit well below 0.63, so these
tests can mostly return nulls. Phase 2 raises the cross-sectional n of both.

---

## Verification record

Checked directly on 2026-09-22, not inferred from documentation.

| Check | Result |
|---|---|
| `www2.census.gov/programs-surveys/cps/datasets/` | 200, no account. Year directories **1994–2026 only**. Census microdata cannot reach 1983. |
| Census `supp/` directories | January displaced-worker files present (`jan10pub`, `jan24pub` with `cps_diswork_repwgt_jan24.sas`). |
| `api.ipums.org/extracts?collection=cps` | 401 without a key. |
| `data.nber.org/cps-basic2/` | 403. |
| `.env` keys | `GCP_PROJECT_ID`, `GCP_LOCATION`, `BLS_API_KEY`, `BLS_CONTACT_EMAIL`. **No `IPUMS_API_KEY`.** `ipumspy` not installed. |
| `www.ddorn.net/data.htm` | 200. `occ1990dd` crosswalks from occ1950, 1960, 1970, 1980, 1990, 2000, 2005, **2010**. **None from occ2018** — CPS 2020+ has no Dorn bridge. |
| `subfile_occ1990dd_occgroups.do` (Autor & Dorn 2013) | Level 1: 6 groups. Level 2: 16 non-service groups. Level 3: service subgroups. Non-overlapping finest partition: **~25 groups** (16 level-2 + 9 service subgroups, `occ3_protect` excluded as the union of `occ3_guard` and `occ2_firepol`). |
| `data/raw/cps_research/cpsaat11.html` (CPS Table 11, 2025) | 563 leaf occupations summing to 162,868k of 163,493k employed. Median 90k. Under 30k: 23% of occupations, 1.2% of employment. Under 50k: 35%, 2.9%. |
| `composition_era_validation.occupation_correlation` | Unweighted Pearson across units (`composition_era_validation.py:264`); `MINIMUM_UNITS = 20`; `COVID_PERIODS = ("2019_2020", "2020_2021")`; AI era from `2022_2023`. |
| `composition_model_era_comparison_occupation.csv` | Composition score pre-AI mean r = **+0.123** over 21 periods — the magnitude reference for detailed-level expectations. |
| Model occupations | 770 labeled SOC 2018 codes, against 867 published SOC 2018 detailed occupations. |
| Harmonized SOC units | 749 units, 741 with trends. |
| `seeds/dws_displacement_panel.csv`, Table 5 | Long-tenured displaced 2.5M–6.9M per survey; smallest group 4k–34k. Table 8 all-tenures 6.3M–15.4M. |

### Cell-size arithmetic (estimates, not measurements)

At an estimated ~2,400 weight per January-supplement record, long-tenured
displacement is ~1,400 sample records per survey and all-tenures ~3,100. Spread
across ~380 occupations the median cell holds 1–3 records — **DWS cannot run at
detailed resolution.** Across ~25 groups the average cell is ~55 (long-tenured) /
~125 (all-tenures).

A year of basic-monthly records is not 12 independent samples: the 4-8-4
rotation means a year covers a small multiple (~2.5–4×) of the monthly sample in
distinct households. A 20% relative standard error on an annual employment level
corresponds to roughly **25k–65k workers**, depending on year and design effect.
These figures rest on assumed sample sizes and design effects; the panel's own
`distinct_households` and bootstrap variance replace them once built.

---

## Must be verified once `IPUMS_API_KEY` exists

The implementation plan's first task. Several are design-breaking if false.

| Item | If false |
|---|---|
| `OCC1990` populated for every basic-monthly sample 1983–2026, including 2020+ | **Design returns for review** — Dorn has no occ2018 bridge. |
| Displaced-worker supplement variables available from 1984 | 2b floor rises; recorded as a deviation. |
| 2002 and 2004 supplements present | The panel's 2001–04 hole stays open; no design change. |
| Lost-job occupation carries a harmonized `OCC1990` | Map raw lost-job codes through Dorn's table for the survey's coding vintage. |
| Supplement weight variable identified | Blocks 2b until resolved. |
| `COMPWT` available 1998+ | Gates G1/G2 fall back to `WTFINL` with a wider tolerance, recorded as a deviation. |
| Household identifiers link across months for every year 1983–2026 | See § Sampling variance — the bootstrap design must be identical across the span. |
| `CLASSWKR` harmonized across the span | The `wage_salary` universe is defined per vintage and disclosed. |
| Extract size within IPUMS limits for ~520 monthly samples | Fall back to ASEC (44 samples), recorded as a fidelity cost. |

---

## Decisions

### P2-D1 — Both consumers, sequenced, one extract layer

**2a** detailed employment panel first (large cells, reuses the existing
validation code almost unchanged); **2b** detailed displacement second, reusing
2a's extract layer, spine, and bridge. They share one download module and one
occupation spine.

### P2-D2 — IPUMS CPS, 1983 floor

Rejected: Census-only microdata, 1994 floor. It needs no credential, but it loses
the 1990–91 downturn — Phase 1's stated payoff was three independent downturns
(1990–91, 2001, 2008–09). Rejected: Census now with an IPUMS-ready abstraction,
as up-front cost for a backend that may never be built.

**Consequence:** nothing is tabulated until `IPUMS_API_KEY` is registered and
placed in `.env`. Code can be built and tested against synthetic fixtures before
then.

### P2-D3 — `occ1990dd` is the spine

~380 time-consistent codes built for spanning 1980-census through modern
vintages, and the spine Phase 1's D2 already pinned. Rejected: the 741
harmonized SOC units — directly comparable to the OEWS occupation-level test,
but they need a detailed 1983–2002 Census→SOC crosswalk that Phase 1 verified
does not exist published, and 741 CPS cells a year leaves too many below any
usable floor.

**Consequence:** CPS detailed results and OEWS occupation-level results compare
directionally, never unit-for-unit.

### P2-D4 — The label bridge: published chain, with its error measured

Demand-type labels live on SOC 2018 codes; the panel lives on `occ1990dd`. The
bridge follows published crosswalks for structure and measures its own
compounded error where a direct route exists.

Rejected: fitting the mapping empirically from the CPS–OEWS overlap. A fitted
bridge is forced to make the two instruments agree, and would silently absorb
the universe difference (self-employed, agriculture) that Phase 1's D3 treats as
a finding. Using CPS data only to set split weights was also considered and
dropped, as a partial reintroduction of the same problem.

### P2-D5 — DWS runs at the Dorn partition (~25 groups)

Displacement cells will not support ~380 occupations. The resolution was first
chosen as "~40–60 groups" on the premise that Dorn's group file supplied that
many; inspecting the file showed ~25, and the choice was re-made on that basis.

The Dorn partition is published and citable, so it adds no hand-cut analysis
choice; cells stay workable; and n=25 lowers the significance bar from r ≈ 0.63
to r ≈ 0.40. The 1990 Census occupational subheadings (~40–50, count unverified)
are a sensitivity only, and only if the plan's first task confirms they form a
clean partition.

### P2-D6 — A 22-SOC-major rollup to 1983 is in scope

Once the bridge exists, summing detailed codes to 22 SOC major groups is nearly
free. This is exactly the successor Phase 1's plan named ("raising granularity
from ten groups to 22"), and it puts the n=22 sector test back to 1983 with all
three downturns.

### P2-D7 — `cps_detailed_*` naming

Phase 1 owns `cps_historical_panel.py` and `seeds/cps_occupation_panel.csv`.
Every Phase 2 artifact uses a `cps_detailed_*`, `occ1990dd_*`, `dws_detailed_*`,
or `cps_major_*` name. Each level writes its own files; nothing gains a `level`
column.

---

## Architecture

### Two halves

**Build — local and manual, never CI.**

```
download_ipums_cps.py ─► data/raw/ipums/ (gitignored)
        │
        ├─► cps_detailed_panel.py ─► gates G1, G2, G5 ─► seeds/cps_detailed_occupation_panel.csv
        │                                              ─► seeds/cps_detailed_occ_crosstab.csv
        │                                              ─► seeds/cps_detailed_gates.csv
        └─► dws_detailed_panel.py ─► gate G3        ─► seeds/dws_detailed_panel.csv
                                                    ─► seeds/dws_detailed_gates.csv
```

A seed is written **only if every gate it depends on passes**. The gate record is
committed beside it. `python cps_detailed_panel.py` and `python
dws_detailed_panel.py` rebuild from raw and write `data/output/*_rebuilt.csv`
for comparison against the seed, never auto-promoted — the pattern of
`dws_panel.rebuild_historical_panel_from_raw`.

**Pipeline — CI and `make run-pipeline`.** Reads committed seeds only. The bridge
(including gate G4, computed from the committed crosstab seed), trend tables, and
validation run inside `synthesize_composition.run_stage`, where Phase 1's CPS
work already runs. A missing seed warns and skips; it never fails the pipeline.
If G4 fails, `occ1990dd_bridge_check.csv` is still written with `gate_passed =
False`, a warning names the failing coding block, and no detailed-level or
22-major-rollup result file is written — a result that depends on an unfit
bridge is not published.

`release.yml` needs no promotion step for these seeds: CI can never rebuild them,
so a release run has nothing new to promote. They change only by a local rebuild
and a deliberate commit.

### Modules

| Module | Role |
|---|---|
| `download_ipums_cps.py` | Defines and submits IPUMS extracts via `ipumspy`; caches under `data/raw/ipums/`. Basic monthly (2a) and January displaced-worker supplements (2b). |
| `cps_detailed_panel.py` | Tabulates basic monthly onto `occ1990dd` × universe × year; household bootstrap; seam measurement; gates G1, G2, G5; seed merge; trend and reliability tables. |
| `occ1990dd_soc_bridge.py` | Builds the chain, scores every `occ1990dd` code on all four model scores, computes `labeled_share`, re-derives `dominant_demand`, and runs the bridge check (G4). |
| `dws_detailed_panel.py` | Tabulates supplements onto the Dorn partition per survey; bootstrap variance; gate G3. |
| `composition_era_validation.py` | Gains a detailed-CPS level and a 22-major-rollup level, each writing its own files. |
| `composition_displacement_validation.py` | Gains a Dorn-group level, per survey. |

`ipumspy` goes in an optional `ipums` dependency group and is imported only
inside `download_ipums_cps.py`, so `uv sync --locked` in CI does not need it.

### Seeds

| Seed | Content |
|---|---|
| `seeds/cps_detailed_occupation_panel.csv` | One row per year × `occ1990dd` × universe: `employed_thousands`, `person_months`, `distinct_households`, `months_observed`, `sampling_variance`. ~33k rows. Aggregates only. |
| `seeds/cps_detailed_occ_crosstab.csv` | Employment by `occ1990dd` × raw vintage `OCC` code × coding block (2003–10, 2011–19, 2020–26). Aggregates only. The input the pipeline-side bridge check (G4) needs, since CI never holds microdata. |
| `seeds/cps_detailed_gates.csv` | G1, G2, G5 results from the build that produced the seed. |
| `seeds/dws_detailed_panel.csv` | One row per survey × Dorn group × tenure class: displaced count (thousands), unweighted count, `sampling_variance`. |
| `seeds/dws_detailed_gates.csv` | G3 result. |
| `seeds/occ1990dd_groups.csv` | The Dorn partition as a table, not evaluated from Stata code. |
| `seeds/occ1990dd_crosswalks/` | Dorn's five crosswalks (occ1980, 1990, 2000, 2005, 2010 → `occ1990dd`), with a README carrying the citation. |
| `seeds/cps_soc_crosswalks/` | Census occupation code → SOC for the 2000, 2010, and 2018 vintages, with a README. The 2018 table exists on disk as `data/raw/cps_research/nem-occcode-cps-crosswalk.xlsx`. |

Committed reference data follows the `seeds/soc_crosswalks/` precedent. IPUMS
terms prohibit redistributing microdata; the seeds hold aggregates only.

### Outputs — `data/output/`

Every one gets a CLAUDE.md Outputs Reference row in the commit that creates it.

| File | Content |
|---|---|
| `cps_detailed_occupation_panel.csv` | Seed merged with the latest build. |
| `cps_detailed_trends.csv` | `attach_growth_columns` layout keyed by `occ1990dd`. |
| `cps_detailed_reliability.csv` | Per period: eligible units, employment share covered, mean sampling variance of growth, observed variance of growth, reliability. |
| `cps_detailed_seam_breaks.csv` | Per code, growth across each seam period against its ordinary-period distribution. |
| `cps_detailed_eligibility_sweep.csv` | Era and cycle results at RSE cutoffs 10%, 20%, 30%, and none, plus the fixed-set run. |
| `occ1990dd_scores.csv` | Four model scores per code, `labeled_share`, re-derived `dominant_demand` and `dominant_strength`. |
| `occ1990dd_bridge_check.csv` | Chained vs direct scores per code and coding block, 2003–2026; per-block correlation (G4). |
| `cps_major_rollup_trends.csv` | 22 SOC major groups, 1983–2026, `bls_sector_trends.csv` layout. |
| `composition_model_era_comparison_cps_detailed.csv`, `composition_cycle_decomposition_cps_detailed.csv` | Detailed-level era and cycle tests, raw and noise-corrected. |
| `composition_model_era_comparison_cps_major.csv`, `composition_cycle_decomposition_cps_major.csv` | 22-major rollup era and cycle tests. |
| `dws_detailed_panel.csv` | Seed merged with the latest build. |
| `composition_model_displacement_validation_detailed.csv` | Predicted vs measured displacement share per Dorn group, one row per survey × model. |

Charts under `data/output/visualizations/`, each with a doc in `docs/charts/`:
`composition_model_signal_over_time_cps_detailed.png` and
`composition_model_signal_over_time_cps_major.png`.

---

## Acquisition and tabulation (2a)

### Extract

All basic-monthly samples January 1983 onward. Variables: year, month,
household and person identifiers, month-in-sample, `WTFINL`, `COMPWT`, age,
employment status, `OCC1990`, `OCC` (the raw vintage-specific code — read by gate G1
and tabulated into the crosstab seed the bridge check uses), `CLASSWKR`.

### Universe and weights

Civilian employed, age 16+. Annual employment is the mean of the year's monthly
weighted totals — how BLS constructs published annual averages. `months_observed`
is carried as Phase 1 does, so a partial terminal year is disclosed rather than
hidden.

**`WTFINL` is the tabulation weight in every year**, for one method across the
span. BLS's published estimates use composite weights from 1998, so the gates
that compare against published figures use `COMPWT` from 1998 on.

Two universes, tabulated side by side:

- `all_employed` — every headline test.
- `wage_salary` — excludes both self-employed classes and unpaid family workers.
  Used **only** for the OEWS overlap comparison, where it aligns the universes.

### Sampling variance

A household-cluster bootstrap: resample whole households within each year,
recompute every cell's annual total, repeat with a fixed seed. One method for
1983–2026 — BLS generalized variance parameters change vintage across the span,
and IPUMS replicate weights do not reach the early years.

Growth variance treats adjacent years as independent. Half the sample carries
over between years and positively correlates the endpoints, so this **overstates**
growth noise — conservative, and documented as such.

**The bootstrap design must be identical in every year.** If households cannot be
linked across months for part of the span, the cluster unit is changed for the
whole span to one available in every year, decided before any model correlation
is computed. `distinct_households` is NaN, not approximated, where linkage is
unavailable.

### Reliability

Per period, over eligible units:

```
reliability = 1 − mean(sampling variance of growth) / variance(observed growth)
r_corrected = r_raw / sqrt(reliability)
```

Model scores are not CPS-sampled, so their reliability is taken as 1. Where
reliability ≤ 0 the corrected r is undefined and reported as such.

Raw r is biased toward zero; corrected r is biased away from zero because the
bootstrap overstates noise. The two bracket the true value.

### Seams

Coding-vintage and survey-design breaks inside the span:

| Period | Cause |
|---|---|
| 1991→1992 | 1980 → 1990 Census occupation codes |
| 1993→1994 | CPS redesign; dependent occupation coding introduced |
| 2002→2003 | 1990 → 2000 Census codes |
| 2010→2011 | 2000 → 2010 Census codes |
| 2019→2020 | 2010 → 2018 Census codes (already COVID-excluded) |

`measure_vintage_seams` compares each code's growth across each seam with its
ordinary-period distribution, using the method of Phase 1's
`measure_comparability_breaks`. **Measured and disclosed, never patched.** Phase
1's D2 removes a *method* seam; these are *data* seams no method removes.

---

## The bridge

### Chain

Anchored on 2010 Census codes, the newest vintage Dorn covers:

```
occ1990dd ─(Dorn occ2010 table)─► Census 2010 code ─(Census/BLS code list)─► SOC 2010 ─(seeds/soc_crosswalks)─► SOC 2018
```

- **Split weights.** Where one code reaches several SOC codes, OEWS **2022**
  employment sets the split — the anchor harmonized units already use for their
  member weights. OEWS excludes the self-employed, so splits in
  self-employment-heavy occupations are misweighted; the bridge check measures
  the consequence.
- **Scores.** All four — `composition_net_change`, `net_employment_change`,
  `occupation_exposure`, `observed_exposure` — so the four-score comparison runs
  at this level.
- **Unlabeled codes.** A unit's score is the weighted mean over its **labeled**
  SOC constituents. `labeled_share` records the weight they carry.
- **`dominant_demand`.** Re-derived with `attach_dominant_demand` after
  aggregation, never carried — per CLAUDE.md, following the Chief Executives bug.

### Bridge check (G4)

For 2003–2026, each `occ1990dd` code is scored a second way: the people CPS
coded into it are mapped from their raw `OCC` codes straight to SOC through the
table for that year's vintage, weighted by CPS employment, bypassing the chain.
The pipeline computes this from `seeds/cps_detailed_occ_crosstab.csv`, so it
always scores against the current model outputs.
Reported per coding block (2003–10, 2011–19, 2020–26):

- the per-unit gap between chained and direct scores;
- the correlation between the two score vectors across units;
- whether each period's era-test r changes when direct scores replace chained ones.

**This is a lower bound for 1983–2002.** No direct route exists from the 1980 and
1990 Census vintages to SOC, so the error in exactly the stretch Phase 2 buys
cannot be measured. The documentation says so in those terms.

Direct scores are diagnostic only. They never replace chained scores in any
reported result; doing so would reopen the method seam Phase 1's D2 forbids.

---

## Displacement (2b)

- **Groups.** `seeds/occ1990dd_groups.csv`, the Dorn partition.
- **Lost-job occupation.** The displaced worker's occupation is the *lost job's*,
  a different variable from current occupation. Harmonized `OCC1990` if IPUMS
  provides it; otherwise raw codes mapped through Dorn's table for the survey's
  coding vintage.
- **Variance.** The same household bootstrap as 2a.
- **Denominator.** 2a's employment on the same spine allows displacement
  *rates* per group, not only shares.
- **2002 and 2004.** Included if IPUMS carries them, closing the panel's 2001–04
  hole (fielded, but never archived by BLS).

---

## Analysis choices pinned before any seed exists

Committed with this spec. Any change after a seed exists is recorded as a named
deviation with its reason.

### Inherited unchanged

COVID periods `2019_2020` and `2020_2021` excluded. AI era from `2022_2023`.
`MINIMUM_UNITS = 20`. Four scores, existing sign conventions. Fisher-z era means
and Welch test. Cycle decomposition of unchanged form: Fisher-z fit strength on
change in unemployment plus an AI-era indicator. Unweighted Pearson across units.

### 2a — detailed employment

| Choice | Headline | Sensitivity |
|---|---|---|
| **Eligibility** | Per period: a code enters if its employment RSE ≤ **20%** in **both endpoint years** of that period | **Fixed set**: RSE ≤ 20% in every year 1983–2026. **Sweep**: per-period cutoffs 10%, 20%, 30%, none. |
| **Noise** | Raw r | Noise-corrected r |
| **Seam periods** 1991→92, 1993→94, 2002→03, 2010→11 | Excluded | Included |
| **Labeled share** | ≥ 0.8 | — |
| **Universe** | `all_employed` | — (`wage_salary` is for the OEWS overlap only) |
| **Bridge** | Chained scores | — (direct scores diagnostic only) |
| **Growth horizon** | Year-over-year | — |

Headline periods: 43 year-over-year periods 1983→2026, less 2 COVID and 4 seams
= **37**, of which 4 are AI-era (2022→23 through 2025→26).

**Why per-period eligibility leads.** A set fixed across all years drops every
occupation that was small at either end of the span — typists, word processors,
and telephone operators on the way down; computer occupations on the way up.
Those are the occupations that changed most, so a fixed set selects on the
outcome and hides the strongest cases. Per-period eligibility keeps an
occupation until it is genuinely unmeasurable. Its cost is that eras compare
somewhat different occupation mixes; the fixed-set sensitivity bounds that, and
every period reports its eligible count and employment share.

**Seam exclusion cost.** 1991→92 falls inside the early-1990s downturn, which the
headline then represents by 1990→91 alone.

### Known risk deliberately left unaddressed: year-over-year noise

At the detailed grain, year-over-year growth is estimated to be mostly sampling
noise. A median-size occupation (~90k) has a level RSE near 15%, so its
year-over-year growth carries a standard error of roughly 15–20%, against
genuine cross-occupation growth differences of a few percent. Estimated
reliability: **~0.1–0.2**.

Multi-year windows, placed inside coding blocks, would fix this by letting real
change accumulate while endpoint noise stays fixed. They were **considered and
declined**: they would cut the detailed test from 37 periods to roughly 9–12.
The decision is to run year-over-year and see how it turns out.

The raw/corrected bracket is therefore the only noise handling, and at
reliability this low the two may diverge widely. `cps_detailed_reliability.csv`
measures the real figure. If results prompt a move to multi-year windows later,
that move is a named deviation, not a quiet change.

### 2b — detailed displacement

| Choice | Headline | Sensitivity |
|---|---|---|
| Resolution | Dorn partition (~25) | 1990 Census subheadings, only if verified as a clean partition |
| Count | All-tenures | Long-tenured |
| Measure | Displacement share per group | Rate, with 2a's employment as denominator |
| Surveys | One correlation per survey, never pooled | — |

The existing panel rule carries over: the predicted vector is identical in every
survey, so a consistent sign across surveys is not independent evidence and
cannot be pooled by sign test or averaged r.

### 22-major rollup

Employment is allocated from `occ1990dd` to SOC major groups through the bridge's
split weights, over **all** SOC constituents — labels are not involved, so
`labeled_share` does not apply. The same era and cycle specification as the sector level, at n=22, 1983–2026,
`all_employed`. Its overlap with OEWS sector growth, 1999–2025, is reported on
`wage_salary` and never reconciled (Phase 1 D3).

---

## Gates

| Gate | Check | Threshold | Runs in |
|---|---|---|---|
| **G1** Tabulation | Microdata mapped to the ten leaf groups through raw `OCC` (bypassing the bridge) vs Phase 1's published LNU series | 2003–2026: within **1%** per group-year, `COMPWT`. 1983–2002: difference reported only — BLS's reconstruction uses conversion factors. | Build |
| **G2** Total | Economy-wide employment vs published CPS annual averages | Within **1%** from 1998, `COMPWT`. Reported before 1998. | Build |
| **G3** DWS tabulation | Microdata long-tenured displacement by the ten groups vs published Table 5 rows in `seeds/dws_displacement_panel.csv` | Within **3%** per group, allowing for published rounding. | Build |
| **G4** Bridge fitness | Correlation of chained vs direct `composition_net_change` across units | **r ≥ 0.8 in every coding block** (2003–10, 2011–19, 2020–26). Below that, the bridge is unfit, detailed and rollup results are withheld, and the design returns for review. | Pipeline, from the crosstab seed |
| **G5** Partition | Dorn groups cover every `occ1990dd` code exactly once | Structural. | Build and test |
| — | 22-major rollup (`wage_salary`) vs OEWS sectors, 1999–2025 | Reported, never gated. | Pipeline |

---

## Expected outcomes and their reading

Written before any result is seen.

- **Expected magnitude.** OEWS occupation-level composition r averages +0.123
  pre-AI. CPS sampling noise attenuates further; expect per-period raw r of
  roughly **+0.05 to +0.15**, possibly lower given the reliability estimate. An
  expectation, not a threshold.
- **The asymmetric rule, strengthened.** A positive result is strong. A null is
  uninformative — task content drifts more for individual occupations than for
  sector aggregates, and `occ1990dd` forces modern occupations into 1990
  categories.
- **Positive, significant intercept in the detailed cycle decomposition,
  1983–2026:** the general mechanism holds at occupation grain across three
  downturns.
- **Detailed null, 22-major rollup positive, same microdata:** the signal is
  between-sector composition, not within-sector occupational sorting — bounded by
  the reliability figures, but informative, because anachronism alone cannot
  explain a gap between two grains of the same data.
- **An era difference whose sign differs between raw and corrected r:** attributed
  to noise; not reported as an era effect.
- **AI era:** 4 periods. No AI-specific claim is made at this level, whatever
  the result.
- **DWS at n=25:** a per-survey correlation above ≈ 0.40 is individually
  significant. Uniform sign across surveys is noted, never pooled.

The Phase 1 composition-stability proxy is recomputed at the detailed grain, so
the least-stable occupations can be named rather than inferred from sector
shares.

---

## Testing

No test touches the network. Fixtures are small synthetic IPUMS-shaped extracts.

| Area | Test |
|---|---|
| Tabulation | Annual averaging; `all_employed` / `wage_salary` split; `distinct_households` under 4-8-4 rotation |
| Bootstrap | Deterministic under a fixed seed |
| Bridge | Split weights sum to 1; renormalization over labeled codes; `labeled_share`; `dominant_demand` re-derived after aggregation (regression test for the Chief Executives failure mode) |
| Seams | An injected break is flagged |
| Eligibility | A shrinking synthetic occupation stays in per period until it falls below the cutoff, and is dropped by the fixed-set sensitivity — mutation-proof, so inverting the rule fails the test |
| Reliability | Known-variance fixture reproduces the expected reliability; reliability ≤ 0 yields undefined corrected r |
| Gates | A failing build gate blocks the seed write; a failing G4 writes the bridge check with `gate_passed = False` and withholds every detailed-level and rollup result file |
| Partition | G5 against the committed `seeds/occ1990dd_groups.csv` |
| Regression | Every existing output byte-identical afterwards, including Phase 1's ten-group files and every AI-era number |

---

## Documentation

- CLAUDE.md: Outputs Reference rows for every new output; a seeds-convention
  paragraph for the IPUMS seeds (built locally, never in CI, aggregates only,
  gate record committed beside each).
- `docs/framework.md`: detailed-level results, the bridge's lower-bound caveat,
  and the unaddressed year-over-year noise.
- `README.md`: IPUMS registration and the local build step.
- `docs/charts/`: one doc per new chart.

---

## Risks

| Risk | Handling |
|---|---|
| No IPUMS key is ever registered | Phase 2 cannot tabulate. Returning to the Census 1994-floor route is a new decision, not a fallback in this spec. |
| `OCC1990` missing for 2020+ | Design returns for review (first-task verification). |
| Extract volume impractical | ASEC fallback, recorded as a fidelity cost. |
| Year-over-year growth mostly noise | Accepted by decision; measured by `cps_detailed_reliability.csv`; bracketed by raw/corrected r. |
| Bridge error compounds through the chain | Measured by G4 for 2003–2026; unmeasurable, and documented as such, for 1983–2002. |
| Coding-vintage seams | Measured per code; headline excludes seam periods. |
| Per-period eligibility changes the occupation mix across eras | Fixed-set sensitivity; per-period counts and employment share reported. |
| Split weights misallocate self-employment-heavy occupations | Measured by the bridge check; `wage_salary` isolates the universe gap in the overlap. |
| Bootstrap design cannot be uniform across the span | Cluster unit chosen for the whole span before any correlation is computed. |
| DWS cells thin even at ~25 groups | Bootstrap variance and reliability reported per survey. |
| Label anachronism larger at detailed grain | Asymmetric reading rule; detailed composition-stability proxy. |
| IPUMS redistribution terms | Seeds hold aggregates only. |

---

## Scope boundary

| In Phase 2 | Named and deferred |
|---|---|
| `occ1990dd` employment panel, 1983–2026, two universes | Multi-year growth windows — considered and declined (above) |
| Chained label bridge with measured error | Wages before 1999 |
| 22-major rollup to 1983 | Monthly CPS resolution |
| DWS at the Dorn partition, per survey, 1984 onward | DOT-1991 era-appropriate labels. Dorn's `occ1990dd_task_alm` (DOT-derived task measures on this spine) is noted as a cheap future anachronism check. |
| Displacement rates on the same spine | Direct per-vintage tabulation (forbidden by Phase 1 D2) |
| Detailed composition-stability proxy | Causal claims of any kind |

---

## Related

- `docs/superpowers/specs/2026-09-13-deep-history-extension-design.md` — Phase 1 design
- `docs/superpowers/plans/2026-09-13-cps-historical-panel.md` — Phase 1 as built, and why it took the published-series route
- `docs/superpowers/plans/2026-09-14-dws-historical-panel.md` — the DWS panel 2b extends
- `docs/framework.md` § Demand Composition Model
- Autor, D. and Dorn, D. (2013). "The Growth of Low-Skill Service Jobs and the Polarization of the U.S. Labor Market." *American Economic Review* 103(5), 1553–1597 — source of the `occ1990dd` crosswalks and occupation groups
