"""
test_composition_displacement_validation.py
───────────────────────────────────────────
Regression tests for composition_displacement_validation.py — the one test in
this project that compares a modeled quantity against a direct measurement of
that same quantity, with no employment growth involved.

Three behaviours are load-bearing:

  • Displacement rates are converted to worker counts before being summed into a
    group. A rate cannot be added across occupations of different size, and doing
    so would weight a 5,000-person occupation like a 2-million-person one.
  • The join between the panel and the SOC mapping is case-normalised. The panel
    keeps the release's own capitalisation while DWS_TO_SOC_MAJOR is keyed
    lowercase, and an un-normalised join silently returns an empty frame rather
    than failing.
  • Shares, not rates, are the headline. The DWS counts people 20+ who lost a
    job; OEWS counts wage and salary jobs. A rate built from one over the other
    has mismatched denominators, so the comparison is made on unit-free shares.
"""

import pandas as pd
import pytest

from composition_displacement_validation import (
    build_displacement_comparison,
    correlate_with_leave_one_out,
    observed_displacement_by_group,
    predicted_displacement_by_group,
    soc_major_to_dws_group,
)
from dws_panel import DWS_TO_SOC_MAJOR


def _panel(survey_year=2026, counts=None):
    """A DWS panel carrying Table 5 occupation rows for one survey."""
    counts = counts or dict.fromkeys(DWS_TO_SOC_MAJOR, 100.0)
    return pd.DataFrame(
        [
            {
                "survey_year": survey_year,
                "period_start_year": survey_year - 3,
                "period_end_year": survey_year - 1,
                "period_years": 3,
                "source_table": "table_5_occupation",
                # Title case, as the release publishes it.
                "group_name": group_name.capitalize(),
                "soc_majors": "|".join(DWS_TO_SOC_MAJOR[group_name]),
                "displaced_thousands": count,
                "reason": "all",
                "tenure_class": "long_tenured",
            }
            for group_name, count in counts.items()
        ]
    )


def _scored_frame():
    """Two occupations per DWS group, with unequal employment and displacement."""
    rows = []
    for group_name, soc_majors in DWS_TO_SOC_MAJOR.items():
        soc_major = soc_majors[0]
        rows.append({"OCC_CODE": f"{soc_major}-1001", "gross_displacement": 0.02, "TOT_EMP_25": 1_000_000.0})
        rows.append({"OCC_CODE": f"{soc_major}-1002", "gross_displacement": 0.01, "TOT_EMP_25": 500_000.0})
    return pd.DataFrame(rows)


class TestSocMajorMapping:
    def test_inverts_to_one_group_per_major(self):
        group_lookup = soc_major_to_dws_group()

        assert len(group_lookup) == 22
        assert group_lookup["43"] == "office and administrative support occupations"
        assert group_lookup["15"] == "professional and related occupations"


class TestObservedDisplacementByGroup:
    def test_normalises_group_name_case_for_the_join(self):
        """The panel keeps the release's capitalisation; the mapping is lowercase."""
        observed_df = observed_displacement_by_group(_panel())

        assert set(observed_df["dws_group"]) == set(DWS_TO_SOC_MAJOR)

    def test_uses_the_most_recent_survey_by_default(self):
        two_survey_panel = pd.concat(
            [_panel(2024, dict.fromkeys(DWS_TO_SOC_MAJOR, 50.0)), _panel(2026, dict.fromkeys(DWS_TO_SOC_MAJOR, 100.0))],
            ignore_index=True,
        )

        observed_df = observed_displacement_by_group(two_survey_panel)

        assert len(observed_df) == len(DWS_TO_SOC_MAJOR)
        assert (observed_df["observed_displaced_thousands"] == 100.0).all()

    def test_named_survey_year_is_honoured(self):
        two_survey_panel = pd.concat(
            [_panel(2024, dict.fromkeys(DWS_TO_SOC_MAJOR, 50.0)), _panel(2026, dict.fromkeys(DWS_TO_SOC_MAJOR, 100.0))],
            ignore_index=True,
        )

        observed_df = observed_displacement_by_group(two_survey_panel, survey_year=2024)

        assert (observed_df["observed_displaced_thousands"] == 50.0).all()

    def test_suppressed_groups_are_dropped_not_zeroed(self):
        counts = dict.fromkeys(DWS_TO_SOC_MAJOR, 100.0)
        counts["farming, fishing, and forestry occupations"] = None

        observed_df = observed_displacement_by_group(_panel(counts=counts))

        assert len(observed_df) == len(DWS_TO_SOC_MAJOR) - 1
        assert "farming, fishing, and forestry occupations" not in set(observed_df["dws_group"])

    def test_returns_empty_when_no_occupation_rows_exist(self):
        reason_only_panel = _panel().assign(source_table="table_2_reason")

        assert observed_displacement_by_group(reason_only_panel).empty


