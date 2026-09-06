"""
cps_panel.py
────────────
Parses BLS CPS Table A-19 ("Employed people by occupation, sex, and age") into a
month-keyed employment panel, and derives the comparison windows used by the CPS
charts in validate_bls.py.

A-19 is a rolling web table: it always shows the latest reference month and the
same month one year earlier, and BLS replaces it in place each month. A single
fetch therefore yields only two months. This module accumulates those months into
a tidy panel so that history survives across runs, and so that the release
workflow — which starts with an empty, gitignored data/ — still has real months
to work with.

Inputs:
  • seeds/cps_a19_panel.csv       (committed panel; the accumulated history)
  • data/raw/cps/table_a19.html   (optional — latest release, from download_cps.js)

Outputs:
  • data/output/cps_a19_panel.csv (seed panel merged with the latest release)

Two comparison windows are derived from the panel:
  • since-anchor — from the last panel month at or before the OEWS reference
    month through the latest month. This is the window the CPS charts exist to
    show: the stretch of time OEWS does not yet cover.
  • year-over-year — the latest month against the same month a year earlier.

The since-anchor window spans different calendar months, and A-19 is not
seasonally adjusted, so it carries seasonal noise that the year-over-year window
does not. It also crosses each January, when CPS introduces updated population
controls without revising prior months. Both caveats are surfaced on the charts.
"""

import os
from dataclasses import dataclass

import pandas as pd

# CPS Table A-19 group name (lowercased) → SOC 2-digit major group code
CPS_TO_SOC_MAJOR: dict[str, str] = {
    "management occupations": "11",
    "business and financial operations occupations": "13",
    "computer and mathematical occupations": "15",
    "architecture and engineering occupations": "17",
    "life, physical, and social science occupations": "19",
    "community and social service occupations": "21",
    "legal occupations": "23",
    "education, training, and library occupations": "25",
    "arts, design, entertainment, sports, and media occupations": "27",
    "healthcare practitioners and technical occupations": "29",
    "healthcare support occupations": "31",
    "protective service occupations": "33",
    "food preparation and serving related occupations": "35",
    "building and grounds cleaning and maintenance occupations": "37",
    "personal care and service occupations": "39",
    "sales and related occupations": "41",
    "office and administrative support occupations": "43",
    "farming, fishing, and forestry occupations": "45",
    "construction and extraction occupations": "47",
    "installation, maintenance, and repair occupations": "49",
    "production occupations": "51",
    "transportation and material moving occupations": "53",
}

MONTH_NUMBER_BY_ABBREVIATION: dict[str, int] = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

SEED_PANEL_PATH = "seeds/cps_a19_panel.csv"
LATEST_RELEASE_HTML_PATH = "data/raw/cps/table_a19.html"
OUTPUT_PANEL_PATH = "data/output/cps_a19_panel.csv"

PANEL_COLUMNS = ["month", "soc_major", "occupation", "employed_thousands", "source_reference_month"]

# A-19 reports the "Total" column group for a single age band; the Men and Women
# column groups repeat the same months for two age bands each.
TOTAL_COLUMN_GROUP = "Total"
TOTAL_AGE_BAND = "16 years and over"


@dataclass(frozen=True)
class CpsComparisonWindows:
    """The two comparison windows derived from the panel, as 'YYYY-MM' month keys."""

    anchor_month: str
    latest_month: str
    year_ago_month: str | None

    @property
    def since_anchor_label(self) -> str:
        return f"{format_month(self.anchor_month)} → {format_month(self.latest_month)}"

    @property
    def year_over_year_label(self) -> str | None:
        if self.year_ago_month is None:
            return None
        return f"{format_month(self.year_ago_month)} → {format_month(self.latest_month)}"

    @property
    def since_anchor_crosses_january(self) -> bool:
        """
        Whether the since-anchor window spans a January.

        CPS introduces updated population controls with each January release and
        does not revise prior months, so a window crossing that boundary carries
        a level shift unrelated to the labor market. Short windows may not cross
        one, so this is checked rather than assumed.
        """
        anchor_period = pd.Period(self.anchor_month, freq="M")
        latest_period = pd.Period(self.latest_month, freq="M")
        return any((anchor_period + offset).month == 1 for offset in range(1, (latest_period - anchor_period).n + 1))

    @property
    def window_caveat(self) -> str:
        """Chart-ready caveat text describing the distortions the since-anchor window carries."""
        caveat = "A-19 is not seasonally adjusted; the since-OEWS window spans different calendar months"
        if self.since_anchor_crosses_january:
            caveat += " and crosses a January population-control update"
        return caveat + "."


