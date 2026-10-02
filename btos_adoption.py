"""
btos_adoption.py
────────────────
Census Business Trends and Outlook Survey (BTOS) AI-use series and its growth
fits — the adoption driver A_t in the decomposed-slope composition forecast
(docs/superpowers/specs/2026-10-02-decomposed-slope-forecast-design.md).

BTOS asks a panel of firms every two weeks whether they used AI in the last two
weeks (Question ID 7). The question changed wording at the end of 2025:

  production    "…use AI in producing goods or services?"   2023 cycle 19 → 2025 cycle 17
  any_function  "…use AI in any of its business functions?" 2025 cycle 24 → latest

census.gov's live National.xlsx carries only the new wording, so the old-wording
history lives in the committed seed (seeds/btos_ai_use.csv), first built from the
copy Anthropic republished in Anthropic/EconomicIndex
release_2025_09_15/data/input/BTOS_National.xlsx. Every run merges the latest
fetch onto the seed; promotion of new points back to seeds/ is by hand (cp).

The growth fits place the old wording on the new wording's scale with a fitted
multiplicative splice parameter, rather than assuming one.

Inputs:
  • data/raw/btos_national.xlsx — fetched by `python btos_adoption.py`
  • seeds/btos_ai_use.csv       — committed series, both wordings
Outputs:
  • data/output/btos_ai_use.csv
  • data/output/btos_adoption_fits.csv
"""

import os
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd
import requests
from scipy.optimize import curve_fit

BTOS_URL = "https://www.census.gov/hfp/btos/downloads/National.xlsx"
RAW_WORKBOOK_PATH = "data/raw/btos_national.xlsx"
SEED_PATH = "seeds/btos_ai_use.csv"
SERIES_OUTPUT_PATH = "data/output/btos_ai_use.csv"
FITS_OUTPUT_PATH = "data/output/btos_adoption_fits.csv"

AI_USE_QUESTION_ID = "7"
WORDING_PRODUCTION = "production"
WORDING_ANY_FUNCTION = "any_function"
SERIES_COLUMNS = ["smpdt", "ref_end", "wording", "ai_use", "std_error"]


def parse_percent(cell) -> float:
    """'9.7%' → 0.097. BTOS writes '.' for a period a question was not asked; that becomes NaN."""
    text = str(cell).strip()
    if not text.endswith("%"):
        return np.nan
    return round(float(text.rstrip("%")) / 100.0, 6)


def wording_of(question_text: str) -> str:
    """Label which of the two AI-use wordings a question row carries; anything else raises."""
    lowered = question_text.lower()
    if "producing goods or services" in lowered:
        return WORDING_PRODUCTION
    if "any of its business functions" in lowered:
        return WORDING_ANY_FUNCTION
    raise ValueError(f"Unrecognised BTOS AI-use wording: {question_text!r}")


def _integer_code(value) -> str | None:
    """'7', 7, 7.0 and '202517' all normalise to their integer string; footer text becomes None."""
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return None


def _ai_use_yes_row(sheet_df: pd.DataFrame) -> pd.Series:
    is_ai_use = sheet_df["Question ID"].map(_integer_code) == AI_USE_QUESTION_ID
    is_yes = sheet_df["Answer"].astype(str).str.strip() == "Yes"
    matching_rows = sheet_df[is_ai_use & is_yes]
    if len(matching_rows) != 1:
        raise ValueError(f"Expected exactly one BTOS AI-use 'Yes' row, found {len(matching_rows)}")
    return matching_rows.iloc[0]


def parse_btos_workbook(workbook_path) -> pd.DataFrame:
    """Read the AI-use 'Yes' share, its standard error, and each period's reference end date."""
    estimates_df = pd.read_excel(workbook_path, sheet_name="Response Estimates", dtype=str)
    errors_df = pd.read_excel(workbook_path, sheet_name="Response Standard Errors", dtype=str)
    dates_df = pd.read_excel(workbook_path, sheet_name="Collection and Reference Dates")

    estimate_row = _ai_use_yes_row(estimates_df)
    error_row = _ai_use_yes_row(errors_df)
    wording = wording_of(estimate_row["Question"])

    dates_df = dates_df.assign(smpdt=dates_df["Smpdt"].map(_integer_code)).dropna(subset=["smpdt"])
    ref_end_by_smpdt = dict(zip(dates_df["smpdt"], pd.to_datetime(dates_df["Ref End"], format="mixed")))

    smpdt_columns = [column for column in estimates_df.columns if (code := _integer_code(column)) and len(code) == 6]
    series_rows = [
        {
            "smpdt": _integer_code(column),
            "ref_end": ref_end_by_smpdt.get(_integer_code(column), pd.NaT),
            "wording": wording,
            "ai_use": parse_percent(estimate_row[column]),
            "std_error": parse_percent(error_row.get(column, np.nan)),
        }
        for column in smpdt_columns
    ]
    series_df = pd.DataFrame(series_rows, columns=SERIES_COLUMNS).dropna(subset=["ai_use"])

    undated = series_df.loc[series_df["ref_end"].isna(), "smpdt"].tolist()
    if undated:
        raise ValueError(f"BTOS sample period(s) {undated} have an estimate but no reference date")
    return series_df.sort_values("ref_end").reset_index(drop=True)


