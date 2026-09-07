/*
 * download_cps.js
 * ───────────────
 * Fetches BLS CPS Table A-19 ("Employed people by occupation, sex, and age") and
 * saves the raw HTML to data/raw/cps/table_a19.html for cps_panel.py to parse.
 *
 * BLS returns HTTP 403 to plain HTTP clients on this path, so the page is loaded
 * through headless Chrome — the same workaround download_bls.js uses for the OEWS
 * zips. The Python requests-based version this replaces failed silently.
 *
 * Kept separate from download_bls.js on purpose: the release workflow caches the
 * OEWS zips on hashFiles('download_bls.js') and skips that script entirely on a
 * cache hit, which would mean the CPS table was never re-fetched.
 *
 * Exit status is environment-dependent by design. Locally a failed fetch exits
 * non-zero so it is noticed. In CI it warns and exits 0: BLS blocks bot traffic
 * and GitHub runners are cloud IPs, and the committed seeds/cps_a19_panel.csv
 * still yields correctly labelled charts from real (if slightly older) months.
 */

const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const CPS_TABLE_A19_URL = 'https://www.bls.gov/web/empsit/cpseea19.htm';

(async () => {
  const outputDir = path.resolve('./data/raw/cps');
  const outputPath = path.join(outputDir, 'table_a19.html');
  fs.mkdirSync(outputDir, { recursive: true });

  let browser;
  try {
    browser = await puppeteer.launch({
      headless: 'new',
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    const page = await browser.newPage();
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');

    console.log(`Downloading CPS Table A-19 from ${CPS_TABLE_A19_URL}...`);
    const response = await page.goto(CPS_TABLE_A19_URL, { waitUntil: 'networkidle0', timeout: 60000 });

    if (!response || !response.ok()) {
      throw new Error(`HTTP ${response ? response.status() : 'no response'}`);
    }

    // Confirm the expected table is present before overwriting a good local copy.
    const html = await page.content();
    if (!html.includes('A-19')) {
      throw new Error('Page loaded but does not contain Table A-19 — layout may have changed');
    }

    fs.writeFileSync(outputPath, html, 'utf-8');
    const sizeKb = (fs.statSync(outputPath).size / 1024).toFixed(1);
    console.log(`Saved ${outputPath} (${sizeKb} KB)`);
  } catch (error) {
    const message = `CPS Table A-19 download failed: ${error.message}`;
    if (process.env.CI) {
      console.warn(`WARNING: ${message}`);
      console.warn('  Continuing with the committed CPS panel seed — charts will use older months.');
    } else {
      console.error(`ERROR: ${message}`);
      process.exitCode = 1;
    }
  } finally {
    if (browser) {
      await browser.close();
    }
  }
})();
