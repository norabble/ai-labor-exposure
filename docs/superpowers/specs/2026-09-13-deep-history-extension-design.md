# Deep History Extension — Design

**Status: approved design, not yet planned or implemented.**

**Goal:** extend the pipeline's employment validation target from 2005–2025 back to
**1983**, at SOC major group level, so that the era comparison and cycle
decomposition in `composition_era_validation.py` rest on three independent
downturns instead of one.

**Scope:** Phase 1 is sector level (22 SOC major groups) only. Detailed
occupations are Phase 2 and get their own spec.

---

## Why 1983, and why not 1960 or 1989

The stopping point is set by data structure, not by preference. Occupational data
has hard boundaries, and effort is a step function at those boundaries rather
than linear in years.

| Boundary | What changes |
|---|---|
| **1999** | First OEWS year coded on SOC 2000 with 22 major-group summary rows. Below this, OEWS is a different taxonomy. |
| **1997** | OEWS begins at all. Pre-1997 OES is industry-based, one industry every three years, no wage data — unusable for this project. |
| **1983** | CPS adopts 1980-census occupation codes. Dorn's `occ1990dd` balanced panel starts at 1980. IPUMS states `OCC1990` is "preferable to OCC1950 for the samples from 1980 onward." |
| **1976 / 1968** | IPUMS CPS basic monthly / ASEC begin. Both sit below the 1970→1980 coding revision, the largest occupational reclassification of the postwar era. |
| **pre-1962** | Decennial census only — four observations at ten-year spacing. |

**1989 was considered and rejected.** It has no data-structural meaning; it sits
in the middle of the 1983–1991 coding block. The cost of the CPS microdata route
is paid in full at 1989 and 1983 alike — the extract differs by six years of the
same samples — so 1989 would mean paying the whole price and discarding free
history, including the run-up to the 1990–91 recession.

**1960 was considered and rejected.** In practice it means 1968 (the earliest
usable annual CPS occupational data). It crosses the 1970→1980 revision, and it
applies 2025 O\*NET task labels to 1968 occupations. The marginal periods are
purchased with construct validity the project cannot spare.

### What 1983 buys

| | Periods (COVID excluded) | Non-COVID downturns |
|---|---:|---:|
| Today — OEWS 2005–2025 | 18 | 1 |
| + OEWS back to 1999 | 24 | 2 |
| + CPS 1983–2026 | ~41 | 3 |

The right-hand column is the point. `composition_cycle_decomposition.csv`
regresses per-period Fisher-z fit strength on the change in unemployment across
18 periods containing **one** downturn (2008–09). That is why "general mechanism"
and "cyclical sorting" cannot currently be separated cleanly. Three independent
downturns — 1990–91, 2001, 2008–09 — is what makes that regression identify
something.

---

## Verification record

All findings below were checked directly on 2026-09-12, not inferred from
documentation, following the convention in `docs/cps_data_expansion.md`.

| Check | Result |
|---|---|
| `www.bls.gov/oes/tables.htm` via headless Chrome | 200. National zips listed for 1997–2004: `oes97nat.zip`…`oes02nat.zip`, then `oesm03`/`oesn03`, `oesm04`/`oesn04`. |
| Same URLs via plain `curl` | 403 — consistent with the Puppeteer requirement in `CLAUDE.md`. |
| `national_1999_dl.xls` structure | **SOC 2000 codes, 22 `group == "major"` rows, 709 detailed occupations.** Columns `occ_code / occ_title / group / tot_emp / a_median` — structurally identical to 2005. |
| `national_2000_dl.xls`, `national_2001_dl.xls`, `national_2002_dl.xls` | Same; 22 majors (2002 additionally flags `00-0000` as major). Header row varies: 37–39 for 1997–2000, 0 for 2001+. Column spellings vary: `occ_titl` vs `occ_title`, `h_wpct10` vs `h_pct10`. |
| `national_1997_dl.xls`, `national_1998_dl.xls` | **OES 5-digit coding**, `div`/`maj` headers, 43 "majors" — a different taxonomy. No clean published OES→SOC crosswalk located. |
| `www.bls.gov/cps/constio198399.htm` | 200. BLS's own reconstruction of CPS employment 1983–99 onto the 2002 Census / SOC 2000 classification, via published series IDs on `api.bls.gov`. **8 major occupation groups only.** |
| IPUMS CPS `OCC1990` availability | Basic monthly from 1976; ASEC from 1968. Samples from 1968 on "bridge no more than one" major coding shift. |
| `data/raw/cps_research/nem-occcode-cps-crosswalk.xlsx` | 841 rows, current vintage only — 2018-basis CPS codes → SOC 2018. **Cannot bridge the 2011–2019 or 2003–2010 blocks.** |
| `ddorn.net/data.htm` | `occ1990dd` crosswalks from 1950/1960/1970/1980/1990/2000 census and 2005 ACS codes. No crosswalk *to* SOC. |