def merge_with_seed(seed_df: pd.DataFrame, fetched_df: pd.DataFrame) -> pd.DataFrame:
    """Union the seed and a fresh fetch; a fetched row replaces the seed's row for the same period and wording."""
    combined_df = pd.concat([seed_df, fetched_df], ignore_index=True)
    combined_df["ref_end"] = pd.to_datetime(combined_df["ref_end"])
    combined_df["smpdt"] = combined_df["smpdt"].astype(str)
    combined_df = combined_df.drop_duplicates(subset=["smpdt", "wording"], keep="last")
    return combined_df.sort_values(["ref_end", "wording"]).reset_index(drop=True)[SERIES_COLUMNS]


def load_series() -> pd.DataFrame:
    """The committed seed merged with the latest fetched workbook, if one was downloaded."""
    seed_df = pd.read_csv(SEED_PATH, dtype={"smpdt": str}, parse_dates=["ref_end"])
    if not os.path.exists(RAW_WORKBOOK_PATH):
        print(f"  ⚠ {RAW_WORKBOOK_PATH} not found; using the committed BTOS seed alone.")
        return merge_with_seed(seed_df, seed_df.iloc[0:0])
    return merge_with_seed(seed_df, parse_btos_workbook(RAW_WORKBOOK_PATH))


def write_seed(workbook_paths: list[str]) -> pd.DataFrame:
    """Build seeds/btos_ai_use.csv from one or more workbooks (one-off, local; see docs/seeds.md)."""
    seed_df = pd.DataFrame(columns=SERIES_COLUMNS)
    for workbook_path in workbook_paths:
        seed_df = merge_with_seed(seed_df, parse_btos_workbook(workbook_path))
    seed_df.to_csv(SEED_PATH, index=False, date_format="%Y-%m-%d")
    return seed_df


def download_workbook() -> None:
    """Fetch census.gov's National.xlsx, failing soft under CI like the BLS fetchers."""
    os.makedirs(os.path.dirname(RAW_WORKBOOK_PATH), exist_ok=True)
    print("Downloading Census BTOS national estimates...")
    try:
        response = requests.get(BTOS_URL, timeout=60)
        response.raise_for_status()
    except requests.RequestException as request_error:
        message = f"Could not fetch BTOS: {request_error}"
        if os.environ.get("CI"):
            print(f"  ⚠ {message} Continuing from the committed seed.")
            return
        print(f"  ✗ {message}")
        sys.exit(1)
    with open(RAW_WORKBOOK_PATH, "wb") as workbook_file:
        workbook_file.write(response.content)
    print(f"  ✓ {RAW_WORKBOOK_PATH}")


# ── Growth fits ────────────────────────────────────────────────────────────────

ADOPTION_EPOCH = pd.Timestamp("2022-01-01")
FORECAST_HORIZON_END = pd.Timestamp("2030-12-01")


def decimal_years(dates) -> np.ndarray:
    """Years since 2022-01-01 — the growth forms' time axis."""
    return ((pd.to_datetime(pd.Series(dates)) - ADOPTION_EPOCH).dt.days / 365.25).to_numpy(float)


def linear_form(years, intercept, slope):
    return intercept + slope * years


def logistic_form(years, ceiling, rate, midpoint):
    return ceiling / (1.0 + np.exp(-rate * (years - midpoint)))


def gompertz_form(years, ceiling, displacement, rate):
    return ceiling * np.exp(-displacement * np.exp(-rate * years))


def exponential_form(years, scale, rate):
    return scale * np.exp(rate * years)


# name → (form, initial guess, (lower bounds, upper bounds)). Every bound keeps the
# form non-decreasing (slope, rate ≥ 0) and every ceiling ≤ 1.
GROWTH_FORMS = {
    "linear": (linear_form, [0.0, 0.05], ([-1.0, 0.0], [1.0, 1.0])),
    "logistic": (logistic_form, [0.6, 0.6, 7.0], ([0.0, 0.0, -10.0], [1.0, 5.0, 40.0])),
    "gompertz": (gompertz_form, [0.6, 3.0, 0.2], ([0.0, 0.0, 0.0], [1.0, 50.0, 5.0])),
    "exponential": (exponential_form, [0.05, 0.3], ([0.0, 0.0], [1.0, 5.0])),
}
# The old wording ("producing goods or services") is narrower, so its multiplier onto
# the new wording's scale is expected below 1.
SPLICE_INITIAL = 0.6
SPLICE_BOUNDS = (0.1, 2.0)


@dataclass
class AdoptionFit:
    name: str
    parameters: tuple[float, ...]
    splice_multiplier: float
    accepted: bool
    rejection_reason: str = ""


