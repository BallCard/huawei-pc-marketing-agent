(function () {
  "use strict";
  const PHASES = [
    { id: "scene", label: "理解需求", role: "内容策划", bot: 0, steps: ["scene"] },
    { id: "sources", label: "准备依据", role: "内容策划", bot: 0, steps: ["model", "recommend", "strategy", "retrieve", "style"] },
    { id: "plan", label: "确定立意", role: "内容策划", bot: 0, steps: ["extract"] },
    { id: "compose", label: "图文创作", role: "创作编辑", bot: 5, steps: ["compose"] },
    { id: "review", label: "独立评审", role: "独立评审", bot: 7, steps: ["verify", "judge", "cross_review"] },
    { id: "lookup", label: "补查证据", role: "内容策划", bot: 0, steps: ["lookup"] },
    { id: "repair", label: "定向修订", role: "创作编辑", bot: 5, steps: ["repair"] },
    { id: "recheck", label: "终稿复核", role: "独立评审", bot: 7, steps: ["reverify", "rejudge", "recross_review"] },
    { id: "poster_image", label: "海报生成", role: "视觉创作", bot: 5, steps: ["poster_prepare", "poster_image"] },
    { id: "poster_review", label: "成图审核", role: "独立评审", bot: 7, steps: ["poster_review"] }
  ];

  function deriveStages(snapshot) {
    const steps = snapshot.steps || [];
    const terminal = ["done", "error"].includes(snapshot.state);
    const phases = [];
    for (const phase of PHASES) {
      const entries = steps.filter(s => phase.steps.includes(s.step));
      // Platform samples can prepare in parallel with the brief; they are a tool, not an earlier act.
      if (phase.id === "sources" && !entries.some(s => ["model", "strategy", "retrieve"].includes(s.step))) continue;
      if (!entries.some(s => s.status !== "skip")) continue;
      const error = entries.some(s => s.status === "error" || terminal && s.status === "running");
      const running = !terminal && entries.some(s => s.status === "running");
      phases.push({ ...phase, entries, status: error ? "error" : running ? "running" : "done" });
    }
    if (terminal) phases.push({ id: "finish", label: snapshot.state === "error" ? "创作中断" : snapshot.result?.status === "input_required" ? "暂未出稿" : "本次完成",
      role: "协作完成", bot: 7, entries: [], status: snapshot.state === "error" ? "error" : snapshot.result?.status === "need_info" ? "waiting" : "done" });
    return phases;
  }

  // Presentation only: each actual phase enters once. It never schedules a model or delays delivery.
  class StageRotation {
    constructor({ onChange = () => {}, now = () => performance.now(),
      setTimer = (fn, ms) => setTimeout(fn, ms), clearTimer = id => clearTimeout(id), holdMs = 1600 } = {}) {
      Object.assign(this, { onChange, now, setTimer, clearTimer, holdMs });
      this.reset();
    }
    reset() {
      if (this.timer != null) this.clearTimer(this.timer);
      this.timer = null;
      this.known = new Map();
      this.seen = new Set();
      this.queue = [];
      this.current = null;
      this.since = 0;
    }
    update(stages, { restore = false, urgent = false } = {}) {
      if (this.timer != null) this.clearTimer(this.timer);
      this.timer = null;
      const wasRunning = this.known.get(this.current)?.status === "running";
      for (const stage of stages) {
        this.known.set(stage.id, stage);
        if (!this.seen.has(stage.id)) { this.seen.add(stage.id); this.queue.push(stage.id); }
      }
      // Give newly returned results a readable moment, even after a long loading state.
      if (wasRunning && this.known.get(this.current)?.status !== "running") this.since = this.now();
      if (restore || urgent) {
        this.queue = [];
        this.current = stages.findLast(s => s.status === "running")?.id || stages.at(-1)?.id || null;
        this.since = this.now();
        this.emit(null, false);
        return;
      }
      this.advance();
    }
    advance() {
      const current = this.known.get(this.current);
      if (current?.status === "running" || !this.queue.length) { this.emit(null, false); return; }
      const remaining = this.holdMs - (this.now() - this.since);
      if (current && remaining > 0) {
        this.timer = this.setTimer(() => { this.timer = null; this.advance(); }, remaining);
        this.emit(null, false);
        return;
      }
      const previous = this.current;
      this.current = this.queue.shift();
      this.since = this.now();
      this.emit(previous, true);
      if (this.queue.length && this.known.get(this.current)?.status !== "running") {
        this.timer = this.setTimer(() => { this.timer = null; this.advance(); }, this.holdMs);
      }
    }
    // 续跑前丢掉一次性的收尾环节，让它在新一轮真正结束时再入场。
    release(ids) {
      for (const id of ids || []) {
        this.known.delete(id);
        this.seen.delete(id);
        this.queue = this.queue.filter(item => item !== id);
        if (this.current === id) this.current = null;
      }
      if (this.timer != null) { this.clearTimer(this.timer); this.timer = null; }
    }
    emit(previous, rotate) {
      this.onChange({ stage: this.known.get(this.current) || null,
        next: this.known.get(this.queue[0]) || null, previous, rotate });
    }
  }
  if (typeof module !== "undefined" && module.exports) module.exports = { StageRotation, deriveStages, PHASES };
  else Object.assign(window, { StageRotation, deriveStages, PROCESS_PHASES: PHASES });
})();
