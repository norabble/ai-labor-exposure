"""
dws_panel.py
────────────
Parses the BLS Displaced Worker Supplement (DWS) news release tables into a
survey-keyed displacement panel, and maps the release's occupation groups onto
SOC major groups so the demand composition model can be validated against
measured displacement.

The DWS is a biennial January supplement to the CPS, running since 1984. Each
release reports displacement over the three calendar years preceding the survey,
where a displaced worker is someone 20 or over who lost a job because a plant or
company closed or moved, because there was insufficient work, or because their
position or shift was abolished. That third reason is the structural category
this project cares about: it is technological and organisational displacement
with the cyclical and demand-shock reasons already separated out, which no
employment or unemployment series achieves without statistical purging.

Like CPS Table A-19, the release is a rolling web page — BLS replaces it in place
with each new survey and publishes no archive of prior releases (checked
2026-09-12: /news.release/archives/disp_*.htm, /bls/news-release/disp.htm and
/data/archived.htm all 404, and web.archive.org is unreachable from CI). History
therefore exists only in the committed seed panel, which accumulates forward one
survey at a time, exactly as seeds/cps_a19_panel.csv does.

Three tables are parsed:
  • Table 2 — long-tenured displaced workers by reason for job loss
  • Table 5 — long-tenured displaced workers by occupation of lost job
  • Table 8 — total displaced workers, all tenures

Inputs:
  • seeds/dws_displacement_panel.csv  (committed panel; the accumulated history)
  • data/raw/dws/disp_t02.html        (optional — latest release, from download_dws.py)
  • data/raw/dws/disp_t05.html
  • data/raw/dws/disp_t08.html

Outputs:
  • data/output/dws_displacement_panel.csv  (seed panel merged with the latest release)

Table 5 publishes ten leaf occupation groups nested under five broad ones. Only
the leaves are kept, and together they cover all 22 SOC major groups exactly
once — but the mapping is one-to-many ("Professional and related occupations"
spans SOC 15 through 29), so it cannot reuse CPS_TO_SOC_MAJOR from cps_panel.py,
whose A-19 groups are already one per major group.
"""

import os
import re

import pandas as pd

SEED_PANEL_PATH = "seeds/dws_displacement_panel.csv"
RAW_RELEASE_DIR = "data/raw/dws"
OUTPUT_PANEL_PATH = "data/output/dws_displacement_panel.csv"

PANEL_COLUMNS = [
    "survey_year",
    "period_start_year",
    "period_end_year",
    "period_years",
    "source_table",
    "group_name",
    "soc_majors",
    "displaced_thousands",
    "reason",
    "tenure_class",
]

# Ten leaf occupation groups from Table 5, each mapped to the SOC major groups it
# spans. Together these cover all 22 majors exactly once; verify_soc_coverage()
# asserts that, so a future relabelling by BLS fails loudly rather than silently
# dropping a sector from the validation.
DWS_TO_SOC_MAJOR: dict[str, list[str]] = {
    "management, business, and financial operations occupations": ["11", "13"],
    "professional and related occupations": ["15", "17", "19", "21", "23", "25", "27", "29"],
    "service occupations": ["31", "33", "35", "37", "39"],
    "sales and related occupations": ["41"],
    "office and administrative support occupations": ["43"],
    "farming, fishing, and forestry occupations": ["45"],
    "construction and extraction occupations": ["47"],
    "installation, maintenance, and repair occupations": ["49"],
    "production occupations": ["51"],
    "transportation and material moving occupations": ["53"],
}

# Reason columns in Table 2, keyed by the panel label they are stored under.
REASON_COLUMN_PATTERNS: dict[str, str] = {
    "plant or company closed down or moved": r"plant or company closed",
    "insufficient work": r"insufficient work",
    "position or shift abolished": r"position or shift abolished",
}

STRUCTURAL_REASON = "position or shift abolished"

# Table 5's leaf rows omit a small unclassified residual, so the leaves need not
# sum exactly to the published total. Anything beyond this gap means the leaf set
# has drifted and the parser is silently dropping a group.
LEAF_COVERAGE_TOLERANCE = 0.05


def verify_soc_coverage() -> None:
    """Raise if the occupation mapping does not cover all 22 SOC major groups exactly once."""
    mapped_majors = [major for majors in DWS_TO_SOC_MAJOR.values() for major in majors]
    duplicated = sorted({major for major in mapped_majors if mapped_majors.count(major) > 1})
    if duplicated:
        raise ValueError(f"DWS_TO_SOC_MAJOR maps these SOC major groups more than once: {duplicated}")
    expected_majors = {f"{code:02d}" for code in range(11, 54, 2)}
    missing = sorted(expected_majors - set(mapped_majors))
    unexpected = sorted(set(mapped_majors) - expected_majors)
    if missing or unexpected:
        raise ValueError(f"DWS_TO_SOC_MAJOR coverage error — missing: {missing}, unexpected: {unexpected}")


