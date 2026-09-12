# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

```bash
make setup          # Install Python + Node deps, set up pre-commit hooks
make download-data  # Download O*NET, Anthropic, and BLS source data
make classify       # LLM-classify all O*NET tasks (expensive, ~19k calls, resumable)
make run-pipeline   # Run the full analysis pipeline (analyze → synthesize → plot → validate)
make test           # Run unit tests
make lint           # Ruff check + format
```

Run specific pipeline stages:
```bash
uv run main.py synthesize plot        # run two stages
uv run main.py validate               # re-run validation only
```

Run a single test:
```bash
uv run pytest tests/test_pipeline.py::TestComputeTaskExposure::test_bounded_has_high_exposure
```

## Architecture

The pipeline has two distinct phases:

**Phase 1 — Classification** (`classify_tasks.py`, run once via `make classify`):
- Reads ~19k O\*NET task statements and sends each to Gemini (Vertex AI) to label it as `Bounded`, `Unbounded`, or `Adversarial`
- Checkpoints after each occupation group to `data/output/classified_all_tasks_checkpoint.csv`; safe to interrupt and resume
- Requires `GCP_PROJECT_ID` (and optionally `GCP_LOCATION`) in `.env`

**Phase 2 — Analysis** (`main.py` orchestrates four stages):
1. `analyze_bls` — extracts national cross-industry employment/wage data from BLS OEWS zip files
2. `synthesize_impacts` — joins classified tasks with Anthropic's task penetration scores, computes per-occupation impact scores
3. `generate_plots` — produces visualizations from the impact report
4. `validate_bls` — correlates model predictions against actual BLS employment/wage trends

## Project Goal

This project produces a **structural exposure score** — a current snapshot of which occupations are most exposed to AI-driven demand change, stratified by demand type. It is not a displacement prediction. Testing against BLS employment data is an ongoing confidence check; null results are expected. See `docs/framework.md` for the full conceptual framework, exposure type taxonomy, and demand type definitions.

## Key Design Decisions

**BLS downloads require Node.js.** BLS blocks plain HTTP requests; `download_bls.js` (OEWS zips) and `download_cps.js` (CPS Table A-19) use Puppeteer (headless Chrome) to bypass this. The Python `requests` approach will not work — A-19 returns 403 to it. The two scripts are deliberately separate: `release.yml` caches the OEWS zips on `hashFiles('download_bls.js')` and skips that script entirely on a cache hit, which would mean the rolling monthly A-19 table was never re-fetched. The 2024/2025 data is only available as all-areas files (`oesm24all.zip`, `oesm25all.zip`); `analyze_bls.py` filters them to national cross-industry rows (`AREA_TYPE==1`, `OWN_CODE==1235`, `NAICS=='000000'`). Historical files 2005–2021 are national-only and require no such filtering. SOC code generations: SOC 2000 (2005–2009), SOC 2010 (2010–2018), SOC 2018 (2019+). Survivorship joining detailed codes against the 2022 anchor: ~82% for 2005–2009, ~83–87% for 2010–2018 overall — but as low as 3% for a single sector (SOC 2018 renumbered every computer code, so Computer and Mathematical keeps only four math occupations before 2019). **Sector-level growth therefore never comes from those survivor rows.** `analyze_bls.py` also keeps each file's 22 major-group summary rows, whose codes are stable across all three SOC generations, and writes them to `bls_sector_trends.csv`; every sector-level correlation in `validate_bls.py` and `synthesize_dynamic.py` reads its growth from that table via `sector_growth_series`, falling back to the survivor mean only if the file is missing. Two level breaks remain even at major-group level, where the SOC revisions moved occupations between groups: 2009→2010 and 2018→2019 (Office and Administrative Support drops 21.8M→19.5M across the latter). 2019+ files carry an `I_GROUP` (industry) column ahead of `O_GROUP`; row selection checks `O_GROUP`, `OCC_GROUP`, `GROUP` in that order and must not match on "GROUP" loosely. Files 2005–2013 are `.xls` format (requires `xlrd`); 2014+ are `.xlsx`.

