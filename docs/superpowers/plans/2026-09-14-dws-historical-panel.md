# DWS Historical Panel and `D` Extension — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the project's only structurally non-circular validation from a single-survey cross-section (n=10) into a ten-survey panel spanning 2008–2026, and widen the economy-wide displacement rate `D` to match.

**Architecture:** BLS *does* publish archived Displaced Worker Supplement news releases — the project's documentation says otherwise, and that is wrong. Nine biennial archives from 2008 to 2024 are reachable, each carrying its tables **inline** in one page rather than split across `disp.t02/t05/t08.htm` as the current release is. This plan adds an archive-fetch path beside the existing current-release path, accumulates every survey into the committed seed panel, and extends `composition_displacement_validation.py` from one cross-section to a per-survey panel.

**Tech Stack:** Python 3.12, pandas, requests, BeautifulSoup/lxml (all existing dependencies). No new dependencies. No Puppeteer — BLS answers plain HTTP given a User-Agent carrying a contact email, which `BLS_CONTACT_EMAIL` already supplies.

**Spec:** `docs/superpowers/specs/2026-09-13-deep-history-extension-design.md` (decision D6)

## Global Constraints

- **No generic abbreviations.** Never `df`, `res`, `tmp`, `val`. Use `displacement_panel_df`, `archive_html`, `survey_year`.
- **Domain terminology in names**: `survey_year`, `tenure_class`, `displaced_thousands`, `source_table`.
- **Module docstrings required** on every Python file — ruff `D100`.
- Ruff line length **140**; rules `E`, `W`, `F`, `I`, `N`, `D100`. Run ruff only on files you touch, never on `.`.
- Tests: `.venv/bin/python -m pytest tests/ -q`. Currently **304 passed, 6 skipped, 1 xfailed**.
- Run Python through `.venv/bin/python`, not `uv run`.
- **Never modify** `data/raw/`, `seeds/classified_all_tasks.csv`, `seeds/cps_a19_panel.csv`, `seeds/cps_occupation_panel.csv`, `seeds/soc_crosswalks/`.
- **Existing outputs must not change** except where a task explicitly says so. Task 11 verifies this.
- Tests must not hit the network. Archive HTML is committed as a fixture or monkeypatched.
- `download_dws.py` must warn and `exit 0` under CI when a fetch fails, so the pipeline still renders from the seed alone — the existing convention.
- Every new pipeline output gets a `CLAUDE.md` Outputs Reference row in the commit that creates it.
- Commit with `PATH="$PWD/.venv/bin:$PATH"`. Stage explicit paths — **never `git add -A`**, this repo has ~20 untracked files in its root.
- Commit message trailers, exactly:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01XmW2c1TmZUtMwrc9wXueCi
  ```

---

## Verified facts this plan depends on

Checked on 2026-09-14 with `requests` and a `BLS_CONTACT_EMAIL` User-Agent. Do not re-derive; do not assume differently.

| Survey archive | URL (under `https://www.bls.gov/news.release/archives/`) | Status |
|---|---|---|
| 2024 | `disp_08292024.htm` | 200 |
| 2022 | `disp_08262022.htm` | 200 — page title reads "Worker Displacement News Release - 2021 A01 Results" |
| 2020 | `disp_08272020.htm` | 200 |
| 2018 | `disp_08282018.htm` | 200 |
| 2016 | `disp_08252016.htm` | 200 |
| 2014 | `disp_08262014.htm` | 200 |
| 2012 | `disp_08242012.htm` | 200 |
| 2010 | `disp_08262010.htm` | 200 |
| 2008 | `disp_08202008.htm` | 200 |
| 2006 and earlier | not found scanning July/August/September, days 15–31 | — |

Other verified facts:

- **The archives carry their tables inline.** The 2022 archive has 8 `<table>` tags in one page and contains the string `Occupation of lost job`. The *current* release splits the same content across three separate URLs (`disp.t02.htm`, `disp.t05.htm`, `disp.t08.htm`) which `download_dws.py` already fetches. The archive path therefore needs its own table-selection logic; it cannot reuse the three-URL pattern.
- **`pd.read_html` must be handed `io.StringIO(html)`, not a raw HTML string.** Passing the string makes lxml treat it as a filename and raise `OSError: Error reading file '<!DOCTYPE HTML>...'`. This was hit during verification.
- **The current release's Table 5 carries only one survey**, with no prior-survey comparison columns — so history genuinely must come from the archives, not from the live tables.
- `seeds/dws_displacement_panel.csv` currently holds **one survey year (2026)**, 14 rows: 10 from `table_5_occupation` (long_tenured), 3 from `table_2_reason` (long_tenured), 1 from `table_8_all_tenures`. Columns: `survey_year, period_start_year, period_end_year, period_years, source_table, group_name, soc_majors, displaced_thousands, reason, tenure_class`.
- `BLS_CONTACT_EMAIL` is set in `.env`. BLS returns 403 to a User-Agent without one.
- `historical_displacement.py` defaults to `start_year=2005` in four places: lines ~205 (`productivity_displacement_rate`), ~231 (`employment_by_year`), ~297 (`economy_displacement_rate`), ~325 (`build_displacement_rate_table`).
- `PRS85006092` (labor productivity) begins in **1947**, so the productivity-based `D` extends backwards for free.

### The *Monthly Labor Review* series — verified 2026-09-14

The BLS MLR subject index (`https://www.bls.gov/opub/mlr/subject/d.htm`, 200) is the authoritative list of displaced-worker articles. Four matter here; the first three were fetched and parsed during planning:

| Article | URL | Covers | Status |
|---|---|---|---|
| Worker displacement in the mid-1990's (07/1999) | `https://www.bls.gov/opub/mlr/1999/07/art2full.pdf` | Table 2: 1981-82 … 1995-96 | 200, 18 pages, **82,578 characters of real extractable text** |
| Worker displacement in a strong labor market (06/2001) | `https://www.bls.gov/opub/mlr/2001/06/art2full.pdf` | Table 2 extended through 1997-98 | 200 |
| Worker displacement in 1999-2000 (06/2004) | `https://www.bls.gov/opub/mlr/2004/06/art4full.pdf` | 1999-2000 | 200, 95,298 bytes |
| Characteristics of displaced workers 2007-2009 (09/2011) | visual essay | 2007-2009 | not needed — the 2008 and 2010 archives already cover it |

**These are real text PDFs, not scans.** `pdfplumber` extracts them directly; no OCR is required. Verified by extracting the 1999 article in full.

**Table 2 is the table to parse.** Its exact title in the 1999 article is *"Displacement rates of long-tenured workers, by industry, class of worker, and occupation of lost job, 1981–96"*, and its header row is:

```
Characteristic 1981–82 1983–84 1985–86 1987–88 1989–90 1991–92¹ 1993–94¹ 1995–96¹
```

Note the superscript footnote markers glued to some period labels, and that row labels are padded with runs of dots (`Executive, administrative, and managerial.....................`) and sometimes **wrap across two lines**. Both must be handled.

**The occupation block's exact row labels**, verbatim from the 1999 article — the hierarchy is the 1980-census scheme, and indentation is lost in extraction so nesting must be inferred from these known labels rather than from whitespace:

```
White-collar occupations²
  Managerial and professional specialty
    Executive, administrative, and managerial
    Professional specialty
  Technical, sales, and administrative support
    Technicians and related support
    Sales occupations
    Administrative support, including clerical
Service occupations
  Protective services
  Other service occupations
Blue-collar occupations³
  Precision production, craft, and repair
    Mechanics and repairers
    Construction trades
    Other precision production occupations
  Operators, fabricators, and laborers
    Machine operators, assemblers, and inspectors
    ...
```