def format_month(month_key: str) -> str:
    """Render a 'YYYY-MM' month key as a readable label like 'Apr 2025'."""
    return pd.Period(month_key, freq="M").strftime("%b %Y")


def parse_month_label(month_label: str) -> str:
    """
    Convert an A-19 column header label to a 'YYYY-MM' month key.

    BLS writes these inconsistently across months — 'Apr. 2025', 'June 2025' and
    'Sept. 2025' all occur — so the month name is matched on its first three
    letters rather than on an exact string.
    """
    normalized_label = str(month_label).replace(".", " ").replace("\xa0", " ").strip()
    label_parts = normalized_label.split()
    if len(label_parts) < 2:
        raise ValueError(f"Unrecognized A-19 month label: {month_label!r}")

    month_number = MONTH_NUMBER_BY_ABBREVIATION.get(label_parts[0][:3].lower())
    if month_number is None:
        raise ValueError(f"Unrecognized month name in A-19 label: {month_label!r}")

    year_text = label_parts[-1]
    if not (year_text.isdigit() and len(year_text) == 4):
        raise ValueError(f"Unrecognized year in A-19 label: {month_label!r}")

    return f"{year_text}-{month_number:02d}"


def extract_total_month_columns(raw_release_df: pd.DataFrame) -> list[tuple[object, str]]:
    """
    Locate the two "Total, 16 years and over" employment columns and the month each holds.

    A-19's header is three rows deep, which pandas flattens into a MultiIndex of
    (column group, age band, month). Selecting on the group and age band rather
    than on position is what keeps the month labels attached to the right data:
    the previous positional implementation assigned fixed month names and would
    silently mislabel every chart once BLS advanced the rolling page.
    """
    if raw_release_df.columns.nlevels != 3:
        raise ValueError(
            f"Expected a 3-level A-19 column header, found {raw_release_df.columns.nlevels} level(s). "
            "The table layout has changed and the parser needs review."
        )

    month_columns = [
        (column_key, parse_month_label(column_key[2]))
        for column_key in raw_release_df.columns
        if column_key[0] == TOTAL_COLUMN_GROUP and column_key[1] == TOTAL_AGE_BAND
    ]

    if len(month_columns) != 2:
        raise ValueError(
            f"Expected exactly 2 '{TOTAL_COLUMN_GROUP} / {TOTAL_AGE_BAND}' columns in A-19, "
            f"found {len(month_columns)}. The table layout has changed and the parser needs review."
        )

    return month_columns


def parse_a19_release(release_html_path: str) -> pd.DataFrame:
    """Parse one A-19 release into tidy panel rows (two months × 22 major groups)."""
    raw_release_df = pd.read_html(release_html_path, flavor="bs4")[0]
    month_columns = extract_total_month_columns(raw_release_df)

    occupation_column = raw_release_df.columns[0]
    release_reference_month = max(month for _, month in month_columns)

    panel_rows = []
    for column_key, month in month_columns:
        month_slice_df = raw_release_df[[occupation_column, column_key]].copy()
        month_slice_df.columns = ["occupation", "employed_thousands"]
        month_slice_df = month_slice_df.dropna(subset=["occupation"])
        month_slice_df["soc_major"] = month_slice_df["occupation"].astype(str).str.lower().str.strip().map(CPS_TO_SOC_MAJOR)
        month_slice_df = month_slice_df.dropna(subset=["soc_major"])
        month_slice_df["employed_thousands"] = pd.to_numeric(month_slice_df["employed_thousands"], errors="coerce")
        month_slice_df = month_slice_df.dropna(subset=["employed_thousands"])
        month_slice_df["month"] = month
        month_slice_df["source_reference_month"] = release_reference_month
        panel_rows.append(month_slice_df[PANEL_COLUMNS])

    return pd.concat(panel_rows, ignore_index=True)


