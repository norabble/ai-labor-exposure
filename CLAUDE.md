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
- `Bounded` → `net_impact = -penetration × BOUNDED_DECLINE` (permanent displacement)
- `Unbounded` → `net_impact = +penetration × UNBOUNDED_REBOUND` (backlog absorbs savings)
- `Adversarial` → `net_impact = +penetration × ADVERSARIAL_REBOUND` (arms race refills work)

The three multipliers (`BOUNDED_DECLINE=1.0`, `UNBOUNDED_REBOUND=0.5`, `ADVERSARIAL_REBOUND=1.0`) at the top of `synthesize_impacts.py` are intentionally exposed as tunable research parameters.

## Coding Standards

From `CONTRIBUTING.md` — these are enforced by pre-commit:

- **No generic abbreviations**: never `df`, `res`, `tmp`, `val`. Use `occupation_impact_df`, `task_penetration_response`, etc.
- **Domain terminology**: variable names must reflect what they contain (`penetration_value`, `demand_type`, `onet_tasks_df`)
- **Module docstrings**: every Python file must have a module-level docstring describing its name, purpose, inputs, and outputs
