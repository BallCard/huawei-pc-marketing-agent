"""用独立上下文复核具体争议，只有可回查的原文才能撤销事实风险。"""
from __future__ import annotations

import copy
import hashlib
import json
import re

from . import llm, settings, marketing_templates


def optional(problem: dict) -> bool:
    return (problem.get("type") in ("expression", "style", "tone") and
            problem.get("severity") not in ("high", "critical") and
            not problem.get("deterministic") and not re.search(
                r"违反.*(?:硬限制|明确要求)|无依据|未.*(?:证实|验证|确认|保留)|虚构体验|型号错误|价格错误|缺.*(?:条件|限定)|无法确认.*(?:兼容|适配)|错字|缺字|遮挡|裁切|不可读",
                str(problem.get("detail", ""))))


def normalize(review: dict) -> dict:
    out = copy.deepcopy(review)
    improvements = out.get("improvements", []) or []
    raw = [{"type": "expression", **p} if p in improvements else p
           for p in out.get("problems", out.get("must_fix", [])) or []]
    for p in improvements:
        p = {"type": "expression", **p}
        if p not in raw:
            raw.append(p)
    for p in out.get("must_fix", []) or []:
        if p not in raw:
            raw.append(p)
    out.setdefault("original_problems", copy.deepcopy(raw))
    suggestions = []
    for problem in raw:
        if optional(problem) and problem not in suggestions:
            suggestions.append(problem)
    out["improvements"] = suggestions
    out["problems"] = [p for p in raw if not optional(p)]
    out["must_fix"] = out["problems"][:]
    if raw and not out["problems"] and out.get("overall") in ("needs_fix", "pass", "ok"):
        out["overall"] = "pass"
    return out


