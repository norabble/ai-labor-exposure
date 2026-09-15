"""
test_dws_panel.py
─────────────────
Regression tests for dws_panel.py — the Displaced Worker Supplement parser and
survey panel.

The fixtures in tests/fixtures/dws_table{2,5,8}_sample.html are trimmed copies of
a real January 2026 release, kept structurally intact (two-row header with
colspans, footnote paragraph) so the tests exercise the same pandas column
flattening the pipeline sees.

Table 2's fixture deliberately keeps all seven of its "Total, 20 years and over"
rows — the release repeats that label under Total, Men, Women and again for each
industry panel, with a different count each time. Only the first is the
all-workers total, so a parser that matched the label without taking the first
match would silently report 212 thousand displaced instead of 3,324.

tests/fixtures/dws_archive_2016.html is a byte-identical copy of the real
archived release (verified with `cmp` after committing) rather than a trimmed
fixture, because it exercises `parse_archived_text_release`'s plain-text
`<PRE>`-block layout: dot-leader-padded labels, fixed-width-aligned (not
delimited) numeric columns, and labels wrapped across two physical lines. A
hand-trimmed fixture risks losing the exact whitespace that layout depends on,
and a committed fixture is also subject to the trailing-whitespace pre-commit
hook, which is why that hook excludes tests/fixtures/.
"""

import os

import pandas as pd
import pytest

from dws_panel import (
    DWS_TO_SOC_MAJOR,
    PANEL_COLUMNS,
    STRUCTURAL_REASON,
    build_release_panel,
    load_dws_panel,
    merge_panel,
    parse_archived_release,
    parse_archived_text_release,
    parse_occupation_table,
    parse_reason_table,
    parse_survey_period,
    parse_total_table,
    verify_soc_coverage,
)

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
TABLE_2_FIXTURE = os.path.join(FIXTURE_DIR, "dws_table2_sample.html")
TABLE_5_FIXTURE = os.path.join(FIXTURE_DIR, "dws_table5_sample.html")
TABLE_8_FIXTURE = os.path.join(FIXTURE_DIR, "dws_table8_sample.html")

RAW_RELEASE_PRESENT = os.path.exists("data/raw/dws/disp_t05.html")


class TestSocCoverage:
    def test_mapping_covers_all_twenty_two_major_groups_exactly_once(self):
        verify_soc_coverage()

        mapped_majors = [major for majors in DWS_TO_SOC_MAJOR.values() for major in majors]
        assert len(mapped_majors) == 22
        assert len(set(mapped_majors)) == 22

    def test_mapping_agrees_with_the_cps_major_group_list(self):
        """The DWS groups must span exactly the majors cps_panel.py already knows about."""
        from cps_panel import CPS_TO_SOC_MAJOR

        mapped_majors = {major for majors in DWS_TO_SOC_MAJOR.values() for major in majors}
        assert mapped_majors == set(CPS_TO_SOC_MAJOR.values())


class TestParseSurveyPeriod:
    def test_reads_survey_year_and_window_from_the_release(self):
        survey_year, period_start_year, period_end_year = parse_survey_period(TABLE_5_FIXTURE)

        assert (survey_year, period_start_year, period_end_year) == (2026, 2023, 2025)

    def test_window_length_is_read_not_assumed(self):
        """The annual rate divides by this window, so it must come from the release text."""
        _, period_start_year, period_end_year = parse_survey_period(TABLE_5_FIXTURE)

        assert period_end_year - period_start_year + 1 == 3

    def test_missing_period_text_raises(self, tmp_path):
        empty_release = tmp_path / "no_period.html"
        empty_release.write_text("<html><body><table><tr><td>1</td></tr></table></body></html>")

        with pytest.raises(ValueError, match="could not read survey period"):
            parse_survey_period(str(empty_release))


