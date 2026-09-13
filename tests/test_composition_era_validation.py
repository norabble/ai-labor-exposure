"""
test_composition_era_validation.py
──────────────────────────────────
Regression tests for composition_era_validation.py — the era comparison and the
cycle decomposition that together answer whether the demand-type signal is
era-invariant.

The statistics are tested against synthetic series with known answers rather
than against the pipeline's own numbers, so a change in the data cannot quietly
make a broken statistic look right.

Two behaviours are load-bearing:

  • Correlations are averaged and tested in Fisher-z space, not in r space. r is
    bounded and its sampling distribution is skewed, so averaging raw r values
    understates strong correlations.
  • COVID periods are excluded from both the era comparison and the cycle
    decomposition. 2019→20 and 2020→21 are shutdown and rehiring, and they
    dominate the unemployment-change term if left in.
"""

import numpy as np
import pandas as pd
import pytest

import historical_displacement
from composition_era_validation import (
    AI_ERA_FIRST_PERIOD,
    CHART_NAME,
    COMPOSITION_SCORE_COLUMN,
    COVID_PERIODS,
    CPS_CHART_NAME,
    CYCLE_OUTPUT_COLUMNS,
    OCCUPATION_CHART_NAME,
    OUTPUT_COLUMNS,
    _period_sort_key,
    build_cps_period_correlations,
    build_period_correlations,
    correlate_with_displacement_rate,
    cps_group_correlation,
    decompose_fit_strength,
    discover_period_columns,
    is_ai_era,
    occupation_correlation,
    period_key,
    plot_signal_over_time,
    sector_correlation,
    summarise_eras,
    unemployment_change_by_period,
)
from validate_bls import build_unit_scores


def _correlation_frame(period_r_pairs, score=COMPOSITION_SCORE_COLUMN, covid_periods=("2019_2020", "2020_2021")):
    """Build a period-correlation frame from (period, r) pairs."""
    return pd.DataFrame(
        [
            {
                "period": period,
                "score": score,
                "fit_r": correlation,
                "fit_p": 0.01 if abs(correlation) > 0.42 else 0.30,
                "n_units": 22,
                "era": "ai" if is_ai_era(f"emp_growth_{period}") else "pre_ai",
                "is_covid": period in covid_periods,
            }
            for period, correlation in period_r_pairs
        ]
    )


class TestPeriodHelpers:
    def test_period_key_strips_either_prefix(self):
        assert period_key("hist_emp_growth_2007_2008") == "2007_2008"
        assert period_key("emp_growth_2023_2024") == "2023_2024"

    @pytest.mark.parametrize(
        "growth_column,expected",
        [
            ("hist_emp_growth_2021_2022", False),
            ("emp_growth_2022_2023", True),
            ("emp_growth_2024_2025", True),
            ("hist_emp_growth_2005_2006", False),
        ],
    )
    def test_ai_era_boundary_is_2022_23(self, growth_column, expected):
        assert is_ai_era(growth_column) is expected

    def test_discover_period_columns_is_chronological_and_excludes_aggregates(self):
        trends_df = pd.DataFrame(
            columns=[
                "emp_growth_composite",
                "hist_emp_growth_2021_2022",
                "hist_emp_growth_2005_2006",
                "hist_emp_growth_pre_ai",
                "emp_growth_2023_2024",
                "emp_growth_2022_2023",
                "wage_growth_2022_2023",
            ]
        )

        period_columns = discover_period_columns(trends_df)

        assert period_columns == [
            "hist_emp_growth_2005_2006",
            "hist_emp_growth_2021_2022",
            "emp_growth_2022_2023",
            "emp_growth_2023_2024",
        ]

    def test_wage_growth_columns_are_not_treated_as_periods(self):
        trends_df = pd.DataFrame(columns=["wage_growth_2022_2023", "hist_wage_growth_2005_2006"])

        assert discover_period_columns(trends_df) == []


