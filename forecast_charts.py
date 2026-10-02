"""
forecast_charts.py
──────────────────
The seven charts of the decomposed-slope composition forecast
(docs/superpowers/specs/2026-10-02-decomposed-slope-forecast-design.md § Component 5).

The first six show the raw start only; the seventh compares the raw and the
seasonally adjusted CPS starts. Every chart is saved through
chart_manifest.save_figure. The sector-change and occupation views are labelled as
conditional projections; occupation numbers are an allocation of sector change,
never an occupation-level forecast.

Inputs:  frames produced by forecast_composition.py and btos_adoption.py
Outputs: data/output/visualizations/forecast_*.png
"""

import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from chart_manifest import save_figure
from plot_constants import SOC_MAJOR_GROUPS

CHART_NAMES = (
    "forecast_slope_history.png",
    "forecast_btos_adoption.png",
    "forecast_sector_change_2030.png",
    "forecast_sector_paths.png",
    "forecast_demand_type_shares.png",
    "forecast_scenario_comparison.png",
    "forecast_cps_start_basis.png",
)
INSTRUMENT_LABELS = {"oews": "OEWS (start May 2025)", "cps": "CPS A-19 (start latest month)"}
# The slope history is each instrument's own estimation history; for CPS that is the 22-sector rollup, not A-19.
HISTORY_LABELS = {"oews": "OEWS sector totals, 1999–2025", "cps": "CPS 22-sector rollup, 1983–2025"}
# Reference categorical slots 1, 2, 3, 7 — validated together: CVD ΔE ≥ 9.2, normal-vision ΔE ≥ 27.6.
FIT_COLORS = {"linear": "#2a78d6", "logistic": "#eb6834", "gompertz": "#1baf7a", "exponential": "#4a3aa7"}
GAIN_COLOR, LOSS_COLOR = "#2a78d6", "#e34948"  # blue/red, not red/green: sign stays legible under deuteranopia
SCENARIO_LABELS = {"steady": "Steady unemployment", "mild_recession": "Mild recession (+1.5 pp in 2027)"}
REFERENCE_SCENARIO = ("steady", "logistic")
START_BASIS_LABELS = {"raw": "Raw latest month", "seasonally_adjusted": "Seasonally adjusted latest month"}
START_BASIS_COLORS = {"raw": "#2a78d6", "seasonally_adjusted": "#eb6834"}  # categorical slots 1 and 2
PROJECTION_NOTE = "Conditional projection: dynamic-model score unchanged, total employment held at start level."


def _instruments_present(instrument_frame: pd.DataFrame) -> list[str]:
    """OEWS then CPS, keeping only those in the frame — CPS is withheld when gate G4 fails."""
    return [instrument for instrument in ("oews", "cps") if instrument in set(instrument_frame["instrument"])]


def _sector_label(soc_major: str) -> str:
    return SOC_MAJOR_GROUPS.get(str(soc_major).zfill(2), str(soc_major))


def _start_and_end(instrument_df: pd.DataFrame) -> tuple[str, str]:
    labels = sorted(instrument_df["as_of"].unique())
    return labels[0], labels[-1]


def _final_change(sector_paths_df: pd.DataFrame, instrument: str, scenario: str, fit: str) -> pd.DataFrame:
    """Start → final share change (percentage points) with band and noise edges, per sector."""
    scenario_df = sector_paths_df[
        (sector_paths_df["instrument"] == instrument)
        & (sector_paths_df["unemployment_scenario"] == scenario)
        & (sector_paths_df["adoption_fit"] == fit)
    ]
    start_label, end_label = _start_and_end(scenario_df)
    start = scenario_df[scenario_df["as_of"] == start_label].set_index("soc_major")
    end = scenario_df[scenario_df["as_of"] == end_label].set_index("soc_major")
    change = pd.DataFrame({"change": end["share"] - start["share"]})
    for column in ("share_p5", "share_p95", "noise_low", "noise_high"):
        if column in end:
            change[column] = end[column] - start["share"]
    return change * 100


