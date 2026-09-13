"""
cps_historical_panel.py
───────────────────────
Build a CPS employment panel by occupation group covering 1983 onward — a second,
independent employment instrument alongside OEWS.

BLS reconstructed CPS employment for 1983-99 onto the 2002 Census / SOC 2000
classification and publishes it under the same series IDs as current data, so one
series ID spans 1983 to the present. Ten of those series are the leaf occupation
groups; their names match the DWS group names the project already maps to SOC
major codes, so no new crosswalk is needed.

Inputs:
  • https://api.bls.gov/publicAPI/v2/timeseries/data/ (ten LNU series, cached)
  • seeds/cps_occupation_panel.csv (committed history)

Outputs:
  • data/output/cps_occupation_panel.csv — merged annual panel
  • data/output/cps_group_trends.csv     — wide trend table with growth columns

Two comparability breaks live inside these series and are disclosed rather than
patched: January 2003 (the classification change the reconstruction bridges) and
January 2000 (where the reconstructed segment meets published data). Data before
1998 is uncomposited and will not sum to published totals.
"""

import os
import warnings

import pandas as pd

from analyze_bls import attach_growth_columns
from historical_displacement import fetch_annual_means

SEED_PATH = "seeds/cps_occupation_panel.csv"
PANEL_OUTPUT_PATH = "data/output/cps_occupation_panel.csv"
TRENDS_OUTPUT_PATH = "data/output/cps_group_trends.csv"
AGREEMENT_OUTPUT_PATH = "data/output/cps_oews_agreement.csv"
SECTOR_TRENDS_INPUT_PATH = "data/output/bls_sector_trends.csv"
OCCUPATION_TRENDS_INPUT_PATH = "data/output/bls_trends.csv"

# Leaf occupation groups only. The aggregate rows (LNU02032201, LNU02032205,
# LNU02032208, LNU02032212) are deliberately excluded: summing them alongside
# their own leaves would double-count.
CPS_GROUP_SERIES: dict[str, str] = {
    "management, business, and financial operations occupations": "LNU02032202",
    "professional and related occupations": "LNU02032203",
    "service occupations": "LNU02032204",
    "sales and related occupations": "LNU02032206",
    "office and administrative support occupations": "LNU02032207",
    "farming, fishing, and forestry occupations": "LNU02032209",
    "construction and extraction occupations": "LNU02032210",
    "installation, maintenance, and repair occupations": "LNU02032211",
    "production occupations": "LNU02032213",
    "transportation and material moving occupations": "LNU02032214",
}

PANEL_COLUMNS = ["year", "cps_group", "employed_thousands"]


def fetch_cps_group_employment(start_year: int = 1983, end_year: int = 2026) -> pd.DataFrame:
    """Annual mean employment per occupation group, in long form.

    The published series are monthly and not seasonally adjusted;
    fetch_annual_means collapses them to annual means, which is what BLS's own
    annual averages are. A series that cannot be fetched is warned about and
    skipped rather than failing the whole panel.
    """
    panel_rows = []
    for cps_group, series_id in CPS_GROUP_SERIES.items():
        annual_means = fetch_annual_means(series_id, start_year, end_year)
        if annual_means is None:
            warnings.warn(f"CPS series {series_id} ({cps_group}) unavailable; skipping", stacklevel=2)
            continue
        for year, employed_thousands in annual_means.items():
            panel_rows.append({"year": int(year), "cps_group": cps_group, "employed_thousands": float(employed_thousands)})
    return pd.DataFrame(panel_rows, columns=PANEL_COLUMNS)


def merge_into_seed(fetched_df: pd.DataFrame, seed_path: str = SEED_PATH) -> pd.DataFrame:
    """Merge a fetch into the committed panel, the fetch winning on collisions.

    Follows the seeds/cps_a19_panel.csv convention: history accumulates in the
    committed file, and a run that cannot reach BLS still renders from the seed.
    """
    if not os.path.exists(seed_path):
        return fetched_df.sort_values(["year", "cps_group"]).reset_index(drop=True)
    seed_df = pd.read_csv(seed_path)
    combined_df = pd.concat([seed_df, fetched_df], ignore_index=True)
    combined_df = combined_df.drop_duplicates(subset=["year", "cps_group"], keep="last")
    return combined_df.sort_values(["year", "cps_group"]).reset_index(drop=True)


