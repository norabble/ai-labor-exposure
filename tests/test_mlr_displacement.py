"""Tests for mlr_displacement.py — parsing displacement rates out of the MLR article PDFs."""

import os
import subprocess
import sys

import pandas as pd
import pytest

from mlr_displacement import (
    MLR_OCCUPATION_LEAVES,
    _iter_table_rows,
    _locate_periods_and_data_lines_from_text,
    _normalize_occupation_key,
    _rate_records_from_periods_and_lines,
    parse_displacement_rate_table,
    parse_total_displacement_rate,
)

ARTICLE_PATH = "data/raw/dws/mlr/mid_1990s_1999.pdf"
ARTICLE_PRESENT = os.path.exists(ARTICLE_PATH)

TABLE2_TEXT_FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "mlr_table2_1999_article.txt")

ARTICLE_PATH_2001 = "data/raw/dws/mlr/strong_labor_market_2001.pdf"
ARTICLE_PRESENT_2001 = os.path.exists(ARTICLE_PATH_2001)

ARTICLE_PATH_2004 = "data/raw/dws/mlr/displacement_1999_2000_2004.pdf"
ARTICLE_PRESENT_2004 = os.path.exists(ARTICLE_PATH_2004)


class TestLeafSelection:
    def test_aggregate_rows_are_not_leaves(self):
        """Aggregates are sums of their own children; including them double-counts."""
        for aggregate in (
            "White-collar occupations",
            "Blue-collar occupations",
            "Managerial and professional specialty",
            "Technical, sales, and administrative support",
            "Precision production, craft, and repair",
            "Operators, fabricators, and laborers",
        ):
            assert aggregate not in MLR_OCCUPATION_LEAVES

    def test_known_leaves_are_present(self):
        for leaf in ("Executive, administrative, and managerial", "Sales occupations", "Construction trades"):
            assert leaf in MLR_OCCUPATION_LEAVES


class TestOccupationKeyNormalization:
    def test_all_canonical_leaves_have_distinct_normalized_keys(self):
        """A key collision would silently merge two distinct occupation groups into one."""
        normalized_keys = {_normalize_occupation_key(leaf) for leaf in MLR_OCCUPATION_LEAVES}
        assert len(normalized_keys) == len(MLR_OCCUPATION_LEAVES)

    def test_comma_drift_normalizes_to_the_same_key(self):
        """The 2001 article drops the comma: "administrative and managerial" vs "administrative, and"."""
        assert _normalize_occupation_key("Executive, administrative, and managerial") == _normalize_occupation_key(
            "Executive, administrative and managerial"
        )

    def test_hyphen_drift_normalizes_to_the_same_key(self):
        """The 2001 and 2004 articles print "material moving" where the 1999 article hyphenates it."""
        assert _normalize_occupation_key("Transportation and material-moving occupations") == _normalize_occupation_key(
            "Transportation and material moving occupations"
        )


