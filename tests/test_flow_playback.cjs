const { test } = require('node:test');
const assert = require('node:assert/strict');
const FlowPlayback = require('../src/mvp/web/flow-playback.js');

test('default browser timers are not rebound to the player object', () => {
  const vm = require('node:vm');
  const fs = require('node:fs');
  let timerId = 0;
  const context = { module: { exports: {} }, performance: { now: () => 0 },
    setTimeout: function () { 'use strict'; assert.equal(this, undefined); return ++timerId; },
    clearTimeout: function () { 'use strict'; assert.equal(this, undefined); }
  };
  vm.runInNewContext(fs.readFileSync(require.resolve('../src/mvp/web/flow-playback.js'), 'utf8'), context);
  const player = new context.module.exports();
  player.update(['done', 'done']);
  player.pause();
  assert.equal(timerId, 1);
});

function fixture() {
  let now = 0;
  let id = 0;
  const timers = new Map();
  const history = [];
  const player = new FlowPlayback({
    now: () => now,
    setTimer: (fn, ms) => { timers.set(++id, { fn, at: now + ms }); return id; },
    clearTimer: key => timers.delete(key),
    onChange: state => history.push(state)
  });
  function tick(ms) {
    const end = now + ms;
    while (true) {
      const due = [...timers].filter(([, timer]) => timer.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
      if (!due) break;
      timers.delete(due[0]);
      now = due[1].at;
      due[1].fn();
    }
    now = end;
  }
  return { player, history, tick, timers };
}

test('a batched snapshot presents four fast stages one by one', () => {
  const { player, tick, history } = fixture();
  player.update(['done', 'done', 'done', 'done', 'running']);
  assert.deepEqual(player.snapshot().states, ['settling', 'wait', 'wait', 'wait', 'wait']);
  tick(649);
  assert.equal(player.snapshot().states[0], 'settling');
  tick(1);
  assert.equal(player.snapshot().handoffFrom, 0);
  assert.deepEqual(player.snapshot().states, ['done', 'wait', 'wait', 'wait', 'wait']);
  tick(180);
  assert.deepEqual(player.snapshot().states, ['done', 'settling', 'wait', 'wait', 'wait']);
  tick(2490);
  assert.deepEqual(player.snapshot().states, ['done', 'done', 'done', 'done', 'running']);
  const counts = history.map(state => state.states.filter(status => status === 'done').length);
  assert.ok(counts.every((count, i) => !i || count - counts[i - 1] <= 1));
});

test('real running work cannot be completed by the presentation clock', () => {
  const { player, tick } = fixture();
  player.update(['running', 'wait']);
  tick(30000);
  assert.deepEqual(player.snapshot().states, ['running', 'wait']);
  player.update(['done', 'running']);
  assert.equal(player.snapshot().states[0], 'done');
  tick(180);
  assert.deepEqual(player.snapshot().states, ['done', 'running']);
});

test('polling does not restart the visible stage or its handoff', () => {
  const { player, tick } = fixture();
  player.update(['done', 'done']);
  tick(400);
  player.update(['done', 'done']);
  tick(250);
  assert.equal(player.snapshot().states[0], 'done');
  tick(80);
  player.update(['done', 'done']);
  tick(100);
  assert.equal(player.snapshot().activeIndex, 1);
});

test('result navigation can wait for the last tick and completion hold', async () => {
  const { player, tick } = fixture();
  player.update(['done', 'done']);
  let settled = false;
  const ready = player.whenSettled().then(() => { settled = true; });
  tick(1759);
  await Promise.resolve();
  assert.equal(settled, false);
  tick(1);
  await ready;
  assert.equal(settled, true);
  assert.deepEqual(player.snapshot().states, ['done', 'done']);
});

test('an error interrupts pending animation immediately', async () => {
  const { player, tick, history, timers } = fixture();
  player.update(['done', 'done', 'done']);
  player.update(['done', 'error', 'skip']);
  await player.whenSettled();
  assert.deepEqual(player.snapshot().states, ['done', 'error', 'skip']);
  assert.equal(timers.size, 0);
  const updates = history.length;
  tick(10000);
  assert.equal(history.length, updates);
});

test('refresh catches up immediately instead of replaying completed stages', async () => {
  const { player, tick, timers } = fixture();
  player.update(['done', 'done', 'running'], { immediate: true });
  assert.deepEqual(player.snapshot().states, ['done', 'done', 'running']);
  tick(2000);
  player.update(['done', 'done', 'done'], { immediate: true });
  await player.whenSettled();
  assert.equal(timers.size, 0);
  assert.equal(player.snapshot().pending, false);
});

test('a new run cancels old timers and releases an old completion wait', async () => {
  const { player, tick } = fixture();
  player.update(['done', 'done']);
  const oldWait = player.whenSettled();
  player.reset();
  await oldWait;
  player.update(['running', 'wait']);
  tick(10000);
  assert.deepEqual(player.snapshot().states, ['running', 'wait']);
});

test('repair reopens verification and then hands off to the reviewer', () => {
  const { player, tick } = fixture();
  player.update(['done', 'done', 'wait'], { immediate: true });
  player.update(['done', 'running', 'wait']);
  assert.deepEqual(player.snapshot().states, ['done', 'running', 'wait']);
  tick(2000);
  player.update(['done', 'done', 'running']);
  tick(180);
  assert.deepEqual(player.snapshot().states, ['done', 'done', 'running']);
});