Only the **leaf** rows are used. Aggregate rows (`White-collar occupations`, `Blue-collar occupations`, `Managerial and professional specialty`, `Technical, sales, and administrative support`, `Precision production, craft, and repair`, `Operators, fabricators, and laborers`) are sums of their own children and would double-count — exactly the leaf-versus-aggregate trap the CPS panel work already hit.

### The documentation this plan corrects

`CLAUDE.md` currently states, as a verified finding:

> The BLS Displaced Worker Supplement news release is a rolling page carrying only the latest biennial survey, and BLS publishes no archive of prior releases — checked 2026-09-12, `/news.release/archives/disp_*.htm` … return 404

The first half is true; **the claim about archives is false.** The original check evidently used wrong release dates — `disp_08252022.htm` does 404, while `disp_08262022.htm` returns 200. Nine archives exist. Task 6 corrects this, and the correction matters beyond this plan: the same false premise shaped the demand-composition plan's decision to proceed with a single survey.

---

## What this plan delivers, and what it does not

**Delivers:** the DWS panel back to **2008** — nine archived surveys plus the current one, ten in total. `composition_displacement_validation.py` goes from a single n=10 cross-section to ten of them, which is the point: `CLAUDE.md` calls that file *"the only validation in the project that compares a modeled quantity against a direct measurement of that same quantity"*, and it currently rests on one survey reporting a null (Pearson +0.220, Spearman +0.600).

**Also delivers the pre-2008 history, from the *Monthly Labor Review* article series** (Tasks 7-10). That data is different in kind and is kept distinguishable rather than blended: it is published as displacement **rates in percent**, not counts in thousands, and on the **1980-census occupational taxonomy**, not the ten modern groups. Both differences are carried explicitly in the panel and handled by an auditable crosswalk.

**Combined coverage after this plan:**

| Source | Survey periods | Basis |
|---|---|---|
| MLR 1999 article | 1981-82 … 1995-96 (8 periods) | rates, 1980-census taxonomy |
| MLR 2001 article | 1997-98 (1 period) | rates, 1980-census taxonomy |
| MLR 2004 article | 1999-2000 (1 period) | rates, 1980-census taxonomy |
| **gap** | **2001-02 and 2003-04** | **unrecoverable — see below** |
| News-release archives | 2005-07 … 2021-23 (9 surveys) | counts, modern ten groups |
| Current release | 2023-25 | counts, modern ten groups |

**The one remaining gap is the 2002 and 2004 surveys**, covering roughly 2001-2004. Archives for those years do not exist — probed every day of July, August, September and December for 2000, 2002, 2004 and 2006, all 404 — and the MLR series skips them: the subject index at `https://www.bls.gov/opub/mlr/subject/d.htm` lists no displacement article between June 2004 (covering 1999-2000) and September 2011 (a visual essay covering 2007-2009, a period the archives already supply). That gap is a property of what BLS published, not a shortcut taken here.

The **productivity-based `D`** reaches back arbitrarily far regardless (`PRS85006092` starts 1947), so `D`'s time variation is extended fully by Task 5.

A further caveat that bounds any pre-1994 extension: the DWS recall window is **five years before 1994 and three years after**, and `dws_displacement_rate` hardcodes a `/3` annualisation. Every survey this plan recovers (2008–2026) is on the 3-year window, so the hardcode stays correct — but Task 4 makes it explicit rather than incidental, so a future pre-1994 extension cannot silently inherit it.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `download_dws.py` | Modify | Add archived-release fetching beside the current-release path |
| `dws_panel.py` | Modify | Parse archive pages (inline tables) into the existing panel schema |
| `seeds/dws_displacement_panel.csv` | Modify | Accumulates from 1 survey to 10 |
| `historical_displacement.py` | Modify | Widen year defaults; make the recall-window assumption explicit |
| `composition_displacement_validation.py` | Modify | Per-survey panel instead of a single cross-section |
| `tests/test_dws_panel.py` | Modify | Archive parsing |
| `tests/test_historical_displacement.py` | Modify | Widened ranges, recall window |
| `tests/test_composition_displacement_validation.py` | Modify | Per-survey panel |
| `mlr_displacement.py` | Create | Parse MLR article PDFs; crosswalk the 1980-census taxonomy |
| `seeds/mlr_occupation_crosswalk.csv` | Create | Committed 1980-census → ten-group crosswalk, with confidence flags |
| `tests/test_mlr_displacement.py` | Create | PDF parsing and crosswalk coverage |
| `pyproject.toml`, `uv.lock` | Modify | Add `pdfplumber`; CI runs `uv sync --locked` so the lock must travel with it |
| `docs/charts/dws_observed_vs_predicted_displacement.md`, `CLAUDE.md`, `docs/framework.md` | Modify | Results, outputs rows, the archive correction, and the MLR caveats |

---

### Task 1: Fetch the nine archived releases

**Files:**
- Modify: `download_dws.py`
- Test: `tests/test_dws_panel.py`

**Interfaces:**
- Produces:
  - `ARCHIVE_RELEASE_URLS: dict[int, str]` — survey year → archive URL
  - `download_archived_releases(request_headers: dict[str, str], output_dir: str = "data/raw/dws/archives") -> list[str]` — returns paths written

- [ ] **Step 1: Write the failing test**

Append to `tests/test_dws_panel.py`:

```python
class TestArchiveUrls:
    def test_nine_archived_surveys_are_listed(self):
        from download_dws import ARCHIVE_RELEASE_URLS

        assert sorted(ARCHIVE_RELEASE_URLS) == [2008, 2010, 2012, 2014, 2016, 2018, 2020, 2022, 2024]

    def test_urls_use_the_verified_release_dates(self):
        from download_dws import ARCHIVE_RELEASE_URLS

        assert ARCHIVE_RELEASE_URLS[2022].endswith("disp_08262022.htm")
        assert ARCHIVE_RELEASE_URLS[2008].endswith("disp_08202008.htm")

    def test_every_url_is_under_the_archive_path(self):
        from download_dws import ARCHIVE_RELEASE_URLS

        assert all("/news.release/archives/" in url for url in ARCHIVE_RELEASE_URLS.values())
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_dws_panel.py::TestArchiveUrls -v`
Expected: FAIL with `ImportError: cannot import name 'ARCHIVE_RELEASE_URLS'`.

- [ ] **Step 3: Implement**

Add to `download_dws.py`. The module does **not** currently import `warnings`, so add `import warnings` beside its existing `import os` / `import sys`:

```python
ARCHIVE_DIR = "data/raw/dws/archives"

# Verified reachable 2026-09-14. The release day differs per survey and a wrong
# day 404s, which is how an earlier check concluded no archive existed at all:
# disp_08252022.htm is a 404 while disp_08262022.htm is the real 2022 release.
ARCHIVE_RELEASE_URLS: dict[int, str] = {
    2008: "https://www.bls.gov/news.release/archives/disp_08202008.htm",
    2010: "https://www.bls.gov/news.release/archives/disp_08262010.htm",
    2012: "https://www.bls.gov/news.release/archives/disp_08242012.htm",
    2014: "https://www.bls.gov/news.release/archives/disp_08262014.htm",
    2016: "https://www.bls.gov/news.release/archives/disp_08252016.htm",
    2018: "https://www.bls.gov/news.release/archives/disp_08282018.htm",
    2020: "https://www.bls.gov/news.release/archives/disp_08272020.htm",
    2022: "https://www.bls.gov/news.release/archives/disp_08262022.htm",
    2024: "https://www.bls.gov/news.release/archives/disp_08292024.htm",
}


def download_archived_releases(request_headers: dict[str, str], output_dir: str = ARCHIVE_DIR) -> list[str]:
    """Fetch every archived Worker Displacement release, skipping any already on disk.

    Unlike the current release, an archive carries all of its tables inline in a
    single page, so one file per survey year is the whole payload. A survey that
    cannot be fetched is warned about and skipped rather than failing the run —
    the committed seed already holds whatever was parsed previously.
    """
    os.makedirs(output_dir, exist_ok=True)
    written_paths = []
    for survey_year, url in sorted(ARCHIVE_RELEASE_URLS.items()):
        destination = os.path.join(output_dir, f"disp_{survey_year}.html")
        if os.path.exists(destination):
            written_paths.append(destination)
            continue
        try:
            response = requests.get(url, headers=request_headers, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
        except requests.RequestException as request_error:
            warnings.warn(f"Could not fetch the {survey_year} DWS archive: {request_error}", stacklevel=2)
            continue
        with open(destination, "w", encoding="utf-8") as archive_file:
            archive_file.write(response.text)
        written_paths.append(destination)
    return written_paths
```

