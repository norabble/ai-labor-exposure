"""Tests for mlr_displacement.py — parsing displacement rates out of the MLR article PDFs."""

import os

import pytest

from mlr_displacement import MLR_OCCUPATION_LEAVES, _normalize_occupation_key, parse_displacement_rate_table

ARTICLE_PATH = "data/raw/dws/mlr/mid_1990s_1999.pdf"
ARTICLE_PRESENT = os.path.exists(ARTICLE_PATH)

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
