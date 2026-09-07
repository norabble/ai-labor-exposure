# Using CPS more fully: building real monthly history

**Status: proposal. Nothing here is implemented.**

## Why this exists

The CPS charts exist to cover the gap after OEWS ends (reference month May 2025). Today that comes from BLS CPS Table A-19, a rolling web page that carries exactly two months — the latest reference month and the same month a year earlier — and is replaced in place each month.

The pipeline now accumulates those months into `seeds/cps_a19_panel.csv`, so history survives across runs. But the panel starts from what happened to be on disk: as of this writing it holds six months (2025-04, 2025-06, 2025-08, 2026-04, 2026-06, 2026-08), and grows by at most two per fetch. Three consequences:

- **The since-OEWS anchor is Apr 2025, not May 2025.** It over-covers the OEWS handoff by a month because Apr is simply the oldest month we have.
- **No seasonal adjustment is possible.** A-19 is NSA, and with a handful of scattered months there is no way to estimate a seasonal factor. The since-OEWS window therefore carries seasonal noise — Farming, Fishing, and Forestry reads +12.7% over Apr 2025 → Aug 2026 against −3.2% year-over-year, which is the summer agricultural ramp, not AI.
- **CPS contributes to `model_signal_over_time.png` only as a side panel, not as a series.** The panel supports one year-over-year pair per fetched release (three so far: Apr, Jun, Aug), and all of them measure the same 2025→2026 span from endpoints two months apart. That is enough for an endpoint-sensitivity check beside the OEWS line, but not enough for a time series — and a real monthly panel would not change this, because CPS still cannot be spliced onto OEWS without an overlapping period to calibrate against.

This document evaluates how to get real monthly history.

## What was checked

All findings below were verified against BLS on 2026-08-02, not inferred from documentation.

| Source | Result |
|---|---|
| `www.bls.gov/web/empsit/cpseea19.htm` (A-19) | 200 via headless Chrome; 403 to plain HTTP. Current month only — no archive path found. |
| `www.bls.gov/news.release/archives/empsit_06052026.htm` | 200. Contains Table **A-13**, not A-19. |
| `www.bls.gov/news.release/empsit.t13.htm` (A-13) | 200. Only ~14 occupation rows. |
| `download.bls.gov/pub/time.series/ln/` | 200 via headless Chrome; **403 to curl**. `ln.series` 15 MB, `ln.data.1.AllData` 389 MB. |
| `api.bls.gov/publicAPI/v2/...` | 200 **to plain curl**, no API key, no bot block. |

### Option A — Archived Employment Situation releases: **rejected**

The archives exist and are fetchable, but they do not contain A-19. A-19 is a web-only *expanded* table; the news release carries **Table A-13** ("Employed and unemployed people by occupation, not seasonally adjusted").

A-13 is far coarser than A-19 — roughly 14 rows, and it collapses exactly the categories this project cares about:

```
A-13 has:  Management, business, and financial operations occupations   (one row)
           Professional and related occupations                          (one row)
           Service occupations                                           (one row)

A-19 splits those into: Management | Business and financial | Computer and mathematical |
           Architecture and engineering | Life, physical, and social science |
           Community and social service | Legal | Education, training, and library |
           Arts, design, entertainment, sports, and media |
           Healthcare practitioners and technical | Healthcare support | Protective service |
           Food preparation | Building and grounds | Personal care
```

Only 7 of the 22 SOC major groups survive individually in A-13. Computer and Mathematical, Legal, Education, and Healthcare Practitioners — the AI-exposure-relevant groups — are all lost. Scraping archived releases would buy history at the cost of the granularity that makes the chart meaningful.

### Option B — BLS public API v2: **recommended**

The `ln` (Labor Force Statistics from the CPS) series database carries monthly employment levels at **exactly A-19's granularity**, with decades of history, and the public API serves them without a key or a browser.

Verified: `LNU02032201` returns June 2026 = 70,366 and April 2026 = 71,339 — identical to the A-19 values the pipeline parses today. Cross-checks hold for aggregates too (`LNU02032202` = 30,585 = Management 20,864 + Business/Financial 9,720).

**All 22 SOC major groups have a monthly employment-level series.** Matching `ln.series` titles against `CPS_TO_SOC_MAJOR` resolves 20 of 22 exactly; the remaining two are wording variants needing an alias:

| A-19 wording | BLS series title | Series ID |
|---|---|---|
| Community and social service | Community and Social **Services** Occupations | `LNU02032458` |
| Healthcare **practitioners** and technical | Healthcare **Practitioner** and Technical Occupations | `LNU02032462` |

Coverage: **2000M01 → 2026M06** for the detailed groups, with some aggregate series reaching back to 1983M01. That is 26 years of monthly history versus the four scattered months we have now.

