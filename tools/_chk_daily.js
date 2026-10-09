const { chromium } = require('playwright-core');
const EXE='C:/Users/milan/AppData/Local/ms-playwright/chromium-1223/chrome-win64/chrome.exe';
(async()=>{
  const b=await chromium.launch({executablePath:EXE});
  const c=await b.newContext({viewport:{width:900,height:1200}});
  const p=await c.newPage(); const errs=[];
  p.on('pageerror',e=>errs.push('pageerror: '+e.message));
  await p.goto('https://9eastray.com/option-daily',{waitUntil:'load'});
  await p.waitForTimeout(6000);
  const t=await p.evaluate(()=>({title:document.title, h1:(document.querySelector('h1')||{}).innerText, body:(document.body.innerText||'').slice(0,300), mustache:/\{\{/.test(document.body.innerText)}));
  console.log(JSON.stringify({t,errs},null,1));
  await b.close();
})();
