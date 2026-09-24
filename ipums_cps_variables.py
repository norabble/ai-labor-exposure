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

VERIFICATION_STATUS = "verified"

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

# EMPSTAT 10 = at work, 12 = has job, not at work last week. Armed forces (01) excluded. Confirmed
# live 2026-09-24 (Task 2, Step 5, basic-probe): the extract's own EMPSTAT codebook labels exactly
# 10 "At work" and 12 "Has job, not at work last week" — no correction needed.
EMPLOYED_EMPSTAT_CODES = (10, 12)
MINIMUM_AGE = 16

# Wage and salary classes only: both self-employed classes (13, 14), unpaid family
# workers (29) and armed forces (26) are excluded. Confirmed live 2026-09-24 (Task 2, Step 5,
# basic-probe): the extract's own CLASSWKR codebook labels the 20s as
# {20: 'Works for wages or salary', 21: 'Wage/salary, private', 22: 'Private, for profit',
# 23: 'Private, nonprofit', 24: 'Wage/salary, government', 25: 'Federal government employee',
# 26: 'Armed forces', 27: 'State government employee', 28: 'Local government employee'} and 29 as
# 'Unpaid family worker' — this tuple (all the 20s except 26 and 29) matches exactly.
WAGE_SALARY_CLASSWKR_CODES = (20, 21, 22, 23, 24, 25, 27, 28)

OCC1990_NOT_IN_UNIVERSE = 999

# BLS's published CPS estimates use composite weights from this year on.
COMPOSITE_WEIGHT_FIRST_YEAR = 1998

# Confirmed live 2026-09-23 against each variable's own IPUMS availability table
# (cps.ipums.org/cps-action/variables/<NAME>#availability): COMPWT 1998-2026, CPSID 1976-2026,
# OCC1990 1968-2026, CLASSWKR 1962-2026. Only COMPWT's floor falls inside this project's
# 1983-2026 basic-monthly span, so it is the only basic-monthly variable whose extract
# eligibility varies by year; the others are available in every year this project requests.
VARIABLE_FIRST_YEAR: dict[str, int] = {"COMPWT": COMPOSITE_WEIGHT_FIRST_YEAR}


def variables_for_year(year: int, variables: list[str] | None = None) -> list[str]:
    """The subset of `variables` (default BASIC_MONTHLY_VARIABLES) IPUMS actually publishes for one year.

    Requesting a variable outside its published range risks IPUMS rejecting the whole extract, or
    silently omitting the column from the output — either way, callers should request only what a
    year actually carries, and readers should still reindex to the full column list (see
    `cps_detailed_panel.read_year_persons`) so a variable dropped here reads back as NaN rather
    than raising KeyError.
    """
    candidate_variables = variables if variables is not None else BASIC_MONTHLY_VARIABLES
    return [name for name in candidate_variables if year >= VARIABLE_FIRST_YEAR.get(name, 0)]


# "CPSID" if households link across months in every year 1983-2026, otherwise
# "household_month" (SERIAL within YEAR and MONTH) for the whole span — the
# bootstrap design must be identical in every year (spec § Sampling variance).
# Confirmed live 2026-09-24 (Task 2, Step 5, basic-probe): every probe month (1983, 1988, 1989,
# 1994, 1998, 2003, 2011, 2020, 2026) shows cpsid_linked_share >= 0.99, so households link across
# months throughout the whole 1983-2026 span — "CPSID" holds unchanged.
HOUSEHOLD_CLUSTER = "CPSID"

# ── Displaced Worker Supplement (Tasks 14-16). Confirmed in Task 2 Step 6. ──
DWS_SURVEY_YEARS: tuple[int, ...] = tuple(range(1984, 2027, 2))
# The supplement does NOT always ride January's sample. Confirmed live 2026-09-23 against the
# DWSUPPWT variable's own availability table (https://cps.ipums.org/cps-action/variables/DWSUPPWT
# -> "Availability" -> the year x month grid), which marks exactly one month per survey year with
# 'X': January for every survey year except 1994, 1996, 1998 and 2000, which carry it in February.
# This corrects an earlier reviewer claim that 2002 was also a February survey — the live table
# shows 2002 as January. Years present in this table (1984-2024) cover every survey this project
# uses except 2026, whose supplement (if BLS conducts and IPUMS publishes one) had not yet
# appeared as of this check.
DWS_SAMPLE_MONTH_BY_SURVEY_YEAR: dict[int, int] = {
    1984: 1,
    1986: 1,
    1988: 1,
    1990: 1,
    1992: 1,
    1994: 2,
    1996: 2,
    1998: 2,
    2000: 2,
    2002: 1,
    2004: 1,
    2006: 1,
    2008: 1,
    2010: 1,
    2012: 1,
    2014: 1,
    2016: 1,
    2018: 1,
    2020: 1,
    2022: 1,
    2024: 1,
    # 2026: unconfirmed — no row yet on the live availability table as of 2026-09-23. Falls back to
    # January below; `download_ipums_cps.dws_sample_id`'s live sample resolution and gate G6D
    # (zero total DWSUPPWT weight fails, per Ruling 10) catch a wrong guess here.
}
DWS_SAMPLE_MONTH_DEFAULT = 1


