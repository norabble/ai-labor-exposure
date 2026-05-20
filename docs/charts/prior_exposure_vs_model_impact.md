# Prior Exposure vs. Model Impact Score

**File:** `prior_exposure_vs_model_impact.png`

## What this chart shows

Each dot is one occupation. The x-axis plots how exposed that occupation's tasks are to AI according to a published estimate from prior literature (Eloundou et al.), and the y-axis shows the impact score this model predicts for that same occupation.

The dashed diagonal line is the **naive baseline**: if AI exposure always caused job displacement, impact would equal minus exposure — every point would fall on that line.

Most points sit well above the naive baseline. This gap is the core finding of the model: raw exposure alone is a poor predictor of labor market impact, because the *type* of demand underlying those tasks changes whether AI augments or displaces the workers doing them.

## What the Eloundou et al. exposure estimate is

The x-axis values come from *GPTs are GPTs: An Early Look at the Labor Market Impact Potential of Large Language Models* (Eloundou, Manning, Mishkin, Rock, 2023). That paper scores each occupation by the fraction of its tasks that could be performed or assisted by an LLM, using a combination of human annotation and GPT-4 evaluation. The "mid" estimate averages their human and model scores.

That paper does not model demand type — it treats all exposure as equally risky. This chart shows where those exposure scores land relative to this model's more granular predictions.

## How to read the dot colors

Colors indicate each occupation's **dominant demand type** — the classification that carries the most task-importance weight for that occupation:

- **Red (Bounded):** Tasks where AI can complete the work to a fixed endpoint. Demand falls once the backlog clears — displacement risk.
- **Orange (Unbounded):** Tasks where capacity savings get reinvested into doing more. Demand grows — expansion.
- **Green (Adversarial):** Tasks driven by a counterparty that escalates in response (e.g., fraud, compliance, security). Demand grows with AI capability — expansion.

## What "diverges from the naive baseline" means

Positive model impact + high exposure = the occupation sits far above the dashed line. This means the model predicts expansion even though prior literature flagged the occupation as highly exposed. The top labeled outliers (Market Research Analysts, Computer Programmers, etc.) all fall into Unbounded or Adversarial demand types — the AI exposure accelerates their work rather than replacing the need for it.