def _flatten_columns(release_df: pd.DataFrame) -> pd.DataFrame:
    """Collapse the release tables' two-row header into single lowercased column labels."""
    flattened_df = release_df.copy()
    flattened_df.columns = [
        " ".join(dict.fromkeys(str(level) for level in column)).strip().lower()
        if isinstance(column, tuple)
        else str(column).strip().lower()
        for column in flattened_df.columns
    ]
    return flattened_df


def _find_column(release_df: pd.DataFrame, pattern: str) -> str:
    """Return the single column whose flattened label matches pattern, or raise."""
    matches = [column for column in release_df.columns if re.search(pattern, column)]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one column matching {pattern!r}, found {matches}")
    return matches[0]


def parse_survey_period(release_html_path: str) -> tuple[int, int, int]:
    """Read the survey year and the displacement window from a release table's caption and footnote.

    Returns (survey_year, period_start_year, period_end_year). The window length is
    what converts a three-year displacement count into an annual rate, so it is read
    from the release rather than hardcoded to three.
    """
    with open(release_html_path, encoding="utf-8", errors="replace") as release_file:
        release_text = re.sub(r"<[^>]*>", " ", release_file.read())
    release_text = re.sub(r"\s+", " ", release_text)

    survey_match = re.search(r"January (\d{4})", release_text)
    window_match = re.search(r"between January (\d{4}) and December (\d{4})", release_text)
    if survey_match is None or window_match is None:
        raise ValueError(f"could not read survey period from {release_html_path}")

    return int(survey_match.group(1)), int(window_match.group(1)), int(window_match.group(2))


def parse_occupation_table(release_html_path: str) -> pd.DataFrame:
    """Parse Table 5 into one row per leaf occupation group, mapped to SOC major groups."""
    verify_soc_coverage()
    release_df = _flatten_columns(pd.read_html(release_html_path, flavor="bs4")[0])

    occupation_column = _find_column(release_df, r"occupation of lost job")
    total_column = _find_column(release_df, r"^total$")

    occupation_df = release_df[[occupation_column, total_column]].copy()
    occupation_df.columns = ["group_name", "displaced_thousands"]
    occupation_df["group_name"] = occupation_df["group_name"].astype(str).str.strip()

    published_total = pd.to_numeric(
        occupation_df.loc[occupation_df["group_name"].str.lower().str.startswith("total,"), "displaced_thousands"],
        errors="coerce",
    ).max()

    occupation_df["soc_majors"] = occupation_df["group_name"].str.lower().map(lambda name: DWS_TO_SOC_MAJOR.get(name))
    occupation_df = occupation_df.dropna(subset=["soc_majors"])
    # A dash means the base was under 75,000 and the value is suppressed, not zero.
    occupation_df["displaced_thousands"] = pd.to_numeric(occupation_df["displaced_thousands"], errors="coerce")

    missing_groups = sorted(set(DWS_TO_SOC_MAJOR) - set(occupation_df["group_name"].str.lower()))
    if missing_groups:
        raise ValueError(f"Table 5 is missing expected leaf occupation groups: {missing_groups}")

    leaf_total = occupation_df["displaced_thousands"].sum()
    if published_total and abs(leaf_total - published_total) / published_total > LEAF_COVERAGE_TOLERANCE:
        raise ValueError(
            f"Table 5 leaf groups sum to {leaf_total:,.0f} against a published total of {published_total:,.0f} "
            f"— beyond the {LEAF_COVERAGE_TOLERANCE:.0%} tolerance, so the leaf set has drifted"
        )

    occupation_df["soc_majors"] = occupation_df["soc_majors"].map("|".join)
    occupation_df["source_table"] = "table_5_occupation"
    occupation_df["reason"] = "all"
    occupation_df["tenure_class"] = "long_tenured"
    return occupation_df


