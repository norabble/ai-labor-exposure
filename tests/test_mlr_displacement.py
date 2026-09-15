"""Tests for mlr_displacement.py — parsing displacement rates out of the MLR article PDFs."""

import os

import pytest

from mlr_displacement import MLR_OCCUPATION_LEAVES, parse_displacement_rate_table

ARTICLE_PATH = "data/raw/dws/mlr/mid_1990s_1999.pdf"
ARTICLE_PRESENT = os.path.exists(ARTICLE_PATH)


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