def build_cps_group_trends(panel_df: pd.DataFrame) -> pd.DataFrame:
    """Pivot the long panel to one row per group with TOT_EMP_{yyyy} and growth columns.

    attach_growth_columns is reused rather than reimplemented so the CPS table
    carries byte-identical growth-column names to bls_sector_trends.csv, which is
    what lets the existing period-discovery machinery read it unchanged.
    """
    wide_df = panel_df.pivot(index="cps_group", columns="year", values="employed_thousands")
    wide_df.columns = [f"TOT_EMP_{int(year)}" for year in wide_df.columns]
    wide_df = wide_df.reset_index()

    available_years = sorted(str(int(year)) for year in panel_df["year"].unique())
    return attach_growth_columns(wide_df, available_years)


COMPARABILITY_BREAK_PERIODS = ("1999_2000", "2002_2003")


def measure_comparability_breaks(
    trends_df: pd.DataFrame,
    break_periods: tuple[str, ...] = COMPARABILITY_BREAK_PERIODS,
) -> pd.DataFrame:
    """Per-group growth in every period, with the known comparability breaks flagged.

    The point is comparison: a break period whose growth sits inside the ordinary
    spread is a break the data survived, and one far outside it is a break that
    contaminates any span crossing it. Neither is patched here.
    """
    growth_rows = []
    for column in trends_df.columns:
        if "emp_growth_" not in column or "composite" in column or "pre_ai" in column:
            continue
        period = column.replace("hist_emp_growth_", "").replace("emp_growth_", "")
        for _, group_row in trends_df.iterrows():
            growth_rows.append(
                {
                    "period": period,
                    "cps_group": group_row["cps_group"],
                    "emp_growth": group_row[column],
                    "is_break_period": period in break_periods,
                }
            )
    return pd.DataFrame(growth_rows)


def compare_with_oews(
    cps_trends_df: pd.DataFrame,
    oews_sector_trends_df: pd.DataFrame,
    soc_major_to_group: dict[str, str],
) -> pd.DataFrame:
    """Per-period growth from both instruments, aggregated to the CPS groups.

    The CPS side of this comparison is the growth of a group TOTAL, so the
    faithful OEWS counterpart is the growth of the group's total employment
    LEVEL, not an unweighted mean of its member SOC majors' growth rates — a
    mean of rates would weight a small SOC major equally with a much larger one
    inside the same CPS group. `bls_sector_trends.csv` carries `TOT_EMP_{yyyy}`
    level columns alongside its growth columns, so each period's OEWS group
    growth is derived as (summed end-year level) / (summed start-year level) - 1.

    Reported, never reconciled. CPS counts the self-employed and agriculture and
    OEWS does not, so the two disagree by construction; the size of the
    disagreement over the 1999-2025 overlap is what bounds confidence in the
    CPS-only stretch before 1999.
    """
    oews_df = oews_sector_trends_df.copy()
    oews_df["cps_group"] = oews_df["soc_major"].astype(str).str.zfill(2).map(soc_major_to_group)
    oews_df = oews_df.dropna(subset=["cps_group"])

    comparison_rows = []
    for column in cps_trends_df.columns:
        if "emp_growth_" not in column or "composite" in column or "pre_ai" in column:
            continue
        period = column.replace("hist_emp_growth_", "").replace("emp_growth_", "")
        start_year, end_year = period.split("_")
        start_level_column = f"TOT_EMP_{start_year}"
        end_level_column = f"TOT_EMP_{end_year}"
        if start_level_column not in oews_df.columns or end_level_column not in oews_df.columns:
            continue

        group_levels = oews_df.groupby("cps_group")[[start_level_column, end_level_column]].sum(min_count=1)
        valid_group_levels = group_levels[group_levels[start_level_column].notna() & (group_levels[start_level_column] != 0)]
        oews_group_growth = valid_group_levels[end_level_column] / valid_group_levels[start_level_column] - 1

        for _, cps_row in cps_trends_df.iterrows():
            group = cps_row["cps_group"]
            if group not in oews_group_growth.index:
                continue
            comparison_rows.append(
                {
                    "period": period,
                    "cps_group": group,
                    "cps_growth": cps_row[column],
                    "oews_growth": oews_group_growth[group],
                    "difference": cps_row[column] - oews_group_growth[group],
                }
            )
    return pd.DataFrame(comparison_rows)


STABILITY_OUTPUT_PATH = "data/output/sector_composition_stability.csv"


