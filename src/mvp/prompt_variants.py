"""显式选择提示词，不使用进程全局开关，线程间不会串版本。"""
from __future__ import annotations

import hashlib
from . import settings

DEFAULT = "baseline"
VARIANTS = {"baseline": "A · 原版基线", "differentiated": "B · 已审核样板模仿"}
STEPS = ("base", "scene", "recommend", "extract", "compose", "repair", "judge")


def directory(variant=DEFAULT):
    if variant not in VARIANTS:
        raise ValueError("未知提示词版本")
    root = settings.PKG / "prompts"
    return root / "baseline" if variant == "baseline" else root


def prompt(name, variant=DEFAULT):
    if name not in STEPS or name == "base":
        raise ValueError("未知提示词阶段")
    root = directory(variant)
    return root.joinpath("base.md").read_text(encoding="utf-8") + "\n\n---\n\n" + root.joinpath(name + ".md").read_text(encoding="utf-8")


def manifest(variant=DEFAULT):
    root = directory(variant)
    files = {name: hashlib.sha256(root.joinpath(name + ".md").read_bytes()).hexdigest() for name in STEPS}
    digest = hashlib.sha256(str(sorted(files.items())).encode()).hexdigest()[:20]
    return {"id": variant, "label": VARIANTS[variant], "digest": digest, "files": files}
