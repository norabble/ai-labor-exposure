---
name: update-cps-monthly
description: Use after a BLS Employment Situation release (first Friday of the month, sometimes the second) to pull the new CPS month into the A-19 panel and the ten-group occupation panel, re-run the CPS-dependent stages, promote the seeds, and update every dated figure — or when asked whether new monthly CPS data is out.
---

# Monthly CPS update

The CPS forecast and validation charts move forward one month per Employment
Situation release. This is the whole routine; skipping a step leaves seeds, charts
and prose describing different months.

**Sandbox.** Every command that reaches api.bls.gov or www.bls.gov
(`download_cps_history.py`, `node download_cps.js`, the pipeline run) must run
outside the Bash sandbox; headless Chrome crashes inside it. In a sandboxed session
`uv run` can also fail because uv cannot write its cache — `.venv/bin/python` is
equivalent, so use it wherever `uv run` is shown below.

## 1. Is the month out?

The release lands at 8:30 ET on the first Friday (second when the first falls too
early in the month). Check the API directly — it is the source:

    uv run python -c "from download_cps_history import fetch_history_payload, parse_api_payload; print(parse_api_payload(fetch_history_payload())['month'].max())"

Compare with `tail -1 seeds/cps_a19_panel.csv`. Same month → stop; nothing to do.

`parse_api_payload` raises if any month lacks one of the 22 groups. A partially
published month therefore shows up as an error: read it as "not out yet or
incomplete", not as a bug to bypass.

## 2. Fetch

    uv run download_cps_history.py
    node download_cps.js

A `ValueError` saying the A-19 page disagrees with the BLS API is a real finding:
a series ID moved or one product was revised. Stop and report it; never bypass it.

## 3. Re-run

    uv run main.py validate composition forecast

`composition` re-fetches the ten-group occupation series. Cache files covering the
current year expire after 24 hours automatically
(`historical_displacement.CURRENT_YEAR_CACHE_MAX_AGE_SECONDS`), so only a re-run
within 24 hours of an earlier same-day run can still serve the previous month.
Check: the latest year's `months_observed` in `data/output/cps_occupation_panel.csv`
must equal the A-19 panel's month count for that year. If it is one short, delete
`data/raw/bls_api/*_<this year>.json` and re-run `composition forecast`.

For this routine the forecast stage prints the 22 × 12 seasonal-factor table and
writes `data/output/cps_seasonal_factors.csv`. A line reading
"⚠ … seasonally adjusted start skipped" means the factors could not be estimated —
report it; do not carry on as if the adjusted start were current.

## 4. Promote the seeds

    cp data/output/cps_a19_panel.csv seeds/

Verify the A-19 seed diff adds exactly 22 rows, one per group, for the one new
month, and that every earlier value is unchanged. `source_reference_month` is
expected to move to the new month on all rows — that is normal, since API rows are
stamped with the pull's latest month.

`seeds/cps_occupation_panel.csv` is three columns (`year, cps_group,
employed_thousands`); `data/output/cps_occupation_panel.csv` adds
`months_observed`. Replace only the current year's ten rows in the seed — copying
the whole file rewrites every row. Verify that diff touches only the current year.

## 5. Charts

    uv run check_charts.py

Copy each stale image from `data/output/visualizations/` to `docs/charts/images/`.
`check_charts.py` cannot flag a chart that has no committed fingerprint, so also
copy the regenerated image for every `docs/charts` page whose figures you update in
step 6 (the text must match the image). Then copy `chart_manifest.json`.

## 6. Dated figures

    grep -rn -E "<previous month name> 20[0-9]{2}|<previous YYYY-MM>" docs README.md

Update each with the `record-measured-result` skill. The figures that move every
month:

- the CPS chart pages: `cps_2026_direction.md`, `cps_model_vs_actual.md`,
  `model_signal_over_time.md` (CPS endpoint table), and
  `composition_model_signal_over_time_cps.md`
- `forecast_cps_start_basis.md` and `forecast_sector_change_2030.md`
- the `docs/framework.md` § Composition Forecast table (raw and seasonally adjusted
  CPS starts), and the CPS era-comparison and cycle-decomposition lines that read the
  ten-group occupation panel — they drift as each month extends that panel's partial
  year
- the `docs/outputs.md` month counts

Each new endpoint month also adds a point to the CPS year-over-year endpoint table.

Then dispatch `claims-auditor` on every changed doc, and `inference-reviewer` if a
sign or significance verdict changed.

## 7. Commit

One commit for seeds, one for charts and docs. `uv run pytest tests/ -q` first.

## What does not move

The CPS slope is fitted on `cps_major_rollup_trends.csv`, built from the IPUMS
detailed panel — a local-only build. Monthly A-19 data never reaches it, so the
decomposition coefficients and the excluded-period label ("2026 averages N months")
stay put until the IPUMS panel is rebuilt. A change there in a monthly update is a
bug.

The seasonal factors themselves change only slightly month to month: a new month
adds at most one ratio per group. A large jump in a factor is worth investigating.
