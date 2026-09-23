"""
dws_detailed_validation.py
──────────────────────────
Phase 2b of the deep history extension: each model's predicted displacement
against measured displacement per Dorn occupation group (~25 groups), one
correlation per Displaced Worker Supplement survey — the ten-group comparison in
composition_displacement_validation.py at 2.5 times the resolution.

Pinned choices (spec § Analysis choices, 2b): the headline is all-tenures
displacement as a share per group; long-tenured and the rate form are
sensitivities. Surveys are never pooled. The predicted vector — each unit's
per-occupation displacement rate through the label bridge, times its CPS
employment in the latest complete year — is identical across surveys, so a
consistent sign across surveys is not independent evidence and is never turned
into a sign test or an averaged r. At n≈25 a single survey needs r ≈ 0.40 to be
individually significant.

The rate form divides each group's displaced count by its CPS employment in the
year before the survey. The recall window covers three to five years, so this is
an approximation, which is why the rate is a sensitivity and not the headline.

Withheld, like both detailed CPS levels, when gate G4 failed: the predictions
travel through the same bridge.

Inputs:
  • seeds/dws_detailed_panel.csv, seeds/cps_detailed_occupation_panel.csv, seeds/occ1990dd_groups.csv
  • data/output/occ1990dd_scores.csv, data/output/occ1990dd_bridge_check.csv (cps_detailed_validation.py)
Outputs:
  • data/output/composition_model_displacement_validation_detailed.csv
"""

import os
import warnings

import pandas as pd
from scipy import stats

from composition_displacement_validation import MINIMUM_GROUPS, correlate_with_leave_one_out
from cps_detailed_measurement import HEADLINE_UNIVERSE, load_detailed_panel
from cps_detailed_validation import BRIDGE_CHECK_OUTPUT_PATH, UNIT_SCORES_OUTPUT_PATH
from dws_detailed_panel import SEED_PATH as DWS_SEED_PATH
from occ1990dd_reference import load_occ1990dd_groups
from occ1990dd_soc_bridge import g4_passed

OUTPUT_PATH = "data/output/composition_model_displacement_validation_detailed.csv"
OUTPUT_COLUMNS = [
    "survey_year",
    "model",
    "tenure_class",
    "measure",
    "pearson_r",
    "pearson_p",
    "spearman_r",
    "spearman_p",
    "leave_one_out_min",
    "leave_one_out_max",
    "n_groups",
]
MODEL_RATE_COLUMNS = {"composition": "composition_gross_displacement", "dynamic": "dynamic_gross_displacement"}
HEADLINE_TENURE_CLASS = "all_tenures"
HEADLINE_MEASURE = "share"
COMPLETE_YEAR_MONTHS = 12


def latest_complete_employment(panel_df: pd.DataFrame) -> pd.Series:
    """Each unit's CPS employment in the latest year with all twelve months."""
    complete_df = panel_df[(panel_df["universe"] == HEADLINE_UNIVERSE) & (panel_df["months_observed"] == COMPLETE_YEAR_MONTHS)]
    latest_df = complete_df[complete_df["year"] == complete_df["year"].max()]
    return latest_df.set_index("occ1990dd")["employed_thousands"]


def group_employment(panel_df: pd.DataFrame, groups_df: pd.DataFrame, year: int) -> pd.Series:
    """CPS employment per Dorn group in one year."""
    year_df = panel_df[(panel_df["universe"] == HEADLINE_UNIVERSE) & (panel_df["year"] == year)].merge(
        groups_df, on="occ1990dd", how="inner"
    )
    return year_df.groupby("dorn_group")["employed_thousands"].sum()


def predicted_by_group(unit_scores_df: pd.DataFrame, unit_employment: pd.Series, groups_df: pd.DataFrame, rate_column: str) -> pd.DataFrame:
    """A model's per-unit displacement rate times unit employment, summed per Dorn group, plus the implied group rate."""
    unit_df = unit_scores_df[["occ1990dd", rate_column]].dropna().merge(groups_df, on="occ1990dd", how="inner")
    unit_df = unit_df.assign(employment=unit_df["occ1990dd"].map(unit_employment)).dropna(subset=["employment"])
    unit_df["predicted_displaced"] = unit_df[rate_column] * unit_df["employment"]
    grouped_df = unit_df.groupby("dorn_group", as_index=False).agg(
        predicted_displaced=("predicted_displaced", "sum"), employment=("employment", "sum")
    )
    grouped_df["predicted_rate"] = grouped_df["predicted_displaced"] / grouped_df["employment"]
    return grouped_df


def _share_correlation(observed_df: pd.DataFrame, predicted_df: pd.DataFrame) -> dict[str, float] | None:
    merged_df = observed_df.merge(predicted_df, on="dorn_group", how="inner")
    if merged_df["predicted_displaced"].nunique() < 2:
        return None
    merged_df["observed_share"] = merged_df["displaced_thousands"] / merged_df["displaced_thousands"].sum()
    merged_df["predicted_share"] = merged_df["predicted_displaced"] / merged_df["predicted_displaced"].sum()
    return correlate_with_leave_one_out(merged_df.rename(columns={"dorn_group": "dws_group"}), "predicted_share")


