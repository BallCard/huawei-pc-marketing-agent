"""运行配置：全部来自环境变量（可由仓库根 .env 提供），代码里不放任何密钥。"""
import os
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = Path(__file__).resolve().parent


def _load_dotenv() -> None:
    f = Path(os.environ.get("APP_ENV_FILE") or ROOT / ".env")
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

# 文字角色统一使用魔搭 DeepSeek 1017；写作和评审仍是独立上下文。
DEFAULT_TEXT_MODEL = "deepseek-ai/DeepSeek-V4.1-Flash-1017"
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api-inference.modelscope.cn/v1").rstrip("/")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
WRITER_MODEL = os.environ.get("WRITER_MODEL", DEFAULT_TEXT_MODEL)
FAST_MODEL = os.environ.get("FAST_MODEL", DEFAULT_TEXT_MODEL)
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", DEFAULT_TEXT_MODEL)
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "180"))
GENERATION_BUDGET_SECONDS = float(os.environ.get("GENERATION_BUDGET_SECONDS", "240"))
LLM_THINKING = os.environ.get("LLM_THINKING", "disabled")


def llm_config(role: str = "writer") -> dict:
    if role in ("poster_review", "image_verify"):
        return {"base_url": POSTER_REVIEW_BASE_URL if role == "poster_review" else IMAGE_VERIFY_BASE_URL,
                "api_key": POSTER_REVIEW_API_KEY if role == "poster_review" else IMAGE_VERIFY_API_KEY,
                "thinking": "auto", "extra": {"enable_thinking": False}}
    prefix = {"writer": "WRITER", "fast": "FAST", "judge": "JUDGE"}[role]
    extra = json.loads(os.environ.get(f"{prefix}_LLM_EXTRA_BODY") or "{}")
    if not isinstance(extra, dict) or {"model", "messages", "stream"} & extra.keys():
        raise ValueError(f"{prefix}_LLM_EXTRA_BODY 必须是 JSON 对象，且不能覆盖 model/messages/stream")
    return {"base_url": (os.environ.get(f"{prefix}_LLM_BASE_URL") or LLM_BASE_URL).rstrip("/"),
            "api_key": os.environ.get(f"{prefix}_LLM_API_KEY") or LLM_API_KEY,
            "thinking": os.environ.get(f"{prefix}_LLM_THINKING") or LLM_THINKING,
            "extra": extra}

# v1.0 使用本地资料包；IMA 连接尚未实现。
KB_BACKEND = os.environ.get("KB_BACKEND", "local")


def _find_kb_dir() -> Path:
    env = os.environ.get("KB_DIR")
    if env:
        return Path(env)
    here = ROOT / "data" / "kb"
    if here.exists():
        return here
    # worktree 位于 <repo>/.claude/worktrees/<name>，共享 data 在主仓库根
    for p in ROOT.parents:
        if (p / "data" / "kb").exists():
            return p / "data" / "kb"
    return here


KB_DIR = _find_kb_dir()
CACHE_DIR = Path(os.environ.get("CACHE_DIR") or str(KB_DIR.parent / "cache"))
KB_BASE_DATE = "2026-10-17"  # 知识库事实基准日
WEB_IMAGE_SEARCH = os.environ.get("WEB_IMAGE_SEARCH", "1") == "1"
WEB_IMAGE_TIMEOUT = float(os.environ.get("WEB_IMAGE_TIMEOUT", "25"))
# 图片核验需要视觉输入，不能随着文字角色切换到 DeepSeek。
IMAGE_VERIFY_MODEL = os.environ.get("IMAGE_VERIFY_MODEL") or "Qwen/Qwen3.5-35B-A3B"
IMAGE_VERIFY_BASE_URL = (os.environ.get("IMAGE_VERIFY_BASE_URL") or "https://api-inference.modelscope.cn/v1").rstrip("/")
IMAGE_VERIFY_API_KEY = os.environ.get("IMAGE_VERIFY_API_KEY") or LLM_API_KEY

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "7860"))
# 公开演示可显式关闭工作台账号：PUBLIC_ACCESS=1 时忽略残留的 AUTH_* 配置。
PUBLIC_ACCESS = os.environ.get("PUBLIC_ACCESS", "0") == "1"
AUTH_USERNAME = "" if PUBLIC_ACCESS else os.environ.get("AUTH_USERNAME", "")
AUTH_PASSWORD = "" if PUBLIC_ACCESS else os.environ.get("AUTH_PASSWORD", "")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "1" if HOST not in ("127.0.0.1", "localhost", "::1") else "0") == "1"
JOB_DB = Path(os.environ.get("JOB_DB") or str(ROOT / "data" / "state" / "jobs.sqlite3"))
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "1"))

