// Integration check for the final, standalone HTML. No live account access.
const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');
const {pathToFileURL} = require('url');
const args = {};
for (let i = 2; i < process.argv.length; i += 2) {
  assert(process.argv[i].startsWith('--') && process.argv[i + 1], 'Expected --key value');
  args[process.argv[i].slice(2)] = process.argv[i + 1];
}
assert(args.html && args.analysis && args.screenshots, 'Required: --html --analysis --screenshots');
const {chromium} = require(args['playwright-module'] || 'playwright');
const analysis = JSON.parse(fs.readFileSync(args.analysis, 'utf8'));
const money = cents => (cents / 100).toLocaleString('zh-CN', {minimumFractionDigits:2, maximumFractionDigits:2});
const ratio = n => n === null ? '—' : n.toFixed(2);
function expected(record) { return `本周投产 ${ratio(record.roi)} 倍　费用 ${money(record.cost_cents)} 元　真实销售 ${money(record.sales_cents)} 元`; }
(async () => {
 const browser = await chromium.launch({headless:true, ...(args['browser-channel'] ? {channel:args['browser-channel']} : {})});
 try {
  const context = await browser.newContext({offline:true, viewport:{width:1100, height:1200}});
  const page = await context.newPage();
  const errors = [], requests = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => { if (/^https?:/.test(r.url())) requests.push(r.url()); });
  await page.goto(pathToFileURL(path.resolve(args.html)).href);
  const select = page.locator('#roi-product');
  await select.locator('option').last().waitFor({state:'attached'});
  assert.equal(await select.locator('option').count(), analysis.products.length + 1);
  assert.equal(await page.locator('tbody tr').count(), analysis.products.length);
  assert.equal(await page.locator('.roi-chart').count(), 3);
  assert.equal(await select.inputValue(), 'all');
  assert.equal(await page.locator('#roi-selection').textContent(), expected(analysis.totals));
  assert.deepEqual((await page.locator('#roi-matrix-top th').allTextContents()).slice(1,8), analysis.period.dates.map(d => d.slice(5).replace('-', '/')));
  const rows = await page.locator('tbody tr').all();
  for (let i = 0; i < rows.length; i++) {
   const cells = await rows[i].locator('td').allTextContents();
   const product = analysis.products[i];
   assert.deepEqual(cells.slice(1,8), product.daily.map(d => ratio(d.roi)));
   assert.deepEqual(cells.slice(8), [money(product.cost_cents), money(product.sales_cents), ratio(product.roi)]);
   const label = await select.locator(`option[value="${product.key}"]`).textContent();
   assert.equal(cells[0], label);
   await select.selectOption(product.key);
   assert.equal(await page.locator('#roi-selection').textContent(), expected(product));
  }
  await page.locator('#roi-matrix-top tbody tr').first().locator('button').click();
  assert.equal(await select.inputValue(), analysis.products[0].key);
  if (analysis.products.length > 10) {
   await page.locator('summary').click();
   await page.locator('#roi-matrix-rest tbody tr').first().locator('button').click();
   assert.equal(await select.inputValue(), analysis.products[10].key);
   await page.locator('summary').click();
  } else assert(await page.locator('details').isHidden());
  const paid = analysis.products.find(p => p.daily.some(d => d.roi !== null));
  if (paid) {
   await select.selectOption(paid.key);
   const index = paid.daily.findIndex(d => d.roi !== null);
   await page.locator('#roi-ratio [data-chart-hit]').first().hover();
   await page.getByRole('tooltip').waitFor({state:'visible'});
   assert((await page.getByRole('tooltip').innerText()).includes(analysis.period.dates[index]));
   await page.locator('h2').hover();
  }
  const zero = analysis.products.find(p => p.cost_cents === 0);
  if (zero) {
   await select.selectOption(zero.key);
   assert.equal(await page.locator('#roi-ratio [data-chart-hit]').count(), 0);
   assert.equal(await page.locator('#roi-selection').textContent(), expected(zero));
  }
  assert(!/经营状态|周环比|复核筛选|低费用高/.test(await page.locator('main').innerText()));
  await select.selectOption('all');
  fs.mkdirSync(args.screenshots, {recursive:true});
  await page.screenshot({path:path.join(args.screenshots,'desktop.png'), fullPage:true});
  await page.setViewportSize({width:360,height:1200});
  await page.waitForTimeout(250);
  await page.screenshot({path:path.join(args.screenshots,'mobile.png'),fullPage:true});
  const geometry = await page.evaluate(() => {
   const charts = [...document.querySelectorAll('.roi-chart')].map(svg => {
    const rect = svg.querySelector('[data-chart-frame]').getBBox();
    const marks = [...svg.querySelectorAll('path[stroke="var(--viz-series-1)"],circle:not([data-chart-hit]),rect[data-tooltip]')].filter(e => e.tagName !== 'path' || e.getAttribute('d')).map(e => e.getBBox());
    return {width:svg.getBoundingClientRect().width,frame:{x:rect.x,y:rect.y,width:rect.width,height:rect.height},
            marks:marks.map(b => ({x:b.x,y:b.y,width:b.width,height:b.height}))};
   });
   return {client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,charts};
  });
  assert(geometry.scroll <= geometry.client, 'Unexpected page horizontal overflow');
  for (const chart of geometry.charts) for (const mark of chart.marks) {
   const f = chart.frame;
   assert(mark.x >= f.x - 0.1 && mark.x + mark.width <= f.x + f.width + 0.1 && mark.y >= f.y - 0.1 && mark.y + mark.height <= f.y + f.height + 0.1, 'Data mark outside plot frame');
  }
  assert.deepEqual(errors, []); assert.deepEqual(requests, []);
  const result = {status:'PASS',productsChecked:analysis.products.length,productDaysChecked:analysis.products.length * 7,offlineHttpRequests:0,pageErrors:[],mobileWidth:360};
  fs.writeFileSync(path.join(args.screenshots,'browser-verification.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify(result));
 } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
