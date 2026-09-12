"""
download_dws.py
───────────────
Downloads the BLS Displaced Worker Supplement (DWS) news release tables used by
the demand composition model.

Unlike the OEWS zips, which BLS serves only to a real browser and which
download_bls.js therefore fetches through Puppeteer, the DWS news release answers
plain HTTP as long as a descriptive User-Agent is sent. No headless browser is
needed here.

Three tables are fetched:
  • Table 2 — long-tenured displaced workers by reason for job loss
  • Table 5 — long-tenured displaced workers by occupation of lost job
  • Table 8 — total displaced workers, all tenures

Inputs:
  • https://www.bls.gov/news.release/disp.t{02,05,08}.htm
  • BLS_CONTACT_EMAIL (environment, via .env) — see below

Outputs:
  • data/raw/dws/disp_t{02,05,08}.html

The release is a rolling page carrying only the latest biennial survey, and BLS
publishes no archive of prior releases, so history accumulates in
seeds/dws_displacement_panel.csv. See dws_panel.py for how that panel is built
and why the archive is unavailable.

BLS enforces its bot policy at the edge: a request whose User-Agent does not
carry a parenthesised contact email is answered with a 403 "Access Denied" page,
and so is any User-Agent containing a URL. BLS_CONTACT_EMAIL therefore has to be
set — in .env alongside GCP_PROJECT_ID, or in the environment. It is deliberately
not hardcoded, because a shared address in a public repository would attribute
every user's traffic to one person.

Like download_cps.js, this warns and exits 0 under CI when a fetch fails, so the
pipeline still renders from the committed seed alone.
"""

import os
import sys

import requests
from dotenv import load_dotenv

RELEASE_TABLE_URLS: dict[str, str] = {
    "disp_t02.html": "https://www.bls.gov/news.release/disp.t02.htm",
    "disp_t05.html": "https://www.bls.gov/news.release/disp.t05.htm",
    "disp_t08.html": "https://www.bls.gov/news.release/disp.t08.htm",
}

RAW_RELEASE_DIR = "data/raw/dws"

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


if __name__ == "__main__":
    main()
