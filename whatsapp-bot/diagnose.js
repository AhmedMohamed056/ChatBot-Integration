/* Temporary diagnostic script - will be removed after debugging */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const puppeteer = require('puppeteer');

async function main() {
  console.log('=== ENVIRONMENT ===');
  console.log('Node:', process.version);
  console.log('Arch:', process.arch);
  console.log('Platform:', process.platform);

  console.log('\n=== TOP-LEVEL PUPPETEER ===');
  console.log('puppeteer require version:', require('puppeteer/package.json').version);

  console.log('\n=== WHATSAPP-WEB.JS ===');
  try {
    const wjs = require('whatsapp-web.js/package.json');
    console.log('whatsapp-web.js version:', wjs.version);
  } catch (e) {
    console.log('could not read whatsapp-web.js version:', e.message);
  }

  console.log('\n=== NESTED PUPPETEER (bundled by whatsapp-web.js) ===');
  const nestedPuppeteerPath = path.resolve(
    __dirname,
    'node_modules',
    'whatsapp-web.js',
    'node_modules',
    'puppeteer',
    'package.json'
  );
  if (fs.existsSync(nestedPuppeteerPath)) {
    const nested = JSON.parse(fs.readFileSync(nestedPuppeteerPath, 'utf8'));
    console.log('nested puppeteer version:', nested.version);
  } else {
    console.log('no nested puppeteer found (whatsapp-web.js uses top-level puppeteer)');
  }

  const nestedPuppeteerCorePath = path.resolve(
    __dirname,
    'node_modules',
    'whatsapp-web.js',
    'node_modules',
    'puppeteer-core',
    'package.json'
  );
  if (fs.existsSync(nestedPuppeteerCorePath)) {
    const nestedCore = JSON.parse(fs.readFileSync(nestedPuppeteerCorePath, 'utf8'));
    console.log('nested puppeteer-core version:', nestedCore.version);
  } else {
    console.log('no nested puppeteer-core found');
  }

  console.log('\n=== TOP-LEVEL PUPPETEER-CORE ===');
  try {
    console.log('puppeteer-core version:', require('puppeteer-core/package.json').version);
  } catch (e) {
    console.log('puppeteer-core not installed at top level:', e.message);
  }

  console.log('\n=== CHROME EXECUTABLE ===');
  const exePath = puppeteer.executablePath();
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
      console.log('could not read chrome version:', e.message);
    }
  }

  console.log('\n=== PUPPETEER CACHE CANDIDATES ===');
  const candidates = [
    path.join(process.env.USERPROFILE || '', '.cache', 'puppeteer'),
    path.join(process.env.LOCALAPPDATA || '', '.cache', 'puppeteer'),
    path.join(process.env.USERPROFILE || '', 'AppData', 'Local', 'ms-playwright'),
  ];
  for (const c of candidates) {
    if (fs.existsSync(c)) {
      console.log('cache exists:', c);
      try {
        console.log('contents:', fs.readdirSync(c));
      } catch (e) {}
    }
  }

  console.log('\n=== AUTH DIR ===');
  const authPath = path.resolve(__dirname, 'auth');
  console.log('auth path:', authPath);
  if (fs.existsSync(authPath)) {
    const list = fs.readdirSync(authPath);
    console.log('auth contents:', list);
    for (const entry of list) {
      const sub = path.join(authPath, entry);
      if (fs.statSync(sub).isDirectory()) {
        console.log('  ', entry, '=>', fs.readdirSync(sub).slice(0, 20));
      }
    }
  } else {
    console.log('auth dir does not exist (fresh)');
  }

  console.log('\n=== DONE ===');
}

main().catch((e) => {
  console.error('DIAG ERROR:', e);
  process.exit(1);
});