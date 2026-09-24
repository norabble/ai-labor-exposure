# IPUMS CPS verification record — Task 2, Phase 2 of the deep history extension

Date: 2026-09-23
REST client: direct `requests`-based client against the IPUMS extract API v2
(`download_ipums_cps.IpumsCpsApi`), `dataFormat: "csv"` — there is no `ipumspy`
version to record; Ruling 4 replaced it with this client (see
`download_ipums_cps.py`'s module docstring). `requests==2.34.2`, Python 3.12.14.
IPUMS sample-ID range seen live: `cps1962_03s` (earliest, a pre-basic-monthly
March CPS supplement) through `cps2026_08s` (latest basic-monthly month
published as of this date), 671 CPS samples total.

**Overall verdict, as of 2026-09-24: VERIFIED.** `VERIFICATION_STATUS` is now
`"verified"` in `ipums_cps_variables.py`. Steps 4, 5 and 6 all passed — see
"Resumed after registration (2026-09-24)" below for the live basic-probe and
per-year DWS-probe evidence that closed out Steps 5 and 6. The account
registration blocker documented immediately below (2026-09-23) has been
resolved by the user; it is kept here as the historical record of what was
blocked and why, since the rest of this file's step-by-step evidence was
gathered around it.

**Original verdict, 2026-09-23: NOT verified.** `VERIFICATION_STATUS` remained
`"unverified"` in `ipums_cps_variables.py`. Step 4 passed, with one client
correction (below). Steps 5 and 6's extract-dependent checks were **blocked**:
the IPUMS account behind `IPUMS_API_KEY` was not registered for the CPS
collection, so every extract-submission call returned `401
UserAuthorizationError`. Only the account holder could resolve this (register
at https://uma.pop.umn.edu/cps/registration/new); no workaround was attempted,
in line with the run instructions' "report and stop" rule for this kind of
block.

## Step 4: sample coverage (`verify_ipums_cps.py samples`)

### First run — pattern bug found

The first live run, using `download_ipums_cps.basic_monthly_sample_id`'s
pre-existing fixed `cps{year}_{month:02d}b` pattern, printed a partial,
non-12-month count for **every** year 1983–2026 (e.g. `1983: 4 months
published (2-8)`) and only `[1994, 1998]` for DWS survey years — clearly wrong
for a product IPUMS has published continuously since 1983 and biennially since
1984. Per the brief's guidance ("list a few IDs... correct the pattern"), the
live sample list was inspected directly:

```
cps1983_01s -> IPUMS-CPS, January 1983
cps1983_02b -> IPUMS-CPS, February 1983
cps1983_03b -> IPUMS-CPS, March 1983
cps1983_03s -> IPUMS-CPS, ASEC 1983
```

Systematically checking every (year, month) 1983–2026 against both `b` and
`s` candidates and their descriptions showed: IPUMS assigns each month's
basic-monthly sample **either** a `b` **or** an `s` suffix, with no
year/month rule (523 basic-monthly month-samples checked, 1983–2025, 0
non-standard descriptions found once ASEC is excluded). March is the sole
month that always carries both, because `03s` there is the unrelated ASEC
supplement rather than a second basic-monthly sample — every March 1983–2025
had both `{year}_03b` ("March {year}") and `{year}_03s` ("ASEC {year}").

### Correction made

| Check | Criterion | Observed | Pass/fail | Constant / code change |
|---|---|---|---|---|
| Sample-ID pattern resolves every published basic-monthly month | every year 1983–2025 shows 12 months (or explains a gap) | Fixed pattern resolved 2-8 months/year everywhere; wrong | FAIL (before fix) | `download_ipums_cps.basic_monthly_sample_id` and `dws_sample_id` now accept an optional `published_samples` set and resolve the real `b`/`s` suffix against it (`_resolve_month_sample_id`, preferring `b`, which is also correct for March). All call sites (`fetch_basic_monthly_year`, `fetch_dws_survey`, `verify_ipums_cps.py`'s `run_samples`/`run_basic_probe`/`run_dws_probe`) now pass it. `BASIC_MONTHLY_SAMPLE_PATTERN` / `DWS_SAMPLE_PATTERN` / `DWS_SAMPLE_MONTH` are kept as the offline/no-live-list fallback only, documented as such. |
| Every year 1983–2025 has 12 months | 12 | 1983–2024 and 2026: 12 (2026 partial as expected, not yet complete); **2025: 11 months, missing October** | PASS with one disclosed gap | No constant change — this is a genuine IPUMS/BLS data gap, not a code or pattern issue. `cps2025_10b` and `cps2025_10s` are both absent from IPUMS's published sample list (confirmed: 0 samples starting `cps2025_10` in the full 671-sample list). Most likely cause: the October 2025 U.S. government shutdown disrupted that month's CPS collection/publication. Recorded here rather than silently worked around. |
| Current year has however many months IPUMS has released | printed | `2026: 8 months published (1-8)` | PASS (informational) | none |
| DWS survey-year January samples present | printed | All 22 survey years present: `[1984, 1986, 1988, 1990, 1992, 1994, 1996, 1998, 2000, 2002, 2004, 2006, 2008, 2010, 2012, 2014, 2016, 2018, 2020, 2022, 2024, 2026]` (after the same suffix-resolution fix — before the fix only `[1994, 1998]` resolved) | PASS | `DWS_SURVEY_YEARS = tuple(range(1984, 2027, 2))` unchanged; correctness came entirely from the sample-ID resolution fix above. |

Full corrected output (`.venv/bin/python verify_ipums_cps.py samples`, run
with `api.ipums.org` reachable):

```
  2025: 11 months published (1-12)
  2026: 8 months published (1-8)
  Years with samples: 1983-2026
  DWS survey-year January samples present: [1984, 1986, 1988, 1990, 1992, 1994, 1996, 1998, 2000, 2002, 2004, 2006, 2008, 2010, 2012, 2014, 2016, 2018, 2020, 2022, 2024, 2026]
```

(Every other year 1983–2024 printed nothing, meaning all 12 months resolved —
`run_samples` only prints years with fewer than 12 or zero months.)

## Step 5: basic-monthly probe (`verify_ipums_cps.py basic-probe`) — BLOCKED

| Check | Criterion | Observed | Pass/fail | Constant set |
|---|---|---|---|---|
| Extract submission succeeds | extract queues and completes | `POST /extracts` → `401 UserAuthorizationError`: `"rybaker5@gmail.com is not registered to IPUMS cps. Please go to https://uma.pop.umn.edu/cps/registration/new to create or renew your registration."` Reproduced twice, including a bare `GET /extracts` (list) call, which fails identically — this is an account-registration gate on the whole extracts endpoint, not a malformed request. | **BLOCKED** | none — cannot proceed until the account completes IPUMS CPS registration |
| `occ1990_valid_share` (2020, latest January) | ≥ 0.99 | not observed | BLOCKED | `EMPLOYED_EMPSTAT_CODES` unchanged |
| `relative_difference`, every row | within ±2% | not observed | BLOCKED | none |
| `compwt_positive_share`, 1998+ | ≥ 0.99 | not observed | BLOCKED | none |
| Household cluster decision | printed | not observed | BLOCKED | `HOUSEHOLD_CLUSTER` unchanged (`"CPSID"`, still the pre-verification default) |
| `EMPSTAT` codes | 10, 12 employed | not observed | BLOCKED | `EMPLOYED_EMPSTAT_CODES` unchanged |
| `CLASSWKR` codes | wage/salary = the 20s except armed forces/unpaid family | not observed | BLOCKED | `WAGE_SALARY_CLASSWKR_CODES` unchanged |
| Estimated full extract size | printed | not observed | BLOCKED | n/a |

No probe extract directory was created (`_submit_and_download` raises before
`os.makedirs`/download), confirmed by `find data/raw/ipums` finding nothing —
no partial or stray microdata is staged anywhere in the repo.

## Step 6: DWS probe (`verify_ipums_cps.py dws-probe`) — partially confirmed, extract-dependent checks BLOCKED

The variable-name portion of this step (documentation only, no extract needed)
was completed against the live IPUMS CPS variable browser's Displaced Worker
Supplement group (`https://cps.ipums.org/cps-action/variables/group?id=dw_dw`,
fetched 2026-09-23):

| Role | Variable found | Matches prior guess? |
|---|---|---|
| Supplement weight | `DWSUPPWT` | yes (`DWS_WEIGHT_VARIABLE`) |
| Reason for job loss | `DWREAS` | yes (`DWS_REASON_VARIABLE`) |
| Years of tenure at lost job | `DWYEARS` | yes (`DWS_TENURE_VARIABLE`) |
| Raw/vintage-coded occupation of lost job | `DWOCC` | yes (`DWS_LOST_JOB_OCC_VARIABLE`) |
| Harmonized 1990-basis occupation of lost job | `DWOCC1990` — present | **no** — was `None`, now set |

| Check | Criterion | Observed | Pass/fail | Constant set |
|---|---|---|---|---|
| Supplement/reason/tenure/raw-occupation variable names | match IPUMS variable browser | all four already matched | PASS | no change (`DWSUPPWT`, `DWREAS`, `DWYEARS`, `DWOCC`) |
| Harmonized lost-job `OCC1990` | present or absent | present, named `DWOCC1990` | recorded | `DWS_LOST_JOB_OCC1990_VARIABLE = "DWOCC1990"` (was `None`) |
| Positive supplement weights in 1984 | present | not observed (needs extract) | BLOCKED | none |
| 2002 and 2004 present or absent | either | not observed (needs extract) | BLOCKED | none |
| Displaced reason codes by label | exactly three codes | not observed (needs extract) | BLOCKED | `DWS_DISPLACED_REASON_CODES` unchanged (`()`) |
| Tenure not-in-universe/missing codes all above 60 | true | not observed (needs extract) | BLOCKED | `DWS_TENURE_VALID_MAXIMUM` unchanged (`60.0`) |
| Raw lost-job occupation present in every probe year | true | not observed (needs extract) — variable exists in the schema (`DWOCC`), but per-year presence in actual survey data is unconfirmed | BLOCKED (gate G3 / Tasks 14-16 cannot be cleared to proceed) | none |

**Whether `DWOCC1990`'s presence in the variable browser is enough on its own
to trust `DWS_LOST_JOB_OCC1990_VARIABLE`'s value is a documentation-only
confirmation, not an extract-verified one** — IPUMS occasionally lists a
variable in a supplement's schema that is sparsely or never populated for a
given sample; the dws-probe would have shown its non-null coverage per survey
year. That check remains open pending the same registration blocker.

## What is and is not safe to build on right now

- Safe: the corrected sample-ID resolution logic in `download_ipums_cps.py`
  (unit-tested, no live dependency at call time other than the sample list
  itself) and `ipums_cps_variables.py`'s confirmed sample-ID coverage
  (1983–2026 basic-monthly, all 22 DWS survey years present).
- Not yet safe: anything depending on `OCC1990` coverage after 2019, the
  composite-weight/`WTFINL` fallback decision, the household-clustering
  variable (`HOUSEHOLD_CLUSTER` is still its pre-verification default,
  `"CPSID"`, unconfirmed), `EMPSTAT`/`CLASSWKR` code values, the DWS
  displaced-reason codes, the DWS tenure valid-value ceiling, or the DWS raw
  lost-job occupation's actual per-year coverage (gate G3). None of these can
  be confirmed without a completed IPUMS CPS registration on the account
  behind `IPUMS_API_KEY`.

## Addendum, 2026-09-23 (final whole-branch review, Ruling 10 / Ruling 11): DWS sample month and variable availability, confirmed against public cps.ipums.org pages

The extract-submission blocker above (account not registered for IPUMS CPS)
still holds — nothing below required an extract. Every fact in this addendum
was read directly off IPUMS's own public variable pages
(`https://cps.ipums.org/cps-action/variables/<NAME>`), which need no API key
and are not affected by the registration gate.

### DWS supplement month is not always January (Ruling 10, Critical finding 1)

`ipums_cps_variables.py` and `download_ipums_cps.dws_sample_id` previously
assumed the Displaced Worker Supplement always rides that survey year's
January basic-monthly sample. A reviewer flagged this as wrong for 1994,
1996, 1998, 2000 and 2002 (claimed February), "confident, unverified."

Fetched `https://cps.ipums.org/cps-action/variables/DWSUPPWT` (the
supplement's own weight variable) and read its "Availability" year x month
grid, which marks exactly one month per survey year with an `X`:

```
1984 Jan   1986 Jan   1988 Jan   1990 Jan   1992 Jan
1994 Feb   1996 Feb   1998 Feb   2000 Feb
2002 Jan   2004 Jan   2006 Jan   2008 Jan   2010 Jan   2012 Jan
2014 Jan   2016 Jan   2018 Jan   2020 Jan   2022 Jan   2024 Jan
```

(2026 has no row yet on the live table as of this check — the survey may not
yet be conducted/published for that year.)

**This confirms four of the reviewer's five flagged years (1994, 1996, 1998,
2000) but refutes the fifth: 2002 is January, not February.** The reviewer's
guess for 2002 would have picked the wrong sample.

`DWS_SAMPLE_MONTH_BY_SURVEY_YEAR` in `ipums_cps_variables.py` now encodes this
table exactly (source: the DWSUPPWT availability grid above, read 2026-09-23),
with `dws_sample_month()` falling back to January (`DWS_SAMPLE_MONTH_DEFAULT`)
only for 2026, which is unconfirmed and marked as such in the module. A wrong
guess there is caught by two independent mechanisms: `dws_sample_id`'s live
`published_samples` resolution (an entirely wrong month simply will not
appear in the sample list IPUMS actually publishes for that year), and gate
G6D's zero-weight-is-a-failure fix (`dws_detailed_panel.py`,
`attach_lost_job_occ1990dd`) — a resolved sample that carries no supplement
data would previously report a vacuous 0.0 unmapped share (a pass); it now
reports 1.0 (a hard failure), and `build_rebuilt_panel` also now raises
`RuntimeError` outright if a whole requested survey set downloads to nothing.

**Step 6 addendum:** confirming DWSUPPWT's positive weight in each survey's
*own* resolved-month extract (not just its presence in the schema) still
requires the blocked extract step. Task 2 Step 6, when unblocked, must submit
each survey year's single resolved sample (per
`DWS_SAMPLE_MONTH_BY_SURVEY_YEAR`) and confirm `DWSUPPWT > 0` for at least one
record before trusting that year — this is exactly the check gate G6D now
also enforces at build time as a backstop, not a replacement for that
verification step.

### Per-variable availability ranges (Ruling 11, Important finding 2)

Fetched each variable's own IPUMS availability table
(`https://cps.ipums.org/cps-action/variables/<NAME>#availability`):

| Variable | Availability (per its own IPUMS page) | Falls inside 1983–2026? |
|---|---|---|
| `COMPWT` | 1998–2026 | **Yes** — floor is 1998, inside the span |
| `CPSID` | 1976–2026 | No — available for the whole span |
| `OCC1990` | 1968–2026 | No — available for the whole span |
| `CLASSWKR` | 1962–2026 | No — available for the whole span |
| `DWOCC1990` | every DWS survey year 1984–2024 individually listed | No — present every survey year checked |
| `DWOCC` | every DWS survey year 1984–2024 individually listed | No — present every survey year checked |
| `DWREAS` | every DWS survey year 1984–2024 individually listed | No — present every survey year checked |
| `DWYEARS` | every DWS survey year 1984–2024 individually listed | No — present every survey year checked |

Only `COMPWT` has a floor that falls inside this project's request range, and
it already matches the pre-existing `COMPOSITE_WEIGHT_FIRST_YEAR = 1998`
constant — no correction needed there, only encoding it as an extract-request
constraint rather than a gate-selection constant alone.
`ipums_cps_variables.VARIABLE_FIRST_YEAR = {"COMPWT": 1998}` and
`variables_for_year(year)` now filter `BASIC_MONTHLY_VARIABLES` per year
before `download_ipums_cps.fetch_basic_monthly_year` submits an extract, and
`cps_detailed_panel.read_year_persons` reindexes each chunk to the full
`BASIC_MONTHLY_VARIABLES` column list (rather than a plain column selection)
so a year that did not request `COMPWT` reads it back as `NaN` instead of
raising `KeyError`. `gate_weight_column` already only reads `COMPWT` from
1998 on, so this NaN never reaches a gate.

The DWS variables (`DWOCC1990`, `DWOCC`, `DWREAS`, `DWYEARS`) needed no
per-year filtering — IPUMS's own availability pages list every one of them as
present for every DWS survey year 1984–2024 individually, so `DWS_VARIABLES`
is unchanged. A single-vintage probe extract (one pre-1998 basic-monthly
year, requesting only `variables_for_year(year)`) is still the direct,
extract-level confirmation Task 2 Step 6 owes once the account is
unblocked — this addendum's evidence is documentation-only, from each
variable's own published page, not from a submitted extract.

## Next step for the user (historical — resolved 2026-09-24)

Register (or renew registration) for the IPUMS CPS collection at
https://uma.pop.umn.edu/cps/registration/new using the account associated
with the current `IPUMS_API_KEY` (the 401 response names it as
`rybaker5@gmail.com`). Once that completes, re-run:

```
.venv/bin/python verify_ipums_cps.py basic-probe
.venv/bin/python verify_ipums_cps.py dws-probe
```

and fill in the BLOCKED rows above before setting `VERIFICATION_STATUS =
"verified"`.

**This was done — see the section below.**

## Resumed after registration (2026-09-24): Steps 5–7 completed live

Registration was confirmed fixed with a direct `GET /extracts` call (200,
`{"data":[],"totalCount":0,...}`, versus the 401 `UserAuthorizationError` of
the day before). All three probes were then run live:
`verify_ipums_cps.py basic-probe`, a new `verify_ipums_cps.py
basic-legacy-probe` (added this session — see "Code correction" below), and a
rewritten `verify_ipums_cps.py dws-probe` that now submits one single-sample
extract **per DWS survey year** rather than one combined extract, so an empty
or wrong-month year cannot hide behind another year's real data in a shared
extract.

### Step 5: basic-monthly probe — PASS, no corrections needed

`.venv/bin/python verify_ipums_cps.py basic-probe` output (probe months 1983,
1988, 1989, 1994, 1998, 2003, 2011, 2020, plus the latest published January,
2026):

```
 year  month  employed_thousands  occ1990_valid_share  compwt_positive_share  cpsid_linked_share          classwkr_codes  published_thousands  relative_difference
 1983      1        97339.716970                  1.0                    0.0                 1.0    13,14,21,25,27,28,29              97262.0             0.000799
 1988      1       112118.491910                  1.0                    0.0                 1.0    13,14,21,25,27,28,29             112139.0            -0.000183
 1989      1       114972.872790                  1.0                    0.0                 1.0    13,14,21,25,27,28,29             114786.0             0.001628
 1994      1       119839.857659                  1.0                    0.0                 1.0 13,14,22,23,25,27,28,29             119901.0            -0.000510
 1998      1       129258.840438                  1.0                    1.0                 1.0 13,14,22,23,25,27,28,29             128882.0             0.002924
 2003      1       135906.819317                  1.0                    1.0                 1.0 13,14,22,23,25,27,28,29             135907.0            -0.000001
 2011      1       137985.844636                  1.0                    1.0                 1.0 13,14,22,23,25,27,28,29             137599.0             0.002811
 2020      1       157394.431215                  1.0                    1.0                 1.0 13,14,22,23,25,27,28,29             156994.0             0.002551
 2026      1       162239.726567                  1.0                    1.0                 1.0 13,14,22,23,25,27,28,29             161670.0             0.003524

  Household cluster decision: CPSID

  EMPSTAT codes: {'NIU': 0, 'Armed Forces': 1, 'At work': 10, 'Has job, not at work last week': 12, 'Unemployed': 20, 'Unemployed, experienced worker': 21, 'Unemployed, new worker': 22, 'Not in labor force': 30, 'NILF, housework': 31, 'NILF, unable to work': 32, 'NILF, school': 33, 'NILF, other': 34, 'NILF, unpaid, lt 15 hours': 35, 'NILF, retired': 36}

  CLASSWKR codes: {'NIU': 0, 'Self-employed': 10, 'Self-employed, not incorporated': 13, 'Self-employed, incorporated': 14, 'Works for wages or salary': 20, 'Wage/salary, private': 21, 'Private, for profit': 22, 'Private, nonprofit': 23, 'Wage/salary, government': 24, 'Federal government employee': 25, 'Armed forces': 26, 'State government employee': 27, 'Local government employee': 28, 'Unpaid family worker': 29, 'Missing/Unknown': 99}

  Probe data file: 22.9 MB for 9 months
  Full 1983-2026 basic monthly, extrapolated: ≈ 1.3 GB
```

| Check | Criterion | Observed | Pass/fail | Constant |
|---|---|---|---|---|
| `occ1990_valid_share` (2020, latest January = 2026) | ≥ 0.99 | 1.0, 1.0 | **PASS** — not the design-breaking STOP | no change |
| `relative_difference`, every row | within ±2% | max magnitude 0.35% (1989) | **PASS** | no change |
| `compwt_positive_share`, 1998+ | ≥ 0.99 | 1.0 for 1998, 2003, 2011, 2020, 2026 | **PASS** | no change — pre-1998 rows show 0.0 because this combined probe requests `BASIC_MONTHLY_VARIABLES` (unfiltered) for every sample; IPUMS answers with 0 rather than rejecting the extract, consistent with `VARIABLE_FIRST_YEAR` |
| Household cluster decision | printed | `CPSID` (every probe month's `cpsid_linked_share` = 1.0) | **PASS** | `HOUSEHOLD_CLUSTER = "CPSID"` — unchanged, now live-confirmed |
| `EMPSTAT` codes | 10, 12 employed | `10: 'At work'`, `12: 'Has job, not at work last week'` | **PASS** | `EMPLOYED_EMPSTAT_CODES = (10, 12)` — unchanged, now live-confirmed |
| `CLASSWKR` codes | wage/salary = the 20s except armed forces (26) / unpaid family (29) | 20-25, 27, 28 all labeled wage/salary variants; 26 "Armed forces"; 29 "Unpaid family worker" | **PASS** | `WAGE_SALARY_CLASSWKR_CODES = (20, 21, 22, 23, 24, 25, 27, 28)` — unchanged, now live-confirmed |
| Estimated full extract size | printed | ≈ 1.3 GB for the full 1983-2026 basic-monthly span | **PASS** | no STOP — nowhere near a plausible IPUMS extract-size limit; the ASEC-fallback question does not arise |

No STOP condition was triggered. All Step 5 constants were already correct;
this run's only role was turning "documentation guess" into "live-confirmed."

### Step 6: DWS probe — PASS, one constant set, one code defect found and fixed

`ipums_cps_variables.DWS_PROBE_YEARS` was widened from `(1984, 1994, 2002,
2004, 2020)` to `(1984, 1994, 2002, 2004, 2024, 2026)` per this session's
instruction, to check the newest survey and the not-yet-published one.

#### Code correction: per-year single-sample DWS extracts, and a new legacy-variable probe

The pre-existing `run_dws_probe` submitted all probe years as **one combined
extract**. Rewritten this session to submit **one extract per survey year**
into its own `data/raw/ipums/probe/dws/<year>/` directory — a design
correction requested for this resumption, not a bug found live, but worth
recording: a combined extract cannot distinguish "this year's supplement is
genuinely empty/wrong-month" from "this year has few displaced-worker
records," because both look like a small subset of one merged table. Per-year
extracts make an empty year unambiguous.

Also added `run_legacy_variable_probe` (`basic-legacy-probe` command): submits
a single pre-1998 basic-monthly month (January 1985) requesting only
`ipums_variables.variables_for_year(1985)` — the exact per-year-filtered
variable list `fetch_basic_monthly_year` uses in the real build — to confirm
IPUMS accepts that filtered request and simply omits `COMPWT` rather than
rejecting the extract or returning a bogus column. Output:

```
  Sample: cps1985_01b
  Requested variables (12): ['YEAR', 'MONTH', 'SERIAL', 'CPSID', 'PERNUM', 'MISH', 'WTFINL', 'AGE', 'EMPSTAT', 'OCC', 'OCC1990', 'CLASSWKR']
  Columns actually returned (14): ['AGE', 'CLASSWKR', 'CPSID', 'CPSIDP', 'CPSIDV', 'EMPSTAT', 'MISH', 'MONTH', 'OCC', 'OCC1990', 'PERNUM', 'SERIAL', 'WTFINL', 'YEAR']
  COMPWT requested: False
  COMPWT present in returned columns: False
  Row count: 153325
```

Confirmed: `COMPWT` was not requested and is not present. IPUMS also returned
two columns never requested (`CPSIDP`, `CPSIDV` — per-person/per-household
CPSID variants IPUMS appears to always include). `cps_detailed_panel.
read_year_persons` already reindexes to `BASIC_MONTHLY_VARIABLES` rather than
selecting columns directly, so these extras are silently dropped there — no
defect.

#### Code defect found live and fixed: a resolved-but-unpublished-supplement sample crashes the probe

Running the rewritten `dws-probe` against all six years, the first five
(1984, 1994, 2002, 2004, 2024) succeeded, then 2026 crashed the whole probe:

```
requests.exceptions.HTTPError: 400 Client Error: Bad Request for url: https://api.ipums.org/extracts?collection=cps&version=2
```

Diagnosed with a direct API call: IPUMS's `cps2026_01s` sample **exists**
(basic-monthly data is published for it) but carries **no DWS supplement
variables at all**:

```json
{"type":"SemanticValidationError","status":{"code":400,"name":"Bad Request"},
 "detail":["DWREAS: This variable is not available in any of the samples currently selected.",
           "DWYEARS: This variable is not available in any of the samples currently selected.",
           "DWOCC: This variable is not available in any of the samples currently selected.",
           "DWOCC1990: This variable is not available in any of the samples currently selected.",
           "DWSUPPWT: This variable is not available in any of the samples currently selected."]}
```

This is a real gap `download_ipums_cps.available_sample_ids` membership
cannot catch (the sample itself is real and published), and one
`run_dws_probe` had no handling for — a legitimate defect surfaced by this
probe, exactly the kind of finding the resumption instructions asked to fix
minimally with a test. **Fix**: added `submit_and_download_or_none` in
`verify_ipums_cps.py`, which calls `download_ipums_cps._submit_and_download`
and returns `None` instead of propagating a `requests.exceptions.HTTPError`;
`run_dws_probe` now prints "does not carry the DWS supplement — skipped" and
continues to the next year rather than crashing. Unit-tested in
`tests/test_verify_ipums_cps.py::TestSubmitAndDownloadOrNone` (one case
raising, one case succeeding), with a fake `_submit_and_download` via
`monkeypatch` — no network. Re-running `dws-probe` after the fix completed
cleanly, the five downloaded years read from cache (not resubmitted) and 2026
skipped with a clear message. This confirms, live, the same 2026 gap the
2026-09-23 addendum had already found from IPUMS's public DWSUPPWT
availability page (documentation-only, at the time) — no survey has been
conducted or published for 2026 yet.

#### Per-year DWS evidence

| Survey year | Resolved sample | Resolved month | Matches `DWS_SAMPLE_MONTH_BY_SURVEY_YEAR`? | Records w/ `DWSUPPWT` > 0 | `DWREAS` codebook | `DWOCC1990` non-999 share |
|---|---|---|---|---|---|---|
| 1984 | `cps1984_01s` | 1 (Jan) | yes | 154,300 / 154,300 (100%) | 10 codes, identical to every other year below | 5.8% |
| 1994 | `cps1994_02s` | 2 (Feb) | yes | 140,491 / 141,051 (99.6%) | identical | 3.4% |
| 2002 | `cps2002_01s` | 1 (Jan) | yes | 92,383 / 141,834 (65.1%) | identical | 5.0% |
| 2004 | `cps2004_01s` | 1 (Jan) | yes | 90,160 / 139,398 (64.7%) | identical | 5.4% |
| 2024 | `cps2024_01s` | 1 (Jan) | yes | 66,709 / 99,135 (67.3%) | identical | 2.3% |
| 2026 | `cps2026_01s` | 1 (Jan, unconfirmed fallback) | n/a — sample carries no DWS variables at all | — | — | — |

`Distinct DWREAS codebooks across probe years: 1` and `Distinct DWYEARS
codebooks across probe years: 1` (both printed by the probe) confirm the five
successful years share one identical codebook — no per-vintage drift.

**Observation, not a correction:** `DWSUPPWT > 0` is a much weaker filter for
"in the DWS-eligible universe" in 1984/1994 (100%/99.6% positive, including
age-0 records) than in 2002/2004/2024 (~65-67% positive). Checked directly:
`DWREAS`'s own NIU (99) share is stable across every year regardless (94.2%,
93.9%, 94.8%, 94.8%, 96.5%) — the true "was this person asked" gate is
`DWREAS != 99` combined with age, not `DWSUPPWT`'s positivity alone.
`dws_detailed_panel.select_displaced` already filters on `weights > 0 & AGE
>= DWS_MINIMUM_AGE & DWREAS.isin(DWS_DISPLACED_REASON_CODES)` together, so
this quirk does not bias the production tabulation — flagged here for
anyone extending the DWS panel who might otherwise use `DWSUPPWT > 0` alone
as an eligibility filter.

**`DWS_MINIMUM_AGE = 20`**: confirmed effectively correct. 1994 shows 3
records with age < 20 (16, 18, 19) among 8,544 `DWREAS`-answered records —
noise, not a rule change; every other year's minimum answering age is exactly
20.

| Check | Criterion | Observed | Pass/fail | Constant set |
|---|---|---|---|---|
| Positive supplement weights in 1984 | present | 154,300 of 154,300 records (100%) | **PASS** | none |
| 2002 and 2004 | present or absent | both present, both resolve to January, both show normal displaced-worker populations | **PASS** (recorded) | none |
| Displaced reason codes by label | exactly three codes | `(1, 2, 3)` in every one of the five successful years, identical codebook | **PASS** | `DWS_DISPLACED_REASON_CODES = (1, 2, 3)` (was `()`) |
| Tenure not-in-universe/missing codes all above 60 | true | real `DWYEARS` values top out at 54.0 across all five years; sentinel codes range 99.96-99.99 — a clean gap | **PASS** | `DWS_TENURE_VALID_MAXIMUM = 60.0` — unchanged, now live-confirmed |
| Raw lost-job occupation present in every probe year | true | `DWOCC` present with real, non-trivial value ranges in every year (e.g. 418 distinct values 0-905 in 1984, 382 distinct values 0-9998 in 2004 — range differs because IPUMS's own DWOCC vintage changes with each year's Census occupation coding) | **PASS** — gate G3 / Tasks 14-16 may proceed | none |
| Harmonized lost-job `OCC1990` | present or absent | present, named `DWOCC1990`, carrying genuine non-999 values in every probe year (2.3%-5.8% of `DWSUPPWT`-positive records) | **PASS** (extract-confirmed, not just documentation) | `DWS_LOST_JOB_OCC1990_VARIABLE = "DWOCC1990"` — unchanged, now extract-confirmed |

No STOP condition was triggered (a raw lost-job occupation was present in
every probed year, so gate G3 is not blocked).

### Step 7: verification record and status — done

Every check in Steps 4, 5 and 6 passed, or was resolved exactly as the
brief's tables direct (the one live code defect — the 2026 DWS
sample-without-supplement crash — was fixed and unit-tested, not routed
around silently). `ipums_cps_variables.VERIFICATION_STATUS` is set to
`"verified"`.

