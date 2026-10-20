(function () {
  "use strict";
  class ProcessState {
    constructor() { this.reset(); }
    reset() { this.events = new Map(); this.artifacts = {}; this.steps = []; this.state = "idle"; this.lastSeq = 0; }
    ingest(snapshot) {
      const added = [];
      for (const event of snapshot.events || []) {
        if (!Number.isInteger(event.seq) || this.events.has(event.seq)) continue;
        this.events.set(event.seq, event);
        added.push(event);
        this.lastSeq = Math.max(this.lastSeq, event.seq);
      }
      this.artifacts = { ...this.artifacts, ...(snapshot.artifacts || snapshot.result?.artifacts || {}) };
      this.steps = snapshot.steps || snapshot.result?.trace || [];
      this.state = snapshot.state || this.state;
      return added.sort((a, b) => a.seq - b.seq);
    }
    orderedEvents() { return [...this.events.values()].sort((a, b) => a.seq - b.seq); }
  }
  if (typeof module !== "undefined" && module.exports) module.exports = ProcessState;
  else window.ProcessState = ProcessState;
})();
