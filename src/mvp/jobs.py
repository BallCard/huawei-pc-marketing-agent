"""单实例任务快照：每步持久保存，重启后如实标记未完成任务。"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import closing
from pathlib import Path


class JobStore:
    def __init__(self, path: Path, keep: int = 30):
        self.path = path
        self.keep = keep
        self.lock = threading.RLock()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock, closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, created REAL, payload TEXT)")
            for jid, raw in db.execute("SELECT id, payload FROM jobs").fetchall():
                job = json.loads(raw)
                if job["state"] == "running":
                    job.update(state="error", error="服务已重启，上次创作已中断。请返回简报重新生成。")
                    for step in job.get("steps", []):
                        if step.get("status") == "running":
                            step["status"] = "error"
                    db.execute("UPDATE jobs SET payload=? WHERE id=?", (json.dumps(job, ensure_ascii=False), jid))

    def create(self, job: dict) -> None:
        with self.lock, closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO jobs VALUES (?, ?, ?)",
                       (job["id"], job["t"], json.dumps(job, ensure_ascii=False)))
            # Keep every running task even if it is older than the retained completed tasks.
            rows = db.execute("SELECT id, payload FROM jobs ORDER BY created DESC").fetchall()
            finished = 0
            for jid, raw in rows:
                if json.loads(raw)["state"] != "running":
                    finished += 1
                    if finished > self.keep:
                        db.execute("DELETE FROM jobs WHERE id=?", (jid,))

    def update(self, jid: str, **changes) -> None:
        with self.lock, closing(sqlite3.connect(self.path)) as db, db:
            row = db.execute("SELECT payload FROM jobs WHERE id=?", (jid,)).fetchone()
            if row is None:
                raise KeyError(jid)
            job = json.loads(row[0])
            job.update(changes)
            db.execute("UPDATE jobs SET payload=? WHERE id=?", (json.dumps(job, ensure_ascii=False), jid))

    def get(self, jid: str) -> dict | None:
        with self.lock, closing(sqlite3.connect(self.path)) as db, db:
            row = db.execute("SELECT payload FROM jobs WHERE id=?", (jid,)).fetchone()
            return json.loads(row[0]) if row else None