class TestSectorCorrelation:
    def _scored_frame(self, n_sectors=22):
        rows = []
        for sector_index in range(n_sectors):
            soc_major = f"{11 + 2 * sector_index:02d}"
            rows.append(
                {
                    "OCC_CODE": f"{soc_major}-0001",
                    "soc_major": soc_major,
                    COMPOSITION_SCORE_COLUMN: sector_index / n_sectors,
                    "emp_growth_2022_2023": sector_index / n_sectors,
                    "TOT_EMP_2025": 100_000.0,
                }
            )
        return pd.DataFrame(rows)

    def test_perfectly_aligned_score_and_growth_give_r_of_one(self):
        result = sector_correlation(self._scored_frame(), COMPOSITION_SCORE_COLUMN, "emp_growth_2022_2023", "TOT_EMP_2025", None)

        assert result is not None
        correlation, _, n_sectors = result
        assert correlation == pytest.approx(1.0)
        assert n_sectors == 22

    def test_returns_none_when_too_few_occupations(self):
        thin_df = self._scored_frame(n_sectors=4)

        assert sector_correlation(thin_df, COMPOSITION_SCORE_COLUMN, "emp_growth_2022_2023", "TOT_EMP_2025", None) is None

    def test_build_period_correlations_covers_every_period_and_score(self):
        scored_df = self._scored_frame()
        scored_df["hist_emp_growth_2020_2021"] = scored_df["emp_growth_2022_2023"]

        correlation_df = build_period_correlations(scored_df, "TOT_EMP_2025", None, [COMPOSITION_SCORE_COLUMN])

        assert set(correlation_df["period"]) == {"2020_2021", "2022_2023"}
        assert set(correlation_df["era"]) == {"pre_ai", "ai"}
        assert correlation_df.loc[correlation_df["period"] == "2020_2021", "is_covid"].all()


class TestSummariseEras:
    def test_splits_periods_into_the_two_eras(self):
        correlation_df = _correlation_frame([("2005_2006", 0.1), ("2018_2019", 0.2), ("2022_2023", 0.5), ("2023_2024", 0.6)])

        era_summary_df = summarise_eras(correlation_df)

        assert list(era_summary_df.columns) == OUTPUT_COLUMNS
        assert set(era_summary_df["era"]) == {"pre_ai", "ai"}
        assert era_summary_df.loc[era_summary_df["era"] == "pre_ai", "n_periods"].iloc[0] == 2
        assert era_summary_df.loc[era_summary_df["era"] == "ai", "n_periods"].iloc[0] == 2

    def test_mean_is_taken_in_fisher_z_space(self):
        """Averaging raw r understates strong correlations; z-averaging does not."""
        correlation_df = _correlation_frame([("2005_2006", 0.2), ("2006_2007", 0.9), ("2022_2023", 0.1), ("2023_2024", 0.1)])

        era_summary_df = summarise_eras(correlation_df)
        pre_ai_mean = era_summary_df.loc[era_summary_df["era"] == "pre_ai", "mean_r"].iloc[0]

        assert pre_ai_mean == pytest.approx(np.tanh((np.arctanh(0.2) + np.arctanh(0.9)) / 2))
        assert pre_ai_mean > (0.2 + 0.9) / 2

    def test_covid_periods_are_excluded_by_default(self):
        correlation_df = _correlation_frame([("2005_2006", 0.1), ("2019_2020", 0.9), ("2022_2023", 0.3), ("2023_2024", 0.3)])

        excluded_summary_df = summarise_eras(correlation_df, exclude_covid=True)
        included_summary_df = summarise_eras(correlation_df, exclude_covid=False)

        assert excluded_summary_df.loc[excluded_summary_df["era"] == "pre_ai", "n_periods"].iloc[0] == 1
        assert included_summary_df.loc[included_summary_df["era"] == "pre_ai", "n_periods"].iloc[0] == 2

    def test_counts_individually_significant_periods(self):
        correlation_df = _correlation_frame([("2005_2006", 0.9), ("2006_2007", 0.1), ("2022_2023", 0.3), ("2023_2024", 0.3)])

        era_summary_df = summarise_eras(correlation_df)

        assert era_summary_df.loc[era_summary_df["era"] == "pre_ai", "n_significant"].iloc[0] == 1

    def test_era_difference_is_nan_when_one_era_is_too_short(self):
        correlation_df = _correlation_frame([("2005_2006", 0.1), ("2006_2007", 0.2), ("2022_2023", 0.5)])

        era_summary_df = summarise_eras(correlation_df)

        assert era_summary_df["welch_p"].isna().all()


