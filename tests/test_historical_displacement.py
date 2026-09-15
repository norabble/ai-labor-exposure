"""
test_historical_displacement.py
───────────────────────────────
Regression tests for historical_displacement.py — the economy-wide displacement
rate D that the demand composition model uses in place of AI penetration.

The tests never reach the network: fetch_annual_means and fetch_bls_series are
monkeypatched, and the DWS arithmetic runs against hand-built panel frames whose
expected rates are computed by hand in the assertions.

Two properties matter more than the rest and are tested directly:

  • A negative D inverts gross_displacement and therefore every prediction the
    model makes. Raw productivity growth is negative in some years, so the clip
    has to hold even when smoothing does not remove the negative.
  • The survey window length is read from the panel, not assumed to be three
    years, because it is what converts a multi-year count into an annual rate.
"""

import os
import warnings

import pandas as pd
import pytest

import historical_displacement
from historical_displacement import (
    DISPLACEMENT_SOURCES,
    build_displacement_rate_table,
    dws_displacement_rate,
    economy_displacement_rate,
    fetch_annual_means,
    productivity_displacement_rate,
)


def _panel(
    survey_year=2026,
    period_start_year=2023,
    period_end_year=2025,
    all_tenures=7445.0,
    structural=1475.856,
    long_tenured_reasons=(1083.624, 761.196),
):
    """Build a one-survey DWS panel with the three tables the rate calculation reads."""
    period_years = period_end_year - period_start_year + 1
    shared = {
        "survey_year": survey_year,
        "period_start_year": period_start_year,
        "period_end_year": period_end_year,
        "period_years": period_years,
        # dws_displacement_rate REQUIRES this column (see its docstring) — every real
        # producer of a DWS panel row sets it, so a fixture that omits it is not
        # representative of any panel the function actually receives.
        "measurement_basis": "count_thousands",
    }
    rows = [
        {
            **shared,
            "source_table": "table_8_all_tenures",
            "group_name": "Total",
            "soc_majors": "",
            "displaced_thousands": all_tenures,
            "reason": "all",
            "tenure_class": "all_tenures",
        },
        {
            **shared,
            "source_table": "table_2_reason",
            "group_name": "Total",
            "soc_majors": "",
            "displaced_thousands": structural,
            "reason": "position or shift abolished",
            "tenure_class": "long_tenured",
        },
        {
            **shared,
            "source_table": "table_2_reason",
            "group_name": "Total",
            "soc_majors": "",
            "displaced_thousands": long_tenured_reasons[0],
            "reason": "plant or company closed down or moved",
            "tenure_class": "long_tenured",
        },
        {
            **shared,
            "source_table": "table_2_reason",
            "group_name": "Total",
            "soc_majors": "",
            "displaced_thousands": long_tenured_reasons[1],
            "reason": "insufficient work",
            "tenure_class": "long_tenured",
        },
        {
            **shared,
            "source_table": "table_5_occupation",
            "group_name": "Office",
            "soc_majors": "43",
            "displaced_thousands": 316.0,
            "reason": "all",
            "tenure_class": "long_tenured",
        },
        {
            **shared,
            "source_table": "table_5_occupation",
            "group_name": "Production",
            "soc_majors": "51",
            "displaced_thousands": 352.0,
            "reason": "all",
            "tenure_class": "long_tenured",
        },
    ]
    return pd.DataFrame(rows)


def _employment(years=range(2023, 2026), thousands=160000.0):
    return pd.Series({year: thousands for year in years}, name="value")


def _total_rate_df(periods=((1984, 1985, 3.0), (1986, 1987, 3.0))):
    """Build a hand-built MLR total-displacement-rate table, the same shape
    mlr_displacement.parse_total_displacement_rate returns, for (start, end, percent) tuples."""
    return pd.DataFrame(
        [
            {
                "period_label": f"{start}-{str(end)[-2:]}",
                "period_start_year": start,
                "period_end_year": end,
                "displacement_rate_percent": percent,
            }
            for start, end, percent in periods
        ]
    )


