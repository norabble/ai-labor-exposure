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
