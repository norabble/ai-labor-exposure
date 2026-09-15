"""
composition_era_validation.py
─────────────────────────────
The headline test of the demand composition model: is the Bounded/Unbounded/
Adversarial signal era-invariant, or does it only appear after AI?

Runs the sector-level validation for every year-over-year period 1999→2025 for
four scores side by side, then compares the pre-2022 and AI-era means:

  composition_net_change   demand composition only — no technology data at all
  net_employment_change    the AI-penetration dynamic model
  occupation_exposure      the rebound-adjusted model
  observed_exposure        Anthropic observed task coverage, when available

Inputs:
  • data/output/occupation_composition_model_report.csv
  • data/output/occupation_dynamic_model_report.csv
  • data/output/bls_trends.csv
  • data/output/bls_sector_trends.csv
  • data/raw/anthropic_job_exposure.csv  (optional)

Outputs:
  • data/output/composition_model_era_comparison.csv
  • data/output/visualizations/composition_model_signal_over_time.png

How to read the result
──────────────────────
docs/model_vs_observed_exposure.md § "Confound: pre-existing sector composition"
records that the AI model's sector-level r was already +0.40 to +0.50 in 2006-09
and files that as a threat to AI attribution. This module tests the opposite
reading. Three outcomes, all publishable:

  • composition-only fits the pre-AI era as well as the AI era → the taxonomy is
    a general theory of productivity-shock pass-through, and AI is one instance.
  • the AI model pulls ahead only after 2022 → there is a real, separable
    AI-specific increment on top of the general effect.
  • the AI model never pulls ahead → the AI-specific claim is weak and the honest
    headline is that this was always a general theory.

Two caveats that bound every number here
─────────────────────────────────────────
**The demand-type labels are from 2025 O*NET task statements, applied
backwards.** docs/framework.md already flags this. Occupational task content
genuinely changed over 1999-2025, so the further back a period sits, the more
anachronistic its labels. Reaching further back buys statistical power at the
cost of construct validity.

**The era test is badly under-powered on the AI side.** There are only three
AI-era YoY periods against twenty-one pre-AI ones, and the periods are
autocorrelated, so the Welch test on Fisher-z transformed correlations reported
here should be read as a descriptive comparison rather than an inferential
result. A non-significant difference is the expected outcome either way and is
not evidence of equivalence.

Sector growth always comes from the major-group totals in bls_sector_trends.csv
via sector_growth_series, never from the survivor occupations — detailed
pre-2019 codes lose 97% of Computer and Mathematical employment, per CLAUDE.md.
"""

import os
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.stats as stats
import seaborn as sns

# _sector_weighted_means is imported rather than reimplemented so this module and
# every existing sector-level chart aggregate identically. Duplicating it would
# let the two drift and report different numbers for the same quantity.
from synthesize_dynamic import _sector_weighted_means

COMPOSITION_REPORT_PATH = "data/output/occupation_composition_model_report.csv"
DYNAMIC_REPORT_PATH = "data/output/occupation_dynamic_model_report.csv"
BLS_TRENDS_PATH = "data/output/bls_trends.csv"
SECTOR_TRENDS_PATH = "data/output/bls_sector_trends.csv"
ANTHROPIC_EXPOSURE_PATH = "data/raw/anthropic_job_exposure.csv"

OUTPUT_PATH = "data/output/composition_model_era_comparison.csv"
CHART_NAME = "composition_model_signal_over_time.png"

# Occupation-level twin of every sector output. Written to separate files rather
# than adding a `level` column, so the sector outputs stay byte-identical and no
# doc can quote a figure without saying which level it came from.
HARMONIZED_TRENDS_PATH = "data/output/bls_harmonized_trends.csv"
UNIT_MEMBERSHIP_PATH = "data/output/soc_harmonization_units.csv"
OCCUPATION_OUTPUT_PATH = "data/output/composition_model_era_comparison_occupation.csv"
OCCUPATION_CYCLE_OUTPUT_PATH = "data/output/composition_cycle_decomposition_occupation.csv"
OCCUPATION_CHART_NAME = "composition_model_signal_over_time_occupation.png"

COMPOSITION_SCORE_COLUMN = "composition_net_change"

# Sign convention differs by score: the gross exposure measures validate with
# negative r (more exposure → less growth) while the redistribution models
# validate with positive r (more net change → more growth).
SCORE_CONFIGS: list[tuple[str, str, str, str]] = [
    (COMPOSITION_SCORE_COLUMN, "Demand composition only (+r = correct)", "#6a51a3", "D"),
    ("net_employment_change", "Dynamic, AI penetration (+r = correct)", "darkorange", "s"),
    ("occupation_exposure", "Rebound-adjusted (−r = correct)", "steelblue", "o"),
    ("observed_exposure", "Observed AI coverage (−r = correct)", "seagreen", "^"),
]

# Periods whose later year is <= 2022 carry the hist_ prefix; see analyze_bls.py.
AI_ERA_FIRST_PERIOD = "2022_2023"

MINIMUM_SECTORS = 5
MINIMUM_OCCUPATIONS = 10
# Occupation level has hundreds of units; require enough that a correlation means something.
MINIMUM_UNITS = 20

COVID_PERIODS = ("2019_2020", "2020_2021")

OUTPUT_COLUMNS = [
    "score",
    "era",
    "n_periods",
    "mean_r",
    "min_r",
    "max_r",
    "n_significant",
    "era_difference_r",
    "welch_t",
    "welch_p",
]


def period_key(growth_column: str) -> str:
    """Strip the prefix from a growth column, leaving e.g. '2018_2019'."""
    return growth_column.replace("hist_emp_growth_", "").replace("emp_growth_", "")