**Task matching is text-based.** The Anthropic task penetration dataset has no Task IDs, so `synthesize_impacts.py` joins O\*NET tasks to Anthropic penetration scores by lowercased exact text match. This is intentional, not a gap. The consequence is that the right-hand side must be collapsed to one row per text before merging — that file repeats some task strings, and a repeated text otherwise fans out into duplicate rows that are each counted again in the occupation's `total_importance`, over-weighting that one task. `build_penetration_lookup` does the collapsing, and it verifies the repeated rows agree before collapsing them rather than assuming it — penetration is core model input, so a file that cannot be trusted raises `ValueError` instead of silently keeping whichever row sorted first. (The known case is one task text published under two capitalisations, four identical rows each, all at 0.7263; `PENETRATION_AGREEMENT_TOLERANCE` sets how close counts as agreeing.) Both joins in `load_and_match` also pass `validate="many_to_one"`, so a future release that reintroduces duplicates fails loudly rather than inflating scores.

**Three demand types drive the model.** The core economic logic lives in `synthesize_impacts.py`:

```
rebound_adjusted_exposure = observed_penetration × (1 − rebound_fraction)
```

- `Bounded` → rebound = 0.1 → productivity gain does not feed back into demand for the task; most exposure is structural
- `Unbounded` → rebound = 0.7 → productivity gain feeds back into demand (non-zero-sum); most exposure is absorbed
- `Adversarial` → rebound = 0.9 → subset of Unbounded; demand growth is zero-sum (arms-race escalation); nearly all exposure is absorbed

`occupation_exposure` is the importance-weighted mean of rebound-adjusted task exposures — always ≥ 0, with higher values indicating greater structural AI exposure. The three rebound constants (`BOUNDED_REBOUND=0.1`, `UNBOUNDED_REBOUND=0.7`, `ADVERSARIAL_REBOUND=0.9`) at the top of `synthesize_impacts.py` are intentionally exposed as tunable research parameters; they are structural priors pending calibration against historical elasticity data. See `docs/model_vs_observed_exposure.md` for a comparison against raw observed AI task coverage.

**`dominant_demand` is derived, never carried.** It and `dominant_strength` are a summary of the
`pct_bounded`/`pct_unbounded`/`pct_adversarial` composition, so they are only valid for the
composition they were computed from. `attach_dominant_demand` in `synthesize_impacts.py` derives
both, and it must be re-applied after any aggregation that changes those percentages — in
particular where `validate_bls.py` collapses several O\*NET occupations into one BLS SOC code.
Aggregating the percentages with `mean` while taking the label with `first` silently produced 8
SOC codes, Chief Executives among them, whose label contradicted their own composition.

## Release Pipeline

Push a `v*` tag to cut a GitHub release with all pipeline outputs attached as assets:

```bash
git tag v1.0 && git push origin v1.0
```

The workflow (`.github/workflows/release.yml`) downloads fresh O\*NET, Anthropic, BLS, and CPS data, then runs `analyze → synthesize → plot → validate`. Classification is skipped — the pre-computed results live in `seeds/classified_all_tasks.csv` and are copied into place before the pipeline runs. To update the seed after a re-classification, copy `data/output/classified_all_tasks.csv` to `seeds/` and commit it.

**`seeds/cps_a19_panel.csv` follows the same convention.** CPS Table A-19 is a rolling page carrying only two months at a time, so history exists only in this committed panel — `data/` is gitignored and CI starts empty. Each run merges the latest fetch into the panel and writes `data/output/cps_a19_panel.csv`; that file must reach `seeds/` or the newly fetched months are lost. A release run does this for you — its last step opens a `release-artifacts/<tag>` pull request carrying the refreshed panel and the regenerated `docs/charts/images/` PNGs, and **merging that pull request is what preserves the months**. After a local run, promote it by hand with `cp data/output/cps_a19_panel.csv seeds/` and commit. If BLS blocks the fetch, `download_cps.js` warns and exits 0 under CI so the pipeline still renders correctly labelled charts from the seed alone.

