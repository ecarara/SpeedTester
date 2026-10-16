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
    MPLCONFIGDIR:path.join(temporary,'mpl'), ISP_LOOKUP_ENABLED:'false', API_RATE_LIMIT_PER_MINUTE:'10000', API_REQUIRE_LOGIN:'true', API_ADMIN_TOKEN:'ui-example-admin-token' };
  const hash=spawnSync(python,['-c',"from api.auth import password_hash;print(password_hash('ui-viewer-password'))"],{cwd:root,env,encoding:'utf8'});
  assert.equal(hash.status,0,hash.stderr);env.API_VIEWER_PASSWORD_HASH=hash.stdout.trim();
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
    await page.coverage.startJSCoverage({resetOnNavigation:false});
    assert.equal((await request.get(base+'/api/samples')).status(),401);
    await page.goto(base,{waitUntil:'networkidle'});
    if(process.env.DASHBOARD_SCREENSHOT)await page.screenshot({path:path.join(root,'docs/images/login.png'),fullPage:true});
    await page.locator('#username').fill('admin');await page.locator('#password').fill('wrong');await page.locator('#loginForm button').click();
    await page.waitForFunction(()=>document.querySelector('#loginError').textContent.length>0);
    await page.locator('#password').fill('ui-example-admin-token');await page.locator('#loginForm button').click();
    await page.waitForURL(base+'/');
    await page.waitForFunction(()=>document.querySelector('#sessionStatus').textContent.includes('Administrador'));
    const session=await (await request.get(base+'/api/auth/session')).json();
    assert.equal((await request.post(base+'/api/availability-events',{data:{started_at:'2020-01-01T00:00:00Z',ended_at:'2020-01-01T01:00:00Z',event_type:'POWER_OUTAGE',source:'manual',note:'Synthetic test interval'},headers:{'X-CSRF-Token':session.csrf_token}})).status(),200);
    await page.locator('#dayFilter').fill('2026-10-10');await page.locator('#dayFilter').dispatchEvent('change');
    // A previous day's chart can also contain eight results. Wait for both
    // queued refreshes to finish before focusing a point that render replaces.
    await page.waitForFunction(()=>!state.refreshing&&!state.refreshPending&&document.querySelector('#coveragePeriod').textContent==='2026-10-10'&&document.querySelector('#coverageTitle').textContent==='8 concluídos');
    assert.equal(await page.locator('#chart circle').count(),16);
    await page.locator('#chart circle').first().focus();
    const chartDetail=await page.waitForFunction(()=>{const value=document.querySelector('#chartDetail').textContent;return /download:.*Mbps/.test(value)?value:false;});
    assert.match(await chartDetail.jsonValue(),/download:.*Mbps/);
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
    await page.waitForSelector('#networkMap .map-marker');
    const geography = await request.get(base+'/dashboard/world-map.svg');
    assert.equal(geography.status(),200,'Offline world geography must be served locally');
    const geographySvg = await geography.text();
    assert.match(geographySvg,/data-country="Brazil"/);
    assert((geographySvg.match(/<path /g)||[]).length>150,'Use country contours instead of illustrative polygons');
    assert.equal(await page.locator('#networkMap image.map-geography').getAttribute('href'),'/dashboard/world-map.svg');
    assert.equal(await page.locator('#networkMap .map-marker').count(),1);
    await page.locator('#networkMap .map-marker').first().focus();
    assert.match(await page.locator('.network-map-detail h4').textContent(),/Operadora de demonstração/);
    await page.locator('#mapOperatorFilter').selectOption({index:1});
    await page.waitForSelector('#networkMap .network-map-list-item');
    await page.locator('#networkMap .network-map-list-item').first().click();
    await page.locator('#mapResetBtn').click();
    if(process.env.NETWORK_MAP_SCREENSHOT) {
      await page.locator('#networkMap .map-marker').first().focus();
      await page.locator('#networkMap').screenshot({path:process.env.NETWORK_MAP_SCREENSHOT});
      await page.setViewportSize({width:390,height:844});
      assert.equal(await page.locator('#networkMap').evaluate(node=>node.scrollWidth<=node.clientWidth),true,'Map must fit the mobile viewport');
      await page.locator('#networkMap').screenshot({path:process.env.NETWORK_MAP_SCREENSHOT.replace(/\.png$/,'-mobile.png')});
      await page.setViewportSize({width:1440,height:1100});
    }
    await page.evaluate(() => {
      const target = document.querySelector('#networkMap');
      window.SpeedTesterNetworkMap.render(target, { points: [
        { operator: 'Operadora A', city: 'São Paulo', country: 'Brasil', coordinate_source: 'city-centroid', latitude: -23.55, longitude: -46.63, samples: 4, avg_download_mbps: 900, avg_upload_mbps: 450, failure_count: 0 },
        { operator: 'Operadora B', city: 'São Paulo', country: 'Brasil', coordinate_source: 'country-centroid', latitude: -23.55, longitude: -46.63, samples: 2, avg_download_mbps: null, avg_upload_mbps: Number.NaN, failure_count: 1 },
        { operator: 'Operadora C', city: 'Local desconhecido', country: 'País desconhecido', coordinate_source: 'unavailable', latitude: null, longitude: null, samples: 1, avg_download_mbps: null, avg_upload_mbps: null, failure_count: 1 },
      ] }, {});
    });
    assert.equal(await page.locator('#networkMap .map-marker').count(),2);
    await page.locator('#networkMap .network-map-list-item').nth(2).click();
    assert.match(await page.locator('.network-map-detail-copy').textContent(),/posição indisponível/);
    await page.evaluate(() => window.SpeedTesterNetworkMap.render(document.querySelector('#networkMap'), { points: [] }, {}));
    assert.match(await page.locator('#networkMap').textContent(),/Nenhum grupo encontrado/);
    const coverage = await page.coverage.stopJSCoverage(), map=createCoverageMap({});
    const dashboardCoverage=coverage.filter(entry=>/\/dashboard\/(charts|auth|network-map)\.js$/.test(entry.url));
    assert(dashboardCoverage.some(entry=>entry.url.endsWith('/charts.js')),'Chart coverage was not captured');
    assert(dashboardCoverage.some(entry=>entry.url.endsWith('/network-map.js')),'Network map coverage was not captured');
    for(const entry of dashboardCoverage){
      const filename=entry.url.endsWith('/charts.js')?'charts.js':entry.url.endsWith('/auth.js')?'auth.js':'network-map.js';
      const converter=v8toIstanbul(path.join(root,'app/dashboard',filename),0,{source:entry.source});
      await converter.load();converter.applyCoverage(entry.functions);map.merge(converter.toIstanbul());
    }
    reports.create('lcovonly').execute(createContext({dir:path.join(root,'coverage-js'),coverageMap:map}));
    if(process.env.DASHBOARD_SCREENSHOT){await page.locator('#periodFilter').selectOption('7');await page.waitForFunction(()=>document.querySelector('#coveragePeriod').textContent==='7 dias');await page.screenshot({path:path.join(root,'docs/images/dashboard.png')});}
    await page.setViewportSize({width:390,height:844});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth), 'Mobile page overflows horizontally');
    assert.deepEqual(errors,[]);
    await page.locator('#logoutBtn').click();await page.waitForURL(base+'/login');
    assert.equal((await request.get(base+'/api/samples')).status(),401);
    await page.locator('#username').fill('viewer');await page.locator('#password').fill('ui-viewer-password');await page.locator('#loginForm button').click();
    await page.waitForURL(base+'/');
    await page.waitForFunction(()=>document.querySelector('#sessionStatus').textContent.includes('Visualizador'));
    assert(await page.locator('#operatorActions').isHidden());assert(await page.locator('#resetBtn').isHidden());
    const viewer=await (await request.get(base+'/api/auth/session')).json();
    assert.equal((await request.post(base+'/api/reset',{headers:{'X-CSRF-Token':viewer.csrf_token}})).status(),403);
    assert.equal((await request.get(base+'/api/export')).status(),200);
    assert.deepEqual(errors,[]);
    console.log('dashboard-e2e-ok: login, admin, CSRF, logout, viewer, protected export, day/7/30/90, runner, empty state, keyboard chart, complete export, mobile, operational timezone');
  } finally {
    if(browser)await browser.close();
    if(server?.exitCode===null){server.kill('SIGTERM');await new Promise(resolve=>server.once('exit',resolve));}
    fs.rmSync(temporary,{recursive:true,force:true});
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