def sector_composition_stability(
    occupation_trends_df: pd.DataFrame,
    earliest_year: str = "1999",
    anchor_year: str = "2022",
) -> pd.DataFrame:
    """Share of each sector's anchor-year employment in occupations that existed at the series start.

    A bound on where the 2025 O*NET demand-type labels are most anachronistic: a
    sector largely composed of occupations OEWS did not publish in 1999 has been
    rebuilt since, so carrying today's labels back through it is the least safe.
    This is a proxy for composition churn, not a measure of task-content drift.
    """
    anchor_col, earliest_col = f"TOT_EMP_{anchor_year}", f"TOT_EMP_{earliest_year}"
    stability_df = occupation_trends_df.dropna(subset=[anchor_col]).copy()
    stability_df["soc_major"] = stability_df["OCC_CODE"].astype(str).str[:2]
    stability_df["antecedent_employment"] = stability_df[anchor_col].where(stability_df[earliest_col].notna(), 0.0)

    grouped_df = (
        stability_df.groupby("soc_major")
        .agg(anchor_employment=(anchor_col, "sum"), antecedent_employment=("antecedent_employment", "sum"))
        .reset_index()
    )
    grouped_df["stable_share"] = grouped_df["antecedent_employment"] / grouped_df["anchor_employment"]
    return grouped_df.sort_values("stable_share").reset_index(drop=True)


def run_stage(
    seed_path: str = SEED_PATH,
    panel_output_path: str = PANEL_OUTPUT_PATH,
    trends_output_path: str = TRENDS_OUTPUT_PATH,
    agreement_output_path: str = AGREEMENT_OUTPUT_PATH,
    stability_output_path: str = STABILITY_OUTPUT_PATH,
    sector_trends_input_path: str = SECTOR_TRENDS_INPUT_PATH,
    occupation_trends_input_path: str = OCCUPATION_TRENDS_INPUT_PATH,
) -> None:
    """Build and write all four CPS-instrument outputs.

    Follows the same convention as `download_cps.js` and `download_dws.py`: a
    fetch that returns nothing, or raises, is warned about and the committed
    seed is used instead — the CPS level of the composition era comparison must
    still render offline from the seed alone, never crash the pipeline.

    Steps 3-4 (the OEWS agreement and composition-stability tables) each depend
    on a separate BLS output that may not exist yet on a partial run; either is
    skipped with a warning without touching the panel or trend table already
    written in steps 1-2.
    """
    try:
        fetched_df = fetch_cps_group_employment()
    except Exception as fetch_error:  # any fetch failure must degrade, not crash the pipeline
        warnings.warn(f"CPS group fetch failed ({fetch_error}); falling back to the committed seed", stacklevel=2)
        fetched_df = pd.DataFrame(columns=PANEL_COLUMNS)

    if fetched_df.empty:
        warnings.warn("CPS group fetch returned no data; building the CPS panel from the committed seed only", stacklevel=2)
        if not os.path.exists(seed_path):
            warnings.warn(f"{seed_path} also absent; cannot build the CPS panel — skipping the CPS instrument", stacklevel=2)
            return
        panel_df = pd.read_csv(seed_path)
    else:
        panel_df = merge_into_seed(fetched_df, seed_path)

    os.makedirs(os.path.dirname(panel_output_path), exist_ok=True)
    panel_df.to_csv(panel_output_path, index=False)

    trends_df = build_cps_group_trends(panel_df)
    os.makedirs(os.path.dirname(trends_output_path), exist_ok=True)
    trends_df.to_csv(trends_output_path, index=False)

    if os.path.exists(sector_trends_input_path):
        try:
            import composition_displacement_validation

            sector_trends_df = pd.read_csv(sector_trends_input_path, dtype={"soc_major": str})
            group_lookup = composition_displacement_validation.soc_major_to_dws_group()
            agreement_df = compare_with_oews(trends_df, sector_trends_df, group_lookup)
            os.makedirs(os.path.dirname(agreement_output_path), exist_ok=True)
            agreement_df.to_csv(agreement_output_path, index=False)
        except Exception as agreement_error:  # must not block the panel/trend table already written
            warnings.warn(f"Could not build the CPS-vs-OEWS agreement table: {agreement_error}", stacklevel=2)
    else:
        warnings.warn(f"{sector_trends_input_path} absent; skipping the CPS-vs-OEWS agreement table", stacklevel=2)

    if os.path.exists(occupation_trends_input_path):
        try:
            occupation_trends_df = pd.read_csv(occupation_trends_input_path)
            stability_df = sector_composition_stability(occupation_trends_df)
            os.makedirs(os.path.dirname(stability_output_path), exist_ok=True)
            stability_df.to_csv(stability_output_path, index=False)
        except Exception as stability_error:  # must not block the panel/trend table already written
            warnings.warn(f"Could not build the sector composition stability table: {stability_error}", stacklevel=2)
    else:
        warnings.warn(f"{occupation_trends_input_path} absent; skipping the composition stability table", stacklevel=2)


if __name__ == "__main__":
    run_stage()