**`seeds/dws_displacement_panel.csv` follows the same convention, for the same reason.** The BLS Displaced Worker Supplement news release is a rolling page carrying only the latest biennial survey, and BLS publishes no archive of prior releases — checked 2026-09-12, `/news.release/archives/disp_*.htm`, `/bls/news-release/disp.htm` and `/data/archived.htm` all return 404, and web.archive.org is unreachable from CI. History therefore accumulates one survey at a time in this committed panel; `data/output/dws_displacement_panel.csv` must reach `seeds/` or a survey is lost. `download_dws.py` needs `BLS_CONTACT_EMAIL` set (see README) because BLS returns 403 to a User-Agent without a contact email, and it warns and exits 0 under CI so the pipeline still renders from the seed alone. The panel currently holds one survey (January 2026, covering 2023–2025); the demand composition model's headline correlation does not depend on the panel's length — see `docs/superpowers/plans/2026-09-11-demand-composition-model.md`.

**`seeds/soc_crosswalks/` and `seeds/oews_aggregate_codes.csv` are committed reference data, not downloads.** The BLS SOC crosswalks and the OEWS hybrid structure are static published files that bls.gov blocks plain HTTP from fetching, and the aggregate-code seed is hand-derived from OEWS titles, so `harmonize_soc.py` reads all four straight from `seeds/` with no download step.

BLS zip downloads are cached by `download_bls.js` hash, so re-runs only re-fetch if the download script changes.

Both workflows set `defaults.run.shell: bash`. GitHub's default is `bash -e`, which stops on a failing command but not on one inside a pipeline — a pipeline's exit code is its last command's. The release job pipes the pipeline into `tee` to capture the run log, so without this a crashed `main.py` would exit 0 and the workflow would go on to package and publish a release from whatever partial output survived.

The release job holds `contents: write` and `pull-requests: write`. It opens a pull request rather than pushing to `main` directly, because `main` is protected and `GITHUB_TOKEN` acts as `github-actions[bot]`, which is not an admin and cannot bypass that.

## Outputs Reference

**When adding a new pipeline output (CSV, visualization, or printed table), add a row here before committing.** This is the authoritative record of what the pipeline produces and what each output is for. If an output changes behaviour or is removed, update or delete its row.

### Data files — `data/output/`