**It also unlocks a measure the project has no access to today.** The same occupation codes carry unemployment series — `LNU03034021` (Unemployment Level) and `LNU04034021` (Unemployment Rate), also 2000M01→2026M06, for all 22 groups. Unemployment rate by occupation is a faster-moving, more forward-looking indicator than employment levels, and OEWS cannot provide it at all. If AI is displacing Bounded occupations, occupational unemployment should move before employment levels do.

Practical notes:

- **No Puppeteer needed.** `api.bls.gov` answered plain curl directly — unlike every other BLS host in this project. Verify `requests` behaves the same before assuming it.
- **Rate limits.** A single unregistered POST with 25 series IDs succeeded. BLS documents tighter per-day limits for unregistered use and raises them substantially with a free API key; check the current published limits rather than trusting the one observation above. Registration is free and removes the question.
- **`api.bls.gov` is not in the sandbox network allowlist** (only `www.bls.gov` is). It needs adding via `/sandbox`.

### Option C — `ln` flat files: viable fallback

`download.bls.gov/pub/time.series/ln/` hosts the whole series database: `ln.series` (15 MB metadata), `ln.data.1.AllData` (389 MB), plus code lookups such as `ln.occupation` (761 occupation codes).

One download, no rate limits, no key. But the host **blocks plain HTTP** — curl gets BLS's "Access Denied / bot activity" page — so it needs the Puppeteer + CDP download-behavior pattern already in `download_bls.js`. Given the API serves the same numbers over a simpler transport, treat this as the fallback if API limits become the binding constraint. `ln.series` is worth fetching once regardless, to generate the series-ID mapping mechanically instead of hardcoding 22 IDs.

## What has to be handled

**The 2020 coding break.** CPS adopted the 2018 Census occupational classification (derived from SOC 2018) with January 2020 data. A-19's own footnote states data for 2020 "are not strictly comparable with earlier years." The series run back to 2000, but any claim spanning that boundary needs the break either modeled or the pre-2020 segment excluded. The safe default is to start at 2020M01 and treat 2000–2019 as a separate, separately-caveated regime.

**January population controls.** CPS introduces updated population controls each January and does not revise prior months, so every January carries a level discontinuity unrelated to the labor market. This already affects the current since-OEWS window; with a full monthly series it becomes tractable — the discontinuity can be measured and adjusted rather than just disclosed.

**Seasonal adjustment.** The `LNU*` series are unadjusted. Seasonally adjusted `LNS*` equivalents exist for headline aggregates but should not be assumed to exist for all 22 occupation groups — check before designing around them. With ~6 years of clean post-2020 monthly data, computing seasonal factors directly is a reasonable alternative. This is what would make non-year-over-year windows honest, including a since-OEWS anchor pinned to exactly May 2025.

**Statistical power — the important caveat.** More months are *not* more independent observations. n stays at 22 major groups no matter how much history is added, and consecutive monthly readings for the same group are heavily autocorrelated. A monthly panel does **not** fix the underpowered n=22 correlations in `cps_model_vs_actual.md`; treating each month as a fresh observation would badly overstate significance. What history actually buys:

1. A CPS line on `model_signal_over_time.png` from a genuinely independent survey — the current chart's three lines all rest on OEWS.
2. Seasonal adjustment, and therefore an anchor at the true OEWS handoff.
3. Unemployment-rate-by-occupation as a leading indicator (Option B).
4. Distinguishing a persistent divergence from a one-window artifact — currently impossible, and the reason the two windows disagreeing on sign cannot be adjudicated.

Any real gain in statistical power has to come from more *occupations*, not more months — which is the detailed-occupation direction, not this one.

## Recommendation

Adopt **Option B**. Concretely:

1. Add `api.bls.gov` to the sandbox allowlist.
2. Fetch `ln.series` once via the `download_bls.js` Puppeteer pattern and generate the 22 employment-level and 22 unemployment-rate series IDs by title match against `CPS_TO_SOC_MAJOR`, with aliases for the two wording variants above. Commit the resulting mapping.
3. Add a `download_cps_history.py` that pulls those series from the API and writes them into the existing panel schema — `month`, `soc_major`, `employed_thousands` — so `cps_panel.py` needs no structural change. Backfill from 2020M01.
4. Once the panel is deep enough, pin the since-OEWS anchor to 2025-05 and compute seasonal factors; keep the year-over-year window as the unadjusted cross-check.
5. Treat unemployment rate by occupation as a separate follow-on, not part of this change.

Steps 1–3 are the substance and should land together; 4 and 5 are independent follow-ups.

## Explicitly out of scope

Detailed-occupation CPS data is a different, larger question. `data/raw/cps_research/` already holds unused May 2026 downloads pointing that way — `cpsaat11.html` (~570 detailed occupations, annual averages), `nem-occcode-cps-crosswalk.xlsx` (CPS → SOC crosswalk), and `monthly_A20_occupation.html`. That route is where additional *statistical power* would come from, since it raises n from 22 into the hundreds. It is not evaluated here.
