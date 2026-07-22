/* Temporary diagnostic script 2 - will be removed after debugging */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const puppeteer = require('puppeteer');

async function main() {
  console.log('=== CHROME EXECUTABLE (awaited) ===');
  const exePath = await puppeteer.executablePath();
  console.log('puppeteer.executablePath():', exePath);
  console.log('exists:', fs.existsSync(exePath));

  if (fs.existsSync(exePath)) {
    try {
      const ver = execSync(
        `powershell -NoProfile -Command "(Get-Item '${exePath}').VersionInfo.FileVersion"`,
        { encoding: 'utf8' }
      ).trim();
      console.log('chrome file version:', ver);
    } catch (e) {
      console.log('could not read chrome version via powershell:', e.message);
    }
  }

  console.log('\n=== PUPPETEER CACHE STRUCTURE ===');
  const cacheRoot = path.join(process.env.USERPROFILE || '', '.cache', 'puppeteer');
  function walk(dir, depth) {
    if (depth > 2) return;
    let entries = [];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch (e) {
      return;
    }
    for (const e of entries) {
      const full = path.join(dir, e.name);
      console.log(full.replace(cacheRoot, '<cache>'));
      if (e.isDirectory()) walk(full, depth + 1);
    }
  }
  walk(cacheRoot, 0);

  console.log('\n=== CHROME VERSION FROM CACHE FOLDER NAME ===');
  const chromeCacheDir = path.join(cacheRoot, 'chrome');
  if (fs.existsSync(chromeCacheDir)) {
    console.log('chrome cache contents:', fs.readdirSync(chromeCacheDir));
  }

  console.log('\n=== NESTED PUPPETEER EXPECTED CHROME VERSION ===');
  const nestedBrowsersPath = path.resolve(
    __dirname,
    'node_modules',
    'whatsapp-web.js',
    'node_modules',
    'puppeteer-core',
    'node_modules',
    '@puppeteer',
    'browsers',
    'package.json'
  );
  if (fs.existsSync(nestedBrowsersPath)) {
    console.log('nested @puppeteer/browsers version:', JSON.parse(fs.readFileSync(nestedBrowsersPath, 'utf8')).version);
  }
  const nestedCorePkg = path.resolve(
    __dirname,
    'node_modules',
    'whatsapp-web.js',
    'node_modules',
    'puppeteer-core',
    'package.json'
  );
  const nestedCore = JSON.parse(fs.readFileSync(nestedCorePkg, 'utf8'));
  console.log('nested puppeteer-core version:', nestedCore.version);
  console.log('nested puppeteer-core engines:', JSON.stringify(nestedCore.engines));

  const topPkg = require('puppeteer/package.json');
  console.log('top puppeteer version:', topPkg.version);
  console.log('top puppeteer engines:', JSON.stringify(topPkg.engines));

  console.log('\n=== CHECKING CDP / PROTOCOLVERSION COMPAT ===');
  try {
    const browser = await puppeteer.launch({
      executablePath: exePath,
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
      protocolTimeout: 60000,
    });
    console.log('browser launched OK with top-level puppeteer');
    const version = await browser.version();
    console.log('browser.version():', version);
    const pages = await browser.pages();
    console.log('pages count:', pages.length);
    await browser.close();
    console.log('browser closed OK');
  } catch (e) {
    console.log('LAUNCH ERROR with top-level puppeteer:', e.message);
  }

  console.log('\n=== DONE ===');
}

main().catch((e) => {
  console.error('DIAG ERROR:', e);
  process.exit(1);
});