Call it from `download_dws.py`'s `main()` alongside the existing current-release download, and keep the existing warn-and-`exit 0`-under-CI behaviour.

- [ ] **Step 4: Run to verify passing**

Run: `.venv/bin/python -m pytest tests/test_dws_panel.py -v`
Expected: PASS.

- [ ] **Step 5: Do the real fetch**

```bash
.venv/bin/python download_dws.py
ls -la data/raw/dws/archives/
```

Expected: nine files, `disp_2008.html` … `disp_2024.html`, each tens of kilobytes. A missing file means that survey's fetch failed — report it, do not silently proceed with eight.

- [ ] **Step 6: Lint and commit**

```bash
.venv/bin/ruff check download_dws.py tests/test_dws_panel.py
.venv/bin/ruff format download_dws.py tests/test_dws_panel.py
git add download_dws.py tests/test_dws_panel.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "$(cat <<'EOF'
Fetch the archived Worker Displacement releases

BLS does publish DWS archives; the project's docs say otherwise because an
earlier check used wrong release dates. Nine biennial archives from 2008 to
2024 are reachable, each carrying its tables inline in one page.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XmW2c1TmZUtMwrc9wXueCi
EOF
)"
```

---

### Task 2: Parse archived releases into the panel schema

**Files:**
- Modify: `dws_panel.py`
- Test: `tests/test_dws_panel.py`

**Interfaces:**
- Consumes: `download_archived_releases` output paths from Task 1.
- Produces: `parse_archived_release(archive_html: str, survey_year: int) -> pd.DataFrame` — same columns as the existing panel: `survey_year, period_start_year, period_end_year, period_years, source_table, group_name, soc_majors, displaced_thousands, reason, tenure_class`.

The archive carries ~8 inline tables; the current release splits the same content across three files. Select tables by their content, not by position — table ordering is not guaranteed stable across sixteen years of releases.

- [ ] **Step 1: Save a fixture**

```bash
mkdir -p tests/fixtures
cp data/raw/dws/archives/disp_2022.html tests/fixtures/dws_archive_2022.html
```

Commit the fixture: tests must not hit the network, and this is the only way to test archive parsing offline.

- [ ] **Step 2: Write the failing test**

```python
class TestArchiveParsing:
    @staticmethod
    def _fixture_html():
        with open("tests/fixtures/dws_archive_2022.html", encoding="utf-8") as fixture_file:
            return fixture_file.read()

    def test_ten_leaf_occupation_rows_are_extracted(self):
        from dws_panel import parse_archived_release

        panel_df = parse_archived_release(self._fixture_html(), 2022)
        occupation_rows = panel_df[panel_df["source_table"] == "table_5_occupation"]
        assert len(occupation_rows) == 10

    def test_occupation_group_names_match_the_soc_mapping(self):
        from dws_panel import DWS_TO_SOC_MAJOR, parse_archived_release

        panel_df = parse_archived_release(self._fixture_html(), 2022)
        occupation_rows = panel_df[panel_df["source_table"] == "table_5_occupation"]
        assert set(occupation_rows["group_name"]) == set(DWS_TO_SOC_MAJOR)

    def test_survey_year_is_stamped_on_every_row(self):
        from dws_panel import parse_archived_release

        panel_df = parse_archived_release(self._fixture_html(), 2022)
        assert (panel_df["survey_year"] == 2022).all()

    def test_suppressed_dashes_become_nan_not_zero(self):
        from dws_panel import parse_archived_release

        panel_df = parse_archived_release(self._fixture_html(), 2022)
        assert (panel_df["displaced_thousands"].dropna() > 0).all()

    def test_columns_match_the_existing_panel_schema(self):
        from dws_panel import parse_archived_release

        expected = {
            "survey_year",
            "period_start_year",
            "period_end_year",
            "period_years",
            "source_table",
            "group_name",
            "soc_majors",
            "displaced_thousands",
            "reason",
            "tenure_class",
        }
        assert set(parse_archived_release(self._fixture_html(), 2022).columns) == expected
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_dws_panel.py::TestArchiveParsing -v`
Expected: FAIL with `ImportError: cannot import name 'parse_archived_release'`.

- [ ] **Step 4: Implement**

Add to `dws_panel.py`. Note the `io.StringIO` wrapper — passing a raw HTML string makes lxml treat it as a filename and raise `OSError: Error reading file '<!DOCTYPE HTML>...'`:

```python
def _select_table_by_heading(archive_html: str, heading_text: str) -> pd.DataFrame | None:
    """The inline table whose first column header contains heading_text, or None.

    Archived releases carry every table in one page and the ordering is not
    guaranteed stable across sixteen years of releases, so tables are selected by
    what they contain rather than by index. _flatten_columns is the module's
    existing helper for these two-row headers and returns a frame with single
    lowercased column labels, so the match is against an already-flattened name.
    """
    for candidate_df in pd.read_html(io.StringIO(archive_html)):
        flattened_df = _flatten_columns(candidate_df)
        if heading_text.lower() in str(flattened_df.columns[0]).lower():
            return flattened_df
    return None


def parse_archived_release(archive_html: str, survey_year: int) -> pd.DataFrame:
    """Every panel row this archived release can supply, in the committed panel's schema.

    Mirrors the current-release parser's output exactly so the two accumulate into
    one seed: leaf occupation rows from the occupation table, the three reason
    rows, and the all-tenures total.
    """
    parsed_rows: list[dict[str, object]] = []
    occupation_table = _select_table_by_heading(archive_html, "Occupation of lost job")
    if occupation_table is not None:
        parsed_rows.extend(_occupation_rows(occupation_table, survey_year))
    reason_table = _select_table_by_heading(archive_html, "Reason for job loss")
    if reason_table is not None:
        parsed_rows.extend(_reason_rows(reason_table, survey_year))
    return pd.DataFrame(parsed_rows, columns=PANEL_COLUMNS)
```

Reuse the existing row-building helpers the current-release parser already uses for leaf selection, dash-to-NaN handling, and `soc_majors` lookup — extract them into `_occupation_rows` / `_reason_rows` if they are currently inline, so both paths share one implementation. Add `import io` at the top of the module.

`_flatten_columns` already exists in `dws_panel.py` (line 113) and collapses these tables' two-row headers into single lowercased labels — reuse it rather than writing a second header-flattener.

- [ ] **Step 5: Run to verify passing**

Run: `.venv/bin/python -m pytest tests/test_dws_panel.py -v`
Expected: PASS.

- [ ] **Step 6: Parse all nine archives and rebuild the seed**

```bash
.venv/bin/python -c "
import pandas as pd
from dws_panel import parse_archived_release, SEED_PANEL_PATH
from download_dws import ARCHIVE_RELEASE_URLS
frames = [pd.read_csv(SEED_PANEL_PATH)]
for survey_year in sorted(ARCHIVE_RELEASE_URLS):
    with open(f'data/raw/dws/archives/disp_{survey_year}.html', encoding='utf-8') as handle:
        frames.append(parse_archived_release(handle.read(), survey_year))
panel_df = pd.concat(frames, ignore_index=True).drop_duplicates(subset=['survey_year','source_table','group_name','reason'], keep='last')
panel_df = panel_df.sort_values(['survey_year','source_table','group_name']).reset_index(drop=True)
panel_df.to_csv(SEED_PANEL_PATH, index=False)
print('surveys:', sorted(panel_df.survey_year.unique()))
print('rows:', len(panel_df))
print(panel_df.groupby('source_table').size().to_dict())
"
```