def plot_slope_history(period_slopes_df, decomposition_df, output_dir):
    instruments = _instruments_present(period_slopes_df)
    figure, axes = plt.subplots(1, len(instruments), figsize=(7 * len(instruments), 5), sharey=True, squeeze=False)
    axes = axes[0]
    for axis, instrument in zip(axes, instruments):
        instrument_df = period_slopes_df[period_slopes_df["instrument"] == instrument].sort_values("end_year")
        included = ~instrument_df["is_covid"].astype(bool) & (instrument_df["excluded_reason"].fillna("") == "")
        axis.errorbar(
            instrument_df.loc[included, "end_year"],
            instrument_df.loc[included, "slope"],
            yerr=1.96 * instrument_df.loc[included, "std_error"],
            fmt="o",
            color="#333333",
            label="β_t (95% CI)",
        )
        axis.scatter(
            instrument_df.loc[~included, "end_year"],
            instrument_df.loc[~included, "slope"],
            marker="x",
            color="#999999",
            label="COVID or excluded period",
        )
        coefficients = decomposition_df[
            (decomposition_df["instrument"] == instrument) & (decomposition_df["specification"] == "main")
        ].set_index("term")["coefficient"]
        fitted = (
            coefficients.get("structural", 0)
            + coefficients.get("cycle", 0) * instrument_df["unemployment_change"]
            + coefficients.get("ai", 0) * instrument_df["adoption"]
        )
        axis.plot(instrument_df["end_year"], fitted, color="#dd8452", label="Fitted β_structural + β_cycle·ΔU + β_AI·A")
        axis.axhline(0, color="#cccccc", linewidth=0.8)
        axis.set_title(HISTORY_LABELS[instrument])
        axis.set_xlabel("Period end year")
    axes[0].set_ylabel("Slope of relative share growth on sector score")
    axes[0].legend(fontsize=8, loc="upper left")
    figure.suptitle("How strongly the dynamic-model score sorted sector shares, by year")
    figure.tight_layout()
    save_figure(figure, os.path.join(output_dir, CHART_NAMES[0]), dpi=150)
    plt.close(figure)


def plot_btos_adoption(btos_series_df, adoption_fits_df, output_dir):
    figure, axis = plt.subplots(figsize=(10, 5.5))
    accepted_df = adoption_fits_df[adoption_fits_df["accepted"].astype(bool)]
    for fit_name, fit_df in accepted_df.groupby("fit"):
        axis.plot(
            pd.to_datetime(fit_df["month"]), fit_df["adoption"] * 100, color=FIT_COLORS.get(fit_name, "#555555"), label=f"{fit_name} fit"
        )
    production_df = btos_series_df[btos_series_df["wording"] == "production"]
    function_df = btos_series_df[btos_series_df["wording"] == "any_function"]
    axis.scatter(
        pd.to_datetime(production_df["ref_end"]),
        production_df["ai_use"] * 100,
        marker="o",
        s=10,
        color="#bbbbbb",
        label="Observed, raw: 'producing goods or services'",
    )
    logistic_rows = accepted_df[accepted_df["fit"] == "logistic"]
    if not logistic_rows.empty:
        # The fit models old = splice × new, so old ÷ splice places the old points on the new wording's scale.
        logistic_splice = float(logistic_rows["splice_multiplier"].iloc[0])
        axis.scatter(
            pd.to_datetime(production_df["ref_end"]),
            production_df["ai_use"] / logistic_splice * 100,
            marker="o",
            s=14,
            color="#333333",
            alpha=0.7,
            label=f"Same, spliced onto new wording (÷{logistic_splice:.2f}, logistic)",
        )
    axis.scatter(
        pd.to_datetime(function_df["ref_end"]),
        function_df["ai_use"] * 100,
        marker="s",
        s=14,
        color="#333333",
        alpha=0.7,
        label="Observed: 'any business function'",
    )
    if not accepted_df.empty:
        splice = accepted_df.groupby("fit")["splice_multiplier"].first()
        axis.text(
            0.01,
            0.97,
            "Splice (old → new wording): " + ", ".join(f"{name} ×{value:.2f}" for name, value in splice.items()),
            transform=axis.transAxes,
            fontsize=8,
            va="top",
        )
    axis.set_ylabel("Firms using AI (%), new-wording scale")
    axis.set_title("Census BTOS AI adoption and growth fits to 2030")
    axis.legend(fontsize=8, loc="lower right")
    figure.tight_layout()
    save_figure(figure, os.path.join(output_dir, CHART_NAMES[1]), dpi=150)
    plt.close(figure)