class TestPredictedDisplacementByGroup:
    def test_rates_become_worker_counts_before_summing(self):
        """0.02 × 1,000,000 + 0.01 × 500,000 = 25,000 — not the mean of the two rates."""
        predicted_df = predicted_displacement_by_group(_scored_frame(), "gross_displacement", "TOT_EMP_25").set_index("dws_group")

        assert predicted_df.loc["production occupations", "predicted_displaced_workers"] == pytest.approx(25_000.0)
        assert predicted_df.loc["production occupations", "group_employment"] == pytest.approx(1_500_000.0)

    def test_every_group_is_represented(self):
        predicted_df = predicted_displacement_by_group(_scored_frame(), "gross_displacement", "TOT_EMP_25")

        assert set(predicted_df["dws_group"]) == set(DWS_TO_SOC_MAJOR)

    def test_occupations_outside_the_mapping_are_dropped(self):
        scored_df = pd.concat(
            [_scored_frame(), pd.DataFrame([{"OCC_CODE": "55-1001", "gross_displacement": 9.0, "TOT_EMP_25": 1e9}])],
            ignore_index=True,
        )

        predicted_df = predicted_displacement_by_group(scored_df, "gross_displacement", "TOT_EMP_25")

        assert predicted_df["predicted_displaced_workers"].max() < 1e8


class TestBuildDisplacementComparison:
    def test_shares_sum_to_one_on_both_sides(self, tmp_path, monkeypatch):
        import composition_displacement_validation as module

        composition_path = tmp_path / "composition.csv"
        _scored_frame().to_csv(composition_path, index=False)
        monkeypatch.setattr(module, "COMPOSITION_REPORT_PATH", str(composition_path))
        monkeypatch.setattr(module, "DYNAMIC_REPORT_PATH", str(tmp_path / "absent.csv"))

        comparison_df = build_displacement_comparison(_panel())

        assert comparison_df["observed_share"].sum() == pytest.approx(1.0)
        assert comparison_df["composition_predicted_share"].sum() == pytest.approx(1.0)

    def test_displacement_rate_cancels_out_of_the_shares(self, tmp_path, monkeypatch):
        """D is one scalar over every occupation, so it cannot move a share."""
        import composition_displacement_validation as module

        monkeypatch.setattr(module, "DYNAMIC_REPORT_PATH", str(tmp_path / "absent.csv"))

        shares = []
        for displacement_rate in (0.005, 0.42):
            scaled_df = _scored_frame()
            scaled_df["gross_displacement"] *= displacement_rate / 0.02
            composition_path = tmp_path / f"composition_{displacement_rate}.csv"
            scaled_df.to_csv(composition_path, index=False)
            monkeypatch.setattr(module, "COMPOSITION_REPORT_PATH", str(composition_path))
            shares.append(build_displacement_comparison(_panel()).set_index("dws_group")["composition_predicted_share"])

        pd.testing.assert_series_equal(shares[0], shares[1])

    def test_returns_none_without_a_composition_report(self, tmp_path, monkeypatch):
        import composition_displacement_validation as module

        monkeypatch.setattr(module, "COMPOSITION_REPORT_PATH", str(tmp_path / "absent.csv"))

        assert build_displacement_comparison(_panel()) is None


class TestCorrelateWithLeaveOneOut:
    def _comparison_frame(self, predicted_values):
        group_names = list(DWS_TO_SOC_MAJOR)[: len(predicted_values)]
        observed = [value / sum(predicted_values) for value in predicted_values]
        return pd.DataFrame(
            {
                "dws_group": group_names,
                "observed_share": observed,
                "composition_predicted_share": predicted_values,
            }
        )

    def test_perfect_agreement_gives_r_of_one(self):
        correlations = correlate_with_leave_one_out(
            self._comparison_frame([0.05, 0.10, 0.15, 0.20, 0.25, 0.25]), "composition_predicted_share"
        )

        assert correlations["pearson_r"] == pytest.approx(1.0)
        assert correlations["spearman_r"] == pytest.approx(1.0)
        assert correlations["n_groups"] == 6

    def test_leave_one_out_range_is_reported(self):
        correlations = correlate_with_leave_one_out(
            self._comparison_frame([0.05, 0.10, 0.15, 0.20, 0.25, 0.25]), "composition_predicted_share"
        )

        assert correlations["leave_one_out_min"] <= correlations["pearson_r"] + 1e-9
        assert correlations["leave_one_out_max"] >= correlations["pearson_r"] - 1e-9

    def test_returns_none_when_too_few_groups(self):
        assert correlate_with_leave_one_out(self._comparison_frame([0.5, 0.5]), "composition_predicted_share") is None

    def test_missing_predictions_are_dropped_not_imputed(self):
        comparison_df = self._comparison_frame([0.05, 0.10, 0.15, 0.20, 0.25, 0.25])
        comparison_df.loc[0, "composition_predicted_share"] = None

        correlations = correlate_with_leave_one_out(comparison_df, "composition_predicted_share")

        assert correlations["n_groups"] == 5