Expected: ten survey years (2008–2026), roughly 140 rows, with ~100 `table_5_occupation` rows. Fewer than ten surveys means a parse silently produced nothing — investigate rather than accept.

- [ ] **Step 7: Sanity-check the magnitudes**

```bash
.venv/bin/python -c "
import pandas as pd
panel_df = pd.read_csv('seeds/dws_displacement_panel.csv')
totals = panel_df[panel_df.source_table=='table_5_occupation'].groupby('survey_year').displaced_thousands.sum()
print(totals.to_string())
"
```

Expected: totals in the low thousands (thousands of workers, so ~2,000–10,000 each), with the 2010 and 2012 surveys — covering the financial crisis — visibly higher than the 2018–2026 ones. A survey whose total is an order of magnitude off the others indicates a parse that picked up percentages instead of counts. Report the table.

- [ ] **Step 8: Lint and commit**

```bash
.venv/bin/ruff check dws_panel.py tests/test_dws_panel.py
.venv/bin/ruff format dws_panel.py tests/test_dws_panel.py
git add dws_panel.py tests/test_dws_panel.py tests/fixtures/dws_archive_2022.html seeds/dws_displacement_panel.csv
PATH="$PWD/.venv/bin:$PATH" git commit -m "$(cat <<'EOF'
Parse archived DWS releases into the displacement panel

Takes the committed panel from one survey to ten (2008-2026). Archived
releases carry their tables inline rather than split across three URLs, and
table order is not stable across sixteen years, so tables are selected by
their heading text rather than by index.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XmW2c1TmZUtMwrc9wXueCi
EOF
)"
```

---

### Task 3: Turn the displacement validation into a per-survey panel

This is the task the plan exists for. `composition_displacement_validation.py` is, by its own docstring, *"the only validation in the project that compares a modeled quantity against a direct measurement of that same quantity"* — employment growth never enters, so circularity is structurally impossible. It currently runs one cross-section over ten occupation groups and reports a null.

**Files:**
- Modify: `composition_displacement_validation.py`
- Test: `tests/test_composition_displacement_validation.py`

**Interfaces:**
- Produces:
  - `build_displacement_comparison_panel(displacement_panel_df: pd.DataFrame) -> pd.DataFrame | None` — one row per (survey_year, model) with `survey_year, model, pearson_r, pearson_p, spearman_r, spearman_p, n_groups`
  - `PANEL_OUTPUT_PATH = "data/output/composition_model_displacement_validation_panel.csv"`

- [ ] **Step 1: Write the failing test**

```python
class TestDisplacementPanel:
    @staticmethod
    def _multi_survey_panel():
        from composition_displacement_validation import soc_major_to_dws_group

        groups = sorted(set(soc_major_to_dws_group().values()))
        rows = []
        for survey_year in (2018, 2020, 2022):
            for index, group in enumerate(groups):
                rows.append(
                    {
                        "survey_year": survey_year,
                        "source_table": "table_5_occupation",
                        "group_name": group,
                        "displaced_thousands": 100.0 + index * 10,
                        "tenure_class": "long_tenured",
                        "reason": None,
                    }
                )
        return pd.DataFrame(rows)

    def test_one_row_per_survey_and_model(self):
        from composition_displacement_validation import build_displacement_comparison_panel

        panel_df = build_displacement_comparison_panel(self._multi_survey_panel())
        assert set(panel_df["survey_year"]) == {2018, 2020, 2022}
        assert panel_df.groupby("survey_year")["model"].nunique().eq(2).all()

    def test_n_groups_counts_groups_not_rows(self):
        from composition_displacement_validation import build_displacement_comparison_panel

        panel_df = build_displacement_comparison_panel(self._multi_survey_panel())
        assert (panel_df["n_groups"] == 10).all()

    def test_a_survey_with_too_few_groups_is_skipped(self):
        from composition_displacement_validation import build_displacement_comparison_panel

        thin_df = self._multi_survey_panel()
        thin_df = thin_df[~((thin_df.survey_year == 2018) & (thin_df.group_name != "service occupations"))]
        panel_df = build_displacement_comparison_panel(thin_df)
        assert 2018 not in set(panel_df["survey_year"])

    def test_both_models_are_scored(self):
        from composition_displacement_validation import build_displacement_comparison_panel

        panel_df = build_displacement_comparison_panel(self._multi_survey_panel())
        assert set(panel_df["model"]) == {"composition", "dynamic"}
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_composition_displacement_validation.py::TestDisplacementPanel -v`
Expected: FAIL with `ImportError: cannot import name 'build_displacement_comparison_panel'`.

- [ ] **Step 3: Implement**

Wrap the existing single-survey comparison in a loop over `survey_year`, reusing `observed_displacement_by_group` (which already accepts a `survey_year` argument) and `predicted_displacement_by_group` unchanged. Skip a survey with fewer than `MINIMUM_GROUPS` groups carrying a non-null count, so a suppressed-heavy survey cannot produce a two-point correlation. `MINIMUM_GROUPS = 5` already exists in this module (line 79) and governs the single-survey path — reuse it rather than introducing a second threshold for the same idea. Report Pearson and Spearman for each of the two models.

Keep the existing single-survey output and chart exactly as they are — the newest survey remains the headline; the panel is additional evidence beside it, not a replacement.

- [ ] **Step 4: Run to verify passing**

Run: `.venv/bin/python -m pytest tests/test_composition_displacement_validation.py -v`
Expected: PASS.

- [ ] **Step 5: Run it and report the panel**

```bash
MPLCONFIGDIR=/tmp/claude-1000/mpl .venv/bin/python main.py composition > /tmp/claude-1000/dws.log 2>&1; echo "exit: $?"
cat data/output/composition_model_displacement_validation_panel.csv
```

**Report the per-survey correlations plainly.** The project's reading rule is asymmetric — a positive result is strong because the 2025-derived demand-type labels are anachronistic and work against it; a null is uninformative rather than disconfirming. Ten surveys of nulls is still a null. Do not average the r values naively either: say how many surveys are individually significant at n=10 (which needs r ≈ 0.63), and report the range.

- [ ] **Step 6: Lint and commit**

```bash
.venv/bin/ruff check composition_displacement_validation.py tests/test_composition_displacement_validation.py
.venv/bin/ruff format composition_displacement_validation.py tests/test_composition_displacement_validation.py
git add composition_displacement_validation.py tests/test_composition_displacement_validation.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "$(cat <<'EOF'
Score predicted displacement against every DWS survey, not just the latest

Replace this line with the per-survey r range and how many of the ten
surveys clear the n=10 significance bar.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XmW2c1TmZUtMwrc9wXueCi
EOF
)"
```

---

### Task 4: Make the recall-window assumption explicit

`dws_displacement_rate` divides by 3 to annualise a three-year lookback. That is correct for every survey this plan recovers, but the DWS used a **five-year** recall before 1994, and a future pre-1994 extension would silently inherit the wrong divisor.

**Files:**
- Modify: `historical_displacement.py`
- Test: `tests/test_historical_displacement.py`

**Interfaces:**
- Produces: `RECALL_WINDOW_CHANGE_YEAR = 1994`; `recall_window_years(survey_year: int) -> int`

- [ ] **Step 1: Write the failing test**