def _period_sort_key(growth_column: str) -> tuple[int, int]:
    key = period_key(growth_column)
    if key == "composite" or key.startswith("pre_ai"):
        return (9999, 9999)
    start_year, end_year = key.split("_")
    return (int(start_year), int(end_year))


def discover_period_columns(trends_df: pd.DataFrame) -> list[str]:
    """Every year-over-year employment growth column, chronologically.

    Excludes the composite and pre_ai aggregates, which span many years and would
    not be a period in the series.
    """
    historical_columns = [column for column in trends_df.columns if column.startswith("hist_emp_growth_") and "_pre_ai" not in column]
    current_columns = [column for column in trends_df.columns if column.startswith("emp_growth_") and "composite" not in column]
    return sorted(historical_columns, key=_period_sort_key) + sorted(current_columns, key=_period_sort_key)


def is_ai_era(growth_column: str) -> bool:
    """True for periods from 2022→23 onward."""
    return _period_sort_key(growth_column) >= _period_sort_key(f"emp_growth_{AI_ERA_FIRST_PERIOD}")


def load_scored_occupations() -> tuple[pd.DataFrame, str, pd.DataFrame | None, list[str]]:
    """Join every model score onto the BLS trend series, keyed by SOC code.

    Returns the joined frame, the latest employment column, the sector growth
    table, and the score columns actually present.
    """
    composition_df = pd.read_csv(COMPOSITION_REPORT_PATH)
    dynamic_df = pd.read_csv(DYNAMIC_REPORT_PATH)
    trends_df = pd.read_csv(BLS_TRENDS_PATH)

    scored_df = composition_df[["OCC_CODE", "net_employment_change"]].rename(columns={"net_employment_change": COMPOSITION_SCORE_COLUMN})
    scored_df = scored_df.merge(
        dynamic_df[["OCC_CODE", "net_employment_change", "occupation_exposure"]],
        on="OCC_CODE",
        how="outer",
        validate="one_to_one",
    )

    if os.path.exists(ANTHROPIC_EXPOSURE_PATH):
        anthropic_df = pd.read_csv(ANTHROPIC_EXPOSURE_PATH)
        if "occ_code" in anthropic_df.columns:
            anthropic_df = anthropic_df.rename(columns={"occ_code": "OCC_CODE"})
        if "observed_exposure" in anthropic_df.columns:
            observed_df = anthropic_df[["OCC_CODE", "observed_exposure"]].drop_duplicates(subset=["OCC_CODE"])
            scored_df = scored_df.merge(observed_df, on="OCC_CODE", how="left")

    scored_df = scored_df.merge(trends_df, on="OCC_CODE", how="inner")
    scored_df["soc_major"] = scored_df["OCC_CODE"].astype(str).str[:2]

    employment_col = sorted(column for column in scored_df.columns if column.startswith("TOT_EMP_"))[-1]

    sector_growth_df = None
    if os.path.exists(SECTOR_TRENDS_PATH):
        sector_growth_df = pd.read_csv(SECTOR_TRENDS_PATH, dtype={"soc_major": str}).set_index("soc_major")

    present_score_columns = [score_col for score_col, _, _, _ in SCORE_CONFIGS if score_col in scored_df.columns]
    return scored_df, employment_col, sector_growth_df, present_score_columns


def sector_correlation(
    scored_df: pd.DataFrame,
    score_col: str,
    growth_col: str,
    employment_col: str,
    sector_growth_df: pd.DataFrame | None,
) -> tuple[float, float, int] | None:
    """Sector-level Pearson r between one score and one period's growth, or None if too thin."""
    subset_df = scored_df[[score_col, growth_col, "soc_major", employment_col]].dropna()
    if len(subset_df) < MINIMUM_OCCUPATIONS:
        return None

    sector_means_df = _sector_weighted_means(subset_df, score_col, growth_col, employment_col, "soc_major", sector_growth_df)
    if len(sector_means_df) < MINIMUM_SECTORS:
        return None

    correlation, p_value = stats.pearsonr(sector_means_df["sector_score"], sector_means_df["sector_growth"])
    return correlation, p_value, len(sector_means_df)


def load_harmonized_inputs() -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """The harmonized unit trend series and unit membership, or None with a warning if absent.

    Both files are written by analyze_bls.py via harmonize_soc.py. They are
    optional here for the same reason the sector growth table is: a missing file
    degrades the occupation-level pass rather than failing the whole stage.
    """
    missing = [path for path in (HARMONIZED_TRENDS_PATH, UNIT_MEMBERSHIP_PATH) if not os.path.exists(path)]
    if missing:
        warnings.warn(f"Occupation-level pass skipped; missing {missing}", stacklevel=2)
        return None
    harmonized_trends_df = pd.read_csv(HARMONIZED_TRENDS_PATH)
    unit_membership_df = pd.read_csv(UNIT_MEMBERSHIP_PATH, dtype={"year": str})
    return harmonized_trends_df, unit_membership_df


