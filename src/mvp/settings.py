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

# 大模型：OpenAI 兼容接口。开发期默认指向本机反代，无需密钥。档位默认 high。
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8045/v1").rstrip("/")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
WRITER_MODEL = os.environ.get("WRITER_MODEL", "gemini-3.8-flash-high")  # 写作/视觉
FAST_MODEL = os.environ.get("FAST_MODEL", "gemini-3.8-flash-low")
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "gemini-3.8-flash-medium")
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "180"))
LLM_THINKING = os.environ.get("LLM_THINKING", "auto")


def llm_config(role: str = "writer") -> dict:
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

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "7860"))
AUTH_USERNAME = os.environ.get("AUTH_USERNAME", "")
AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD", "")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "1" if HOST not in ("127.0.0.1", "localhost", "::1") else "0") == "1"
JOB_DB = Path(os.environ.get("JOB_DB") or str(ROOT / "data" / "state" / "jobs.sqlite3"))
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "1"))


def validate_runtime() -> None:
    if KB_BACKEND != "local":
        raise RuntimeError("v1.0 只支持 KB_BACKEND=local；IMA 接入尚未实现")
    if bool(AUTH_USERNAME) != bool(AUTH_PASSWORD):
        raise RuntimeError("AUTH_USERNAME 和 AUTH_PASSWORD 必须同时配置")
    if HOST not in ("127.0.0.1", "localhost", "::1") and not AUTH_PASSWORD:
        raise RuntimeError("对外监听前必须配置 AUTH_USERNAME 与 AUTH_PASSWORD，并通过 HTTPS 访问")
    if MAX_CONCURRENT_JOBS < 1:
        raise RuntimeError("MAX_CONCURRENT_JOBS 必须至少为 1")
    if LLM_THINKING not in ("auto", "enabled", "disabled"):
        raise RuntimeError("LLM_THINKING 仅支持 auto、enabled、disabled")
    for role in ("writer", "fast", "judge"):
        if llm_config(role)["thinking"] not in ("auto", "enabled", "disabled"):
            raise RuntimeError(f"{role} 的 thinking 配置无效")
