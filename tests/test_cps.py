"""
test_cps.py
───────────
Regression tests for cps_panel.py — the CPS Table A-19 parser and month panel.

The fixture in tests/fixtures/table_a19_sample.html is a trimmed copy of a real
A-19 release, kept structurally intact (three-row header with colspans) so the
tests exercise the same pandas column flattening the pipeline sees. Its months
are deliberately June, not April: the parser this replaces assigned fixed
"apr_2025"/"apr_2026" names to whatever columns sat in positions 1 and 2, so a
regression to positional parsing shows up here as wrong month keys rather than
passing silently.
"""

import os

import pandas as pd
import pytest

from cps_panel import (
    CpsComparisonWindows,
    build_growth_frame,
    build_year_over_year_growth,
    extract_total_month_columns,
    format_month,
    load_cps_panel,
    merge_panel,
    oews_reference_month,
    parse_a19_release,
    parse_month_label,
    resolve_comparison_windows,
    year_over_year_month_pairs,
)

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "table_a19_sample.html")


def _panel(rows):
    """Build a panel frame from (month, soc_major, employed_thousands) triples."""
    return pd.DataFrame(
        [
            {
                "month": month,
                "soc_major": soc_major,
                "occupation": f"Group {soc_major}",
                "employed_thousands": employed_thousands,
                "source_reference_month": month,
            }
            for month, soc_major, employed_thousands in rows
        ]
    )


class TestParseMonthLabel:
    @pytest.mark.parametrize(
        ("month_label", "expected_month"),
        [
            ("Apr. 2025", "2025-04"),
            ("June 2025", "2025-06"),
            ("July 2026", "2026-07"),
            ("Sept. 2025", "2025-09"),
            ("Jan.\xa02026", "2026-01"),
            ("  Dec. 2024  ", "2024-12"),
        ],
    )
    def test_parses_bls_label_variants(self, month_label, expected_month):
        """BLS abbreviates some months and spells out others; both forms occur in A-19."""
        assert parse_month_label(month_label) == expected_month

    @pytest.mark.parametrize("bad_label", ["2025", "Smarch 2025", "Apr. 25", ""])
    def test_rejects_unparseable_labels(self, bad_label):
        with pytest.raises(ValueError):
            parse_month_label(bad_label)

    def test_format_month_round_trips(self):
        assert format_month(parse_month_label("June 2025")) == "Jun 2025"


class TestExtractTotalMonthColumns:
    def test_reads_months_from_header_not_position(self):
        raw_release_df = pd.read_html(FIXTURE_PATH, flavor="bs4")[0]
        month_columns = extract_total_month_columns(raw_release_df)
        assert [month for _, month in month_columns] == ["2025-06", "2026-06"]

    def test_raises_when_total_column_group_is_missing(self, tmp_path):
        """A layout change must fail loudly rather than mislabel every downstream chart."""
        altered_fixture = tmp_path / "altered.html"
        altered_fixture.write_text(open(FIXTURE_PATH, encoding="utf-8").read().replace(">Total<", ">Grand total<"), encoding="utf-8")
        raw_release_df = pd.read_html(str(altered_fixture), flavor="bs4")[0]
        with pytest.raises(ValueError, match="found 0"):
            extract_total_month_columns(raw_release_df)


class TestParseA19Release:
    def test_returns_two_months_per_major_group(self):
        release_df = parse_a19_release(FIXTURE_PATH)
        assert sorted(release_df["month"].unique()) == ["2025-06", "2026-06"]
        assert release_df["soc_major"].nunique() == 4
        assert len(release_df) == 8

    def test_maps_occupation_names_to_soc_major_codes(self):
        release_df = parse_a19_release(FIXTURE_PATH)
        assert set(release_df["soc_major"]) == {"15", "23", "43", "51"}

    def test_attaches_employment_levels_to_the_right_month(self):
        release_df = parse_a19_release(FIXTURE_PATH)
        computer_occupations = release_df[release_df["soc_major"] == "15"].set_index("month")
        assert computer_occupations.loc["2025-06", "employed_thousands"] == 6602
        assert computer_occupations.loc["2026-06", "employed_thousands"] == 6950

    def test_stamps_the_release_reference_month(self):
        release_df = parse_a19_release(FIXTURE_PATH)
        assert set(release_df["source_reference_month"]) == {"2026-06"}