class TestParseOccupationTable:
    def test_returns_the_ten_leaf_groups_not_the_broad_ones(self):
        occupation_df = parse_occupation_table(TABLE_5_FIXTURE)

        assert len(occupation_df) == 10
        assert set(occupation_df["group_name"].str.lower()) == set(DWS_TO_SOC_MAJOR)

    def test_drops_the_broad_parent_rows_that_would_double_count(self):
        occupation_df = parse_occupation_table(TABLE_5_FIXTURE)

        group_names = set(occupation_df["group_name"])
        assert "Management, professional, and related occupations" not in group_names
        assert "Sales and office occupations" not in group_names
        assert "Natural resources, construction, and maintenance occupations" not in group_names

    def test_maps_groups_to_pipe_joined_soc_majors(self):
        occupation_df = parse_occupation_table(TABLE_5_FIXTURE).set_index("group_name")

        assert occupation_df.loc["Office and administrative support occupations", "soc_majors"] == "43"
        assert occupation_df.loc["Professional and related occupations", "soc_majors"] == "15|17|19|21|23|25|27|29"

    def test_counts_match_the_published_release(self):
        occupation_df = parse_occupation_table(TABLE_5_FIXTURE).set_index("group_name")

        assert occupation_df.loc["Office and administrative support occupations", "displaced_thousands"] == 316
        assert occupation_df.loc["Production occupations", "displaced_thousands"] == 352
        assert occupation_df.loc["Farming, fishing, and forestry occupations", "displaced_thousands"] == 19

    def test_leaf_groups_sum_close_to_the_published_total(self):
        occupation_df = parse_occupation_table(TABLE_5_FIXTURE)

        # The release's own total is 3,324; the leaves omit a small unclassified residual.
        assert 3100 < occupation_df["displaced_thousands"].sum() < 3324

    def test_suppressed_dash_becomes_nan_not_zero(self, tmp_path):
        """A dash means the base was under 75,000, which is not the same as no displacement."""
        suppressed_release = tmp_path / "suppressed.html"
        suppressed_release.write_text(
            "<html><body><table>"
            "<tr><th>Occupation of lost job</th><th>Total</th></tr>"
            "<tr><th>Occupation of lost job</th><th>Total</th></tr>"
            + "".join(f"<tr><td>{name.title()}</td><td>{'-' if name.startswith('farming') else 100}</td></tr>" for name in DWS_TO_SOC_MAJOR)
            + "</table></body></html>"
        )

        occupation_df = parse_occupation_table(str(suppressed_release)).set_index("group_name")
        farming_value = occupation_df.loc["Farming, Fishing, And Forestry Occupations", "displaced_thousands"]

        assert pd.isna(farming_value)

    def test_missing_leaf_group_raises(self, tmp_path):
        incomplete_release = tmp_path / "incomplete.html"
        incomplete_release.write_text(
            "<html><body><table>"
            "<tr><th>Occupation of lost job</th><th>Total</th></tr>"
            "<tr><th>Occupation of lost job</th><th>Total</th></tr>"
            "<tr><td>Production occupations</td><td>352</td></tr>"
            "</table></body></html>"
        )

        with pytest.raises(ValueError, match="missing expected leaf occupation groups"):
            parse_occupation_table(str(incomplete_release))


class TestParseReasonTable:
    def test_takes_the_first_total_row_not_a_later_repeat(self):
        """Seven rows share the label 'Total, 20 years and over'; only the first is the all-workers total."""
        reason_df = parse_reason_table(TABLE_2_FIXTURE)

        # 3,324 × 44.4% — any later repeat would give a much smaller count.
        structural_count = reason_df.loc[reason_df["reason"] == STRUCTURAL_REASON, "displaced_thousands"].iloc[0]
        assert structural_count == pytest.approx(3324 * 0.444, rel=1e-6)

    def test_returns_all_three_reasons_as_counts(self):
        reason_df = parse_reason_table(TABLE_2_FIXTURE)

        assert len(reason_df) == 3
        # The three reasons partition the long-tenured total, but the release publishes
        # them to one decimal place and they sum to 99.9%, not 100 — so the recovered
        # counts land just under the published 3,324.
        assert reason_df["displaced_thousands"].sum() == pytest.approx(3324, rel=2e-3)

    def test_structural_reason_is_the_largest_category(self):
        reason_df = parse_reason_table(TABLE_2_FIXTURE).set_index("reason")

        assert reason_df.loc[STRUCTURAL_REASON, "displaced_thousands"] > reason_df.loc["insufficient work", "displaced_thousands"]


class TestParseTotalTable:
    def test_reads_the_all_tenures_total(self):
        total_df = parse_total_table(TABLE_8_FIXTURE)

        assert len(total_df) == 1
        assert total_df["displaced_thousands"].iloc[0] == 7445
        assert total_df["tenure_class"].iloc[0] == "all_tenures"

    def test_all_tenures_total_exceeds_the_long_tenured_total(self):
        """Table 8 counts short-tenured workers too, so it must be the larger figure."""
        long_tenured = parse_occupation_table(TABLE_5_FIXTURE)["displaced_thousands"].sum()

        assert parse_total_table(TABLE_8_FIXTURE)["displaced_thousands"].iloc[0] > long_tenured


