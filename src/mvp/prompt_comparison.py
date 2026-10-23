"""固定一次策划与证据，串行对照两个写作提示词；共用新版审核口径。"""
from __future__ import annotations

import copy
import hashlib
import time

from . import llm, pipeline as p, prompt_variants as pv, settings, marketing_templates
from .editorial_context import check_similarity
from .progress import Trace
from .verify import count_chars


def compare(task, instruction=None, on_update=None, *, frozen_shared=None):
    tr = Trace(on_update, budget_seconds=settings.GENERATION_BUDGET_SECONDS * 3)
    task = copy.deepcopy(task)
    task["prompt_variant"] = "differentiated"
    task = marketing_templates.prepare_task(task)
    task.pop("similarity_feedback", None)
    versions = {v: pv.manifest(v) for v in pv.VARIANTS}
    prompt_texts = {v: {name: pv.directory(v).joinpath(name + ".md").read_text(encoding="utf-8")
                        for name in pv.STEPS} for v in pv.VARIANTS}
    results = {}
    shared = {}
    note = "固定新版策划、证据、上下文、模型与平台策略，仅切换写作提示词；两稿各生成一次，不自动修订，统一使用新版审核。"

    def finish(status="comparison"):
        tr.emit("workflow_finished", "controller", label="提示词对照已完成", status=status)
        snapshot = tr.snapshot()
        tr.closed = True
        return {"status": status, "mode": "prompt_comparison", "scope": note, "task": task,
                "prompt_versions": versions, "shared": shared, "variants": results,
                "prompt_snapshots": prompt_texts,
                "total_ms": int((time.monotonic() - tr.started) * 1000),
                "trace": snapshot["steps"], "events": snapshot["events"], "artifacts": snapshot["artifacts"],
                "llm_calls": copy.deepcopy(tr.calls)}

    missing = p.check_task(task)
    if missing:
        results["preparation"] = missing
        return finish("comparison_incomplete")
    kb = p.get_kb()
    tr.publish("comparison_scope", {"note": note, "versions": versions}, "controller", "固定条件对照已开始")
    tr.deadline = time.monotonic() + settings.GENERATION_BUDGET_SECONDS
    try:
        if frozen_shared is not None:
            shared = copy.deepcopy(frozen_shared)
            scene, plan, strat = shared["scene"], shared["planning"], shared["strategy"]
            task["creative_context"] = shared["creative_context"]
            dm = p.decide_model({**task, "product": shared["model"]}, scene, kb)
            if dm["status"] != "ok":
                raise ValueError("固定策划的型号已不可用")
            doc = kb.load(dm["model_id"])
            available = {im.id: im for im in doc.images}
            available.update({im.id: im for im in p.web_images.cached_images(doc, require_fresh=False)})
            images = [available[row["name"]] for row in shared["images"] if row["name"] in available]
            if p.image_catalog(images) != shared["images"] or p.style_examples(task["platform"]) != shared["style_examples"]:
                raise ValueError("图片或风格例子已有变化，请重新准备共同输入")
            facts = plan["facts"]
            shared["reused_preparation_digest"] = shared.pop("digest", None)
            shared["review_prompt"] = versions["differentiated"]
            tr.publish("frozen_preparation", {"digest": shared["reused_preparation_digest"]}, "planner", "沿用已保存策划与证据，不重新选题")
        else:
            scene = tr.run("scene", "整理共用需求", lambda: p.parse_scene_cached(task, instruction))
            if scene.get("need_info", {}).get("blocking") and p._clarify_round(task) >= p.MAX_CLARIFY_ROUNDS:
                scene["need_info"] = {**scene["need_info"], "blocking": False, "deferred": True}
            if scene.get("need_info", {}).get("blocking"):
                results["preparation"] = {"status": "need_info", "questions": scene["need_info"].get("questions", [])}
                return finish("comparison_incomplete")
            model_task = task
            if task.get("_template_product") and not task.get("product"):
                model_task = {**task, "product": task["_template_product"]}
            dm = tr.run("model", "确定样板对应型号" if task.get("_template_product") else "确定共用型号", lambda: p.decide_model(model_task, scene, kb))
            if dm["status"] != "ok":
                results["preparation"] = dm
                return finish("comparison_incomplete")
            strat = p.plan_strategy(task, scene, kb, dm["model_id"], instruction)
            retrieved = tr.run("retrieve", "固定产品资料和图片", lambda: p.retrieve(kb, dm["model_id"], strat),
                               view=lambda r: {"model": r["doc"].name, "images": len(r["images"])})
            doc, images = retrieved["doc"], retrieved["images"]
            task["_resolved_model_id"] = doc.id
            task["_resolved_model_name"] = doc.name
            plan, hit = tr.run("extract", "只做一次共用策划", lambda: p.plan_content_cached(doc, scene, strat, task, instruction))
            facts = plan["facts"]
            shared = {"scene": scene, "planning": plan, "strategy": p._strategy_view(strat),
                      "creative_context": task.get("creative_context") or {}, "model": doc.name,
                      "images": p.image_catalog(images), "cache_hit": hit,
                      "writer_model": settings.FAST_MODEL if task.get("speed") == "fast" else settings.WRITER_MODEL,
                      "judge_model": settings.FAST_MODEL if task.get("speed") == "fast" else settings.JUDGE_MODEL,
                      "review_prompt": versions["differentiated"], "cross_review": "共用 cross-review.md",
                      "style_examples": p.style_examples(task["platform"]), "instruction": instruction or ""}
        shared["request"] = {k: v for k, v in task.items() if k not in ("prompt_variant", "creative_context", "similarity_feedback")}
        if plan.get("template"):
            task["_template_plan"] = copy.deepcopy(plan["template"])
        shared["digest"] = hashlib.sha256(p.jdump(shared).encode()).hexdigest()[:20]
        tr.publish("comparison_inputs", shared, "planner", "两份稿件的共同输入已固定")
    except (llm.LLMError, ValueError) as exc:
        results["preparation"] = {"status": "error", "error": str(exc)}
        return finish("comparison_incomplete")

    for variant in pv.VARIANTS:
        tr.deadline = time.monotonic() + settings.GENERATION_BUDGET_SECONDS
        branch_task = {**copy.deepcopy(task), "prompt_variant": variant}
        article = None
        branch_started = time.monotonic()
        det = {"issues": [], "platform_issues": [], "images": []}
        jd = {"overall": "not_reviewed", "problems": []}
        error = None
        try:
            raw = tr.run("compose_" + variant, pv.VARIANTS[variant] + " · 创作", lambda: p.compose(
                branch_task, copy.deepcopy(scene), copy.deepcopy(strat), copy.deepcopy(facts), images,
                instruction, writer_model=shared["writer_model"], plan=copy.deepcopy(plan)),
                view=lambda a: {"title": a.get("title")})
            article = p.normalize_article(raw, facts, images, task=branch_task, plan=plan)
            tr.publish("draft:" + variant, article, "editor", pv.VARIANTS[variant] + " · 实际初稿")
            det = p.deterministic_check(article, facts, doc, strat, images, branch_task)
            # 两边的审核输入里也不携带作者版本标签，避免按标签给分。
            review_task = {k: v for k, v in task.items() if k != "prompt_variant"}
            # 审核函数用版本选项选择系统提示词，载荷不需要作者标签。
            jd = tr.run("judge_" + variant, "统一口径审核 · " + variant, lambda: p.judge(
                article, facts, strat, det, shared["judge_model"], images,
                {**review_task, "prompt_variant": "differentiated"}, plan.get("risks", [])))
            jd = tr.run("cross_" + variant, "核对审核争议 · " + variant, lambda: p.reconcile.cross_check(
                jd, article, facts, strat, review_task, shared["judge_model"]))
        except (llm.LLMError, ValueError) as exc:
            error = str(exc)
        entry = {"prompt_version": versions[variant], "shared_digest": shared["digest"],
                 "total_ms": int((time.monotonic() - branch_started) * 1000), "error": error,
                 "writer_system_digest": hashlib.sha256(p.prompt("compose", variant).encode()).hexdigest()}
        if article is not None:
            issues = p.collect_issues(det, jd)
            if error:
                issues.append("生成或审核未完成：" + error)
            issues.extend("关键需求缺依据：" + str(g) for g in plan.get("critical_gaps", []))
            if scene.get("need_info", {}).get("deferred"):
                issues.append("两轮确认后仍有未知需求，相关条件尚未验证。")
            entry.update(article=article, status="ok_with_flags" if issues else "ok", chars=count_chars(article),
                         verification={"state": "needs_review" if issues else "passed", "remaining": issues,
                                       "rules": det, "judge": jd},
                         similarity=check_similarity(article, task.get("creative_context") or {}, facts))
        else:
            entry.update(status="error", article=None)
        results[variant] = entry
        tr.publish("comparison:" + variant, entry, "controller", pv.VARIANTS[variant] + " · 结果已保留")
    return finish()