def plot_sector_change_2030(sector_paths_df, output_dir):
    scenario, fit = REFERENCE_SCENARIO
    instruments = _instruments_present(sector_paths_df)
    figure, axes = plt.subplots(1, len(instruments), figsize=(7 * len(instruments), 9), sharey=True, squeeze=False)
    axes = axes[0]
    order = _final_change(sector_paths_df, "oews", scenario, fit)["change"].sort_values().index
    positions = np.arange(len(order))
    for axis, instrument in zip(axes, instruments):
        change = _final_change(sector_paths_df, instrument, scenario, fit).reindex(order)
        axis.hlines(positions, change["noise_low"], change["noise_high"], color="#dddddd", linewidth=6, label="Sector-noise 90% interval")
        axis.hlines(
            positions, change["share_p5"], change["share_p95"], color="#8fa8c8", linewidth=3, label="Parameter 90% band (bootstrap)"
        )
        axis.scatter(
            change["change"], positions, color=np.where(change["change"] >= 0, GAIN_COLOR, LOSS_COLOR), zorder=3, label="Projected change"
        )
        axis.axvline(0, color="#999999", linewidth=0.8)
        axis.set_title(INSTRUMENT_LABELS[instrument])
        axis.set_xlabel("Change in employment share by 2030 (percentage points)")
    axes[0].set_yticks(positions, [_sector_label(code) for code in order])
    axes[0].legend(fontsize=8, loc="lower right")
    figure.suptitle(f"Projected sector share change to 2030 — steady unemployment, logistic adoption\n{PROJECTION_NOTE}", fontsize=11)
    figure.tight_layout()
    save_figure(figure, os.path.join(output_dir, CHART_NAMES[2]), dpi=150)
    plt.close(figure)


def plot_sector_paths(sector_paths_df, output_dir):
    oews_df = sector_paths_df[sector_paths_df["instrument"] == "oews"]
    reference_change = _final_change(sector_paths_df, "oews", *REFERENCE_SCENARIO)["change"]
    movers = reference_change.abs().sort_values(ascending=False).index[:8]
    figure, axes = plt.subplots(len(movers), 2, figsize=(12, 2.0 * len(movers)), sharex=True)
    axes = np.atleast_2d(axes)
    for row_index, sector in enumerate(movers):
        for column_index, scenario in enumerate(SCENARIO_LABELS):
            axis = axes[row_index, column_index]
            for fit_name, fit_df in oews_df[(oews_df["soc_major"] == sector) & (oews_df["unemployment_scenario"] == scenario)].groupby(
                "adoption_fit"
            ):
                fit_df = fit_df.sort_values("as_of")
                axis.plot(fit_df["as_of"], fit_df["share"] * 100, color=FIT_COLORS.get(fit_name, "#555555"), label=fit_name)
            if row_index == 0:
                axis.set_title(SCENARIO_LABELS[scenario])
            if column_index == 0:
                axis.set_ylabel(_sector_label(sector), fontsize=8, rotation=0, ha="right")
    axes[0, 1].legend(fontsize=7, loc="upper right")
    figure.suptitle(f"Employment share paths (%), eight largest-moving sectors, OEWS start\n{PROJECTION_NOTE}", fontsize=10)
    figure.tight_layout()
    save_figure(figure, os.path.join(output_dir, CHART_NAMES[3]), dpi=150)
    plt.close(figure)