class TestRateTableParsingFromCommittedTextFixture:
    """Exercises the real, fragile parsing logic — _locate_periods_and_data_lines_from_text,
    _iter_table_rows, and _rate_records_from_periods_and_lines, the same functions
    parse_displacement_rate_table and parse_total_displacement_rate call after finding the
    PDF page — against a committed plain-text fixture of the real extracted Table 2 page
    from the 1999 MLR article (tests/fixtures/mlr_table2_1999_article.txt, copied verbatim
    from pdfplumber's own extract_text() output for data/raw/dws/mlr/mid_1990s_1999.pdf, not
    hand-written), rather than a synthetic string.

    Runs unconditionally, unlike every other test in this file, which `skipif`s on a
    gitignored PDF that CI never downloads (`uv sync --locked` plus `pytest tests/`, with
    no `data/` at all) — closing the zero-CI-coverage gap the 2026-09-15 final review found
    in this parser (Important finding I5). The real extract also carries the actual
    extraction fragility this parser exists to handle, which a hand-built fixture might
    accidentally sanitize away: dot leaders, wrapped labels ("Executive, administrative,
    and" / "managerial......"), and a footnote superscript glued onto a label
    ("White-collar occupations²"). Keep the real-PDF tests below as they are, additionally.
    """

    @staticmethod
    def _fixture_text():
        with open(TABLE2_TEXT_FIXTURE_PATH, encoding="utf-8") as fixture_file:
            return fixture_file.read()

    def test_eight_periods_are_recovered(self):
        periods, _ = _locate_periods_and_data_lines_from_text(self._fixture_text())
        assert [period_label for period_label, _, _ in periods] == [
            "1981-82",
            "1983-84",
            "1985-86",
            "1987-88",
            "1989-90",
            "1991-92",
            "1993-94",
            "1995-96",
        ]

    def test_wrapped_labels_are_reassembled(self):
        """'Executive, administrative, and' wraps onto its own line ahead of the line
        carrying 'managerial......' and its values."""
        periods, data_lines = _locate_periods_and_data_lines_from_text(self._fixture_text())
        rows = dict(_iter_table_rows(data_lines, len(periods)))
        assert "Executive, administrative, and managerial" in rows

    def test_footnote_superscript_glued_onto_a_label_does_not_corrupt_it(self):
        """'White-collar occupations²......' must not leave the superscript glued to the
        label. The preceding standalone "Occupation" section header carries forward and
        prepends (the same pending-label-fragment behaviour that reassembles a wrapped
        label), so the recovered key is "Occupation White-collar occupations", not the
        bare label alone -- what matters here is that no key anywhere contains the raw
        superscript glyph."""
        periods, data_lines = _locate_periods_and_data_lines_from_text(self._fixture_text())
        rows = dict(_iter_table_rows(data_lines, len(periods)))
        assert "Occupation White-collar occupations" in rows
        assert not any("²" in label for label in rows)

    def test_the_total_row_is_recovered_at_the_known_published_value(self):
        periods, data_lines = _locate_periods_and_data_lines_from_text(self._fixture_text())
        rows = dict(_iter_table_rows(data_lines, len(periods)))
        assert rows["Total, 20 years and older"][0] == "3.9"

    def test_parse_displacement_rate_table_recovers_a_known_published_value(self):
        """Sales occupations, 1981-82, is published as 3.7 percent -- runs the actual
        production leaf-matching and canonicalisation logic
        (_rate_records_from_periods_and_lines), the same code
        parse_displacement_rate_table calls on a real PDF path."""
        periods, data_lines = _locate_periods_and_data_lines_from_text(self._fixture_text())
        records = _rate_records_from_periods_and_lines(periods, data_lines)
        rate_df = pd.DataFrame(records)

        row = rate_df[(rate_df.mlr_occupation == "Sales occupations") & (rate_df.period_label == "1981-82")]
        assert row["displacement_rate_percent"].iloc[0] == pytest.approx(3.7)

    def test_parse_displacement_rate_table_recovers_a_leading_decimal_value(self):
        """Protective services, 1985-86, is printed as '.5' with no leading zero."""
        periods, data_lines = _locate_periods_and_data_lines_from_text(self._fixture_text())
        records = _rate_records_from_periods_and_lines(periods, data_lines)
        rate_df = pd.DataFrame(records)

        row = rate_df[(rate_df.mlr_occupation == "Protective services") & (rate_df.period_label == "1985-86")]
        assert row["displacement_rate_percent"].iloc[0] == pytest.approx(0.5)

    def test_parse_displacement_rate_table_recovers_every_leaf(self):
        periods, data_lines = _locate_periods_and_data_lines_from_text(self._fixture_text())
        records = _rate_records_from_periods_and_lines(periods, data_lines)
        rate_df = pd.DataFrame(records)

        assert set(rate_df["mlr_occupation"].unique()) == set(MLR_OCCUPATION_LEAVES)
        counts = rate_df.groupby("mlr_occupation")["period_label"].nunique()
        assert (counts == 8).all()


@pytest.mark.skipif(not ARTICLE_PRESENT, reason="MLR article not downloaded; run download_dws.py")
class TestRateTableParsing:
    def test_eight_periods_are_recovered(self):
        rate_df = parse_displacement_rate_table(ARTICLE_PATH)
        assert sorted(rate_df["period_label"].unique()) == [
            "1981-82",
            "1983-84",
            "1985-86",
            "1987-88",
            "1989-90",
            "1991-92",
            "1993-94",
            "1995-96",
        ]

    def test_period_years_are_parsed_as_four_digit_integers(self):
        rate_df = parse_displacement_rate_table(ARTICLE_PATH)
        first = rate_df[rate_df["period_label"] == "1995-96"].iloc[0]
        assert first["period_start_year"] == 1995
        assert first["period_end_year"] == 1996

    def test_a_known_published_value_is_recovered_exactly(self):
        """Sales occupations, 1981-82, is published as 3.7 percent."""
        rate_df = parse_displacement_rate_table(ARTICLE_PATH)
        row = rate_df[(rate_df.mlr_occupation == "Sales occupations") & (rate_df.period_label == "1981-82")]
        assert row["displacement_rate_percent"].iloc[0] == pytest.approx(3.7)

    def test_leading_decimal_values_are_parsed(self):
        """BLS prints values below one without a leading zero, e.g. Protective services 1985-86 is '.5'."""
        rate_df = parse_displacement_rate_table(ARTICLE_PATH)
        row = rate_df[(rate_df.mlr_occupation == "Protective services") & (rate_df.period_label == "1985-86")]
        assert row["displacement_rate_percent"].iloc[0] == pytest.approx(0.5)

    def test_every_leaf_appears_in_every_period(self):
        rate_df = parse_displacement_rate_table(ARTICLE_PATH)
        counts = rate_df.groupby("mlr_occupation")["period_label"].nunique()
        assert (counts == 8).all()


