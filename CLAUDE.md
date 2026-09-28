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
uv run check_charts.py  # Committed charts vs docs/outputs.md, and vs the latest run's fingerprints
```

Run specific pipeline stages:
```bash
uv run main.py synthesize plot        # run two stages
uv run main.py composition            # re-run only the experimental composition model
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
5. `synthesize_composition` — **experimental**: the demand composition model, which strips all AI data from the predictor to test whether the Bounded/Unbounded/Adversarial taxonomy applies before AI. Runs last because its era comparison scores against the AI dynamic model that `validate` writes. See `docs/framework.md` § Demand Composition Model.

## Project Goal

This project produces a **structural exposure score** — a current snapshot of which occupations are most exposed to AI-driven demand change, stratified by demand type. It is not a displacement prediction. Testing against BLS employment data is an ongoing confidence check; null results are expected. See `docs/framework.md` for the full conceptual framework, exposure type taxonomy, and demand type definitions.

## Key Design Decisions

**BLS downloads require Node.js.** BLS blocks plain HTTP requests; `download_bls.js` (OEWS zips) and `download_cps.js` (CPS Table A-19) use Puppeteer (headless Chrome) to bypass this. The Python `requests` approach will not work — A-19 returns 403 to it. The two scripts are deliberately separate: `release.yml` caches the OEWS zips on `hashFiles('download_bls.js')` and skips that script entirely on a cache hit, which would mean the rolling monthly A-19 table was never re-fetched. The 2024/2025 data is only available as all-areas files (`oesm24all.zip`, `oesm25all.zip`); `analyze_bls.py` filters them to national cross-industry rows (`AREA_TYPE==1`, `OWN_CODE==1235`, `NAICS=='000000'`). Historical files 1999–2021 are national-only and require no such filtering. SOC code generations: SOC 2000 (1999–2009), SOC 2010 (2010–2018), SOC 2018 (2019+). The series starts at 1999, the first OEWS year coded on SOC 2000 with 22 major-group summary rows; 1997 and 1998 use the pre-SOC five-digit OES coding system with div/maj group headers and are deliberately excluded. Files 1999–2000 carry ~38 banner rows above the column header, 2000 and 2002 spell the title column `occ_titl`, and 2002 flags `00-0000` as a major group — `load_bls_year` and `select_major_group_rows` handle all three. 1999–2002 are annual estimates while 2003 onward carry a May reference month, so the 2002→2003 interval is not a clean twelve months. Survivorship joining detailed codes against the 2022 anchor: ~82% for 2005–2009, ~83–87% for 2010–2018 overall — but as low as 3% for a single sector (SOC 2018 renumbered every computer code, so Computer and Mathematical keeps only four math occupations before 2019). Occupation-level survivorship falls further still for 1999–2004, the same SOC 2000 vintage as 2005–2009. **Sector-level growth therefore never comes from those survivor rows.** `analyze_bls.py` also keeps each file's 22 major-group summary rows, whose codes are stable across all three SOC generations, and writes them to `bls_sector_trends.csv`; every sector-level correlation in `validate_bls.py` and `synthesize_dynamic.py` reads its growth from that table via `sector_growth_series`, falling back to the survivor mean only if the file is missing. Two level breaks remain even at major-group level, where the SOC revisions moved occupations between groups: 2009→2010 and 2018→2019 (Office and Administrative Support drops 21.8M→19.5M across the latter). 2019+ files carry an `I_GROUP` (industry) column ahead of `O_GROUP`; row selection checks `O_GROUP`, `OCC_GROUP`, `GROUP` in that order and must not match on "GROUP" loosely. Files 1999–2013 are `.xls` format (requires `xlrd`); 2014+ are `.xlsx`.

**BLS suppresses wages in two different ways, and neither is missing data.** `#` means the wage is at or above a ceiling BLS sets each year — a censored value with a known floor. `*` means the estimate was not released, which for the 4–6 hourly-only occupations a year (actors, dancers, musicians) means BLS declines to invent an annual figure they don't work the hours for. `analyze_bls.py` reports both counts per year rather than coercing them to an indistinguishable `NaN`, computes growth from `H_MEDIAN` where the annual series is unavailable, and derives the censoring floor from the data — BLS documents the ceiling only through 2018 and moved it twice after. The censored set is almost entirely physicians and surgeons, so no wage-growth window in the current data has two uncensored physician endpoints; censoring stops in 2025, so that series begins with the 2026 release. See `docs/wage_censoring.md`.

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