def plot_demand_type_shares(demand_shares_df, output_dir):
    figure, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    for axis, demand_type in zip(axes, ("Bounded", "Unbounded", "Adversarial")):
        type_df = demand_shares_df[demand_shares_df["dominant_demand"] == demand_type]
        for (scenario, fit_name), path_df in type_df.groupby(["unemployment_scenario", "adoption_fit"]):
            path_df = path_df.sort_values("as_of")
            axis.plot(
                path_df["as_of"],
                path_df["share"] * 100,
                color=FIT_COLORS.get(fit_name, "#555555"),
                linestyle="-" if scenario == "steady" else "--",
                label=f"{fit_name}, {scenario.replace('_', ' ')}",
            )
        axis.set_title(demand_type)
        axis.set_ylabel("Share of scored employment (%)")
        axis.tick_params(axis="x", rotation=45)
    axes[0].legend(fontsize=7)
    figure.suptitle("Employment share by dominant demand type (sector change allocated to occupations), OEWS start", fontsize=11)
    figure.tight_layout()
    save_figure(figure, os.path.join(output_dir, CHART_NAMES[4]), dpi=150)
    plt.close(figure)


def plot_scenario_comparison(sector_paths_df, output_dir):
    reference_change = _final_change(sector_paths_df, "oews", *REFERENCE_SCENARIO)["change"]
    movers = list(reference_change.abs().sort_values(ascending=False).index[:6])
    combinations = (
        sector_paths_df[sector_paths_df["instrument"] == "oews"][["unemployment_scenario", "adoption_fit"]]
        .drop_duplicates()
        .sort_values(["unemployment_scenario", "adoption_fit"])
    )
    figure, axis = plt.subplots(figsize=(12, 6))
    bar_width = 0.8 / len(combinations)
    for combination_index, combination in enumerate(combinations.itertuples(index=False)):
        change = _final_change(sector_paths_df, "oews", combination.unemployment_scenario, combination.adoption_fit)["change"].reindex(
            movers
        )
        axis.bar(
            np.arange(len(movers)) + combination_index * bar_width,
            change,
            width=bar_width,
            color=FIT_COLORS.get(combination.adoption_fit, "#555555"),
            hatch="" if combination.unemployment_scenario == "steady" else "//",
            edgecolor="white",
            label=f"{combination.adoption_fit}, {SCENARIO_LABELS[combination.unemployment_scenario]}",
        )
    axis.set_xticks(
        np.arange(len(movers)) + 0.4 - bar_width / 2, [_sector_label(code) for code in movers], rotation=20, ha="right", fontsize=8
    )
    axis.axhline(0, color="#999999", linewidth=0.8)
    axis.set_ylabel("Change in employment share by 2030 (pp)")
    axis.set_title(f"2030 share change under each scenario, six largest-moving sectors (OEWS start)\n{PROJECTION_NOTE}", fontsize=10)
    axis.legend(fontsize=7)
    figure.tight_layout()
    save_figure(figure, os.path.join(output_dir, CHART_NAMES[5]), dpi=150)
    plt.close(figure)