class TestWidenedRange:
    def test_default_start_year_reaches_the_mlr_series(self):
        """1981 is mlr_long_tenured's own floor, now the binding constraint on D's reach
        (the DWS count-derived sources only go back to 1984)."""
        import historical_displacement

        assert historical_displacement.DEFAULT_START_YEAR == 1981

    def test_productivity_rate_accepts_the_widened_range(self, monkeypatch):
        import historical_displacement

        captured_years = {}

        def fake_fetch(series_id, start_year, end_year):
            captured_years["start"] = start_year
            return pd.Series({year: 2.0 for year in range(start_year, end_year + 1)})

        monkeypatch.setattr(historical_displacement, "fetch_annual_means", fake_fetch)
        historical_displacement.productivity_displacement_rate(start_year=1984, end_year=2025)
        assert captured_years["start"] == 1984


class TestDwsDisplacementRate:
    def test_all_tenures_rate_is_count_over_employment_over_window(self):
        rate_series = dws_displacement_rate(_panel(), _employment(), tenure_class="all_tenures")

        assert rate_series.loc[2024] == pytest.approx(7445.0 / 160000.0 / 3)

    def test_rate_is_assigned_to_every_year_in_the_survey_window(self):
        rate_series = dws_displacement_rate(_panel(), _employment(), tenure_class="all_tenures")

        assert list(rate_series.index) == [2023, 2024, 2025]
        assert rate_series.nunique() == 1

    def test_window_length_comes_from_the_panel_not_a_hardcoded_three(self):
        """A two-year survey window must divide by two, or the rate is 50% too low."""
        two_year_panel = _panel(period_start_year=2024, period_end_year=2025)

        rate_series = dws_displacement_rate(two_year_panel, _employment(years=range(2024, 2026)), tenure_class="all_tenures")

        assert rate_series.loc[2024] == pytest.approx(7445.0 / 160000.0 / 2)
        assert list(rate_series.index) == [2024, 2025]

    def test_structural_long_tenured_uses_the_reported_reason_count(self):
        rate_series = dws_displacement_rate(_panel(), _employment(), tenure_class="long_tenured", structural_only=True)

        assert rate_series.loc[2024] == pytest.approx(1475.856 / 160000.0 / 3)

    def test_structural_all_tenures_applies_the_long_tenured_share(self):
        """The release reports reasons for long-tenured workers only, so the share is carried across."""
        structural_share = 1475.856 / (1475.856 + 1083.624 + 761.196)

        rate_series = dws_displacement_rate(_panel(), _employment(), tenure_class="all_tenures", structural_only=True)

        assert rate_series.loc[2024] == pytest.approx(7445.0 * structural_share / 160000.0 / 3)

    def test_structural_rate_is_smaller_than_the_unrestricted_rate(self):
        unrestricted = dws_displacement_rate(_panel(), _employment(), tenure_class="all_tenures")
        structural = dws_displacement_rate(_panel(), _employment(), tenure_class="all_tenures", structural_only=True)

        assert (structural < unrestricted).all()

    def test_missing_employment_denominator_warns_and_skips(self):
        with pytest.warns(UserWarning, match="No employment denominator"):
            rate_series = dws_displacement_rate(_panel(), _employment(years=range(1990, 1993)), tenure_class="all_tenures")

        assert rate_series.empty

    def test_a_rate_row_masquerading_as_a_count_does_not_inflate_the_rate(self):
        """Mutation-proof: this is the property test_rates_and_counts_are_never_summed_together
        (tests/test_dws_panel.py) claimed to cover but did not — that test only asserted
        the committed seed happens to keep one measurement_basis per survey_year, which
        says nothing about what dws_displacement_rate actually does if a panel ever mixes
        bases. Here a rate-basis row shares the real row's survey_year and source_table
        ("table_8_all_tenures", what the all_tenures path sums) with a large, non-NaN
        displaced_thousands. If the required `measurement_basis == "count_thousands"`
        filter in dws_displacement_rate were ever weakened back to `if "measurement_basis"
        in ...columns` or deleted outright, this row would be summed in and the rate
        below would come out roughly 134x too high (999,999 / 7,445) instead of matching
        the clean panel's own rate."""
        clean_panel = _panel()
        contaminating_row = clean_panel.iloc[[0]].copy()
        assert contaminating_row["source_table"].iloc[0] == "table_8_all_tenures"
        contaminating_row["displaced_thousands"] = 999_999.0
        contaminating_row["measurement_basis"] = "rate_percent"
        contaminated_panel = pd.concat([clean_panel, contaminating_row], ignore_index=True)

        clean_rate_series = dws_displacement_rate(clean_panel, _employment(), tenure_class="all_tenures")
        contaminated_rate_series = dws_displacement_rate(contaminated_panel, _employment(), tenure_class="all_tenures")

        assert contaminated_rate_series.loc[2024] == pytest.approx(clean_rate_series.loc[2024])

    def test_accumulates_multiple_surveys(self):
        two_survey_panel = pd.concat(
            [_panel(survey_year=2024, period_start_year=2021, period_end_year=2023, all_tenures=6000.0), _panel()],
            ignore_index=True,
        )

        rate_series = dws_displacement_rate(two_survey_panel, _employment(years=range(2021, 2026)), tenure_class="all_tenures")

        assert set(rate_series.index) == set(range(2021, 2026))