class TestMergePanel:
    def _panel_row(self, survey_year, group_name, displaced_thousands):
        return {
            "survey_year": survey_year,
            "period_start_year": survey_year - 3,
            "period_end_year": survey_year - 1,
            "period_years": 3,
            "source_table": "table_5_occupation",
            "group_name": group_name,
            "soc_majors": "43",
            "displaced_thousands": displaced_thousands,
            "reason": "all",
            "tenure_class": "long_tenured",
        }

    def test_accumulates_distinct_surveys(self):
        existing_panel_df = pd.DataFrame([self._panel_row(2024, "Office", 300)])
        new_release_df = pd.DataFrame([self._panel_row(2026, "Office", 316)])

        merged_panel_df = merge_panel(existing_panel_df, new_release_df)

        assert sorted(merged_panel_df["survey_year"]) == [2024, 2026]

    def test_new_release_wins_on_a_revised_survey(self):
        existing_panel_df = pd.DataFrame([self._panel_row(2026, "Office", 300)])
        new_release_df = pd.DataFrame([self._panel_row(2026, "Office", 316)])

        merged_panel_df = merge_panel(existing_panel_df, new_release_df)

        assert len(merged_panel_df) == 1
        assert merged_panel_df["displaced_thousands"].iloc[0] == 316


class TestLoadDwsPanel:
    def test_returns_none_when_no_seed_and_no_release(self, tmp_path, capsys):
        panel_df = load_dws_panel(
            seed_path=str(tmp_path / "missing_seed.csv"),
            raw_release_dir=str(tmp_path / "missing_raw"),
            output_path=None,
        )

        assert panel_df is None
        assert "No DWS panel available" in capsys.readouterr().out

    def test_falls_back_to_the_seed_when_the_release_is_unparseable(self, tmp_path, capsys):
        seed_path = tmp_path / "seed.csv"
        pd.DataFrame([dict.fromkeys(PANEL_COLUMNS, "x")]).to_csv(seed_path, index=False)
        broken_release_dir = tmp_path / "raw"
        broken_release_dir.mkdir()
        (broken_release_dir / "disp_t05.html").write_text("<html><body>not a release</body></html>")

        panel_df = load_dws_panel(seed_path=str(seed_path), raw_release_dir=str(broken_release_dir), output_path=None)

        assert panel_df is not None and len(panel_df) == 1
        assert "Could not parse the DWS release" in capsys.readouterr().out


@pytest.mark.skipif(not RAW_RELEASE_PRESENT, reason="DWS release HTML not downloaded")
class TestAgainstDownloadedRelease:
    def test_build_release_panel_produces_the_expected_shape(self):
        release_panel_df = build_release_panel()

        assert list(release_panel_df.columns) == PANEL_COLUMNS
        # Ten occupation groups, three reasons, one all-tenures total.
        assert len(release_panel_df) == 14
        assert release_panel_df["survey_year"].nunique() == 1


class TestArchiveUrls:
    def test_nine_archived_surveys_are_listed(self):
        from download_dws import ARCHIVE_RELEASE_URLS

        assert sorted(ARCHIVE_RELEASE_URLS) == [2008, 2010, 2012, 2014, 2016, 2018, 2020, 2022, 2024]

    def test_urls_use_the_verified_release_dates(self):
        from download_dws import ARCHIVE_RELEASE_URLS

        assert ARCHIVE_RELEASE_URLS[2022].endswith("disp_08262022.htm")
        assert ARCHIVE_RELEASE_URLS[2008].endswith("disp_08202008.htm")

    def test_every_url_is_under_the_archive_path(self):
        from download_dws import ARCHIVE_RELEASE_URLS

        assert all("/news.release/archives/" in url for url in ARCHIVE_RELEASE_URLS.values())