Final IPUMS sample-ID range seen across this whole verification effort:
`cps1962_03s` through `cps2026_08s` (Step 4), plus every sample actually
extracted for Steps 5-6 above (`cps1983_01s` .. `cps2026_01s` and
`cps1985_01b`). REST client: `requests==2.34.2`, Python 3.12.14, IPUMS extract
API v2, `dataFormat: "csv"` (see the top of this file — unchanged from
2026-09-23).

## Addendum 2026-09-24 — DWCLASS (self-employed lost-job exclusion, G3 fix)

**Root cause being fixed:** `dws-diagnosis-report.md` (same directory as the
brief) found that `dws_detailed_panel.select_displaced` counts self-employed
lost-job records that BLS's published Table 5 explicitly excludes, and traced
G3's 40/90-pass rate to that population mismatch. User approved adding the
class-of-worker-of-lost-job variable and excluding self-employed records.

**Variable confirmed live** by fetching
`https://cps.ipums.org/cps-action/variables/DWCLASS` directly (`curl -A
"Mozilla/5.0"`, `allowed_domains: ["cps.ipums.org"]`) rather than relying on
the WebFetch summarizer, which could not see the codes table (it loads via a
separate endpoint). Two pieces of evidence:

1. The variable page's embedded `categories` JSON gives the full coding
   scheme directly (`<h1>DWCLASS</h1>`, `jsonPath:
   "/cps-action/frequencies/DWCLASS"`, confirming the page is genuinely
   DWCLASS's own, not a mixed/cached fetch):

   | Code | Label |
   |---|---|
   | 01 | Government |
   | 02 | Private, for-profit |
   | 03 | Private, non-profit |
   | 04 | Self-employed |
   | 05 | Without pay/family business |
   | 96 | Refused |
   | 97 | Don't Know |
   | 98 | No response |
   | 99 | NIU |

2. `https://cps.ipums.org/cps-action/frequencies/DWCLASS` (the JSON the page's
   own `jsonPath` points at) returns real per-sample category counts, e.g. for
   category id `8857833` (code 04, "Self-employed"): `126` in one sample and
   `75` in another, both out of populations of ~100k-140k weighted-eligible
   records. **Self-employed lost-job records are genuinely present in the
   data** despite the page's own "Universe" prose (`<div
   id="universe_section">`) reading "Civilians age 20 or older who lost or
   left their job in the last five/three years **and were not
   self-employed**" — that prose is an apparent documentation error (perhaps
   copied from `DWSTAT`'s page, which the diagnosis report already found
   really does implement that exclusion from 1998 on) rather than a coding
   fact; the live codes and frequencies are authoritative, and they show one
   merged "Self-employed" code carrying real weight in every checked sample.

   IPUMS's own codebook does **not** split incorporated from unincorporated
   self-employment for this variable the way `CLASSWKR` does for current jobs
   (codes 13/14) — there is exactly one merged "Self-employed" code (04).
   `ipums_cps_variables.DWS_SELF_EMPLOYED_CLASS_CODES = (4,)` is therefore the
   whole exclusion BLS's technical note describes ("excludes all self-employed
   people, both those with incorporated businesses as well as those with
   unincorporated businesses" — bls.gov/news.release/disp.tn.htm).

**Availability confirmed live** from the same page's availability table:
DWCLASS is published for every one of this project's 21 DWS survey years,
1984-2024, on exactly the same January/February grid every other DWS variable
already uses (`DWS_SAMPLE_MONTH_BY_SURVEY_YEAR`) — January for every survey
year except 1994/1996/1998/2000 (February). No gaps, so no
`VARIABLE_FIRST_YEAR` entry was needed for `DWCLASS` in
`ipums_cps_variables.variables_for_year`'s per-year mechanism (that mechanism
is unused for the DWS extract path anyway, which requests one fixed variable
list — `DWS_VARIABLES` — per survey year rather than varying it).

**Missing/NIU handling:** codes 96 (Refused), 97 (Don't Know), 98 (No
response) and 99 (NIU) say nothing about whether the lost job was
self-employed, so `ipums_cps_variables.DWS_MISSING_CLASS_CODES = (96, 97, 98,
99)` are never excluded by `dws_detailed_panel.select_displaced` — a record
must positively match `DWS_SELF_EMPLOYED_CLASS_CODES` to be dropped.
`dws_detailed_panel.missing_lost_job_class_count` counts these kept records
per survey; see `dws-selfemp-report.md` for the per-survey counts from the
real rebuild.

This addendum does not change `VERIFICATION_STATUS` (already `"verified"`) —
it documents one additional variable added to an already-verified extract
definition for a separate, user-approved bug fix.

## Addendum 2026-09-24 — DWRECALL, DWLASTWRK (expected-recall and reference-window exclusions, G3 fix round 2)

**Root cause being fixed:** `g3-diagnosis2-report.md` (same directory as the
brief) found that, even after the DWCLASS fix above, `select_displaced` still
counts two further populations BLS's published Table 5/8 excludes: layoffs
where the respondent expected recall to the same job within six months, and
lost jobs outside the survey's own reference window. User approved adding
`DWRECALL` and `DWLASTWRK` and excluding both.

**Both variables confirmed live** by fetching
`https://cps.ipums.org/cps-action/variables/DWRECALL` and
`https://cps.ipums.org/cps-action/variables/DWLASTWRK` directly (`curl`,
`allowed_domains: ["cps.ipums.org"]`, saved to local HTML and grepped for the
embedded `categories` JSON) — the same method the DWCLASS addendum above used,
since WebFetch's summarizer again could not see the codes table (confirmed:
a WebFetch call on each URL returned only the universe prose and a
placeholder availability grid, not the codes).