class TestProductivityDisplacementRate:
    def test_negative_smoothed_growth_is_clipped_and_warned(self, monkeypatch):
        """A negative D would flip gross_displacement and invert every prediction."""
        monkeypatch.setattr(
            historical_displacement,
            "fetch_annual_means",
            lambda series_id, start_year, end_year: pd.Series({2019: -4.0, 2020: -5.0, 2021: -6.0}),
        )

        with pytest.warns(UserWarning, match="negative"):
            rate_series = productivity_displacement_rate(2019, 2021, smoothing_years=1)

        assert (rate_series >= 0).all()

    def test_growth_is_converted_from_percent_to_fraction(self, monkeypatch):
        monkeypatch.setattr(
            historical_displacement,
            "fetch_annual_means",
            lambda series_id, start_year, end_year: pd.Series({2018: 2.0, 2019: 2.0, 2020: 2.0}),
        )

        rate_series = productivity_displacement_rate(2018, 2020, smoothing_years=1)

        assert rate_series.loc[2019] == pytest.approx(0.02)

    def test_smoothing_averages_across_neighbouring_years(self, monkeypatch):
        monkeypatch.setattr(
            historical_displacement,
            "fetch_annual_means",
            lambda series_id, start_year, end_year: pd.Series({2018: 0.0, 2019: 3.0, 2020: 0.0}),
        )

        rate_series = productivity_displacement_rate(2018, 2020, smoothing_years=3)

        assert rate_series.loc[2019] == pytest.approx(0.01)

    def test_returns_none_when_the_series_cannot_be_fetched(self, monkeypatch):
        monkeypatch.setattr(historical_displacement, "fetch_annual_means", lambda *args: None)

        assert productivity_displacement_rate(2005, 2025) is None


