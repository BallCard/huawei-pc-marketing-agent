"""把实际终稿的未通过原因转成可裁定的问题；人工结论不覆盖自动审核。"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone


class ReviewConflict(ValueError):
    pass


def fingerprint(result: dict) -> str:
    payload = {key: result.get(key) for key in ("article", "verification", "context_version", "poster")}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:24]


def questions(result: dict) -> dict:
    vf = result.get("verification") or {}
    version = vf.get("article_version", 1)
    artifacts = result.get("artifacts") or {}
    judge = vf.get("judge") or {}
    records = []

    def add(problem, origin):
        detail = str(problem.get("detail") or "").strip()
        if not detail:
            return
        index = problem.get("index", -1)
        where = problem.get("where", "article")
        quote = problem.get("quote") or ""
        article = result.get("article") or {}
        if not quote and where in ("title", "lead", "cta"):
            quote = article.get(where, "")
        if not quote and isinstance(index, int) and 0 <= index < len(article.get("blocks", [])):
            block = article["blocks"][index]
            quote = block.get("text", block.get("caption", ""))
        if any((row["where"],row["index"],row["quote"],row["detail"],row["origin"]) == (where,index,quote,detail,origin) for row in records):
            return
        identity = json.dumps([where, index, quote, detail, origin], ensure_ascii=False)
        records.append({"id": hashlib.sha256(identity.encode()).hexdigest()[:16], "where": where,
                        "index": index, "quote": quote, "detail": detail,
                        "type": problem.get("type", problem.get("kind", origin)), "origin": origin,
                        "direction": problem.get("direction", ""),
                        "question": "这条意见，你希望怎样处理？"})

    for problem in judge.get("problems", []):
        add(problem, "judge")
    rules = artifacts.get(f"rules:{version}") or {}
    for problem in rules.get("issues", []):
        add(problem, "rules")
    for detail in vf.get("remaining", []):
        detail = detail if isinstance(detail, str) else detail.get("detail", "")
        if not any(row["detail"] in detail for row in records):
            add({"detail": detail}, "remaining")
    poster = result.get("poster") or {}
    for problem in (poster.get("review") or {}).get("problems", []):
        add(problem, "poster")
    if poster.get("status") == "error" and poster.get("error"):
        add({"detail": poster["error"], "direction": "核对后重新生成海报。"}, "poster")
    if judge.get("overall") in ("not_reviewed", "incomplete", None) and not records:
        add({"detail": "自动评审未完成，尚无完整审核结论。", "direction": "重新运行独立审核，或由使用者核对后裁定。"}, "review")
    return {"token": fingerprint(result), "version": version, "questions": records,
            "facts": (result.get("evidence") or {}).get("facts", []),
            "previous": result.get("human_review"), "automatic_overall": judge.get("overall")}


def validate_decision(result: dict, payload: dict) -> dict:
    form = questions(result)
    if payload["token"] != form["token"]:
        raise ReviewConflict("稿件或审核结论已更新，请重新打开问题详情。")
    records = {row["id"]: row for row in form["questions"]}
    if not records:
        raise ValueError("当前作品没有待裁定的问题。")
    answers = payload.get("answers") or []
    if len({a["id"] for a in answers}) != len(answers) or {a["id"] for a in answers} != set(records):
        raise ValueError("请逐项选择处理方式后再提交。")
    decisions = []
    for answer in answers:
        choice = answer["choice"]
        reason = answer.get("reason", "").strip()
        if choice == "disagree" and not reason:
            raise ValueError("认为误判时，请补充裁定理由或依据。")
        decisions.append({**records[answer["id"]], "choice": choice, "reason": reason})
    resolution = payload["resolution"]
    if resolution == "adopt" and any(a["choice"] != "disagree" for a in decisions):
        raise ValueError("人工采用本稿前，需逐项确认原文可用并说明理由；有待修改或待确认项时请修订或暂缓。")
    return {"token": form["token"], "resolution": resolution, "answers": decisions,
            "state": {"adopt": "adopted", "hold": "deferred", "continue": "continuing"}[resolution],
            "at": datetime.now(timezone.utc).isoformat(), "version": form["version"]}


def instructions(decision: dict) -> list[str]:
    lines = []
    for answer in decision["answers"]:
        action = {"fix": "接受意见，请定向修正", "disagree": "用户认为误判，请结合所述理由重新判断，不将用户说法直接当作产品证据",
                  "defer": "用户尚未确认；不得将缺口写成已证实承诺"}[answer["choice"]]
        lines.append(f"{action}。原问题：{answer['detail']}。原句：{answer['quote']}。修改建议：{answer['direction']}。用户说明：{answer['reason']}")
    return lines
