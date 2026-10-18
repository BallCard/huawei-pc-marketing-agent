"""运行配置：全部来自环境变量（可由仓库根 .env 提供），代码里不放任何密钥。"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = Path(__file__).resolve().parent


def _load_dotenv() -> None:
    f = ROOT / ".env"
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
FAST_MODEL = os.environ.get("FAST_MODEL", "gemini-3.8-flash-high")  # 场景解析/事实提取/修订（可用 FAST_MODEL 单独降档换速度）
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "gemini-3.8-flash-high")  # 独立审核：与写作同模型，靠独立提示词+确定性规则表防自审；有其他模型额度时可用环境变量覆盖
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "180"))

# 知识库：local 读 data/kb 副本；ima 走 ima OpenAPI（评测/演示必须用 ima，见 docs/contracts/ima-access.md）
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
CACHE_DIR = Path(os.environ.get("CACHE_DIR", str(KB_DIR.parent / "cache")))
KB_BASE_DATE = "2026-10-17"  # 知识库事实基准日
