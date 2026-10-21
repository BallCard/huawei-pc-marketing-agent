const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const base=process.env.UI_BASE||'http://127.0.0.1:7882';
const out='data/ui-checks/mobile';
fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const failures=[],report=[];
 const page=await browser.newPage();
 page.on('pageerror',e=>failures.push(e.message));
 async function fit(label){
  const result=await page.evaluate(()=>{
   const w=innerWidth;
   const outside=[...document.querySelectorAll('body *')].filter(e=>{
    const r=e.getBoundingClientRect();
    if(!r.width||!r.height||getComputedStyle(e).visibility==='hidden')return false;
    // Internal preview/table scrollers may intentionally contain wide content.
    for(let p=e.parentElement;p&&p!==document.body;p=p.parentElement){
     if(['auto','scroll','hidden'].includes(getComputedStyle(p).overflowX))return false;
    }
    return r.left < -1 || r.right > w+1;
   }).map(e=>e.id||e.className||e.tagName);
   return {width:w,scroll:document.documentElement.scrollWidth,outside};
  });
  assert.ok(result.scroll<=result.width+1,`${label}: document overflow ${JSON.stringify(result)}`);
  assert.deepEqual(result.outside,[],`${label}: out of bounds`);
  report.push(label);
 }
 try{
  for(const [width,height] of [[320,568],[360,640],[390,844],[430,932],[667,375],[768,1024],[900,600],[1440,900]]){
   await page.setViewportSize({width,height});
   await page.goto(base+'/static/ui-review/index.html');
   for(const name of ['brief','process','work','evidence']){
    await page.locator(`header [data-page="${name}"]`).click();
    await fit(`prototype ${name} ${width}x${height}`);
    if(name==='brief'&&width<=430&&height>=640){
     assert.ok(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight+1),'default mobile brief fits one screen');
    }
    if(width===390)await page.screenshot({path:`${out}/prototype-${name}.png`,fullPage:true});
   }
   await page.locator('header [data-page="brief"]').click();
   await page.locator('[data-action="presets"]').click();
   await fit(`prototype presets ${width}`);
   await page.locator('[data-close]').click();
   await page.locator('header [data-page="work"]').click();
   await page.locator('[data-action="refine"]').click();
   await fit(`prototype refine ${width}`);
   await page.locator('[data-close]').click();
   await page.goto(base+'/static/index.html');
   if(await page.locator('#enter-studio').isVisible())await page.locator('#enter-studio').click();
   await page.waitForFunction(()=>!document.querySelector('.site-header').inert);
   for(const name of ['create','process','work','evidence']){
    await page.locator(`#tab-${name}`).click();
    await fit(`studio ${name} ${width}x${height}`);
   }
   await page.locator('#tab-create').click();
   if(width===390)await page.screenshot({path:`${out}/studio-brief.png`});
   if(width<=700)assert.equal(await page.locator('#audience').evaluate(e=>getComputedStyle(e).fontSize),'16px');
   for(const trigger of ['#open-presets','#open-options']){
    await page.locator(trigger).click();
    await fit(`studio ${trigger} ${width}`);
    await page.keyboard.press('Escape');
   }
   for(const platform of ['xiaohongshu','wechat_article','moments','poster']){
    await page.evaluate(platform=>{
     const r={task:{platform},model:{name:'手机适配测试型号'},article:{title:'手机布局测试',blocks:[{type:'paragraph',text:'这是一段用于检查长内容换行与滚动的测试文字。'.repeat(15)}]},images:[]};
     Studio.finishRun(r);Studio.renderPreview(r);
     document.querySelector('#stage').hidden=false;document.querySelector('#revise').hidden=false;
     Studio.navigate('work');
    },platform);
    await fit(`studio result ${platform} ${width}`);
    await page.locator('#redo').scrollIntoViewIfNeeded();
    assert.ok(await page.locator('#redo').isVisible());
    if(width===390)await page.screenshot({path:`${out}/studio-${platform}.png`,fullPage:true});
   }
   await page.evaluate(()=>{
    Studio.navigate('evidence');
    document.querySelector('#dbg-evidence').hidden=false;
    document.querySelector('#evidence').innerHTML='<table><tr><th>事实</th><th>来源</th><th>适用条件</th></tr>'+('<tr><td>核验测试内容</td><td>source-file-with-a-long-name.md</td><td>具体配置需核对</td></tr>'.repeat(20))+'</table>';
   });
   await fit(`studio populated evidence ${width}`);
   await page.evaluate(()=>{
    const d=document.querySelector('#review-question-dialog')||document.querySelector('.review-dialog');
    d.showModal();
   });
   await fit(`studio review dialog ${width}`);
   await page.keyboard.press('Escape');
   await page.goto(base+'/static/login.html');
   await fit(`login ${width}`);
  }
  assert.deepEqual(failures,[],'browser errors');
  fs.writeFileSync(`${out}/report.json`,JSON.stringify({checks:report.length,report,errors:failures},null,2));
  console.log(`PASS: ${report.length} viewport/page checks; no browser errors`);
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
