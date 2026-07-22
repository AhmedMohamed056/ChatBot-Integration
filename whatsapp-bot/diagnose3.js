/* Temporary diagnostic script 3 - tests nested puppeteer vs top-level against Chrome 150 */
const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer');

async function main() {
  const exePath = await puppeteer.executablePath();
  console.log('Chrome executable:', exePath);
  console.log('Chrome exists:', fs.existsSync(exePath));

  // Test 1: Top-level puppeteer@25.3.0 driving Chrome 150
  console.log('\n=== TEST 1: TOP-LEVEL puppeteer@25.3.0 + Chrome 150 ===');
  try {
    const browser = await puppeteer.launch({
      executablePath: exePath,
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
      protocolTimeout: 60000,
    });
    const page = (await browser.pages())[0];
    console.log('step: goto web.whatsapp.com');
    await page.goto('https://web.whatsapp.com/', { waitUntil: 'load', timeout: 60000, referer: 'https://whatsapp.com/' });
    console.log('step: evaluate simple expression');
    const result = await page.evaluate('1 + 1');
    console.log('evaluate result:', result);
    console.log('step: evaluate window location');
    const loc = await page.evaluate(() => window.location.href);
    console.log('location:', loc);
    await browser.close();
    console.log('TEST 1 PASSED: top-level puppeteer works with Chrome 150');
  } catch (e) {
    console.log('TEST 1 FAILED:', e.message);
  }

  // Test 2: Nested puppeteer@24.38.0 (the one whatsapp-web.js uses) driving Chrome 150
  console.log('\n=== TEST 2: NESTED puppeteer@24.38.0 + Chrome 150 ===');
  const nestedPuppeteerPath = path.resolve(
    __dirname,
    'node_modules',
    'whatsapp-web.js',
    'node_modules',
    'puppeteer'
  );
  console.log('nested puppeteer path:', nestedPuppeteerPath);
  console.log('nested puppeteer exists:', fs.existsSync(nestedPuppeteerPath));

  if (fs.existsSync(nestedPuppeteerPath)) {
    try {
      const nestedPuppeteer = require(nestedPuppeteerPath);
      console.log('nested puppeteer version:', require(path.join(nestedPuppeteerPath, 'package.json')).version);
      const browser = await nestedPuppeteer.launch({
        executablePath: exePath,
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
        protocolTimeout: 60000,
      });
      const page = (await browser.pages())[0];
      console.log('step: goto web.whatsapp.com');
      await page.goto('https://web.whatsapp.com/', { waitUntil: 'load', timeout: 60000, referer: 'https://whatsapp.com/' });
      console.log('step: evaluate simple expression');
      const result = await page.evaluate('1 + 1');
      console.log('evaluate result:', result);
      console.log('step: evaluate window location');
      const loc = await page.evaluate(() => window.location.href);
      console.log('location:', loc);
      await browser.close();
      console.log('TEST 2 PASSED: nested puppeteer@24.38.0 works with Chrome 150');
    } catch (e) {
      console.log('TEST 2 FAILED:', e.message);
      console.log('FULL ERROR:', e.stack);
    }
  }

  // Test 3: Check what Chrome version puppeteer@24.38.0 expects
  console.log('\n=== TEST 3: EXPECTED CHROME VERSIONS ===');
  const nestedPkgPath = path.join(nestedPuppeteerPath, 'package.json');
  if (fs.existsSync(nestedPkgPath)) {
    const nestedPkg = JSON.parse(fs.readFileSync(nestedPkgPath, 'utf8'));
    console.log('nested puppeteer version:', nestedPkg.version);
    const browsersConfigPath = path.join(nestedPuppeteerPath, 'browsers.json');
    if (fs.existsSync(browsersConfigPath)) {
      const browsers = JSON.parse(fs.readFileSync(browsersConfigPath, 'utf8'));
      console.log('nested browsers.json:', JSON.stringify(browsers, null, 2).slice(0, 2000));
    }
  }

  const topPkgPath = path.resolve(__dirname, 'node_modules', 'puppeteer', 'package.json');
  const topPkg = JSON.parse(fs.readFileSync(topPkgPath, 'utf8'));
  console.log('top puppeteer version:', topPkg.version);
  const topBrowsersPath = path.resolve(__dirname, 'node_modules', 'puppeteer', 'browsers.json');
  if (fs.existsSync(topBrowsersPath)) {
    const topBrowsers = JSON.parse(fs.readFileSync(topBrowsersPath, 'utf8'));
    console.log('top browsers.json:', JSON.stringify(topBrowsers, null, 2).slice(0, 2000));
  }

  console.log('\n=== DONE ===');
}

main().catch((e) => {
  console.error('DIAG ERROR:', e);
  process.exit(1);
});