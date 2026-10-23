/* Record the real local app. No response fixtures, injected results or production UI edits.
   NODE_PATH=<installed playwright packages> node scripts/record_demo.cjs
   Demo server must use the desired real model configuration and an isolated JOB_DB. */
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');

const base = process.env.DEMO_BASE || 'http://127.0.0.1:7886';
const out = path.resolve(process.env.DEMO_OUTPUT || 'data/demo-recording');
const temp = path.resolve('data/demo-temp');
fs.mkdirSync(temp,{recursive:true});
process.env.TEMP=temp;
process.env.TMP=temp;
const product = 'HUAWEI MateBook 14（鸿蒙版）';
const cases = [
  {id:'student-xhs', title:'大学生 · 小红书', platform:'xiaohongshu',
   sentence:'给每天背电脑去图书馆的大学新生写一篇小红书笔记，围绕携带电脑、连接U盘整理学习资料这两个日常动作，语气自然，邀请到店看看真机。'},
  {id:'office-xhs', title:'移动办公 · 小红书', platform:'xiaohongshu',
   sentence:'给经常带电脑拜访客户的职场新人写一篇小红书笔记，围绕出门携带、到现场连接U盘展示资料，先讲具体动作和好处，邀请到店看看真机。'},
  {id:'office-moments', title:'移动办公 · 朋友圈', platform:'moments',
   sentence:'给经常带电脑拜访客户的职场新人写一条门店朋友圈，围绕出门携带、到现场连接U盘展示资料，只讲一个最相关的卖点，邀请到店看看真机。'}
];
fs.mkdirSync(out,{recursive:true});
let started = 0;
const report = {recorded_at:new Date().toISOString(), base, real_requests:true, viewport:{width:1600,height:900}, marks:[], cases:[], errors:[]};
function save(){fs.writeFileSync(path.join(out,'recording.json'),JSON.stringify(report,null,2));}
function mark(kind,label,extra={}) {
  const row={kind,label,at_seconds:(Date.now()-started)/1000,...extra};
  report.marks.push(row); save(); console.log(JSON.stringify(row));
}
const pause = ms=>new Promise(r=>setTimeout(r,ms));
async function click(page,selector) {
  const item=page.locator(selector); await item.waitFor({state:'visible'});
  const b=await item.boundingBox(); if(b)await page.mouse.move(b.x+b.width/2,b.y+b.height/2,{steps:18});
  await pause(220); await item.click(); await pause(550);
}
async function fill(page,selector,text) {
  await click(page,selector); await page.locator(selector).fill(text); await pause(1200);
}
async function snapshot(page,id) {
  const response=await page.request.get(`${base}/api/job/${id}`);
  if(!response.ok())throw new Error(`job read HTTP ${response.status()}`);
  return response.json();
}
async function main(){
  const browser=await chromium.launch({headless:true,channel:'msedge'});
  const context=await browser.newContext({viewport:report.viewport,deviceScaleFactor:1,locale:'zh-CN',
    recordVideo:{dir:out,size:report.viewport},acceptDownloads:true});
  started=Date.now(); const page=await context.newPage(); const video=page.video();
  page.on('pageerror',err=>{report.errors.push(err.message);save();});
  try{
    await page.goto(base,{waitUntil:'networkidle'});
    mark('intro','华章有据 · 实际网页录制');
    await page.screenshot({path:path.join(out,'00-welcome.png')}); await pause(4000);
    await click(page,'#enter-studio'); await pause(1800);
    const requested=process.env.DEMO_CASES?.split(',');
    for(const item of cases.filter(c=>!requested||requested.includes(c.id))){
      mark('case_start',item.title,{case:item.id});
      await click(page,'#tab-create');
      await click(page,'#mode-sentence');
      await fill(page,'#scene-description',item.sentence);
      await fill(page,'#product',product);
      await click(page,`button[data-platform="${item.platform}"]`);
      await page.screenshot({path:path.join(out,`${item.id}-brief.png`)});
      const reply=page.waitForResponse(r=>r.url()===`${base}/api/run`&&r.request().method()==='POST');
      await click(page,'#go'); const response=await reply;
      if(!response.ok())throw new Error(`generation start HTTP ${response.status()}`);
      let id=(await response.json()).job;
      mark('generation_start',item.title,{case:item.id,job:id});
      const deadline=Date.now()+780000;
      let job=null,lastLabel='',lastHeartbeat=Date.now();
      while(Date.now()<deadline){
        job=await snapshot(page,id);
        const running=(job.steps||[]).filter(s=>s.status==='running').map(s=>s.label).join(' / ');
        if(running&&running!==lastLabel){mark('stage',running,{case:item.id,job:id});lastLabel=running;}
        if(Date.now()-lastHeartbeat>25000){console.log(JSON.stringify({heartbeat:item.id,job:id,state:job.state,elapsed_ms:job.elapsed_ms}));lastHeartbeat=Date.now();}
        if(job.state!=='running'){
          const result=job.result||{};
          if(['need_info','input_required'].includes(result.status)){
            const question=page.locator('#agent-ask-question');
            await question.waitFor({state:'visible',timeout:12000});
            mark('clarification',await question.innerText(),{case:item.id,job:id});
            await pause(3500);
            // The demonstrator supplies an honest content preference, never product evidence.
            await fill(page,'#agent-ask-input','只介绍资料中能确认的携带和U盘连接信息；不需要软件适配或续航承诺，邀请到店看真机。');
            await page.locator('#agent-ask-form').evaluate(form=>form.requestSubmit());
            await pause(1200);
            const next=page.waitForResponse(r=>r.url()===`${base}/api/run`&&r.request().method()==='POST');
            await click(page,'.ask-submit'); const nr=await next;
            if(!nr.ok())throw new Error(`clarification start HTTP ${nr.status()}`);
            id=(await nr.json()).job; mark('generation_resume',item.title,{case:item.id,job:id});
            continue;
          }
          break;
        }
        await pause(1200);
      }
      if(!job||job.state==='running')throw new Error('real generation did not finish within recording limit');
      fs.writeFileSync(path.join(out,`${item.id}-job.json`),JSON.stringify(job,null,2));
      const r=job.result||{};
      report.cases.push({id:item.id,job:id,state:job.state,status:r.status,title:r.article?.title,
        elapsed_ms:r.total_ms,models:r.models_used,workflow:r.workflow_version,images:r.images?.length,
        image_notice:r.image_notice,remaining:r.verification?.remaining,sentence:item.sentence,platform:item.platform});
      mark('generation_end',item.title,{case:item.id,job:id,status:r.status});
      if(!r.article?.title)throw new Error(`no finished article: ${r.status||job.state}`);
      await pause(2200); await click(page,'#tab-work'); await pause(5000);
      await page.screenshot({path:path.join(out,`${item.id}-work.png`)});
      mark('work',item.title,{case:item.id});
      const preview=page.locator('#preview').locator('..');
      await preview.hover(); await page.mouse.wheel(0,420); await pause(3500);
      if(item.id==='student-xhs'){
        await click(page,'button[data-preview-device="mobile"]');await pause(4000);
        await page.screenshot({path:path.join(out,'student-xhs-mobile.png')});
        await click(page,'button[data-preview-device="desktop"]');
      }
      await click(page,'#tab-evidence');await pause(5000);
      await page.screenshot({path:path.join(out,`${item.id}-evidence.png`)});
      mark('evidence',item.title,{case:item.id});
      await click(page,'#insight-tab-judge');await pause(4000);
      await click(page,'#insight-tab-verify');await pause(4500);
      await page.screenshot({path:path.join(out,`${item.id}-review.png`)});
      if(item.id==='student-xhs'){
        await click(page,'#tab-work');await pause(1500);
        const download=page.waitForEvent('download',{timeout:45000});
        await click(page,'#dl');const file=await download;
        await file.saveAs(path.join(out,'student-xhs-export.html'));
        mark('export','实际导出含图片的 HTML',{case:item.id});await pause(2500);
      }
      mark('case_end',item.title,{case:item.id});
    }
    await click(page,'#tab-work'); await pause(4000);mark('finished','录制完成');
  }catch(err){report.failure=err.message;save();console.error(err.message);process.exitCode=1;}
  finally{await context.close();report.video=await video.path();report.duration_seconds=(Date.now()-started)/1000;save();await browser.close();}
}
main().catch(err=>{console.error(err);process.exitCode=1;});
