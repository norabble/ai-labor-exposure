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

Like CPS Table A-19, the current release is a rolling web page — BLS replaces it
in place with each new survey, carrying only the latest survey at any time. Nine
archives of prior releases do exist, at
https://www.bls.gov/news.release/archives/disp_<MMDDYYYY>.htm for survey years
2008, 2010, 2012, 2014, 2016, 2018, 2020, 2022, and 2024 (verified 2026-09-14; an
earlier note here claiming no archive existed was wrong — it probed the wrong
release dates). Surveys 2000-2006 genuinely have no archive. History before 2008
therefore comes from the Monthly Labor Review displaced-worker article series
instead (see mlr_displacement.py), as displacement *rates* rather than counts.
Even with the archive, the rolling current-release page is still replaced in
place each cycle, so history overall exists only in the committed seed panel,
which accumulates forward one survey at a time, exactly as seeds/cps_a19_panel.csv
does.

Three tables are parsed:
  • Table 2 — long-tenured displaced workers by reason for job loss
  • Table 5 — long-tenured displaced workers by occupation of lost job
  • Table 8 — total displaced workers, all tenures

Inputs:
  • seeds/dws_displacement_panel.csv  (committed panel; the accumulated history)
  • data/raw/dws/disp_t02.html        (optional — latest release, from download_dws.py)
  • data/raw/dws/disp_t05.html
  • data/raw/dws/disp_t08.html
  • mlr_displacement.parse_displacement_rate_table output  (via mlr_rows_for_panel,
    consumed by the seed-rebuild script described in the project's implementation
    plan, not by load_dws_panel itself)

Outputs:
  • data/output/dws_displacement_panel.csv  (seed panel merged with the latest release)

The panel carries two measurement bases, distinguished by the `measurement_basis`
column (`count_thousands` or `rate_percent`) and the `source` column
(`news_release`, `news_release_archive`, or `mlr_article`): counted DWS releases
for survey years 2008 onward, and rates read off the pre-2008 Monthly Labor
Review article series (see mlr_displacement.py) for 1983 through 2001. The two
bases are never blended — a rate and a count cannot be summed — so every
consumer that aggregates `displaced_thousands` must filter to
`measurement_basis == "count_thousands"` first; `mlr_rows_for_panel` is the
function that reshapes the MLR rate table into this panel's row shape, one row
per (period, MLR occupation leaf) rather than per (period, DWS group), because
four DWS groups each receive two MLR leaves and rates cannot be collapsed into
one without employment weights the MLR tables never published.

Table 5 publishes ten leaf occupation groups nested under five broad ones. Only
the leaves are kept, and together they cover all 22 SOC major groups exactly
once — but the mapping is one-to-many ("Professional and related occupations"
spans SOC 15 through 29), so it cannot reuse CPS_TO_SOC_MAJOR from cps_panel.py,
whose A-19 groups are already one per major group.

`parse_archived_release` extends the panel further back using the nine archived
releases `download_dws.download_archived_releases` fetches from
/news.release/archives/disp_<MMDDYYYY>.htm, and all three tables — occupation,
reason, and the all-tenures total analogous to Table 8 — are recovered from
every one of the nine. Unlike the current release, an archived page carries
every table inline on one page rather than split across three files, so the
occupation and reason tables are selected by their heading text rather than by
a fixed index — ordering is not guaranteed stable across sixteen years of
releases. Table 8 cannot be selected by heading text on the HTML-table archives
(2018-2024): it shares its column signature with two other tables on the page
and no heading distinguishes any of the three, so `_select_total_table` picks
it out instead by a semantic invariant — its total must exceed Table 5's own
published long-tenured total, which the other same-signature tables merely
repeat — and skips it with a warning, rather than guessing, when that
invariant fails to single out exactly one candidate. On the plain-text
archives (2008-2016) Table 8's caption is unique among the page's `<PRE>`
captions, so it is found directly by `_select_pre_block`, the same way the
occupation and reason blocks already are.

