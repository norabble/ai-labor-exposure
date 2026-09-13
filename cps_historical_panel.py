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
        if column not in oews_df.columns:
            continue
        period = column.replace("hist_emp_growth_", "").replace("emp_growth_", "")
        oews_group_growth = oews_df.groupby("cps_group")[column].mean()
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
