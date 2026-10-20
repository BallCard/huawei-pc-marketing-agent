const test=require('node:test');
const assert=require('node:assert/strict');
const {ProcessClock,phaseDuration}=require('../src/mvp/web/process-clock.js');

test('unchanged progress snapshots cannot reset the clock during a long model call',()=>{
  let now=0;const clock=new ProcessClock(()=>now);
  clock.update({state:'running',elapsed_ms:8000});
  for(let poll=1;poll<=10;poll++){now=poll*900;clock.update({state:'running',elapsed_ms:8000});}
  assert.equal(clock.read(),17000);
  now+=2000;assert.equal(clock.read(),19000);
});

test('refresh accepts server elapsed time; terminal time freezes at authoritative total; reset starts fresh',()=>{
  let now=0;const clock=new ProcessClock(()=>now);
  clock.update({state:'running',elapsed_ms:42000});assert.equal(clock.read(),42000);
  now=3000;clock.update({state:'done',elapsed_ms:43000,result:{total_ms:44000}});
  now=50000;assert.equal(clock.read(),44000);
  clock.reset();clock.update({state:'running',elapsed_ms:20});assert.equal(clock.read(),20);
});

test('phase timers exclude earlier parallel preparation and do not add overlapping checks',()=>{
  const source={id:'sources',status:'running',entries:[{step:'style',started_ms:0,ms:20,status:'done'},{step:'model',started_ms:8000,ms:2000,status:'done'},{step:'retrieve',started_ms:10000,ms:0,status:'running'}]};
  assert.equal(phaseDuration(source,15000),7000);
  const review={id:'review',status:'done',entries:[{step:'verify',started_ms:20000,ms:10,status:'done'},{step:'judge',started_ms:20000,ms:7000,status:'done'}]};
  assert.equal(phaseDuration(review,90000),7000);
  assert.equal(phaseDuration({id:'scene',status:'done',entries:[{step:'scene',started_ms:0,ms:8000,status:'done'}]},90000),8000);
});
