const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');
const https = require('https');

(async () => {
  const downloadDir = path.resolve('./data/raw/bls');
  fs.mkdirSync(downloadDir, { recursive: true });

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const page = await browser.newPage();

  // Set user agent
  await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');

  // Set download behavior
  const client = await page.target().createCDPSession();
  await client.send('Page.setDownloadBehavior', {
    behavior: 'allow',
    downloadPath: downloadDir
  });

  // 2024 and 2025 are only available as the full "all areas" file; 2022/2023 are national-only.
  const urls = [
    'https://www.bls.gov/oes/special-requests/oesm25all.zip',
    'https://www.bls.gov/oes/special.requests/oesm24all.zip',
    'https://www.bls.gov/oes/special.requests/oesm23nat.zip',
    'https://www.bls.gov/oes/special.requests/oesm22nat.zip'
  ];

  for (const url of urls) {
    const filename = url.split('/').pop();
    const destPath = path.join(downloadDir, filename);

    if (fs.existsSync(destPath)) {
      console.log(`Already exists, skipping: ${filename}`);
      continue;
    }

    console.log(`Downloading ${url}...`);
    try {
      await page.goto(url, { waitUntil: 'networkidle0', timeout: 60000 });
    } catch (e) {
      // goto throws when a download starts — this is expected
      console.log(`Note: page.goto threw an exception (normal for downloads): ${e.message}`);
    }

    // Poll until the file appears (up to 120 seconds)
    console.log('Waiting for download to complete...');
    const deadline = Date.now() + 120000;
    while (!fs.existsSync(destPath) && Date.now() < deadline) {
      await new Promise(resolve => setTimeout(resolve, 2000));
    }

    if (fs.existsSync(destPath)) {
      const size = (fs.statSync(destPath).size / (1024 * 1024)).toFixed(2);
      console.log(`Downloaded ${filename} (${size} MB)`);
    } else {
      console.error(`ERROR: ${filename} did not appear after 120s — URL may not exist or download failed`);
    }
  }

  await browser.close();

  const files = fs.readdirSync(downloadDir);
  console.log(`Files in download directory: ${files.join(', ')}`);
})();
