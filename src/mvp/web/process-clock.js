(function () {
  "use strict";
  class ProcessClock {
    constructor(now = () => performance.now()) { this.now = now; this.reset(); }
    reset() { this.base = 0; this.sampledAt = this.now(); this.running = false; this.floor = false; }
    // 追问续跑沿用同一条时间线：新任务的总时长再短，也不让「已用」往回跳。
    holdFloor() { this.floor = true; }
    read() { return this.base + (this.running ? Math.max(0, this.now() - this.sampledAt) : 0); }
    update(snapshot) {
      const previous = this.read(), running = snapshot.state === "running";
      const sample = running ? snapshot.elapsed_ms : snapshot.result?.total_ms ?? snapshot.elapsed_ms;
      const next = running ? Math.max(this.running ? previous : 0, Number(sample) || 0) : Number.isFinite(sample) ? sample : previous;
      this.base = !running && this.floor ? Math.max(previous, next) : next;
      this.sampledAt = this.now(); this.running = running;
    }
  }
  function phaseDuration(stage, elapsed) {
    let entries = (stage?.entries || []).filter(s => s.status !== "skip");
    if (stage?.id === "sources") entries = entries.filter(s => s.step !== "style");
    const timed = entries.filter(s => Number.isFinite(s.started_ms));
    if (!timed.length) return Math.max(0, ...entries.map(s => Number(s.ms) || 0));
    const start = Math.min(...timed.map(s => s.started_ms));
    const end = stage.status === "running" ? elapsed : Math.max(...timed.map(s => s.started_ms + (Number(s.ms) || 0)));
    return Math.max(0, end - start);
  }
  if (typeof module !== "undefined" && module.exports) module.exports = {ProcessClock, phaseDuration};
  else Object.assign(window, {ProcessClock, phaseDuration});
})();
