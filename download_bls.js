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

  const urls = [
    'https://www.bls.gov/oes/special.requests/oesm23nat.zip',
    'https://www.bls.gov/oes/special.requests/oesm22nat.zip'
  ];

  for (const url of urls) {
    console.log(`Downloading ${url}...`);
    try {
      await page.goto(url, { waitUntil: 'networkidle0', timeout: 30000 });
    } catch (e) {
      // goto might throw an error when a download starts instead of a page load
      console.log(`Note: page.goto threw an exception (normal for downloads): ${e.message}`);
    }

    // Wait for the file to appear in the directory
    console.log('Waiting for download to complete...');
    await new Promise(resolve => setTimeout(resolve, 5000));
  }

  await browser.close();

  const files = fs.readdirSync(downloadDir);
  console.log(`Files in download directory: ${files.join(', ')}`);
})();