class TestArchiveParsing:
    """Parsing the four archived releases that render their tables as HTML."""

    FIXTURE_PATH = "tests/fixtures/dws_archive_2022.html"

    @classmethod
    def _fixture_html(cls):
        with open(cls.FIXTURE_PATH, encoding="utf-8") as fixture_file:
            return fixture_file.read()

    def test_ten_leaf_occupation_rows_are_extracted(self):
        panel_df = parse_archived_release(self._fixture_html(), 2022)
        occupation_rows = panel_df[panel_df["source_table"] == "table_5_occupation"]
        assert len(occupation_rows) == 10

    def test_occupation_group_names_match_the_soc_mapping(self):
        """Case-insensitively: the release prints Title Case, DWS_TO_SOC_MAJOR is keyed lowercase.

        _occupation_rows stores the release's own casing and lowercases only for the
        lookup, so the current-release and archived-release paths agree.
        """
        panel_df = parse_archived_release(self._fixture_html(), 2022)
        occupation_rows = panel_df[panel_df["source_table"] == "table_5_occupation"]
        assert {name.lower() for name in occupation_rows["group_name"]} == set(DWS_TO_SOC_MAJOR)

    def test_every_occupation_row_resolves_to_soc_majors(self):
        panel_df = parse_archived_release(self._fixture_html(), 2022)
        occupation_rows = panel_df[panel_df["source_table"] == "table_5_occupation"]
        assert occupation_rows["soc_majors"].notna().all()

    def test_survey_year_is_stamped_on_every_row(self):
        panel_df = parse_archived_release(self._fixture_html(), 2022)
        assert (panel_df["survey_year"] == 2022).all()

    def test_the_displacement_window_is_read_from_the_release_not_the_survey_year(self):
        """The 2022 survey reports displacement over 2019-2021, not 2022."""
        panel_df = parse_archived_release(self._fixture_html(), 2022)
        assert panel_df["period_start_year"].iloc[0] == 2019
        assert panel_df["period_end_year"].iloc[0] == 2021
        assert panel_df["period_years"].iloc[0] == 3

    def test_the_window_is_not_derived_from_the_survey_year_by_a_fixed_offset(self):
        """Every real archive has window == survey_year-3..survey_year-1, so no real
        fixture can tell a correct parser from one applying a fixed offset. This
        states a window matching no offset from any survey year.
        """
        from dws_panel import _parse_archived_period

        release_html = "<html><body><p>Workers displaced between January 2010 and December 2014.</p></body></html>"
        assert _parse_archived_period(release_html) == (2010, 2014)

    def test_an_unreadable_window_raises_rather_than_guessing(self):
        from dws_panel import _parse_archived_period

        with pytest.raises(ValueError):
            _parse_archived_period("<html><body><p>No window stated here.</p></body></html>")

    def test_counts_are_positive_and_suppressed_values_are_not_zero(self):
        panel_df = parse_archived_release(self._fixture_html(), 2022)
        present = panel_df["displaced_thousands"].dropna()
        assert (present > 0).all()

    def test_columns_match_the_existing_panel_schema(self):
        panel_df = parse_archived_release(self._fixture_html(), 2022)
        assert list(panel_df.columns) == PANEL_COLUMNS

    def test_a_plain_text_archive_yields_an_empty_frame_rather_than_raising(self):
        """2008-2016 archives use <PRE> blocks and are handled by a separate parser."""
        panel_df = parse_archived_release("<html><body><pre>Total 1234</pre></body></html>", 2012)
        assert panel_df.empty
        assert list(panel_df.columns) == PANEL_COLUMNS


# A minimal synthetic occupation table in the same dot-leader / whitespace-run
# layout as the real 2008-2016 archives, with the Farming leaf's count suppressed
# as a dash rather than a real value. Embedded in a full <html> page with the
# window footnote sentence, so parse_archived_text_release can be exercised
# end-to-end without depending on which real year happens to suppress a count.
_SYNTHETIC_PLAIN_TEXT_ARCHIVE = """
<html><body><pre>
Table 5. Long-tenured displaced workers (1) by occupation of lost job and employment status in January 2016
(Numbers in thousands)
              Occupation of lost job                  Total
                                                                  Total      Employed   Unemployed  Not in the
                                                                                                   labor force

     Total, 20 years and over (2).................     3,191      100.0        65.5        15.9        18.6

 Management, business, and financial operations occupations       702      100.0        72.1        14.6        13.3
 Professional and related occupations...........       598      100.0        65.5        12.3        22.3
 Service occupations..............................       313      100.0        63.4        19.0        17.6
 Sales and related occupations..................       340      100.0        66.1        18.3        15.6
 Office and administrative support occupations..       479      100.0        61.1        13.0        25.9
 Farming, fishing, and forestry occupations.....          -      100.0         (3)         (3)         (3)
 Construction and extraction occupations........       193      100.0        61.1        28.5        10.4
 Installation, maintenance, and repair occupations       102      100.0        62.3        16.4        21.3
 Production occupations.........................       246      100.0        55.3        21.1        23.6
 Transportation and material moving occupations        171      100.0        78.9         9.1        12.0

   1 Data refer to persons who had 3 or more years of tenure on a job they had lost or left between January 2013
and December 2015 because of plant or company closings or moves, insufficient work, or the abolishment of
their positions or shifts.
   2 Total includes a small number who did not report occupation.
   3 Data not shown where base is less than 75,000.
</pre></body></html>
"""