class TestDecomposeFitStrength:
    def test_recovers_a_planted_cycle_coefficient(self):
        """Fit strength built as z = 0.2 + 0.15·dU must come back with those coefficients."""
        periods = ["2005_2006", "2006_2007", "2007_2008", "2008_2009", "2018_2019", "2022_2023", "2023_2024", "2024_2025"]
        unemployment_change = pd.Series(dict(zip(periods, [-1.0, 0.0, 1.0, 2.0, 3.0, -0.5, 0.2, 0.1])))
        planted_r = [np.tanh(0.2 + 0.15 * unemployment_change[period]) for period in periods]
        correlation_df = _correlation_frame(list(zip(periods, planted_r)))

        cycle_df = decompose_fit_strength(correlation_df, unemployment_change)

        assert list(cycle_df.columns) == CYCLE_OUTPUT_COLUMNS
        coefficients = cycle_df.set_index("term")["coefficient"]
        assert coefficients["intercept"] == pytest.approx(0.2, abs=1e-6)
        assert coefficients["unemployment_change"] == pytest.approx(0.15, abs=1e-6)

    def test_detects_an_ai_era_premium_over_and_above_the_cycle(self):
        periods = ["2005_2006", "2006_2007", "2007_2008", "2008_2009", "2018_2019", "2022_2023", "2023_2024", "2024_2025"]
        unemployment_change = pd.Series(dict(zip(periods, [-1.0, 0.0, 1.0, 3.0, 0.0, 0.0, 0.2, 0.1])))
        planted_r = [
            np.tanh(0.1 + 0.1 * unemployment_change[period] + (0.4 if is_ai_era(f"emp_growth_{period}") else 0.0)) for period in periods
        ]

        cycle_df = decompose_fit_strength(_correlation_frame(list(zip(periods, planted_r))), unemployment_change)
        coefficients = cycle_df.set_index("term")["coefficient"]

        assert coefficients["ai_era"] == pytest.approx(0.4, abs=1e-6)

    def test_reports_no_ai_premium_when_the_cycle_explains_everything(self):
        periods = ["2005_2006", "2006_2007", "2007_2008", "2008_2009", "2018_2019", "2022_2023", "2023_2024", "2024_2025"]
        unemployment_change = pd.Series(dict(zip(periods, [-1.0, 0.0, 1.0, 3.0, 0.0, 0.0, 0.2, 0.1])))
        planted_r = [np.tanh(0.2 + 0.15 * unemployment_change[period]) for period in periods]

        cycle_df = decompose_fit_strength(_correlation_frame(list(zip(periods, planted_r))), unemployment_change)
        coefficients = cycle_df.set_index("term")["coefficient"]

        assert coefficients["ai_era"] == pytest.approx(0.0, abs=1e-6)

    def test_covid_periods_are_excluded_from_the_regression(self):
        periods = ["2005_2006", "2006_2007", "2007_2008", "2008_2009", "2019_2020", "2022_2023", "2023_2024", "2024_2025"]
        unemployment_change = pd.Series(dict(zip(periods, [-1.0, 0.0, 1.0, 3.0, 4.4, 0.0, 0.2, 0.1])))
        correlation_df = _correlation_frame(list(zip(periods, [0.2, 0.3, 0.4, 0.5, 0.95, 0.3, 0.3, 0.3])))

        cycle_df = decompose_fit_strength(correlation_df, unemployment_change)

        assert cycle_df["n_periods"].iloc[0] == len(periods) - 1

    def test_skips_a_score_with_too_few_periods_to_fit(self):
        unemployment_change = pd.Series({"2005_2006": 0.0, "2022_2023": 1.0})
        correlation_df = _correlation_frame([("2005_2006", 0.2), ("2022_2023", 0.3)])

        assert decompose_fit_strength(correlation_df, unemployment_change).empty

    def test_periods_confined_to_one_era_warn_instead_of_raising(self):
        """Without both eras the AI-era effect is unidentified; the normal equations are singular."""
        periods = ["2005_2006", "2006_2007", "2007_2008", "2008_2009", "2018_2019"]
        unemployment_change = pd.Series(dict(zip(periods, [-1.0, 0.0, 1.0, 2.0, 3.0])))
        correlation_df = _correlation_frame(list(zip(periods, [0.2, 0.3, 0.4, 0.5, 0.1])))

        with pytest.warns(UserWarning, match="do not span both eras"):
            cycle_df = decompose_fit_strength(correlation_df, unemployment_change)

        assert cycle_df.empty