| File | Produced by | Purpose |
|------|-------------|---------|
| `occupation_exposure_report.csv` | `synthesize_impacts.py` | Per-occupation rebound-adjusted exposure score, dominant demand type, dominant strength, mean penetration, Eloundou exposure, and exposure tier. Primary model output. |
| `bls_trends.csv` | `analyze_bls.py` | Year-over-year and composite employment/wage growth by detailed occupation, 2005–2025 (pre-2022 columns prefixed `hist_`). Used for occupation-level validation. Pre-2019 columns are NaN for occupations whose SOC code changed. |
| `bls_sector_trends.csv` | `analyze_bls.py` | Same column layout keyed by two-digit `soc_major`, built from each OEWS file's own major-group summary rows. Complete for all 22 sectors in every year 2005–2025, because major-group codes survive SOC revisions. The source of every sector-level growth measure in `validate_bls.py`. |
| `bls_harmonized_trends.csv` | `analyze_bls.py` (via `harmonize_soc.py`) | Occupation-level employment/wage trends 2005–2025 on harmonized units — connected components of the SOC 2000→2010→2018 crosswalks (plus the OEWS 2019–20 hybrid), with residual "All Other" edges pruned. Same column layout as `bls_trends.csv`, keyed by `unit_id`. A unit's year is NaN when any member code OEWS publishes was absent. Used for the occupation-level historical validation. |
| `soc_harmonization_units.csv` | `analyze_bls.py` (via `harmonize_soc.py`) | Which OEWS code in which year belongs to which harmonized unit, with the unit's SOC 2018 members and major groups. |
| `soc_harmonization_pruned_edges.csv` | `analyze_bls.py` (via `harmonize_soc.py`) | Crosswalk edges dropped because they link a residual "All Other" category to a specific occupation. The leakage the harmonization accepts, listed for audit. |
| `exposure_volume_by_occupation.csv` | `validate_bls.py` | Per-occupation `employment_share × mean_penetration` (`exposure_volume`), sorted descending. Shows where AI exposure is landing in the workforce. |
| `exposure_volume_by_group.csv` | `validate_bls.py` | Same metric rolled up to SOC major group. Includes `group_dominant_demand` and `pct_of_total_exposure`. |
| `employment_by_demand_type.csv` | `validate_bls.py` | Total workers, % of modeled workforce, mean occupation impact, and occupation count for each dominant demand type. |
| `dws_displacement_panel.csv` | `dws_panel.py` | Displaced Worker Supplement counts by occupation group, by reason for job loss, and in total across all tenures, accumulated from every DWS release parsed so far. Merge of `seeds/dws_displacement_panel.csv` with the latest fetch. The occupation rows are the independent validation target for the demand composition model's displacement term; the `position or shift abolished` reason row isolates structural displacement from the cyclical and demand-shock categories. |
| `cps_a19_panel.csv` | `cps_panel.py` (via `validate_bls.py`) | CPS Table A-19 employment (thousands) by SOC major group and month, accumulated from every A-19 release parsed so far. Merge of `seeds/cps_a19_panel.csv` with the latest fetch. |
| `equilibration_sensitivity.csv` | `synthesize_dynamic.py` (via `validate_bls.py`) | Sector-level Pearson r against composite employment growth at each equilibration rate, sweeping the absorption scalar from 0 (no reabsorption) to 100× the conservation-pinned value. Shows how much of the dynamic model's headline result depends on the conservation constraint holding exactly. Also printed during `validate`. See `docs/framework.md` § Robustness to the equilibration rate. |
| `occupation_dynamic_model_report.csv` | `validate_bls.py` | Dynamic labor equilibrium model output. Signed `net_employment_change` per occupation (negative = net loser, positive = net gainer); employment-weighted sum = 0 by construction. Includes `gross_displacement`, `absorption`, `absorption_capacity` (Unbounded + Adversarial share — Adversarial is a carve-out from Unbounded and absorbs on the same footing), contribution columns, and `pct_*` composition for transparency. |
| `sector_jackknife.csv` | `synthesize_dynamic.py` (via `validate_bls.py`) | Leave-one-sector-out recomputation of the dynamic model's sector-level composite employment correlation: one row per dropped SOC major group with the resulting r, p, and the full-sample r for reference. Shows which sector, if any, the headline result depends on (currently Office and Administrative Support — dropping it gives p = 0.094). Range summarised during `validate`. See `docs/framework.md` § Leave-one-sector-out jackknife. |

### Visualizations — `data/output/visualizations/`

