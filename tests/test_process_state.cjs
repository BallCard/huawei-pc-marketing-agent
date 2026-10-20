const test = require('node:test');
const assert = require('node:assert/strict');
const ProcessState = require('../src/mvp/web/process-state.js');

test('polls deduplicate event ids and retain ordered decisions across refresh', () => {
  const state = new ProcessState();
  const first = {state:'running', steps:[{step:'scene',status:'done'}], events:[{seq:2,type:'artifact_ready'},{seq:1,type:'step_started'}], artifacts:{brief:{audience:'学生'}}};
  assert.deepEqual(state.ingest(first).map(e=>e.seq), [1,2]);
  assert.equal(state.ingest(first).length, 0);
  state.ingest({state:'done',events:[{seq:3,type:'workflow_finished'}],artifacts:{final:{version:2,state:'needs_review'}}});
  assert.deepEqual(state.orderedEvents().map(e=>e.seq), [1,2,3]);
  assert.equal(state.artifacts.brief.audience, '学生');
  assert.equal(state.artifacts.final.state,'needs_review');
  const restored = new ProcessState();
  restored.ingest({...first, events:state.orderedEvents(),artifacts:state.artifacts,state:'done'});
  assert.deepEqual(restored.orderedEvents(),state.orderedEvents());
  assert.deepEqual(restored.artifacts,state.artifacts);
});

test('simultaneous steps and repair versions remain intact beneath presentation', () => {
  const state = new ProcessState();
  state.ingest({state:'running', steps:[{step:'verify',status:'running'},{step:'judge',status:'running'}], artifacts:{'draft:1':{title:'前'}}});
  assert.equal(state.steps.filter(s=>s.status==='running').length,2);
  state.ingest({state:'running',steps:[{step:'repair',status:'running'}],artifacts:{'draft:2':{title:'后'}}});
  assert.equal(state.artifacts['draft:1'].title,'前');
  assert.equal(state.artifacts['draft:2'].title,'后');
  state.reset();
  assert.equal(state.lastSeq,0);
  assert.deepEqual(state.artifacts,{});
});