class TestFourDigitPeriods:
    def test_ai_era_boundary_is_four_digits(self):
        assert AI_ERA_FIRST_PERIOD == "2022_2023"

    def test_covid_periods_are_four_digits(self):
        assert COVID_PERIODS == ("2019_2020", "2020_2021")

    def test_period_key_strips_both_prefixes(self):
        assert period_key("hist_emp_growth_2007_2008") == "2007_2008"
        assert period_key("emp_growth_2023_2024") == "2023_2024"

    def test_century_spanning_period_does_not_collide_with_the_composite_sentinel(self):
        assert _period_sort_key("hist_emp_growth_1999_2000") != _period_sort_key("emp_growth_composite")

    def test_periods_sort_chronologically_across_the_century(self):
        columns = [
            "emp_growth_composite",
            "emp_growth_2022_2023",
            "hist_emp_growth_1999_2000",
            "hist_emp_growth_1983_1984",
        ]
        assert sorted(columns, key=_period_sort_key) == [
            "hist_emp_growth_1983_1984",
            "hist_emp_growth_1999_2000",
            "emp_growth_2022_2023",
            "emp_growth_composite",
        ]

    def test_span_carrying_pre_ai_key_does_not_raise_and_sorts_with_composite(self):
        """A span-carrying pre_ai key (e.g. 'pre_ai_2005_2022') must not raise on int('pre', ...)."""
        assert _period_sort_key("hist_emp_growth_pre_ai_2005_2022") == _period_sort_key("emp_growth_composite")


class TestUnemploymentChangeByPeriod:
    """
    unemployment_change_by_period must map a four-digit period key straight onto
    the rate series' own four-digit year index — no century offset. Before the
    fix, "2007_2008" was looked up as 2000 + 2007 = 4007, which is never in the
    index, so the returned Series was silently empty.
    """

    def test_four_digit_period_key_maps_to_the_matching_years(self, monkeypatch):
        fake_rate = pd.Series({2007: 4.6, 2008: 5.8, 2022: 3.6, 2023: 3.9})
        monkeypatch.setattr(historical_displacement, "fetch_annual_means", lambda *args, **kwargs: fake_rate)

        result = unemployment_change_by_period(["2007_2008", "2022_2023"])

        assert not result.empty
        assert result["2007_2008"] == pytest.approx(5.8 - 4.6)
        assert result["2022_2023"] == pytest.approx(3.9 - 3.6)

    def test_returns_empty_when_no_period_falls_on_a_known_year(self, monkeypatch):
        """A guard against the fix regressing: an out-of-range key still yields nothing, not a crash."""
        fake_rate = pd.Series({2007: 4.6, 2008: 5.8})
        monkeypatch.setattr(historical_displacement, "fetch_annual_means", lambda *args, **kwargs: fake_rate)

        result = unemployment_change_by_period(["1950_1951"])

        assert result.empty

    def test_pre_2005_period_produces_the_correct_year_to_year_change(self, monkeypatch):
        """The OEWS series now reaches back to 1999, so the unemployment lookup must too.

        Before this fix the fetch was hardcoded to start in 2005, so a period like
        '1999_2000' had no start-year row to difference against and was silently
        dropped from the cycle decomposition entirely (n stayed at 18 even after
        the 2001 recession entered the historical window). This exercises the real
        period-key split-and-difference logic against a rate Series that actually
        carries 1999-2005, the way the real fetch would once its start year is
        widened, rather than injecting the change value as a fixture.
        """
        fake_rate = pd.Series({1999: 4.2, 2000: 4.0, 2001: 4.7, 2002: 5.8, 2003: 6.0, 2004: 5.5, 2005: 5.1})
        monkeypatch.setattr(historical_displacement, "fetch_annual_means", lambda *args, **kwargs: fake_rate)

        result = unemployment_change_by_period(["1999_2000", "2000_2001", "2004_2005"])

        assert not result.empty
        assert result["1999_2000"] == pytest.approx(4.0 - 4.2)
        assert result["2000_2001"] == pytest.approx(4.7 - 4.0)
        assert result["2004_2005"] == pytest.approx(5.1 - 5.5)

    def test_fetches_from_the_series_own_start_year(self, monkeypatch):
        """The hardcoded 2005 start must be gone: the fetch should request from 1948, LNS14000000's own start."""
        captured_args = {}

        def fake_fetch_annual_means(series_id, start_year, end_year):
            captured_args["start_year"] = start_year
            return pd.Series({1999: 4.2, 2000: 4.0})

        monkeypatch.setattr(historical_displacement, "fetch_annual_means", fake_fetch_annual_means)

        unemployment_change_by_period(["1999_2000"])

        assert captured_args["start_year"] == 1948


