# Censored and withheld wages in the OEWS panel

BLS suppresses some wage estimates in OEWS. The two flags mean different things,
and neither is a missing value:

| Flag | Meaning | Recoverable? |
|------|---------|--------------|
| `#` | The wage is at or above the year's published ceiling | No — bounded only |
| `*` | The estimate was not released | Yes, for hourly-only occupations |

## `*` — hourly-only occupations

BLS marks a handful of occupations `HOURLY` and declines to publish an annual
wage for them, because they "generally don't work a standard 2,080 hour work
year". In 2022 these were Actors, Dancers, Musicians and Singers, Disc Jockeys,
and Entertainers and Performers — 4–6 occupations in any given year.

Their annual wage is not missing data; it is a number BLS deliberately does not
invent. `H_MEDIAN` is published for all of them.

`analyze_bls.compute_wage_growth` therefore computes growth from the annual
series where both endpoints exist and from the hourly series otherwise. Growth
is a ratio, so the two are directly comparable and can share a column;
`wage_source_composite` records which series each occupation used.

**Do not reconstruct an annual wage as `H_MEDIAN × 2080`.** That fabricates the
exact quantity BLS withheld, for the occupations where it is least meaningful.

## `#` — censored high wages

`#` means the wage is at or above a ceiling BLS sets each year. It is a censored
value with a known floor, not an unknown one. The ceiling has moved repeatedly,
and BLS documents it only through 2018:

| Vintage | Ceiling |
|---------|---------|
| 2005–2007 | $145,600 (> $70/hr) |
| 2008–2010 | $166,400 (> $80/hr) |
| 2011–2015 | $187,200 (≥ $90/hr) |
| 2016–2018 | $208,000 (≥ $100/hr) |
| 2019–2024 | undocumented; 2022 publishes a wage of $226,880, so it rose again |
| 2025 | none — censoring stops, 0 occupations flagged |

Because the documentation stops in 2018, `analyze_bls.derive_censoring_floor`
derives the floor from the data instead. Censoring is applied on the value, so
every censored wage exceeds every published wage, and the highest published wage
of the year is a valid floor for all of them. That tracks the undocumented
changes on its own; a hardcoded table would have gone stale in 2019 and silently
wrong in 2022. The derived floors are written to `data/output/wage_censoring.csv`.

### Who this removes, and why it matters

The censored set is almost entirely physicians and surgeons — in 2022:
Anesthesiologists, Cardiologists, Dermatologists, Emergency Medicine Physicians,
Obstetricians and Gynecologists, Pathologists, Radiologists, Oral and
Maxillofacial / Orthopedic / Pediatric Surgeons, and Surgeons All Other.

They are ~1% of occupations but the top of the wage distribution, so dropping
them removes the right tail of the very variable being analysed. For this project
specifically, diagnostic specialties — radiology above all — are the flagship
contested cases for AI exposure, and they are absent from every wage correlation.

**No wage-growth window in the current data has two uncensored physician
endpoints.** Censoring stops in 2025, so a clean physician wage series begins
with the 2025→2026 comparison, once the 2026 release lands. Until then their
wage growth is bounded, never observed.

## Bounding, and the sensitivity check

`validate_bls.analyse_wage_censoring_sensitivity` reports the composite wage
correlation under three scenarios:

| Scenario | Assumption |
|----------|------------|
| `excluded` | Status quo — censored occupations dropped |
| `floor` | The anchor wage sits at its lower bound, so growth is at its **maximum** |
| `ceiling` | The anchor wage already equals the latest year's, so growth is **zero** |

Anything outside `[floor, ceiling]` would require the anchor wage to be below the
year's published maximum — contradicting the censoring — or to have fallen in
nominal terms across the window.

Bounding needs one observed endpoint. Where both are censored, nothing can be
said; those occupations are counted and reported rather than quietly bounded.

If `r` is stable across the three scenarios, censoring did not drive the wage
result. Results are written to `data/output/wage_censoring_sensitivity.csv`.