### The `_period_sort_key` century bug

`analyze_bls.py` keys everything on two-digit year strings. Executed
2026-09-12:

```
year "83":  classified as (current)   ← should be hist_
year "00":  classified as hist_       ← correct by coincidence
sorted periods: ['05_06', '22_23', '83_84', '99_00', 'composite']
_period_sort_key("99_00") == _period_sort_key("composite"):  True
```

Three silent failures:

1. `curr_year <= COMPOSITE_ANCHOR_YEAR` in `attach_growth_columns` is a **string**
   comparison. `"83" <= "22"` is False, so every 1983–1999 period would be emitted
   without the `hist_` prefix and land in the 2×2 AI-era grid charts.
2. `available_years = sorted(year_dataframes.keys())` string-sorts, placing
   `"00".."25"` before `"83".."99"`. The series order inverts.
3. `_period_sort_key("99_00")` returns `(99, 0)` — the sentinel reserved for
   `composite` and `pre_ai`.

This blocks the OEWS-to-1999 extension as well as the CPS work. It is a
prerequisite, not a cleanup.

---

## Decisions

### D1 — Build the panel from IPUMS CPS microdata; build the BLS published series too

Approach chosen over two alternatives:

- *Published BLS series only* (`constio198399` + the `ln` occupation series) is
  roughly two days' work but gives **8 occupation groups** before 2000. At n=8,
  significance needs r ≈ 0.71; the composition model's observed sector r values
  are 0.3–0.6. The likely outcome is an uninterpretable null.
- *Per-block crosswalks* (map each CPS coding vintage directly to SOC) has a
  higher fidelity ceiling, but no published 1980-census→SOC crosswalk exists, so
  the hardest crosswalk would be hand-built — and it covers exactly the stretch
  being purchased.

The published series are built regardless, as the **validation target** for the
microdata tabulation. Building the microdata panel without them means trusting
our own crosswalk with nothing to test it against.

### D2 — One method across the whole span

From 2003 onward, mapping year-specific Census codes straight to SOC via
published crosswalks would be more faithful than routing through `OCC1990`. We
deliberately do not do this. A method seam at 2002/2003 falls inside the pre-AI
stretch, and the entire purpose of the work is comparing fit strength *across*
period boundaries. **`OCC1990` is the spine for all 43 years.**

Per-vintage Census crosswalks have two legitimate roles and one forbidden one.
They *calibrate* the spine — the allocation matrix below is estimated in a window
where a per-vintage crosswalk supplies the SOC side — and they *validate* it
wherever both routes can be computed. They are never used to tabulate part of the
series directly, which is what would introduce the seam.

### D3 — Never splice CPS onto OEWS

CPS and OEWS run as two full-length parallel series. CPS includes the
self-employed and agriculture; OEWS does not. Levels are not comparable and
growth rates only partly so. The 1999–2025 overlap is reported as an
agreement check — disagreement there is a finding about instrument divergence,
not a defect to reconcile.

This follows existing precedent: `model_signal_over_time.png` already draws CPS
"unconnected on an endpoint-month axis so it is not read as a continuation of the
OEWS line."

### D4 — Extend OEWS to 1999

Six additional files, verified structurally identical to 2005. Widens the
CPS↔OEWS overlap from 20 years to 26 and puts a second downturn (2001) inside
the window where both instruments measure it. Stops at 1999: 1997–1998 need an
OES→SOC crosswalk that BLS does not publish cleanly, for two years.

### D5 — Migrate to four-digit years

`TOT_EMP_1999`, `emp_growth_1999_2000`, `hist_emp_growth_1983_1984`. The
alternative — a century-pivot helper preserving two-digit keys — keeps published
column names but carries a century-ambiguous key into a 43-year series, in a
project whose headline result is an era comparison.

This renames columns in `bls_trends.csv` and `bls_sector_trends.csv`. Nothing
outside the repository consumes those files, so the rename costs only the
in-repo references: `CLAUDE.md`'s Outputs Reference rows, the chart modules, and
the docs that name specific columns, all updated in the same commit. Four-digit
years are the cleaner maintenance position independently of the century bug.

### D6 — Extend `D` and the DWS panel to 1984

`productivity` extends free (`PRS85006092` starts 1947). The DWS sources need the
supplements, which become just another IPUMS extract once `download_ipums_cps.py`
exists, on the same CPS occupation vintages the `OCC1990` spine already handles.

