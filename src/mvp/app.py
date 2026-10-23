"""华章有据单实例服务：默认仅本机访问，对外部署使用 HTTPS 和访问账号。"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
import uuid
import copy
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from . import __version__, pipeline, settings, review, poster, prompt_variants, marketing_templates
from .jobs import JobStore, public_snapshot
from .kb import get_kb
from .poster_channel import PosterChannel
from .editorial_context import EditorialStore, StoreProfile, store_key

STORE = JobStore(settings.JOB_DB)
JOB_SLOTS = threading.BoundedSemaphore(max(1, settings.MAX_CONCURRENT_JOBS))
REVIEW_LOCK = threading.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_runtime()
    get_kb()  # Fail at startup if the required product package is missing.
    STORE.initialize()
    EditorialStore(STORE.path).backfill()
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
    if request.url.path.startswith("/api/poster-worker/"):
        token = request.headers.get("X-Poster-Worker-Key", "")
        if not settings.POSTER_WORKER_TOKEN or not secrets.compare_digest(token.encode(), settings.POSTER_WORKER_TOKEN.encode()):
            return JSONResponse({"detail":"Unauthorized"}, status_code=401)
        try:
            size = int(request.headers.get("content-length") or "0")
        except ValueError:
            return JSONResponse({"detail":"无效的请求大小"}, status_code=400)
        if size < 0:
            return JSONResponse({"detail":"无效的请求大小"}, status_code=400)
        if size > 29 * 1024 * 1024:
            return JSONResponse({"detail":"图片交付超出大小限制"}, status_code=413)
        # 同时约束分块请求，不能只相信 Content-Length。
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > 29 * 1024 * 1024:
                return JSONResponse({"detail":"图片交付超出大小限制"}, status_code=413)
            chunks.append(chunk)
        request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
    public = {"/healthz", "/about", "/login", "/api/login", "/static/style.css", "/static/login.css", "/static/fonts.css", "/static/typography.css", "/static/mobile.css",
              "/static/login.js", "/static/brand/logo-mark.svg", "/static/brand/app-icon.svg",
              "/static/gallery/welcome.jpg", "/static/gallery/brief.jpg", "/static/gallery/workflow.jpg",
              "/static/gallery/result.jpg", "/static/gallery/evidence.jpg", "/static/gallery/clarify.jpg",
              "/static/gallery/store.jpg"}
    public_gallery = request.url.path.startswith("/static/gallery/") and request.url.path.endswith((".jpg", ".png", ".jpeg"))
    public_font = request.url.path.startswith("/static/fonts/") and request.url.path.endswith((".woff2", "/OFL.txt"))
    if settings.AUTH_PASSWORD and request.url.path not in public and not public_font and not public_gallery:
        if not valid_session(request.cookies.get("studio-session", "")):
            if request.url.path == "/":
                linked = request.query_params.get("job", "")
                return RedirectResponse("/login?job=" + linked if re.fullmatch(r"[a-f0-9]{32}", linked) else "/login", status_code=303)
            return JSONResponse({"detail": "登录已失效，请刷新页面重新登录"}, status_code=401,
                                headers={"Cache-Control": "no-store"})
    response = await call_next(request)
    if public_font and request.url.path.endswith(".woff2") and response.status_code == 200:
        response.headers["Content-Type"] = "font/woff2"
    if request.url.path.startswith(("/api/", "/img/")) or request.url.path in ("/", "/login", "/logout"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


class ClarifyAnswer(BaseModel):
    id: str = ""
    field: str = "other"
    question: str
    answer: str


class TopicIn(BaseModel):
    title: str = Field(default="", max_length=160)
    source: str = Field(default="", max_length=600)
    checked_on: str = Field(default="", max_length=10)


class TaskIn(BaseModel):
    prompt_variant: Literal["baseline", "differentiated"] = "baseline"
    marketing_template: str = Field(default="auto", pattern=r"^(auto|C\d{2}|S\d{2})$")
    demo_mode: bool = False
    concept_subject: str = Field(default="", max_length=80)
    topic_context: TopicIn = Field(default_factory=TopicIn)
    store_id: str = Field(default="default", pattern=r"^[A-Za-z0-9_-]{1,64}$")
    touchpoints: list[Literal["企业微信私信", "朋友圈", "门店社群", "到店邀约"]] = Field(default_factory=list, max_length=4)
    product: str = ""
    audience: str = ""
    scenario: str = ""
    platform: str = "xiaohongshu"
    speed: str = "quality"   # 保留已有简报档位；当前文字角色统一使用 DeepSeek 1017
    goal: str = ""
    constraints: list[str] = Field(default_factory=list)
    extra: str = ""
    instruction: str = ""
    clarify_round: int = Field(default=0, ge=0)
    clarify_answers: list[ClarifyAnswer] = Field(default_factory=list)

    @model_validator(mode="after")
    def version_scope(self):
        if self.prompt_variant == "baseline" and (self.demo_mode or self.marketing_template != "auto"):
            raise ValueError("样板选择和概念演示请使用 B；A 保留原版基线")
        return self


class LoginIn(BaseModel):
    username: str = Field(max_length=200)
    password: str = Field(max_length=500)


class WorkerHeartbeat(BaseModel):
    ready: bool


class WorkerDelivery(BaseModel):
    claim_token: str = Field(min_length=20, max_length=100)
    image: str | None = Field(default=None, max_length=28 * 1024 * 1024)
    error: Literal["account_not_ready", "generation_failed", "generation_timeout", "invalid_image"] | None = None


@app.post("/api/poster-worker/heartbeat")
def poster_worker_heartbeat(body: WorkerHeartbeat):
    PosterChannel(STORE.path).heartbeat(body.ready)
    return {"ok":True}


@app.post("/api/poster-worker/claim")
def poster_worker_claim():
    channel = PosterChannel(STORE.path)
    return {"task":channel.claim() if channel.worker_ready() else None}


@app.post("/api/poster-worker/{task_id}/result")
def poster_worker_result(task_id: str, body: WorkerDelivery):
    if bool(body.image) == bool(body.error):
        raise HTTPException(400, "只能交付图片或错误之一。")
    errors = {"account_not_ready":"出图账号尚未完成连接，请联系工作台维护者。", "generation_failed":"网页出图未完成，请核对账号会话或额度后手动重试。",
              "generation_timeout":"网页出图超时；本次不会自动重新生成。", "invalid_image":"网页未返回有效图片。"}
    try:
        return PosterChannel(STORE.path).finish(task_id, body.claim_token, body.image, errors.get(body.error), settings.POSTER_DIR)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


class ReviewAnswer(BaseModel):
    id: str = Field(max_length=64)
    choice: Literal["fix", "disagree", "defer"]
    reason: str = Field(default="", max_length=2000)


class ReviewDecision(BaseModel):
    token: str = Field(max_length=64)
    answers: list[ReviewAnswer] = Field(max_length=100)
    resolution: Literal["continue", "adopt", "hold"]


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


def _start(task: dict, instruction: str | None, *, source: dict | None = None, decision: dict | None = None,
           poster_only: bool = False, poster_review_only: bool = False, comparison: bool = False) -> str:
    if not JOB_SLOTS.acquire(blocking=False):
        raise HTTPException(429, "已有创作正在运行，请完成后再试", headers={"Retry-After": "10"})
    jid = uuid.uuid4().hex
    job = {"id": jid, "state": "running", "steps": [], "events": [], "artifacts": {},
           "result": None, "error": None, "t": time.time()}
    try:
        if source is None:
            # 只从服务端取已保存资料，忽略客户端伪造的确认状态与历史。
            context_store = EditorialStore(STORE.path)
            context_store.backfill()
            task = {**task, "creative_context": context_store.snapshot(task.get("store_id") or "default")}
            if comparison:
                task = {**task, "prompt_variant": "differentiated"}
            task = marketing_templates.prepare_task(task)
            try:
                marketing_templates.validate_task(task)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from None
        STORE.create(job)
    except Exception:
        JOB_SLOTS.release()
        raise

    def cb(u: dict):
        STORE.update(jid, **{k: u[k] for k in ("steps", "events", "artifacts", "elapsed_ms", "started_at") if k in u})

    def work():
        try:
            if comparison:
                from .prompt_comparison import compare
                result = compare(task, instruction, on_update=cb)
            elif poster_only:
                result = copy.deepcopy(source)
                result["poster_parent"] = source.get("job_id")
                result.pop("automatic_followup", None)
                result["trace"] = [s for s in result.get("trace", []) if not s.get("step", "").startswith("poster_")]
                result["total_ms"] = 0
                if result.get("human_review"):
                    result["text_human_review"] = result.pop("human_review")
            else:
                result = (pipeline.continue_review(source, decision, on_update=cb) if source is not None else
                          pipeline.run(task, instruction, on_update=cb))
            if task.get("platform") == "poster" and result.get("article") and settings.POSTER_IMAGE_ENABLED:
                result = poster.attach(result, jid, on_update=cb, review_only=poster_review_only, decision=decision)
            result["job_id"] = jid
            EditorialStore(STORE.path).remember(jid, result)
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
            "prompt_variants": [prompt_variants.manifest(k) for k in prompt_variants.VARIANTS],
            "marketing_templates": marketing_templates.library(),
            "poster_service": {"provider":settings.POSTER_IMAGE_PROVIDER, "fallback":settings.POSTER_FALLBACK_PROVIDER,
                               "fallback_model":settings.POSTER_FALLBACK_MODEL if settings.POSTER_FALLBACK_PROVIDER else "",
                               **PosterChannel(STORE.path).status()},
            "models": [{"id": m.id, "name": m.name, "group": m.group} for m in kb.models()],
            "platforms": {k: v["name"] for k, v in pipeline.platforms_cfg().items()},
            "scenarios": list(pipeline.scenes_cfg()["scenarios"])}


@app.post("/api/run")
def run(t: TaskIn):
    task = t.model_dump()
    instr = task.pop("instruction") or None
    return {"job": _start(task, instr)}


@app.post("/api/compare")
def compare_prompts(t: TaskIn):
    if t.platform == "poster":
        raise HTTPException(422, "提示词对照先使用朋友圈、小红书或公众号；海报出图不纳入文字对照。")
    task = t.model_dump()
    instruction = task.pop("instruction") or None
    return {"job": _start(task, instruction, comparison=True)}


@app.get("/api/prompts/{variant}")
def read_prompts(variant: Literal["baseline", "differentiated"]):
    root = prompt_variants.directory(variant)
    return {"version": prompt_variants.manifest(variant),
            "steps": {name: root.joinpath(name + ".md").read_text(encoding="utf-8")
                      for name in prompt_variants.STEPS}}


def _store_id(sid: str):
    try:
        return store_key(sid)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@app.get("/api/context/{sid}")
def creative_context(sid: str):
    cs = EditorialStore(STORE.path)
    sid = _store_id(sid)
    return {"profile": cs.profile(sid), "history": cs.history(sid), "context": cs.snapshot(sid)}


@app.put("/api/context/{sid}")
def save_creative_context(sid: str, profile: StoreProfile):
    cs = EditorialStore(STORE.path)
    return {"profile": cs.save_profile(_store_id(sid), profile)}


@app.get("/api/context/{sid}/history/{jid}")
def context_history_item(sid: str, jid: str):
    entry = EditorialStore(STORE.path).history_item(_store_id(sid), jid)
    if entry is None:
        raise HTTPException(404, "该门店没有这篇历史稿")
    return entry


class PublicationIn(BaseModel):
    published: bool


@app.put("/api/context/{sid}/history/{jid}/publication")
def mark_publication(sid: str, jid: str, body: PublicationIn):
    try:
        EditorialStore(STORE.path).mark_published(_store_id(sid), jid, body.published)
    except KeyError:
        raise HTTPException(404, "该门店没有这篇历史稿") from None
    return {"published": body.published}


@app.get("/api/job/{jid}")
def job(jid: str):
    j = STORE.get(jid)
    if not j:
        raise HTTPException(404, "任务不存在")
    snapshot = public_snapshot(j)
    if snapshot.get("result"):
        snapshot["result"] = {**snapshot["result"], "job_id": jid}
    return JSONResponse(snapshot)


def _reviewable_job(jid: str) -> dict:
    job = STORE.get(jid)
    if not job:
        raise HTTPException(404, "任务不存在")
    if job["state"] != "done" or not (job.get("result") or {}).get("article"):
        raise HTTPException(409, "请等待作品及终审结果返回后再裁定。")
    return job


@app.get("/api/job/{jid}/review")
def review_questions(jid: str):
    return review.questions(_reviewable_job(jid)["result"])


@app.post("/api/job/{jid}/review")
def decide_review(jid: str, payload: ReviewDecision):
    with REVIEW_LOCK:
        saved = _reviewable_job(jid)
        result = copy.deepcopy(saved["result"])
        result["job_id"] = jid
        try:
            decision = review.validate_decision(result, payload.model_dump())
        except review.ReviewConflict as exc:
            raise HTTPException(409, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        previous = result.get("human_review") or result.get("automatic_followup") or {}
        if previous.get("next_job"):
            raise HTTPException(409, "该稿件已提交后续处理，请打开最新任务再裁定。")
        decision["actor"] = settings.AUTH_USERNAME or "本机用户"
        next_job = None
        if payload.resolution == "continue":
            only_image = poster.text_approved(result) and all(a["origin"] == "poster" for a in decision["answers"])
            next_job = _start(result["task"], None, source=result, decision=decision, poster_only=only_image,
                              poster_review_only=only_image and not any(a["choice"] == "fix" for a in decision["answers"]))
            decision["next_job"] = next_job
        elif payload.resolution == "adopt" and result.get("poster", {}).get("status") == "blocked":
            result["human_review"] = decision
            next_job = _start(result["task"], None, source=result, poster_only=True)
            decision["next_job"] = next_job
        result["human_review" if decision.get("mode") == "human" else "automatic_followup"] = decision
        history = saved.get("review_history", []) + [decision]
        STORE.update(jid, result=result, review_history=history)
        return {"result": result, "job": next_job}


@app.post("/api/job/{jid}/poster/regenerate")
def regenerate_poster(jid: str):
    saved = _reviewable_job(jid)
    source = {**saved["result"], "job_id":jid}
    if (source.get("task") or {}).get("platform") != "poster":
        raise HTTPException(422, "只有门店海报可以重新生图。")
    if not settings.POSTER_IMAGE_ENABLED:
        raise HTTPException(409, "生图功能当前未启用。")
    if not poster.text_approved(source):
        raise HTTPException(409, "请先在问题详情中修订或裁定文案，再重新生图。")
    return {"job": _start(source["task"], None, source=source, poster_only=True)}


@app.get("/api/job/{jid}/poster/image")
def poster_image(jid: str, download: bool = False):
    saved = STORE.get(jid)
    metadata = ((saved or {}).get("result") or {}).get("poster") or ((saved or {}).get("artifacts") or {}).get("poster") or {}
    if not saved or not metadata.get("sha256") or not re.fullmatch(r"[a-f0-9]{32}", jid):
        raise HTTPException(404, "海报尚未生成或未登记。")
    path = settings.POSTER_DIR / jid / "poster.png"
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != metadata["sha256"]:
        raise HTTPException(404, "海报文件不可用或与登记结果不一致。")
    return FileResponse(path, media_type="image/png", filename="门店海报.png" if download else None)


@app.get("/healthz")
def health():
    return {"status": "ok"}


@app.get("/img/{model_id}/{filename}")
def img(model_id: str, filename: str):
    """仅提供知识库登记图片和已核验的官方联网补图。"""
    p = get_kb().image_file(model_id, filename) if get_kb().info(model_id) else None
    if not p or not Path(p).exists():
        raise HTTPException(404, "图片未登记或未通过来源核验")
    return FileResponse(p)


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
