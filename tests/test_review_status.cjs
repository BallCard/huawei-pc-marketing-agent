const test=require('node:test');
const assert=require('node:assert/strict');
const review=require('../src/mvp/web/review-status.js');

test('budget-interrupted review is explicitly incomplete, not a factual rejection',()=>{
  const result=review({budget:{exhausted:true,limit_seconds:90},verification:{judge:{overall:'not_reviewed'},remaining:['独立评审未通过或未完成，需要复核。','时间预算耗尽']}});
  assert.equal(result.state,'incomplete');
  assert.ok(result.detail.includes('90 秒'));
  assert.ok(!result.label.includes('发现问题'));
});

test('actual failed review keeps its specific issue, while pass needs no manual review',()=>{
  const failed=review({verification:{judge:{overall:'needs_fix',problems:[{detail:'重量缺少配置限定'}]}}});
  assert.equal(failed.state,'needs_fix');assert.equal(failed.detail,'重量缺少配置限定');
  const passed=review({verification:{judge:{overall:'pass'},remaining:[]}});
  assert.equal(passed.needsReview,false);
});

test('a final-version incomplete review cannot borrow the initial pass',()=>{
  const result=review({verification:{judge:{overall:'not_reviewed'}}},{'review:1':{overall:'pass'},'draft:2':{},final:{version:2,state:'needs_review',remaining:[]}},[{step:'rejudge',status:'error',detail:{error:'连接中断'}}]);
  assert.equal(result.state,'incomplete');assert.equal(result.detail,'连接中断');
});

test('manual adoption is distinct from automatic pass and never rewrites the verdict',()=>{
  const source={verification:{judge:{overall:'needs_fix',problems:[{detail:'表达问题'}]}},human_review:{state:'adopted'}};
  const status=review(source);
  assert.equal(status.state,'human_adopted');assert.equal(status.passed,false);
  assert.equal(status.needsReview,false);assert.equal(status.automaticPassed,false);
  assert.equal(source.verification.judge.overall,'needs_fix');
});

test('triage distinguishes automatic correction from the small set of important unknowns',()=>{
  const verification={judge:{overall:'needs_fix',problems:[{detail:'重量条件错误'}]},triage:{human:0,automatic:2,optional:4,dismissed:2,merged:0}};
  let status=review({verification});
  assert.equal(status.needsReview,true);assert.equal(status.label,'待自动修订或重试');
  verification.triage.human=1;
  status=review({verification});assert.equal(status.label,'1 项重要条件待确认');
  assert.equal(review({verification,automatic_followup:{state:'continuing',mode:'automatic'}}).state,'continuing');
});

test('optional suggestions do not create a manual review gate on an otherwise verified article',()=>{
  const status=review({verification:{judge:{overall:'pass',problems:[],improvements:[{type:'expression',detail:'语气偏好'}]},remaining:[],
    triage:{human:0,automatic:0,optional:1,dismissed:0,merged:0}}});
  assert.equal(status.passed,true);assert.equal(status.needsReview,false);
});