This is ranked **above** the employment-growth extension in scientific value.
`composition_displacement_validation.py` is by its own docstring "the only
validation in the project that compares a modeled quantity against a direct
measurement of that same quantity," and it currently runs at n=10 groups from a
single survey. Twenty biennial surveys turn that cross-section into a panel.

---

## Architecture

| Artifact | Role |
|---|---|
| `download_ipums_cps.py` | Submits and downloads IPUMS CPS extracts via the Extract API (`ipumspy`). Local/manual only — never runs in CI. Serves both the occupation panel and the DWS supplements. |
| `cps_soc_allocation.py` | Builds and applies the `OCC1990` → SOC-major-group allocation matrix. |
| `cps_occupation_panel.py` | Tabulates microdata into annual employment by SOC major group; merges the latest build into the committed seed. |
| `seeds/cps_occupation_panel.csv` | The committed panel: `year, soc_major, employed_thousands, unweighted_count`. ~968 rows. |
| `seeds/cps_soc_crosswalks/` | Census occupation-code crosswalks per vintage — 2000-basis → SOC 2000 (calibration window), 2010-basis → SOC 2010 and 2018-basis → SOC 2018 (validation windows). Committed static reference data, following the `seeds/soc_crosswalks/` precedent. The 2018-basis one already exists on disk as `nem-occcode-cps-crosswalk.xlsx`. |
| `data/output/cps_sector_trends.csv` | **Same column layout as `bls_sector_trends.csv`**, keyed by `soc_major`. |

`cps_sector_trends.csv` matching the existing layout is load-bearing:
`sector_growth_series` gains an instrument argument rather than a second code
path, and `validate_bls.py`, `synthesize_dynamic.py` and
`composition_era_validation.py` loop over instruments. Model scores are untouched;
only the growth target varies.

### Sample and universe

Basic monthly CPS, pooled to annual averages — matching how BLS constructs the
published annual averages that serve as validation target, and preserving monthly
resolution for later work. Employed, age 16+, civilian. Weight `WTFINL`.

ASEC is the lighter fallback if extract volume proves impractical; the tradeoff
is smaller samples and a March reference rather than an annual average.

### The allocation matrix

`OCC1990` carries ~380 harmonized codes; SOC major groups number 22. The mapping
is many-to-many, so it is a matrix of employment-weighted shares
P(SOC major | `OCC1990`), not a lookup.

Estimated on **2003–2010** — the window closest in time to the 1983–2002 stretch
it is applied to, on the SOC 2000 vintage that BLS's own reconstruction also
targets. Re-estimated on 2011–2019 and 2020–2026, with the spread in the
resulting sector series reported as the error bar on the deep history.

This inherits the limitation BLS states of its own reconstruction — conversion
factors reflect one period's employment distribution applied to another — and the
documentation says so in those terms.

### Validation gates

The panel does not ship unless all four pass:

1. **2000–2026 against the BLS `ln` occupation series at all 22 groups.** Same
   survey, same universe, BLS's own tabulation. Must agree tightly; this tests
   whether the tabulation is correct at all.
2. **1983–1999 against `constio198399`** at its 8 groups, after aggregating our 22
   up. The only external check available for the deep stretch.
3. **Economy-wide employment against published CPS annual averages**, every year.
4. **Sector growth against OEWS across the 1999–2025 overlap** — reported, never
   reconciled.

---

## What moves, and what does not

| Test | Now | After |
|---|---|---|
| Era comparison (pre-AI vs AI, Fisher-z) | 15 pre-AI vs 3 AI periods | ~38 vs 3 |
| Cycle decomposition | 18 periods, one downturn | ~41 periods, three downturns |
| Unemployment input | `fetch_annual_means(..., 2005, 2026)` | widened to 1948 (`LNS14000000`) |
| DWS displacement validation | n=10, one survey | 10 groups × ~20 surveys |
| **AI-era cross-sectional results** | — | **unchanged, exactly** |

The model scores and the 2022–2025 OEWS data are untouched, so every headline
AI-era number — the +0.509 sector correlation, its +0.34 to +0.59 jackknife
range, the equilibration sweep — is byte-identical afterwards. Only the
historical tests move.

**The AI side stays at three periods.** Nothing here changes that; it is bounded
by the calendar. What changes is the baseline those three periods are compared
against, and the cycle term. The under-power caveat in
`composition_era_validation.py`'s docstring remains true and remains in place.

### Definitional changes to existing outputs

- `hist_emp_growth_pre_ai` currently means 2005→2022; with OEWS at 1999 it becomes
  1999→2022. Renamed to carry its span explicitly rather than silently changing
  meaning.
- `harmonize_soc.py` gains 1999–2004 — the same SOC 2000 vintage as 2005–2009, so
  units extend naturally, but occupation-level survivorship against the 2022
  anchor falls further. Sector-level growth is unaffected; it never comes from
  survivor rows.

