"""Parses Displaced Worker Supplement occupation displacement rates out of MLR article PDFs.

Table 2 of each biennial Monthly Labor Review displaced-worker article reports the
displacement rate of long-tenured workers by occupation, for eight or more two-year survey
periods. This module locates that table inside an already-downloaded article PDF (see
`download_dws.py`, which saves articles to `data/raw/dws/mlr/`) and parses its leaf
occupation rows into a long-form DataFrame, extending displacement-rate history back before
the Displaced Worker Supplement panel's 2008 archive coverage begins.

Inputs:
  • an MLR article PDF path, read with `pdfplumber`
  • seeds/mlr_occupation_crosswalk.csv  (committed reference data, read by `load_mlr_crosswalk`)

Outputs:
  • `parse_displacement_rate_table` returns a DataFrame with columns
    `period_label, period_start_year, period_end_year, mlr_occupation, displacement_rate_percent`,
    restricted to the leaf occupation rows named in `MLR_OCCUPATION_LEAVES`.
  • `parse_total_displacement_rate` returns a DataFrame with columns
    `period_label, period_start_year, period_end_year, displacement_rate_percent` for
    Table 2's economy-wide "Total, 20 years and older" row — consumed by
    `historical_displacement.mlr_displacement_rate` as a displacement-rate D source
    distinct from (never spliced onto) the DWS count-derived sources.
  • `load_mlr_crosswalk` / `mlr_to_dws_group` — the 1980-census-to-modern-DWS-group
    crosswalk, consumed by `dws_panel.mlr_rows_for_panel` to fold these rates into
    the DWS displacement panel.
"""

import re

import pandas as pd
import pdfplumber

# Table 2's occupation block is a hierarchy (White-collar / Service / Blue-collar
# occupations, each summing their own children's displaced-worker counts), and text
# extraction destroys the indentation that would otherwise reveal that structure. These are
# the leaf rows only, worded exactly as the 1999 article (`mid_1990s_1999.pdf`) prints them —
# the canonical spelling emitted in the output `mlr_occupation` column regardless of which
# article a row was matched from. Selecting by normalised-label membership rather than by
# position: an aggregate row double-counts its children's displaced workers if it is treated
# as an independent occupation alongside them.
MLR_OCCUPATION_LEAVES = (
    "Executive, administrative, and managerial",
    "Professional specialty",
    "Technicians and related support",
    "Sales occupations",
    "Administrative support, including clerical",
    "Protective services",
    "Other service occupations",
    "Mechanics and repairers",
    "Construction trades",
    "Other precision production occupations",
    "Machine operators, assemblers, and inspectors",
    "Transportation and material-moving occupations",
    "Handlers, equipment cleaners, helpers, and laborers",
    "Farming, forestry, and fishing",
)

# Anchored on the caption itself ("Table 2. Displacement rates of long-tenured
# workers..."), not a bare "Table 2" substring: MLR prose style lowercases its own
# cross-references ("table 2"), so the risk of a false match today is low, but an
# unanchored substring would still match "Table 2" inside a prose cross-reference
# on an earlier page before ever reaching the caption page, and the failure would
# be silent — the wrong page just happens not to carry a "Characteristic" header,
# or worse, happens to carry unrelated numbers that get parsed as Table 2's own.
_TABLE_CAPTION_PATTERN = re.compile(r"^\s*Table 2\.", re.MULTILINE)
_DOT_LEADER_PATTERN = re.compile(r"\.{2,}")
_SUPERSCRIPT_PATTERN = re.compile(r"[¹²³⁰-⁹]+")
_NUMBER_TOKEN_PATTERN = re.compile(r"\.?\d+(?:\.\d+)?")
_PERIOD_TOKEN_PATTERN = re.compile(r"(\d{4})[‐‑‒–—-](\d{2,4})")
_WHITESPACE_RUN_PATTERN = re.compile(r"\s+")


def _normalize_occupation_key(occupation_label: str) -> str:
    """Fold an occupation label to a comparison key robust to inter-article wording drift.

    Every MLR article re-typesets Table 2's occupation labels, and each new article examined so
    far has introduced its own small drift from the 1999 article's wording that
    `MLR_OCCUPATION_LEAVES` is worded from — a dropped comma (`Executive, administrative and
    managerial` in the 2001 article), a hyphen rendered as a space (`Transportation and material
    moving occupations` in the 2001 and 2004 articles). Rather than enumerate each variant as it
    turns up, both the canonical leaf labels and every article's row labels are folded through
    this key before comparison: lowercased, with hyphens and commas neutralised to spaces (since
    both are used inconsistently as separators across articles) and whitespace runs collapsed.
    """
    normalized_text = occupation_label.lower().replace("-", " ").replace(",", " ")
    return _WHITESPACE_RUN_PATTERN.sub(" ", normalized_text).strip()


