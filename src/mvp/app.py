"""华章有据单实例服务：默认仅本机访问，对外部署使用 HTTPS 和访问账号。"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, pipeline, settings
from .jobs import JobStore
from .kb import get_kb

STORE = JobStore(settings.JOB_DB)
JOB_SLOTS = threading.BoundedSemaphore(max(1, settings.MAX_CONCURRENT_JOBS))


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_runtime()
    get_kb()  # Fail at startup if the required product package is missing.
    STORE.initialize()
    yield


app = FastAPI(title="华章有据", version=__version__, lifespan=lifespan)
WEB = settings.PKG / "web"
SESSION_SECONDS = 12 * 60 * 60


def session_token(timestamp: int) -> str:
    message = f"{timestamp}|{settings.AUTH_USERNAME}".encode()
    signature = hmac.new(settings.AUTH_PASSWORD.encode(), message, hashlib.sha256).hexdigest()
    return f"{timestamp}.{signature}"


def valid_session(token: str) -> bool:
    try:
        timestamp = int(token.split(".", 1)[0])
        age = time.time() - timestamp
        return 0 <= age < SESSION_SECONDS and secrets.compare_digest(token, session_token(timestamp))
    except (ValueError, TypeError):
        return False


@app.middleware("http")
async def access_control(request: Request, call_next):
    public = {"/healthz", "/about", "/login", "/api/login", "/static/style.css", "/static/login.css",
              "/static/login.js", "/static/brand/logo-mark.svg", "/static/brand/app-icon.svg",
              "/static/gallery/welcome.jpg", "/static/gallery/brief.jpg", "/static/gallery/workflow.jpg",
              "/static/gallery/result.jpg", "/static/gallery/evidence.jpg"}
    if settings.AUTH_PASSWORD and request.url.path not in public:
        if not valid_session(request.cookies.get("studio-session", "")):
            if request.url.path == "/":
                return RedirectResponse("/login", status_code=303)
            return JSONResponse({"detail": "登录已失效，请刷新页面重新登录"}, status_code=401,
                                headers={"Cache-Control": "no-store"})
    response = await call_next(request)
    if request.url.path.startswith(("/api/", "/img/")) or request.url.path in ("/", "/login", "/logout"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


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


class LoginIn(BaseModel):
    username: str = Field(max_length=200)
    password: str = Field(max_length=500)


@app.get("/login")
def login_page():
    if not settings.AUTH_PASSWORD:
        return RedirectResponse("/", status_code=303)
    return FileResponse(WEB / "login.html")


@app.get("/about")
def about_page():
    return FileResponse(WEB / "about.html")


@app.post("/api/login")
def login(credentials: LoginIn):
    if not settings.AUTH_PASSWORD:
        return {"ok": True}
    user_ok = secrets.compare_digest(credentials.username.encode(), settings.AUTH_USERNAME.encode())
    password_ok = secrets.compare_digest(credentials.password.encode(), settings.AUTH_PASSWORD.encode())
    if not (user_ok and password_ok):
        time.sleep(0.5)
        raise HTTPException(401, "账号或密码不正确")
    response = JSONResponse({"ok": True})
    response.set_cookie("studio-session", session_token(int(time.time())), max_age=SESSION_SECONDS,
                        httponly=True, secure=settings.COOKIE_SECURE, samesite="strict")
    return response


@app.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("studio-session")
    return response


def _start(task: dict, instruction: str | None) -> str:
    if not JOB_SLOTS.acquire(blocking=False):
        raise HTTPException(429, "已有创作正在运行，请完成后再试", headers={"Retry-After": "10"})
    jid = uuid.uuid4().hex
    job = {"id": jid, "state": "running", "steps": [], "result": None, "error": None, "t": time.time()}
    try:
        STORE.create(job)
    except Exception:
        JOB_SLOTS.release()
        raise

    def cb(u: dict):
        STORE.update(jid, steps=u.get("steps", []))

    def work():
        try:
            result = pipeline.run(task, instruction, on_update=cb)
            STORE.update(jid, result=result, state="done")
        except Exception as e:  # noqa: BLE001
            STORE.update(jid, error=f"{type(e).__name__}: {e}", state="error")
        finally:
            JOB_SLOTS.release()

    try:
        threading.Thread(target=work, daemon=True).start()
    except Exception:
        STORE.update(jid, state="error", error="无法启动任务线程，请重试")
        JOB_SLOTS.release()
        raise
    return jid


@app.get("/api/info")
def info():
    kb = get_kb()
    return {"name": "华章有据", "version": __version__, "auth_enabled": bool(settings.AUTH_PASSWORD), "kb": kb.whoami(),
            "writer_model": settings.WRITER_MODEL, "judge_model": settings.JUDGE_MODEL,
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
    j = STORE.get(jid)
    if not j:
        raise HTTPException(404, "任务不存在")
    return JSONResponse({k: j[k] for k in ("id", "state", "steps", "result", "error")})


@app.get("/healthz")
def health():
    return {"status": "ok"}


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
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
