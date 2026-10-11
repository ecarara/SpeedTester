// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Edson Angelo Carara

// Run against the local synthetic demo only. Requires the optional playwright package.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const url = new URL(process.argv[2] || 'http://127.0.0.1:8000');
  if (!['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)) {
    throw new Error('Capture requires the local synthetic demo, never staging.');
  }
  const output = path.resolve(__dirname, '../docs/images/dashboard.png');
  fs.mkdirSync(path.dirname(output), { recursive: true });
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1200 },
      deviceScaleFactor: 1, timezoneId: 'America/Sao_Paulo', locale: 'pt-BR' });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(url.href, { waitUntil: 'networkidle' });
    const response = await page.request.get(new URL('/api/samples', url).href);
    const samples = await response.json();
    if (samples.length !== 56 || samples.some(row => row.server_name !== 'iperf3.example.com')) {
      throw new Error('Expected 56 synthetic samples from seed_demo.py.');
    }
    await page.locator('#dayFilter').fill('2026-10-10');
    await page.locator('#dayFilter').dispatchEvent('change');
    await page.locator('#runnerFilter').selectOption('iperf3');
    await page.waitForFunction(() => document.querySelector('#coverageTitle').textContent === '8 concluídos');
    await page.waitForSelector('#chart svg circle');
    await page.evaluate(() => document.fonts.ready);
    await page.locator('.brand').click();
    if (errors.length) throw new Error(errors.join('\n'));
    const layout = await page.locator('.layout').first().boundingBox();
    await page.screenshot({ path: output, animations: 'disabled',
      clip: { x: 0, y: 0, width: 1440, height: Math.ceil(layout.y + layout.height + 24) } });
    console.log(`Screenshot saved: ${output}`);
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
