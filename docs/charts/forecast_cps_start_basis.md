# Composition Projection: Raw vs Seasonally Adjusted CPS Start

**File:** `forecast_cps_start_basis.png`

![CPS projection from a raw and a seasonally adjusted start](images/forecast_cps_start_basis.png)

## What this chart shows

**It tests whether starting the CPS projection in September, a month with its own seasonal pattern, changes the answer.** Table A-19 is not seasonally adjusted, so the latest month's sector shares carry that month's seasonality into the projection.

Each sector has two bars: its projected change in employment share, in percentage points, from 2026-09 to 2030-12, under the reference scenario (steady unemployment, logistic AI adoption). The blue bar starts from the raw 2026-09 shares. The orange bar starts from the same shares divided by each sector's September seasonal factor and renormalised to sum to one. Sectors are ordered by the raw projection.

**Reading the factor in each label.** The factor is that sector's September seasonal factor (`cps_seasonal_factors.csv`). Above 1 means September runs seasonally high for the sector, so the adjusted start is lower than the raw one. Factors come from a centred 2×12 moving average, use months from 2022 onward, and rest on 3 or 4 years per calendar month.

**The raw start stays primary.** The other six forecast charts, and the CPS panel of `forecast_sector_change_2030.png`, use the raw start. This chart is the only place the adjusted start appears.

## Reading

Measured 2026-10-02 from `forecast_sector_paths.csv` (filter `instrument == "cps"`, `unemployment_scenario == "steady"`, `adoption_fit == "logistic"`, n = 22 sectors). Change = (share at `as_of == "2030-12"` − share at `as_of == "2026-09"`) × 100, per `start_basis`.

- **The two starts give nearly the same projection.** The absolute raw-versus-adjusted gap in projected change has median 0.002 pp and mean 0.004 pp across the 22 sectors.
- **The largest gaps are:**

| Sector | Raw change | Adjusted change | Gap |
|---|---|---|---|
| Office and Administrative Support | +3.414 | +3.432 | +0.018 |
| Healthcare Practitioners and Technical | −0.870 | −0.885 | −0.014 |
| Architecture and Engineering | −0.292 | −0.303 | −0.012 |

- **No sector changes sign** (0 of 22 have raw and adjusted changes of opposite sign).
- **The start shares themselves move more than the projections do.** The largest adjustment to a sector's 2026-09 share is 0.136 pp (Building and Grounds Cleaning and Maintenance, factor 1.042, whose share falls).

The seasonal adjustment therefore does not drive the CPS projection. That says nothing about whether the CPS projection itself is reliable (see `forecast_sector_change_2030.md`).

## Limitations

- Each factor rests on 3 or 4 years per calendar month, so a single unusual year moves it. Farming, Fishing, and Forestry has the widest factor range, 0.882 (April) to 1.182 (July).
- The adjustment changes the start shares only; the score and the fitted slopes are not re-estimated.