def _build_leaf_key_to_canonical_label() -> dict[str, str]:
    """Map each leaf's normalised key back to its canonical (1999-article) spelling.

    A row matched under a drifted spelling from a later article is still emitted with one
    consistent label. Guards against two distinct leaves normalising to the same key — that
    would silently merge two occupation groups, which is worse than the wording-drift gap this
    mapping fixes — by inserting one leaf at a time and checking for a pre-existing key, rather
    than a dict comprehension, which would silently keep only one of a colliding pair.
    """
    leaf_key_to_canonical_label: dict[str, str] = {}
    for leaf_label in MLR_OCCUPATION_LEAVES:
        leaf_key = _normalize_occupation_key(leaf_label)
        if leaf_key in leaf_key_to_canonical_label:
            raise ValueError(
                f"Normalised occupation key {leaf_key!r} collides between {leaf_key_to_canonical_label[leaf_key]!r} and {leaf_label!r}"
            )
        leaf_key_to_canonical_label[leaf_key] = leaf_label
    return leaf_key_to_canonical_label


_LEAF_KEY_TO_CANONICAL_LABEL = _build_leaf_key_to_canonical_label()

# Crosswalk from the 1980-census occupational taxonomy (MLR_OCCUPATION_LEAVES) to the ten
# modern DWS groups (dws_panel.DWS_TO_SOC_MAJOR keys). Committed reference data, following the
# pattern harmonize_soc.py uses for seeds/soc_crosswalks/: a static, hand-derived correspondence
# rather than something downloaded or recomputed at run time.
MLR_CROSSWALK_PATH = "seeds/mlr_occupation_crosswalk.csv"
MLR_CROSSWALK_COLUMNS = ["mlr_occupation", "dws_group", "mapping_confidence", "note"]


def load_mlr_crosswalk(path: str = MLR_CROSSWALK_PATH) -> pd.DataFrame:
    """Load the 1980-census-to-DWS-group crosswalk seed, one row per MLR_OCCUPATION_LEAVES entry."""
    crosswalk_df = pd.read_csv(path)
    missing_columns = [column for column in MLR_CROSSWALK_COLUMNS if column not in crosswalk_df.columns]
    if missing_columns:
        raise ValueError(f"{path} lacks columns {missing_columns}")
    return crosswalk_df[MLR_CROSSWALK_COLUMNS]


def mlr_to_dws_group(path: str = MLR_CROSSWALK_PATH) -> dict[str, str]:
    """Build the 1980-census-to-DWS-group lookup from the crosswalk seed, at call time.

    Read fresh on every call rather than cached at import — the same choice
    `harmonize_soc.load_aggregate_codes` makes for its own seed file. Building this
    at import time instead (an earlier version of this module did) made `import
    dws_panel` — and transitively `historical_displacement` and
    `composition_displacement_validation` — raise `FileNotFoundError` from any
    working directory other than the repo root, since the whole project otherwise
    assumes cwd=root throughout. The crosswalk is small (14 rows), so re-reading it
    on each call costs nothing worth caching against.
    """
    crosswalk_df = load_mlr_crosswalk(path)
    return dict(zip(crosswalk_df["mlr_occupation"], crosswalk_df["dws_group"]))


def _strip_footnote_superscripts(text: str) -> str:
    """Remove unicode superscript footnote markers glued to labels and period headers."""
    return _SUPERSCRIPT_PATTERN.sub("", text)


def _normalize_period_end_suffix(end_suffix: str) -> str:
    """Undo a footnote marker rendered as a plain digit glued onto a two-digit year suffix.

    A valid suffix is always two digits (e.g. "82") or four (e.g. "2000"). A three-digit
    match can only be a genuine two-digit suffix with a footnote marker glued onto it that
    did not extract as a unicode superscript — observed in the 2004 article, where footnote
    1 glues onto "1991-92" in the header as "1991-921".
    """
    if len(end_suffix) in (2, 4):
        return end_suffix
    if len(end_suffix) == 3:
        return end_suffix[:2]
    raise ValueError(f"Unexpected period end-year suffix {end_suffix!r}; cannot disambiguate from a footnote marker")


