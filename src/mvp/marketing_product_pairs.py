"""已审核营销手法对应的华为型号与预制视觉 fallback。"""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

from . import settings


def library() -> dict:
    return yaml.safe_load((settings.PKG / "config" / "marketing_product_pairs.yaml").read_text(encoding="utf-8"))


def pair(template_id: str) -> dict | None:
    row = library().get("pairs", {}).get(template_id)
    return copy.deepcopy(row) if row else None


def fallback_url(template_id: str) -> str | None:
    row = pair(template_id)
    if not row or not row.get("fallback_asset"):
        return None
    path = settings.PKG / "web" / row["fallback_asset"]
    if not path.exists():
        return None
    return "/static/" + row["fallback_asset"].replace("\\", "/")


def fallback_path(template_id: str) -> Path | None:
    row = pair(template_id)
    if not row or not row.get("fallback_asset"):
        return None
    path = settings.PKG / "web" / row["fallback_asset"]
    return path if path.exists() else None