```python
class TestRecallWindow:
    def test_modern_surveys_use_a_three_year_window(self):
        from historical_displacement import recall_window_years

        assert recall_window_years(2008) == 3
        assert recall_window_years(2026) == 3

    def test_pre_1994_surveys_use_a_five_year_window(self):
        from historical_displacement import recall_window_years

        assert recall_window_years(1992) == 5
        assert recall_window_years(1984) == 5

    def test_the_boundary_year_itself_is_three(self):
        from historical_displacement import recall_window_years

        assert recall_window_years(1994) == 3
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_historical_displacement.py::TestRecallWindow -v`
Expected: FAIL with `ImportError: cannot import name 'recall_window_years'`.

- [ ] **Step 3: Implement**

```python
# The DWS asked about displacement over the previous five years through the 1992
# survey and three years from 1994 on. Every survey currently in the panel is on
# the three-year window; this exists so a pre-1994 extension cannot inherit the
# wrong divisor by accident.
RECALL_WINDOW_CHANGE_YEAR = 1994


def recall_window_years(survey_year: int) -> int:
    """Years of displacement a given DWS survey asked about."""
    return 3 if survey_year >= RECALL_WINDOW_CHANGE_YEAR else 5
```

Use it in `dws_displacement_rate` in place of the hardcoded `/ 3`, keyed on each row's `survey_year`.

- [ ] **Step 4: Run to verify passing and confirm no numeric change**

Run: `.venv/bin/python -m pytest tests/test_historical_displacement.py -v`
Expected: PASS. Because every panel survey is ≥ 1994, `historical_displacement_rate.csv` must be **unchanged** — verify that explicitly and report it.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/ruff check historical_displacement.py tests/test_historical_displacement.py
.venv/bin/ruff format historical_displacement.py tests/test_historical_displacement.py
git add historical_displacement.py tests/test_historical_displacement.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "$(cat <<'EOF'
Key the DWS annualisation to each survey's recall window

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XmW2c1TmZUtMwrc9wXueCi
EOF
)"
```

---

### Task 5: Widen `D`'s year range

**Files:**
- Modify: `historical_displacement.py`
- Test: `tests/test_historical_displacement.py`

`historical_displacement.py` defaults to `start_year=2005` in four places. The employment series and the CPS/OEWS instruments now reach back to 1983 and 1999 respectively, so `D` is the remaining constraint on time variation. `PRS85006092` begins in 1947, so the productivity source extends for free.

- [ ] **Step 1: Write the failing test**

```python
class TestWidenedRange:
    def test_default_start_year_reaches_the_dws_panel(self):
        import historical_displacement

        assert historical_displacement.DEFAULT_START_YEAR == 1984

    def test_productivity_rate_accepts_the_widened_range(self, monkeypatch):
        import historical_displacement

        captured_years = {}

        def fake_fetch(series_id, start_year, end_year):
            captured_years["start"] = start_year
            return pd.Series({year: 2.0 for year in range(start_year, end_year + 1)})

        monkeypatch.setattr(historical_displacement, "fetch_annual_means", fake_fetch)
        historical_displacement.productivity_displacement_rate(start_year=1984, end_year=2025)
        assert captured_years["start"] == 1984
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_historical_displacement.py::TestWidenedRange -v`
Expected: FAIL with `AttributeError: module 'historical_displacement' has no attribute 'DEFAULT_START_YEAR'`.

- [ ] **Step 3: Implement**

Introduce `DEFAULT_START_YEAR = 1984` and use it as the default in `productivity_displacement_rate`, `employment_by_year`, `economy_displacement_rate` and `build_displacement_rate_table`, replacing the four separate `2005` literals. Keep `end_year` as it is.

**Watch the API budget.** `fetch_annual_means` chunks at 10 years unregistered and 20 registered, and a cold CI cache plus the CPS instrument's own fetch already competes for the same daily quota — this is the failure that shipped in the previous plan and had to be fixed. Widening from 2005 to 1984 adds roughly two chunks per series. Note the new total in your report.

- [ ] **Step 4: Run and confirm what moved**

Run: `.venv/bin/python -m pytest tests/ -q`, then regenerate and inspect:

```bash
MPLCONFIGDIR=/tmp/claude-1000/mpl .venv/bin/python main.py composition > /tmp/claude-1000/d.log 2>&1; echo "exit: $?"
.venv/bin/python -c "
import pandas as pd
rate_df = pd.read_csv('data/output/historical_displacement_rate.csv')
print(rate_df.groupby('source').year.agg(['min','max','count']).to_string())
"
```

Expected: the `productivity` source now spans 1984 onward; the DWS sources span the surveys actually in the panel. Report both ranges.

**`D` cancels out of every cross-sectional correlation** — `docs/framework.md` proves this and the demand-composition plan verified it numerically — so widening `D` must **not** change any correlation. Confirm `composition_model_era_comparison.csv` and `composition_cycle_decomposition.csv` are unchanged, and report it. A moved correlation means something reads `D` that should not.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/ruff check historical_displacement.py tests/test_historical_displacement.py
.venv/bin/ruff format historical_displacement.py tests/test_historical_displacement.py
git add historical_displacement.py tests/test_historical_displacement.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "$(cat <<'EOF'
Widen the displacement rate's default range to 1984

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XmW2c1TmZUtMwrc9wXueCi
EOF
)"
```

---

### Task 6: Documentation for the archive path, including the archive correction

This task covers the archive work only. The MLR path's documentation lands in Task 10 Step 6, because its results do not exist until then.

**Files:**
- Modify: `CLAUDE.md`, `docs/framework.md`, `docs/charts/dws_observed_vs_predicted_displacement.md`

- [ ] **Step 1: Correct the false archive claim in `CLAUDE.md`**

The Release Pipeline section states that BLS "publishes no archive of prior releases — checked 2026-09-12, `/news.release/archives/disp_*.htm` … return 404". Replace it with what is actually true: nine biennial archives from 2008 to 2024 are reachable at `disp_MMDDYYYY.htm`, the release day differs per survey, and a wrong day 404s — which is how the original check reached the opposite conclusion. Keep the accurate half: the *current* release page is still rolling and carries only the latest survey.

State plainly that this correction matters beyond the panel: the same false premise shaped the demand-composition plan's decision to proceed with a single survey.

- [ ] **Step 2: Add the Outputs Reference row**

For `composition_model_displacement_validation_panel.csv`, describing it as the per-survey version of the project's only non-circular validation, and noting that at n=10 groups a survey needs r ≈ 0.63 to be individually significant.

- [ ] **Step 3: Update the chart doc**

`docs/charts/dws_observed_vs_predicted_displacement.md` currently describes a single survey and quotes "Null at n=10 (composition Pearson +0.220, Spearman +0.600)". Add the panel result beside it with the real measured numbers from Task 3, keeping the single-survey headline as the chart's own subject.

- [ ] **Step 4: Record the scope gap in `docs/framework.md`**

One or two sentences: the DWS panel reaches 2008, not the spec's 1984; the productivity-based `D` does reach 1984; pre-2008 DWS recovery would need the *Monthly Labor Review* articles (verified reachable, PDF, and leaving a gap between roughly 1997 and 2007) and is a named follow-on.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/
PATH="$PWD/.venv/bin:$PATH" git commit -m "$(cat <<'EOF'
Correct the DWS archive claim and document the survey panel

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XmW2c1TmZUtMwrc9wXueCi
EOF
)"
```

---

### Task 7: Add the PDF parser and fetch the MLR articles

**Files:**
- Modify: `pyproject.toml`, `uv.lock`, `download_dws.py`
- Test: `tests/test_dws_panel.py`

**Interfaces:**
- Produces: `MLR_ARTICLE_URLS: dict[str, str]` — article key → URL; `download_mlr_articles(request_headers, output_dir="data/raw/dws/mlr") -> list[str]`

- [ ] **Step 1: Add the dependency**

```bash
UV_CACHE_DIR="${TMPDIR:-/tmp/claude-1000}/uv-cache" uv add pdfplumber
```

`pdfplumber` (verified working at 0.11.10) is chosen over `pypdf` because it preserves the visual row structure these numeric tables depend on. **CI runs `uv sync --locked`**, so `uv.lock` must be regenerated and committed in this same commit or CI fails at install rather than at test time.

- [ ] **Step 2: Write the failing test**

```python
class TestMlrArticleUrls:
    def test_three_articles_cover_the_pre_2008_window(self):
        from download_dws import MLR_ARTICLE_URLS

        assert set(MLR_ARTICLE_URLS) == {"mid_1990s_1999", "strong_labor_market_2001", "displacement_1999_2000_2004"}

    def test_urls_point_at_the_verified_pdfs(self):
        from download_dws import MLR_ARTICLE_URLS

        assert MLR_ARTICLE_URLS["mid_1990s_1999"].endswith("/opub/mlr/1999/07/art2full.pdf")
        assert MLR_ARTICLE_URLS["displacement_1999_2000_2004"].endswith("/opub/mlr/2004/06/art4full.pdf")
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_dws_panel.py::TestMlrArticleUrls -v`
Expected: FAIL with `ImportError: cannot import name 'MLR_ARTICLE_URLS'`.

- [ ] **Step 4: Implement**

```python
MLR_DIR = "data/raw/dws/mlr"