def parse_reason_table(release_html_path: str) -> pd.DataFrame:
    """Parse Table 2 into one row per reason for job loss, as counts rather than percentages.

    The release publishes reasons as a percent distribution over the long-tenured
    total; those percentages are converted to counts here so every panel row carries
    the same unit.
    """
    release_df = _flatten_columns(pd.read_html(release_html_path, flavor="bs4")[0])

    characteristic_column = _find_column(release_df, r"^characteristic")
    total_column = _find_column(release_df, r"^total$")

    all_worker_rows = release_df[release_df[characteristic_column].astype(str).str.strip().str.lower() == "total, 20 years and over"]
    if all_worker_rows.empty:
        raise ValueError(f"Table 2 has no 'Total, 20 years and over' row in {release_html_path}")
    # The first such row is the all-workers total; the later ones break out men and women.
    total_row = all_worker_rows.iloc[0]
    displaced_total = pd.to_numeric(total_row[total_column], errors="coerce")

    reason_rows = []
    for reason_label, column_pattern in REASON_COLUMN_PATTERNS.items():
        reason_percent = pd.to_numeric(total_row[_find_column(release_df, column_pattern)], errors="coerce")
        reason_rows.append(
            {
                "group_name": "Total, 20 years and over",
                "soc_majors": "",
                # Rounded because this is recovered from a percentage published to one
                # decimal place; further digits are false precision.
                "displaced_thousands": round(displaced_total * reason_percent / 100.0, 3),
                "source_table": "table_2_reason",
                "reason": reason_label,
                "tenure_class": "long_tenured",
            }
        )
    return pd.DataFrame(reason_rows)


def parse_total_table(release_html_path: str) -> pd.DataFrame:
    """Parse Table 8 into the single all-tenures displacement total."""
    release_df = _flatten_columns(pd.read_html(release_html_path, flavor="bs4")[0])

    characteristic_column = _find_column(release_df, r"^characteristic")
    total_column = _find_column(release_df, r"^total$")

    all_worker_rows = release_df[release_df[characteristic_column].astype(str).str.strip().str.lower() == "total, 20 years and over"]
    if all_worker_rows.empty:
        raise ValueError(f"Table 8 has no 'Total, 20 years and over' row in {release_html_path}")

    return pd.DataFrame(
        [
            {
                "group_name": "Total, 20 years and over",
                "soc_majors": "",
                "displaced_thousands": pd.to_numeric(all_worker_rows.iloc[0][total_column], errors="coerce"),
                "source_table": "table_8_all_tenures",
                "reason": "all",
                "tenure_class": "all_tenures",
            }
        ]
    )


def build_release_panel(raw_release_dir: str = RAW_RELEASE_DIR) -> pd.DataFrame:
    """Parse one downloaded release into tidy panel rows across all three tables."""
    occupation_path = os.path.join(raw_release_dir, "disp_t05.html")
    reason_path = os.path.join(raw_release_dir, "disp_t02.html")
    total_path = os.path.join(raw_release_dir, "disp_t08.html")

    survey_year, period_start_year, period_end_year = parse_survey_period(occupation_path)

    release_panel_df = pd.concat(
        [parse_occupation_table(occupation_path), parse_reason_table(reason_path), parse_total_table(total_path)],
        ignore_index=True,
    )
    release_panel_df["survey_year"] = survey_year
    release_panel_df["period_start_year"] = period_start_year
    release_panel_df["period_end_year"] = period_end_year
    release_panel_df["period_years"] = period_end_year - period_start_year + 1
    return release_panel_df[PANEL_COLUMNS]


def merge_panel(existing_panel_df: pd.DataFrame, new_release_df: pd.DataFrame) -> pd.DataFrame:
    """Merge a freshly parsed release into the accumulated panel, the new release winning ties."""
    combined_panel_df = pd.concat([existing_panel_df, new_release_df], ignore_index=True)
    combined_panel_df = combined_panel_df.drop_duplicates(
        subset=["survey_year", "source_table", "group_name", "reason", "tenure_class"], keep="last"
    )
    return combined_panel_df.sort_values(["survey_year", "source_table", "group_name", "reason"]).reset_index(drop=True)


def load_dws_panel(
    seed_path: str = SEED_PANEL_PATH,
    raw_release_dir: str = RAW_RELEASE_DIR,
    output_path: str | None = OUTPUT_PANEL_PATH,
) -> pd.DataFrame | None:
    """Load the committed panel, merge in a downloaded release if one is present, and write the result.

    Returns None with a warning when neither a seed nor a release is available, so
    callers can skip the DWS-dependent work rather than fail the pipeline.
    """
    existing_panel_df = pd.DataFrame(columns=PANEL_COLUMNS)
    if os.path.exists(seed_path):
        existing_panel_df = pd.read_csv(seed_path, dtype={"soc_majors": str}).fillna({"soc_majors": ""})

    release_panel_df = None
    if os.path.exists(os.path.join(raw_release_dir, "disp_t05.html")):
        try:
            release_panel_df = build_release_panel(raw_release_dir)
        except (ValueError, IndexError, KeyError) as parse_error:
            print(f"  ⚠ Could not parse the DWS release ({parse_error}); falling back to the seed panel.")

    if release_panel_df is not None:
        panel_df = merge_panel(existing_panel_df, release_panel_df)
    else:
        panel_df = existing_panel_df

    if panel_df.empty:
        print("  ⚠ No DWS panel available (no seed and no parseable release); DWS-based steps will be skipped.")
        return None

    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        panel_df.to_csv(output_path, index=False)

    return panel_df