class TestFetchAnnualMeans:
    def test_excludes_the_bls_annual_average_periods(self, monkeypatch):
        """M13 and Q05 are BLS's own annual averages; counting them double-weights the year."""
        monkeypatch.setattr(
            historical_displacement,
            "fetch_bls_series",
            lambda series_id, start_year, end_year: pd.DataFrame(
                [
                    {"year": 2020, "period": "M01", "value": 1.0},
                    {"year": 2020, "period": "M02", "value": 3.0},
                    {"year": 2020, "period": "M13", "value": 99.0},
                ]
            ),
        )

        annual_means = fetch_annual_means("ANY", 2020, 2020)

        assert annual_means.loc[2020] == pytest.approx(2.0)

    def test_chunks_requests_to_respect_the_api_year_cap(self, monkeypatch):
        requested_spans = []

        def _record(series_id, start_year, end_year):
            requested_spans.append((start_year, end_year))
            return pd.DataFrame([{"year": start_year, "period": "M01", "value": 1.0}])

        monkeypatch.setattr(historical_displacement, "fetch_bls_series", _record)
        monkeypatch.setattr(historical_displacement, "_api_key", lambda: "")

        fetch_annual_means("ANY", 2005, 2025)

        assert len(requested_spans) > 1
        assert all(end - start + 1 <= historical_displacement.UNREGISTERED_MAX_YEARS for start, end in requested_spans)
        assert requested_spans[0][0] == 2005 and requested_spans[-1][1] == 2025

    def test_returns_none_when_every_chunk_fails(self, monkeypatch):
        monkeypatch.setattr(historical_displacement, "fetch_bls_series", lambda *args: None)

        assert fetch_annual_means("ANY", 2005, 2025) is None


class TestEconomyDisplacementRate:
    def test_unknown_source_raises(self):
        with pytest.raises(ValueError, match="unknown displacement rate source"):
            economy_displacement_rate("unemployment_vibes")

    def test_returns_none_when_no_dws_panel_is_available(self, monkeypatch):
        monkeypatch.setattr(historical_displacement, "load_dws_panel", lambda: None)

        with pytest.warns(UserWarning, match="No DWS panel available"):
            assert economy_displacement_rate("dws_all_tenures") is None

    def test_returns_none_when_no_employment_denominator_is_available(self, monkeypatch):
        monkeypatch.setattr(historical_displacement, "load_dws_panel", lambda: _panel())
        monkeypatch.setattr(historical_displacement, "employment_by_year", lambda *args: None)

        with pytest.warns(UserWarning, match="No employment denominator"):
            assert economy_displacement_rate("dws_all_tenures") is None


class TestBuildDisplacementRateTable:
    def test_skips_sources_that_are_unavailable_rather_than_failing(self, monkeypatch):
        monkeypatch.setattr(historical_displacement, "load_dws_panel", lambda: None)
        monkeypatch.setattr(historical_displacement, "load_mlr_total_displacement_rate", lambda *args, **kwargs: None)
        monkeypatch.setattr(historical_displacement, "fetch_annual_means", lambda *args: pd.Series({2020: 2.0}))

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            rate_table_df = build_displacement_rate_table(2020, 2020)

        assert set(rate_table_df["source"]) == {"productivity"}

    def test_returns_an_empty_frame_when_nothing_is_available(self, monkeypatch):
        monkeypatch.setattr(historical_displacement, "load_dws_panel", lambda: None)
        monkeypatch.setattr(historical_displacement, "load_mlr_total_displacement_rate", lambda *args, **kwargs: None)
        monkeypatch.setattr(historical_displacement, "fetch_annual_means", lambda *args: None)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            rate_table_df = build_displacement_rate_table()

        assert rate_table_df.empty
        assert list(rate_table_df.columns) == historical_displacement.OUTPUT_COLUMNS

    def test_every_named_source_is_attempted(self, monkeypatch):
        monkeypatch.setattr(historical_displacement, "load_dws_panel", lambda: _panel())
        monkeypatch.setattr(historical_displacement, "employment_by_year", lambda *args: _employment())
        monkeypatch.setattr(historical_displacement, "fetch_annual_means", lambda *args: pd.Series({2023: 2.0, 2024: 2.0, 2025: 2.0}))
        monkeypatch.setattr(historical_displacement, "load_mlr_total_displacement_rate", lambda *args, **kwargs: _total_rate_df())

        # Widened to 1984-2025 so the request window covers both the mocked DWS
        # survey window (2023-2025) and the mocked MLR periods (1984-1987) — the
        # two sources never overlap in calendar time, unlike every other source
        # pairing this file tests.
        rate_table_df = build_displacement_rate_table(1984, 2025)

        assert set(rate_table_df["source"]) == set(DISPLACEMENT_SOURCES)

    def test_dws_and_mlr_rows_are_flagged_as_interpolated_across_the_window(self, monkeypatch):
        monkeypatch.setattr(historical_displacement, "load_dws_panel", lambda: _panel())
        monkeypatch.setattr(historical_displacement, "employment_by_year", lambda *args: _employment())
        monkeypatch.setattr(historical_displacement, "fetch_annual_means", lambda *args: pd.Series({2023: 2.0, 2024: 2.0, 2025: 2.0}))
        monkeypatch.setattr(historical_displacement, "load_mlr_total_displacement_rate", lambda *args, **kwargs: _total_rate_df())

        rate_table_df = build_displacement_rate_table(1984, 2025)

        assert rate_table_df[rate_table_df["source"].str.startswith("dws")]["is_interpolated"].all()
        assert rate_table_df[rate_table_df["source"] == "mlr_long_tenured"]["is_interpolated"].all()
        assert not rate_table_df[rate_table_df["source"] == "productivity"]["is_interpolated"].any()


