"""将评审分成自动修订、可选建议和重要未决；人工裁定保留自动原判。"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timezone

from .reconcile import normalize, optional


class ReviewConflict(ValueError):
    pass


def fingerprint(result: dict) -> str:
    payload = copy.deepcopy({key: result.get(key) for key in ("article", "verification", "context_version", "poster")})
    (payload.get("verification") or {}).pop("triage", None)
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:24]


def questions(result: dict) -> dict:
    vf = result.get("verification") or {}
    version = vf.get("article_version", 1)
    artifacts = result.get("artifacts") or {}
    judge = normalize(vf.get("judge") or {})
    records, automatic, suggestions = [], [], []
    dismissed = list((judge.get("cross_review") or {}).get("dismissed", [])) + judge.get("dismissed_counting_notes", [])
    seen = set()
    article = result.get("article") or {}

    def add(problem, origin, target=None):
        detail = str(problem.get("detail") or "").strip()
        if not detail:
            return
        index, where = problem.get("index", -1), problem.get("where", "article")
        quote = problem.get("quote") or ""
        if not quote and where in ("title", "lead", "cta"):
            quote = article.get(where, "")
        if not quote and isinstance(index, int) and 0 <= index < len(article.get("blocks", [])):
            block = article["blocks"][index]
            quote = block.get("text", block.get("caption", ""))
        identity = json.dumps([where, index, quote, detail], ensure_ascii=False)
        if identity in seen:
            return
        seen.add(identity)
        row = {**problem, "id": hashlib.sha256(identity.encode()).hexdigest()[:16], "where": where,
               "index": index, "quote": quote, "detail": detail,
               "type": problem.get("type", problem.get("kind", origin)), "origin": origin,
               "direction": problem.get("direction", ""), "question": "这个重要条件，现有资料仍无法确认，怎样处理？"}
        if target is not None:
            bucket = target
        elif optional(problem):
            bucket = suggestions
        elif origin == "rules" or problem.get("cross_check") == "confirmed" or problem.get("deterministic"):
            bucket = automatic
        else:
            bucket = records
        bucket.append(row)

    rules = artifacts.get(f"rules:{version}") or vf.get("rules") or {}
    for problem in rules.get("issues", []):
        add(problem, "rules", automatic)
    for detail in rules.get("platform_issues", vf.get("platform", [])):
        add({"detail": detail, "type": "platform", "direction": "按平台硬限制修订后重新核验。"}, "rules", automatic)
    for problem in judge.get("problems", []):
        # 模型和规则指向同一位置、同一错误时，以规则的修订任务为准。
        if not any(p["detail"] == problem.get("detail") and p["where"] == problem.get("where") and
                   p["index"] == problem.get("index", -1) for p in automatic):
            add(problem, "judge")
    for problem in judge.get("improvements", []):
        add(problem, "judge", suggestions if optional(problem) else None)
    for detail in vf.get("remaining", []):
        detail = detail if isinstance(detail, str) else detail.get("detail", "")
        known = records + automatic + suggestions + dismissed
        if not any(p.get("detail") and p["detail"] in detail for p in known):
            retry = "时间预算" in detail or "秒总预算" in detail or any(s in detail for s in ("未完成", "未通过或未完成"))
            add({"detail": detail, "type": "retry" if retry else "uncertain"}, "remaining", automatic if retry else None)
    poster = result.get("poster") or {}
    image_review = normalize(poster.get("review") or {})
    for problem in sorted(image_review.get("problems", []), key=lambda p: not p.get("deterministic", False)):
        if not any(p["origin"] == "poster" and p["quote"] and p["quote"] == problem.get("quote") and
                   p["type"] == problem.get("type") for p in automatic):
            add(problem, "poster")
    for problem in image_review.get("improvements", []):
        add(problem, "poster", suggestions if optional(problem) else None)
    dismissed += (image_review.get("cross_review") or {}).get("dismissed", [])
    if poster.get("status") == "error" and poster.get("error"):
        add({"detail": poster["error"], "type": "retry", "direction": "重试海报生成或审核。"}, "poster", automatic)
    if judge.get("overall") in ("not_reviewed", "incomplete", None) and not any(p["type"] == "retry" for p in automatic):
        add({"detail": "自动评审未完成，尚无完整审核结论。", "type": "retry", "direction": "重新运行独立审核。"}, "review", automatic)
    if image_review.get("overall") == "incomplete":
        add({"detail": "成图审核未完成，需要重新核验实际图片。", "type": "retry"}, "poster", automatic)
    if not records and not automatic and (vf.get("judge") or {}).get("overall") == "needs_fix" and judge.get("overall") == "pass":
        add({"detail": "历史稿件仅剩可选建议，请重新核验后更新通过状态。", "type": "retry"}, "review", automatic)

    # 同一具体根因、风险类别、引用依据才合并；每个原始位置均保留。
    groups = {}
    for row in records:
        refs = article.get("fact_refs", {}).get(row["where"], [])
        if isinstance(row["index"], int) and 0 <= row["index"] < len(article.get("blocks", [])):
            refs = article["blocks"][row["index"]].get("fact_refs", [])
        family = "evidence" if row["type"] in ("unsupported", "overclaim", "evidence_gap", "facts") else row["type"]
        root = str(row.get("root_cause") or "").strip()
        subject = row["detail"] + " " + row["quote"]
        domain = next((name for name, pattern in (("price", r"价格|报价|起价|优惠|\d+元"),
                      ("compatibility", r"软件|兼容|适配|Windows|鸿蒙|CPU架构"),
                      ("weight", r"重量|kg|千克"), ("battery", r"续航|电池|小时"))
                      if re.search(pattern, subject, re.I)), family)
        if re.fullmatch(r"(?:事实|缺少|缺乏|没有|产品|证据|依据|不足|问题|风险|无法确认|重要|待确认|支持|所有|未确认|资料|需核对)+", root):
            root = ""
        key = (row["origin"], domain, root, tuple(sorted(refs)) if refs else row["quote"]) if root else (row["id"],)
        if key not in groups:
            groups[key] = {**row, "members": [], "occurrences": 0}
        groups[key]["members"].append(row)
        groups[key]["occurrences"] += 1
    grouped = list(groups.values())
    for row in grouped:
        row["id"] = hashlib.sha256("|".join(sorted(p["id"] for p in row["members"])).encode()).hexdigest()[:16]
        if row.get("root_cause"):
            row["question"] = f"关于“{row['root_cause']}”，现有依据仍不足，怎样处理？"
        if row["occurrences"] > 1:
            row["detail"] = f"{row['root_cause']}（涉及 {row['occurrences']} 处，统一处理）"
    return {"token": fingerprint(result), "version": version, "questions": grouped,
            "automatic_issues": automatic, "suggestions": suggestions, "dismissed": dismissed,
            "summary": {"human": len(grouped), "automatic": len(automatic), "optional": len(suggestions),
                        "dismissed": len(dismissed), "merged": len(records) - len(grouped)},
            "facts": (result.get("evidence") or {}).get("facts", []),
            "previous": result.get("human_review") or result.get("automatic_followup"), "automatic_overall": judge.get("overall")}


def annotate(result: dict) -> dict:
    if result.get("article"):
        result.setdefault("verification", {})["triage"] = questions(result)["summary"]
    return result


def validate_decision(result: dict, payload: dict) -> dict:
    form = questions(result)
    if payload["token"] != form["token"]:
        raise ReviewConflict("稿件或审核结论已更新，请重新打开问题详情。")
    records = {row["id"]: row for row in form["questions"]}
    if not records and not form["automatic_issues"]:
        raise ValueError("当前作品没有待裁定或待修订的问题。")
    answers = payload.get("answers") or []
    if len({a["id"] for a in answers}) != len(answers) or {a["id"] for a in answers} != set(records):
        raise ValueError("请逐项选择处理方式后再提交。")
    decisions = []
    for answer in answers:
        choice, reason = answer["choice"], answer.get("reason", "").strip()
        if choice == "disagree" and not reason:
            raise ValueError("认为误判时，请补充裁定理由或依据。")
        decisions.append({**records[answer["id"]], "choice": choice, "reason": reason})
    resolution = payload["resolution"]
    if resolution == "adopt" and (form["automatic_issues"] or any(a["choice"] != "disagree" for a in decisions)):
        raise ValueError("存在确定错误、未完成审核或待确认项时，请先修订或暂缓，不能直接采用。")
    if resolution == "continue":
        decisions += [{**row, "choice": "recheck" if row["type"] == "retry" else "fix", "reason": "", "automatic": True}
                      for row in form["automatic_issues"]]
    return {"token": form["token"], "resolution": resolution, "answers": decisions,
            "mode": "human" if records else "automatic",
            "state": {"adopt": "adopted", "hold": "deferred", "continue": "continuing"}[resolution],
            "at": datetime.now(timezone.utc).isoformat(), "version": form["version"]}


def instructions(decision: dict) -> list[str]:
    lines = []
    for answer in decision["answers"]:
        action = {"fix": "接受意见，请定向修正", "disagree": "用户认为误判，请结合所述理由重新判断，不将用户说法直接当作产品证据",
                  "defer": "用户尚未确认；不得将缺口写成已证实承诺", "recheck": "重新完成独立审核，不视为用户批准"}[answer["choice"]]
        for member in answer.get("members") or [answer]:
            lines.append(f"{action}。位置：{member['where']}#{member['index']}。原问题：{member['detail']}。原句：{member['quote']}。修改建议：{member['direction']}。用户说明：{answer['reason']}")
    return lines