### Charts

`model_signal_over_time.png` and `composition_model_signal_over_time.png` stretch
from ~10 plotted periods to ~41. Per D3, OEWS and CPS render as **separate lines
in the same axes** — never one joined line — with the 1999–2025 overlap shaded, so
a reader can see directly whether the two instruments agree.

---

## The anachronism, and the asymmetry it creates

The demand-type labels come from 2025 O\*NET task statements. Applied to 1983 they
are 42 years stale. No crosswalk fixes this; it is a construct-validity limit, not
a data-quality one.

**The interpretation rule is asymmetric, and is recorded here before any result is
seen:**

- **A positive result is strong.** If 2025-measured composition predicts 1980s
  sector dynamics, composition is both persistent and predictive, and the
  anachronism worked *against* the finding.
- **A null result is uninformative.** It is equally consistent with "no general
  mechanism" and with "composition changed too much to carry backwards." It
  cannot distinguish them.

Stating this in advance is what prevents a null from being rationalised after the
fact and a positive from being oversold.

**Cheap mitigation.** For each SOC major group, compute the share of 2022
employment sitting in detailed occupations that have a 1999 OEWS antecedent — a
composition-stability proxy, available from data Phase 1 produces anyway. The
deep-history result is reported with and without the least-stable sectors. This
does not measure task-content drift; it bounds where the labels are most suspect.

**The actual fix is out of scope and named:** reclassifying 1991 DOT task
statements with the same Bounded/Unbounded/Adversarial classifier would give
era-appropriate labels for the computerization era. Machine-readable DOT exists
(DOL OALJ LIBDOT; ICPSR 6100). That is a separate project.

## Analysis choices are pinned before the panel is built

Going from 18 periods to 41 multiplies the forking paths: COVID exclusion, which
downturns count, Fisher-z averaging, instrument precedence, overlap weighting. The
era comparison is the project's headline claim, which is the wrong place to choose
analysis parameters after seeing data.

The implementation plan fixes, before `seeds/cps_occupation_panel.csv` exists:

- Period exclusions (COVID periods stay excluded, on the existing rationale; the
  1990–91, 2001 and 2008–09 downturns are **observations, not exclusions** — they
  are the point).
- Which instrument leads in each reported figure, and how the overlap is handled.
- The cycle-decomposition specification, unchanged in form from the current one.
- What each plausible outcome would mean, written down in advance.

---

## Scope boundary

| In Phase 1 | Named and deferred |
|---|---|
| CPS sector panel 1983–2026, 22 SOC major groups | Detailed occupations (Phase 2, own spec) |
| OEWS extension to 1999 | Wages before 1999 (ORG extract, different earnings concept) |
| Four-digit year migration | Monthly CPS resolution (`docs/cps_data_expansion.md`) |
| `D` and the DWS panel back to 1984 | DOT-1991 era-appropriate labels |
| Composition-stability proxy | Causal claims of any kind |

Wages are deferred on purpose: pre-1999 wage growth needs a different extract and
a different earnings concept than OEWS's median annual wage, and the project's
wage-side results are null nearly everywhere already. Employment is where the
signal is.

---

## Risks

| Risk | Handling |
|---|---|
| IPUMS extract volume for 44 years of basic monthly proves impractical | ASEC fallback (44 samples rather than ~520), documented as a fidelity cost |
| Allocation matrix estimated on 2003–2010 misrepresents 1983 composition | Three-window sensitivity reported as the error bar; BLS states the same limitation of its own factors |
| CPS 1994 redesign introduces a level break inside the 1992–2002 block | Verify magnitude against published annual averages; disclose |
| January population-control revisions produce annual discontinuities | Already a known CPS property; annual averages damp it, and it is disclosed |
| DWS recall window changes 5yr (1984–92) → 3yr (1994+) | `dws_displacement_rate` hardcodes `/3`; must be made recall-aware |
| "Position or shift abolished" not coded consistently back to 1984 | Verify before relying on the structural-displacement source |
| Four-digit migration silently changes a number rather than just a name | Regression check that all AI-era outputs are byte-identical apart from renames — a correctness check on the migration, not a compatibility guarantee |
| IPUMS terms prohibit redistributing microdata | Only aggregate counts are committed; the seed holds 22 groups × years, never records |

---

## Related

- `docs/framework.md` § Demand Composition Model — the model this extension tests
- `docs/charts/composition_model_signal_over_time.md` — the chart that grows from
  10 periods to ~41
- `docs/cps_data_expansion.md` — the monthly-CPS proposal, deliberately separate
- `docs/superpowers/plans/2026-09-11-demand-composition-model.md` — the work this
  builds on
