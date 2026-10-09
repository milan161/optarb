// 验证三个页面的导航链接在本地/线上都指向正确目标
const { chromium } = require('playwright-core');
const EXE='C:/Users/milan/AppData/Local/ms-playwright/chromium-1223/chrome-win64/chrome.exe';
(async()=>{
  const base = process.env.VBASE || 'http://127.0.0.1:8104';
  const b=await chromium.launch({executablePath:EXE});
  const c=await b.newContext({viewport:{width:1440,height:900}});
  const p=await c.newPage();
  const out=[];
  for (const route of ['/option','/option-daily','/option-risk']) {
    await p.goto(base+route,{waitUntil:'load'});
    await p.waitForTimeout(1200);
    const links = await p.$$eval('a[href]', as => as.map(a=>a.getAttribute('href')));
    out.push({route, links: links.filter(h=>h && h.includes('option'))});
  }
  console.log(JSON.stringify(out,null,1));
  await b.close();
})();
