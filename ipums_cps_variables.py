"""
ipums_cps_variables.py
──────────────────────
Every IPUMS CPS variable name, code value and sample-ID pattern that Phase 2 of
the deep history extension depends on, in one module — because several of them
can only be confirmed against IPUMS itself.

Each value starts as the expected value from IPUMS documentation. Plan Task 2
(`verify_ipums_cps.py`) confirms or corrects every one against a probe extract,
records the evidence in docs/superpowers/plans/2026-09-23-ipums-verification.md,
and only then sets VERIFICATION_STATUS to "verified". The panel builds refuse to
read real data until it is.

Inputs: none. Outputs: none — constants only.
"""

VERIFICATION_STATUS = "unverified"

COLLECTION = "cps"
# Offline/formatting fallback only — confirmed live 2026-09-23 (Task 2, Step 4) that IPUMS does
# not use a fixed 'b' suffix for every month (of 523 basic-monthly month-samples 1983-2025, the
# suffix varies with no year/month rule; only March always has both, since '03s' there is the
# unrelated ASEC supplement). `download_ipums_cps.basic_monthly_sample_id` resolves the real
# suffix from `available_sample_ids` when given it; this pattern is what it falls back to
# without that live sample list.
BASIC_MONTHLY_SAMPLE_PATTERN = "cps{year}_{month:02d}b"
BASIC_MONTHLY_FIRST_YEAR = 1983

BASIC_MONTHLY_VARIABLES = [
    "YEAR",
    "MONTH",
    "SERIAL",
    "CPSID",
    "PERNUM",
    "MISH",
    "WTFINL",
    "COMPWT",
    "AGE",
    "EMPSTAT",
    "OCC",
    "OCC1990",
    "CLASSWKR",
]

# EMPSTAT 10 = at work, 12 = has job, not at work last week. Armed forces (01) excluded.
EMPLOYED_EMPSTAT_CODES = (10, 12)
MINIMUM_AGE = 16

# Wage and salary classes only: both self-employed classes (13, 14), unpaid family
# workers (29) and armed forces (26) are excluded.
WAGE_SALARY_CLASSWKR_CODES = (20, 21, 22, 23, 24, 25, 27, 28)

OCC1990_NOT_IN_UNIVERSE = 999

# BLS's published CPS estimates use composite weights from this year on.
COMPOSITE_WEIGHT_FIRST_YEAR = 1998

# "CPSID" if households link across months in every year 1983-2026, otherwise
# "household_month" (SERIAL within YEAR and MONTH) for the whole span — the
# bootstrap design must be identical in every year (spec § Sampling variance).
HOUSEHOLD_CLUSTER = "CPSID"

# ── Displaced Worker Supplement (Tasks 14-16). Confirmed in Task 2 Step 6. ──
DWS_SURVEY_YEARS: tuple[int, ...] = tuple(range(1984, 2027, 2))
# The supplement rides inside that year's January basic-monthly sample, which carries the same
# unpredictable 'b'/'s' suffix as BASIC_MONTHLY_SAMPLE_PATTERN above; DWS_SAMPLE_MONTH plus
# `download_ipums_cps.dws_sample_id`'s live resolution is what actually picks the right one.
# DWS_SAMPLE_PATTERN is the offline/formatting fallback, and it guesses 'b'.
DWS_SAMPLE_MONTH = 1
DWS_SAMPLE_PATTERN = "cps{year}_01b"
DWS_WEIGHT_VARIABLE = "DWSUPPWT"
DWS_REASON_VARIABLE = "DWREAS"
DWS_TENURE_VARIABLE = "DWYEARS"
# Raw, vintage-coded occupation of the lost job. Required: gate G3 reads it.
DWS_LOST_JOB_OCC_VARIABLE = "DWOCC"
# Harmonized 1990-basis occupation of the lost job, or None if IPUMS has none. Confirmed present
# (named DWOCC1990) against the live IPUMS CPS variable browser 2026-09-23 — see the DWS
# Displaced Worker Supplement group at https://cps.ipums.org/cps-action/variables/group?id=dw_dw.
# Its presence in the extract itself (which years carry it, whether it is ever missing) is still
# unconfirmed: the dws-probe extract needed for that is blocked (Task 2 Step 6; see the
# verification record).
DWS_LOST_JOB_OCC1990_VARIABLE: str | None = "DWOCC1990"
# Task 2 fills these from the DWREAS codebook: the codes whose labels name a
# plant or company closing or move, insufficient work, or an abolished position
# or shift — BLS's three displacement reasons.
DWS_DISPLACED_REASON_LABEL_FRAGMENTS = ("closed", "insufficient work", "abolished")
DWS_DISPLACED_REASON_CODES: tuple[int, ...] = ()
# Tenure values above this are IPUMS not-in-universe / missing codes.
DWS_TENURE_VALID_MAXIMUM = 60.0
DWS_MINIMUM_AGE = 20

DWS_VARIABLES = [
    "YEAR",
    "MONTH",
    "SERIAL",
    "CPSID",
    "PERNUM",
    "AGE",
    DWS_WEIGHT_VARIABLE,
    DWS_REASON_VARIABLE,
    DWS_TENURE_VARIABLE,
    DWS_LOST_JOB_OCC_VARIABLE,
] + ([DWS_LOST_JOB_OCC1990_VARIABLE] if DWS_LOST_JOB_OCC1990_VARIABLE else [])