def _rate_correlation(observed_df: pd.DataFrame, predicted_df: pd.DataFrame, employment_by_group: pd.Series) -> dict[str, float] | None:
    merged_df = observed_df.merge(predicted_df[["dorn_group", "predicted_rate"]], on="dorn_group", how="inner")
    merged_df["observed_rate"] = merged_df["displaced_thousands"] / merged_df["dorn_group"].map(employment_by_group)
    merged_df = merged_df.dropna(subset=["observed_rate", "predicted_rate"])
    if len(merged_df) < MINIMUM_GROUPS or merged_df["predicted_rate"].nunique() < 2:
        return None
    pearson_r, pearson_p = stats.pearsonr(merged_df["predicted_rate"], merged_df["observed_rate"])
    spearman_r, spearman_p = stats.spearmanr(merged_df["predicted_rate"], merged_df["observed_rate"])
    return {"pearson_r": pearson_r, "pearson_p": pearson_p, "spearman_r": spearman_r, "spearman_p": spearman_p, "n_groups": len(merged_df)}


def build_detailed_displacement_comparison(
    dws_panel_df: pd.DataFrame, unit_scores_df: pd.DataFrame, panel_df: pd.DataFrame, groups_df: pd.DataFrame
) -> pd.DataFrame:
    """One row per (survey, model, tenure class, measure) with Pearson and Spearman r."""
    unit_employment = latest_complete_employment(panel_df)
    predictions = {
        model: predicted_by_group(unit_scores_df, unit_employment, groups_df, rate_column)
        for model, rate_column in MODEL_RATE_COLUMNS.items()
        if rate_column in unit_scores_df.columns
    }
    comparison_rows = []
    for (survey_year, tenure_class), observed_df in dws_panel_df.groupby(["survey_year", "tenure_class"]):
        observed_df = observed_df[["dorn_group", "displaced_thousands"]]
        employment_by_group = group_employment(panel_df, groups_df, int(survey_year) - 1)
        for model, predicted_df in predictions.items():
            for measure, correlations in (
                ("share", _share_correlation(observed_df, predicted_df)),
                ("rate", _rate_correlation(observed_df, predicted_df, employment_by_group)),
            ):
                if correlations is None:
                    continue
                comparison_rows.append(
                    {"survey_year": int(survey_year), "model": model, "tenure_class": tenure_class, "measure": measure}
                    | {
                        column: correlations.get(column, float("nan"))
                        for column in (
                            "pearson_r",
                            "pearson_p",
                            "spearman_r",
                            "spearman_p",
                            "leave_one_out_min",
                            "leave_one_out_max",
                            "n_groups",
                        )
                    }
                )
    return pd.DataFrame(comparison_rows, columns=OUTPUT_COLUMNS)


def run(dws_seed_path: str = DWS_SEED_PATH, g4_passed_this_run: bool | None = None) -> pd.DataFrame | None:
    """Score both models' displacement against every DWS survey at Dorn-group level.

    `g4_passed_this_run` is the caller's own fresh verdict — pass
    `cps_detailed_validation.LAST_RUN_G4_PASSED` from a `run_stage` that just ran that module in
    the same pipeline invocation. Withholds unless it is exactly True: `cps_detailed_validation`
    withholds on any failure or early return before writing `occ1990dd_bridge_check.csv`, so an
    explicit False here means the file on disk (if any) does not reflect this run and must not be
    trusted. Left at the default None when called standalone (e.g. from a shell or a notebook,
    with no fresher verdict available) — that falls back to recomputing the verdict from the
    on-disk bridge check, the same check this function has always made.
    """
    if not os.path.exists(dws_seed_path):
        warnings.warn(
            f"{dws_seed_path} absent — built locally from IPUMS (dws_detailed_panel.py); detailed DWS validation skipped", stacklevel=2
        )
        return None
    panel_df = load_detailed_panel()
    if panel_df is None or not os.path.exists(UNIT_SCORES_OUTPUT_PATH):
        warnings.warn("The detailed CPS panel or occ1990dd scores are absent; detailed DWS validation skipped", stacklevel=2)
        return None
    if g4_passed_this_run is False:
        warnings.warn(
            "Gate G4 did not pass in this run; detailed DWS validation withheld rather than trusting a possibly stale "
            "occ1990dd_bridge_check.csv from an earlier run",
            stacklevel=2,
        )
        return None
    if g4_passed_this_run is None and (
        not os.path.exists(BRIDGE_CHECK_OUTPUT_PATH) or not g4_passed(pd.read_csv(BRIDGE_CHECK_OUTPUT_PATH))
    ):
        warnings.warn(
            "Gate G4 has not passed; detailed DWS validation withheld, since its predictions travel through the bridge", stacklevel=2
        )
        return None

    comparison_df = build_detailed_displacement_comparison(
        pd.read_csv(dws_seed_path), pd.read_csv(UNIT_SCORES_OUTPUT_PATH), panel_df, load_occ1990dd_groups()
    )
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    comparison_df.to_csv(OUTPUT_PATH, index=False)

    print("\n── Predicted vs measured displacement, Dorn occupation groups, every DWS survey ──")
    headline_df = comparison_df[(comparison_df["tenure_class"] == HEADLINE_TENURE_CLASS) & (comparison_df["measure"] == HEADLINE_MEASURE)]
    for model, model_df in headline_df.groupby("model"):
        print(
            f"  {model:<12} Pearson r {model_df['pearson_r'].min():+.3f} to {model_df['pearson_r'].max():+.3f} "
            f"(median {model_df['pearson_r'].median():+.3f}) across {len(model_df)} surveys; "
            f"{int((model_df['pearson_p'] < 0.05).sum())} individually significant; n≈{int(model_df['n_groups'].median())} needs r≈0.40"
        )
    print("  Surveys share one predicted vector, so a consistent sign is not independent evidence and is not pooled.")
    print(f"  ✓ {OUTPUT_PATH}")
    return comparison_df
