// 验证「移仓决策台」ETF 试点的平价理论价列
// 用法：NODE_PATH=<ws>/node_modules node shots/verify_parity.js
const { chromium } = require('playwright-core');

const URL = process.env.VURL || 'http://127.0.0.1:8104/option-risk';
const EXE = 'C:/Users/milan/AppData/Local/ms-playwright/chromium-1223/chrome-win64/chrome.exe';
const OUT = process.env.VOUT || 'D:/Study/Optarb/shots';

(async () => {
  const browser = await chromium.launch({ executablePath: EXE });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1200 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });

  await page.goto(URL, { waitUntil: 'load' });
  await page.waitForTimeout(2500);

  const rep = { url: URL, steps: [] };

  // ★ 切品种后不能只 sleep —— 页面要等 /api/live 回来才更新，
  //   而 MO 的 /api/window 很慢会把渲染拖到 5s+（实测）。
  //   固定 sleep 3.5s 会拍到上一个品种的数据，得到假结果。
  //   正解：等**该品种自己的** /api/live 响应到达，再多等 900ms 让 Vue 渲染。
  // ⚠️ 过滤条件**不能写死 `/api/live`** —— 线上前缀是 `/optarb_api/live`，
  //   写死会永远匹配不上、一路超时（2026-09-30 踩过）。
  async function switchTo(v) {
    const [resp] = await Promise.all([
      page.waitForResponse(r => /\/live\?/.test(r.url()) && r.url().includes('variety=' + v),
        { timeout: 40000 }),
      page.selectOption('select', v),
    ]);
    await page.waitForTimeout(900);
    return resp.status();
  }

  // ---- 1. 品种下拉有哪些选项 ----
  const opts = await page.$$eval('select', sels =>
    sels.map(s => [...s.options].map(o => o.value + '|' + o.textContent.trim())));
  rep.selectOptions = opts;

  // ---- 2. 切到 E300 ----
  rep.e300Http = await switchTo('E300');

  rep.e300 = await page.evaluate(() => {
    const q = s => document.querySelector(s);
    const txt = el => el ? el.innerText.replace(/\s+/g, ' ').trim() : null;
    const tbl = q('table');
    const heads = tbl ? [...tbl.querySelectorAll('thead th')].map(th => th.innerText.replace(/\s+/g, ' ').trim()) : [];
    const rows = tbl ? [...tbl.querySelectorAll('tbody tr')].map(tr =>
      [...tr.querySelectorAll('td')].map(td => td.innerText.replace(/\s+/g, ' ').trim())) : [];
    const live = q('.live');
    return {
      bodyHasMustache: /\{\{|\[\[/.test(document.body.innerText),
      bigLabel: txt(q('.big .lab')),
      bigVal: txt(q('.big .val')),
      bigSub: txt(q('.big .sub')),
      verdict: txt(q('.verdict')),
      meta: txt(q('.meta')),
      tableHeads: heads,
      rowCount: rows.length,
      rows: rows.slice(0, 12),
      hasParityNote: /平价理论价/.test(document.body.innerText),
      histError: (() => { const e = q('.err'); return e ? txt(e) : null; })(),
    };
  });

  await page.screenshot({ path: OUT + '/etf_e300.png', fullPage: false });

  // ---- 3. 切到 E500 ----
  rep.e500Http = await switchTo('E500');
  rep.e500 = await page.evaluate(() => {
    const q = s => document.querySelector(s);
    const tbl = q('table');
    return {
      bigLabel: (q('.big .lab') || {}).innerText,
      tableHeads: tbl ? [...tbl.querySelectorAll('thead th')].map(th => th.innerText.replace(/\s+/g, ' ').trim()) : [],
      rows: tbl ? [...tbl.querySelectorAll('tbody tr')].map(tr =>
        [...tr.querySelectorAll('td')].map(td => td.innerText.replace(/\s+/g, ' ').trim())).slice(0, 12) : [],
    };
  });
  await page.screenshot({ path: OUT + '/etf_e500.png', fullPage: false });

  // ---- 4. 切回 MO，确认股指没被改坏 ----
  rep.moHttp = await switchTo('MO');
  rep.mo = await page.evaluate(() => {
    const q = s => document.querySelector(s);
    const tbl = q('table');
    return {
      bigLabel: (q('.big .lab') || {}).innerText,
      verdict: (q('.verdict') || {}).innerText,
      tableHeads: tbl ? [...tbl.querySelectorAll('thead th')].map(th => th.innerText.replace(/\s+/g, ' ').trim()) : [],
      rows: tbl ? [...tbl.querySelectorAll('tbody tr')].map(tr =>
        [...tr.querySelectorAll('td')].map(td => td.innerText.replace(/\s+/g, ' ').trim())).slice(0, 6) : [],
    };
  });
  await page.screenshot({ path: OUT + '/etf_mo.png', fullPage: false });

  rep.errors = errors;
  console.log(JSON.stringify(rep, null, 1));
  await browser.close();
})().catch(e => { console.error('FATAL', e); process.exit(1); });
