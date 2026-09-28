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

**Read the rate measure first.** The share measure is mostly a group-size
effect: a "size" pseudo-model (`model == "employment_size_benchmark"`) reports
how well each group's plain employment share alone predicts its observed
displacement share — no model score enters it at all — and it tracks the real
models' share r closely. The rate measure divides that size effect out, so it
is the informative test and is printed, and should be read, before the share
line.

The rate form divides each group's displaced count by its CPS employment in the
year before the survey. The recall window covers three to five years, so this is
an approximation, which is why the rate is a sensitivity and not the headline.
The rate form alone also applies a proportional, missing-at-random allocation of
each survey's occupation nonresponse (gate "G6D-nonresponse" in
seeds/dws_detailed_gates.csv, via `dws_detailed_panel.nonresponse_share_by_survey`):
observed counts are scaled up by 1/(1 - that survey's nonresponse share) before
dividing by employment. The headline share measure and gate G3 stay unallocated,
the same way BLS's own published counts are never allocated.

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
from dws_detailed_panel import GATES_SEED_PATH as DWS_GATES_SEED_PATH
from dws_detailed_panel import SEED_PATH as DWS_SEED_PATH
from dws_detailed_panel import nonresponse_share_by_survey
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
SIZE_BENCHMARK_MODEL = "employment_size_benchmark"


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


def _employment_size_benchmark_correlation(observed_df: pd.DataFrame, employment_by_group: pd.Series) -> dict[str, float] | None:
    """A size-only pseudo-model: does a group's plain employment share alone predict its observed
    displacement share? No model score enters this at all — it uses the same employment
    (`group_employment`, CPS employment in the survey's prior year) the rate measure already
    computes, so it costs nothing extra to derive here."""
    merged_df = observed_df.copy()
    merged_df["employment"] = merged_df["dorn_group"].map(employment_by_group)
    merged_df = merged_df.dropna(subset=["employment"])
    if merged_df["employment"].nunique() < 2:
        return None
    merged_df["observed_share"] = merged_df["displaced_thousands"] / merged_df["displaced_thousands"].sum()
    merged_df["employment_share"] = merged_df["employment"] / merged_df["employment"].sum()
    return correlate_with_leave_one_out(merged_df.rename(columns={"dorn_group": "dws_group"}), "employment_share")


def allocate_nonresponse_for_rate(displaced_thousands: pd.Series, employment: pd.Series, nonresponse_share: float) -> pd.Series:
    """Proportional, missing-at-random allocation of occupation nonresponse — the rate measure's only.

    Scales `displaced_thousands` up by 1/(1 - nonresponse_share) before dividing by `employment`,
    as if the nonresponding share of each survey's lost-job occupations were distributed across
    groups the same way the reported share was. Applied only here (`_rate_correlation`); the
    headline share measure and gate G3 stay unallocated. A missing or out-of-range nonresponse
    share (NaN, or >= 1) leaves the counts unscaled rather than dividing by zero or a negative
    number.
    """
    inflation_factor = 1.0 / (1.0 - nonresponse_share) if pd.notna(nonresponse_share) and nonresponse_share < 1.0 else 1.0
    return (displaced_thousands * inflation_factor) / employment


def _rate_correlation(
    observed_df: pd.DataFrame, predicted_df: pd.DataFrame, employment_by_group: pd.Series, nonresponse_share: float = float("nan")
) -> dict[str, float] | None:
    merged_df = observed_df.merge(predicted_df[["dorn_group", "predicted_rate"]], on="dorn_group", how="inner")
    merged_df["observed_rate"] = allocate_nonresponse_for_rate(
        merged_df["displaced_thousands"], merged_df["dorn_group"].map(employment_by_group), nonresponse_share
    )
    merged_df = merged_df.dropna(subset=["observed_rate", "predicted_rate"])
    if len(merged_df) < MINIMUM_GROUPS or merged_df["predicted_rate"].nunique() < 2:
        return None
    pearson_r, pearson_p = stats.pearsonr(merged_df["predicted_rate"], merged_df["observed_rate"])
    spearman_r, spearman_p = stats.spearmanr(merged_df["predicted_rate"], merged_df["observed_rate"])
    return {"pearson_r": pearson_r, "pearson_p": pearson_p, "spearman_r": spearman_r, "spearman_p": spearman_p, "n_groups": len(merged_df)}


def build_detailed_displacement_comparison(
    dws_panel_df: pd.DataFrame,
    unit_scores_df: pd.DataFrame,
    panel_df: pd.DataFrame,
    groups_df: pd.DataFrame,
    nonresponse_share_by_survey_year: pd.Series | None = None,
) -> pd.DataFrame:
    """One row per (survey, model, tenure class, measure) with Pearson and Spearman r.

    `nonresponse_share_by_survey_year` (indexed by survey year, e.g. from
    `dws_detailed_panel.nonresponse_share_by_survey`) feeds only the rate measure's proportional
    nonresponse allocation (see `allocate_nonresponse_for_rate`); the share measure never sees it.
    A survey year absent from the series leaves that survey's rate measure unallocated.
    """
    nonresponse_share_by_survey_year = (
        nonresponse_share_by_survey_year if nonresponse_share_by_survey_year is not None else pd.Series(dtype=float)
    )
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
        survey_nonresponse_share = nonresponse_share_by_survey_year.get(int(survey_year), float("nan"))
        for model, predicted_df in predictions.items():
            for measure, correlations in (
                ("share", _share_correlation(observed_df, predicted_df)),
                ("rate", _rate_correlation(observed_df, predicted_df, employment_by_group, survey_nonresponse_share)),
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
        size_benchmark_correlations = _employment_size_benchmark_correlation(observed_df, employment_by_group)
        if size_benchmark_correlations is not None:
            comparison_rows.append(
                {"survey_year": int(survey_year), "model": SIZE_BENCHMARK_MODEL, "tenure_class": tenure_class, "measure": "share"}
                | {
                    column: size_benchmark_correlations.get(column, float("nan"))
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


def run(
    dws_seed_path: str = DWS_SEED_PATH, g4_passed_this_run: bool | None = None, dws_gates_path: str = DWS_GATES_SEED_PATH
) -> pd.DataFrame | None:
    """Score both models' displacement against every DWS survey at Dorn-group level.

    `g4_passed_this_run` is the caller's own fresh verdict — pass
    `cps_detailed_validation.LAST_RUN_G4_PASSED` from a `run_stage` that just ran that module in
    the same pipeline invocation. Withholds unless it is exactly True: `cps_detailed_validation`
    withholds on any failure or early return before writing `occ1990dd_bridge_check.csv`, so an
    explicit False here means the file on disk (if any) does not reflect this run and must not be
    trusted. Left at the default None when called standalone (e.g. from a shell or a notebook,
    with no fresher verdict available) — that falls back to recomputing the verdict from the
    on-disk bridge check, the same check this function has always made.

    `dws_gates_path` (`dws_detailed_panel.GATES_SEED_PATH` by default) is where the rate measure's
    per-survey nonresponse share is read from; a missing gates seed leaves the rate measure
    unallocated for every survey rather than blocking the run.
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

    if os.path.exists(dws_gates_path):
        nonresponse_share_by_survey_year = nonresponse_share_by_survey(pd.read_csv(dws_gates_path))
    else:
        warnings.warn(f"{dws_gates_path} absent — the rate measure's nonresponse allocation is skipped for every survey", stacklevel=2)
        nonresponse_share_by_survey_year = pd.Series(dtype=float)

    comparison_df = build_detailed_displacement_comparison(
        pd.read_csv(dws_seed_path),
        pd.read_csv(UNIT_SCORES_OUTPUT_PATH),
        panel_df,
        load_occ1990dd_groups(),
        nonresponse_share_by_survey_year,
    )
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    comparison_df.to_csv(OUTPUT_PATH, index=False)

    print("\n── Predicted vs measured displacement, Dorn occupation groups, every DWS survey ──")
    print("  Rate measure first — it is size-free and the informative test; the share measure below is mostly group size.")
    rate_df = comparison_df[(comparison_df["tenure_class"] == HEADLINE_TENURE_CLASS) & (comparison_df["measure"] == "rate")]
    for model, model_df in rate_df.groupby("model"):
        print(
            f"  rate   {model:<12} Pearson r {model_df['pearson_r'].min():+.3f} to {model_df['pearson_r'].max():+.3f} "
            f"(median {model_df['pearson_r'].median():+.3f}) across {len(model_df)} surveys; "
            f"{int((model_df['pearson_p'] < 0.05).sum())} individually significant; n≈{int(model_df['n_groups'].median())} needs r≈0.40"
        )

    headline_df = comparison_df[(comparison_df["tenure_class"] == HEADLINE_TENURE_CLASS) & (comparison_df["measure"] == HEADLINE_MEASURE)]
    benchmark_df = headline_df[headline_df["model"] == SIZE_BENCHMARK_MODEL]
    benchmark_median_r = benchmark_df["pearson_r"].median() if not benchmark_df.empty else float("nan")
    for model, model_df in headline_df[headline_df["model"] != SIZE_BENCHMARK_MODEL].groupby("model"):
        print(
            f"  share  {model:<12} Pearson r {model_df['pearson_r'].min():+.3f} to {model_df['pearson_r'].max():+.3f} "
            f"(median {model_df['pearson_r'].median():+.3f}) across {len(model_df)} surveys; "
            f"{int((model_df['pearson_p'] < 0.05).sum())} individually significant; n≈{int(model_df['n_groups'].median())} needs r≈0.40; "
            f"size-only benchmark median r {benchmark_median_r:+.3f} across {len(benchmark_df)} surveys"
        )
    print("  Surveys share one predicted vector, so a consistent sign is not independent evidence and is not pooled.")
    print(f"  ✓ {OUTPUT_PATH}")
    return comparison_df