class TestMergePanel:
    def test_reparsing_the_same_release_is_idempotent(self):
        release_df = parse_a19_release(FIXTURE_PATH)
        merged_once = merge_panel(pd.DataFrame(columns=release_df.columns), release_df)
        merged_twice = merge_panel(merged_once, release_df)
        assert len(merged_twice) == len(merged_once) == 8

    def test_accumulates_months_across_releases(self):
        earlier_release_df = _panel([("2025-04", "15", 6643), ("2026-04", "15", 6834)])
        later_release_df = parse_a19_release(FIXTURE_PATH)
        merged_df = merge_panel(earlier_release_df, later_release_df)
        assert sorted(merged_df["month"].unique()) == ["2025-04", "2025-06", "2026-04", "2026-06"]

    def test_later_release_wins_for_a_repeated_month(self):
        """CPS rebases population controls each January, so a month's level can be restated."""
        original_df = _panel([("2025-06", "15", 6602)])
        restated_df = _panel([("2025-06", "15", 6700)])
        restated_df["source_reference_month"] = "2026-06"
        merged_df = merge_panel(original_df, restated_df)
        assert len(merged_df) == 1
        assert merged_df["employed_thousands"].iloc[0] == 6700


class TestOewsReferenceMonth:
    def test_derives_may_of_the_latest_oews_year(self):
        assert oews_reference_month(["OCC_CODE", "TOT_EMP_23", "TOT_EMP_25", "TOT_EMP_24"]) == "2025-05"

    def test_raises_without_employment_columns(self):
        with pytest.raises(ValueError):
            oews_reference_month(["OCC_CODE", "A_MEDIAN_25"])


class TestResolveComparisonWindows:
    def test_anchor_is_the_last_month_at_or_before_the_oews_reference(self):
        panel_df = _panel([("2025-04", "15", 1), ("2025-06", "15", 1), ("2026-04", "15", 1), ("2026-06", "15", 1)])
        windows = resolve_comparison_windows(panel_df, "2025-05")
        assert windows.anchor_month == "2025-04"
        assert windows.latest_month == "2026-06"
        assert windows.year_ago_month == "2025-06"

    def test_anchor_ignores_backfilled_history_before_the_oews_handoff(self):
        """Back-filling older months must not drag the anchor away from the OEWS handoff."""
        panel_df = _panel([("2015-06", "15", 1), ("2025-04", "15", 1), ("2025-06", "15", 1), ("2026-06", "15", 1)])
        windows = resolve_comparison_windows(panel_df, "2025-05")
        assert windows.anchor_month == "2025-04"

    def test_year_ago_month_is_absent_when_the_panel_lacks_it(self):
        panel_df = _panel([("2025-04", "15", 1), ("2026-04", "15", 1), ("2026-06", "15", 1)])
        windows = resolve_comparison_windows(panel_df, "2025-05")
        assert windows.year_ago_month is None
        assert windows.year_over_year_label is None

    def test_falls_back_to_earliest_month_when_none_precede_the_reference(self):
        panel_df = _panel([("2025-08", "15", 1), ("2026-06", "15", 1)])
        windows = resolve_comparison_windows(panel_df, "2025-05")
        assert windows.anchor_month == "2025-08"

    def test_raises_with_fewer_than_two_months(self):
        with pytest.raises(ValueError, match="at least 2 months"):
            resolve_comparison_windows(_panel([("2026-06", "15", 1)]), "2025-05")

    def test_detects_a_january_crossing_in_the_since_anchor_window(self):
        windows = CpsComparisonWindows(anchor_month="2025-04", latest_month="2026-06", year_ago_month="2025-06")
        assert windows.since_anchor_crosses_january is True
        assert "January population-control update" in windows.window_caveat

    def test_omits_the_january_caveat_for_a_window_that_does_not_cross_one(self):
        """The caveat describes a dynamic window, so it must not assert a crossing that did not happen."""
        windows = CpsComparisonWindows(anchor_month="2026-02", latest_month="2026-06", year_ago_month=None)
        assert windows.since_anchor_crosses_january is False
        assert "January" not in windows.window_caveat
        assert "not seasonally adjusted" in windows.window_caveat

    def test_january_itself_counts_as_a_crossing(self):
        windows = CpsComparisonWindows(anchor_month="2025-12", latest_month="2026-01", year_ago_month=None)
        assert windows.since_anchor_crosses_january is True

    def test_labels_render_readable_month_names(self):
        windows = CpsComparisonWindows(anchor_month="2025-04", latest_month="2026-06", year_ago_month="2025-06")
        assert windows.since_anchor_label == "Apr 2025 → Jun 2026"
        assert windows.year_over_year_label == "Jun 2025 → Jun 2026"