def merge_panel(existing_panel_df: pd.DataFrame, new_release_df: pd.DataFrame) -> pd.DataFrame:
    """
    Upsert new release rows into the panel, keyed on (month, soc_major).

    When two releases report the same month, the later release wins — A-19 levels
    for a given month can shift when CPS rebases its population controls.
    """
    combined_df = pd.concat([existing_panel_df, new_release_df], ignore_index=True)
    combined_df = combined_df.sort_values(["month", "soc_major", "source_reference_month"], kind="stable")
    deduplicated_df = combined_df.drop_duplicates(subset=["month", "soc_major"], keep="last")
    return deduplicated_df.sort_values(["month", "soc_major"], kind="stable").reset_index(drop=True)


def load_cps_panel(
    seed_path: str = SEED_PANEL_PATH,
    release_html_path: str = LATEST_RELEASE_HTML_PATH,
    output_path: str | None = OUTPUT_PANEL_PATH,
) -> pd.DataFrame | None:
    """
    Build the working panel from the committed seed plus the latest fetched release.

    Returns None only when neither source is available. Neither a missing release
    HTML nor an unparseable one is fatal: the seed alone still yields correctly
    labelled charts from real months, which is what keeps a blocked download or a
    BLS layout change from silently republishing stale ones. The parse error is
    still surfaced loudly — it just does not take the rest of the pipeline with it.
    """
    panel_df = pd.DataFrame(columns=PANEL_COLUMNS)
    if os.path.exists(seed_path):
        panel_df = pd.read_csv(seed_path, dtype={"month": str, "soc_major": str, "source_reference_month": str})

    if os.path.exists(release_html_path):
        try:
            panel_df = merge_panel(panel_df, parse_a19_release(release_html_path))
        except (ValueError, IndexError) as parse_error:
            print(f"  WARNING: could not parse {release_html_path} — {parse_error}")
            if panel_df.empty:
                return None
            print("  Falling back to the committed CPS panel seed; charts will use older months.")
    elif panel_df.empty:
        return None
    else:
        print(f"  Note: {release_html_path} not found — using the committed CPS panel seed only.")

    if panel_df.empty:
        return None

    if output_path is not None:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        panel_df.to_csv(output_path, index=False)

    return panel_df


def oews_reference_month(bls_trends_columns: list[str]) -> str:
    """
    Derive the OEWS reference month from the latest TOT_EMP_* column.

    OEWS estimates always carry a May reference month, so TOT_EMP_25 means May 2025.
    """
    employment_columns = sorted(column for column in bls_trends_columns if column.startswith("TOT_EMP_"))
    if not employment_columns:
        raise ValueError("No TOT_EMP_* column found; cannot determine the OEWS reference month.")
    latest_year_suffix = employment_columns[-1].removeprefix("TOT_EMP_")
    return f"20{latest_year_suffix}-05"


