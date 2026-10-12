// Verify final two-week HTML in an offline browser, including all table values.
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {pathToFileURL}=require('url');const args={};
for(let i=2;i<process.argv.length;i+=2){assert(process.argv[i+1]);args[process.argv[i].slice(2)]=process.argv[i+1]}
const {chromium}=require(args['playwright-module']||'playwright');
const analysis=JSON.parse(fs.readFileSync(args.analysis,'utf8'));
const money=n=>n===null||n===undefined?'—':(n/100).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2});
const ratio=n=>n===null||n===undefined?'—':n.toFixed(2);
const signed=n=>n===null?'—':(n>0?'+':'')+(n!==0&&Math.abs(n)<.005?n.toPrecision(2):n.toFixed(2));
const pct=c=>c.pct===null?(c.reason==='baseline_zero'?'不可算（上周为0）':'不可算'):(c.pct>0?'+':'')+c.pct.toFixed(1)+'%';
(async()=>{
 const browser=await chromium.launch({headless:true,...(args['browser-channel']?{channel:args['browser-channel']}:{})});
 try{
  const context=await browser.newContext({offline:true,viewport:{width:1180,height:1200}});
  const page=await context.newPage();const errors=[],requests=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/^https?:/.test(r.url()))requests.push(r.url())});
  await page.goto(pathToFileURL(path.resolve(args.html)).href);
  const select=page.locator('#roi-product');
  await select.locator('option').last().waitFor({state:'attached'});
  assert.equal(await select.locator('option').count(),analysis.products.length+1);
  assert.equal(await page.locator('#comparison-top tbody tr,#comparison-rest tbody tr').count(),analysis.products.length);
  assert.equal(await page.locator('.chart').count(),3);
  assert.equal(await page.evaluate(()=>window.BAD),undefined);
  assert.equal(await page.locator('#metrics [data-metric="roi"] .value').textContent(),ratio(analysis.totals.current.roi)+' 倍');
  assert((await page.locator('#metrics [data-metric="roi"] p').last().textContent()).includes(pct(analysis.totals.changes.roi)));
  for(const p of analysis.products){
   const row=page.locator(`#comparison-top tr[data-product="${p.key}"],#comparison-rest tr[data-product="${p.key}"]`);
   const values={previous_roi:ratio(p.previous?.roi),current_roi:ratio(p.current?.roi),roi_delta:signed(p.changes.roi.delta),roi_pct:pct(p.changes.roi),
                 cost:money(p.current?.cost_cents),cost_pct:pct(p.changes.cost_cents),sales:money(p.current?.sales_cents),sales_pct:pct(p.changes.sales_cents)};
   for(const [column,value] of Object.entries(values))assert.equal(await row.locator(`[data-column="${column}"]`).textContent(),value);
   await select.selectOption(p.key);
   assert.equal(await page.locator('#metrics [data-metric="roi"] .value').textContent(),ratio(p.current?.roi)+' 倍');
   assert.equal(await page.locator('#metrics [data-metric="cost"] .value').textContent(),money(p.current?.cost_cents)+' 元');
   const roiTicks=await page.locator('#ratio-chart .tick text').allTextContents();
   assert(!roiTicks.some(text=>/^[\d.]+[mkMGµn]$/.test(text)),'ROI axis must use ordinary numbers in multiples');
   for(const metric of ['cost','sales']){
    const key=metric+'_cents';const amounts=[p.previous,p.current].filter(Boolean).flatMap(w=>w.daily.map(d=>d[key]/100));
    if(Math.max(0,...amounts)<1000){const ticks=await page.locator(`#${metric}-chart .tick text`).allTextContents();assert(!ticks.some(text=>/^[\d.]+[mkMGµn]$/.test(text)),'Small currency amounts must not use SI fractions')}
   }
  }
  assert.equal(await page.locator('select').count(),1,'Only product selection is needed');
  assert.equal(await page.locator('[data-column="state"],[data-column="review_days"],#review-line,#state-counts,#roi-filter,.alert-day').count(),0);
  assert.equal(await page.locator('#comparison-top th').count(),9);
  const renderedText=await page.locator('main').textContent();
  assert(!/经营状态|有费无销|有费用无销售|复核范围/.test(renderedText),'Removed state review must not appear');
  await page.locator('#comparison-top tbody tr').first().locator('button').click();assert.equal(await select.inputValue(),analysis.products[0].key);
  if(analysis.products.length>10){await page.locator('#comparison-rest-details summary').click();await page.locator('#comparison-rest tbody tr').first().locator('button').click();assert.equal(await select.inputValue(),analysis.products[10].key);await page.locator('#comparison-rest-details summary').click()}
  await select.selectOption('all');
  await page.locator('#ratio-chart [data-chart-hit]').first().hover();await page.getByRole('tooltip').waitFor({state:'visible'});
  const tooltip=await page.getByRole('tooltip').textContent();assert(tooltip.includes(analysis.previous.period.dates[0])&&tooltip.includes(analysis.current.period.dates[0]));await page.locator('h1').hover();
  await page.locator('#heat-details summary').click();
  const heatRows=await page.locator('#daily-heatmap tbody tr').all();assert.equal(heatRows.length,analysis.products.length);
  for(let k=0;k<heatRows.length;k++){
   const cells=(await heatRows[k].locator('td').allTextContents()).slice(1);let expected=[];
   for(const side of ['previous','current'])expected.push(...(analysis.products[k][side]?analysis.products[k][side].daily.map(d=>ratio(d.roi)):Array(7).fill('无记录')));
   assert.deepEqual(cells,expected);
  }
  await page.locator('#heat-details summary').click();
  fs.mkdirSync(args.screenshots,{recursive:true});await page.screenshot({path:path.join(args.screenshots,'desktop.png'),fullPage:true});
  await select.selectOption('all');await page.setViewportSize({width:360,height:1200});await page.waitForTimeout(200);await page.screenshot({path:path.join(args.screenshots,'mobile.png'),fullPage:true});
  const geometry=await page.evaluate(()=>({client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,
    charts:[...document.querySelectorAll('.chart')].map(svg=>{const f=svg.querySelector('[data-chart-frame]').getBBox();return {frame:{x:f.x,y:f.y,width:f.width,height:f.height},
      marks:[...svg.querySelectorAll('[data-mark]')].filter(e=>e.tagName!=='path'||e.getAttribute('d')).map(e=>{const b=e.getBBox();return {x:b.x,y:b.y,width:b.width,height:b.height}})}})}));
  assert(geometry.scroll<=geometry.client,'Page horizontal overflow');for(const chart of geometry.charts)for(const b of chart.marks){const f=chart.frame;assert(b.x>=f.x-.1&&b.x+b.width<=f.x+f.width+.1&&b.y>=f.y-.1&&b.y+b.height<=f.y+f.height+.1,'Mark outside frame')}
  assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);
  const result={status:'PASS',productsChecked:analysis.products.length,recordsChecked:analysis.audit.record_count,stateReviewRemoved:true,tableColumns:9,offlineHttpRequests:0,pageErrors:[],mobileWidth:360};
  fs.writeFileSync(path.join(args.screenshots,'browser-verification.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