def plot_cps_start_basis(sector_paths_df, seasonal_factors_df, output_dir):
    """Per sector, the 2030 change from the raw and from the seasonally adjusted CPS start."""
    scenario, fit = REFERENCE_SCENARIO
    cps_df = sector_paths_df[sector_paths_df["instrument"] == "cps"]
    changes = {basis: _final_change(cps_df[cps_df["start_basis"] == basis], "cps", scenario, fit)["change"] for basis in START_BASIS_LABELS}
    order = changes["raw"].sort_values().index
    positions = np.arange(len(order))
    start_label, end_label = _start_and_end(cps_df)
    month_factors_df = seasonal_factors_df[seasonal_factors_df["calendar_month"] == int(start_label[5:7])]
    month_factors = month_factors_df.set_index(month_factors_df["soc_major"].astype(str).str.zfill(2))["factor"]

    final_shares = {
        basis: cps_df[
            (cps_df["start_basis"] == basis)
            & (cps_df["unemployment_scenario"] == scenario)
            & (cps_df["adoption_fit"] == fit)
            & (cps_df["as_of"] == end_label)
        ].set_index("soc_major")["share"]
        for basis in START_BASIS_LABELS
    }
    share_gap = ((final_shares["seasonally_adjusted"] - final_shares["raw"]) * 100).reindex(order)

    figure, (axis, gap_axis) = plt.subplots(1, 2, figsize=(15, 9), sharey=True, gridspec_kw={"width_ratios": [1.2, 1]})
    for basis, offset in (("raw", -0.18), ("seasonally_adjusted", 0.18)):
        axis.barh(
            positions + offset,
            changes[basis].reindex(order),
            height=0.34,
            color=START_BASIS_COLORS[basis],
            label=START_BASIS_LABELS[basis],
        )
    axis.set_yticks(positions, [f"{_sector_label(code)}  (factor {month_factors.get(code, np.nan):.3f})" for code in order])
    axis.axvline(0, color="#999999", linewidth=0.8)
    axis.set_xlabel(f"Change {start_label} to {end_label} (pp)")
    axis.legend(fontsize=8, loc="lower right")
    axis.set_title("Change to 2030 from each start", fontsize=10)
    gap_axis.barh(positions, share_gap, height=0.6, color=np.where(share_gap >= 0, GAIN_COLOR, LOSS_COLOR))
    gap_axis.axvline(0, color="#999999", linewidth=0.8)
    gap_axis.set_xlabel(f"{end_label} share, adjusted minus raw (pp)")
    gap_axis.set_title("2030 share: adjusted − raw", fontsize=10)
    start_month_name = pd.Period(start_label, freq="M").strftime("%B")
    figure.suptitle(
        f"CPS projection: raw vs seasonally adjusted {start_label} start. Steady unemployment, logistic adoption.\n"
        f"Factor = the sector's {start_month_name} seasonal factor; above 1 means {start_month_name} runs seasonally high.\n"
        f"{PROJECTION_NOTE}",
        fontsize=9,
    )
    figure.tight_layout(rect=(0, 0, 1, 0.94))
    save_figure(figure, os.path.join(output_dir, CHART_NAMES[6]), dpi=150)
    plt.close(figure)


def draw_all(
    period_slopes_df,
    decomposition_df,
    btos_series_df,
    adoption_fits_df,
    sector_paths_df,
    demand_shares_df,
    seasonal_factors_df=None,
    output_dir="data/output/visualizations",
) -> list[str]:
    """Draw every forecast chart; returns the file names written.

    The six original charts show the raw start only. The start-basis comparison is
    drawn only when a seasonally adjusted CPS start exists.
    """
    os.makedirs(output_dir, exist_ok=True)
    raw_paths_df = sector_paths_df[sector_paths_df["start_basis"] == "raw"]
    plot_slope_history(period_slopes_df, decomposition_df, output_dir)
    plot_btos_adoption(btos_series_df, adoption_fits_df, output_dir)
    plot_sector_change_2030(raw_paths_df, output_dir)
    plot_sector_paths(raw_paths_df, output_dir)
    plot_demand_type_shares(demand_shares_df, output_dir)
    plot_scenario_comparison(raw_paths_df, output_dir)
    written = list(CHART_NAMES[:6])
    if seasonal_factors_df is not None and (sector_paths_df["start_basis"] == "seasonally_adjusted").any():
        plot_cps_start_basis(sector_paths_df, seasonal_factors_df, output_dir)
        written.append(CHART_NAMES[6])
    return written