def issue_id(problem: dict) -> str:
    return hashlib.sha256(json.dumps(problem, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def _compact(text) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def _article_text(article: dict, problem: dict) -> str:
    where, index = problem.get("where"), problem.get("index", -1)
    if where in ("title", "lead", "cta"):
        return article.get(where, "")
    if isinstance(index, int) and 0 <= index < len(article.get("blocks", [])):
        block = article["blocks"][index]
        return block.get("text", block.get("caption", ""))
    return ""


def _supported_dismissal(decision: dict, problem: dict, article: dict, facts: list[dict], task=None) -> bool:
    if not str(decision.get("reason") or "").strip():
        return False
    current = _compact(_article_text(article, problem))
    quote = _compact(decision.get("article_quote"))
    if not quote and decision.get("verdict") == "supported":
        quote = current  # 实际句段由程序读取，随后仍须与完整证据及条件逐字核对。
    if not current or quote != current:
        return False
    refs = set(article.get("fact_refs", {}).get(problem.get("where"), []))
    index = problem.get("index", -1)
    if isinstance(index, int) and 0 <= index < len(article.get("blocks", [])):
        refs.update(article["blocks"][index].get("fact_refs", []))
    for citation in decision.get("evidence", []) or []:
        if not isinstance(citation, dict):
            continue
        fact = next((f for f in facts if f.get("id") == citation.get("fact_id") in refs), None)
        if not fact or decision.get("verdict") != "supported":
            continue
        if fact.get("kind") == "demo_context":
            labels = marketing_templates.disclosures(task or {}, (task or {}).get("_template_plan"))
            if not (task or {}).get("demo_mode") or not labels or not set(labels).issubset(article.get("disclosures", [])):
                continue
        original = _compact(fact.get("text"))
        cited = _compact(citation.get("quote"))
        conditions = [_compact(c.get("text", "") if isinstance(c, dict) else c) for c in fact.get("conditions", [])]
        full = original + "".join(conditions)
        # 必须引用整条依据及条件，不能摘取一个数字、无关事实或漏掉版本条件。
        plain = lambda s: re.sub(r"[\W_]+", "", s)
        if (original and cited in full and original in cited and all(c in cited for c in conditions)
                and plain(current) == plain(full) and all(plain(c) in plain(current) for c in conditions)):
            return True
    # “到店核对软件”本身没有保证兼容；仅允许用实际邀请原句撤销这种误判。
    return bool(decision.get("verdict") == "no_fact_claim" and
                re.fullmatch(r"(?:请|建议|欢迎|到店|带).{0,60}(?:核对|确认|体验|试用).{0,25}[。！!？?]?", quote) and
                not re.search(r"保证|一定|都能|已适配|开箱即|兼容所有|支持|无需|满足|流畅|顺畅|适合|\d|全部|任何|所有", quote))


def cross_check(review: dict, article: dict, facts: list[dict], strategy: dict,
                task: dict, model: str | None = None) -> dict:
    out = normalize(review)
    problems = out["problems"]
    if not problems or out.get("overall") in ("incomplete", "not_reviewed"):
        out["cross_review"] = {"status": "not_needed", "decisions": [], "dismissed": []}
        return out
    ids = {issue_id(p): p for p in problems}
    payload = {"原始需求": task, "实际终稿": article, "完整事实及条件": facts,
               "平台规则": {k: strategy.get(k) for k in ("platform_name", "chars", "writing_limits", "price_policy")},
               "需要交叉核对的意见": [{"id": key, **p} for key, p in ids.items()]}
    guidance = ""
    if task.get("_template_plan"):
        payload["已审核样板"] = task["_template_plan"]
        payload["可见概念标识"] = article.get("disclosures", [])
        guidance = "\n本次按已审核样板创作。D 是标有 fictional_demo 的虚构演示设定，只能在 demo_mode=true 且 disclosures 可见时支持完全对应的演示门店／安排，不能证明产品参数、价格、真实合作或客户体验。不要把标注后的情景演绎当成真人经历；撤销意见仍须满足完整逐字原文与条件校验，不新增推断例外。"
    try:
        raw = llm.chat([{"role": "system", "content": (settings.PKG / "prompts" / "cross-review.md").read_text(encoding="utf-8") + guidance},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                       model=model or settings.JUDGE_MODEL, role="judge", json_mode=True,
                       max_tokens=2600, retries=0, timeout=35)
        data = llm.parse_json(raw)
        decisions = data.get("decisions", [])
        if not isinstance(decisions, list):
            raise ValueError("交叉复核缺少逐项结论")
    except llm.BudgetExceeded:
        raise
    except (llm.LLMError, ValueError, TypeError, AttributeError):
        out["cross_review"] = {"status": "incomplete", "decisions": [], "dismissed": [],
                               "reason": "交叉复核未完成，保留重要风险原判。"}
        return out
    kept, dismissed, audit = [], [], []
    for key, problem in ids.items():
        matches = [d for d in decisions if isinstance(d, dict) and d.get("id") == key]
        decision = matches[0] if len(matches) == 1 else {}
        evidence = decision.get("evidence")
        decision["evidence"] = [c for c in evidence if isinstance(c, dict)] if isinstance(evidence, list) else []
        action = decision.get("decision")
        accepted = (action == "dismiss" and problem.get("type") in ("unsupported", "evidence_gap", "overclaim", "facts") and
                    not problem.get("deterministic") and _supported_dismissal(decision, problem, article, facts, task))
        # 模型称“确定错误”仍需可回查依据；缺证据只能保留为重要未决。
        refs = article.get("fact_refs", {}).get(problem.get("where"), [])
        index = problem.get("index", -1)
        if isinstance(index, int) and 0 <= index < len(article.get("blocks", [])):
            refs = article["blocks"][index].get("fact_refs", [])
        confirmed = action == "confirm" and bool(decision.get("reason")) and any(
            isinstance(c, dict) and any(f.get("id") == c.get("fact_id") and
                (not refs or f.get("id") in refs) and
                len(_compact(c.get("quote"))) >= 6 and _compact(c.get("quote")) in _compact(f.get("text")) for f in facts)
            for c in decision.get("evidence", []) or [])
        row = {**problem, "cross_check": "dismissed" if accepted else "confirmed" if confirmed else "unresolved",
               "cross_reason": str(decision.get("reason") or "交叉复核仍无法确认。"),
               "root_cause": str(decision.get("root_cause") or "").strip(), "evidence": decision.get("evidence", [])}
        if action == "dismiss" and not accepted:
            row["cross_reason"] = "复核提出撤销，但原句、引用或适用条件未通过校验，保留待确认。" + row["cross_reason"]
        if accepted:
            dismissed.append({**row, "evidence": decision.get("evidence", []), "verdict": decision.get("verdict"),
                              "article_quote": decision.get("article_quote", "")})
        else:
            kept.append(row)
        audit.append({"id": key, "decision": row["cross_check"], "reason": row["cross_reason"], "model_decision": decision})
    out["problems"], out["must_fix"] = kept, kept[:]
    out["cross_review"] = {"status": "completed", "decisions": audit, "dismissed": dismissed}
    # 更新对应语义主张，避免已撤销的误判仍在事实表里显示失败。
    for claim in out.get("claims", []):
        location = (claim.get("where"), claim.get("index", -1))
        if any((p.get("where"), p.get("index", -1)) == location for p in dismissed) and not any(
                (p.get("where"), p.get("index", -1)) == location for p in kept):
            verdicts = [p.get("verdict") for p in dismissed if (p.get("where"), p.get("index", -1)) == location]
            claim["verdict"] = "no_fact_claim" if all(v == "no_fact_claim" for v in verdicts) else "supported"
    out["overall"] = "needs_fix" if kept else "pass"
    return out
