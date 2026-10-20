"""真实进展与产物快照。锁内编号和持久化，避免并行步骤覆盖或乱序。"""
from __future__ import annotations

import copy
import threading
import time

from . import llm


NODE = {"scene": "planner", "extract": "planner", "compose": "editor", "repair": "editor",
        "judge": "reviewer", "rejudge": "reviewer"}


class Trace:
    def __init__(self, cb=None, budget_seconds=90):
        self.steps = []
        self.events = []
        self.artifacts = {}
        self.calls = []
        self.cb = cb
        self.lock = threading.RLock()
        self.started = time.monotonic()
        self.started_at = time.time()
        self.deadline = self.started + budget_seconds
        self.closed = False

    def snapshot(self):
        with self.lock:
            return copy.deepcopy({"steps": self.steps, "events": self.events, "artifacts": self.artifacts,
                                  "elapsed_ms": int((time.monotonic() - self.started) * 1000), "started_at": self.started_at})

    def emit(self, kind, node, **data):
        with self.lock:
            if self.closed:
                return
            self.events.append({"seq": len(self.events) + 1, "type": kind, "node": node,
                                "at_ms": int((time.monotonic() - self.started) * 1000), **data})
            if self.cb:
                self.cb(self.snapshot())

    def publish(self, key, value, node, label, **data):
        with self.lock:
            if self.closed:
                return
            self.artifacts[key] = copy.deepcopy(value)
            self.emit("artifact_ready", node, artifact=key, label=label, **data)

    def skip(self, step, label, reason):
        with self.lock:
            self.steps.append({"step": step, "node": NODE.get(step, step), "label": label,
                               "status": "skip", "ms": 0, "detail": {"reason": reason}})
            self.emit("step_skipped", NODE.get(step, step), step=step, label=label, reason=reason)

    def record_call(self, entry):
        with self.lock:
            if not self.closed:
                self.calls.append(entry)

    def run(self, step, label, fn, *, view=None, inputs="", depends_on=()):
        with llm.budget(self.deadline, self.record_call):
            llm.remaining()
            node = NODE.get(step, step)
            record = {"step": step, "node": node, "label": label, "status": "running", "ms": 0,
                      "started_ms": int((time.monotonic() - self.started) * 1000),
                      "input_summary": inputs, "depends_on": list(depends_on), "detail": {}}
            with self.lock:
                self.steps.append(record)
                self.emit("step_started", node, step=step, label=label)
            started = time.monotonic()
            try:
                result = fn()
                with self.lock:
                    record["detail"] = view(result) if view else result
                    record["status"] = "done"
                return result
            except Exception as exc:
                with self.lock:
                    record.update(status="error", detail={"error": str(exc)})
                raise
            finally:
                with self.lock:
                    record["ms"] = int((time.monotonic() - started) * 1000)
                    self.emit("step_finished", node, step=step, label=label, status=record["status"])
