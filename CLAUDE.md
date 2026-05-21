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
uv run pytest tests/test_pipeline.py::TestComputeTaskImpact::test_bounded_reduces_demand
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

## Key Design Decisions

**BLS downloads require Node.js.** BLS blocks plain HTTP requests; `download_bls.js` uses Puppeteer (headless Chrome) to bypass this. The Python `requests` approach will not work. The 2024 data is only available as `oesm24all.zip` (all areas); `analyze_bls.py` filters it to national cross-industry rows (`AREA_TYPE==1`, `OWN_CODE==1235`, `NAICS=='000000'`).

**Task matching is text-based.** The Anthropic task penetration dataset has no Task IDs, so `synthesize_impacts.py` joins O\*NET tasks to Anthropic penetration scores by lowercased exact text match. This is intentional, not a gap.

**Three demand types drive the model.** The core economic logic lives in `synthesize_impacts.py`:

```
task_impact = penetration × (1 − rebound_fraction)
```

- `Bounded` → rebound = 0.0 → full displacement, no absorption
- `Unbounded` → rebound = 0.5 → half absorbed by backlog expansion
- `Adversarial` → rebound = 1.0 → fully absorbed by arms-race escalation

`occupation_impact` is the importance-weighted mean of task impacts — always ≥ 0, with higher values indicating greater structural disruption. The three rebound constants (`BOUNDED_REBOUND=0.0`, `UNBOUNDED_REBOUND=0.5`, `ADVERSARIAL_REBOUND=1.0`) at the top of `synthesize_impacts.py` are intentionally exposed as tunable research parameters.

## Release Pipeline

Push a `v*` tag to cut a GitHub release with all pipeline outputs attached as assets:

```bash
git tag v1.0 && git push origin v1.0
```

The workflow (`.github/workflows/release.yml`) downloads fresh O\*NET, Anthropic, and BLS data, then runs `analyze → synthesize → plot → validate`. Classification is skipped — the pre-computed results live in `seeds/classified_all_tasks.csv` and are copied into place before the pipeline runs. To update the seed after a re-classification, copy `data/output/classified_all_tasks.csv` to `seeds/` and commit it.

BLS zip downloads are cached by `download_bls.js` hash, so re-runs only re-fetch if the download script changes.

## Outputs Reference

**When adding a new pipeline output (CSV, visualization, or printed table), add a row here before committing.** This is the authoritative record of what the pipeline produces and what each output is for. If an output changes behaviour or is removed, update or delete its row.

### Data files — `data/output/`

| File | Produced by | Purpose |
|------|-------------|---------|
| `occupation_impact_report.csv` | `synthesize_impacts.py` | Per-occupation impact scores, dominant demand type, dominant strength, mean penetration, Eloundou exposure, and impact narrative. Primary model output. |
| `bls_trends.csv` | `analyze_bls.py` | Year-over-year and composite employment/wage growth by occupation (2022–2025). Used for model validation. |
| `exposure_volume_by_occupation.csv` | `validate_bls.py` | Per-occupation `employment_share × mean_penetration` (`exposure_volume`), sorted descending. Shows where AI exposure is landing in the workforce. |
| `exposure_volume_by_group.csv` | `validate_bls.py` | Same metric rolled up to SOC major group. Includes `group_dominant_demand` and `pct_of_total_exposure`. |
| `employment_by_demand_type.csv` | `validate_bls.py` | Total workers, % of modeled workforce, mean occupation impact, and occupation count for each dominant demand type. |

### Visualizations — `data/output/visualizations/`

| File | Produced by | Purpose |
|------|-------------|---------|
| `most_impacted_jobs.png` | `generate_plots.py` | Horizontal bar chart of top 30 occupations by displacement impact, colored by dominant demand type. |
| `prior_exposure_vs_model_impact.png` | `generate_plots.py` | Scatter of Eloundou et al. exposure vs. model impact score, colored by dominant demand type. Shows where demand type causes the model to diverge from naive exposure-as-displacement. See `docs/charts/prior_exposure_vs_model_impact.md`. |
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
| `observed_ai_usage_vs_model_impact.png` | `validate_bls.py` | Scatter of observed AI task coverage vs. model impact score. Strong r (0.712): Bounded occupations with high penetration dominate the upper-right; Adversarial/Unbounded cluster near zero regardless of coverage. See `docs/charts/observed_ai_usage_vs_model_impact.md`. |
| `sector_adjusted_employment_growth.png` | `validate_bls.py` | 2×2 grid: model impact vs. employment growth residual (occupation minus employment-weighted sector mean) per period. See `docs/charts/sector_adjusted_growth.md`. |
| `sector_adjusted_wage_growth.png` | `validate_bls.py` | Same layout as above for wage growth residuals. |
| `sector_level_validation.png` | `validate_bls.py` | 2-panel labeled bubble scatter: employment-weighted sector impact vs. composite growth. Wage r=−0.485, p=0.022, jackknife-robust. See `docs/charts/sector_level_validation.md`. |
| `top_risk_trajectories.png` | `validate_bls.py` | Line chart of 2022–2025 BLS employment trajectories for top 10 most-negative-impact occupations, indexed to 100 at 2022. Each line annotated with model prediction vs. actual change. |
| `high_risk_concentration.png` | `validate_bls.py` | Bubble chart: displacement pressure vs. employment share for occupations above 5% threshold. Bubble size ∝ AI exposure volume. See `docs/charts/high_risk_concentration.md`. |

## Coding Standards

From `CONTRIBUTING.md` — these are enforced by pre-commit:

- **No generic abbreviations**: never `df`, `res`, `tmp`, `val`. Use `occupation_impact_df`, `task_penetration_response`, etc.
- **Domain terminology**: variable names must reflect what they contain (`penetration_value`, `demand_type`, `onet_tasks_df`)
- **Module docstrings**: every Python file must have a module-level docstring describing its name, purpose, inputs, and outputs