def fit_adoption(series_df: pd.DataFrame) -> dict[str, AdoptionFit]:
    """Fit every growth form to both wordings at once, with the splice multiplier as a free parameter."""
    years = decimal_years(series_df["ref_end"])
    is_production_wording = (series_df["wording"] == WORDING_PRODUCTION).to_numpy(float)
    observed_adoption = series_df["ai_use"].to_numpy(float)
    horizon_years = decimal_years([FORECAST_HORIZON_END])[0]

    adoption_fits = {}
    for name, (form, initial, (lower, upper)) in GROWTH_FORMS.items():

        def spliced_form(stacked, *parameters, form=form):
            fit_years, production_flag = stacked
            multiplier = np.where(production_flag == 1.0, parameters[-1], 1.0)
            return form(fit_years, *parameters[:-1]) * multiplier

        try:
            fitted_parameters, _ = curve_fit(
                spliced_form,
                np.vstack([years, is_production_wording]),
                observed_adoption,
                p0=[*initial, SPLICE_INITIAL],
                bounds=([*lower, SPLICE_BOUNDS[0]], [*upper, SPLICE_BOUNDS[1]]),
                maxfev=20000,
            )
        except (RuntimeError, ValueError) as fit_error:
            adoption_fits[name] = AdoptionFit(name, (), np.nan, False, f"did not converge: {fit_error}")
            continue

        adoption_fit = AdoptionFit(name, tuple(float(p) for p in fitted_parameters[:-1]), float(fitted_parameters[-1]), True)
        horizon_adoption = float(form(horizon_years, *adoption_fit.parameters))
        if name == "exponential" and horizon_adoption > 1.0:
            adoption_fit.accepted = False
            adoption_fit.rejection_reason = f"exceeds 100% adoption by {FORECAST_HORIZON_END:%Y-%m} ({horizon_adoption:.2f})"
        adoption_fits[name] = adoption_fit
    return adoption_fits


def accepted_fits(adoption_fits: dict[str, AdoptionFit]) -> dict[str, AdoptionFit]:
    return {name: adoption_fit for name, adoption_fit in adoption_fits.items() if adoption_fit.accepted}


def evaluate_fit(adoption_fit: AdoptionFit, dates) -> np.ndarray:
    """Fitted adoption on the new-wording scale, clipped to [0, 1]."""
    form = GROWTH_FORMS[adoption_fit.name][0]
    return np.clip(form(decimal_years(dates), *adoption_fit.parameters), 0.0, 1.0)


def annual_mean_adoption(adoption_fit: AdoptionFit, years: list[int]) -> pd.Series:
    """Mean of the twelve mid-month fitted values in each calendar year."""
    annual_means = {}
    for year in years:
        mid_months = pd.date_range(f"{year}-01-15", periods=12, freq=pd.DateOffset(months=1))
        annual_means[year] = float(evaluate_fit(adoption_fit, mid_months).mean())
    return pd.Series(annual_means, name=f"adoption_{adoption_fit.name}")


def fits_table(adoption_fits: dict[str, AdoptionFit]) -> pd.DataFrame:
    """Parameters plus monthly fitted adoption 2022-01 → 2030-12 per fit; a rejected fit gets one row, month blank."""
    months = pd.Series(pd.date_range(ADOPTION_EPOCH, FORECAST_HORIZON_END, freq="MS"))
    table_frames = []
    for adoption_fit in adoption_fits.values():
        base = {
            "fit": adoption_fit.name,
            "accepted": adoption_fit.accepted,
            "rejection_reason": adoption_fit.rejection_reason,
            "parameters": ";".join(f"{value:.6g}" for value in adoption_fit.parameters),
            "splice_multiplier": adoption_fit.splice_multiplier,
        }
        if adoption_fit.accepted:
            table_frames.append(pd.DataFrame({**base, "month": months, "adoption": evaluate_fit(adoption_fit, months)}))
        else:
            table_frames.append(pd.DataFrame([{**base, "month": pd.NaT, "adoption": np.nan}]))
    return pd.concat(table_frames, ignore_index=True)


def run_adoption() -> tuple[pd.DataFrame, dict[str, AdoptionFit]]:
    """Load the merged series, fit every form, and write both outputs."""
    series_df = load_series()
    series_df.to_csv(SERIES_OUTPUT_PATH, index=False, date_format="%Y-%m-%d")
    adoption_fits = fit_adoption(series_df)
    fits_table(adoption_fits).to_csv(FITS_OUTPUT_PATH, index=False, date_format="%Y-%m-%d")
    for adoption_fit in adoption_fits.values():
        status = "accepted" if adoption_fit.accepted else f"rejected — {adoption_fit.rejection_reason}"
        print(f"  {adoption_fit.name:<12} splice ×{adoption_fit.splice_multiplier:.3f}  {status}")
    return series_df, adoption_fits


if __name__ == "__main__":
    download_workbook()
