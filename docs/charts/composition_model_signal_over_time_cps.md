# Composition Model Signal Over Time — CPS Instrument (1983→2026)

`data/output/visualizations/composition_model_signal_over_time_cps.png`, produced
by `composition_era_validation.py`.

Same layout and the same four lines as
[`composition_model_signal_over_time.md`](composition_model_signal_over_time.md),
run against a second, independent instrument: the ten CPS `LNU0203220x`
occupation-group employment series, fetched directly from the BLS historical
timeseries API — not the Table A-19 page this project uses elsewhere (see
`docs/cps_data_expansion.md`) — aggregated to ten occupation groups instead of
BLS OEWS aggregated to 22 SOC major sectors. Each
point is a group-level Pearson r between a model score and year-over-year CPS
employment growth, one point per period. The panel covers
43 year-over-year periods from 1983→2026; 41 are usable after the two COVID
periods (2019→20, 2020→21) are excluded, matching the treatment of every other
era test in this project. Ringed markers are individually significant at
p < 0.05; red bands mark COVID; the dashed blue line and shaded region mark the
AI era from 2022→23.

| Line | Score | Correct sign |
|---|---|---|
| Purple diamonds | `composition_net_change` — demand composition only, no technology data | + |
| Orange squares | `net_employment_change` — dynamic model on AI penetration | + |
| Blue circles | `occupation_exposure` — rebound-adjusted | − |
| Green triangles | `observed_exposure` — Anthropic observed task coverage | − |

`composition_net_change` is the line this chart exists to test — it is the only
score with no AI data in it at all, so a CPS-era result for it is a genuine
second measurement of the sector-level finding, not a repeat of it on the same
instrument.

## Why n=10, not n=22, and why that is the price of admission

This CPS occupation-group series only ever published ten groups, for the whole
1983→2026 span; OEWS's 22 SOC major groups do not exist before 1999 and cannot
be reconstructed from CPS's ten. At n=10, a correlation needs to reach
**|r| ≈ 0.63 for p < 0.05** — far more than the n=22 sector test's **|r| ≈ 0.42**.
Magnitudes and significance counts from this chart are **not comparable** to
the sector-level or occupation-level charts for this reason alone; a smaller
r here can be a stronger true effect than a larger r at sector level, and vice
versa. This is the direct cost of reaching back to 1983: the only way to get a
consistent occupational breakdown that far back is to accept a coarser one.

## CPS and OEWS are separate instruments, never spliced

Every chart and CSV built on CPS draws its own series; nothing here is stitched
onto the OEWS-based charts to make one continuous 1983→2025 line, because they
are two different surveys with two different scopes (see below) and, as it
happens, only moderate agreement where they overlap. `cps_oews_agreement.csv`
(`compare_with_oews`) pairs CPS group-level growth against the group's summed
OEWS employment-level growth for every period both instruments cover: **260
paired observations across 26 periods, Pearson r = 0.547, mean |difference| =
0.0215**. The two instruments move together directionally (r² ≈ 0.30 means over
two-thirds of period-to-period variance is unexplained), which is enough to say
the pre-1999 CPS-only stretch is **not contradicted** by the one check
available — it does **not** license treating it as validated to OEWS-level
precision. See `docs/charts/cps_model_vs_actual.md` for the corresponding
2025→2026 comparison at sector level.

## The two comparability breaks

The reconstructed 1983–1999 segment of the CPS series meets published data at
January 2000, and that reconstruction itself bridges a classification change at
January 2003. `measure_comparability_breaks` puts a number on both, against the
ordinary year-over-year spread of |growth| across every other period (median
0.0167, 95th percentile 0.0617):

| Break | Median \|growth\| | Max \|growth\| | Max occurs in |
|---|---:|---:|---|
| 1999→2000 | 0.0208 | 0.0735 | Farming, fishing, and forestry |
| 2002→2003 | 0.0173 | 0.0904 | Installation, maintenance, and repair |

Neither break's **median** exceeds the ordinary series' 95th percentile — most
groups pass through either break unremarkably. But each break's **max** does
exceed it, by a wide margin, and lands on one specific, volatile group each
time. Read both halves: the breaks are typically invisible in this chart, but
they hit one small group hard apiece, and a reader tracing a single group's
line across either break should discount a sharp move there before reading it
as a real employment shift.

## The terminal period is a partial year, disclosed rather than dropped

The underlying series is not seasonally adjusted, and `fetch_annual_means`
averages whatever months BLS has published for a year — it does not require a
full twelve. In the cache behind this chart, 2025 carries 11 months (October
is unpublished) and 2026 carries 8 (January–August), so `emp_growth_2025_2026`
— one of only four CPS AI-era periods — compares two unequal, seasonally
unbalanced month sets: an NSA series has a within-year seasonal shape, so
averaging 8 months of one year against 11 of another is not the same
comparison as averaging matched months of both. The panel now carries a
`months_observed` column recording how many months back each annual mean, so
this is visible rather than silent.

