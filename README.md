# AI Labor Exposure

> A data pipeline designed to move beyond static estimates of "AI observed exposure"—the assumption that if a model can do a task, human labor will proportionally decrease. Instead, this project categorizes O*NET tasks according to their fundamental economic demand rules: **Bounded, Unbounded, and Adversarial**.
>
> By applying dynamic demand classifications against Anthropic's Economic Index and occupational data using LLM-assisted pipelines, this repository seeks to measure not just *where* AI acts as a replacement, but where it acts as a productivity engine (The Infinite Frontier) or fuels zero-sum escalation (The Arms Race).

## Influences & Background

* **[AI Jobs: The Hidden Rules of Demand](https://substack.norabble.com/p/ai-jobs-the-hidden-rules-of-demand)** (`norabble`) - *The core theoretical framework for Bounded, Unbounded, and Adversarial demand dynamics.*
* **[Anthropic's Labor Market Impacts](https://www.anthropic.com/research/labor-market-impacts)** - *The foundational "Observed Exposure" dataset mapping AI capabilities to O\*NET task statements.*

## Demand Type Framework

| Type | Mechanism | Example Roles |
|------|-----------|---------------|
| **Bounded** | Finishing faster reduces workers needed; no new demand is created | Payroll, Data Entry |
| **Unbounded** | Efficiency unlocks a backlog of unmet demand; output expands | Programming, Science, Healthcare |
| **Adversarial** | Zero-sum competition; time saved is reinvested to stay ahead | Law, Sales, Marketing, Cybersecurity |

## Prerequisites

- Python 3.12+ with [uv](https://docs.astral.sh/uv/)
- Node.js (for BLS data download — BLS blocks plain HTTP requests, requiring a headless browser)
- A GCP project with Vertex AI enabled (for the classification stage only)

## Setup

```bash
# Install Python and Node dependencies, set up pre-commit hooks
make setup
```

Create a `.env` file in the project root:

```
GCP_PROJECT_ID=your-gcp-project-id
GCP_LOCATION=us-central1
```

## Running the Pipeline

The pipeline has two phases. Phase 1 (classification) is expensive and slow; it only needs to run once.

### Phase 1 — Classify O\*NET Tasks (one-time, ~19k LLM calls)

```bash
make download-data   # Download O*NET, Anthropic, and BLS source data
make classify        # Classify all tasks via Vertex AI (resumable if interrupted)
```

Output: `data/output/classified_all_tasks.csv`

### Phase 2 — Synthesize and Validate

```bash
make run-pipeline
# or selectively:
uv run main.py synthesize plot
uv run main.py validate
```

Stages:

| Stage | Input | Output |
|-------|-------|--------|
| `analyze` | `data/raw/bls/*.zip` | `data/output/bls_trends.csv` |
| `synthesize` | classified tasks + penetration data | `data/output/occupation_impact_report.csv` |
| `plot` | occupation impact report | `data/output/visualizations/*.png` |
| `validate` | impact report + BLS trends | correlation statistics + validation plots |

## Model

The occupation-level impact score is a task-importance-weighted average of per-task net impacts:

```
Adversarial task:  net_impact = +penetration × ADVERSARIAL_REBOUND  (default 1.0)
Unbounded task:    net_impact = +penetration × UNBOUNDED_REBOUND    (default 0.5)
Bounded task:      net_impact = −penetration × BOUNDED_DECLINE      (default 1.0)
```

Scores range from −1 (full displacement) to +1 (full demand expansion). The rebound/decline multipliers in `synthesize_impacts.py` are intentionally exposed as tunable parameters.

## Outputs

- **`occupation_impact_report.csv`** — Per-occupation impact score, demand type breakdown, penetration metrics, and narrative label
- **`visualizations/most_impacted_jobs.png`** — Top 15 highest/lowest impact occupations
- **`visualizations/exposure_vs_impact.png`** — Our model vs. naive Eloundou exposure-only prediction
- **`visualizations/bls_emp_growth_vs_impact.png`** — Predicted impact vs. actual BLS employment growth
- **`visualizations/bls_wage_growth_vs_impact.png`** — Predicted impact vs. actual BLS wage growth

## Development

```bash
make test    # Run unit tests
make lint    # Ruff check + format
```