class TestBuildGrowthFrame:
    def test_computes_both_windows_independently(self):
        panel_df = _panel([("2025-04", "15", 100.0), ("2025-06", "15", 200.0), ("2026-06", "15", 250.0)])
        windows = resolve_comparison_windows(panel_df, "2025-05")
        growth_df = build_growth_frame(panel_df, windows).set_index("soc_major")
        assert growth_df.loc["15", "emp_growth_since_anchor"] == pytest.approx(1.5)
        assert growth_df.loc["15", "emp_growth_year_over_year"] == pytest.approx(0.25)

    def test_omits_year_over_year_when_the_month_is_unavailable(self):
        panel_df = _panel([("2025-04", "15", 100.0), ("2026-06", "15", 150.0)])
        windows = resolve_comparison_windows(panel_df, "2025-05")
        growth_df = build_growth_frame(panel_df, windows)
        assert "emp_growth_year_over_year" not in growth_df.columns
        assert growth_df["emp_growth_since_anchor"].iloc[0] == pytest.approx(0.5)

    def test_end_to_end_from_the_fixture_uses_the_parsed_months(self):
        panel_df = merge_panel(_panel([("2025-04", "15", 6643.0), ("2025-04", "23", 1917.0)]), parse_a19_release(FIXTURE_PATH))
        windows = resolve_comparison_windows(panel_df, "2025-05")
        growth_df = build_growth_frame(panel_df, windows).set_index("soc_major")
        assert windows.since_anchor_label == "Apr 2025 → Jun 2026"
        assert growth_df.loc["15", "emp_growth_since_anchor"] == pytest.approx((6950 - 6643) / 6643)
        assert growth_df.loc["15", "emp_growth_year_over_year"] == pytest.approx((6950 - 6602) / 6602)


class TestYearOverYearMonthPairs:
    def test_returns_only_months_whose_year_ago_counterpart_is_present(self):
        panel_df = _panel(
            [
                ("2025-04", "15", 100.0),
                ("2025-06", "15", 110.0),
                ("2026-04", "15", 120.0),
                ("2026-08", "15", 130.0),
            ]
        )
        assert year_over_year_month_pairs(panel_df) == [("2025-04", "2026-04")]

    def test_returns_every_supported_pair_oldest_first(self):
        panel_df = _panel(
            [
                ("2025-04", "15", 100.0),
                ("2025-06", "15", 100.0),
                ("2025-08", "15", 100.0),
                ("2026-04", "15", 110.0),
                ("2026-06", "15", 110.0),
                ("2026-08", "15", 110.0),
            ]
        )
        assert year_over_year_month_pairs(panel_df) == [
            ("2025-04", "2026-04"),
            ("2025-06", "2026-06"),
            ("2025-08", "2026-08"),
        ]

    def test_returns_empty_when_no_month_has_a_year_ago_counterpart(self):
        panel_df = _panel([("2025-04", "15", 100.0), ("2025-06", "15", 110.0)])
        assert year_over_year_month_pairs(panel_df) == []


