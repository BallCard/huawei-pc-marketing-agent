"""把需求追问整理成题目自带选项的表单，所有入口共享两轮上限。"""
from __future__ import annotations

import hashlib
import re

MAX_ROUNDS = 2
FIELDS = {"product", "audience", "scenario", "platform", "software", "system", "budget", "portability", "other"}


def round_count(task: dict) -> int:
    try:
        return max(0, int(task.get("clarify_round") or 0))
    except (TypeError, ValueError):
        return 0


def question_text(item) -> str:
    return str(item.get("question") or "").strip() if isinstance(item, dict) else str(item or "").strip()


def infer_field(text: str) -> str:
    # 软件问题经常顺带提到 CPU、系统、机型；先识别用户真正需要回答的内容。
    rules = [
        ("software", r"软件|编程|设计类|课程.*(?:要求|指定)"),
        ("product", r"(?:确认|选择|指定|哪个|哪款|具体|收录|对应|选).*?(?:型号|机型)|型号.*(?:选择|确认)|知识库里没有找到"),
        ("budget", r"预算|价位|经费|多少钱"),
        ("system", r"系统|Windows|macOS|鸿蒙|云电脑|虚拟机"),
        ("audience", r"人群|写给谁|谁看|目标读者|职业|年级"),
        ("platform", r"平台|发布到|发到|发在"),
        ("portability", r"携带|通勤|便携|重量.*(?:上限|不超过)"),
        ("scenario", r"场景|用途|做什么|用在哪"),
    ]
    return next((field for field, pattern in rules if re.search(pattern, text, re.I)), "other")


def prepare_questions(questions, task: dict, *, candidates=(), field="") -> list[dict]:
    """每轮只保留一个未答关键问题；候选型号只用于明确的型号选择题。"""
    answered = {question_text(a) for a in task.get("clarify_answers", []) if isinstance(a, dict)}
    answered_ids = {a.get("id") for a in task.get("clarify_answers", []) if isinstance(a, dict) and a.get("id")}
    for item in questions or []:
        text = question_text(item)
        if not text or text in answered:
            continue
        spec = item if isinstance(item, dict) else {}
        detected = infer_field(text)
        kind = field or spec.get("field") or detected
        if kind not in FIELDS:
            kind = detected
        if detected == "software" and kind == "product":
            kind = "software"
        qid = str(spec.get("id") or hashlib.sha256((kind + text).encode()).hexdigest()[:12])
        if qid in answered_ids:
            continue
        raw_options = spec.get("options") or []
        if not isinstance(raw_options, list):
            raw_options = []
        options = list(dict.fromkeys(o.strip() for o in raw_options if isinstance(o, str) and o.strip()))[:4]
        if kind == "product":
            options = [o for o in options if o in candidates or o == "按需求帮我推荐"]
            options = options or list(candidates)[:3]
            if "按需求帮我推荐" not in options:
                options = [*options[:3], "按需求帮我推荐"]
        else:
            options = [o for o in options if o not in candidates and not re.search(r"(?:HUAWEI\s*)?MateBook", o, re.I)]
        return [{"id": qid, "question": text, "field": kind, "options": options,
                 "placeholder": str(spec.get("placeholder") or ("填写软件名称；有明确版本要求再补充" if kind == "software" else "也可以写自己的情况…"))}]
    return []


def form_result(result: dict, task: dict) -> dict:
    """在任务出口执行，型号消歧和输入检查也不能绕过问询上限。"""
    if result.get("status") != "need_info":
        return result
    specs = prepare_questions(result.get("question_specs") or result.get("questions"), task,
                              candidates=result.get("candidates", []), field=result.get("question_field", ""))
    count = round_count(task)
    if count >= MAX_ROUNDS or not specs:
        return {**result, "status": "input_required", "questions": [], "question_specs": [],
                "unresolved_questions": [question_text(q) for q in result.get("questions", [])],
                "message": result.get("reason") or "现有信息还不足以安全确定型号，请在创作简报中明确型号或调整必须条件。",
                "clarification": {"round": min(count, MAX_ROUNDS), "max_rounds": MAX_ROUNDS, "exhausted": True}}
    # 型号候选属于型号题，不能污染软件、预算等问题的选项或输入框。
    if specs[0]["field"] != "product":
        result = {**result, "candidates": [], "candidate_ids": []}
    return {**result, "questions": [s["question"] for s in specs], "question_specs": specs,
            "clarification": {"round": count + 1, "max_rounds": MAX_ROUNDS, "exhausted": False}}