def occupation_correlation(
    scored_df: pd.DataFrame,
    score_col: str,
    growth_col: str,
    employment_col: str,
    harmonized_trends_df: pd.DataFrame,
    unit_membership_df: pd.DataFrame,
) -> tuple[float, float, int] | None:
    """Occupation-level Pearson r on harmonized SOC units, or None if too thin.

    The unit is the unit of observation, not the OEWS code: scores are the
    employment-weighted mean over a unit's 2022 members, so the same occupation
    definitions carry every period instead of moving with SOC survivorship.

    Returns None when fewer than MINIMUM_UNITS units carry both a score and a
    growth value, and when the score has no variance across units — the demand
    composition score is a function of composition alone, so a period can
    legitimately arrive with every unit tied.
    """
    from validate_bls import build_unit_scores

    if growth_col not in harmonized_trends_df.columns:
        return None

    unit_scores_df = build_unit_scores(scored_df, unit_membership_df, employment_col, [score_col])
    paired_df = unit_scores_df.merge(harmonized_trends_df[["unit_id", growth_col]], on="unit_id", how="inner")
    paired_df = paired_df[[score_col, growth_col]].dropna()
    if len(paired_df) < MINIMUM_UNITS:
        return None
    if paired_df[score_col].nunique() < 2 or paired_df[growth_col].nunique() < 2:
        return None

    correlation, p_value = stats.pearsonr(paired_df[score_col], paired_df[growth_col])
    return correlation, p_value, len(paired_df)


def build_period_correlations(
    scored_df: pd.DataFrame,
    employment_col: str,
    sector_growth_df: pd.DataFrame | None,
    score_columns: list[str],
) -> pd.DataFrame:
    """One row per (period, score) with the sector-level r, p and sector count."""
    correlation_rows = []
    for growth_col in discover_period_columns(scored_df):
        for score_col in score_columns:
            result = sector_correlation(scored_df, score_col, growth_col, employment_col, sector_growth_df)
            if result is None:
                continue
            correlation, p_value, n_sectors = result
            correlation_rows.append(
                {
                    "period": period_key(growth_col),
                    "score": score_col,
                    "fit_r": correlation,
                    "fit_p": p_value,
                    "n_units": n_sectors,
                    "era": "ai" if is_ai_era(growth_col) else "pre_ai",
                    "is_covid": period_key(growth_col) in COVID_PERIODS,
                }
            )
    return pd.DataFrame(correlation_rows)


def build_occupation_period_correlations(
    scored_df: pd.DataFrame,
    employment_col: str,
    harmonized_trends_df: pd.DataFrame,
    unit_membership_df: pd.DataFrame,
    score_columns: list[str],
) -> pd.DataFrame:
    """One row per (period, score) with the occupation-level r, p and unit count.

    Same frame shape as build_period_correlations, so summarise_eras,
    decompose_fit_strength and correlate_with_displacement_rate consume it
    unchanged. Periods are discovered from the harmonized trend file, whose
    growth columns carry the same names as the occupation-level trend file.
    """
    correlation_rows = []
    for growth_col in discover_period_columns(harmonized_trends_df):
        for score_col in score_columns:
            result = occupation_correlation(scored_df, score_col, growth_col, employment_col, harmonized_trends_df, unit_membership_df)
            if result is None:
                continue
            correlation, p_value, n_units = result
            correlation_rows.append(
                {
                    "period": period_key(growth_col),
                    "score": score_col,
                    "fit_r": correlation,
                    "fit_p": p_value,
                    "n_units": n_units,
                    "era": "ai" if is_ai_era(growth_col) else "pre_ai",
                    "is_covid": period_key(growth_col) in COVID_PERIODS,
                }
            )
    return pd.DataFrame(correlation_rows)


CPS_GROUP_TRENDS_PATH = "data/output/cps_group_trends.csv"
# Ten groups total; require most of them present before a correlation means anything.
MINIMUM_CPS_GROUPS = 8

# CPS-level twin of every sector/occupation output. Written to separate files rather
# than adding a `level` column, so the sector outputs stay byte-identical.
CPS_OUTPUT_PATH = "data/output/composition_model_era_comparison_cps.csv"
CPS_CYCLE_OUTPUT_PATH = "data/output/composition_cycle_decomposition_cps.csv"
CPS_CHART_NAME = "composition_model_signal_over_time_cps.png"


def cps_group_correlation(
    scored_df: pd.DataFrame,
    score_col: str,
    growth_col: str,
    employment_col: str,
    cps_trends_df: pd.DataFrame,
) -> tuple[float, float, int] | None:
    """Pearson r between a model score and CPS growth across the ten occupation groups.

    Model scores are aggregated to the CPS groups employment-weighted, using the
    same SOC-major lookup the DWS displacement validation uses, so the taxonomy is
    shared rather than re-derived. Returns None when fewer than MINIMUM_CPS_GROUPS
    groups carry both a score and a growth value.
    """
    from composition_displacement_validation import soc_major_to_dws_group

    if growth_col not in cps_trends_df.columns:
        return None

    group_lookup = soc_major_to_dws_group()
    aggregation_df = scored_df.dropna(subset=[score_col, employment_col]).copy()
    aggregation_df["cps_group"] = aggregation_df["OCC_CODE"].astype(str).str[:2].map(group_lookup)
    aggregation_df = aggregation_df.dropna(subset=["cps_group"])
    if aggregation_df.empty:
        return None

    weighted_df = aggregation_df.assign(weighted_score=aggregation_df[score_col] * aggregation_df[employment_col])
    group_scores_df = (
        weighted_df.groupby("cps_group")
        .agg(weighted_score=("weighted_score", "sum"), group_employment=(employment_col, "sum"))
        .reset_index()
    )
    group_scores_df["group_score"] = group_scores_df["weighted_score"] / group_scores_df["group_employment"]

    paired_df = group_scores_df.merge(cps_trends_df[["cps_group", growth_col]], on="cps_group", how="inner")
    paired_df = paired_df[["group_score", growth_col]].dropna()
    if len(paired_df) < MINIMUM_CPS_GROUPS:
        return None
    if paired_df["group_score"].nunique() < 2 or paired_df[growth_col].nunique() < 2:
        return None

    correlation, p_value = stats.pearsonr(paired_df["group_score"], paired_df[growth_col])
    return correlation, p_value, len(paired_df)