class TestCorrelateWithDisplacementRate:
    """
    correlate_with_displacement_rate keys the displacement lookup on the raw
    end-year of the period ("2007_2008" -> 2008), not 2000 + end-year. Before
    the fix every lookup missed and the result was always the empty frame.
    """

    def test_four_digit_periods_produce_a_non_empty_correlation(self, monkeypatch):
        periods = ["2007_2008", "2008_2009", "2009_2010", "2010_2011", "2011_2012"]
        correlation_df = _correlation_frame(list(zip(periods, [0.1, 0.3, 0.2, 0.4, 0.5])))
        fake_displacement_rate = pd.Series({2008: 0.010, 2009: 0.020, 2010: 0.015, 2011: 0.025, 2012: 0.030})
        monkeypatch.setattr(historical_displacement, "productivity_displacement_rate", lambda *args, **kwargs: fake_displacement_rate)

        result_df = correlate_with_displacement_rate(correlation_df)

        assert not result_df.empty
        assert result_df.iloc[0]["n_periods"] == len(periods)


class TestOccupationLevelCorrelation:
    """The occupation-level twin of the sector path, on harmonized SOC units."""

    @staticmethod
    def _membership_frame(n_units: int) -> pd.DataFrame:
        return pd.DataFrame([{"year": "2022", "unit_id": f"u{i}", "oews_code": f"11-{1000 + i}"} for i in range(n_units)])

    @staticmethod
    def _scored_frame(n_units: int) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "OCC_CODE": f"11-{1000 + i}",
                    COMPOSITION_SCORE_COLUMN: i / n_units,
                    "TOT_EMP_2025": 1000.0,
                }
                for i in range(n_units)
            ]
        )

    @staticmethod
    def _unit_growth_frame(n_units: int, growth_col: str, slope: float) -> pd.DataFrame:
        return pd.DataFrame([{"unit_id": f"u{i}", growth_col: slope * i / n_units} for i in range(n_units)])

    def test_perfectly_correlated_units_give_r_of_one(self):
        n_units = 30
        result = occupation_correlation(
            self._scored_frame(n_units),
            COMPOSITION_SCORE_COLUMN,
            "emp_growth_2022_2023",
            "TOT_EMP_2025",
            self._unit_growth_frame(n_units, "emp_growth_2022_2023", 1.0),
            self._membership_frame(n_units),
        )
        assert result is not None
        correlation, _, n_reported = result
        assert correlation == pytest.approx(1.0)
        assert n_reported == n_units

    def test_reported_n_counts_units_not_occupations(self):
        """Two occupations mapping to one unit must report n=1 unit, not n=2."""
        membership_df = pd.DataFrame(
            [
                {"year": "2022", "unit_id": "u0", "oews_code": "11-1000"},
                {"year": "2022", "unit_id": "u0", "oews_code": "11-1001"},
            ]
        )
        scored_df = self._scored_frame(2)
        unit_scores = build_unit_scores(scored_df, membership_df, "TOT_EMP_2025", [COMPOSITION_SCORE_COLUMN])
        assert len(unit_scores) == 1

    def test_too_few_units_returns_none(self):
        n_units = 3
        result = occupation_correlation(
            self._scored_frame(n_units),
            COMPOSITION_SCORE_COLUMN,
            "emp_growth_2022_2023",
            "TOT_EMP_2025",
            self._unit_growth_frame(n_units, "emp_growth_2022_2023", 1.0),
            self._membership_frame(n_units),
        )
        assert result is None

    def test_tied_scores_do_not_crash_and_yield_nan_or_none(self):
        """31% of occupations share one composition score; ties must not raise."""
        n_units = 30
        scored_df = self._scored_frame(n_units)
        scored_df[COMPOSITION_SCORE_COLUMN] = 0.5  # every unit identical
        result = occupation_correlation(
            scored_df,
            COMPOSITION_SCORE_COLUMN,
            "emp_growth_2022_2023",
            "TOT_EMP_2025",
            self._unit_growth_frame(n_units, "emp_growth_2022_2023", 1.0),
            self._membership_frame(n_units),
        )
        assert result is None or pd.isna(result[0])