# The Monthly Labor Review displaced-worker series, from the BLS subject index at
# https://www.bls.gov/opub/mlr/subject/d.htm. These carry the pre-2008 history the
# news-release archives do not reach. All three verified reachable 2026-09-14.
MLR_ARTICLE_URLS: dict[str, str] = {
    "mid_1990s_1999": "https://www.bls.gov/opub/mlr/1999/07/art2full.pdf",
    "strong_labor_market_2001": "https://www.bls.gov/opub/mlr/2001/06/art2full.pdf",
    "displacement_1999_2000_2004": "https://www.bls.gov/opub/mlr/2004/06/art4full.pdf",
}


def download_mlr_articles(request_headers: dict[str, str], output_dir: str = MLR_DIR) -> list[str]:
    """Fetch the MLR displaced-worker articles, skipping any already on disk.

    Warns and skips on failure rather than raising, matching how every other
    download in this module degrades so the pipeline still renders from the seed.
    """
    os.makedirs(output_dir, exist_ok=True)
    written_paths = []
    for article_key, url in sorted(MLR_ARTICLE_URLS.items()):
        destination = os.path.join(output_dir, f"{article_key}.pdf")
        if os.path.exists(destination):
            written_paths.append(destination)
            continue
        try:
            response = requests.get(url, headers=request_headers, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
        except requests.RequestException as request_error:
            warnings.warn(f"Could not fetch MLR article {article_key}: {request_error}", stacklevel=2)
            continue
        with open(destination, "wb") as article_file:
            article_file.write(response.content)
        written_paths.append(destination)
    return written_paths
```

Call it from `main()` beside the archive download.

- [ ] **Step 5: Run the tests and the real fetch**

```bash
.venv/bin/python -m pytest tests/test_dws_panel.py -v
.venv/bin/python download_dws.py
ls -la data/raw/dws/mlr/
```

Expected: three PDFs, roughly 95 KB, 123 KB and 95 KB.

- [ ] **Step 6: Lint and commit**

```bash
.venv/bin/ruff check download_dws.py tests/test_dws_panel.py
.venv/bin/ruff format download_dws.py tests/test_dws_panel.py
git add pyproject.toml uv.lock download_dws.py tests/test_dws_panel.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "$(cat <<'EOF'
Fetch the Monthly Labor Review displaced-worker articles

Adds pdfplumber and pulls the three MLR articles carrying the pre-2008
history the news-release archives do not reach. They are real text PDFs,
not scans, so no OCR is needed.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XmW2c1TmZUtMwrc9wXueCi
EOF
)"
```

---

### Task 8: Parse MLR Table 2 into per-period occupation rates

**Files:**
- Create: `mlr_displacement.py`
- Test: `tests/test_mlr_displacement.py`

A new module rather than more weight in `dws_panel.py`: the MLR path has a different input format (PDF), a different unit (rates), and a different taxonomy, and those three differences deserve their own file with one clear responsibility.

**Interfaces:**
- Produces:
  - `MLR_OCCUPATION_LEAVES: tuple[str, ...]` — the leaf row labels to keep
  - `parse_displacement_rate_table(article_pdf_path: str) -> pd.DataFrame` — columns `period_label, period_start_year, period_end_year, mlr_occupation, displacement_rate_percent`

- [ ] **Step 1: Write the failing test**

Tests must not hit the network, and a PDF fixture is large — parse the already-downloaded article from `data/raw/dws/mlr/` and skip when absent, following `tests/test_harmonize_soc.py`'s `RAW_BLS_PRESENT` pattern:

```python
"""Tests for mlr_displacement.py — parsing displacement rates out of the MLR article PDFs."""

import os

import pandas as pd
import pytest

from mlr_displacement import MLR_OCCUPATION_LEAVES, parse_displacement_rate_table

ARTICLE_PATH = "data/raw/dws/mlr/mid_1990s_1999.pdf"
ARTICLE_PRESENT = os.path.exists(ARTICLE_PATH)


class TestLeafSelection:
    def test_aggregate_rows_are_not_leaves(self):
        """Aggregates are sums of their own children; including them double-counts."""
        for aggregate in (
            "White-collar occupations",
            "Blue-collar occupations",
            "Managerial and professional specialty",
            "Technical, sales, and administrative support",
            "Precision production, craft, and repair",
            "Operators, fabricators, and laborers",
        ):
            assert aggregate not in MLR_OCCUPATION_LEAVES

    def test_known_leaves_are_present(self):
        for leaf in ("Executive, administrative, and managerial", "Sales occupations", "Construction trades"):
            assert leaf in MLR_OCCUPATION_LEAVES


@pytest.mark.skipif(not ARTICLE_PRESENT, reason="MLR article not downloaded; run download_dws.py")
class TestRateTableParsing:
    def test_eight_periods_are_recovered(self):
        rate_df = parse_displacement_rate_table(ARTICLE_PATH)
        assert sorted(rate_df["period_label"].unique()) == [
            "1981-82",
            "1983-84",
            "1985-86",
            "1987-88",
            "1989-90",
            "1991-92",
            "1993-94",
            "1995-96",
        ]

    def test_period_years_are_parsed_as_four_digit_integers(self):
        rate_df = parse_displacement_rate_table(ARTICLE_PATH)
        first = rate_df[rate_df["period_label"] == "1995-96"].iloc[0]
        assert first["period_start_year"] == 1995
        assert first["period_end_year"] == 1996

    def test_a_known_published_value_is_recovered_exactly(self):
        """Sales occupations, 1981-82, is published as 3.7 percent."""
        rate_df = parse_displacement_rate_table(ARTICLE_PATH)
        row = rate_df[(rate_df.mlr_occupation == "Sales occupations") & (rate_df.period_label == "1981-82")]
        assert row["displacement_rate_percent"].iloc[0] == pytest.approx(3.7)

    def test_leading_decimal_values_are_parsed(self):
        """BLS prints values below one without a leading zero, e.g. Protective services 1985-86 is '.5'."""
        rate_df = parse_displacement_rate_table(ARTICLE_PATH)
        row = rate_df[(rate_df.mlr_occupation == "Protective services") & (rate_df.period_label == "1985-86")]
        assert row["displacement_rate_percent"].iloc[0] == pytest.approx(0.5)

    def test_every_leaf_appears_in_every_period(self):
        rate_df = parse_displacement_rate_table(ARTICLE_PATH)
        counts = rate_df.groupby("mlr_occupation")["period_label"].nunique()
        assert (counts == 8).all()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_mlr_displacement.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mlr_displacement'`.

- [ ] **Step 3: Implement**

Create `mlr_displacement.py` with a module docstring naming its purpose, inputs and outputs. The parser must handle four things the verification exposed:

1. **Dot leaders.** Row labels are padded with runs of `.` before the numbers — strip with `re.sub(r"\.{2,}", " ", line)`.
2. **Wrapped labels.** Some labels break across two lines, with the numbers on the second (`Executive, administrative, and\nmanagerial..... 2.5 2.4 ...`). Join a line carrying no numbers to the line that follows it.
3. **Superscript footnote markers** glued to labels and period headers (`White-collar occupations²`, `1991–92¹`) — strip non-ASCII digit superscripts and trailing digits that are not part of a year.
4. **Leading-decimal values.** BLS prints values below one as `.5`, not `0.5`; `float(".5")` works, but a regex requiring a leading digit would miss them. Match numbers as `r"\.?\d+(?:\.\d+)?"`.

Select rows by exact membership in `MLR_OCCUPATION_LEAVES` rather than by position or indentation — extraction discards leading whitespace, so nesting cannot be inferred from the text.

Parse `1981–82` (en dash) into `period_start_year=1981, period_end_year=1982`, normalising the label to an ASCII hyphen. Two-digit end years are in the same century as the start year for every period here.

- [ ] **Step 4: Run to verify passing**

Run: `.venv/bin/python -m pytest tests/test_mlr_displacement.py -v`
Expected: PASS.

- [ ] **Step 5: Parse all three articles and report coverage**

```bash
.venv/bin/python -c "
from mlr_displacement import parse_displacement_rate_table
import glob
for path in sorted(glob.glob('data/raw/dws/mlr/*.pdf')):
    try:
        rate_df = parse_displacement_rate_table(path)
        print(path, '->', sorted(rate_df.period_label.unique()))
    except Exception as parse_error:
        print(path, '-> FAILED:', parse_error)
"
```

Expected: the 1999 article yields eight periods, the 2001 article yields its own set including `1997-98`, and the 2004 article yields `1999-2000`. **The later two articles have their own layouts and may need per-article handling** — if one fails, report exactly how rather than loosening the parser until it silently produces wrong numbers.

- [ ] **Step 6: Lint and commit**

```bash
.venv/bin/ruff check mlr_displacement.py tests/test_mlr_displacement.py
.venv/bin/ruff format mlr_displacement.py tests/test_mlr_displacement.py
git add mlr_displacement.py tests/test_mlr_displacement.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "$(cat <<'EOF'
Parse displacement rates out of the MLR article tables

Replace this line with the per-article period coverage from Step 5.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XmW2c1TmZUtMwrc9wXueCi
EOF
)"
```

---

### Task 9: Crosswalk the 1980-census taxonomy to the ten modern groups

**Files:**
- Modify: `mlr_displacement.py`
- Create: `seeds/mlr_occupation_crosswalk.csv`
- Test: `tests/test_mlr_displacement.py`

**Interfaces:**
- Produces: `MLR_TO_DWS_GROUP: dict[str, str]`; `load_mlr_crosswalk(path="seeds/mlr_occupation_crosswalk.csv") -> pd.DataFrame`

The 1980-census sub-major groups map onto the ten modern DWS groups more cleanly than the major groups do — which is why the parser keeps leaves rather than aggregates.

- [ ] **Step 1: Write the crosswalk seed**

Create `seeds/mlr_occupation_crosswalk.csv` with columns `mlr_occupation, dws_group, mapping_confidence, note`. The mapping, derived from the 1980-census-to-SOC correspondence:

| `mlr_occupation` | `dws_group` | confidence |
|---|---|---|
| Executive, administrative, and managerial | management, business, and financial operations occupations | high |
| Professional specialty | professional and related occupations | high |
| Technicians and related support | professional and related occupations | high |
| Sales occupations | sales and related occupations | high |
| Administrative support, including clerical | office and administrative support occupations | high |
| Protective services | service occupations | high |
| Other service occupations | service occupations | high |
| Mechanics and repairers | installation, maintenance, and repair occupations | high |
| Construction trades | construction and extraction occupations | high |
| Other precision production occupations | production occupations | medium |
| Machine operators, assemblers, and inspectors | production occupations | high |
| Transportation and material moving occupations | transportation and material moving occupations | high |
| Handlers, equipment cleaners, helpers, and laborers | transportation and material moving occupations | **low** |
| Farming, forestry, and fishing | farming, fishing, and forestry occupations | high |

Confirm the last four labels against the actual parsed output before committing — the verification captured the block only as far as machine operators. If a label differs, use what the PDF says and record the discrepancy.

The **low-confidence** row is the honest one: handlers, cleaners, helpers and labourers split across production and transportation/material moving in the modern scheme, and this assigns them wholly to one. Task 10 must expose that so a reader can see it.

- [ ] **Step 2: Write the failing test**

```python
class TestCrosswalk:
    def test_every_leaf_has_a_mapping(self):
        from mlr_displacement import MLR_OCCUPATION_LEAVES, MLR_TO_DWS_GROUP

        assert set(MLR_OCCUPATION_LEAVES) <= set(MLR_TO_DWS_GROUP)

    def test_every_target_is_a_real_dws_group(self):
        from dws_panel import DWS_TO_SOC_MAJOR
        from mlr_displacement import MLR_TO_DWS_GROUP

        assert set(MLR_TO_DWS_GROUP.values()) <= set(DWS_TO_SOC_MAJOR)

    def test_all_ten_modern_groups_are_reachable(self):
        from dws_panel import DWS_TO_SOC_MAJOR
        from mlr_displacement import MLR_TO_DWS_GROUP

        assert set(MLR_TO_DWS_GROUP.values()) == set(DWS_TO_SOC_MAJOR)

    def test_low_confidence_mappings_are_flagged(self):
        from mlr_displacement import load_mlr_crosswalk

        crosswalk_df = load_mlr_crosswalk()
        assert (crosswalk_df["mapping_confidence"] == "low").any()
```

- [ ] **Step 3: Run to verify failure, then implement**

Run: `.venv/bin/python -m pytest tests/test_mlr_displacement.py::TestCrosswalk -v`
Expected: FAIL with `ImportError: cannot import name 'MLR_TO_DWS_GROUP'`.

Load the seed into `MLR_TO_DWS_GROUP` at module level, following how `harmonize_soc.py` reads its committed crosswalks from `seeds/`.

- [ ] **Step 4: Run to verify passing**

Run: `.venv/bin/python -m pytest tests/test_mlr_displacement.py -v`
Expected: PASS. `test_all_ten_modern_groups_are_reachable` failing means a modern group has no 1980-census source — report which, rather than inventing a mapping to satisfy the test.

- [ ] **Step 5: Commit**

```bash
.venv/bin/ruff check mlr_displacement.py tests/test_mlr_displacement.py
.venv/bin/ruff format mlr_displacement.py tests/test_mlr_displacement.py
git add mlr_displacement.py tests/test_mlr_displacement.py seeds/mlr_occupation_crosswalk.csv
PATH="$PWD/.venv/bin:$PATH" git commit -m "$(cat <<'EOF'
Crosswalk the 1980-census occupational taxonomy to the ten DWS groups

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XmW2c1TmZUtMwrc9wXueCi
EOF
)"
```

---

### Task 10: Fold the MLR rates into the panel, kept distinguishable

**Files:**
- Modify: `dws_panel.py`, `seeds/dws_displacement_panel.csv`
- Test: `tests/test_dws_panel.py`

MLR rows are rates on a crosswalked taxonomy; archive rows are counts on the native one. Blending them silently would be the worst outcome of this whole plan.

**Interfaces:**
- Produces: a `measurement_basis` column on the panel — `count_thousands` or `rate_percent`; and `source` — `news_release`, `news_release_archive`, or `mlr_article`.

- [ ] **Step 1: Write the failing test**