def build_cps_period_correlations(
    scored_df: pd.DataFrame,
    employment_col: str,
    cps_trends_df: pd.DataFrame,
    score_columns: list[str],
) -> pd.DataFrame:
    """One row per (period, score) on the CPS instrument, in the shared frame shape."""
    correlation_rows = []
    for growth_col in discover_period_columns(cps_trends_df):
        for score_col in score_columns:
            result = cps_group_correlation(scored_df, score_col, growth_col, employment_col, cps_trends_df)
            if result is None:
                continue
            correlation, p_value, n_groups = result
            correlation_rows.append(
                {
                    "period": period_key(growth_col),
                    "score": score_col,
                    "fit_r": correlation,
                    "fit_p": p_value,
                    "n_units": n_groups,
                    "era": "ai" if is_ai_era(growth_col) else "pre_ai",
                    "is_covid": period_key(growth_col) in COVID_PERIODS,
                }
            )
    return pd.DataFrame(correlation_rows)


def summarise_eras(period_correlation_df: pd.DataFrame, exclude_covid: bool = True) -> pd.DataFrame:
    """Compare pre-2022 and AI-era correlations per score.

    Correlations are Fisher z-transformed before averaging and testing, because r
    is bounded and its sampling distribution is skewed. The Welch test does not
    assume equal variances, which matters when one era has 16 periods and the
    other 3.

    COVID periods are excluded by default: 2019→20 and 2020→21 are dominated by
    shutdown and rehiring, not by any displacement mechanism this model describes.
    """
    comparison_df = period_correlation_df[~period_correlation_df["is_covid"]] if exclude_covid else period_correlation_df

    summary_rows = []
    for score_col in comparison_df["score"].unique():
        score_df = comparison_df[comparison_df["score"] == score_col]
        pre_ai_r = score_df.loc[score_df["era"] == "pre_ai", "fit_r"]
        ai_era_r = score_df.loc[score_df["era"] == "ai", "fit_r"]

        era_difference = welch_t = welch_p = np.nan
        if len(pre_ai_r) >= 2 and len(ai_era_r) >= 2:
            pre_ai_z, ai_era_z = np.arctanh(pre_ai_r), np.arctanh(ai_era_r)
            welch_t, welch_p = stats.ttest_ind(ai_era_z, pre_ai_z, equal_var=False)
            era_difference = float(np.tanh(ai_era_z.mean()) - np.tanh(pre_ai_z.mean()))

        for era_name, era_r in (("pre_ai", pre_ai_r), ("ai", ai_era_r)):
            if era_r.empty:
                continue
            era_p = score_df.loc[score_df["era"] == era_name, "fit_p"]
            summary_rows.append(
                {
                    "score": score_col,
                    "era": era_name,
                    "n_periods": len(era_r),
                    # Averaged in z space then transformed back, not averaged in r space.
                    "mean_r": float(np.tanh(np.arctanh(era_r).mean())),
                    "min_r": float(era_r.min()),
                    "max_r": float(era_r.max()),
                    "n_significant": int((era_p < 0.05).sum()),
                    "era_difference_r": era_difference,
                    "welch_t": float(welch_t) if not np.isnan(welch_t) else np.nan,
                    "welch_p": float(welch_p) if not np.isnan(welch_p) else np.nan,
                }
            )

    return pd.DataFrame(summary_rows)[OUTPUT_COLUMNS]


UNEMPLOYMENT_SERIES_ID = "LNS14000000"
UNEMPLOYMENT_SERIES_START_YEAR = 1948  # LNS14000000's own start; never needs revisiting if the series extends further back.

CYCLE_OUTPUT_PATH = "data/output/composition_cycle_decomposition.csv"
CYCLE_OUTPUT_COLUMNS = ["score", "term", "coefficient", "std_error", "t_statistic", "p_value", "n_periods", "r_squared"]


def unemployment_change_by_period(period_keys: list[str]) -> pd.Series | None:
    """Change in the annual mean unemployment rate across each period, e.g. '2007_2008' → +1.18."""
    from historical_displacement import fetch_annual_means

    unemployment_rate = fetch_annual_means(UNEMPLOYMENT_SERIES_ID, UNEMPLOYMENT_SERIES_START_YEAR, 2026)
    if unemployment_rate is None:
        return None

    change_by_period = {}
    for key in period_keys:
        start_year, end_year = (int(part) for part in key.split("_"))
        if start_year in unemployment_rate.index and end_year in unemployment_rate.index:
            change_by_period[key] = unemployment_rate[end_year] - unemployment_rate[start_year]
    return pd.Series(change_by_period, name="unemployment_change")