| File | Produced by | Purpose |
|------|-------------|---------|
| `highest_exposure_occupations.png` | `generate_plots.py` | Horizontal bar chart of top 30 occupations by rebound-adjusted structural exposure, colored by dominant demand type. |
| `theoretical_vs_rebound_adjusted_exposure.png` | `generate_plots.py` | Scatter of Eloundou et al. theoretical exposure vs. rebound-adjusted exposure score, colored by dominant demand type. Shows where demand type causes the model to diverge from naive exposure. See `docs/charts/theoretical_vs_rebound_adjusted_exposure.md`. |
| `model_vs_naive_divergence.png` | `generate_plots.py` | Top 5 occupations where the model departs most from the naive exposure baseline. See `docs/charts/model_vs_naive_divergence.md`. |
| `usage_by_demand_type.png` | `generate_plots.py` | Stacked bar: Claude conversation share by demand type, with each bar stacked by occupational category (SOC major group). Task share shown as a simple reference bar alongside. |
| `task_importance_vs_penetration.png` | `generate_plots.py` | Grouped boxplot: task importance score by demand type, split by whether the task has AI penetration > 0. |
| `model_vs_actual_employment_growth.png` | `validate_bls.py` | 2×2 grid: model impact score vs. YoY employment growth for each period (2022–23, 23–24, 24–25, composite). Per-demand trend lines + overall trend line. |
| `model_vs_actual_wage_growth.png` | `validate_bls.py` | Same layout as above for median wage growth. |
| `employment_vs_wage_growth_by_demand_type.png` | `validate_bls.py` | Composite employment growth vs. composite wage growth, colored by demand type. Tests whether Unbounded/Adversarial occupations show the expected productivity premium. See `docs/charts/employment_vs_wage_growth_by_demand_type.md`. |
| `exposure_volume_by_group.png` | `validate_bls.py` | Horizontal bar: employment-weighted AI exposure by SOC major group, colored by group dominant demand type. |
| `exposure_share_by_group.png` | `validate_bls.py` | Same as above but each bar shows the group's share of total economy-wide AI exposure volume. |
| `employment_by_demand_type.png` | `validate_bls.py` | Bar chart: total U.S. workers in each dominant demand type bucket, annotated with % of modeled workforce and mean impact score. |
| `wage_quartile_demand_type.png` | `validate_bls.py` | Two-panel: (left) employment-weighted demand type share by wage quartile; (right) employment-weighted mean model impact score by quartile. |
| `observed_vs_rebound_adjusted_exposure.png` | `validate_bls.py` | Scatter of observed AI task coverage vs. rebound-adjusted exposure score. Strong r (0.712): Bounded occupations with high penetration dominate the upper-right; Adversarial/Unbounded cluster near zero regardless of coverage. See `docs/charts/observed_vs_rebound_adjusted_exposure.md`. |
| `sector_adjusted_employment_growth.png` | `validate_bls.py` | 2×2 grid: model impact vs. employment growth residual (occupation minus employment-weighted sector mean) per period. See `docs/charts/sector_adjusted_growth.md`. |
| `sector_adjusted_wage_growth.png` | `validate_bls.py` | Same layout as above for wage growth residuals. |
| `sector_level_validation.png` | `validate_bls.py` | 2-panel labeled bubble scatter: employment-weighted sector mean rebound-adjusted exposure vs. composite growth. No significant relationship — employment r=−0.290 (p=0.191), wage r=−0.218 (p=0.330). Growth from BLS major-group totals. See `docs/charts/sector_level_validation.md`. |
| `top_exposure_trajectories.png` | `validate_bls.py` | Line chart of 2022–2025 BLS employment trajectories for top 10 highest-exposure occupations, indexed to 100 at 2022. Each line annotated with model exposure score vs. actual employment change. |
| `high_exposure_concentration.png` | `validate_bls.py` | Bubble chart: structural exposure pressure vs. employment share for occupations above 5% threshold. Bubble size ∝ AI exposure volume. See `docs/charts/high_exposure_concentration.md`. |
| `dynamic_model_net_change_distribution.png` | `validate_bls.py` / `synthesize_dynamic.py` | Histogram of signed `net_employment_change` across all matched occupations, layered by dominant demand type. Annotates zero line and economy-wide mean. See `docs/charts/dynamic_model_net_change_distribution.md`. |
| `dynamic_model_winners_losers.png` | `validate_bls.py` / `synthesize_dynamic.py` | Diverging horizontal bar: top 20 occupations by net employment gain vs. top 20 by net employment loss, colored by dominant demand type. See `docs/charts/dynamic_model_winners_losers.md`. |
| `dynamic_vs_rebound_model_comparison.png` | `validate_bls.py` / `synthesize_dynamic.py` | Scatter of `occupation_exposure` (x, existing model, ≥ 0) vs `net_employment_change` (y, dynamic model, signed). Shows how the two models reorder occupations. See `docs/charts/dynamic_vs_rebound_model_comparison.md`. |
| `dynamic_model_vs_actual_employment_growth.png` | `validate_bls.py` | 2×2 grid: dynamic model `net_employment_change` vs. YoY employment growth for each period. See `docs/charts/dynamic_model_growth_validation.md`. |
| `dynamic_model_vs_actual_wage_growth.png` | `validate_bls.py` | Same layout as above for median wage growth. See `docs/charts/dynamic_model_growth_validation.md`. |
| `dynamic_model_sector_adjusted_employment_growth.png` | `validate_bls.py` | 2×2 grid: dynamic model `net_employment_change` vs. sector-adjusted employment growth residual per period. See `docs/charts/dynamic_model_growth_validation.md`. |
| `dynamic_model_sector_adjusted_wage_growth.png` | `validate_bls.py` | Same layout as above for sector-adjusted wage growth residuals. See `docs/charts/dynamic_model_growth_validation.md`. |
| `dynamic_sector_level_validation.png` | `validate_bls.py` / `synthesize_dynamic.py` | 2-panel bubble scatter: employment-weighted sector mean `net_employment_change` vs. composite growth. Employment r=+0.509, p=0.015 (jackknife range +0.34 to +0.59) — the strongest sector-level signal in the pipeline. See `docs/charts/dynamic_sector_level_validation.md`. |
| `sector_level_employment_validation.png` | `validate_bls.py` | 2×2 grid: sector mean rebound-adjusted exposure vs. sector employment growth per period. Significant only in 2023→24 (r=−0.428, p=0.047). See `docs/charts/sector_level_employment_validation.md`. |
| `sector_level_wage_validation.png` | `validate_bls.py` | 2×2 grid: sector mean rebound-adjusted exposure vs. sector wage growth per period. No significant signal in any period. See `docs/charts/sector_level_wage_validation.md`. |
| `dynamic_sector_level_employment_validation.png` | `validate_bls.py` | 2×2 grid: sector mean `net_employment_change` vs. sector employment growth per period. Significant in 2023→24 (r=+0.530, p=0.011), 2024→25 (r=+0.482, p=0.023), and composite. See `docs/charts/dynamic_sector_level_employment_validation.md`. |
| `dynamic_sector_level_wage_validation.png` | `validate_bls.py` | 2×2 grid: sector mean `net_employment_change` vs. sector wage growth per period. No significant signal in any period. See `docs/charts/dynamic_sector_level_wage_validation.md`. |
| `eloundou_sector_level_employment_validation.png` | `validate_bls.py` | 2×2 grid: sector mean Eloundou theoretical exposure vs. sector employment growth per period. No significant signal in any period. See `docs/charts/eloundou_sector_level_employment_validation.md`. |
| `eloundou_sector_level_wage_validation.png` | `validate_bls.py` | 2×2 grid: sector mean Eloundou theoretical exposure vs. sector wage growth per period. Negative but not significant in 2022→23 (r=−0.394, p=0.070); drops to r=−0.210 when the six post-COVID recovery sectors are excluded. See `docs/charts/eloundou_sector_level_wage_validation.md`. |
| `anthropic_observed_sector_level_employment_validation.png` | `validate_bls.py` | 2×2 grid: sector mean Anthropic observed task coverage vs. sector employment growth per period. Trending negative in 2023→24 (r=−0.373, p=0.088) — the hypothesised direction for a gross coverage measure, though short of significance. See `docs/charts/anthropic_observed_sector_level_employment_validation.md`. |
| `anthropic_observed_sector_level_wage_validation.png` | `validate_bls.py` | 2×2 grid: sector mean Anthropic observed task coverage vs. sector wage growth per period. Negative and significant: 2022→23 r=−0.442 (p=0.040), 2023→24 r=−0.484 (p=0.022), composite r=−0.502 (p=0.017, leave-one-out range −0.45 to −0.63). High-coverage knowledge sectors had the weakest median-wage growth 2022→25. Only partly a post-COVID recovery confound. See `docs/charts/anthropic_observed_sector_level_wage_validation.md`. |
| `cps_2026_direction.png` | `validate_bls.py` | Paired horizontal bars: employment growth by SOC major group over both CPS windows — since the OEWS reference month, and 12-month year-over-year. Dates read from the panel, not hardcoded. Directional indicator only — not BLS OEWS. See `docs/charts/cps_2026_direction.md`. |
| `cps_rebound_model_vs_actual.png` | `validate_bls.py` | Scatter: employment-weighted rebound-adjusted exposure score per SOC major group vs. CPS growth since the OEWS reference month; year-over-year r reported in the subtitle. See `docs/charts/cps_model_vs_actual.md`. |
| `cps_dynamic_model_vs_actual.png` | `validate_bls.py` | Scatter: employment-weighted dynamic net employment change per SOC major group vs. CPS growth since the OEWS reference month; year-over-year r reported in the subtitle. See `docs/charts/cps_model_vs_actual.md`. |
| `model_signal_over_time.png` | `validate_bls.py` | Sector-level Pearson r by YoY period (2015→2025) for rebound-adjusted, dynamic, and Anthropic observed models. 2022 boundary and COVID years marked. Tests whether the AI-era signal is pre-existing or emerges post-2022. A separate right-hand panel adds the 2025→2026 span from CPS A-19 — different survey, drawn unconnected on an endpoint-month axis so it is not read as a continuation of the OEWS line. See `docs/charts/model_signal_over_time.md`. |
| `model_signal_over_time_occupation.png` | `validate_bls.py` | Same layout as above but occupation-level (no sector aggregation). Each point is a harmonized SOC unit from `soc_harmonization_units.csv`, so the same occupation definitions carry every period and n is near-constant (~695, annotated at bottom) instead of moving with SOC survivorship. Higher power, noisier than sector-level version. See `docs/charts/model_signal_over_time_occupation.md`. |