```python
class TestMeasurementBasis:
    def test_existing_rows_are_labelled_as_counts(self):
        panel_df = pd.read_csv("seeds/dws_displacement_panel.csv")
        modern = panel_df[panel_df["survey_year"] >= 2008]
        assert (modern["measurement_basis"] == "count_thousands").all()

    def test_mlr_rows_are_labelled_as_rates(self):
        panel_df = pd.read_csv("seeds/dws_displacement_panel.csv")
        historical = panel_df[panel_df["survey_year"] < 2008]
        assert not historical.empty
        assert (historical["measurement_basis"] == "rate_percent").all()

    def test_rates_and_counts_are_never_summed_together(self):
        """A single survey year must not mix bases — that is the blend this column exists to prevent."""
        panel_df = pd.read_csv("seeds/dws_displacement_panel.csv")
        per_year = panel_df.groupby("survey_year")["measurement_basis"].nunique()
        assert (per_year == 1).all()
```

- [ ] **Step 2: Run to verify failure, then implement**

Add `measurement_basis` and `source` to `PANEL_COLUMNS`, default existing rows to `count_thousands` / `news_release_archive` (or `news_release` for the current survey), and write MLR rows with `rate_percent` / `mlr_article`.

Store the MLR rate in `displacement_rate_percent`, a **new column** — do not put a percentage into `displaced_thousands`, which every existing consumer reads as a count. `load_dws_panel` and `dws_displacement_rate` must filter to `measurement_basis == "count_thousands"` so nothing downstream changes behaviour.

- [ ] **Step 3: Rebuild the seed with both sources**

```bash
.venv/bin/python -c "
import glob
import pandas as pd
from dws_panel import SEED_PANEL_PATH, mlr_rows_for_panel
from mlr_displacement import parse_displacement_rate_table
frames = [pd.read_csv(SEED_PANEL_PATH)]
for path in sorted(glob.glob('data/raw/dws/mlr/*.pdf')):
    frames.append(mlr_rows_for_panel(parse_displacement_rate_table(path)))
panel_df = pd.concat(frames, ignore_index=True).drop_duplicates(
    subset=['survey_year','source_table','group_name','reason'], keep='last')
panel_df = panel_df.sort_values(['survey_year','source_table','group_name']).reset_index(drop=True)
panel_df.to_csv(SEED_PANEL_PATH, index=False)
print(panel_df.groupby(['measurement_basis']).survey_year.nunique().to_string())
print('survey years:', sorted(panel_df.survey_year.unique()))
"
```

Expected: `count_thousands` covering ten survey years (2008-2026) and `rate_percent` covering the MLR periods. Report the full year list — that is this plan's headline deliverable.

- [ ] **Step 4: Confirm nothing downstream moved**

```bash
MPLCONFIGDIR=/tmp/claude-1000/mpl .venv/bin/python main.py composition > /tmp/claude-1000/mlr.log 2>&1; echo "exit: $?"
```

`historical_displacement_rate.csv` and the displacement validation must be unchanged by the MLR rows, because those consumers filter to counts. A change means the filter is missing — report it as a Critical finding.

- [ ] **Step 5: Document the MLR path**

Add to `CLAUDE.md`: an Outputs Reference note that `dws_displacement_panel.csv` now carries two measurement bases, a `seeds/mlr_occupation_crosswalk.csv` entry under the committed-reference-data convention alongside `seeds/soc_crosswalks/`, and the `pdfplumber` dependency in the setup notes.

Add to `docs/framework.md`, in the subsection Task 6 created: that pre-2008 displacement history comes from the MLR article series as **rates on the 1980-census taxonomy**, crosswalked to the ten modern groups; that one crosswalk row (handlers, equipment cleaners, helpers and labourers) is flagged low-confidence because it splits across two modern groups; and that the 2002 and 2004 surveys are genuinely absent because BLS published neither an archive nor an MLR article for them.

State the combined coverage plainly: 1981-82 through 2023-25, with a hole at 2001-04.

- [ ] **Step 6: Lint and commit**

```bash
.venv/bin/ruff check dws_panel.py tests/test_dws_panel.py
.venv/bin/ruff format dws_panel.py tests/test_dws_panel.py
git add dws_panel.py tests/test_dws_panel.py seeds/dws_displacement_panel.csv CLAUDE.md docs/framework.md
PATH="$PWD/.venv/bin:$PATH" git commit -m "$(cat <<'EOF'
Carry the MLR rate history beside the archive counts, not blended

Replace this line with the survey-year coverage by measurement basis.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XmW2c1TmZUtMwrc9wXueCi
EOF
)"
```

---

### Task 11: Prove nothing else changed

**Files:** none — verification only, no commit.

- [ ] **Step 1: Snapshot the baseline BEFORE Task 1 commits**

This must run on the pre-work `HEAD`. If you are reading this after starting, check out the pre-Task-1 commit into a scratch worktree and run the pipeline there.

```bash
mkdir -p /tmp/claude-1000/dws-baseline
cp data/output/*.csv /tmp/claude-1000/dws-baseline/
```

- [ ] **Step 2: Re-run the full pipeline**

```bash
MPLCONFIGDIR=/tmp/claude-1000/mpl .venv/bin/python main.py analyze synthesize plot validate composition > /tmp/claude-1000/dws-full.log 2>&1; echo "exit: $?"
```

- [ ] **Step 3: Compare**

```bash
.venv/bin/python -c "
import glob, os, pandas as pd
for baseline_path in sorted(glob.glob('/tmp/claude-1000/dws-baseline/*.csv')):
    name = os.path.basename(baseline_path)
    current_path = f'data/output/{name}'
    if not os.path.exists(current_path):
        print(f'{name}: MISSING'); continue
    baseline_df, current_df = pd.read_csv(baseline_path), pd.read_csv(current_path)
    if baseline_df.shape != current_df.shape:
        print(f'{name}: SHAPE {baseline_df.shape} -> {current_df.shape}'); continue
    numeric = [c for c in baseline_df.columns if pd.api.types.is_numeric_dtype(baseline_df[c]) and c in current_df.columns]
    diffs = [c for c in numeric if not baseline_df[c].equals(current_df[c])]
    print(f'{name}: {\"OK\" if not diffs else \"DIFF \" + str(diffs[:4])}')
"
```

**Expected, and this is the interesting part.** Two files are *expected* to change, because the panel they read grew from one survey to ten:
- `dws_displacement_panel.csv`
- `composition_model_displacement_validation.csv` — only if the newest survey's own numbers shift, which they should **not**; the newest survey is unchanged data, so a DIFF here is a real finding.

Everything else must report `OK`. In particular `composition_model_era_comparison.csv` and `composition_cycle_decomposition.csv` must be unchanged at all three levels, because `D` cancels from every cross-sectional correlation. A DIFF there means something depends on `D`'s amplitude that should not — report it precisely as a Critical finding.

- [ ] **Step 4: Report**

Summarise: surveys in the panel before and after, per-survey correlation range, how many surveys clear n=10 significance, whether the era and cycle outputs are unchanged, and the new BLS API request count.

---

## Out of scope for this plan

- **The 2002 and 2004 surveys**, covering roughly 2001-2004. Not a choice: BLS published no news-release archive for those years (probed exhaustively) and no MLR article covers them. The panel will carry a genuine hole there.
- **Converting MLR rates into counts or shares.** Doing so needs employment by occupation group per period; the CPS panel from the previous plan supplies that for the ten modern groups from 1983, but the MLR rates are on the 1980-census taxonomy and the earliest period (1981-82) predates the CPS panel entirely. The rates are carried as rates, flagged as such, and left for a later plan to convert if it wants to.
- **The IPUMS 22-group CPS upgrade** — the successor to the CPS historical panel plan, unrelated to displacement.
- Occupation taxonomy reconciliation for pre-1994 surveys, which used the 1980/1990 census occupational classification rather than the ten groups `DWS_TO_SOC_MAJOR` maps.
- Wages, monthly resolution, DOT-1991 era-appropriate labels.
