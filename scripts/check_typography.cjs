/* Uses recorded local jobs and real Chromium font inspection; never calls a generation model. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');
const base='http://127.0.0.1:7882';
const output=path.resolve('data/ui-checks');
const jobs={xiaohongshu:'807684c49cd9470dbc9230d2641ae874',wechat_article:'d712e97b95ea48b3a64bf0c01ef6cd5d',moments:'8157690675fc4febb78a8cbb41b7023f',poster:'aa6f2b2effea4272a5820dec5e6e8f51'};
fs.mkdirSync(output,{recursive:true});

async function main(){
  const browser=await chromium.launch({headless:true,channel:'msedge'}),errors=[],report=[];
  const context=await browser.newContext({viewport:{width:1440,height:900},acceptDownloads:true});
  const watch=page=>{
    page.on('pageerror',e=>errors.push(e.message));
    page.on('response',r=>{if(r.url().includes('.woff2')) assert.equal(new URL(r.url()).origin,base,'webfont is served by this site');});
  };
  async function fonts(page,selector){
    await page.evaluate(()=>document.fonts.ready);
    const cdp=await context.newCDPSession(page);await cdp.send('DOM.enable');await cdp.send('CSS.enable');
    const {root}=await cdp.send('DOM.getDocument');
    const {nodeId}=await cdp.send('DOM.querySelector',{nodeId:root.nodeId,selector});
    assert.ok(nodeId,selector);
    const result=await cdp.send('CSS.getPlatformFontsForNode',{nodeId});
    assert.ok(result.fonts.length,selector+' has rendered text');
    assert.ok(result.fonts.every(f=>f.isCustomFont||/Emoji/.test(f.familyName)),selector+' uses supplied font files for text');
    await cdp.detach();return result.fonts;
  }
  async function fit(page){
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'no horizontal overflow');
  }
  try{
    const page=await context.newPage();watch(page);
    await page.goto(base);await page.evaluate(()=>document.fonts.ready);
    await fonts(page,'.welcome h1');
    assert.equal(await page.locator('.welcome h1').evaluate(n=>getComputedStyle(n).fontWeight),'650');
    await page.waitForFunction(()=>getComputedStyle(document.querySelector('#enter-studio')).opacity==='1');
    await page.screenshot({path:path.join(output,'type-welcome.png')});
    await page.locator('#enter-studio').click();await page.locator('#welcome').waitFor({state:'hidden'});
    await fonts(page,'.intro h1');await fonts(page,'.page-nav button');await fonts(page,'label');
    assert.equal(await page.locator('label').first().evaluate(n=>getComputedStyle(n).fontWeight),'650');
    await page.screenshot({path:path.join(output,'type-create.png')});
    for(const [width,height] of [[1280,720],[390,844]]){
      await page.setViewportSize({width,height});await fit(page);
      await page.locator('#go').scrollIntoViewIfNeeded();assert.ok(await page.locator('#go').isVisible());
      await page.screenshot({path:path.join(output,`type-create-${width}.png`)});
    }
    report.push('welcome, creation, navigation and form labels use self-hosted fonts and real weights; desktop and mobile fit');
    await page.close();

    for(const [platform,id] of Object.entries(jobs)){
      const p=await context.newPage();watch(p);
      await p.addInitScript(job=>{sessionStorage.setItem('studio-welcomed','1');sessionStorage.setItem('studio-active-job',JSON.stringify({id:job,task:{},mode:'structured'}));},id);
      await p.goto(`${base}/#process`);await p.locator('#view-result').waitFor({state:'visible'});
      await fonts(p,'.stage-copy h3');
      if(platform==='xiaohongshu'){
        await p.evaluate(()=>document.fonts.ready);await p.screenshot({path:path.join(output,'type-process.png')});
        await p.setViewportSize({width:1280,height:720});await fit(p);
        const button=p.locator('.is-current .stage-detail');await button.scrollIntoViewIfNeeded();assert.ok(await button.isVisible());
        await p.setViewportSize({width:390,height:844});await fit(p);await p.screenshot({path:path.join(output,'type-process-390.png')});
        await p.setViewportSize({width:1440,height:900});
      }
      await p.locator('#view-result').click();await p.evaluate(()=>document.fonts.ready);
      const selectors={xiaohongshu:'.xhs-title',wechat_article:'.wx-title',moments:'.mm-author',poster:'.po-title'};
      await fonts(p,selectors[platform]);await fit(p);
      await p.screenshot({path:path.join(output,`type-work-${platform}.png`)});
      if(platform==='xiaohongshu'){
        const download=p.waitForEvent('download');await p.locator('#dl').click();
        const file=path.join(output,'type-export.html');await (await download).saveAs(file);
        const html=fs.readFileSync(file,'utf8');assert.ok(html.includes('data:font/woff2;base64,'));assert.ok(html.includes('SIL OPEN FONT LICENSE'));
        assert.ok(!/src:\s*url\(["']?\/static\/fonts\//.test(html),'exported font data is embedded');
        const offline=await browser.newContext({offline:true,viewport:{width:1440,height:900}});
        const exported=await offline.newPage();await exported.goto(pathToFileURL(file).href);await exported.evaluate(()=>document.fonts.ready);
        const cdp=await offline.newCDPSession(exported);await cdp.send('DOM.enable');await cdp.send('CSS.enable');const {root}=await cdp.send('DOM.getDocument');const {nodeId}=await cdp.send('DOM.querySelector',{nodeId:root.nodeId,selector:'.xhs-title'});const used=await cdp.send('CSS.getPlatformFontsForNode',{nodeId});assert.ok(used.fonts.length&&used.fonts.every(f=>f.isCustomFont));
        await exported.screenshot({path:path.join(output,'type-export-offline.png')});await offline.close();
        await p.getByRole('tab',{name:'事实核验'}).click();await fonts(p,'.insight-caption h3');await fit(p);
        await p.screenshot({path:path.join(output,'type-evidence.png')});
      }
      await p.setViewportSize({width:390,height:844});await fit(p);await p.evaluate(()=>document.fonts.ready);
      await p.screenshot({path:path.join(output,`type-work-${platform}-390.png`)});
      report.push(`${platform}: preview title uses bundled fonts; desktop/mobile fit`);
      await p.close();
    }
    for(const route of ['/about','/static/login.html','/static/brand/index.html']){
      const p=await context.newPage();watch(p);await p.goto(base+route);await p.evaluate(()=>document.fonts.ready);await fit(p);
      await fonts(p,route.includes('brand')?'.heading':route==='/about'?'h1':'label');
      await p.setViewportSize({width:390,height:844});await fit(p);await p.close();
    }
    const mark=await(await fetch(base+'/static/brand/wordmark.svg')).text();assert.ok(!mark.includes('<text'));
    report.push('about/login/brand pages use the same fonts; wordmark is vector outlines; exported HTML renders bundled fonts offline with licenses');
    assert.deepEqual(errors,[]);report.push('zero browser runtime errors');
    fs.writeFileSync(path.join(output,'type-report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
  }finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exit(1)});