## Seeds

`data/` is gitignored and CI starts empty, so some history exists only in `seeds/`. A run writes the refreshed copy to `data/output/`, and it is lost unless promoted back. Full detail — formats, parsers, BLS archive quirks, measurement bases — is in `docs/seeds.md`; read it before touching a seed's pipeline.

| Seed | Refreshed by | Promoted to `seeds/` by |
|------|--------------|-------------------------|
| `classified_all_tasks.csv` | `make classify` (paid, ~19k LLM calls) | `cp data/output/classified_all_tasks.csv seeds/` |
| `cps_a19_panel.csv` | every run (rolling two-month A-19 page) | merging the release's `release-artifacts/<tag>` PR; after a local run, `cp` by hand |
| `dws_displacement_panel.csv` | every run (current DWS release only) | same as above. `python dws_panel.py` rebuilds history from raw archives for comparison only, never promoted |
| `cps_occupation_panel.csv` | composition stage (inline BLS API fetch) | `cp` by hand — `release.yml` does not promote it yet |
| `cps_detailed_occupation_panel.csv`, `cps_detailed_occ_crosstab.csv`, `cps_detailed_gates.csv` | local IPUMS build only, never CI (`cps_detailed_panel.py build`) | `python cps_detailed_panel.py promote` — refuses unless gates G1/G2/G5/G6 pass |
| `dws_detailed_panel.csv`, `dws_detailed_gates.csv` | local IPUMS build only, never CI (`dws_detailed_panel.py build`) | `python dws_detailed_panel.py promote` — refuses unless gates G3/G6D pass |
| `mlr_occupation_crosswalk.csv`, `oews_aggregate_codes.csv`, `occ1990dd_groups.csv`, `soc_crosswalks/`, `cps_soc_crosswalks/`, `occ1990dd_crosswalks/` | never — static published or hand-derived reference data | edited directly, deliberately |

IPUMS terms prohibit redistributing microdata, so the IPUMS-built seeds hold aggregates only. `download_ipums_cps.py` needs `IPUMS_API_KEY`; `download_dws.py` needs `BLS_CONTACT_EMAIL` (BLS returns 403 without a contact email in the User-Agent). Both BLS fetchers warn and exit 0 under CI so the pipeline still renders from the seeds alone.

BLS zip downloads are cached by `download_bls.js` hash, so re-runs only re-fetch if the download script changes.

Both workflows set `defaults.run.shell: bash`. GitHub's default is `bash -e`, which stops on a failing command but not on one inside a pipeline — a pipeline's exit code is its last command's. The release job pipes the pipeline into `tee` to capture the run log, so without this a crashed `main.py` would exit 0 and the workflow would go on to package and publish a release from whatever partial output survived.

The release job holds `contents: write` and `pull-requests: write`. It opens a pull request rather than pushing to `main` directly, because `main` is protected and `GITHUB_TOKEN` acts as `github-actions[bot]`, which is not an admin and cannot bypass that.

## Chart freshness

Every chart is saved through `chart_manifest.save_figure`, never a bare `savefig`, so it gets a content fingerprint. `check_charts.py` fails if a documented chart has no committed image, a committed image is undocumented, a markdown image link is broken (all three also run in `pytest` as the CI gate), or a committed image's fingerprint differs from the latest local run's. A Stop hook runs it and reports failures. The committed `docs/charts/images/chart_manifest.json` is refreshed by the release PR along with the images.

## Outputs Reference

`docs/outputs.md` is the authoritative record of every pipeline output (CSV, visualization, printed table) and what it is for. **When adding, changing, or removing an output, update its row there in the same commit.** Rows describe the output; measured results go in `docs/framework.md` or `docs/charts/*.md` (use the `record-measured-result` skill).

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
