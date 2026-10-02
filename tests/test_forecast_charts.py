"""
test_forecast_charts.py
───────────────────────
Smoke test for forecast_charts.py: every chart is drawn from small synthetic
frames and saved through chart_manifest, so a renamed column fails here rather
than in a release run.
"""

import numpy as np
import pandas as pd

from forecast_charts import CHART_NAMES, draw_all

SECTORS = ["11", "15", "43", "53"]


def synthetic_inputs():
    periods = pd.DataFrame(
        {
            "instrument": ["oews"] * 4 + ["cps"] * 4,
            "period": ["2019_2020", "2022_2023", "2023_2024", "2024_2025"] * 2,
            "end_year": [2020, 2023, 2024, 2025] * 2,
            "slope": [0.01, 0.03, 0.04, 0.05] * 2,
            "std_error": 0.01,
            "is_covid": [True, False, False, False] * 2,
            "excluded_reason": "",
            "unemployment_change": [3.0, -0.3, 0.2, 0.1] * 2,
            "adoption": [0.0, 0.1, 0.15, 0.2] * 2,
        }
    )
    decomposition = pd.DataFrame(
        {
            "instrument": ["oews"] * 3 + ["cps"] * 3,
            "specification": "main",
            "term": ["structural", "cycle", "ai"] * 2,
            "coefficient": [0.01, 0.005, 0.1] * 2,
            "p_value": [0.01, 0.2, 0.05] * 2,
        }
    )
    btos_series = pd.DataFrame(
        {
            "ref_end": pd.date_range("2023-09-10", periods=6, freq="90D"),
            "wording": ["production"] * 3 + ["any_function"] * 3,
            "ai_use": [0.04, 0.06, 0.08, 0.17, 0.19, 0.22],
        }
    )
    months = pd.date_range("2022-01-01", "2030-12-01", freq="MS")
    fits = pd.concat(
        [
            pd.DataFrame(
                {"fit": name, "accepted": True, "splice_multiplier": 0.55, "month": months, "adoption": np.linspace(0.02, top, len(months))}
            )
            for name, top in (("linear", 0.6), ("logistic", 0.5))
        ]
    )
    path_rows = []
    for instrument, labels, bases in (
        ("oews", ["2025-05", "2030-05"], ("raw",)),
        ("cps", ["2026-09", "2030-12"], ("raw", "seasonally_adjusted")),
    ):
        for start_basis in bases:
            basis_shift = 0.002 if start_basis == "seasonally_adjusted" else 0.0
            for scenario in ("steady", "mild_recession"):
                for fit in ("linear", "logistic"):
                    for label_index, label in enumerate(labels):
                        for sector_index, sector in enumerate(SECTORS):
                            share = 0.25 + (label_index * 0.01 + basis_shift) * (sector_index - 1.5)
                            path_rows.append(
                                {
                                    "instrument": instrument,
                                    "start_basis": start_basis,
                                    "unemployment_scenario": scenario,
                                    "adoption_fit": fit,
                                    "as_of": label,
                                    "soc_major": sector,
                                    "share": share,
                                    "employment": share * 1000,
                                    "share_p5": share - 0.005,
                                    "share_p95": share + 0.005,
                                    "noise_low": share - 0.01,
                                    "noise_high": share + 0.01,
                                }
                            )
    sector_paths = pd.DataFrame(path_rows)
    demand_shares = pd.DataFrame(
        [
            {"unemployment_scenario": s, "adoption_fit": f, "as_of": a, "dominant_demand": d, "share": v}
            for s in ("steady", "mild_recession")
            for f in ("linear", "logistic")
            for a, shift in (("2025-05", 0.0), ("2030-05", 0.01))
            for d, v in (("Bounded", 0.7 - shift), ("Unbounded", 0.2 + shift), ("Adversarial", 0.1))
        ]
    )
    seasonal_factors = pd.DataFrame(
        [
            {"soc_major": sector, "calendar_month": month, "factor": 1.0 + 0.01 * (month - 6.5) / 6, "n_years": 3}
            for sector in SECTORS
            for month in range(1, 13)
        ]
    )
    return periods, decomposition, btos_series, fits, sector_paths, demand_shares, seasonal_factors


def test_draw_all_writes_every_chart(tmp_path):
    written = draw_all(*synthetic_inputs(), output_dir=str(tmp_path))
    assert sorted(written) == sorted(CHART_NAMES)
    for chart_name in CHART_NAMES:
        assert (tmp_path / chart_name).stat().st_size > 0
    assert (tmp_path / "chart_manifest.json").exists()


def test_draw_all_handles_oews_only(tmp_path):
    periods, decomposition, btos_series, fits, sector_paths, demand_shares, seasonal_factors = synthetic_inputs()
    oews_only = [frame[frame["instrument"] == "oews"] for frame in (periods, decomposition, sector_paths)]
    written = draw_all(oews_only[0], oews_only[1], btos_series, fits, oews_only[2], demand_shares, None, output_dir=str(tmp_path))
    assert sorted(written) == sorted(name for name in CHART_NAMES if name != "forecast_cps_start_basis.png")


def test_existing_charts_ignore_the_adjusted_start(tmp_path):
    """Dropping the adjusted rows must not change any of the six original charts."""
    inputs = list(synthetic_inputs())
    with_adjusted = draw_all(*inputs, output_dir=str(tmp_path / "with"))
    inputs[4] = inputs[4][inputs[4]["start_basis"] == "raw"]
    without_adjusted = draw_all(*inputs[:6], None, output_dir=str(tmp_path / "without"))
    for chart_name in without_adjusted:
        assert (tmp_path / "with" / chart_name).read_bytes() == (tmp_path / "without" / chart_name).read_bytes()
    assert "forecast_cps_start_basis.png" in with_adjusted


def test_start_basis_chart_draws_both_panels(tmp_path):
    import matplotlib.pyplot as plt

    from forecast_charts import plot_cps_start_basis

    inputs = synthetic_inputs()
    plot_cps_start_basis(inputs[4], inputs[6], str(tmp_path))
    assert (tmp_path / "forecast_cps_start_basis.png").stat().st_size > 0
    plt.close("all")