@pytest.mark.skipif(not ARTICLE_PRESENT_2001, reason="MLR 2001 article not downloaded; run download_dws.py")
class TestRateTableParsing2001Article:
    """The 2001 article adds a period beyond the 1999 article and drifts two leaves' wording."""

    def test_nine_periods_are_recovered(self):
        rate_df = parse_displacement_rate_table(ARTICLE_PATH_2001)
        assert sorted(rate_df["period_label"].unique()) == [
            "1981-82",
            "1983-84",
            "1985-86",
            "1987-88",
            "1989-90",
            "1991-92",
            "1993-94",
            "1995-96",
            "1997-98",
        ]

    def test_all_fourteen_leaves_are_recovered_despite_wording_drift(self):
        """1997-98 is sourced only from this article; a drifted leaf missing here is permanently
        absent from the panel for that period, with no other source to recover it from."""
        rate_df = parse_displacement_rate_table(ARTICLE_PATH_2001)
        assert set(rate_df["mlr_occupation"].unique()) == set(MLR_OCCUPATION_LEAVES)

    def test_drifted_leaves_are_emitted_under_the_canonical_spelling(self):
        rate_df = parse_displacement_rate_table(ARTICLE_PATH_2001)
        matched_labels = set(rate_df["mlr_occupation"].unique())
        assert "Executive, administrative, and managerial" in matched_labels
        assert "Transportation and material-moving occupations" in matched_labels


@pytest.mark.skipif(not ARTICLE_PRESENT_2004, reason="MLR 2004 article not downloaded; run download_dws.py")
class TestRateTableParsing2004Article:
    """The 2004 article adds a further period and drifts one leaf's wording."""

    def test_ten_periods_are_recovered(self):
        rate_df = parse_displacement_rate_table(ARTICLE_PATH_2004)
        assert sorted(rate_df["period_label"].unique()) == [
            "1981-82",
            "1983-84",
            "1985-86",
            "1987-88",
            "1989-90",
            "1991-92",
            "1993-94",
            "1995-96",
            "1997-98",
            "1999-2000",
        ]

    def test_all_fourteen_leaves_are_recovered_despite_wording_drift(self):
        """1999-2000 is sourced only from this article; a drifted leaf missing here is
        permanently absent from the panel for that period, with no other source to recover it
        from."""
        rate_df = parse_displacement_rate_table(ARTICLE_PATH_2004)
        assert set(rate_df["mlr_occupation"].unique()) == set(MLR_OCCUPATION_LEAVES)


class TestTotalDisplacementRateParsing:
    """Table 2's economy-wide "Total, 20 years and older" row, parsed independently of the
    occupation leaves. All three articles are expected to be present in this environment."""

    @pytest.mark.skipif(not ARTICLE_PRESENT, reason="MLR article not downloaded; run download_dws.py")
    def test_eight_periods_are_recovered_from_the_1999_article(self):
        total_rate_df = parse_total_displacement_rate(ARTICLE_PATH)
        assert sorted(total_rate_df["period_label"]) == [
            "1981-82",
            "1983-84",
            "1985-86",
            "1987-88",
            "1989-90",
            "1991-92",
            "1993-94",
            "1995-96",
        ]

    @pytest.mark.skipif(not ARTICLE_PRESENT_2004, reason="MLR 2004 article not downloaded; run download_dws.py")
    def test_ten_periods_are_recovered_from_the_2004_article(self):
        total_rate_df = parse_total_displacement_rate(ARTICLE_PATH_2004)
        assert sorted(total_rate_df["period_label"]) == [
            "1981-82",
            "1983-84",
            "1985-86",
            "1987-88",
            "1989-90",
            "1991-92",
            "1993-94",
            "1995-96",
            "1997-98",
            "1999-2000",
        ]

    @pytest.mark.skipif(not ARTICLE_PRESENT_2004, reason="MLR 2004 article not downloaded; run download_dws.py")
    def test_a_known_published_total_value_is_recovered_exactly(self):
        """1999-2000 is published as 2.5 percent, per the 2004 article (the only one covering it)."""
        total_rate_df = parse_total_displacement_rate(ARTICLE_PATH_2004)
        row = total_rate_df[total_rate_df["period_label"] == "1999-2000"]
        assert row["displacement_rate_percent"].iloc[0] == pytest.approx(2.5)

    @pytest.mark.skipif(
        not (ARTICLE_PRESENT and ARTICLE_PRESENT_2001 and ARTICLE_PRESENT_2004),
        reason="not all three MLR articles are downloaded; run download_dws.py",
    )
    def test_overlapping_periods_agree_exactly_across_all_three_articles(self):
        """A free consistency check on both the parser and the source: the total row for
        1981-82 through 1995-96 is published identically in every article that carries it."""
        rate_by_article = {
            article_path: parse_total_displacement_rate(article_path).set_index("period_label")["displacement_rate_percent"]
            for article_path in (ARTICLE_PATH, ARTICLE_PATH_2001, ARTICLE_PATH_2004)
        }
        shared_periods = ["1981-82", "1983-84", "1985-86", "1987-88", "1989-90", "1991-92", "1993-94", "1995-96"]
        expected_values = [3.9, 3.1, 3.1, 2.4, 3.1, 3.9, 3.3, 2.9]

        for article_path, rate_by_period in rate_by_article.items():
            for period_label, expected_value in zip(shared_periods, expected_values):
                assert rate_by_period[period_label] == pytest.approx(expected_value), f"{article_path} disagrees on {period_label}"


