const test = require('node:test');
const assert = require('node:assert/strict');
const {StageRotation, deriveStages} = require('../src/mvp/web/stage-rotation.js');

function clock() {
  let time = 0, serial = 0;
  const timers = new Map(), changes = [];
  const rotation = new StageRotation({holdMs:1000,now:()=>time,
    setTimer:(fn,ms)=>{const id=++serial;timers.set(id,{fn,at:time+ms});return id;},
    clearTimer:id=>timers.delete(id),onChange:change=>changes.push(change)});
  return {rotation,changes,advance(ms){
    const end=time+ms;
    while([...timers.values()].some(t=>t.at<=end)) {
      const [id,timer]=[...timers].sort((a,b)=>a[1].at-b[1].at)[0];
      time=timer.at;timers.delete(id);timer.fn();
    }
    time=end;
  }};
}
const phase=(id,status='done')=>({id,status});

test('a running stage holds; completed fast phases rotate once, in order',()=>{
  const c=clock();
  c.rotation.update([phase('scene','running')]);
  c.advance(5000);
  assert.equal(c.rotation.current,'scene');
  c.rotation.update([phase('scene'),phase('sources'),phase('plan','running')]);
  assert.equal(c.rotation.current,'scene','new scene results must remain visible after a long loading state');
  c.rotation.update([phase('scene'),phase('sources'),phase('plan','running')]);
  c.advance(1000);
  assert.equal(c.rotation.current,'sources');
  c.advance(1000);
  assert.equal(c.rotation.current,'plan');
  c.advance(2000);
  assert.deepEqual(c.changes.filter(x=>x.rotate).map(x=>x.stage.id),['scene','sources','plan']);
});

test('later polls update the visible result without replaying its entrance',()=>{
  const c=clock();
  c.rotation.update([phase('plan','running')]);
  c.rotation.update([{...phase('plan'),decision:'actual returned decision'}]);
  assert.equal(c.changes.at(-1).rotate,false);
  assert.equal(c.changes.at(-1).stage.decision,'actual returned decision');
  assert.equal(c.changes.filter(x=>x.rotate).length,1);
});

test('refresh chooses the current real stage and drops historical presentation',()=>{
  const c=clock();
  c.rotation.update([phase('scene'),phase('plan'),phase('review','running')],{restore:true});
  assert.equal(c.rotation.current,'review');
  assert.deepEqual(c.rotation.queue,[]);
  c.rotation.update([phase('scene'),phase('plan'),phase('review'),phase('finish')],{restore:true});
  assert.equal(c.rotation.current,'finish');
  c.advance(10000);
  assert.equal(c.rotation.current,'finish');
  assert.equal(c.changes.some(x=>x.rotate),false);
});

test('failure or budget termination immediately clears pending presentation',()=>{
  const c=clock();
  c.rotation.update([phase('scene'),phase('plan'),phase('compose')]);
  c.rotation.update([phase('scene'),phase('plan'),phase('compose','error'),phase('finish')],{urgent:true});
  assert.equal(c.rotation.current,'finish');
  c.advance(10000);
  assert.equal(c.rotation.current,'finish');
  assert.equal(c.rotation.queue.length,0);
});

test('追问续跑从定格环节接着走，收尾环节不提前复用',()=>{
  const c=clock();
  c.rotation.update([phase('scene'),phase('sources')]);c.advance(2000);
  c.rotation.update([phase('scene'),phase('sources'),phase('finish','waiting')],{urgent:true});
  assert.equal(c.rotation.current,'finish');
  c.rotation.release(['finish']);
  c.rotation.update([{...phase('scene')},{...phase('sources')},phase('plan','running')],{restore:true});
  assert.equal(c.rotation.current,'plan','续跑回到新出现的环节，而不是第一个环节');
  assert.deepEqual(c.rotation.queue,[]);
  c.rotation.update([phase('scene'),phase('sources'),phase('plan'),phase('finish')]);
  c.advance(10000);
  assert.equal(c.rotation.current,'finish');
});

test('tools and parallel checks are grouped; skipped recommendation is retained as a tool',()=>{
  const stages=deriveStages({state:'running',steps:[
    {step:'scene',status:'done'},{step:'style',status:'done'},
    {step:'model',status:'done'},{step:'recommend',status:'skip'},{step:'retrieve',status:'done'},
    {step:'extract',status:'done'},{step:'compose',status:'done'},
    {step:'verify',status:'done'},{step:'judge',status:'running'},
    {step:'lookup',status:'skip'},{step:'repair',status:'skip'}]});
  assert.deepEqual(stages.map(x=>x.id),['scene','sources','plan','compose','review']);
  assert.equal(stages.at(-1).status,'running');
  assert.equal(stages.find(x=>x.id==='sources').entries.find(x=>x.step==='recommend').status,'skip');
  assert.equal(deriveStages({state:'running',steps:[{step:'style',status:'running'}]}).length,0);
});

test('actual supplemental lookup, repair and recheck enter once in order; terminal state stops breathing',()=>{
  const c=clock();
  const stages=deriveStages({state:'done',steps:['scene','model','extract','compose','verify','judge','lookup','repair','reverify','rejudge'].map(step=>({step,status:'done'}))});
  c.rotation.update(stages);c.advance(10000);
  assert.deepEqual(c.changes.filter(x=>x.rotate).map(x=>x.stage.id),['scene','sources','plan','compose','review','lookup','repair','recheck','finish']);
  const failed=deriveStages({state:'error',steps:[{step:'judge',status:'running'}]});
  assert.equal(failed[0].status,'error');
  assert.equal(failed.at(-1).id,'finish');
});