Of the nine archives, 2018, 2020, 2022, and 2024 render their tables as HTML
`<table>` elements that `pandas.read_html` can parse directly; 2008–2016 lay
theirs out as plain-text `<PRE>` blocks instead, with dot-leader-padded labels
and fixed-width-aligned (not delimited) numeric columns. `parse_archived_release`
detects which layout a page uses — no inline `<table>` at all means `<PRE>` —
and dispatches to `parse_archived_text_release`, which reconstructs the same
column shape `_occupation_rows`, `_reason_rows`, and `_total_rows` already
expect out of the plain text, rather than duplicating their leaf-selection,
dash-to-NaN, SOC mapping, and coverage-check logic.
"""

import html
import io
import os
import re

import pandas as pd

from mlr_displacement import mlr_to_dws_group

SEED_PANEL_PATH = "seeds/dws_displacement_panel.csv"
RAW_RELEASE_DIR = "data/raw/dws"
OUTPUT_PANEL_PATH = "data/output/dws_displacement_panel.csv"

# The two measurement bases a panel row can carry. Rates and counts must never be
# summed together — see mlr_rows_for_panel and the module docstring.
COUNT_MEASUREMENT_BASIS = "count_thousands"
RATE_MEASUREMENT_BASIS = "rate_percent"

PANEL_COLUMNS = [
    "survey_year",
    "period_start_year",
    "period_end_year",
    "period_years",
    "source_table",
    "group_name",
    "mlr_occupation",
    "soc_majors",
    "displaced_thousands",
    "displacement_rate_percent",
    "reason",
    "tenure_class",
    "measurement_basis",
    "source",
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

# Patterns used to recover tabular rows from a plain-text <PRE> block (2008-2016
# archives). Dot leaders pad a row label out to its numbers column
# ("Service occupations............."); numeric columns are aligned with runs of
# plain whitespace rather than a delimiter, so rows are split on those runs, never
# a fixed character offset.
_DOT_LEADER_PATTERN = re.compile(r"\.{2,}")
_WHITESPACE_RUN_PATTERN = re.compile(r"\s{2,}")
_PRE_TABLE_NUMERIC_TOKEN_PATTERN = re.compile(r"-|[\d,]+(?:\.\d+)?")

# An archived HTML release's Table 8 (all-tenures total) shares this six-column
# "Characteristic" plus employment-status-breakdown signature with two other
# tables on the page — Table 1 (long-tenured, by age/sex/race) and Table 3
# (long-tenured, by advance notice) — so no heading text picks it out alone; see
# _select_total_table. The reason and area-of-residence tables carry different
# breakdown columns (by reason for job loss, by census region) and never match.
_TOTAL_TABLE_SIGNATURE_PATTERNS = (r"^characteristic", r"^total$", r"employed", r"unemployed", r"not in (?:the )?labor force")

# Table 8 has always carried this many rows (one "Total, 20 years and over" row
# plus its age/sex/race/ethnicity breakdown) in every archived and current
# release checked so far. Corroborating evidence only, per _select_total_table —
# never the primary selector, since a row-count match alone cannot distinguish
# Table 8 from the other same-signature tables.
_EXPECTED_TOTAL_TABLE_ROW_COUNT = 59


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


def _parse_archived_period(archive_html: str) -> tuple[int, int]:
    """Read the three-year displacement window (period_start_year, period_end_year) from an archived release's text.

    Unlike the current release, an archived release's survey year is supplied by the
    caller of `parse_archived_release` — the January in which BLS conducted that
    survey — rather than derived here. The window does not equal that year: the
    archive published as `disp_2018.html` (page title "2017 A01 Results") reports
    displacement between January 2015 and December 2017, not 2018 itself.
    """
    release_text = re.sub(r"<[^>]*>", " ", archive_html)
    release_text = re.sub(r"\s+", " ", release_text)

    window_match = re.search(r"between January (\d{4}) and December (\d{4})", release_text)
    if window_match is None:
        raise ValueError("could not read the displacement window from the archived release")

    return int(window_match.group(1)), int(window_match.group(2))


def _read_flattened_tables(archive_html: str) -> list[pd.DataFrame]:
    """Every inline `<table>` on the page, each with `_flatten_columns` already applied.

    Returns an empty list — rather than letting `pandas.read_html` raise — when the
    page carries no `<table>` elements at all. Five of the nine archived releases
    (2008–2016) lay their tables out as plain-text `<PRE>` blocks; those are out of
    scope for this parser, and the caller treats an empty list as "nothing here to
    parse" rather than a failure.
    """
    try:
        return [_flatten_columns(candidate_df) for candidate_df in pd.read_html(io.StringIO(archive_html))]
    except ValueError:
        return []


def _select_table_by_heading(candidate_tables: list[pd.DataFrame], heading_text: str) -> pd.DataFrame | None:
    """The table any of whose flattened columns contain heading_text, or None.

    Archived releases carry every table inline on one page and the ordering is not
    guaranteed stable across sixteen years of releases, so tables are selected by
    what they contain rather than by index. The heading text does not always land in
    the first column: "Reason for job loss" appears only inside the second-header-row
    labels ("Percent distribution by reason for job loss ..."), never as a first
    column header on its own, so every column is checked rather than just the first.
    """
    for candidate_df in candidate_tables:
        if any(heading_text.lower() in str(column).lower() for column in candidate_df.columns):
            return candidate_df
    return None


def _has_total_table_signature(candidate_df: pd.DataFrame) -> bool:
    """True if candidate_df carries Table 8's six-column "Characteristic" plus
    employment-status-breakdown signature — see `_TOTAL_TABLE_SIGNATURE_PATTERNS`.
    """
    return all(any(re.search(pattern, column) for column in candidate_df.columns) for pattern in _TOTAL_TABLE_SIGNATURE_PATTERNS)


def _table5_long_tenured_total(occupation_table_df: pd.DataFrame) -> float:
    """Table 5's own published long-tenured total (its "Total, ..." row), read the
    same way `_occupation_rows` reads it — `startswith("total,")`, tolerating a
    footnote marker appended straight onto the label. This is the baseline
    `_select_total_table`'s invariant compares each same-signature candidate against:
    the true long-tenured population, not the ten leaf groups' sum, which
    `_occupation_rows` already establishes omits a small unclassified residual (see
    LEAF_COVERAGE_TOLERANCE) and so would sit close enough to Table 1's own
    long-tenured grand total to leave the two indistinguishable by magnitude alone.
    """
    occupation_column = _find_column(occupation_table_df, r"occupation of lost job")
    total_column = _find_column(occupation_table_df, r"^total$")
    return pd.to_numeric(
        occupation_table_df.loc[
            occupation_table_df[occupation_column].astype(str).str.strip().str.lower().str.startswith("total,"),
            total_column,
        ],
        errors="coerce",
    ).max()


def _select_total_table(candidate_tables: list[pd.DataFrame], occupation_table_df: pd.DataFrame, survey_year: int) -> pd.DataFrame | None:
    """Select Table 8 (the all-tenures total) among an archived HTML release's tables.

    Table 8 shares its six-column signature with two other tables on the page — Table
    1 (long-tenured, by age/sex/race) and Table 3 (long-tenured, by advance notice) —
    and no heading text distinguishes any of the three (see the module docstring and
    `_has_total_table_signature`). This was previously left unparsed for exactly that
    reason. It is now selected by a semantic invariant instead of a heuristic:
    all-tenures displacement must exceed long-tenured displacement from the same
    release, so the winning candidate's "Total, 20 years and over" total must exceed
    `_table5_long_tenured_total` — Table 5's own published long-tenured total, the
    authoritative figure for "long-tenured displacement from the same release" (Table
    1 and Table 3 both republish this identical number under their own headings, so
    they tie rather than exceed it and are excluded by the strict inequality; only
    Table 8, which counts short-tenured workers too, actually exceeds it).

    If zero same-signature candidates satisfy the invariant, or more than one does,
    this returns None with a warning naming the survey year, exactly as a missing
    occupation or reason table is skipped elsewhere in this module — a wrong Table 8
    would silently poison the project's default displacement rate, so failing to
    parse is strictly better than guessing. A row count of 59 (`_EXPECTED_TOTAL_TABLE_ROW_COUNT`,
    matching the current release's own Table 8) is checked only as corroboration once a
    unique candidate is already selected; it never decides which candidate wins.
    """
    long_tenured_total = _table5_long_tenured_total(occupation_table_df)
    invariant_satisfying_tables: list[pd.DataFrame] = []

    for candidate_df in candidate_tables:
        if not _has_total_table_signature(candidate_df):
            continue
        characteristic_column = _find_column(candidate_df, r"^characteristic")
        total_column = _find_column(candidate_df, r"^total$")
        total_rows = candidate_df[
            candidate_df[characteristic_column].astype(str).str.strip().str.lower().str.startswith("total, 20 years and over")
        ]
        if total_rows.empty:
            continue
        candidate_total = pd.to_numeric(total_rows.iloc[0][total_column], errors="coerce")
        if pd.notna(candidate_total) and candidate_total > long_tenured_total:
            invariant_satisfying_tables.append(candidate_df)

    if len(invariant_satisfying_tables) != 1:
        print(
            f"  ⚠ Could not uniquely identify Table 8 (all-tenures total) in the {survey_year} archived release — "
            f"{len(invariant_satisfying_tables)} same-signature candidates exceeded the long-tenured baseline "
            f"({long_tenured_total:,.0f}); skipping the all-tenures row rather than guessing."
        )
        return None

    selected_total_table = invariant_satisfying_tables[0]
    characteristic_column = _find_column(selected_total_table, r"^characteristic")
    total_column = _find_column(selected_total_table, r"^total$")
    selected_total = pd.to_numeric(
        selected_total_table[
            selected_total_table[characteristic_column].astype(str).str.strip().str.lower().str.startswith("total, 20 years and over")
        ].iloc[0][total_column],
        errors="coerce",
    )
    assert selected_total > long_tenured_total, "the selected Table 8 candidate must exceed the long-tenured baseline"

    if len(selected_total_table) != _EXPECTED_TOTAL_TABLE_ROW_COUNT:
        print(
            f"  ⚠ Table 8 in the {survey_year} archived release has {len(selected_total_table)} rows, not the "
            f"expected {_EXPECTED_TOTAL_TABLE_ROW_COUNT} — keeping it since the long-tenured-total invariant "
            f"still uniquely selected it."
        )
    return selected_total_table


def parse_archived_release(archive_html: str, survey_year: int) -> pd.DataFrame:
    """Every panel row an archived release can supply, in the committed panel's schema.

    Mirrors the current-release parser's occupation, reason, and all-tenures output so
    all three accumulate into one seed: leaf occupation rows from the occupation table
    (Table 5), the three reason rows (Table 2), and the single all-tenures total
    analogous to Table 8 — all selected out of the page's inline tables rather than a
    fixed index, since ordering is not guaranteed stable across sixteen years of
    releases. The occupation and reason tables are selected by heading text
    (`_select_table_by_heading`); Table 8 cannot be, because it shares its column
    signature with two other tables on the page and no heading distinguishes any of
    the three, so it is instead selected by the semantic invariant in
    `_select_total_table` — its total must exceed Table 5's own published
    long-tenured total, which the same-signature tables merely repeat rather than
    exceed. That invariant is asserted once a unique candidate is chosen, and the
    table is skipped with a warning (rather than guessed) if zero or more than one
    candidate satisfies it, or if there is no occupation table to read the baseline
    from at all.

    Dispatches to `parse_archived_text_release` when the page carries no inline
    HTML `<table>` elements at all — the five 2008-2016 archives, which lay their
    tables out as plain-text `<PRE>` blocks instead — so a caller looping over
    every archived release gets parsed rows for all nine rather than having to
    special-case the plain-text layout itself.
    """
    candidate_tables = _read_flattened_tables(archive_html)
    if not candidate_tables:
        return parse_archived_text_release(archive_html, survey_year)

    parsed_frames: list[pd.DataFrame] = []
    occupation_table = _select_table_by_heading(candidate_tables, "Occupation of lost job")
    if occupation_table is not None:
        parsed_frames.append(_occupation_rows(occupation_table))
    reason_table = _select_table_by_heading(candidate_tables, "Reason for job loss")
    if reason_table is not None:
        parsed_frames.append(_reason_rows(reason_table))
    if occupation_table is not None:
        total_table = _select_total_table(candidate_tables, occupation_table, survey_year)
        if total_table is not None:
            parsed_frames.append(_total_rows(total_table))

    if not parsed_frames:
        print(f"  ⚠ No occupation or reason table found in the {survey_year} archived release; skipping.")
        return pd.DataFrame(columns=PANEL_COLUMNS)

    release_panel_df = pd.concat(parsed_frames, ignore_index=True)
    period_start_year, period_end_year = _parse_archived_period(archive_html)
    release_panel_df["survey_year"] = survey_year
    release_panel_df["period_start_year"] = period_start_year
    release_panel_df["period_end_year"] = period_end_year
    release_panel_df["period_years"] = period_end_year - period_start_year + 1
    release_panel_df["source"] = "news_release_archive"
    return release_panel_df[PANEL_COLUMNS]


def _occupation_rows(occupation_table_df: pd.DataFrame) -> pd.DataFrame:
    """Table 5's leaf occupation rows, mapped to SOC major groups.

    Shared by the current-release parser (`parse_occupation_table`, which reads the
    table from its own standalone file) and the archived-release parser
    (`parse_archived_release`, which selects the same table by heading text out of a
    page carrying every table inline), so the leaf-row selection, dash-to-NaN, and
    coverage checks live in one place.
    """
    verify_soc_coverage()

    occupation_column = _find_column(occupation_table_df, r"occupation of lost job")
    total_column = _find_column(occupation_table_df, r"^total$")

    occupation_df = occupation_table_df[[occupation_column, total_column]].copy()
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
    occupation_df["mlr_occupation"] = ""
    occupation_df["displacement_rate_percent"] = float("nan")
    occupation_df["measurement_basis"] = COUNT_MEASUREMENT_BASIS
    return occupation_df


def parse_occupation_table(release_html_path: str) -> pd.DataFrame:
    """Parse Table 5 into one row per leaf occupation group, mapped to SOC major groups."""
    release_df = _flatten_columns(pd.read_html(release_html_path, flavor="bs4")[0])
    return _occupation_rows(release_df)


def _reason_rows(reason_table_df: pd.DataFrame) -> pd.DataFrame:
    """Table 2's three reason-for-job-loss rows, as counts rather than percentages.

    The release publishes reasons as a percent distribution over the long-tenured
    total; those percentages are converted to counts here so every panel row carries
    the same unit. Shared by the current-release parser (`parse_reason_table`) and
    the archived-release parser (`parse_archived_release`).
    """
    characteristic_column = _find_column(reason_table_df, r"^characteristic")
    total_column = _find_column(reason_table_df, r"^total$")

    all_worker_rows = reason_table_df[
        reason_table_df[characteristic_column].astype(str).str.strip().str.lower() == "total, 20 years and over"
    ]
    if all_worker_rows.empty:
        raise ValueError("reason table has no 'Total, 20 years and over' row")
    # The first such row is the all-workers total; the later ones break out men and women.
    total_row = all_worker_rows.iloc[0]
    displaced_total = pd.to_numeric(total_row[total_column], errors="coerce")

    reason_rows = []
    for reason_label, column_pattern in REASON_COLUMN_PATTERNS.items():
        reason_percent = pd.to_numeric(total_row[_find_column(reason_table_df, column_pattern)], errors="coerce")
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
                "mlr_occupation": "",
                "displacement_rate_percent": float("nan"),
                "measurement_basis": COUNT_MEASUREMENT_BASIS,
            }
        )
    return pd.DataFrame(reason_rows)


def parse_reason_table(release_html_path: str) -> pd.DataFrame:
    """Parse Table 2 into one row per reason for job loss, as counts rather than percentages."""
    release_df = _flatten_columns(pd.read_html(release_html_path, flavor="bs4")[0])
    return _reason_rows(release_df)


def _archive_pre_blocks(archive_html: str) -> list[str]:
    """Every `<PRE>` block's text on an archived release page, HTML entities decoded, in document order.

    The five 2008-2016 archives lay every table out as one plain-text `<PRE>`
    block per table rather than as HTML `<table>` elements, so this is the
    plain-text analogue of `_read_flattened_tables`.
    """
    return [html.unescape(pre_block_text) for pre_block_text in re.findall(r"<pre[^>]*>(.*?)</pre>", archive_html, re.S | re.I)]


def _select_pre_block(pre_blocks: list[str], caption_text: str, exclude_text: str | None = None) -> str | None:
    """The first pre block whose caption contains caption_text and, if given, not exclude_text.

    Only the caption — the block's first 400 characters, with whitespace runs
    collapsed to one space so a phrase wrapped across two physical lines still
    reads as one string — is searched, not the whole block. "reason for job loss"
    also appears deep inside unrelated tables (a row-group label in Table 6 and
    Table 8, a repeated column header in Table 2 itself), so searching the whole
    block finds too many matches; restricting the search to the caption and, for
    the reason table, excluding Table 3's competing caption phrase ("...advance
    notice, reason for job loss...") is what makes the match unique. Selection is
    always by this caption content, never by the block's position on the page,
    which is not guaranteed stable across sixteen years of releases.
    """
    for pre_block_text in pre_blocks:
        caption = re.sub(r"\s+", " ", pre_block_text[:400]).strip().lower()
        if caption_text in caption and (exclude_text is None or exclude_text not in caption):
            return pre_block_text
    return None


def _parse_pre_table_rows(pre_block_text: str) -> list[tuple[str, list[str]]]:
    """Every (row_label, numeric_tokens) row in a `<PRE>`-formatted table block.

    Dot leaders pad a row label out to its numbers column
    (`Service occupations.............`); those are collapsed to a single space
    first with `_DOT_LEADER_PATTERN`, and each line is then split on runs of two
    or more whitespace characters with `_WHITESPACE_RUN_PATTERN` — never a fixed
    character offset, which the repo's trailing-whitespace-stripping pre-commit
    hook could silently break for a column-position-dependent parser.

    A label too long for the label column wraps onto its own line with no
    numbers at all (`Management, business, and financial operations\\n   occupations
    ....`); such a line is buffered as a pending label fragment and prefixed onto
    the label of the next line that does carry numbers, so the two physical lines
    recombine into one row.
    """
    pending_label_fragment = ""
    parsed_rows: list[tuple[str, list[str]]] = []
    for raw_line in pre_block_text.split("\n"):
        line = _DOT_LEADER_PATTERN.sub(" ", raw_line).strip()
        if not line:
            pending_label_fragment = ""
            continue
        line_tokens = _WHITESPACE_RUN_PATTERN.split(line)
        if len(line_tokens) >= 2 and _PRE_TABLE_NUMERIC_TOKEN_PATTERN.fullmatch(line_tokens[1]):
            row_label = f"{pending_label_fragment} {line_tokens[0]}".strip() if pending_label_fragment else line_tokens[0]
            parsed_rows.append((row_label, line_tokens[1:]))
            pending_label_fragment = ""
        elif len(line_tokens) == 1:
            pending_label_fragment = f"{pending_label_fragment} {line_tokens[0]}".strip() if pending_label_fragment else line_tokens[0]
        else:
            pending_label_fragment = ""
    return parsed_rows


def _pre_table_count_string(numeric_token: str) -> str:
    """Strip thousands-separator commas from a `<PRE>`-table numeric token, leaving a suppressed dash as-is.

    `pandas.read_html` strips comma thousands separators automatically when it
    parses an HTML `<table>`; the rows `_parse_pre_table_rows` recovers bypass
    `read_html` entirely, so this stands in for that step. Without it,
    `pd.to_numeric` inside `_occupation_rows` / `_reason_rows` would coerce
    "3,191" to NaN rather than 3191 — comma-separated, not truncated at the comma.
    """
    return numeric_token if numeric_token == "-" else numeric_token.replace(",", "")


def parse_archived_text_release(archive_html: str, survey_year: int) -> pd.DataFrame:
    """Parse a plain-text `<PRE>`-block archived DWS release (2008-2016) into panel rows.

    Reconstructs, out of the plain text, the same column shape `_occupation_rows`,
    `_reason_rows`, and `_total_rows` already expect from an HTML table — column
    names chosen to satisfy the regex patterns those helpers search for
    (`"occupation of lost job"` / `"total"` for the occupation table;
    `"characteristic"` / `"total"` plus each `REASON_COLUMN_PATTERNS` phrase for the
    reason table; `"characteristic"` / `"total"` again for the all-tenures table) —
    then calls them, so leaf selection, dash-to-NaN, SOC mapping, and the coverage
    check live in one place rather than being duplicated here.

    Only the reason table's first "Total, 20 years and over" row is used — the
    same row the HTML-table path takes via `_reason_rows`' own first-match logic —
    since the release repeats that label for the Men and Women breakdowns beneath
    it. The five numeric tokens on that row are, in publication order, the total
    count, the (redundant) 100.0% total, and the plant/insufficient-work/position
    percentages; that order is stable across all five plain-text archives.

    Table 8's own "Total, 20 years and over" row needs none of the HTML path's
    same-signature disambiguation (`_select_total_table`): its caption ("Table 8.
    Total displaced workers...") is unique among the page's `<PRE>` captions, so
    `_select_pre_block` finds it directly, the same way it already finds the
    occupation and reason blocks.

    Returns an empty, correctly-columned frame with a warning printed to stdout
    when none of the three tables can be found on the page, so a caller looping
    over every archived release can treat that as "nothing to parse" rather than a
    failure.
    """
    pre_blocks = _archive_pre_blocks(archive_html)
    parsed_frames: list[pd.DataFrame] = []

    occupation_block = _select_pre_block(pre_blocks, "by occupation of lost job")
    if occupation_block is not None:
        occupation_table_df = pd.DataFrame(
            [
                (row_label, _pre_table_count_string(numeric_tokens[0]))
                for row_label, numeric_tokens in _parse_pre_table_rows(occupation_block)
            ],
            columns=["occupation of lost job", "total"],
        )
        parsed_frames.append(_occupation_rows(occupation_table_df))

    reason_block = _select_pre_block(pre_blocks, "reason for job loss", exclude_text="advance notice")
    if reason_block is not None:
        total_row = next(
            (
                numeric_tokens
                for row_label, numeric_tokens in _parse_pre_table_rows(reason_block)
                if row_label.lower().startswith("total, 20 years and over")
            ),
            None,
        )
        if total_row is not None and len(total_row) >= 5:
            reason_table_df = pd.DataFrame(
                [
                    {
                        "characteristic": "Total, 20 years and over",
                        "total": _pre_table_count_string(total_row[0]),
                        "plant or company closed down or moved": total_row[2],
                        "insufficient work": total_row[3],
                        "position or shift abolished": total_row[4],
                    }
                ]
            )
            parsed_frames.append(_reason_rows(reason_table_df))

    total_block = _select_pre_block(pre_blocks, "table 8.")
    if total_block is not None:
        total_row = next(
            (
                numeric_tokens
                for row_label, numeric_tokens in _parse_pre_table_rows(total_block)
                if row_label.lower().startswith("total, 20 years and over")
            ),
            None,
        )
        if total_row is not None:
            total_table_df = pd.DataFrame([{"characteristic": "Total, 20 years and over", "total": _pre_table_count_string(total_row[0])}])
            parsed_frames.append(_total_rows(total_table_df))

    if not parsed_frames:
        print(f"  ⚠ No occupation, reason, or total table found in the {survey_year} archived plain-text release; skipping.")
        return pd.DataFrame(columns=PANEL_COLUMNS)

    release_panel_df = pd.concat(parsed_frames, ignore_index=True)
    period_start_year, period_end_year = _parse_archived_period(archive_html)
    release_panel_df["survey_year"] = survey_year
    release_panel_df["period_start_year"] = period_start_year
    release_panel_df["period_end_year"] = period_end_year
    release_panel_df["period_years"] = period_end_year - period_start_year + 1
    release_panel_df["source"] = "news_release_archive"
    return release_panel_df[PANEL_COLUMNS]


def _total_rows(total_table_df: pd.DataFrame) -> pd.DataFrame:
    """Table 8's single all-tenures displacement total, in the panel's row shape.

    Shared by the current-release parser (`parse_total_table`, which reads the table
    from its own standalone file) and both archived-release parsers —
    `parse_archived_text_release`, which reconstructs the same column shape out of a
    plain-text `<PRE>` block, and `parse_archived_release`'s HTML-table path, which
    selects the table via `_select_total_table` — so the row shape lives in one place.

    Matched by `startswith` rather than an exact match on "total, 20 years and over",
    because an archived release's Table 8 (and the same-signature tables
    `_select_total_table` compares it against) sometimes appends a footnote marker
    directly onto that label with no separating space ("...and over(2)"); this is the
    same tolerance `_occupation_rows` already applies to Table 5's own total row.
    """
    characteristic_column = _find_column(total_table_df, r"^characteristic")
    total_column = _find_column(total_table_df, r"^total$")

    all_worker_rows = total_table_df[
        total_table_df[characteristic_column].astype(str).str.strip().str.lower().str.startswith("total, 20 years and over")
    ]
    if all_worker_rows.empty:
        raise ValueError("Table 8 has no 'Total, 20 years and over' row")

    return pd.DataFrame(
        [
            {
                "group_name": "Total, 20 years and over",
                "soc_majors": "",
                "displaced_thousands": pd.to_numeric(all_worker_rows.iloc[0][total_column], errors="coerce"),
                "source_table": "table_8_all_tenures",
                "reason": "all",
                "tenure_class": "all_tenures",
                "mlr_occupation": "",
                "displacement_rate_percent": float("nan"),
                "measurement_basis": COUNT_MEASUREMENT_BASIS,
            }
        ]
    )


def parse_total_table(release_html_path: str) -> pd.DataFrame:
    """Parse Table 8 into the single all-tenures displacement total."""
    release_df = _flatten_columns(pd.read_html(release_html_path, flavor="bs4")[0])
    try:
        return _total_rows(release_df)
    except ValueError as total_row_error:
        raise ValueError(f"{total_row_error} in {release_html_path}") from total_row_error


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
    release_panel_df["source"] = "news_release"
    return release_panel_df[PANEL_COLUMNS]


def merge_panel(existing_panel_df: pd.DataFrame, new_release_df: pd.DataFrame) -> pd.DataFrame:
    """Merge a freshly parsed release into the accumulated panel, the new release winning ties.

    `mlr_occupation` is part of the dedup key alongside the original five columns
    because four DWS groups each receive two MLR leaf rows sharing every other
    key column (see mlr_rows_for_panel) — without it, this drop_duplicates would
    silently collapse one of every colliding pair on every merge.
    """
    combined_panel_df = pd.concat([existing_panel_df, new_release_df], ignore_index=True)
    combined_panel_df = combined_panel_df.drop_duplicates(
        subset=["survey_year", "source_table", "group_name", "reason", "tenure_class", "mlr_occupation"], keep="last"
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
        existing_panel_df = pd.read_csv(seed_path, dtype={"soc_majors": str, "mlr_occupation": str}).fillna(
            {"soc_majors": "", "mlr_occupation": ""}
        )

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


def mlr_rows_for_panel(rate_df: pd.DataFrame) -> pd.DataFrame:
    """Reshape parse_displacement_rate_table output into DWS panel rows.

    Emits one row per (period, MLR occupation leaf) — NOT one row per (period, DWS
    group) — because four DWS groups each receive two MLR leaves (professional and
    related occupations gets Professional specialty and Technicians and related
    support; service occupations gets Protective services and Other service
    occupations; production occupations gets Other precision production
    occupations and Machine operators, assemblers, and inspectors; transportation
    and material moving occupations gets Transportation and material-moving
    occupations and Handlers, equipment cleaners, helpers, and laborers). These
    are rates, so they cannot be summed, and averaging them would need employment
    weights the MLR tables never published — an unweighted mean would be a
    fabricated number baked into a committed seed. `group_name` carries the
    crosswalked DWS group so these rows sit beside the archive rows' occupation
    groups; the new `mlr_occupation` column preserves the native 1980-census
    label so the colliding pairs stay visible in the data rather than silently
    merged, leaving the weighting decision to whichever consumer eventually needs
    one group-level number.

    `survey_year` is `period_end_year + 1` — the same rule the modern archive rows
    already follow (a 2026 survey covers 2023-2025, a 2008 survey covers
    2005-2007), so one derivation covers the whole panel. It is a panel key, not a
    literal fieldwork date for these pre-2008 periods: the real mid-1990s DWS
    surveys used a recall window longer than three years, and the true period is
    always in `period_start_year` / `period_end_year`, not in `survey_year`.

    Raises ValueError if any mlr_occupation in rate_df has no entry in
    mlr_to_dws_group(), rather than silently dropping an occupation from the panel.
    """
    panel_rows_df = rate_df.copy()

    panel_rows_df["group_name"] = panel_rows_df["mlr_occupation"].map(mlr_to_dws_group())
    unmapped_occupations = sorted(panel_rows_df.loc[panel_rows_df["group_name"].isna(), "mlr_occupation"].unique())
    if unmapped_occupations:
        raise ValueError(f"No DWS group crosswalk entry for MLR occupations: {unmapped_occupations}")

    panel_rows_df["soc_majors"] = panel_rows_df["group_name"].map(lambda dws_group: "|".join(DWS_TO_SOC_MAJOR[dws_group]))
    panel_rows_df["survey_year"] = panel_rows_df["period_end_year"] + 1
    panel_rows_df["period_years"] = panel_rows_df["period_end_year"] - panel_rows_df["period_start_year"] + 1
    panel_rows_df["source_table"] = "mlr_table_2_occupation"
    panel_rows_df["tenure_class"] = "long_tenured"
    panel_rows_df["reason"] = "all"
    panel_rows_df["displaced_thousands"] = float("nan")
    panel_rows_df["measurement_basis"] = RATE_MEASUREMENT_BASIS
    panel_rows_df["source"] = "mlr_article"

    return panel_rows_df[PANEL_COLUMNS]