def decompose_fit_strength(
    period_correlation_df: pd.DataFrame,
    unemployment_change: pd.Series,
    exclude_covid: bool = True,
) -> pd.DataFrame:
    """Regress each model's per-period fit strength on the business cycle and an AI-era dummy.

    The era comparison on its own cannot separate two explanations of a pre-AI
    signal: that the taxonomy describes a general mechanism, or that it is picking
    up cyclical sorting — Bounded and clerical work is shed in downturns and
    rehired in recoveries, which docs/framework.md § "Future investigation: the
    business cycle" already suspected.

    Regressing Fisher-z fit strength on the change in unemployment plus an AI-era
    indicator separates them:

      intercept    the taxonomy's signal at zero cyclical movement — a general,
                   non-cyclical baseline if it is positive
      change in U  how much of the fit is cyclical sorting
      AI era       whatever remains specific to 2022 onward once the cycle is
                   accounted for

    COVID periods are excluded by default; they are shutdown and rehiring rather
    than any mechanism the model describes, and they dominate the cycle term.
    """
    comparison_df = period_correlation_df[~period_correlation_df["is_covid"]] if exclude_covid else period_correlation_df

    coefficient_rows = []
    for score_col in comparison_df["score"].unique():
        score_df = comparison_df[comparison_df["score"] == score_col].copy()
        score_df["unemployment_change"] = score_df["period"].map(unemployment_change)
        score_df = score_df.dropna(subset=["unemployment_change", "fit_r"])

        term_names = ["intercept", "unemployment_change", "ai_era"]
        if len(score_df) <= len(term_names):
            continue

        fit_strength = np.arctanh(score_df["fit_r"].to_numpy())
        design_matrix = np.column_stack(
            [
                np.ones(len(score_df)),
                score_df["unemployment_change"].to_numpy(),
                (score_df["era"] == "ai").astype(float).to_numpy(),
            ]
        )

        # With every period in one era the AI-era column is constant and the normal
        # equations are singular, which would raise rather than degrade. That happens
        # for real whenever the trend series has not reached 2022 yet.
        if np.linalg.matrix_rank(design_matrix) < design_matrix.shape[1]:
            warnings.warn(
                f"Cannot decompose fit strength for {score_col}: the periods do not span both eras "
                f"(or the cycle term is constant), so the AI-era effect is not identified.",
                stacklevel=2,
            )
            continue

        coefficients, *_ = np.linalg.lstsq(design_matrix, fit_strength, rcond=None)
        residuals = fit_strength - design_matrix @ coefficients
        degrees_of_freedom = len(score_df) - design_matrix.shape[1]
        residual_variance = np.sum(residuals**2) / degrees_of_freedom
        standard_errors = np.sqrt(residual_variance * np.diag(np.linalg.inv(design_matrix.T @ design_matrix)))
        t_statistics = coefficients / standard_errors
        p_values = 2 * (1 - stats.t.cdf(np.abs(t_statistics), degrees_of_freedom))
        total_sum_of_squares = np.sum((fit_strength - fit_strength.mean()) ** 2)

        for term_name, coefficient, standard_error, t_statistic, p_value in zip(
            term_names, coefficients, standard_errors, t_statistics, p_values
        ):
            coefficient_rows.append(
                {
                    "score": score_col,
                    "term": term_name,
                    "coefficient": float(coefficient),
                    "std_error": float(standard_error),
                    "t_statistic": float(t_statistic),
                    "p_value": float(p_value),
                    "n_periods": len(score_df),
                    "r_squared": float(1 - np.sum(residuals**2) / total_sum_of_squares),
                }
            )

    return pd.DataFrame(coefficient_rows, columns=CYCLE_OUTPUT_COLUMNS)


DISPLACEMENT_RATE_TRACKING_SOURCES = ("productivity", "dws_long_tenured", "mlr_long_tenured")

TRACKING_OUTPUT_COLUMNS = [
    "score",
    "pearson_r",
    "pearson_p",
    "n_periods",
    "n_distinct_displacement_values",
    "displacement_vs_year_r",
    "displacement_vs_year_p",
]


def displacement_rate_time_trend(displacement_rate: pd.Series) -> tuple[int, float, float]:
    """Measure, rather than assert, how much of a displacement-rate source is just calendar time.

    Returns `(n_distinct_values, year_trend_r, year_trend_p)`: how many distinct
    annual values the series actually carries (a DWS or MLR source repeats one
    survey-window or article-period average across every year it covers, so a
    21-year series can carry far fewer independent readings than its length
    suggests — the effective sample size `correlate_with_displacement_rate`'s own
    p-values assume is overstated by roughly that ratio), and the Pearson
    correlation of the series against its own calendar year (a source that is
    largely monotonic in time is not distinguishable, by this test alone, from "fit
    strength changed over time" for any other reason — including the AI-era
    boundary, which is itself a fixed point in calendar time). `year_trend_r`/`_p`
    are `nan` when fewer than 3 points are available, since a two-point
    correlation is undefined in any informative sense.

    This is the same measure-and-disclose treatment `cps_historical_panel.py`'s
    `measure_comparability_breaks` already gives the CPS series' two classification
    breaks: quantified and attached to the output, not just described in prose.
    """
    n_distinct_values = int(displacement_rate.nunique())
    if len(displacement_rate) < 3:
        return n_distinct_values, float("nan"), float("nan")
    year_trend_r, year_trend_p = stats.pearsonr(displacement_rate.index.values.astype(float), displacement_rate.values)
    return n_distinct_values, float(year_trend_r), float(year_trend_p)


