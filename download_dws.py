"""
download_dws.py
───────────────
Downloads the BLS Displaced Worker Supplement (DWS) news release tables used by
the demand composition model.

Unlike the OEWS zips, which BLS serves only to a real browser and which
download_bls.js therefore fetches through Puppeteer, the DWS news release answers
plain HTTP as long as a descriptive User-Agent is sent. No headless browser is
needed here.

Three tables are fetched from the current release:
  • Table 2 — long-tenured displaced workers by reason for job loss
  • Table 5 — long-tenured displaced workers by occupation of lost job
  • Table 8 — total displaced workers, all tenures

BLS does publish an archive of prior DWS releases, at
/news.release/archives/disp_<MMDDYYYY>.htm — contrary to an earlier note in this
project that concluded otherwise. That check used wrong release dates: the
release day differs per survey, and a wrong day genuinely 404s (disp_08252022.htm
is a 404; disp_08262022.htm, the real 2022 release, is not). Nine biennial
archives from 2008 to 2024 were individually verified reachable on 2026-09-14 and
are listed in ARCHIVE_RELEASE_URLS. Unlike the current release, which splits its
tables across three URLs, each archive carries all of its tables inline in one
page, so one file per survey year is the whole payload.

Also fetched here: the three Monthly Labor Review displaced-worker articles that
carry the pre-2008 history the news-release archives do not reach (see
MLR_ARTICLE_URLS). These are PDFs, not HTML; a later step parses them.

Inputs:
  • https://www.bls.gov/news.release/disp.t{02,05,08}.htm
  • https://www.bls.gov/news.release/archives/disp_<MMDDYYYY>.htm (nine surveys)
  • https://www.bls.gov/opub/mlr/<year>/<month>/art<n>full.pdf (three MLR articles)
  • BLS_CONTACT_EMAIL (environment, via .env) — see below

Outputs:
  • data/raw/dws/disp_t{02,05,08}.html
  • data/raw/dws/archives/disp_<year>.html
  • data/raw/dws/mlr/<article_key>.pdf

The current release is a rolling page carrying only the latest biennial survey,
so history accumulates in seeds/dws_displacement_panel.csv. See dws_panel.py for
how that panel is built. Parsing the archive pages into that panel is a separate
step from fetching them, which is all this module does for the archives.

BLS enforces its bot policy at the edge, and the rules are narrower than they
first appear (probed 2026-09-12):

  • A User-Agent with no parenthesised contact email gets a 403 "Access Denied"
    page. So does a bare "curl/8.5.0".
  • A User-Agent containing the literal string "github.com" is refused whatever
    surrounds it — a repo URL, and also a GitHub noreply address such as
    6422297+user@users.noreply.github.com. The equivalent gitlab.com noreply
    domain is accepted, so this is a specific block rather than a general
    URL-detection rule.
  • A "+" in the local part is fine: 6422297+user@example.com is accepted.

So a GitHub noreply address cannot be used here, which is just as well — those
addresses do not receive mail, and the point of the policy is that BLS can warn
an operator before blocking them. A provider alias such as user+bls@gmail.com
works and stays reachable.

BLS_CONTACT_EMAIL therefore has to be set — in .env alongside GCP_PROJECT_ID, or
in the environment. It is deliberately not hardcoded, because a shared address in
a public repository would attribute every user's traffic to one person.

Like download_cps.js, this warns and exits 0 under CI when a fetch fails, so the
pipeline still renders from the committed seed alone.
"""

import os
import sys
import warnings

import requests
from dotenv import load_dotenv

RELEASE_TABLE_URLS: dict[str, str] = {
    "disp_t02.html": "https://www.bls.gov/news.release/disp.t02.htm",
    "disp_t05.html": "https://www.bls.gov/news.release/disp.t05.htm",
    "disp_t08.html": "https://www.bls.gov/news.release/disp.t08.htm",
}

RAW_RELEASE_DIR = "data/raw/dws"

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

REQUEST_TIMEOUT_SECONDS = 60

CONTACT_EMAIL_VARIABLE = "BLS_CONTACT_EMAIL"


def build_request_headers() -> dict[str, str]:
    """Build the User-Agent BLS requires: a tool name plus a parenthesised contact email."""
    load_dotenv()
    contact_email = os.environ.get(CONTACT_EMAIL_VARIABLE, "").strip()
    if not contact_email:
        raise RuntimeError(
            f"{CONTACT_EMAIL_VARIABLE} is not set. BLS returns 403 to requests that do not carry a contact "
            f"email in the User-Agent, so set it in .env (see README) before downloading DWS tables."
        )
    return {"User-Agent": f"ai-exposure-research ({contact_email})"}


# Every DWS table page carries its table number in the caption. Verifying this
# before overwriting avoids replacing a good local copy with an error page served
# with a 200 status.
EXPECTED_CAPTION_MARKERS: dict[str, str] = {
    "disp_t02.html": "Table 2.",
    "disp_t05.html": "Table 5.",
    "disp_t08.html": "Table 8.",
}


def download_release_table(file_name: str, url: str, request_headers: dict[str, str]) -> bool:
    """Fetch one release table and write it to the raw directory. Returns True on success."""
    response = requests.get(url, headers=request_headers, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()

    expected_marker = EXPECTED_CAPTION_MARKERS[file_name]
    if expected_marker not in response.text:
        print(f"  ⚠ {url} did not contain {expected_marker!r}; leaving any existing copy untouched.")
        return False

    output_path = os.path.join(RAW_RELEASE_DIR, file_name)
    with open(output_path, "w", encoding="utf-8") as output_file:
        output_file.write(response.text)
    print(f"  ✓ {file_name} ({len(response.text):,} bytes)")
    return True


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


def main() -> None:
    """Download all three DWS release tables, failing soft under CI."""
    os.makedirs(RAW_RELEASE_DIR, exist_ok=True)
    print("Downloading BLS Displaced Worker Supplement tables...")

    try:
        request_headers = build_request_headers()
        downloaded = [download_release_table(file_name, url, request_headers) for file_name, url in RELEASE_TABLE_URLS.items()]
    except (requests.RequestException, RuntimeError) as request_error:
        message = f"Could not fetch the Displaced Worker Supplement: {request_error}"
        if os.environ.get("CI"):
            print(f"  ⚠ {message} Continuing from the committed seed panel.")
            return
        print(f"  ✗ {message}")
        sys.exit(1)

    if not all(downloaded):
        print("  ⚠ Some DWS tables were not refreshed; the committed seed panel still applies.")

    print("Downloading archived Displaced Worker Supplement releases...")
    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter("always")
        archived_paths = download_archived_releases(request_headers)
        for caught_warning in caught_warnings:
            print(f"  ⚠ {caught_warning.message}")
    print(f"  ✓ {len(archived_paths)} of {len(ARCHIVE_RELEASE_URLS)} archived releases available")

    print("Downloading Monthly Labor Review displaced-worker articles...")
    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter("always")
        mlr_article_paths = download_mlr_articles(request_headers)
        for caught_warning in caught_warnings:
            print(f"  ⚠ {caught_warning.message}")
    print(f"  ✓ {len(mlr_article_paths)} of {len(MLR_ARTICLE_URLS)} MLR articles available")


if __name__ == "__main__":
    main()
