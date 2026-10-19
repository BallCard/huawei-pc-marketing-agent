"""确定性核验：数字对账、型号串用、图片登记与型号、合规规则表、平台规格。

这一层不调用模型，结果可复现；独立审核模型（judge）在其上做语义层核验。
"""
from __future__ import annotations

import re
from functools import lru_cache

import yaml

from . import settings
from .kb import ModelDoc, norm

UNIT = r"(?:mm|cm|kg|g|Wh|W|nits|nit|Hz|GB|TB|MB|英寸|寸|小时|h|ppi|PPI|万|元|克|毫米|厘米|瓦|像素|nm|MP|K|倍|%|％|:|：)"
NUM_UNIT_RE = re.compile(rf"(\d+(?:[.,]\d+)?)\s*(?:×\s*\d+(?:\.\d+)?\s*)?{UNIT}")
MODEL_RE = re.compile(r"MateBook(?:\s*(?:Fold|Pro\s?S|Pro|GT|X|D|SE|Ultra|酷睿|\d{2}))+", re.I)


@lru_cache(maxsize=1)
def compliance_rules() -> list[dict]:
    d = yaml.safe_load((settings.PKG / "config" / "compliance.yaml").read_text(encoding="utf-8"))
    return [{**r, "re": re.compile(r["pattern"])} for r in d["rules"]]


def scan_compliance(text: str, allowed_text: str = "") -> list[dict]:
    """返回命中列表。命中词若本身出现在所选事实原文里（引用资料），不算违规。"""
    hits = []
    for r in compliance_rules():
        for m in r["re"].finditer(text or ""):
            w = m.group(0)
            if w and w in allowed_text:
                continue
            hits.append({"rule": r["rule"], "kind": r["kind"], "hit": w})
    return hits


def unit_numbers(text: str) -> list[str]:
    out = []
    for m in NUM_UNIT_RE.finditer(text or ""):
        n = m.group(1).replace(",", "")
        out.append(n)
    return out


def check_numbers(text: str, support_nums: set[str]) -> list[str]:
    """带单位的数字必须能在所引用事实原文里找到；找不到视为无依据。"""
    bad = []
    for n in unit_numbers(text):
        if n not in support_nums and n.rstrip("0").rstrip(".") not in support_nums:
            bad.append(n)
    return sorted(set(bad))


def check_model_mentions(text: str, doc: ModelDoc) -> list[str]:
    """正文里出现的 MateBook 型号串必须与所选型号一致（防串号）。"""
    me = norm(doc.name) + "|" + norm(doc.id)
    bad = []
    for m in MODEL_RE.finditer(text or ""):
        tok = norm(m.group(0))
        if len(tok) < 8:      # 仅 “matebook” 之类，不构成型号
            continue
        if tok not in me:
            bad.append(m.group(0).strip())
    return sorted(set(bad))


def image_model_ok(img, doc: ModelDoc) -> bool:
    """图片索引.csv「产品型号」必须对得上所选型号。"""
    a, b = norm(img.model), norm(doc.name)
    return bool(a) and (a == b or a in b or b in a)


def count_chars(article: dict) -> int:
    txt = (article.get("lead") or "") + "".join(
        b.get("text", "") for b in article.get("blocks", []) if b.get("type") == "text") + (article.get("cta") or "")
    return len(re.sub(r"\s+", "", txt))


def check_platform(article: dict, spec: dict) -> list[str]:
    issues = []
    n_img = sum(1 for b in article.get("blocks", []) if b.get("type") == "image")
    lo, hi = spec["images"]
    if n_img < lo:
        issues.append(f"配图 {n_img} 张，少于{spec['name']}要求的 {lo} 张")
    if n_img > hi:
        issues.append(f"配图 {n_img} 张，多于{spec['name']}上限 {hi} 张")
    chars = count_chars(article)
    lo_c, hi_c = spec["chars"]
    if chars < lo_c * 0.7:
        issues.append(f"正文约 {chars} 字，明显少于{spec['name']}建议的 {lo_c}-{hi_c} 字")
    if chars > hi_c:
        issues.append(f"正文约 {chars} 字，超过{spec['name']}上限 {hi_c} 字；请删减次要卖点和重复铺垫")
    limits = spec.get("writing_limits", {})
    fields = [("title", "标题", article.get("title", "")), ("lead", "导语", article.get("lead", "")),
              ("cta", "行动引导", article.get("cta", ""))]
    for idx, block in enumerate(article.get("blocks", []), 1):
        if block.get("type") == "text":
            fields.append(("text_block", f"第 {idx} 块正文", block.get("text", "")))
        elif block.get("type") == "image":
            fields.append(("caption", f"第 {idx} 块图注", block.get("caption", "")))
    for key, label, text in fields:
        limit = limits.get(key)
        size = len(re.sub(r"\s+", "", text or ""))
        if limit and size > limit:
            issues.append(f"{label} {size} 字，超过 {limit} 字；改为短句，保留必要的版本与适用条件")
    if spec.get("tags") and not article.get("tags"):
        issues.append("缺少话题标签")
    return issues


def price_leak(text: str) -> list[str]:
    """价格 forbid 时，文本里不得出现金额。"""
    return sorted({m.group(0) for m in re.finditer(r"\d[\d,]*(?:\.\d+)?\s*(?:元|¥|￥)|[¥￥]\s*\d[\d,]*|起售价|到手价|售价|价格\s*\d", text or "")})