def correlate_with_displacement_rate(
    period_correlation_df: pd.DataFrame, exclude_covid: bool = True, source: str = "productivity"
) -> pd.DataFrame:
    """Does each model's fit strength track the economy-wide displacement rate itself?

    The prediction from docs/framework.md § Future investigation: the business
    cycle is that periods of greater displacement show stronger demand-type
    sorting. Three D sources are available now (historical_displacement.DISPLACEMENT_SOURCES):
    smoothed productivity growth has annual coverage back to 1947; dws_long_tenured
    varies annually across 2005-2025 now that the DWS panel holds ten archived
    surveys rather than one repeated rate; and mlr_long_tenured, built from the
    pre-2008 Monthly Labor Review articles, varies across 1981-2000. `source` selects
    which of the three this call uses — `productivity` is the default so existing
    callers see no change in behaviour. dws_long_tenured and mlr_long_tenured are
    never combined into one series (see historical_displacement.mlr_displacement_rate);
    each is tested separately, one call per source.

    This is a weak test by construction, and not only for the "few autocorrelated
    periods" reason stated below: for the DWS/MLR sources, the regressor itself
    repeats one survey-window or article-period average across every year the
    window covers, so the number of *periods* this function reports is not the
    number of *independent* displacement readings — `displacement_rate_time_trend`
    measures that gap directly (`n_distinct_displacement_values` in the output) so
    a reader does not have to take "roughly two dozen usable periods" at face
    value. The same helper also reports `displacement_vs_year_r`/`_p`: the
    correlation of the source against calendar year alone. Where that is large,
    a fit-strength correlation against the source cannot be distinguished from a
    fit-strength trend against time itself — see docs/framework.md § Demand
    Composition Model for what this means for `dws_long_tenured` specifically,
    where the confound is large enough to make the test's own significant result
    uninformative about displacement rather than merely weak evidence for it.

    It is reported as a hypothesis check; a null result is expected and
    uninformative, not disconfirming, per this project's asymmetric reading rule —
    and, as the above makes explicit, so is a positive result confounded with time.
    """
    from historical_displacement import economy_displacement_rate

    # PRS85006092 begins in 1947, so fetching from 1997 costs nothing and gives the
    # earliest period this test uses (1999_2000, which maps to displacement year 2000)
    # a full centered 3-year window instead of an edge-truncated one for the
    # productivity source. Matches the unemployment lookup's own widening
    # (LNS14000000, see UNEMPLOYMENT_SERIES_START_YEAR above) so both business-cycle
    # covariates see the same 1999-2025 span. The dws_long_tenured and mlr_long_tenured
    # sources ignore whichever part of this start year predates their own coverage.
    displacement_rate = economy_displacement_rate(source, start_year=1997)
    if displacement_rate is None or displacement_rate.empty:
        return pd.DataFrame(columns=TRACKING_OUTPUT_COLUMNS)

    n_distinct_displacement_values, displacement_vs_year_r, displacement_vs_year_p = displacement_rate_time_trend(displacement_rate)

    comparison_df = period_correlation_df[~period_correlation_df["is_covid"]] if exclude_covid else period_correlation_df

    correlation_rows = []
    for score_col in comparison_df["score"].unique():
        score_df = comparison_df[comparison_df["score"] == score_col].copy()
        score_df["displacement_rate"] = score_df["period"].map(lambda key: displacement_rate.get(int(key.split("_")[1]), float("nan")))
        score_df = score_df.dropna(subset=["displacement_rate", "fit_r"])
        if len(score_df) < 5:
            continue
        correlation, p_value = stats.pearsonr(np.arctanh(score_df["fit_r"]), score_df["displacement_rate"])
        correlation_rows.append(
            {
                "score": score_col,
                "pearson_r": float(correlation),
                "pearson_p": float(p_value),
                "n_periods": len(score_df),
                "n_distinct_displacement_values": n_distinct_displacement_values,
                "displacement_vs_year_r": displacement_vs_year_r,
                "displacement_vs_year_p": displacement_vs_year_p,
            }
        )

    return pd.DataFrame(correlation_rows, columns=TRACKING_OUTPUT_COLUMNS)


def print_displacement_rate_tracking(tracking_df: pd.DataFrame, source: str) -> None:
    """Print whether fit strength tracks the named economy-wide displacement rate source.

    Prints a skip message, rather than nothing, when a source could not be tested —
    either because the source itself is entirely unavailable, or because fewer than
    5 usable periods overlap it — so an absent source is visibly accounted for
    rather than silently missing from the output.

    Prints the source's own time-trend diagnostic (`displacement_rate_time_trend`,
    carried on every row as `n_distinct_displacement_values` /
    `displacement_vs_year_r` / `_p`) right beside the correlation it qualifies,
    rather than leaving a reader to take the reported `n_periods` at face value or
    to rediscover separately that a source is highly correlated with calendar year.
    """
    print(f"\n── Does fit strength track the economy-wide displacement rate? ({source}) ──")
    if tracking_df.empty:
        print(f"  Skipped: {source} has fewer than 5 usable periods overlapping this level's data.")
        return
    diagnostic_row = tracking_df.iloc[0]
    print(
        f"  D itself: {int(diagnostic_row['n_distinct_displacement_values'])} distinct annual values "
        f"(effective n is that, not the period count below); D vs. calendar year "
        f"r={diagnostic_row['displacement_vs_year_r']:+.3f} (p={diagnostic_row['displacement_vs_year_p']:.4f})"
    )
    for _, tracking_row in tracking_df.iterrows():
        print(
            f"  {tracking_row['score']:<26} Pearson {tracking_row['pearson_r']:+.3f} "
            f"(p={tracking_row['pearson_p']:.3f}, n={int(tracking_row['n_periods'])})"
        )
    print(
        "  Hypothesis check only, few and autocorrelated periods, with the regressor itself repeating across "
        "each survey/article window: a null result here is uninformative, not disconfirming, and a positive "
        "result confounded with the calendar-year trend above is equally uninformative about displacement "
        "specifically (see docs/framework.md § Demand Composition Model)."
    )


