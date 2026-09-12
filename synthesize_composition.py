"""
synthesize_composition.py
─────────────────────────
The demand composition model — the dynamic labor equilibrium model with all
technology-exposure information removed, leaving only demand-type composition
scaled by a single economy-wide displacement rate.

It exists to test whether the Bounded/Unbounded/Adversarial taxonomy is a
*general* theory of how productivity shocks route into labor demand rather than
an AI-specific one. docs/model_vs_observed_exposure.md § "Confound: pre-existing
sector composition" records that the dynamic model's sector-level correlation was
already +0.40 to +0.50 in 2006-09, before AI, and files that as a threat to AI
attribution. If the taxonomy is general, it is instead the expected result.

Inputs:
  • data/output/occupation_exposure_report.csv  (pct_bounded/unbounded/adversarial)
  • data/output/bls_trends.csv                  (employment weights)
  • data/output/historical_displacement_rate.csv (via historical_displacement.py)

Outputs:
  • data/output/occupation_composition_model_report.csv

The model
─────────
    gross_displacement_o  = D · [(1 − BOUNDED_REBOUND)·pct_bounded_o
                               + (1 − ADVERSARIAL_REBOUND)·pct_adversarial_o]
    absorption_capacity_o = pct_unbounded_o + pct_adversarial_o
    K                     = Σ E·gross_displacement / Σ E·absorption_capacity
    net_o                 = K·absorption_capacity_o − gross_displacement_o

This is the dynamic model with the per-task penetration score p_t replaced by a
uniform economy-wide rate D. The rebound constants are imported unchanged from
synthesize_impacts.py, so the Adversarial residual-displacement term survives.
The predictor contains no technology-exposure information of any kind, which
makes it a strictly harder test than the AI model faces.

Two properties carry the argument
─────────────────────────────────
**D cancels from every cross-sectional correlation.** Because K = D·κ where κ is
a pure composition constant, net_o = D·(κ·absorption_capacity_o −
displacement_shape_o): the whole vector scales with D, and Pearson r is
scale-invariant. This is what makes the design non-circular — a single
economy-wide scalar cannot manufacture a cross-sectional pattern across 22
sectors or 770 occupations. D sets the amplitude; the taxonomy sets the shape;
only the shape is tested. tests/test_composition_model.py asserts this directly,
so it fails loudly if D ever starts carrying cross-sectional information.

**It is a distinct model, not a relabel.** Against the AI-penetration score
across 770 occupations, Pearson r = 0.759 and Spearman ρ = 0.803 — related but
substantially reordered, because stripping penetration lets occupations AI has
not yet touched re-enter with their full compositional weight (Chief Executives
has bounded_exposure_contribution = 0.0 despite pct_bounded = 0.28).

Uniform technology exposure is a deliberate assumption, and a false one: 1990s
software hit routine tasks hardest, not all tasks equally. It is the minimal
assumption that keeps the test clean. If the model fails, this is the first thing
to relax — plausibly by weighting with a Routine Task Intensity index built from
the O*NET data already on disk.

Resolution, and where the assumption shows
──────────────────────────────────────────
Because the score is a function of the composition alone, occupations sharing a
composition share a score. 239 of the 770 scored occupations — 31% — are exactly
100% Bounded, so they all sit on one floor value, and 16 are exactly 100%
Unbounded at the ceiling. The model produces 513 distinct scores against the AI
model's 560.

That is where the uniform-exposure assumption becomes visible rather than
merely stated: Drywall and Ceiling Tile Installers and Procurement Clerks
receive the identical most-negative score, because both are wholly Bounded and
the model has no way to know that software can reach the second and not the
first. The ties cost resolution and therefore statistical power; they do not
bias the correlation, since they are a property of the predictor and not of the
outcome. Any claim from this model about a specific occupation should be treated
as a claim about its composition class.
"""

import os

import pandas as pd

from synthesize_dynamic import attach_absorption_capacity, compute_dynamic_equilibrium
from synthesize_impacts import ADVERSARIAL_REBOUND, BOUNDED_REBOUND, attach_dominant_demand

OUTPUT_PATH = "data/output/occupation_composition_model_report.csv"

BOUNDED_DISPLACEMENT_COLUMN = "composition_bounded_displacement"
ADVERSARIAL_DISPLACEMENT_COLUMN = "composition_adversarial_displacement"
COMPOSITION_DISPLACEMENT_COMPONENTS = (BOUNDED_DISPLACEMENT_COLUMN, ADVERSARIAL_DISPLACEMENT_COLUMN)

COMPOSITION_PCT_COLUMNS = ("pct_bounded", "pct_unbounded", "pct_adversarial")