class TestArchiveTextParsing:
    """Parsing the five archived releases (2008-2016) that lay tables out as plain-text <PRE> blocks."""

    FIXTURE_PATH = "tests/fixtures/dws_archive_2016.html"

    @classmethod
    def _fixture_html(cls):
        with open(cls.FIXTURE_PATH, encoding="utf-8") as fixture_file:
            return fixture_file.read()

    def test_ten_leaf_occupation_rows_are_extracted_from_the_real_fixture(self):
        panel_df = parse_archived_text_release(self._fixture_html(), 2016)
        occupation_rows = panel_df[panel_df["source_table"] == "table_5_occupation"]

        assert len(occupation_rows) == 10

    def test_group_names_match_the_soc_mapping_case_insensitively(self):
        """The release prints Title Case; DWS_TO_SOC_MAJOR is keyed lowercase — expected and correct."""
        panel_df = parse_archived_text_release(self._fixture_html(), 2016)
        occupation_rows = panel_df[panel_df["source_table"] == "table_5_occupation"]

        assert {group_name.lower() for group_name in occupation_rows["group_name"]} == set(DWS_TO_SOC_MAJOR)
        assert occupation_rows["soc_majors"].notna().all()

    def test_dispatches_through_parse_archived_release_by_content_not_index(self):
        """parse_archived_release must detect the plain-text layout and delegate on its own."""
        dispatched_panel_df = parse_archived_release(self._fixture_html(), 2016)
        direct_panel_df = parse_archived_text_release(self._fixture_html(), 2016)

        assert len(dispatched_panel_df) == len(direct_panel_df) == 13

    def test_the_window_comes_from_the_release_text(self):
        """The 2016 survey reports displacement over 2013-2015, not 2016."""
        panel_df = parse_archived_text_release(self._fixture_html(), 2016)

        assert panel_df["period_start_year"].iloc[0] == 2013
        assert panel_df["period_end_year"].iloc[0] == 2015
        assert panel_df["period_years"].iloc[0] == 3

    def test_columns_match_the_existing_panel_schema(self):
        panel_df = parse_archived_text_release(self._fixture_html(), 2016)

        assert list(panel_df.columns) == PANEL_COLUMNS

    def test_comma_thousands_separator_parses_correctly_not_truncated_at_the_comma(self):
        from dws_panel import _pre_table_count_string

        count_string = _pre_table_count_string("3,191")

        assert count_string == "3191"
        assert pd.to_numeric(count_string) == 3191.0

    def test_a_suppressed_dash_becomes_nan_not_zero(self):
        """A dash means the base was under 75,000, which is not the same as no displacement."""
        panel_df = parse_archived_text_release(_SYNTHETIC_PLAIN_TEXT_ARCHIVE, 2016)
        occupation_rows = panel_df[panel_df["source_table"] == "table_5_occupation"].copy()
        occupation_rows["group_name"] = occupation_rows["group_name"].str.lower()
        occupation_rows = occupation_rows.set_index("group_name")

        farming_value = occupation_rows.loc["farming, fishing, and forestry occupations", "displaced_thousands"]

        assert pd.isna(farming_value)

    def test_other_leaf_counts_in_the_synthetic_archive_are_unaffected_by_the_suppression(self):
        panel_df = parse_archived_text_release(_SYNTHETIC_PLAIN_TEXT_ARCHIVE, 2016)
        occupation_rows = panel_df[panel_df["source_table"] == "table_5_occupation"]
        present_counts = occupation_rows["displaced_thousands"].dropna()

        assert (present_counts > 0).all()
        assert len(present_counts) == 9
