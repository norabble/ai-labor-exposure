"""Parses Displaced Worker Supplement occupation displacement rates out of MLR article PDFs.

Table 2 of each biennial Monthly Labor Review displaced-worker article reports the
displacement rate of long-tenured workers by occupation, for eight or more two-year survey
periods. This module locates that table inside an already-downloaded article PDF (see
`download_dws.py`, which saves articles to `data/raw/dws/mlr/`) and parses its leaf
occupation rows into a long-form DataFrame, extending displacement-rate history back before
the Displaced Worker Supplement panel's 2008 archive coverage begins.

Inputs: an MLR article PDF path, read with `pdfplumber`.
Outputs: `parse_displacement_rate_table` returns a DataFrame with columns
`period_label, period_start_year, period_end_year, mlr_occupation, displacement_rate_percent`,
restricted to the leaf occupation rows named in `MLR_OCCUPATION_LEAVES`.
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

_TABLE_CAPTION = "Table 2"
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
            if _TABLE_CAPTION in page_text:
                return page_text
    raise ValueError(f"No page containing a {_TABLE_CAPTION!r} caption found in {article_pdf_path}")


def parse_displacement_rate_table(article_pdf_path: str) -> pd.DataFrame:
    """Parse Table 2's leaf occupation rows out of an MLR displaced-worker article PDF.

    Returns a long-form DataFrame with one row per (occupation, period) pair, columns
    `period_label, period_start_year, period_end_year, mlr_occupation,
    displacement_rate_percent`, restricted to the occupations in `MLR_OCCUPATION_LEAVES`
    (matched by normalised label, so a row survives inter-article wording drift) and always
    emitted under that tuple's canonical spelling.
    """
    page_text = _find_table_page_text(article_pdf_path)
    lines = page_text.splitlines()

    header_line_index = next((index for index, line in enumerate(lines) if line.strip().startswith("Characteristic")), None)
    if header_line_index is None:
        raise ValueError(f"No 'Characteristic ...' header row found in the Table 2 page of {article_pdf_path}")
    periods = _parse_period_header(lines[header_line_index])
    period_count = len(periods)
    if period_count == 0:
        raise ValueError(f"Parsed zero periods from the header row of {article_pdf_path}")

    records = []
    pending_label_fragment = ""
    for line in lines[header_line_index + 1 :]:
        cleaned_line = _strip_footnote_superscripts(_DOT_LEADER_PATTERN.sub(" ", line))
        tokens = cleaned_line.split()

        # A row needs at least one label token ahead of its period_count values; anything
        # shorter, or whose trailing tokens aren't all numbers, is a label-only fragment
        # (a section header, a wrapped label's first line, or footnote prose) to carry
        # forward and prepend to the next row that does parse as data.
        if len(tokens) <= period_count or not all(_NUMBER_TOKEN_PATTERN.fullmatch(token) for token in tokens[-period_count:]):
            pending_label_fragment = f"{pending_label_fragment} {cleaned_line.strip()}".strip()
            continue

        value_tokens = tokens[-period_count:]
        label_tokens = tokens[:-period_count]
        occupation_label = f"{pending_label_fragment} {' '.join(label_tokens)}".strip().rstrip(".")
        pending_label_fragment = ""

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

    return pd.DataFrame(
        records,
        columns=[
            "period_label",
            "period_start_year",
            "period_end_year",
            "mlr_occupation",
            "displacement_rate_percent",
        ],
    )