class TestCrosswalk:
    def test_every_leaf_has_a_mapping(self):
        from mlr_displacement import MLR_OCCUPATION_LEAVES, mlr_to_dws_group

        assert set(MLR_OCCUPATION_LEAVES) <= set(mlr_to_dws_group())

    def test_every_target_is_a_real_dws_group(self):
        from dws_panel import DWS_TO_SOC_MAJOR
        from mlr_displacement import mlr_to_dws_group

        assert set(mlr_to_dws_group().values()) <= set(DWS_TO_SOC_MAJOR)

    def test_all_ten_modern_groups_are_reachable(self):
        from dws_panel import DWS_TO_SOC_MAJOR
        from mlr_displacement import mlr_to_dws_group

        assert set(mlr_to_dws_group().values()) == set(DWS_TO_SOC_MAJOR)

    def test_low_confidence_mappings_are_flagged(self):
        from mlr_displacement import load_mlr_crosswalk

        crosswalk_df = load_mlr_crosswalk()
        assert (crosswalk_df["mapping_confidence"] == "low").any()

    def test_below_high_confidence_mappings_are_flagged(self):
        """Two rows sit below `high` confidence, not just the one `low` row: the
        handlers/equipment-cleaners/helpers/laborers row (low, a genuine split across
        the modern production and transportation/material-moving groups) and `Other
        precision production occupations` (medium, a judgement-call boundary). An
        earlier version of CLAUDE.md, docs/framework.md and the chart doc mentioned
        only the low row."""
        from mlr_displacement import load_mlr_crosswalk

        crosswalk_df = load_mlr_crosswalk()
        below_high = crosswalk_df[crosswalk_df["mapping_confidence"] != "high"]

        assert set(below_high["mapping_confidence"]) == {"low", "medium"}

    def test_importing_dws_panel_does_not_require_cwd_to_be_the_repo_root(self):
        """Regression test for the defect mlr_to_dws_group()'s docstring describes: an
        earlier version of this module read seeds/mlr_occupation_crosswalk.csv at
        import time with a relative path, so `import dws_panel` (which imports this
        module) raised FileNotFoundError from any cwd other than the repo root. Runs
        the import in a subprocess from outside the repo so a regression is caught
        even though every other test in this suite runs from the repo root."""
        project_root = os.path.dirname(os.path.abspath(__file__)) + "/.."
        result = subprocess.run(
            [sys.executable, "-c", "import dws_panel"],
            cwd="/tmp",
            env={**os.environ, "PYTHONPATH": os.path.abspath(project_root)},
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    def test_mlr_to_dws_group_is_called_fresh_each_time_not_cached_at_import(self):
        """mlr_to_dws_group() must be safe to call from any cwd — it is called at
        call time, not built once at import, so `import dws_panel` (and
        transitively historical_displacement and composition_displacement_validation)
        cannot fail with FileNotFoundError just from importing this module."""
        import mlr_displacement

        assert "MLR_TO_DWS_GROUP" not in dir(mlr_displacement)
        first_call = mlr_displacement.mlr_to_dws_group()
        second_call = mlr_displacement.mlr_to_dws_group()
        assert first_call == second_call
        assert first_call is not second_call