1. **DWRECALL** embedded `categories` JSON (`https://cps.ipums.org/cps-action/variables/DWRECALL`,
   fetched 2026-09-24):

   | Code | Label |
   |---|---|
   | 01 | No |
   | 02 | Yes |
   | 96 | Refused |
   | 97 | Don't Know |
   | 98 | No response |
   | 99 | NIU |

   Universe (page prose): "Persons who lost a job in the last year because of
   a shift elimination or insufficient work" — plant-closing layoffs are
   therefore NIU (99) on this variable, never coded 2, so the recall exclusion
   cannot touch them. `DWS_RECALL_EXPECTED_CODE = 2` ("Yes") is the whole
   exclusion; 96/97/98/99 are kept, the same missing-is-kept convention as
   `DWS_MISSING_CLASS_CODES`.

   **Availability**, from the same page's year x month grid: `X` (published)
   only from the 1994 survey on — February for 1994/1996/1998/2000, January
   for 2002-2024 (even years) — and no mark at all for 1984-1992.
   `DWS_RECALL_FIRST_SURVEY_YEAR = 1994` records this; it is the first survey
   year IPUMS publishes DWRECALL for, and it is absent from every earlier
   survey's extract (no column, not a null value in a present column).

2. **DWLASTWRK** embedded `categories` JSON (`https://cps.ipums.org/cps-action/variables/DWLASTWRK`,
   fetched 2026-09-24):

   | Code | Label |
   |---|---|
   | 00 | This year |
   | 01 | Last year |
   | 02 | Two years ago |
   | 03 | Three years ago |
   | 04 | Four years ago |
   | 05 | Five years ago |
   | 95 | Other |
   | 96 | Refused |
   | 97 | Don't Know |
   | 98 | No response |
   | 99 | NIU |

   Universe (page prose, two periods): "1984-1992: Civilians age 20 or older
   who lost or left a job in the past five years because the company closed
   down, eliminated the shift or position, or had insufficient work" and
   "1994+: ... in the past three years ...". `dws_lastwrk_window` encodes this
   as codes `(1, 2, 3)` for 1994+ and `(1, 2, 3, 4, 5)` for 1984-1992. Code 00
   ("this year") is excluded on both windows — the diagnosis's exact match to
   BLS Table 8 (within 0.5k in every 2008-2024 survey) uses codes 1-3 only,
   never 0, and the survey's own resolved sample month (January or February)
   falls inside the still-in-progress current calendar year, which is outside
   "the last N calendar years" both universe statements describe.

   **Availability**, from the same page's year x month grid: published in
   every DWS survey year 1984-2024, on the same January/February pattern as
   every other DWS variable (`DWS_SAMPLE_MONTH_BY_SURVEY_YEAR`) — so `DWLASTWRK`
   needs no `DWS_VARIABLE_FIRST_YEAR` entry, unlike `DWRECALL`.

