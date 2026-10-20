const test = require('node:test');
const assert = require('node:assert/strict');
const describe = require('../src/mvp/web/process-activity.js');
const stage=(id,status='running')=>({id,status,entries:[]});
const fact={id:'F1',sid:'S2',text:'机身约 1.3 kg，仅配置 A',source:{label:'产品事实·尺寸与重量',path:'P1-产品参数库/测试电脑/产品事实.md'}};

test('pending planning displays actual input documents, never a made-up angle or future selection',()=>{
  const result=describe(stage('plan'),{artifacts:{sources:{model:'测试电脑',snippets:[{sid:'S2',text:fact.text,source:fact.source}]}},steps:[]});
  assert.equal(result.records[0].path,fact.source.path);
  assert.ok(result.note.includes('1 条候选资料'));
  assert.ok(!result.title.includes('已选定'));
  assert.ok(!JSON.stringify(result).includes('值得讲'));
});

test('writing exposes raw selected evidence and sources instead of the article angle and marketing goal',()=>{
  const result=describe(stage('compose'),{artifacts:{evidence:{facts:[fact]},plan:{goal:'收藏笔记并加入开学选购对比清单',angles:[{title:'开学移动自习'}]}},steps:[{step:'style',status:'done',detail:{spec:{name:'小红书'}}}]});
  assert.equal(result.title,'正在生成小红书初稿');
  assert.equal(result.records[0].detail,fact.text);
  assert.equal(result.records[0].path,fact.source.path);
  assert.ok(!JSON.stringify(result).includes('收藏笔记'));
  assert.ok(!JSON.stringify(result).includes('开学移动自习'));
});

test('an official image URL in a cached result is not labelled as a current network request',()=>{
  const result=describe(stage('sources'),{artifacts:{sources:{image_search:{status:'cached',reason:'复用已核验图片',pages:['https://consumer.huawei.com/cn/laptops/test/']}}}});
  assert.equal(result.records[0].kind,'cache');
  assert.equal(result.records.some(r=>r.kind==='web'),false);
  assert.ok(!result.title.includes('联网'));
});

test('live web activity is displayed only from an actual tool event and stops on termination',()=>{
  const event={seq:1,type:'tool_activity',step:'retrieve',operation:'page',resource:'page1',kind:'web',status:'running',label:'正在读取华为官网页面',url:'https://consumer.huawei.com/cn/laptops/test/'};
  const snapshot={events:[event],artifacts:{}};
  const result=describe(stage('sources'),snapshot);
  assert.equal(result.title,event.label);
  assert.equal(result.records[0].path,event.url);
  assert.equal(result.records[0].status,'running');
  const terminated=describe(stage('sources','error'),{...snapshot,state:'error'});
  assert.ok(!terminated.records.some(r=>r.status==='running'));
  assert.ok(terminated.title.includes('未完成'));
});

test('recheck uses final-version review, preserving pending and failed states',()=>{
  const result=describe(stage('recheck'),{steps:[{step:'reverify',status:'done'},{step:'rejudge',status:'running'}],artifacts:{'review:1':{overall:'pass'},'rules:2':{issues:[],platform_issues:[]}}});
  assert.equal(result.records[1].status,'running');
  assert.ok(!result.records[1].detail.includes('未发现'));
  const failed=describe(stage('finish','done'),{state:'done',artifacts:{final:{version:2,state:'needs_review',remaining:['缺少配置条件']}}});
  assert.ok(failed.title.includes('终稿 v2'));
  assert.ok(failed.records.some(r=>r.detail==='缺少配置条件'));
});

test('scene card shows actual audience, scenario, task and returned decision summary',()=>{
  const snapshot={artifacts:{request:{audience:'大学新生',scenario:'图书馆',constraints:['不提价格']},brief:{user_problem:'每天背电脑去图书馆查资料',tradeoffs:['携带负担与屏幕尺寸之间的取舍'],top_dims:['portability','display'],hard_constraints:['不提价格']}}};
  const result=describe(stage('scene','done'),snapshot);
  assert.equal(result.records[0].detail,'大学新生 · 图书馆');
  assert.ok(result.records.some(r=>r.detail==='每天背电脑去图书馆查资料'));
  assert.ok(result.records.some(r=>r.label==='本次判断摘要'&&r.detail.includes('携带负担与屏幕尺寸')));
  const pending=describe(stage('scene'),{artifacts:{request:snapshot.artifacts.request}});
  assert.ok(!pending.records.some(r=>r.label==='本次判断摘要'),'no invented analysis before return');
});

test('budget-interrupted automatic review shows its cause and avoids duplicate generic manual warnings',()=>{
  const result=describe(stage('finish','done'),{state:'done',result:{budget:{exhausted:true,limit_seconds:90},verification:{judge:{overall:'not_reviewed'}}},steps:[{step:'judge',status:'error',detail:{error:'时间预算耗尽，结果未返回'}}],artifacts:{final:{version:1,state:'needs_review',remaining:['独立评审未通过或未完成，需要复核。','时间预算耗尽，必要修订或复核尚未完成。']}}});
  assert.ok(result.title.includes('自动评审未完成'));
  assert.equal(result.records.length,1);
  assert.ok(result.records[0].detail.includes('90 秒总预算'));
  assert.equal(result.records[0].status,'incomplete');
});