def _expand_period_end_year(period_start_year: int, end_suffix: str) -> int:
    """Expand a two- or four-digit end-year suffix to a full four-digit year."""
    if len(end_suffix) == 4:
        return int(end_suffix)
    century = (period_start_year // 100) * 100
    period_end_year = century + int(end_suffix)
    if period_end_year <= period_start_year:
        period_end_year += 100
    return period_end_year


def _parse_period_header(header_line: str) -> list[tuple[str, int, int]]:
    """Parse the `Characteristic 1981-82 1983-84 ...` header line into period metadata.

    Returns a list of `(period_label, period_start_year, period_end_year)` tuples, in column
    order, with the period label normalised to an ASCII hyphen regardless of the source
    en dash.
    """
    stripped_line = _strip_footnote_superscripts(header_line)
    periods = []
    for match in _PERIOD_TOKEN_PATTERN.finditer(stripped_line):
        period_start_year = int(match.group(1))
        end_suffix = _normalize_period_end_suffix(match.group(2))
        period_end_year = _expand_period_end_year(period_start_year, end_suffix)
        period_label = f"{period_start_year}-{end_suffix}"
        periods.append((period_label, period_start_year, period_end_year))
    return periods


def _find_table_page_text(article_pdf_path: str) -> str:
    """Return the extracted text of the page whose caption identifies it as Table 2."""
    with pdfplumber.open(article_pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            if _TABLE_CAPTION_PATTERN.search(page_text):
                return page_text
    raise ValueError(f"No page containing a Table 2 caption found in {article_pdf_path}")


def _locate_periods_and_data_lines_from_text(
    page_text: str, source_label: str = "<extracted text>"
) -> tuple[list[tuple[str, int, int]], list[str]]:
    """Find Table 2's period header in an already-extracted page's text and return the periods plus the lines after it.

    This is the PDF-independent half of `_locate_periods_and_data_lines`: it does
    the actual fragile parsing (locating the header row, decoding period labels,
    handling dot leaders and wrapped labels via `_iter_table_rows`) without ever
    calling `pdfplumber`. Split out specifically so that parsing can be exercised
    in tests against a committed plain-text fixture of a real extracted page
    (`tests/fixtures/mlr_table2_1999_article.txt`) — this parser's zero CI
    coverage was a Minor finding in the 2026-09-15 final review, since all
    real-PDF tests `skipif` on files CI never downloads.

    Shared by `parse_displacement_rate_table` (the leaf occupation rows) and
    `parse_total_displacement_rate` (the economy-wide total row): both tables are
    the same page, the same header, and the same row-continuation format, so both
    parse from this one pass rather than each re-finding the header.
    """
    lines = page_text.splitlines()

    header_line_index = next((index for index, line in enumerate(lines) if line.strip().startswith("Characteristic")), None)
    if header_line_index is None:
        raise ValueError(f"No 'Characteristic ...' header row found in the Table 2 page of {source_label}")
    periods = _parse_period_header(lines[header_line_index])
    if len(periods) == 0:
        raise ValueError(f"Parsed zero periods from the header row of {source_label}")
    return periods, lines[header_line_index + 1 :]


def _locate_periods_and_data_lines(article_pdf_path: str) -> tuple[list[tuple[str, int, int]], list[str]]:
    """Find Table 2's period header on the caption page of a PDF and return the periods plus the lines after it.

    A thin wrapper around `_locate_periods_and_data_lines_from_text`: this
    function's own job is only the PDF-specific page lookup (`_find_table_page_text`,
    which requires `pdfplumber` and a real PDF file); the parsing itself is the
    pure function above.
    """
    page_text = _find_table_page_text(article_pdf_path)
    return _locate_periods_and_data_lines_from_text(page_text, source_label=article_pdf_path)


def _iter_table_rows(data_lines: list[str], period_count: int) -> list[tuple[str, list[str]]]:
    """Parse Table 2's rows into (occupation_label, value_tokens) pairs.

    A row's label sometimes wraps onto its own line ahead of the line carrying its
    values (a section header, a wrapped label's first line, or footnote prose); such
    a label-only line is carried forward in `pending_label_fragment` and prepended to
    the next line that does parse as data — one that has at least one label token
    ahead of its `period_count` trailing numeric tokens.
    """
    rows: list[tuple[str, list[str]]] = []
    pending_label_fragment = ""
    for line in data_lines:
        cleaned_line = _strip_footnote_superscripts(_DOT_LEADER_PATTERN.sub(" ", line))
        tokens = cleaned_line.split()

        if len(tokens) <= period_count or not all(_NUMBER_TOKEN_PATTERN.fullmatch(token) for token in tokens[-period_count:]):
            pending_label_fragment = f"{pending_label_fragment} {cleaned_line.strip()}".strip()
            continue

        value_tokens = tokens[-period_count:]
        label_tokens = tokens[:-period_count]
        occupation_label = f"{pending_label_fragment} {' '.join(label_tokens)}".strip().rstrip(".")
        pending_label_fragment = ""
        rows.append((occupation_label, value_tokens))

    return rows


_RATE_TABLE_COLUMNS = [
    "period_label",
    "period_start_year",
    "period_end_year",
    "mlr_occupation",
    "displacement_rate_percent",
]


def _rate_records_from_periods_and_lines(periods: list[tuple[str, int, int]], data_lines: list[str]) -> list[dict[str, str | int | float]]:
    """Match each data line's occupation label against MLR_OCCUPATION_LEAVES and expand it into one record per period.

    The pure row-selection half of `parse_displacement_rate_table`, taking already-located
    periods and data lines rather than a PDF path — shared with
    `parse_displacement_rate_table`'s text-fixture-backed tests
    (tests/test_mlr_displacement.py), so those tests exercise this exact leaf-matching and
    canonicalisation logic rather than a re-implementation of it.
    """
    records = []
    for occupation_label, value_tokens in _iter_table_rows(data_lines, len(periods)):
        canonical_occupation_label = _LEAF_KEY_TO_CANONICAL_LABEL.get(_normalize_occupation_key(occupation_label))
        if canonical_occupation_label is None:
            continue

        displacement_rates = [float(token) for token in value_tokens]
        for (period_label, period_start_year, period_end_year), displacement_rate_percent in zip(periods, displacement_rates):
            records.append(
                {
                    "period_label": period_label,
                    "period_start_year": period_start_year,
                    "period_end_year": period_end_year,
                    "mlr_occupation": canonical_occupation_label,
                    "displacement_rate_percent": displacement_rate_percent,
                }
            )
    return records


def parse_displacement_rate_table(article_pdf_path: str) -> pd.DataFrame:
    """Parse Table 2's leaf occupation rows out of an MLR displaced-worker article PDF.

    Returns a long-form DataFrame with one row per (occupation, period) pair, columns
    `period_label, period_start_year, period_end_year, mlr_occupation,
    displacement_rate_percent`, restricted to the occupations in `MLR_OCCUPATION_LEAVES`
    (matched by normalised label, so a row survives inter-article wording drift) and always
    emitted under that tuple's canonical spelling.
    """
    periods, data_lines = _locate_periods_and_data_lines(article_pdf_path)
    records = _rate_records_from_periods_and_lines(periods, data_lines)
    return pd.DataFrame(records, columns=_RATE_TABLE_COLUMNS)


# Table 2's economy-wide row, immediately under the header and above the White-collar /
# Service / Blue-collar breakdown that MLR_OCCUPATION_LEAVES selects leaves from. Worded
# exactly as all three articles print it (verified identical in mid_1990s_1999.pdf,
# strong_labor_market_2001.pdf and displacement_1999_2000_2004.pdf).
_TOTAL_ROW_LABEL = "Total, 20 years and older"
_TOTAL_ROW_KEY = _normalize_occupation_key(_TOTAL_ROW_LABEL)


def parse_total_displacement_rate(article_pdf_path: str) -> pd.DataFrame:
    """Parse Table 2's economy-wide "Total, 20 years and older" row out of an MLR article PDF.

    This is the displacement rate for all long-tenured workers 20 and older,
    independent of occupation — the source `historical_displacement.mlr_displacement_rate`
    turns into an annual economy-wide D estimate reaching back to 1981. Reuses the same
    header/period location and row-continuation parsing as `parse_displacement_rate_table`
    (via `_locate_periods_and_data_lines` / `_iter_table_rows`) rather than a second parser.

    Returns a DataFrame with one row per period, columns `period_label,
    period_start_year, period_end_year, displacement_rate_percent`. Raises ValueError
    if the total row cannot be found on the Table 2 page.
    """
    periods, data_lines = _locate_periods_and_data_lines(article_pdf_path)

    for occupation_label, value_tokens in _iter_table_rows(data_lines, len(periods)):
        if _normalize_occupation_key(occupation_label) != _TOTAL_ROW_KEY:
            continue

        displacement_rates = [float(token) for token in value_tokens]
        records = [
            {
                "period_label": period_label,
                "period_start_year": period_start_year,
                "period_end_year": period_end_year,
                "displacement_rate_percent": displacement_rate_percent,
            }
            for (period_label, period_start_year, period_end_year), displacement_rate_percent in zip(periods, displacement_rates)
        ]
        return pd.DataFrame(
            records,
            columns=["period_label", "period_start_year", "period_end_year", "displacement_rate_percent"],
        )

    raise ValueError(f"No {_TOTAL_ROW_LABEL!r} row found in the Table 2 page of {article_pdf_path}")