**Evidence behind `dws_variables_for_year`:** `DWS_VARIABLES` is a single flat
list shared by every survey year's extract request
(`download_ipums_cps.fetch_dws_survey`), but `DWRECALL`'s availability grid
above shows it genuinely absent for 1984-1992 — not merely null. Requesting a
variable IPUMS does not publish for any resolved sample raises a `400
SemanticValidationError` naming that variable
(`download_ipums_cps.MISSING_VARIABLE_ERROR_FRAGMENT`, confirmed live
2026-09-24 for the unrelated 2026-survey-has-no-supplement case, same
mechanism); `submit_and_download_or_none` narrowly treats that one error as
"no supplement this sample" and returns `None`. Without
`dws_variables_for_year`, requesting `DWRECALL` for e.g. survey year 1990
would trigger that same 400, be caught by
`submit_and_download_or_none`, and silently skip an otherwise-valid pre-1994
survey as if it had no DWS supplement at all — a false negative, not merely a
missing column. `dws_variables_for_year(survey_year)` (mirroring
`ipums_cps_variables.variables_for_year`, the existing basic-monthly
mechanism that already does the equivalent thing for `COMPWT` before 1998)
filters `DWS_VARIABLES` against a new `DWS_VARIABLE_FIRST_YEAR` dict
(`{"DWRECALL": 1994}`) before every DWS extract request, so a pre-1994
extract never asks IPUMS for `DWRECALL` at all. Regression test:
`tests/test_download_ipums_cps.py::TestFetchDwsSurvey::test_a_pre_1994_survey_does_not_request_dwrecall`.

This addendum does not change `VERIFICATION_STATUS` (already `"verified"`) —
it documents two additional variables added to an already-verified extract
definition for a separate, user-approved bug fix.