class TestCpsGroupCorrelation:
    @staticmethod
    def _scored_frame():
        """Two occupations per DWS group, scores rising with the group's index."""
        from composition_displacement_validation import soc_major_to_dws_group

        lookup = soc_major_to_dws_group()
        rows = []
        for index, (soc_major, group) in enumerate(sorted(lookup.items())):
            for suffix in ("1001", "1002"):
                rows.append(
                    {
                        "OCC_CODE": f"{soc_major}-{suffix}",
                        COMPOSITION_SCORE_COLUMN: index / 100.0,
                        "TOT_EMP_2025": 1000.0,
                    }
                )
        return pd.DataFrame(rows)

    @staticmethod
    def _cps_trends(growth_col, slope):
        """Growth rising with the same group order _scored_frame implies.

        Groups are contiguous blocks when the lookup is walked in soc_major order
        (e.g. every "professional and related" code sorts before every "service"
        code), so that walk order — not alphabetical group-name order — is what
        lines up with the per-group mean score _scored_frame produces.
        """
        from composition_displacement_validation import soc_major_to_dws_group

        groups_in_soc_major_order = []
        for _soc_major, group in sorted(soc_major_to_dws_group().items()):
            if group not in groups_in_soc_major_order:
                groups_in_soc_major_order.append(group)
        return pd.DataFrame([{"cps_group": group, growth_col: slope * index} for index, group in enumerate(groups_in_soc_major_order)])

    def test_positive_relationship_is_recovered(self):
        result = cps_group_correlation(
            self._scored_frame(),
            COMPOSITION_SCORE_COLUMN,
            "emp_growth_2022_2023",
            "TOT_EMP_2025",
            self._cps_trends("emp_growth_2022_2023", 0.01),
        )
        assert result is not None
        correlation, _, n_groups = result
        assert correlation > 0.9
        assert n_groups == 10

    def test_missing_growth_column_returns_none(self):
        result = cps_group_correlation(
            self._scored_frame(),
            COMPOSITION_SCORE_COLUMN,
            "emp_growth_1983_1984",
            "TOT_EMP_2025",
            self._cps_trends("emp_growth_2022_2023", 0.01),
        )
        assert result is None

    def test_reported_n_counts_groups_not_occupations(self):
        result = cps_group_correlation(
            self._scored_frame(),
            COMPOSITION_SCORE_COLUMN,
            "emp_growth_2022_2023",
            "TOT_EMP_2025",
            self._cps_trends("emp_growth_2022_2023", 0.01),
        )
        assert result[2] == 10  # not 44 occupations


class TestCpsLevelPlumbing:
    def test_cps_chart_name_is_selected_for_the_cps_level(self, tmp_path):
        """plot_signal_over_time must actually write under CPS_CHART_NAME for level='cps_group'.

        A dict rebuilt inline in the test would pass even if production used a
        wrong key (e.g. "cps"), since the test's own dict would never disagree
        with itself. Calling the real function and checking the file it wrote
        catches that class of bug.
        """
        period_correlation_df = pd.DataFrame(
            [
                {"period": "2020_2021", "score": COMPOSITION_SCORE_COLUMN, "fit_r": 0.30, "fit_p": 0.20, "n_units": 10},
                {"period": "2021_2022", "score": COMPOSITION_SCORE_COLUMN, "fit_r": 0.45, "fit_p": 0.03, "n_units": 10},
            ]
        )
        plot_signal_over_time(period_correlation_df, str(tmp_path), level="cps_group")
        assert (tmp_path / CPS_CHART_NAME).exists()
        assert not (tmp_path / OCCUPATION_CHART_NAME).exists()
        assert not (tmp_path / CHART_NAME).exists()

    def test_cps_correlation_frame_has_the_shared_shape(self):
        scored_df = TestCpsGroupCorrelation._scored_frame()
        cps_trends_df = TestCpsGroupCorrelation._cps_trends("emp_growth_2022_2023", 0.01)
        frame = build_cps_period_correlations(scored_df, "TOT_EMP_2025", cps_trends_df, [COMPOSITION_SCORE_COLUMN])
        assert set(frame.columns) == {"period", "score", "fit_r", "fit_p", "n_units", "era", "is_covid"}
