"""本地 MVP 服务：FastAPI + 单页前端。启动：python -m src.mvp.app（默认 http://127.0.0.1:7860）。

安全提示：服务只绑定 127.0.0.1，没有登录鉴权，仅供本机调试；上线/公网部署前必须加鉴权。
"""
from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import pipeline, settings
from .kb import get_kb

app = FastAPI(title="华为PC营销软文智能体 MVP")
WEB = settings.PKG / "web"
JOBS: dict[str, dict] = {}
JOB_LOCK = threading.Lock()


class TaskIn(BaseModel):
    product: str = ""
    audience: str = ""
    scenario: str = ""
    platform: str = "xiaohongshu"
    speed: str = "quality"   # quality=写作/审核用 high；fast=全 low，演示用
    goal: str = ""
    constraints: list[str] = Field(default_factory=list)
    extra: str = ""
    instruction: str = ""


def _start(task: dict, instruction: str | None) -> str:
    jid = uuid.uuid4().hex[:10]
    job = {"id": jid, "state": "running", "steps": [], "result": None, "error": None, "t": time.time()}
    with JOB_LOCK:
        JOBS[jid] = job
        for k in list(JOBS)[:-30]:
            JOBS.pop(k, None)

    def cb(u: dict):
        job["steps"] = [dict(s) for s in u.get("steps", [])]

    def work():
        try:
            job["result"] = pipeline.run(task, instruction, on_update=cb)
            job["state"] = "done"
        except Exception as e:  # noqa: BLE001
            job["error"] = f"{type(e).__name__}: {e}"
            job["state"] = "error"

    threading.Thread(target=work, daemon=True).start()
    return jid


@app.get("/api/info")
def info():
    kb = get_kb()
    return {"kb": kb.whoami(), "writer_model": settings.WRITER_MODEL, "judge_model": settings.JUDGE_MODEL,
            "models": [{"id": m.id, "name": m.name, "group": m.group} for m in kb.models()],
            "platforms": {k: v["name"] for k, v in pipeline.platforms_cfg().items()},
            "scenarios": list(pipeline.scenes_cfg()["scenarios"])}


@app.post("/api/run")
def run(t: TaskIn):
    task = t.model_dump()
    instr = task.pop("instruction") or None
    return {"job": _start(task, instr)}


@app.get("/api/job/{jid}")
def job(jid: str):
    j = JOBS.get(jid)
    if not j:
        raise HTTPException(404, "任务不存在")
    return JSONResponse({k: j[k] for k in ("id", "state", "steps", "result", "error")})


@app.get("/img/{model_id}/{filename}")
def img(model_id: str, filename: str):
    """只放行 图片索引.csv 登记过的文件，防止目录穿越与读取非登记文件。"""
    p = get_kb().image_file(model_id, filename) if get_kb().info(model_id) else None
    if not p or not Path(p).exists():
        raise HTTPException(404, "图片未在图片索引中登记")
    return FileResponse(p)


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(__import__("os").environ.get("PORT", "7860")))
