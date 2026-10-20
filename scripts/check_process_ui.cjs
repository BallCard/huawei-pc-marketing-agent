/* Recorded real artifacts + explicit transport/branch fixtures. No model calls.
   NODE_PATH=<playwright packages> node scripts/check_process_ui.cjs --job <completed local job id> */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');
const option = name => process.argv[process.argv.indexOf(name)+1];
const base = process.argv.includes('--base') ? option('--base') : 'http://127.0.0.1:7882';
const jobId = process.argv.includes('--job') ? option('--job') : null;
const output = path.resolve('data/ui-checks');
fs.mkdirSync(output,{recursive:true});
const clone = value => structuredClone(value);

async function main() {
  assert.ok(jobId,'--job is required; use a completed local real job');
  const response = await fetch(`${base}/api/job/${jobId}`);
  assert.equal(response.status,200);
  const original = await response.json();
  assert.ok(original.result?.article,'recorded job must contain a real article');
  const browser = await chromium.launch({headless:true,channel:'msedge'});
  const page = await browser.newPage({viewport:{width:1440,height:900}});
  const errors=[], report=[];
  let expected503=false;
  page.on('pageerror',e=>errors.push(e.message));
  page.on('console',m=>{
    const expected=expected503 && m.location().url.endsWith('/api/run') && m.text().includes('503');
    if(m.type()==='error'&&!expected) errors.push(m.text());
  });
  try {
    const events=original.events||original.result.events;
    const artifacts=original.artifacts||original.result.artifacts;
    const at=seq=>{
      const shown=events.filter(e=>e.seq<=seq);
      const keys=new Set(shown.map(e=>e.artifact).filter(Boolean));
      const steps=original.steps.filter(s=>shown.some(e=>e.step===s.step)).map(s=>{
        const done=shown.find(e=>e.step===s.step&&['step_finished','step_skipped'].includes(e.type));
        return {...s,status:done?.type==='step_skipped'?'skip':done?done.status:'running',ms:done?s.ms:0};
      });
      return {id:'ui-fixture',state:'running',steps,events:shown,artifacts:Object.fromEntries([...keys].map(k=>[k,artifacts[k]])),elapsed_ms:shown.at(-1)?.at_ms||0,result:null,error:null};
    };
    const seqFor=key=>events.find(e=>e.artifact===key)?.seq;
    let snapshot=at(events.find(e=>e.step==='scene'&&e.type==='step_started').seq);
    let startFailure=false;
    await page.route('**/api/run',route=>route.fulfill(startFailure?{status:503,json:{detail:'UI fixture: 启动失败'}}:{json:{job:'ui-fixture'}}));
    await page.route('**/api/job/ui-fixture',route=>route.fulfill({json:snapshot}));
    await page.addInitScript(()=>sessionStorage.setItem('studio-welcomed','1'));
    await page.goto(base);
    await page.locator('#audience').fill('大学新生');
    await page.locator('#scenario').fill('图书馆');
    await page.locator('#product').fill('HUAWEI MateBook 14（鸿蒙版）');
    await page.locator('#go').click();
    const current=id=>page.locator(`.turn-card.is-current[data-stage="${id}"]`);
    await current('scene').waitFor();
    assert.equal(await page.locator('.phase-dot.current[data-phase="scene"]').count(),1);
    const barBox=await page.locator('.rotation-footer').boundingBox();
    const firstCardBox=await current('scene').boundingBox();
    assert.ok(barBox.y+barBox.height<=firstCardBox.y,'larger horizontal progress sits above the content card');
    await page.evaluate(()=>{window.progressSceneNode=document.querySelector('.phase-dot[data-phase="scene"]')});
    assert.equal(await current('scene').locator('.bot-portrait').count(),1);
    assert.ok(await current('scene').locator('.activity-row').count()>0);
    assert.equal(await current('scene').locator('.activity-spinner').count(),1);
    assert.ok(!(await current('scene').innerText()).includes(artifacts.plan.decision_reason),'pending step cannot invent a decision');
    await page.screenshot({path:path.join(output,'rotation-scene.png')});
    const firstElapsed=Number((await page.locator('#process-elapsed').innerText()).match(/\d+/)[0]);
    await page.waitForFunction(min=>Number(document.querySelector('#process-elapsed').textContent.match(/\d+/)[0])>=min,firstElapsed+2);
    snapshot=at(seqFor('brief'));
    await page.waitForFunction(task=>document.querySelector('.is-current[data-stage="scene"]')?.textContent.includes(task),artifacts.brief.user_problem);
    assert.ok((await current('scene').innerText()).includes(artifacts.brief.audience));
    assert.ok((await current('scene').innerText()).includes(artifacts.brief.scenario));
    assert.ok((await current('scene').innerText()).includes('本次判断摘要'));
    await page.screenshot({path:path.join(output,'scene-analysis.png')});
    report.push('scene exposes real audience, scenario, task and returned decision summary; clock advances across repeated unchanged polls');
    snapshot=at(seqFor('sources'));
    await current('sources').waitFor();
    assert.ok((await current('sources').innerText()).includes('跳过推荐'));
    assert.equal(await page.locator('.turn-card.is-current').count(),1);
    snapshot=at(seqFor('plan'));
    await current('plan').waitFor();
    await page.waitForFunction(()=>!document.querySelector('.is-leaving'));
    const selected=artifacts.plan.angles.find(a=>a.id===artifacts.plan.selected_angle);
    assert.ok(!(await current('plan').innerText()).includes(selected.title));
    assert.ok(!(await current('plan').innerText()).includes(artifacts.plan.decision_reason));
    assert.ok((await current('plan').innerText()).includes(artifacts.evidence.facts[0].source.path));
    assert.ok(await current('plan').locator('.activity-row.knowledge').count()>0);
    await page.screenshot({path:path.join(output,'rotation-plan.png')});
    await current('plan').getByRole('button',{name:'全部处理记录'}).click();
    await page.locator('#step-dialog[open]').waitFor();
    assert.equal(await page.locator('.evidence-record').count(),artifacts.evidence.facts.length);
    assert.ok((await page.locator('#step-dialog-body').innerText()).includes(artifacts.evidence.facts[0].text));
    assert.ok((await page.locator('#step-dialog-body').innerText()).includes('另一个角度'));
    await page.waitForResponse(r=>r.url().endsWith('/api/job/ui-fixture'));
    await page.waitForResponse(r=>r.url().endsWith('/api/job/ui-fixture'));
    assert.equal(await page.locator('.turn-card.is-current').count(),1);
    assert.equal(await page.locator('#step-dialog[open]').count(),1);
    await page.locator('#step-dialog [data-close-dialog]').click();
    report.push('original Bot + actual operations, loading and source paths; no conceptual headline or marketing goal; complete evidence details; duplicate polls stay stable');

    snapshot=at(events.find(e=>e.step==='compose'&&e.type==='step_started').seq);
    await page.locator('.is-leaving[data-stage="plan"]').waitFor();
    assert.equal(await current('compose').count(),1);
    assert.equal(await current('compose').getAttribute('class').then(v=>v.includes('is-entering')),true);
    const animation=await page.locator('.is-leaving').evaluate(n=>getComputedStyle(n).animationName);
    assert.equal(animation,'stage-leave');
    await page.screenshot({path:path.join(output,'rotation-transition.png')});
    await page.waitForFunction(()=>!document.querySelector('.is-leaving'));
    assert.equal(await page.locator('.turn-card').count(),1);
    assert.equal(await current('compose').locator('.activity-spinner').evaluate(n=>getComputedStyle(n).animationName),'activity-load');
    assert.equal(await page.locator('.phase-dot.current[data-phase="compose"]').count(),1);
    assert.equal(await page.locator('.phase-dot[data-phase="scene"] .phase-line.done').count(),1);
    assert.equal(await page.locator('.phase-dot[data-phase="compose"] .phase-line.running').count(),1);
    assert.equal(await page.evaluate(()=>window.progressSceneNode===document.querySelector('.phase-dot[data-phase="scene"]')),true,'completed line segments retain their nodes during live updates');
    assert.ok((await current('compose').innerText()).includes(artifacts.evidence.facts[0].source.path));
    assert.ok(!(await current('compose').innerText()).includes(artifacts.plan.goal));
    await page.screenshot({path:path.join(output,'activity-writing.png')});
    snapshot=at(seqFor('draft:1'));
    snapshot.steps=snapshot.steps.map(s=>s.step==='compose'?{...s,status:'done'}:s);
    report.push('previous Bot slides down and fades; next Bot enters from above; outgoing DOM is removed');

    snapshot.steps.push({step:'verify',label:'规则检查',status:'done',ms:8},{step:'judge',label:'独立评审',status:'running',ms:0,started_ms:snapshot.elapsed_ms});
    await current('review').waitFor();
    assert.equal(await current('review').locator('[data-tool="verify"].done').count(),1);
    assert.equal(await current('review').locator('[data-tool="judge"].running').count(),1);
    report.push('one review stage retains simultaneous deterministic-check and independent-review states');

    // Branch fixtures only: exercise a missing-evidence lookup and a targeted revision.
    const problem={where:'lead',index:-1,type:'expression',quote:artifacts['draft:1'].lead,detail:'切入需要更具体',direction:'落到查资料的任务'};
    const after=clone(artifacts['draft:1']);after.lead='去图书馆，把今天要看的资料先带齐。';
    snapshot.steps=snapshot.steps.map(s=>({...s,status:s.status==='running'?'done':s.status}));
    snapshot.artifacts['review:1']={overall:'needs_fix',problems:[problem]};
    snapshot.steps.push({step:'lookup',label:'补查本型号资料',status:'running',ms:0});
    await current('lookup').waitFor();
    snapshot.artifacts.lookup={reason:'本型号资料仍无相应依据，删除承诺。',added:0};
    snapshot.steps.at(-1).status='done';
    snapshot.steps.push({step:'repair',label:'定向修订',status:'running',ms:0});
    await current('repair').waitFor();
    assert.ok((await current('repair').innerText()).includes(problem.detail));
    snapshot.artifacts.revision={changes:[{where:'lead',index:-1,before:problem.quote,after:after.lead,problems:[problem],fact_refs:[]}],issues:[problem.detail]};
    snapshot.artifacts['draft:2']=after;
    await page.waitForFunction(()=>document.querySelector('.is-current .stage-activities').textContent.includes('已修改 1 处文段'));
    await current('repair').getByRole('button',{name:'全部处理记录'}).click();
    assert.equal(await page.locator('.revision-record ins').innerText(),after.lead);
    await page.screenshot({path:path.join(output,'rotation-revision-details.png')});
    await page.locator('#step-dialog [data-close-dialog]').click();
    snapshot.steps.at(-1).status='done';
    snapshot.steps.push({step:'reverify',label:'终稿规则检查',status:'done',ms:8},{step:'rejudge',label:'独立复审',status:'running',ms:0});
    await current('recheck').waitFor();
    assert.equal(await page.locator('.phase-dot.current[data-phase="recheck"]').count(),1);
    assert.equal(await page.locator('.phase-dot').count(),8,'only actual lookup, repair and recheck extend the horizontal line');
    await current('recheck').getByRole('button',{name:'全部处理记录'}).click();
    report.push('actual branch presentation: lookup -> targeted revision -> recheck; located before/after remains available on demand');

    const result=clone(original.result);
    result.article=after;result.status='ok_with_flags';result.verification.remaining=['复审仍有待确认项'];
    result.verification.judge.overall='needs_fix';result.verification.article_version=2;
    result.artifacts={...snapshot.artifacts,final:{article:after,state:'needs_review',version:2,remaining:['复审仍有待确认项']}};
    snapshot={...snapshot,state:'done',result,artifacts:result.artifacts,steps:snapshot.steps.map(s=>({...s,status:s.status==='running'?'done':s.status}))};
    await page.locator('#view-result').waitFor({state:'visible'});
    assert.ok(page.url().endsWith('#process'));
    assert.equal(await page.locator('#step-dialog[open]').count(),1,'completion must not close details the reader is inspecting');
    await page.locator('#step-dialog [data-close-dialog]').click();
    // Result is immediately usable, even if the small presentation queue has not finished.
    await page.locator('#view-result').click();
    await page.locator('#preview').waitFor({state:'visible'});
    assert.ok((await page.locator('#work-review-status').innerText()).includes('自动评审发现问题'));
    await page.getByRole('tab',{name:'事实核验'}).click();
    assert.ok((await page.locator('#evidence').innerText()).includes('F1'));
    await page.getByRole('tab',{name:'生成过程'}).click();
    await page.reload();
    await current('finish').waitFor();
    assert.ok((await current('finish').innerText()).includes('自动评审发现问题'));
    assert.equal(await page.locator('.is-leaving').count(),0,'refresh must not replay historical steps');
    report.push('completion never blocks work; final flagged state stays truthful; refresh directly restores final stage');

    for(const [width,height] of [[1440,900],[1280,720],[768,1024],[390,844]]) {
      await page.setViewportSize({width,height});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`horizontal fit at ${width}`);
      const card=await current('finish').boundingBox();
      assert.ok(card.x>=0&&card.x+card.width<=width,`card fits ${width}`);
      await page.screenshot({path:path.join(output,`rotation-${width}.png`),fullPage:true});
    }
    await page.emulateMedia({reducedMotion:'reduce'});
    assert.equal(await current('finish').evaluate(n=>getComputedStyle(n).animationName),'none');
    await page.evaluate(()=>{window.ProcessView.reset();const root=window.ProcessView.update({state:'running',steps:[{step:'scene',status:'done'}]});document.querySelector('#flow').replaceChildren(root);window.ProcessView.update({state:'running',steps:[{step:'scene',status:'done'},{step:'model',status:'done'}]});});
    await current('sources').waitFor();
    assert.equal(await page.locator('.is-entering,.is-leaving').count(),0,'reduced motion changes stages without movement');
    report.push('1440/1280/768/390 fit; horizontal progress stays above the card, extends for actual branches, and retains completed segments; reduced motion supported');

    // Explicit partial-result fixture: rules passed but the automatic model review hit the budget.
    const partial=clone(original.result);
    partial.status='ok_with_flags';partial.budget={exhausted:true,limit_seconds:90};partial.total_ms=90000;
    partial.verification={...partial.verification,article_version:1,judge:{overall:'not_reviewed',problems:[]},remaining:['独立评审未通过或未完成，需要复核。','时间预算耗尽，必要修订或复核尚未完成。']};
    partial.artifacts={...clone(artifacts),'rules:1':{issues:[],platform_issues:[]},final:{version:1,state:'needs_review',remaining:partial.verification.remaining,article:partial.article}};
    delete partial.artifacts['review:1'];delete partial.artifacts['review:2'];delete partial.artifacts['draft:2'];
    snapshot={id:'ui-fixture',state:'done',steps:[{step:'verify',status:'done',ms:8,started_ms:75000},{step:'judge',status:'error',ms:15000,started_ms:75000,detail:{error:'时间预算耗尽，结果未返回'}}],events:[],artifacts:partial.artifacts,result:partial,elapsed_ms:90000};
    await page.reload();await current('finish').waitFor();
    assert.ok((await current('finish').innerText()).includes('自动评审未完成'));
    assert.ok((await current('finish').innerText()).includes('90 秒总预算'));
    assert.equal(await current('finish').locator('.activity-row.incomplete').count(),1);
    assert.equal(await current('finish').locator('[data-tool="verify"].done').count(),1);
    assert.ok(!(await current('finish').innerText()).includes('独立评审未通过或未完成'));
    await page.screenshot({path:path.join(output,'budget-review-clear.png')});
    await page.getByRole('tab',{name:'事实核验'}).click();
    await page.getByRole('tab',{name:'审核记录'}).click();
    assert.ok((await page.locator('#verify').innerText()).includes('90 秒总预算'));
    await page.getByRole('tab',{name:'生成过程'}).click();
    report.push('budget-limited automatic review is labelled incomplete with its cause; passed rules stay passed; full review page agrees');

    snapshot={id:'ui-fixture',state:'error',steps:[],events:[],artifacts:{},result:null,error:'UI fixture: 资料读取失败'};
    await page.reload();
    await page.getByText('运行出错：UI fixture: 资料读取失败').waitFor();
    assert.ok((await current('finish').innerText()).includes('已中断'));
    snapshot={id:'ui-fixture',state:'done',steps:[],events:[],artifacts:{},result:{status:'budget_exceeded',questions:['UI fixture: 时间预算用尽']},error:null};
    await page.evaluate(()=>sessionStorage.setItem('studio-active-job',JSON.stringify({id:'ui-fixture',task:{},mode:'structured'})));
    await page.reload();
    await page.getByText('本次创作已到时间预算。').waitFor();
    assert.equal(await page.locator('#view-result').isVisible(),false);
    assert.equal(await page.locator('#stage').isVisible(),false);
    assert.ok((await current('finish').innerText()).includes('审核未完成'));
    expected503=true;startFailure=true;
    await page.getByRole('tab',{name:'创作简报'}).click();
    await page.locator('#audience').fill('大学新生');await page.locator('#scenario').fill('图书馆');await page.locator('#go').click();
    await page.getByText('UI fixture: 启动失败',{exact:true}).waitFor();
    assert.equal(await page.locator('#process-live').innerText(),'执行中断');
    report.push('startup/task failures and budget without a draft expose recovery and never claim a passed review');
    assert.deepEqual(errors,[]);
    report.push('zero unexpected runtime or console errors; injected HTTP 503 is expected');
    fs.writeFileSync(path.join(output,'rotation-report.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify(report,null,2));

    const real=await browser.newPage({viewport:{width:1440,height:900}});
    await real.addInitScript(id=>{sessionStorage.setItem('studio-welcomed','1');sessionStorage.setItem('studio-active-job',JSON.stringify({id,task:{},mode:'structured'}));},jobId);
    await real.goto(`${base}/#process`);
    await real.locator('#view-result').waitFor({state:'visible'});
    await real.screenshot({path:path.join(output,'rotation-real-complete.png')});
    await real.close();
  } finally {await browser.close();}
}
main().catch(error=>{console.error(error);process.exit(1);});