The period is kept, not dropped: excluding it would discard one of only four
CPS AI-era observations to correct a shift that changes neither sign nor
significance. Recomputed on matched months (January–August of both 2025 and
2026), `emp_growth_2025_2026`'s Pearson r moves from **+0.259 to +0.330** for
`composition_net_change` and from **+0.204 to +0.346** for
`occupation_exposure` — both shifts point the same direction (stronger, not
weaker) and neither crosses zero or a significance threshold at n=10. Treat
the headline numbers below as a slight understatement of this period's fit,
not a distortion of its sign.

## The anachronism rule, and what the era result means under it

Demand-type labels come from 2025 O\*NET task statements, applied backwards to
occupations as they existed as early as 1983. The project's reading rule is
asymmetric: a positive result is strong *because* the anachronism works against
it, while a null result is uninformative rather than disconfirming, since a
null is exactly what an anachronistic label would also produce. The CPS era
result, below, is a null — report it as uninformative, not as evidence against
the taxonomy.

**Era comparison** (`composition_model_era_comparison_cps.csv`,
`composition_net_change`): pre-2022 mean r = +0.425 (n=37 periods), AI-era mean
r = +0.256 (n=4 periods), difference −0.169, Welch p = 0.445 — not
distinguishable from zero.

**Cycle decomposition** (`composition_cycle_decomposition_cps.csv`,
`composition_net_change`, n=41 periods, R² = 0.023): intercept +0.4603
(p < 0.0001), `unemployment_change` +0.0298 (p = 0.692), `ai_era` −0.2026
(p = 0.370). The R² and the intercept are answering two different questions,
not contradicting each other: the intercept asks whether mean period-level fit
strength is above zero across the whole 1983–2026 span (it robustly is), while
R² asks whether unemployment change and an AI-era indicator explain the
period-to-period *variation* in that fit strength (they do not, at this level
of aggregation and power).

One divergence from the sector-level result is worth stating rather than
burying: the business-cycle term is significant at sector level (+0.137,
p = 0.002, n=24 periods) but vanishes at CPS level (+0.030, p = 0.692, n=41).
Candidate explanations include the ten-group aggregation washing out cyclical
sorting that survives at 22 sectors, genuinely different pre-1999 cyclical
behaviour, and differences between the two instruments themselves. None of
these is established by the data on hand — do not pick one.

Recall the n=10/n=22 power gap above before reading anything into these
magnitudes against the sector-level table in `docs/framework.md`.

### Composition-stability sensitivity

`sector_composition_stability.csv` bounds where the anachronism is worst — the
share of a sector's 2022 employment sitting in occupations OEWS also published
in 1999. The three least stable are SOC 15 Computer and Mathematical (0.0326,
independently reproducing the ~3% figure `CLAUDE.md` already documents from the
SOC 2018 computer-code renumbering), SOC 31 Healthcare Support (0.2442), and
SOC 29 Healthcare Practitioners and Technical (0.3656); the most stable are
SOC 37 (0.9927) and SOC 43 (0.9803).

Because SOC 15 and SOC 29 both map to the same CPS group
("professional and related occupations"), excluding all three least-stable SOC
majors drops exactly **two** CPS groups, leaving eight:

| | pre-2022 mean r | AI-era mean r | difference | Welch p |
|---|---:|---:|---:|---:|
| Full sample (10 groups) | +0.425 | +0.256 | −0.169 | 0.445 |
| Excluding least-stable (8 groups) | +0.386 | +0.277 | −0.109 | 0.674 |

| Term | Full sample | Excluding least-stable |
|---|---:|---:|
| intercept | +0.460 (p < 0.0001) | +0.402 (p < 0.0001) |
| `unemployment_change` | +0.030 | −0.021 |
| `ai_era` | −0.203 | −0.115 |

**No sign or significance flip on any headline number.** Two caveats bound how
much that is worth: (a) at n=8, the significance threshold rises to
|r| ≈ 0.71 — this run can only show *absence of a flip*, never robustness; and
(b) the sensitivity check was scoped to `composition_net_change` only, not the
other three scores plotted on this chart.

## CPS counts people OEWS does not

This CPS occupation-group series comes from a household survey that counts the
self-employed and agricultural workers; OEWS is an establishment survey of wage
and salary jobs
and counts neither. Total CPS employment runs from roughly 101 million in 1983
to roughly 163 million in 2025 — legitimately above OEWS's 127–130 million for
the same era, because the two are counting different populations, not because
one series is wrong. This is one more reason the two are drawn as separate
series and never spliced.

## Related

- `docs/framework.md` § Demand Composition Model — the model, computation, and
  the sector-level (OEWS) result this chart extends
- `docs/charts/composition_model_signal_over_time.md` — the sector-level
  (OEWS, n=22, 1999→2025) version of this chart
- `docs/charts/cps_model_vs_actual.md` — the AI-era CPS validation (2025→2026)
  for the rebound-adjusted and dynamic models