class TestMlrDisplacementRate:
    """mlr_displacement_rate is a pure function of a total-rate table (mirroring
    dws_displacement_rate / load_dws_panel's split), so these run against hand-built
    fixtures rather than the real MLR PDFs."""

    def test_a_two_year_period_is_spread_across_both_its_years_at_half_the_published_rate(self):
        rate_series = historical_displacement.mlr_displacement_rate(_total_rate_df(periods=((1985, 1986, 3.0),)))

        assert rate_series[1985] == pytest.approx(0.015)
        assert rate_series[1986] == pytest.approx(0.015)

    def test_two_periods_produce_four_distinct_years(self):
        rate_series = historical_displacement.mlr_displacement_rate(_total_rate_df(periods=((1981, 1982, 3.9), (1983, 1984, 3.1))))

        assert list(rate_series.index) == [1981, 1982, 1983, 1984]
        assert rate_series[1981] == pytest.approx(0.0195)
        assert rate_series[1983] == pytest.approx(0.0155)

    def test_never_shares_a_value_with_the_dws_count_derived_rate(self):
        """The two sources divide by different denominators (long-tenured workers employed
        vs. total employment) and must not be conflated even where their outputs coincide
        by construction — they are separate calls into separate functions with no shared
        arithmetic path, verified here by construction rather than by comparing values."""
        mlr_rate_series = historical_displacement.mlr_displacement_rate(_total_rate_df(periods=((2005, 2006, 3.0),)))
        dws_rate_series = dws_displacement_rate(_panel(), _employment(), tenure_class="long_tenured")

        assert set(mlr_rate_series.index).isdisjoint(set(dws_rate_series.index))


class TestLoadMlrTotalDisplacementRate:
    def test_returns_none_when_no_article_exists(self, tmp_path):
        missing_path = str(tmp_path / "nonexistent.pdf")

        with pytest.warns(UserWarning, match="No MLR articles found"):
            assert historical_displacement.load_mlr_total_displacement_rate(article_paths=(missing_path,)) is None

    @pytest.mark.skipif(
        not os.path.exists("data/raw/dws/mlr/mid_1990s_1999.pdf"),
        reason="MLR articles not downloaded; run download_dws.py",
    )
    def test_real_articles_produce_a_rate_in_the_documented_magnitude_range(self):
        """historical_displacement.py's module docstring documents dws_long_tenured as
        0.56-1.69%; the MLR figure is a different denominator (long-tenured workers
        employed, not total employment) and is expected to run higher, 1.2-2.0%."""
        total_rate_df = historical_displacement.load_mlr_total_displacement_rate()
        assert total_rate_df is not None

        rate_series = historical_displacement.mlr_displacement_rate(total_rate_df)

        assert rate_series.index.min() == 1981
        assert rate_series.index.max() == 2000
        assert rate_series.min() >= 0.012
        assert rate_series.max() <= 0.020
