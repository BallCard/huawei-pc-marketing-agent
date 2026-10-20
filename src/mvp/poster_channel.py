"""VPS 主动领取图片任务；不向 VPS 开放工作台账号或知识库接口。"""
from __future__ import annotations

import base64
import json
import re
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class PosterChannel:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def db(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                connection.execute("CREATE TABLE IF NOT EXISTS poster_worker (slot INTEGER PRIMARY KEY, heartbeat REAL, ready INTEGER)")
                connection.execute("""CREATE TABLE IF NOT EXISTS poster_tasks (
                    id TEXT PRIMARY KEY, job_id TEXT UNIQUE, created REAL, expires REAL,
                    state TEXT, claim_token TEXT, payload TEXT, result TEXT, error TEXT)""")
                yield connection
        finally:
            connection.close()

    def heartbeat(self, ready: bool):
        with self.db() as db:
            db.execute("INSERT INTO poster_worker VALUES(1,?,?) ON CONFLICT(slot) DO UPDATE SET heartbeat=excluded.heartbeat, ready=excluded.ready", (time.time(), int(ready)))

    def status(self) -> dict:
        with self.db() as db:
            row = db.execute("SELECT heartbeat,ready FROM poster_worker WHERE slot=1").fetchone()
        connected = bool(row and time.time() - row["heartbeat"] < 75)
        return {"connected":connected, "account_configured":bool(connected and row["ready"])}

    def worker_ready(self) -> bool:
        return self.status()["account_configured"]

    def create(self, job_id: str, payload: dict, expires: float) -> str:
        if not re.fullmatch(r"[a-f0-9]{32}", job_id):
            raise ValueError("无效的图片任务编号。")
        with self.db() as db:
            existing = db.execute("SELECT id FROM poster_tasks WHERE job_id=?", (job_id,)).fetchone()
            if existing:
                return existing["id"]
            task_id = uuid.uuid4().hex
            db.execute("INSERT INTO poster_tasks VALUES(?,?,?,?,?,?,?,?,?)", (task_id,job_id,time.time(),expires,"queued",None,json.dumps(payload,ensure_ascii=False),None,None))
        return task_id

    def claim(self) -> dict | None:
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            # 已领取的任务不重新分配，避免超时/重启时再次消耗生图额度。
            db.execute("UPDATE poster_tasks SET state='error', error='任务等待已超时，尚未提交生图', payload=NULL WHERE state='queued' AND expires<?", (time.time(),))
            db.execute("UPDATE poster_tasks SET state='error', error='原任务已超时且未收到图片，请核对网页结果后手动重试。', payload=NULL WHERE state='running' AND expires<?", (time.time()-120,))
            if db.execute("SELECT 1 FROM poster_tasks WHERE state='running'").fetchone():
                return None
            row = db.execute("SELECT * FROM poster_tasks WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
            if not row:
                return None
            token = secrets.token_urlsafe(32)
            db.execute("UPDATE poster_tasks SET state='running',claim_token=? WHERE id=? AND state='queued'", (token,row["id"]))
            return {"id":row["id"], "claim_token":token, "payload":json.loads(row["payload"])}

    def get(self, task_id: str) -> dict | None:
        with self.db() as db:
            row = db.execute("SELECT id,job_id,state,result,error FROM poster_tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["result"] = json.loads(result["result"]) if result["result"] else None
        return result

    def finish(self, task_id: str, token: str, image: str | None, error: str | None, poster_dir: Path) -> dict:
        from .poster import save_image
        from .llm import LLMError
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM poster_tasks WHERE id=?", (task_id,)).fetchone()
            if not row or not row["claim_token"] or not secrets.compare_digest(token.encode(), row["claim_token"].encode()):
                raise ValueError("任务领取凭证无效。")
            if row["state"] in ("done", "error"):
                return {"accepted":True}  # 只重试交付同一结果，不重生或覆盖已完成图片。
            if row["state"] != "running":
                raise ValueError("任务未被领取。")
            if error:
                db.execute("UPDATE poster_tasks SET state='error',error=?,payload=NULL WHERE id=?", (error,task_id))
            else:
                if not image or len(image) > 28 * 1024 * 1024:
                    raise ValueError("没有收到有效图片，或图片超出大小限制。")
                content = base64.b64decode(image, validate=True)
                try:
                    result = save_image(content, poster_dir / row["job_id"])
                except LLMError as exc:
                    raise ValueError(str(exc)) from exc
                db.execute("UPDATE poster_tasks SET state='done',result=?,payload=NULL WHERE id=?", (json.dumps(result),task_id))
        return {"accepted":True}
