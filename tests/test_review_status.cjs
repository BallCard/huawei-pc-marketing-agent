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
