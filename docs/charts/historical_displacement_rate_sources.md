# Historical Displacement Rate Sources (1981–2025)

`data/output/visualizations/historical_displacement_rate_sources.png`, produced
by `historical_displacement.py` (`plot_displacement_rate_history`, called from
`synthesize_composition.write_displacement_rate_table()` so a pipeline run
produces the chart and `historical_displacement_rate.csv` together).

Two stacked panels, sharing a year axis from 1981 to 2025, show all six
estimates of D — the economy-wide annual displacement rate that is the demand
composition model's only empirical input, in place of AI penetration.

## What it shows

**Top panel — total-employment denominator.** The four DWS-derived sources
(`dws_all_tenures`, `dws_long_tenured`, `dws_structural_long_tenured`,
`dws_structural_all_tenures`), each dividing displaced-worker counts by total
employment, 2005–2025. `dws_structural_all_tenures` is drawn bold with markers
and labelled `DEFAULT_SOURCE` in its own legend entry — it is the rate the
composition model actually uses unless told otherwise.

**Bottom panel — long-tenured-employment denominator.** `mlr_long_tenured`
alone, 1981–2000, from the pre-2008 Monthly Labor Review displaced-worker
articles. Its panel title is drawn in the series' own color and states plainly
that this is **a different quantity, not comparable to the panel above**: it
divides displaced long-tenured workers by *long-tenured workers employed*,
where every `dws_*` source divides by *total employment* — matching the same
rule this project applies to CPS-versus-OEWS employment. The two are never drawn as
one continuous line, and splitting them onto separate axes with different axis
labels and a different-colored title makes that visible in the picture itself,
not only in a caption.

**Both panels are step functions, not annual readings.** Every DWS or MLR value
is one survey-window or article-period average repeated across every year it
covers (`is_interpolated=True`). `dws_long_tenured` holds only 10 distinct
values across its 21 years (2005–2025); `mlr_long_tenured` holds 6 across its
20 (1981–2000). Both are drawn with `drawstyle="steps-post"`, so the chart shows
a flat window and an instantaneous jump at each survey boundary, rather than a
smooth line implying resolution the data does not have. The chart computes
these two counts from the data it is passed rather than hardcoding them, so the
figure stays correct as the panel grows.

**The 2001–2004 hole is shown, not bridged.** BLS published neither an archived
DWS release nor an MLR article for the 2002 or 2004 survey. Both panels carry a
hatched gray band over those four years; neither step line has a value there,
and neither is stretched or interpolated across the gap to imply otherwise.

**`productivity` is drawn differently again.** It is the only source that is
*not* interpolated — a 3-year centered rolling mean of smoothed labor
productivity growth, one independent reading per year, 1981–2025 — so it is
drawn as a plain dotted gray reference line rather than a step, and appears on
both panels for context rather than being assigned to either denominator group.

## Reading cautions

**Do not read the two panels on a shared scale.** They happen to share the same
y-axis range in the rendered chart (because `productivity`, which appears on
both, spans roughly the same magnitude as the DWS group), but the quantities
they measure are not the same population and were never intended to be
compared point-for-point across panels — only within a panel, or against the
`productivity` reference line drawn on it.

**A flat segment is a survey window, not a claim about that year specifically.**
Reading "2015 had a 0.58% displacement rate" from `dws_long_tenured` is reading
the 2013–2015 survey window's average, repeated; see
`historical_displacement.dws_displacement_rate`'s docstring for the spreading
rule.

**D cancels out of every cross-sectional correlation the composition model
reports** (see `docs/framework.md` § Demand Composition Model and
`synthesize_composition.py`'s module docstring), so nothing in this chart
should be read as evidence for or against that model's cross-sectional
results. It documents the amplitude and time variation the model actually gets
its sole empirical input from — nothing more.

## Related

- `docs/framework.md` § Demand Composition Model
- `historical_displacement.py` module docstring — why DWS was chosen as the
  primary source and what was rejected
- CLAUDE.md § `seeds/dws_displacement_panel.csv` — the two measurement bases
  (`count_thousands` vs. `rate_percent`) and the archive correction that made
  the ten-survey DWS panel and the MLR pre-2008 extension possible
