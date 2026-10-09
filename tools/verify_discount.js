// 验收「卖沽移仓价差（日报）」页的 贴水(卖出腿) 一行。
// 目的：确认 ETF 不再显示 0，且股指数值未变。
//
// 用法：
//   export NODE_PATH="C:/Users/milan/.workbuddy-ai/binaries/node/workspace/node_modules"
//   node tools/verify_discount.js [baseUrl]
//   默认 baseUrl = http://127.0.0.1:8104
//
// 注意（踩过的坑）：
//   · 切品种必须 waitForResponse 等**该品种自己的** /api/migrate 响应，
//     固定 sleep 会拍到上一个品种的数据。
//   · 线上前缀是 /optarb_api，所以正则写 /\/migrate\?/ 而不是 /api/migrate。

const { chromium } = require('playwright-core');

const CHROME = 'C:/Users/milan/AppData/Local/ms-playwright/chromium-1223/chrome-win64/chrome.exe';
const BASE = process.argv[2] || 'http://127.0.0.1:8104';
const OUTDIR = process.argv[3] || 'D:/Study/Optarb/.tmp/shots';

const WANT = ['E500', 'E300', 'E880', 'IO', 'MO', 'HO'];

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const ctx = await browser.newContext({
    viewport: { width: 760, height: 900 },
    deviceScaleFactor: 2,
  });
  const page = await ctx.newPage();

  const errs = [];
  page.on('pageerror', e => errs.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text()); });

  await page.goto(BASE + '/option-daily', { waitUntil: 'load' });
  await page.waitForSelector('.meta', { timeout: 30000 });

  const readLine = () => page.evaluate(() => {
    const spans = [...document.querySelectorAll('.meta span')];
    const disc = spans.find(s => s.innerText.includes('贴水'));
    const fwd = spans.find(s => s.innerText.includes('远期'));
    const spot = spans.find(s => s.innerText.includes('指数'));
    const sel = document.querySelector('select');
    return {
      variety: sel ? sel.value : null,
      spot: spot ? spot.innerText.replace(/\s+/g, ' ') : null,
      forward: fwd ? fwd.innerText.replace(/\s+/g, ' ') : null,
      discount: disc ? disc.innerText.replace(/\s+/g, ' ') : '(无贴水行)',
    };
  });

  const results = [];
  for (const v of WANT) {
    // 切到目标品种：先挂响应监听，再 selectOption
    const resp = page.waitForResponse(
      r => /\/migrate\?/.test(r.url()) && r.url().includes('variety=' + v),
      { timeout: 60000 }
    ).catch(() => null);
    await page.selectOption('select', v);
    await resp;
    await page.waitForTimeout(700);
    const line = await readLine();
    results.push(line);
    await page.screenshot({ path: `${OUTDIR}/daily_${v}.png`, fullPage: false });
  }

  console.log('URL      :', BASE + '/option-daily');
  console.log('控制台错误:', errs.length ? errs.join(' | ') : '（无）');
  console.log('');
  for (const r of results) {
    console.log('品种 %-5s | %s', r.variety, r.discount);
    console.log('        | %s  %s', r.spot, r.forward);
  }

  await browser.close();
})().catch(e => { console.error('FAILED:', e); process.exit(1); });