def print_cycle_decomposition(cycle_decomposition_df: pd.DataFrame) -> None:
    """Print the cycle-versus-AI-era decomposition of each model's fit strength."""
    print("\n── Fit strength decomposed: general mechanism, business cycle, or AI era? ──")
    for score_col, _, _, _ in SCORE_CONFIGS:
        score_df = cycle_decomposition_df[cycle_decomposition_df["score"] == score_col]
        if score_df.empty:
            continue
        print(f"  {score_col}  (n={int(score_df['n_periods'].iloc[0])} periods, R²={score_df['r_squared'].iloc[0]:.3f})")
        for _, coefficient_row in score_df.iterrows():
            significance = "*" if coefficient_row["p_value"] < 0.05 else " "
            print(
                f"    {coefficient_row['term']:<22}{coefficient_row['coefficient']:+.4f}"
                f"  t={coefficient_row['t_statistic']:+5.2f}  p={coefficient_row['p_value']:.4f} {significance}"
            )


def plot_signal_over_time(period_correlation_df: pd.DataFrame, output_dir: str, level: str = "sector") -> None:
    """Fit strength by period for every model, with the AI boundary and COVID marked.

    level selects which of the three passes is being drawn — "sector" (n=22 major
    groups), "occupation" (harmonized SOC units), or "cps_group" (ten CPS
    occupation groups). The charts are deliberately identical in layout so they
    read as a set.
    """
    is_occupation_level = level == "occupation"
    is_cps_level = level == "cps_group"
    unit_counts = period_correlation_df["n_units"].dropna()
    if is_cps_level and not unit_counts.empty:
        minimum_units, maximum_units = int(unit_counts.min()), int(unit_counts.max())
        group_range = str(minimum_units) if minimum_units == maximum_units else f"{minimum_units}-{maximum_units}"
        unit_label = f"n={group_range} CPS occupation groups"
    elif is_occupation_level and not unit_counts.empty:
        unit_label = f"n={int(unit_counts.min())}-{int(unit_counts.max())} harmonized units"
    elif is_cps_level:
        unit_label = f"n={MINIMUM_CPS_GROUPS}-10 CPS occupation groups"
    else:
        unit_label = "n=22 sectors"
    ordered_periods = sorted(period_correlation_df["period"].unique(), key=lambda key: _period_sort_key(f"emp_growth_{key}"))
    if len(ordered_periods) < 2:
        return

    sns.set_theme(style="whitegrid")
    figure, axis = plt.subplots(figsize=(15, 5.5))
    period_positions = {period: index for index, period in enumerate(ordered_periods)}

    for period in ordered_periods:
        if period in COVID_PERIODS:
            axis.axvspan(period_positions[period] - 0.4, period_positions[period] + 0.4, alpha=0.12, color="red", zorder=0)

    ai_era_start = next((period_positions[p] for p in ordered_periods if is_ai_era(f"emp_growth_{p}")), None)
    if ai_era_start is not None:
        axis.axvspan(ai_era_start - 0.5, len(ordered_periods) - 0.5, alpha=0.08, color="royalblue", zorder=0)
        axis.axvline(ai_era_start - 0.5, color="royalblue", linestyle="--", linewidth=1.2, alpha=0.7, label="AI era begins (2022→23)")

    axis.axhline(0, color="grey", linewidth=0.8)

    for score_col, label, color, marker in SCORE_CONFIGS:
        score_df = period_correlation_df[period_correlation_df["score"] == score_col]
        if score_df.empty:
            continue
        score_df = score_df.assign(position=score_df["period"].map(period_positions)).sort_values("position")
        axis.plot(
            score_df["position"],
            score_df["fit_r"],
            marker=marker,
            linestyle="-",
            color=color,
            label=label,
            linewidth=1.8 if score_col == COMPOSITION_SCORE_COLUMN else 1.3,
            markersize=6 if score_col == COMPOSITION_SCORE_COLUMN else 5,
            alpha=1.0 if score_col == COMPOSITION_SCORE_COLUMN else 0.75,
            zorder=5 if score_col == COMPOSITION_SCORE_COLUMN else 3,
        )
        significant_df = score_df[score_df["fit_p"] < 0.05]
        axis.scatter(
            significant_df["position"],
            significant_df["fit_r"],
            s=110,
            facecolors="none",
            edgecolors=color,
            linewidths=1.6,
            zorder=6,
        )

    axis.set_xticks(list(period_positions.values()))
    axis.set_xticklabels([f"{p.split('_')[0]}→\n{p.split('_')[1]}" for p in ordered_periods], fontsize=8)
    level_word = {"occupation": "Occupation", "cps_group": "CPS group"}.get(level, "Sector")
    axis.set_ylabel(f"{level_word}-level Pearson r vs. employment growth")
    axis.set_title(
        "Is the demand-type signal era-invariant?\n"
        f"{level_word}-level correlation by year-over-year period, "
        f"{unit_label}. Ringed markers are p < 0.05.",
        fontsize=11,
    )
    axis.legend(fontsize=8, loc="best", framealpha=0.9)
    figure.text(
        0.5,
        -0.02,
        "Demand-type labels come from 2025 O*NET task statements applied backwards; earlier periods are more anachronistic. "
        "Red bands are COVID periods, excluded from the era comparison."
        + (
            " The composition score is a function of demand-type mix alone, so many units share one value; "
            "Pearson r is bounded by that tie structure."
            if is_occupation_level
            else ""
        ),
        ha="center",
        fontsize=7.5,
        style="italic",
        color="dimgray",
    )

    os.makedirs(output_dir, exist_ok=True)
    chart_name = {"occupation": OCCUPATION_CHART_NAME, "cps_group": CPS_CHART_NAME}.get(level, CHART_NAME)
    figure.savefig(os.path.join(output_dir, chart_name), dpi=150, bbox_inches="tight")
    plt.close(figure)
    print(f"  Saved {os.path.join(output_dir, chart_name)}")