def resolve_comparison_windows(panel_df: pd.DataFrame, oews_reference: str) -> CpsComparisonWindows:
    """
    Pick the anchor, latest, and year-ago months from the panel.

    The anchor is the last panel month at or before the OEWS reference month —
    the point where OEWS stops and CPS takes over — rather than simply the
    earliest month in the panel. That distinction matters once the panel is
    back-filled with history: the earliest month would drift away from the OEWS
    handoff and quietly change what the chart means.
    """
    available_months = sorted(panel_df["month"].unique())
    if len(available_months) < 2:
        raise ValueError(f"CPS panel needs at least 2 months to compute growth, found {len(available_months)}.")

    latest_month = available_months[-1]
    months_at_or_before_reference = [month for month in available_months if month <= oews_reference]
    anchor_month = months_at_or_before_reference[-1] if months_at_or_before_reference else available_months[0]

    if anchor_month == latest_month:
        raise ValueError(f"CPS anchor and latest month are both {latest_month}; no window to measure.")

    year_ago_candidate = str(pd.Period(latest_month, freq="M") - 12)
    year_ago_month = year_ago_candidate if year_ago_candidate in available_months else None

    return CpsComparisonWindows(anchor_month=anchor_month, latest_month=latest_month, year_ago_month=year_ago_month)


def year_over_year_month_pairs(panel_df: pd.DataFrame) -> list[tuple[str, str]]:
    """
    Every (year_ago_month, latest_month) pair the panel can support, oldest first.

    A-19 hands over the latest month and the same month a year earlier in a single
    release, so each fetch contributes exactly one such pair. With six months on
    hand the panel yields three — all of them measuring the same 2025→2026 span
    from endpoints two months apart, which is why they are the endpoint-sensitivity
    check in model_signal_over_time.png rather than three periods of a time series.
    """
    available_months = sorted(panel_df["month"].unique())
    available_month_set = set(available_months)
    return [
        (str(pd.Period(month, freq="M") - 12), month)
        for month in available_months
        if str(pd.Period(month, freq="M") - 12) in available_month_set
    ]


def build_year_over_year_growth(panel_df: pd.DataFrame, year_ago_month: str, latest_month: str) -> pd.DataFrame:
    """
    Per-major-group employment growth for one year-over-year month pair.

    Returns soc_major and emp_growth_year_over_year. Unlike build_growth_frame this
    takes an explicit pair rather than the derived comparison windows, so callers
    can walk every pair the panel supports.
    """
    employment_by_month_df = panel_df.pivot_table(index="soc_major", columns="month", values="employed_thousands", aggfunc="last")
    missing_months = [month for month in (year_ago_month, latest_month) if month not in employment_by_month_df.columns]
    if missing_months:
        raise ValueError(f"CPS panel is missing month(s) {missing_months}; cannot build a year-over-year frame.")

    year_ago_employment = employment_by_month_df[year_ago_month]
    latest_employment = employment_by_month_df[latest_month]
    growth_series = (latest_employment - year_ago_employment) / year_ago_employment
    return growth_series.dropna().rename("emp_growth_year_over_year").reset_index()


def build_growth_frame(panel_df: pd.DataFrame, windows: CpsComparisonWindows) -> pd.DataFrame:
    """
    Compute both comparison windows per SOC major group.

    Returns one row per major group with employment levels for each window
    endpoint plus emp_growth_since_anchor and emp_growth_year_over_year. The
    year-over-year column is absent when the panel lacks the year-ago month.
    """
    employment_by_month_df = panel_df.pivot_table(index="soc_major", columns="month", values="employed_thousands", aggfunc="last")
    occupation_by_group = panel_df.sort_values("month").groupby("soc_major")["occupation"].last()

    growth_df = pd.DataFrame(
        {
            "occupation": occupation_by_group,
            "anchor_employment": employment_by_month_df[windows.anchor_month],
            "latest_employment": employment_by_month_df[windows.latest_month],
        }
    )
    growth_df["emp_growth_since_anchor"] = (growth_df["latest_employment"] - growth_df["anchor_employment"]) / growth_df[
        "anchor_employment"
    ]

    if windows.year_ago_month is not None:
        growth_df["year_ago_employment"] = employment_by_month_df[windows.year_ago_month]
        growth_df["emp_growth_year_over_year"] = (growth_df["latest_employment"] - growth_df["year_ago_employment"]) / growth_df[
            "year_ago_employment"
        ]

    return growth_df.dropna(subset=["emp_growth_since_anchor"]).reset_index()