def dws_sample_month(survey_year: int) -> int:
    """The month whose CPS sample carries survey_year's Displaced Worker Supplement.

    Falls back to DWS_SAMPLE_MONTH_DEFAULT (January) for a survey year absent from
    DWS_SAMPLE_MONTH_BY_SURVEY_YEAR (currently only 2026) — unverified for that year; a wrong
    guess is caught downstream (an empty extract, or gate G6D's zero-weight failure).
    """
    return DWS_SAMPLE_MONTH_BY_SURVEY_YEAR.get(survey_year, DWS_SAMPLE_MONTH_DEFAULT)


# Offline/formatting fallback only, kept for callers that want a guessed sample id without a live
# sample list; it always guesses January's 'b' id and does not reflect the February years above.
DWS_SAMPLE_PATTERN = "cps{year}_01b"
DWS_WEIGHT_VARIABLE = "DWSUPPWT"
DWS_REASON_VARIABLE = "DWREAS"
DWS_TENURE_VARIABLE = "DWYEARS"
# Raw, vintage-coded occupation of the lost job. Required: gate G3 reads it.
DWS_LOST_JOB_OCC_VARIABLE = "DWOCC"
# Harmonized 1990-basis occupation of the lost job, or None if IPUMS has none. Confirmed present
# (named DWOCC1990) against the live IPUMS CPS variable browser 2026-09-23, and confirmed live
# 2026-09-24 in the extract itself: a single-sample probe for each of 1984, 1994, 2002, 2004 and
# 2024 shows DWOCC1990 carrying genuine non-999 (not-in-universe) values for 2.3%-5.8% of
# DWSUPPWT-positive records in every year checked — the share that is genuinely a displaced
# worker, consistent across the whole span.
DWS_LOST_JOB_OCC1990_VARIABLE: str | None = "DWOCC1990"
# Task 2 fills these from the DWREAS codebook: the codes whose labels name a
# plant or company closing or move, insufficient work, or an abolished position
# or shift — BLS's three displacement reasons. Confirmed live 2026-09-24: single-sample probe
# extracts for 1984, 1994, 2002, 2004 and 2024 all show the identical DWREAS codebook (1 distinct
# codebook across all five), with codes 1/2/3 the only ones matching these label fragments in
# every year.
DWS_DISPLACED_REASON_LABEL_FRAGMENTS = ("closed", "insufficient work", "abolished")
DWS_DISPLACED_REASON_CODES: tuple[int, ...] = (1, 2, 3)
# Tenure values above this are IPUMS not-in-universe / missing codes. Confirmed live 2026-09-24:
# across the same five probe years, real DWYEARS values top out at 54.0 and the not-in-universe
# sentinel codes start at 99.96 (99.96-99.99 across the five years) — a clean gap this ceiling
# sits inside.
DWS_TENURE_VALID_MAXIMUM = 60.0
DWS_MINIMUM_AGE = 20

# Class of worker for the *lost* job. Required so `select_displaced` can exclude self-employed
# lost jobs the way BLS's published Table 5 does. Confirmed live 2026-09-24 by fetching
# https://cps.ipums.org/cps-action/variables/DWCLASS directly (its embedded `categories` JSON and
# its `/cps-action/frequencies/DWCLASS` endpoint, which shows code 04 with nonzero weighted counts
# in real samples — e.g. 126 of ~102k records in one probe sample — so self-employed lost jobs
# genuinely occur in the data despite the page's own "Universe" note claiming the variable's
# universe already excludes them, an apparent documentation error rather than a coding fact) and
# against its availability table: DWCLASS is published for every one of this project's DWS survey
# years, 1984-2024, on the same January/February grid every other DWS variable uses (confirmed
# against `DWS_SAMPLE_MONTH_BY_SURVEY_YEAR`), so no `VARIABLE_FIRST_YEAR` entry is needed for it.
DWS_LOST_JOB_CLASS_VARIABLE = "DWCLASS"
# DWCLASS's full coding scheme, confirmed live 2026-09-24 from the variable page's embedded
# `categories` JSON: 01 Government, 02 Private, for-profit, 03 Private, non-profit,
# 04 Self-employed, 05 Without pay/family business, 96 Refused, 97 Don't Know, 98 No response,
# 99 NIU. BLS's technical note (bls.gov/news.release/disp.tn.htm) excludes "all self-employed
# people, both those with incorporated businesses as well as those with unincorporated
# businesses" from Table 5's displaced-worker population; IPUMS's DWCLASS does not split
# incorporated from unincorporated self-employment into separate codes the way `CLASSWKR` above
# does for current jobs (13/14) — this single merged code (04) is the whole exclusion.
DWS_SELF_EMPLOYED_CLASS_CODES: tuple[int, ...] = (4,)
# Codes that say nothing about whether the lost job was self-employed: NIU (not asked at all),
# Refused, Don't Know, and No response. A record carrying one of these is never excluded as
# self-employed — excluding requires a positive match against DWS_SELF_EMPLOYED_CLASS_CODES, not
# the absence of a wage/salary code — but `dws_detailed_panel.missing_lost_job_class_count` counts
# them separately per survey so their share stays visible rather than silently absorbed.
DWS_MISSING_CLASS_CODES: tuple[int, ...] = (96, 97, 98, 99)

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
    DWS_LOST_JOB_CLASS_VARIABLE,
] + ([DWS_LOST_JOB_OCC1990_VARIABLE] if DWS_LOST_JOB_OCC1990_VARIABLE else [])