def print_era_summary(era_summary_df: pd.DataFrame) -> None:
    """Print the 2x2 that the model exists to fill in."""
    print("\n── Era comparison: is the demand-type signal era-invariant? ──")
    print(f"  {'score':<26}{'era':<9}{'n':>4}{'mean r':>9}{'range':>18}{'sig':>5}")
    for score_col, _, _, _ in SCORE_CONFIGS:
        score_df = era_summary_df[era_summary_df["score"] == score_col]
        for _, summary_row in score_df.iterrows():
            era_label = "pre-2022" if summary_row["era"] == "pre_ai" else "AI era"
            range_text = f"{summary_row['min_r']:+.3f} to {summary_row['max_r']:+.3f}"
            print(
                f"  {score_col:<26}{era_label:<9}{int(summary_row['n_periods']):>4}"
                f"{summary_row['mean_r']:>+9.3f}{range_text:>18}{int(summary_row['n_significant']):>5}"
            )
        if not score_df.empty and pd.notna(score_df["welch_p"].iloc[0]):
            print(
                f"  {'':<26}difference {score_df['era_difference_r'].iloc[0]:+.3f}  "
                f"Welch t={score_df['welch_t'].iloc[0]:+.2f}, p={score_df['welch_p'].iloc[0]:.3f}"
            )
    period_counts = era_summary_df.drop_duplicates(subset=["score", "era"]).groupby("era")["n_periods"].max()
    ai_periods = int(period_counts.get("ai", 0))
    pre_ai_periods = int(period_counts.get("pre_ai", 0))
    print(f"  Only {ai_periods} AI-era periods against {pre_ai_periods} pre-AI, autocorrelated — descriptive, not inferential.")


def _summarise_one_level(
    period_correlation_df: pd.DataFrame,
    output_dir: str,
    level: str,
    era_output_path: str,
    cycle_output_path: str,
) -> pd.DataFrame:
    """Era comparison, cycle decomposition, displacement tracking and chart for one level.

    Both levels run identical logic on identically shaped frames; only the output
    paths and the chart's labelling differ. Keeping this in one place is what stops
    the two passes drifting apart.
    """
    print(f"\n── Demand composition model, {level} level ──")
    era_summary_df = summarise_eras(period_correlation_df)
    os.makedirs(os.path.dirname(era_output_path), exist_ok=True)
    era_summary_df.to_csv(era_output_path, index=False)
    print_era_summary(era_summary_df)

    unemployment_change = unemployment_change_by_period(sorted(period_correlation_df["period"].unique()))
    if unemployment_change is None:
        print("  ⚠ No unemployment series available; skipping the cycle decomposition.")
    else:
        cycle_decomposition_df = decompose_fit_strength(period_correlation_df, unemployment_change)
        cycle_decomposition_df.to_csv(cycle_output_path, index=False)
        print_cycle_decomposition(cycle_decomposition_df)
        print(f"  ✓ {cycle_output_path}")

    for displacement_source in DISPLACEMENT_RATE_TRACKING_SOURCES:
        tracking_df = correlate_with_displacement_rate(period_correlation_df, source=displacement_source)
        print_displacement_rate_tracking(tracking_df, displacement_source)

    plot_signal_over_time(period_correlation_df, output_dir, level=level)
    print(f"  ✓ {era_output_path}")
    return era_summary_df


def run(output_dir: str = "data/output/visualizations") -> pd.DataFrame | None:
    """Build the era comparison, write it, and draw the signal-over-time chart."""
    if not os.path.exists(COMPOSITION_REPORT_PATH):
        print(f"  ⚠ {COMPOSITION_REPORT_PATH} not found; run the composition stage first.")
        return None

    scored_df, employment_col, sector_growth_df, score_columns = load_scored_occupations()
    period_correlation_df = build_period_correlations(scored_df, employment_col, sector_growth_df, score_columns)
    if period_correlation_df.empty:
        print("  ⚠ No period correlations could be computed.")
        return None

    era_summary_df = _summarise_one_level(period_correlation_df, output_dir, "sector", OUTPUT_PATH, CYCLE_OUTPUT_PATH)

    harmonized_inputs = load_harmonized_inputs()
    if harmonized_inputs is not None:
        harmonized_trends_df, unit_membership_df = harmonized_inputs
        occupation_correlation_df = build_occupation_period_correlations(
            scored_df, employment_col, harmonized_trends_df, unit_membership_df, score_columns
        )
        if occupation_correlation_df.empty:
            print("  ⚠ No occupation-level period correlations could be computed.")
        else:
            _summarise_one_level(
                occupation_correlation_df,
                output_dir,
                "occupation",
                OCCUPATION_OUTPUT_PATH,
                OCCUPATION_CYCLE_OUTPUT_PATH,
            )

    if os.path.exists(CPS_GROUP_TRENDS_PATH):
        cps_trends_df = pd.read_csv(CPS_GROUP_TRENDS_PATH)
        cps_correlation_df = build_cps_period_correlations(scored_df, employment_col, cps_trends_df, score_columns)
        if cps_correlation_df.empty:
            print("  ⚠ No CPS-level period correlations could be computed.")
        else:
            _summarise_one_level(cps_correlation_df, output_dir, "cps_group", CPS_OUTPUT_PATH, CPS_CYCLE_OUTPUT_PATH)
    else:
        warnings.warn(f"{CPS_GROUP_TRENDS_PATH} absent; CPS level skipped", stacklevel=2)

    return era_summary_df


if __name__ == "__main__":
    run()