# 生图与成图审核独立于本机文本反代；部署可复用同一魔搭推理令牌。
POSTER_IMAGE_ENABLED = os.environ.get("POSTER_IMAGE_ENABLED", "1") == "1"
POSTER_IMAGE_PROVIDER = os.environ.get("POSTER_IMAGE_PROVIDER", "modelscope")
POSTER_WORKER_TOKEN = os.environ.get("POSTER_WORKER_TOKEN", "")
POSTER_IMAGE_AUTH_MODE = os.environ.get("POSTER_IMAGE_AUTH_MODE", "bearer")
POSTER_IMAGE_BASE_URL = os.environ.get("POSTER_IMAGE_BASE_URL", "https://api-inference.modelscope.cn/v1").rstrip("/")
POSTER_IMAGE_API_KEY = os.environ.get("POSTER_IMAGE_API_KEY", "")
POSTER_IMAGE_MODEL = os.environ.get("POSTER_IMAGE_MODEL", "Qwen/Qwen-Image-Edit-2511")
POSTER_REVIEW_MODEL = os.environ.get("POSTER_REVIEW_MODEL", "Qwen/Qwen3.5-35B-A3B")
POSTER_REVIEW_BASE_URL = os.environ.get("POSTER_REVIEW_BASE_URL", "https://api-inference.modelscope.cn/v1").rstrip("/")
POSTER_REVIEW_API_KEY = os.environ.get("POSTER_REVIEW_API_KEY") or (POSTER_IMAGE_API_KEY if POSTER_IMAGE_PROVIDER == "modelscope" else os.environ.get("FAST_LLM_API_KEY", ""))
POSTER_IMAGE_TIMEOUT = float(os.environ.get("POSTER_IMAGE_TIMEOUT", "600"))
POSTER_REVIEW_TIMEOUT = float(os.environ.get("POSTER_REVIEW_TIMEOUT", "60"))
# 主链路明确失败时的一次性免费备选；留空表示不降级，失败后仍退回预制样例。
POSTER_FALLBACK_PROVIDER = os.environ.get("POSTER_FALLBACK_PROVIDER", "")
POSTER_FALLBACK_MODEL = os.environ.get("POSTER_FALLBACK_MODEL", "Qwen/Qwen-Image-Edit-2511")
# 剩余时间不足以完成一次备选生图时不再切换，避免必然超时。
POSTER_FALLBACK_MIN_SECONDS = float(os.environ.get("POSTER_FALLBACK_MIN_SECONDS", "180"))
POSTER_DIR = Path(os.environ.get("POSTER_DIR") or str(JOB_DB.parent / "posters"))


def validate_runtime() -> None:
    if POSTER_IMAGE_AUTH_MODE not in ("bearer", "basic"):
        raise RuntimeError("POSTER_IMAGE_AUTH_MODE 仅支持 bearer、basic")
    if POSTER_IMAGE_PROVIDER not in ("modelscope", "gemini_web_proxy", "chatgpt_web_proxy", "private_worker"):
        raise RuntimeError("POSTER_IMAGE_PROVIDER 仅支持 modelscope、gemini_web_proxy、chatgpt_web_proxy、private_worker")
    if POSTER_FALLBACK_PROVIDER:
        if POSTER_FALLBACK_PROVIDER not in ("modelscope", "gemini_web_proxy", "chatgpt_web_proxy", "private_worker"):
            raise RuntimeError("POSTER_FALLBACK_PROVIDER 仅支持 modelscope、gemini_web_proxy、chatgpt_web_proxy、private_worker")
        if POSTER_FALLBACK_PROVIDER == POSTER_IMAGE_PROVIDER:
            raise RuntimeError("POSTER_FALLBACK_PROVIDER 不能与 POSTER_IMAGE_PROVIDER 相同")
        if POSTER_FALLBACK_PROVIDER == "modelscope" and not POSTER_IMAGE_API_KEY:
            raise RuntimeError("魔搭免费备选需要 POSTER_IMAGE_API_KEY")
        if POSTER_FALLBACK_PROVIDER == "private_worker" and not POSTER_WORKER_TOKEN:
            raise RuntimeError("私有 worker 备选需要 POSTER_WORKER_TOKEN")
    if POSTER_FALLBACK_MIN_SECONDS < 0:
        raise RuntimeError("POSTER_FALLBACK_MIN_SECONDS 不能为负")
    if KB_BACKEND != "local":
        raise RuntimeError("v1.0 只支持 KB_BACKEND=local；IMA 接入尚未实现")
    if bool(AUTH_USERNAME) != bool(AUTH_PASSWORD):
        raise RuntimeError("AUTH_USERNAME 和 AUTH_PASSWORD 必须同时配置")
    if HOST not in ("127.0.0.1", "localhost", "::1") and not AUTH_PASSWORD and not PUBLIC_ACCESS:
        raise RuntimeError("对外监听前必须配置 AUTH_USERNAME 与 AUTH_PASSWORD，或显式设置 PUBLIC_ACCESS=1 公开演示")
    if MAX_CONCURRENT_JOBS < 1:
        raise RuntimeError("MAX_CONCURRENT_JOBS 必须至少为 1")
    if LLM_THINKING not in ("auto", "enabled", "disabled"):
        raise RuntimeError("LLM_THINKING 仅支持 auto、enabled、disabled")
    for role in ("writer", "fast", "judge"):
        if llm_config(role)["thinking"] not in ("auto", "enabled", "disabled"):
            raise RuntimeError(f"{role} 的 thinking 配置无效")
