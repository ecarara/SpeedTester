// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Edson Angelo Carara
// Deterministic browser acceptance test against a disposable local demo.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const net = require('node:net');
const { spawn, spawnSync } = require('node:child_process');
const { chromium } = require('playwright');
const v8toIstanbul = require('v8-to-istanbul');
const { createCoverageMap } = require('istanbul-lib-coverage');
const { createContext } = require('istanbul-lib-report');
const reports = require('istanbul-reports');

(async () => {
  const root = path.resolve(__dirname, '..'), temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'speedtester-ui-'));
  const python = process.env.PYTHON || 'python3', database = path.join(temporary, 'demo.db');
  const env = { ...process.env, PYTHONPATH: path.join(root, 'app'), DB_PATH:database,
    MPLCONFIGDIR:path.join(temporary,'mpl'), ISP_LOOKUP_ENABLED:'false', API_RATE_LIMIT_PER_MINUTE:'10000' };
  let server, browser;
  try {
    const fixture = spawnSync(python, ['scripts/seed_demo.py','--db',database], { cwd:root, env, encoding:'utf8' });
    assert.equal(fixture.status, 0, fixture.stderr);
    const port = await new Promise(resolve => { const socket=net.createServer(); socket.listen(0,'127.0.0.1',()=>{const assigned=socket.address().port;socket.close(()=>resolve(assigned));}); });
    const base = 'http://127.0.0.1:'+port;
    server = spawn(python,['-m','uvicorn','api.server:app','--host','127.0.0.1','--port',String(port)],{cwd:root,env,stdio:'ignore'});
    browser = await chromium.launch({headless:true});
    const page = await browser.newPage({viewport:{width:1440,height:1100}, timezoneId:'UTC', locale:'pt-BR', acceptDownloads:true});
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    const request=page.request;
    for(let i=0;i<120;i++) {
      try { if((await request.get(base+'/health')).ok())break; } catch { /* Wait for the actual HTTP service. */ }
      if(server.exitCode!==null)throw new Error('API exited during startup');
      if(i===119)throw new Error('API startup timeout');
      await new Promise(resolve=>setTimeout(resolve,250));
    }
    await page.coverage.startJSCoverage();
    await page.goto(base,{waitUntil:'networkidle'});
    await page.locator('#dayFilter').fill('2026-10-10');await page.locator('#dayFilter').dispatchEvent('change');
    await page.waitForFunction(()=>document.querySelector('#coverageTitle').textContent==='8 concluídos');
    assert.equal(await page.locator('#chart circle').count(),16);
    await page.locator('#chart circle').first().focus();
    assert.match(await page.locator('#chartDetail').textContent(),/download:.*Mbps/);
    for(const [period,count] of [['7',56],['30',56],['90',56]]) {
      await page.locator('#periodFilter').selectOption(period);
      await page.waitForFunction(([expected,period])=>document.querySelector('#coverageTitle').textContent===expected+' concluídos'&&document.querySelector('#coveragePeriod').textContent===period+' dias',[count,period]);
      assert.match(await page.locator('#coveragePeriod').textContent(),new RegExp(period+' dias'));
      assert.equal(await page.locator('#chart circle').count(),112);
    }
    const downloadEvent = page.waitForEvent('download'); await page.locator('#exportJsonBtn').click();
    const download = await downloadEvent, file = await download.path();
    assert.equal(JSON.parse(fs.readFileSync(file,'utf8')).length,56);
    await page.locator('#runnerFilter').selectOption('ookla');
    await page.waitForFunction(()=>document.querySelector('#heroLatest').textContent==='Nenhuma medição no período');
    assert.match(await page.locator('#chart').textContent(),/Sem medições/);
    await page.locator('#runnerFilter').selectOption('iperf3');
    await page.waitForFunction(()=>document.querySelector('#coverageTitle').textContent==='56 concluídos'&&document.querySelectorAll('#chart circle').length===112);
    await page.setViewportSize({width:390,height:844});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth), 'Mobile page overflows horizontally');
    assert.deepEqual(errors,[]);
    const coverage = await page.coverage.stopJSCoverage(), map=createCoverageMap({});
    const chartCoverage=coverage.filter(entry=>entry.url.endsWith('/dashboard/charts.js'));
    assert.equal(chartCoverage.length,1,'Chart coverage was not captured');
    for(const entry of chartCoverage){
      const converter=v8toIstanbul(path.join(root,'app/dashboard/charts.js'),0,{source:entry.source});
      await converter.load();converter.applyCoverage(entry.functions);map.merge(converter.toIstanbul());
    }
    reports.create('lcovonly').execute(createContext({dir:path.join(root,'coverage-js'),coverageMap:map}));
    console.log('dashboard-e2e-ok: day/7/30/90, runner, empty state, keyboard chart, complete export, mobile, operational timezone');
  } finally {
    if(browser)await browser.close();
    if(server?.exitCode===null){server.kill('SIGTERM');await new Promise(resolve=>server.once('exit',resolve));}
    fs.rmSync(temporary,{recursive:true,force:true});
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
