#!/usr/bin/env node
/**
 * Probe both recommend and invited APIs via puppeteer (click tabs)
 */
const path = require('path');
const CookieManager = require('./cookie-manager.js');
const cm = new CookieManager();
const cookies = cm.load();
const puppeteer = require('puppeteer-core');

const EDGE_PATH = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';

async function main() {
  const browser = await puppeteer.launch({
    headless: 'new',
    executablePath: EDGE_PATH,
    args: ['--no-sandbox']
  });
  const page = await browser.newPage();
  
  const cookieList = Object.entries(cookies).map(([name, value]) => ({
    name, value, domain: '.zhihu.com', path: '/'
  }));
  await page.setCookie(...cookieList);

  const apis = [];
  page.on('response', async resp => {
    const url = resp.url();
    try {
      const ct = resp.headers()['content-type'] || '';
      if (ct.includes('json') && url.includes('question_route')) {
        const json = await resp.json();
        const key = url.replace('https://www.zhihu.com/api/v4/creators/question_route/', '').split('?')[0];
        apis.push({ key, url, count: json.data?.length || 0 });
      }
    } catch {}
  });

  // Navigate to recommend page
  await page.goto('https://www.zhihu.com/creator/featured-question/recommend', {
    waitUntil: 'networkidle0', timeout: 30000
  });
  await new Promise(r => setTimeout(r, 5000));

  // Click the "邀请" tab
  try {
    const tabs = await page.$$('a[href*="invited"], div[class*="tab"], span[class*="tab"]');
    for (const tab of tabs) {
      const text = await page.evaluate(el => el.textContent, tab);
      if (text && text.includes('邀请')) {
        console.log('Clicking tab:', text.trim());
        await tab.click();
        break;
      }
    }
  } catch {}

  await new Promise(r => setTimeout(r, 5000));

  console.log('\nAPI calls intercepted:');
  apis.forEach(a => console.log(`  ${a.key} => ${a.count} items`));

  if (apis.length === 0) {
    console.log('(no question_route APIs found)');
  } else {
    // Also try the found API with different params
    console.log('\nTrying direct API calls...');
  }

  await browser.close();
}

main().catch(e => {
  console.error('ERROR:', e.message);
  process.exit(1);
});