## Coding Standards

From `CONTRIBUTING.md`. Only some of these are machine-checkable — the rest are
review conventions, so hold to them without expecting a tool to catch a lapse:

- **No generic abbreviations**: never `df`, `res`, `tmp`, `val`. Use `occupation_exposure_df`, `task_penetration_response`, etc. *(convention — no linter enforces this)*
- **Domain terminology**: variable names must reflect what they contain (`penetration_value`, `demand_type`, `onet_tasks_df`). *(convention — no linter enforces this)*
- **Module docstrings**: every Python file must have a module-level docstring describing its name, purpose, inputs, and outputs. *(enforced — ruff `D100`)*

Ruff's selected rules are `E`, `W`, `F`, `I`, `N`, and `D100`. Note that `N` is
pep8-**naming**, which checks casing conventions only; it has nothing to say
about the abbreviation rule above.

## CI

`.github/workflows/ci.yml` runs on every pull request and on pushes to `main`:
`ruff check`, `ruff format --check`, `pytest tests/`, and a `node --check` parse
of the Puppeteer scripts. It installs with `uv sync --locked`, so a dependency
bump that does not re-lock fails there rather than at release time.

The ruff version is pinned in two places that must agree — the `dev` group in
`pyproject.toml` and the `ruff-pre-commit` rev in `.pre-commit-config.yaml`. If
they drift, `make lint` and the pre-commit hook will reformat each other's work.