def compute_composition_displacement(occupation_df: pd.DataFrame, displacement_rate: float) -> pd.DataFrame:
    """Attach composition-derived displacement components scaled by the economy-wide rate.

    The rebound constants are the same structural priors the AI model uses, so the
    two differ only in what supplies the exposure term: per-task penetration there,
    a single economy-wide rate here.

    Raises on a negative rate: it would flip the sign of gross_displacement and
    invert every prediction the model makes, which is a silent catastrophe rather
    than a recoverable input error.
    """
    if displacement_rate < 0:
        raise ValueError(
            f"displacement_rate must be non-negative, got {displacement_rate}. A negative rate inverts "
            f"gross_displacement and therefore every prediction the demand composition model makes."
        )

    missing_columns = [column for column in COMPOSITION_PCT_COLUMNS if column not in occupation_df.columns]
    if missing_columns:
        raise ValueError(f"occupation frame is missing demand composition columns: {missing_columns}")

    composition_model_df = occupation_df.copy()
    composition_model_df[BOUNDED_DISPLACEMENT_COLUMN] = displacement_rate * (1.0 - BOUNDED_REBOUND) * composition_model_df["pct_bounded"]
    composition_model_df[ADVERSARIAL_DISPLACEMENT_COLUMN] = (
        displacement_rate * (1.0 - ADVERSARIAL_REBOUND) * composition_model_df["pct_adversarial"]
    )
    composition_model_df["composition_displacement_rate"] = displacement_rate
    return composition_model_df


def build_composition_model(
    occupation_df: pd.DataFrame,
    employment_col: str,
    displacement_rate: float,
) -> pd.DataFrame:
    """Run the demand composition model through the dynamic model's equilibrium.

    Reuses attach_absorption_capacity and compute_dynamic_equilibrium from
    synthesize_dynamic.py unchanged — only the displacement components differ.
    """
    composition_model_df = compute_composition_displacement(occupation_df, displacement_rate)
    composition_model_df = attach_absorption_capacity(composition_model_df)

    equilibrium_df = compute_dynamic_equilibrium(
        composition_model_df,
        employment_col,
        displacement_components=COMPOSITION_DISPLACEMENT_COMPONENTS,
    )
    equilibrium_df["composition_displacement_rate"] = displacement_rate
    return equilibrium_df


def write_composition_model(composition_model_df: pd.DataFrame, output_path: str = OUTPUT_PATH) -> None:
    """Write the model report, sorted from the largest net loser to the largest net gainer."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    composition_model_df.sort_values("net_employment_change").to_csv(output_path, index=False)


def load_composition_inputs(
    exposure_report_path: str = "data/output/occupation_exposure_report.csv",
    bls_trends_path: str = "data/output/bls_trends.csv",
) -> tuple[pd.DataFrame, str]:
    """Collapse O*NET occupations onto BLS SOC codes and attach employment weights.

    Mirrors the aggregation in validate_bls.main, but takes only the AI-free
    columns — the demand composition and the employment weight — so this model
    never reads a penetration-derived quantity. dominant_demand is re-derived
    after the collapse rather than carried, per CLAUDE.md.

    Returns the merged frame and the name of the latest employment column, which
    changes with the OEWS data vintage and so is never hardcoded.
    """
    occupation_exposure_df = pd.read_csv(exposure_report_path)
    bls_trends_df = pd.read_csv(bls_trends_path)

    occupation_exposure_df["OCC_CODE"] = occupation_exposure_df["O*NET-SOC Code"].astype(str).str.split(".").str[0]

    aggregated_exposure_df = (
        occupation_exposure_df.groupby("OCC_CODE")
        .agg({"Title": "first", "pct_bounded": "mean", "pct_unbounded": "mean", "pct_adversarial": "mean"})
        .reset_index()
    )
    aggregated_exposure_df = attach_dominant_demand(aggregated_exposure_df)

    merged_df = pd.merge(aggregated_exposure_df, bls_trends_df, on="OCC_CODE", how="inner")
    employment_col = sorted(column for column in merged_df.columns if column.startswith("TOT_EMP_"))[-1]
    return merged_df, employment_col


def synthesize(displacement_source: str | None = None) -> pd.DataFrame | None:
    """Build and write the demand composition model report.

    The displacement rate only scales the score — every cross-sectional
    correlation is invariant to it — so when no rate is available the stage still
    runs at a nominal rate and says so, rather than failing.
    """
    from historical_displacement import DEFAULT_SOURCE, economy_displacement_rate

    print("Building the demand composition model...")
    merged_df, employment_col = load_composition_inputs()

    source = displacement_source or DEFAULT_SOURCE
    displacement_rate_series = economy_displacement_rate(source)
    if displacement_rate_series is None or displacement_rate_series.empty:
        displacement_rate = 0.01
        print(f"  ⚠ No displacement rate from {source!r}; using a nominal {displacement_rate:.1%}. Correlations are unaffected.")
    else:
        displacement_rate = float(displacement_rate_series.mean())
        print(f"  Displacement rate D = {displacement_rate:.4%} (source: {source})")

    composition_model_df = build_composition_model(merged_df, employment_col, displacement_rate)
    composition_model_df["displacement_source"] = source
    write_composition_model(composition_model_df)

    net_change = composition_model_df["net_employment_change"]
    print(f"  {len(composition_model_df)} occupations scored; net change {net_change.min():+.4f} to {net_change.max():+.4f}")
    print(f"  ✓ {OUTPUT_PATH}")
    return composition_model_df


def attach_composition_dominant_demand(composition_model_df: pd.DataFrame) -> pd.DataFrame:
    """Re-derive dominant_demand after any aggregation that changed the pct_* composition.

    CLAUDE.md is explicit that dominant_demand is a summary of the composition it
    was computed from and must never be carried through an aggregation. This is a
    thin pass-through to attach_dominant_demand so callers of this module do not
    have to reach into synthesize_impacts themselves.
    """
    return attach_dominant_demand(composition_model_df)


if __name__ == "__main__":
    synthesize()