class TestBuildYearOverYearGrowth:
    def test_computes_growth_for_the_requested_pair_only(self):
        panel_df = _panel(
            [
                ("2025-06", "15", 100.0),
                ("2025-08", "15", 200.0),
                ("2026-06", "15", 150.0),
                ("2026-08", "15", 250.0),
            ]
        )
        june_growth_df = build_year_over_year_growth(panel_df, "2025-06", "2026-06").set_index("soc_major")
        august_growth_df = build_year_over_year_growth(panel_df, "2025-08", "2026-08").set_index("soc_major")
        assert june_growth_df.loc["15", "emp_growth_year_over_year"] == pytest.approx(0.5)
        assert august_growth_df.loc["15", "emp_growth_year_over_year"] == pytest.approx(0.25)

    def test_drops_groups_missing_from_either_endpoint(self):
        panel_df = _panel([("2025-06", "15", 100.0), ("2026-06", "15", 150.0), ("2026-06", "23", 80.0)])
        growth_df = build_year_over_year_growth(panel_df, "2025-06", "2026-06")
        assert growth_df["soc_major"].tolist() == ["15"]

    def test_raises_when_a_requested_month_is_absent(self):
        panel_df = _panel([("2025-06", "15", 100.0), ("2026-06", "15", 150.0)])
        with pytest.raises(ValueError, match="missing month"):
            build_year_over_year_growth(panel_df, "2025-07", "2026-06")


class TestLoadCpsPanel:
    def test_falls_back_to_the_seed_when_no_release_was_fetched(self, tmp_path):
        """The CI degradation path: a blocked download still yields real, correctly labelled months."""
        seed_path = tmp_path / "seed.csv"
        _panel([("2025-04", "15", 6643), ("2026-04", "15", 6834)]).to_csv(seed_path, index=False)
        panel_df = load_cps_panel(str(seed_path), str(tmp_path / "absent.html"), None)
        assert sorted(panel_df["month"].unique()) == ["2025-04", "2026-04"]

    def test_merges_the_fetched_release_over_the_seed(self, tmp_path):
        seed_path = tmp_path / "seed.csv"
        output_path = tmp_path / "out" / "panel.csv"
        _panel([("2025-04", "15", 6643), ("2026-04", "15", 6834)]).to_csv(seed_path, index=False)
        panel_df = load_cps_panel(str(seed_path), FIXTURE_PATH, str(output_path))
        assert sorted(panel_df["month"].unique()) == ["2025-04", "2025-06", "2026-04", "2026-06"]
        assert output_path.exists()

    def test_falls_back_to_the_seed_when_the_release_cannot_be_parsed(self, tmp_path):
        """A BLS layout change must degrade to the seed, not take down the validation stage."""
        seed_path = tmp_path / "seed.csv"
        _panel([("2025-04", "15", 6643), ("2026-04", "15", 6834)]).to_csv(seed_path, index=False)
        broken_release = tmp_path / "broken.html"
        broken_release.write_text(open(FIXTURE_PATH, encoding="utf-8").read().replace(">Total<", ">Grand total<"), encoding="utf-8")
        panel_df = load_cps_panel(str(seed_path), str(broken_release), None)
        assert sorted(panel_df["month"].unique()) == ["2025-04", "2026-04"]

    def test_returns_none_when_the_release_is_unparseable_and_no_seed_exists(self, tmp_path):
        broken_release = tmp_path / "broken.html"
        broken_release.write_text(open(FIXTURE_PATH, encoding="utf-8").read().replace(">Total<", ">Grand total<"), encoding="utf-8")
        assert load_cps_panel(str(tmp_path / "absent.csv"), str(broken_release), None) is None

    def test_returns_none_when_neither_source_exists(self, tmp_path):
        assert load_cps_panel(str(tmp_path / "absent.csv"), str(tmp_path / "absent.html"), None) is None

    def test_preserves_leading_zero_soc_codes_from_the_seed(self, tmp_path):
        """soc_major must stay a string — read as int, '11' would become 11 and break the merge."""
        seed_path = tmp_path / "seed.csv"
        _panel([("2025-04", "11", 21016), ("2026-04", "11", 20526)]).to_csv(seed_path, index=False)
        panel_df = load_cps_panel(str(seed_path), str(tmp_path / "absent.html"), None)
        assert panel_df["soc_major"].tolist() == ["11", "11"]
