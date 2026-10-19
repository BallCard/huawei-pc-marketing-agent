(function () {
  "use strict";

  // The server trace stays untouched. This clock only paces how the UI hands it on.
  class FlowPlayback {
    constructor({ onChange = () => {}, now = () => performance.now(),
      setTimer = (fn, ms) => setTimeout(fn, ms), clearTimer = timer => clearTimeout(timer),
      minActiveMs = 650, handoffMs = 180, finishMs = 280 } = {}) {
      Object.assign(this, { onChange, now, setTimer, clearTimer, minActiveMs, handoffMs, finishMs });
      this.waiters = [];
      this.reset();
    }

    pause() {
      if (this.timer != null) this.clearTimer(this.timer);
      this.timer = null;
    }

    reset() {
      this.pause();
      this.target = [];
      this.states = [];
      this.activeIndex = -1;
      this.activeSince = 0;
      this.phase = "idle";
      this.handoffFrom = null;
      this.until = 0;
      this.waiters.splice(0).forEach(resolve => resolve());
    }

    snapshot() {
      return { states: this.states.slice(), activeIndex: this.activeIndex,
        handoffFrom: this.handoffFrom, pending: this.activeIndex >= 0 || this.phase !== "idle" };
    }

    whenSettled() {
      return this.snapshot().pending ? new Promise(resolve => this.waiters.push(resolve)) : Promise.resolve();
    }

    update(target, { immediate = false } = {}) {
      this.pause();
      if (this.states.length !== target.length) {
        this.reset();
        this.states = target.map(() => "wait");
      }
      this.target = target.slice();
      if (immediate || target.includes("error")) {
        this.states = target.slice();
        this.phase = "idle";
        this.handoffFrom = null;
        this.activeIndex = target.includes("error") ? -1 : target.indexOf("running");
        this.activeSince = this.now();
        this.emit();
        return;
      }
      this.advance();
    }

    emit() {
      const state = this.snapshot();
      this.onChange(state);
      if (!state.pending) this.waiters.splice(0).forEach(resolve => resolve());
    }

    wakeAfter(ms) {
      this.timer = this.setTimer(() => {
        this.timer = null;
        this.advance();
      }, Math.max(0, ms));
    }

    advance() {
      const now = this.now();
      // A repair may reopen the verification node after its previous check passed.
      const reopened = this.target.findIndex((status, i) => status === "running" && this.states[i] === "done");
      if (reopened >= 0) {
        this.activeIndex = reopened;
        this.activeSince = now;
        this.phase = "idle";
        this.handoffFrom = null;
      }

      if (this.phase !== "idle") {
        if (now < this.until) {
          this.wakeAfter(this.until - now);
          this.emit();
          return;
        }
        this.phase = "idle";
        this.handoffFrom = null;
      }

      if (this.activeIndex >= 0) {
        const i = this.activeIndex;
        const status = this.target[i];
        if (status === "running") {
          this.states[i] = "running";
          this.emit();
          return;
        }
        if (status === "done") {
          // Already-finished fast work is labelled as a handoff, not a live model call.
          this.states[i] = "settling";
          const remaining = this.minActiveMs - (now - this.activeSince);
          if (remaining > 0) {
            this.wakeAfter(remaining);
            this.emit();
            return;
          }
          this.states[i] = "done";
          this.activeIndex = -1;
          this.phase = i === this.states.length - 1 ? "finish" : "handoff";
          this.handoffFrom = i;
          const duration = this.phase === "finish" ? this.finishMs : this.handoffMs;
          this.until = now + duration;
          this.wakeAfter(duration);
          this.emit();
          return;
        }
        this.states[i] = status;
        this.activeIndex = -1;
      }

      let next = this.states.findIndex(status => status !== "done" && status !== "skip");
      while (next >= 0 && this.target[next] === "skip") {
        this.states[next] = "skip";
        next = this.states.findIndex(status => status !== "done" && status !== "skip");
      }
      if (next >= 0 && this.target[next] !== "wait") {
        this.activeIndex = next;
        this.activeSince = now;
        this.states[next] = this.target[next] === "done" ? "settling" : "running";
        if (this.target[next] === "done") this.wakeAfter(this.minActiveMs);
      }
      this.emit();
    }
  }

  if (typeof module !== "undefined" && module.exports) module.exports = FlowPlayback;
  else window.FlowPlayback = FlowPlayback;
})();
