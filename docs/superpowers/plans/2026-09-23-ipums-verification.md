# IPUMS CPS verification record — Task 2, Phase 2 of the deep history extension

Date: 2026-09-23
REST client: direct `requests`-based client against the IPUMS extract API v2
(`download_ipums_cps.IpumsCpsApi`), `dataFormat: "csv"` — there is no `ipumspy`
version to record; Ruling 4 replaced it with this client (see
`download_ipums_cps.py`'s module docstring). `requests==2.34.2`, Python 3.12.14.
IPUMS sample-ID range seen live: `cps1962_03s` (earliest, a pre-basic-monthly
March CPS supplement) through `cps2026_08s` (latest basic-monthly month
published as of this date), 671 CPS samples total.

**Overall verdict: NOT verified.** `VERIFICATION_STATUS` remains `"unverified"`
in `ipums_cps_variables.py`. Step 4 passed, with one client correction (below).
Steps 5 and 6's extract-dependent checks are **blocked**: the IPUMS account
behind `IPUMS_API_KEY` is not registered for the CPS collection, so every
extract-submission call returns `401 UserAuthorizationError`. Only the account
holder can resolve this (register at
https://uma.pop.umn.edu/cps/registration/new); no workaround was attempted, in
line with the run instructions' "report and stop" rule for this kind of block.

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

## Next step for the user

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
