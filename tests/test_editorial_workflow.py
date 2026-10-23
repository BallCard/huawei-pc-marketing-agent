import copy
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.mvp import llm, pipeline
from src.mvp.kb import ModelDoc, Snippet
from src.mvp.progress import Trace


def scene():
    return dict(audience="大学新生", scenario="图书馆", user_problem="每天带电脑查资料", goal="到店体验",
                hard_constraints=[], soft_preferences=[], tradeoffs=[], unmappable=[],
                weights={}, prior_weights={}, llm_weights={}, top_dims=["portability"],
                need_info={"blocking": False, "questions": []})


def review(problems=()):
    return {"overall": "needs_fix" if problems else "pass", "problems": list(problems)}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.doc = ModelDoc("test", "测试电脑", "", Path("."), snippets=[
            Snippet("S1", "spec", "重量", "约 1.3 kg，仅配置 A", "facts.md"),
            Snippet("S2", "spec", "接口", "配备 USB-A 接口", "facts.md")])
        self.facts = [{"id": "F1", "sid": "S1", "text": self.doc.snippets[0].text,
                       "role": "proof", "why": "便携", "source": {"label": "重量", "model": self.doc.name}}]
        self.plan = dict(facts=self.facts, angles=[{"id": "A", "title": "携带"}, {"id": "B", "title": "接口"}],
                         selected_angle="A", decision_reason="证据支持携带", reader_task="每天查资料", goal="到店体验",
                         unsupported_requests=[], critical_gaps=[], risks=[])
        self.article = dict(title="去图书馆", lead="课本已经够重", blocks=[{"type": "text", "text": "配置 A 约 1.3 kg。", "fact_refs": ["F1"]}],
                            cta="到店体验", tags=[], pending_confirm=[])
        self.task = dict(product="测试电脑", audience="大学新生", scenario="图书馆", platform="moments", constraints=[])
        self.det = dict(issues=[], platform_issues=[], images=[])
        self.kb = Mock(backend="local")
        self.kb.resolve.return_value = ("ok", ["test"])
        self.kb.whoami.return_value = {"backend": "local"}
        self.kb.load.return_value = self.doc
        self.kb.prices.return_value = []
        patches = [patch.object(pipeline, "get_kb", return_value=self.kb),
                   patch.object(pipeline, "parse_scene_cached", return_value=scene()),
                   patch.object(pipeline, "plan_content_cached", return_value=(self.plan, False)),
                   patch.object(pipeline, "compose", return_value=self.article),
                   patch.object(pipeline, "deterministic_check", return_value=self.det),
                   patch.object(pipeline, "judge", return_value=review()),
                   patch.object(pipeline.web_images, "find_hero", return_value={"images": [], "status": "unavailable", "pages": []}),
                   patch.object(pipeline.reconcile, "cross_check", side_effect=lambda review, *a: pipeline.reconcile.normalize(review))]
        self.mocks = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)

    def test_specified_model_skips_recommend_and_direct_pass_skips_revision(self):
        with patch.object(pipeline.llm, "ask_json") as model:
            result = pipeline.run(self.task)
        model.assert_not_called()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(self.mocks[3].call_count, 1)
        skipped = {s["step"] for s in result["trace"] if s["status"] == "skip"}
        self.assertTrue({"recommend", "repair", "lookup", "rejudge"}.issubset(skipped))
        self.assertEqual(result["verification"]["article_version"], 1)
        self.assertEqual(result["scene_judgement"]["hard_constraints"], [])
        self.assertFalse(any("价格" in item for item in result["verification"]["pending_confirm"]))

    def test_scene_judgement_exposes_orchestration_sources_and_weights(self):
        # 作品页“选型与 Agent 编排”直接读取这些字段，缺失会让公开示例退回默认 40/60。
        result = pipeline.run(self.task)
        sj = result["scene_judgement"]
        self.assertEqual(set(sj["weight_mix"]), {"structured", "unstructured"})
        self.assertAlmostEqual(sum(sj["weight_mix"].values()), 1, places=2)
        self.assertTrue(sj["top_dims"])
        self.assertTrue(all(isinstance(d, str) for d in sj["top_dims"]))
        if sj["weights"]:
            self.assertLessEqual(set(sj["weights"]), set(sj["prior_weights"]))

    def test_only_optional_style_notes_pass_without_revision_or_manual_question(self):
        self.mocks[5].return_value = review([{"where": "lead", "type": "expression", "detail": "可以再轻松些"}])
        result = pipeline.run(self.task)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["verification"]["state"], "passed")
        self.assertEqual(result["verification"]["triage"]["human"], 0)
        self.assertEqual(result["verification"]["triage"]["optional"], 1)
        self.assertEqual(self.mocks[3].call_count, 1)

    def test_cross_review_clears_only_the_semantic_false_alarm_not_rule_failure(self):
        p = {"where": "title", "type": "unsupported", "detail": "标题重量无依据"}
        self.mocks[5].return_value = review([p])
        self.mocks[7].side_effect = lambda r, *a: {"overall": "pass", "problems": [], "original_problems": [p],
            "cross_review": {"status": "completed", "dismissed": [p]}}
        self.mocks[4].return_value = {**self.det, "issues": [{"where": "title", "index": -1, "kind": "model", "detail": "型号错写"}]}
        result = pipeline.run(self.task)
        self.assertEqual(result["status"], "ok_with_flags")
        self.assertEqual(result["verification"]["triage"]["human"], 0)
        self.assertEqual(result["verification"]["triage"]["automatic"], 1)
        self.assertEqual(result["verification"]["triage"]["dismissed"], 1)

    def test_cross_review_budget_retains_first_review_issues_instead_of_losing_them(self):
        p = {"where": "title", "type": "unsupported", "detail": "重量尚无依据"}
        self.mocks[5].return_value = review([p])
        self.mocks[7].side_effect = llm.BudgetExceeded("cross budget")
        result = pipeline.run(self.task, enable_revision=False)
        self.assertTrue(result["budget"]["exhausted"])
        self.assertEqual(result["verification"]["judge"]["problems"], [p])
        self.assertEqual(result["status"], "ok_with_flags")

    def test_automatic_followup_repairs_actual_source_and_rechecks_new_version(self):
        from src.mvp import review as decisions
        source = pipeline.run(self.task)
        p = {"where": "title", "index": -1, "type": "model", "detail": "型号错写", "cross_check": "confirmed"}
        source["verification"]["judge"] = review([p])
        source["verification"]["state"] = "needs_review"
        source["verification"]["remaining"] = ["型号错写"]
        form = decisions.questions(source)
        self.assertEqual(form["questions"], [])
        decision = decisions.validate_decision(source, {"token": form["token"], "answers": [], "resolution": "continue"})
        after = {**self.article, "title": "携电脑去图书馆"}
        self.mocks[3].return_value = after
        out = pipeline.continue_review(source, decision)
        self.assertEqual(out["article"]["title"], after["title"])
        self.assertEqual(out["verification"]["article_version"], 2)
        self.assertEqual(out["status"], "ok")
        self.assertNotIn("human_review", out)
        self.assertIn("型号错写", " ".join(self.mocks[3].call_args.kwargs["issues"]))

    def test_followup_cannot_erase_existing_critical_requirements_when_prose_passes(self):
        self.plan["critical_gaps"] = ["指定软件版本兼容性未验证"]
        source = pipeline.run(self.task)
        decision = {"answers": [{"choice": "recheck", "where": "article", "index": -1, "detail": "重查", "quote": "", "direction": "", "reason": ""}]}
        out = pipeline.continue_review(source, decision)
        self.assertEqual(out["status"], "ok_with_flags")
        self.assertTrue(any("指定软件版本" in p for p in out["verification"]["remaining"]))

    def test_first_clarification_round_can_still_block(self):
        self.mocks[1].return_value = {**scene(), "need_info": {"blocking": True, "questions": ["请提供需要运行的软件名称和版本。"]}}
        result = pipeline.run({**self.task, "clarify_round": 0})
        self.assertEqual(result["status"], "need_info")
        self.assertEqual(result["questions"], ["请提供需要运行的软件名称和版本。"])

    def test_exhausted_clarification_proceeds_and_keeps_questions_as_pending(self):
        question = "请提供需要运行的软件名称和版本。"
        self.mocks[1].return_value = {**scene(), "need_info": {"blocking": True, "questions": [question]}}
        result = pipeline.run({**self.task, "clarify_round": 2})
        self.assertEqual(result["status"], "ok_with_flags")
        self.assertFalse(result["artifacts"]["brief"]["need_info"]["blocking"])
        self.assertIn(question, result["artifacts"]["brief"]["need_info"]["questions"])
        self.assertIn(question, result["verification"]["pending_confirm"])
        self.assertEqual(result["task"]["clarify_round"], 2)

    def test_second_round_can_ask_one_focused_question(self):
        self.mocks[1].return_value = {**scene(), "need_info": {"blocking": True, "questions": [
            {"id": "software", "field": "software", "question": "主要用哪些软件？",
             "options": ["Python 编程", "CAD 建模", "还没确定"]},
            {"question": "预算多少？", "field": "budget", "options": ["5000 元以内", "8000 元以上"]}]}}
        result = pipeline.run({**self.task, "clarify_round": 1})
        self.assertEqual(result["status"], "need_info")
        self.assertEqual(result["questions"], ["主要用哪些软件？"])
        self.assertEqual(result["question_specs"][0]["options"], ["Python 编程", "CAD 建模", "还没确定"])
        self.assertEqual(result["clarification"]["round"], 2)

    def test_repeated_scene_question_does_not_interrupt_specified_model_again(self):
        question = {"id": "software_use", "field": "software", "question": "主要用什么软件？"}
        self.mocks[1].return_value = {**scene(), "need_info": {"blocking": True, "questions": [question]}}
        result = pipeline.run({**self.task, "clarify_round": 1, "clarify_answers": [{**question, "answer": "还没确定"}]})
        self.assertEqual(result["status"], "ok_with_flags")
        self.assertIn("article", result)

    def test_unresolved_recommendation_does_not_open_third_round_or_force_model(self):
        with patch.object(pipeline, "decide_model", return_value={"status": "need_info", "questions": ["必须使用 Windows 吗？"],
                "candidates": ["测试电脑"]}):
            result = pipeline.run({**self.task, "product": "", "clarify_round": 2})
        self.assertEqual(result["status"], "input_required")
        self.assertEqual(result["question_specs"], [])
        self.mocks[3].assert_not_called()

    def test_model_ambiguity_uses_the_same_round_limit(self):
        self.kb.resolve.return_value = ("ambiguous", ["a", "b"])
        self.kb.info.side_effect = lambda mid: SimpleNamespace(name=mid)
        result = pipeline.run({**self.task, "clarify_round": 2})
        self.assertEqual(result["status"], "input_required")
        self.assertTrue(result["clarification"]["exhausted"])

    def test_semantic_feedback_drives_one_revision_and_reviews_displayed_final(self):
        issue = {"where": "lead", "index": -1, "type": "requirement", "quote": "课本已经够重", "detail": "未满足用户明确场景", "direction": "落到查资料"}
        self.mocks[5].side_effect = [review([issue]), review()]
        after = {**self.article, "lead": "去图书馆，把要看的资料带齐。"}
        self.mocks[3].side_effect = [self.article, after]
        result = pipeline.run(self.task)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(self.mocks[3].call_count, 2)
        self.assertIn("落到查资料", " ".join(self.mocks[3].call_args.kwargs["issues"]))
        self.assertEqual(self.mocks[5].call_args.args[0], result["article"])
        self.assertEqual(result["artifacts"]["draft:2"], result["article"])
        self.assertEqual(result["verification"]["article_version"], 2)
        self.assertEqual(result["revisions"][0]["before"], self.article["lead"])

    def test_evidence_lookup_without_result_instructs_deletion(self):
        issue = {"where": "body", "index": 0, "type": "unsupported", "quote": "全天续航", "detail": "缺续航实测"}
        self.mocks[5].side_effect = [review([issue]), review()]
        with patch.object(pipeline, "supplement_evidence", return_value={"facts": self.facts, "added": [], "reason": "未找到依据，删除承诺"}) as lookup:
            result = pipeline.run(self.task)
        self.assertEqual(lookup.call_count, 1)
        self.assertEqual(lookup.call_args.args[1].id, "test")
        self.assertIn("删除", " ".join(self.mocks[3].call_args.kwargs["issues"]))
        self.assertEqual(result["artifacts"]["lookup"]["added"], [])

    def test_failed_re_review_stays_flagged_without_second_revision_or_silent_deletion(self):
        issue = {"where": "body", "index": 0, "type": "overclaim", "detail": "缺少配置条件"}
        self.mocks[5].side_effect = [review([issue]), review([issue])]
        result = pipeline.run(self.task)
        self.assertEqual(self.mocks[3].call_count, 2)
        self.assertEqual(self.mocks[5].call_count, 2)
        self.assertEqual(result["status"], "ok_with_flags")
        self.assertEqual(result["verification"]["state"], "needs_review")
        self.assertEqual(result["artifacts"]["final"]["article"], result["article"])
        self.assertEqual(len(result["article"]["blocks"]), 1)

    def test_re_review_budget_cannot_reuse_original_review(self):
        issue = {"where": "lead", "index": -1, "type": "requirement", "detail": "未满足用户明确场景"}
        self.mocks[5].side_effect = [review([issue]), llm.BudgetExceeded("budget")]
        result = pipeline.run(self.task)
        self.assertEqual(result["verification"]["judge"]["overall"], "not_reviewed")
        self.assertEqual(result["status"], "ok_with_flags")
        self.assertEqual(result["verification"]["article_version"], 2)
        self.assertIn("budget_exhausted", [e["type"] for e in result["events"]])

    def test_budget_before_draft_has_no_fake_article(self):
        self.mocks[3].side_effect = llm.BudgetExceeded("budget")
        result = pipeline.run(self.task)
        self.assertEqual(result["status"], "budget_exceeded")
        self.assertNotIn("article", result)

    def test_unresponsive_provider_is_bounded_and_late_completion_cannot_change_result(self):
        release = threading.Event()
        def blocked(*a, **kw):
            release.wait(2)
            return self.article
        self.mocks[3].side_effect = blocked
        try:
            with patch.object(pipeline.settings, "GENERATION_BUDGET_SECONDS", .08):
                result = pipeline.run(self.task)
            frozen = copy.deepcopy(result)
            self.assertEqual(result["status"], "budget_exceeded")
            self.assertTrue(result["budget"]["exhausted"])
            self.assertLess(result["total_ms"], 500)
            release.set()
            self.assertEqual(result, frozen)
        finally:
            release.set()

    def test_parallel_review_and_check_and_monotonic_persistent_events(self):
        barrier = threading.Barrier(2)
        self.mocks[4].side_effect = lambda *a: (barrier.wait(2), copy.deepcopy(self.det))[1]
        self.mocks[5].side_effect = lambda *a: (barrier.wait(2), review())[1]
        snapshots = []
        result = pipeline.run(self.task, on_update=snapshots.append)
        self.assertEqual(result["status"], "ok")
        seqs = [e["seq"] for e in result["events"]]
        self.assertEqual(seqs, list(range(1, len(seqs) + 1)))
        lengths = [len(s["events"]) for s in snapshots]
        self.assertEqual(lengths, sorted(lengths))
        self.assertTrue(any(sum(s["status"] == "running" for s in snap["steps"]) >= 2 for snap in snapshots))
        self.assertIn("final", snapshots[-1]["artifacts"])

    def test_completed_rules_are_published_while_independent_review_is_waiting(self):
        rules_ready = threading.Event()
        snapshots = []
        def on_update(snapshot):
            snapshots.append(snapshot)
            if "rules:1" in snapshot["artifacts"]:
                rules_ready.set()
        def waiting_review(*a, **kw):
            self.assertTrue(rules_ready.wait(2), "规则检查不能被模型评审阻塞")
            return review()
        self.mocks[5].side_effect = waiting_review
        result = pipeline.run(self.task, on_update=on_update)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(any("rules:1" in s["artifacts"] and "review:1" not in s["artifacts"] for s in snapshots))

    def test_review_budget_retains_completed_rules_and_does_not_claim_pass(self):
        def waiting_review(*a, **kw):
            raise llm.BudgetExceeded("review timed out")
        self.mocks[5].side_effect = waiting_review
        result = pipeline.run(self.task)
        self.assertIn("rules:1", result["artifacts"])
        self.assertNotIn("review:1", result["artifacts"])
        self.assertEqual(result["verification"]["judge"]["overall"], "not_reviewed")
        self.assertEqual(result["status"], "ok_with_flags")

    def test_critical_requirement_gap_cannot_pass(self):
        self.plan["critical_gaps"] = ["专业软件兼容性未确认"]
        result = pipeline.run(self.task)
        self.assertEqual(result["status"], "ok_with_flags")
        self.assertIn("关键需求", " ".join(result["verification"]["remaining"]))


class EvidenceTests(unittest.TestCase):
    def test_editorial_claim_cannot_supply_a_resolution_missing_from_original_evidence(self):
        doc = ModelDoc("m", "型号", "", Path("."))
        facts = [{"id": "F1", "text": "分辨率 3120 × 2080，刷新率 120 Hz", "claim": "3.1K 屏幕"}]
        article = dict(title="", lead="", cta="", tags=["#屏幕"], blocks=[
            {"type": "text", "text": "3.1K 屏幕，最高 120 Hz。", "fact_refs": ["F1"]}])
        strategy = {"platform": "xiaohongshu", "price_policy": "forbid"}
        check = pipeline.deterministic_check(article, facts, doc, strategy, [])
        self.assertEqual([i["detail"] for i in check["issues"]], ["数字 3.1 不在所引用事实中"])
        article["blocks"][0]["text"] = "分辨率 3120 × 2080，最高 120 Hz。"
        self.assertEqual(pipeline.deterministic_check(article, facts, doc, strategy, [])["issues"], [])

    def test_scene_cache_marker_does_not_invalidate_the_content_plan(self):
        doc = ModelDoc("cache-test", "型号", "", Path("."))
        profile = {**scene(), "cache_hit": False}
        strategy = {"price_snippets": []}
        pipeline._CACHE.clear()
        self.addCleanup(pipeline._CACHE.clear)
        with patch.object(pipeline, "plan_content", return_value={"facts": []}) as plan:
            _, first = pipeline.plan_content_cached(doc, profile, strategy, {})
            _, second = pipeline.plan_content_cached(doc, {**profile, "cache_hit": True}, strategy, {})
        self.assertFalse(first)
        self.assertTrue(second)
        self.assertEqual(plan.call_count, 1)

    def test_request_is_counted_even_when_no_response_arrives_before_budget(self):
        calls = []
        def no_response(*args, **kwargs):
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["status"], "running")
            raise llm.BudgetExceeded("budget")
        with patch.object(llm.httpx, "post", side_effect=no_response):
            with llm.budget(time.monotonic()+1, calls.append):
                with self.assertRaises(llm.BudgetExceeded):
                    llm.chat([], retries=0)
        self.assertEqual(len(calls), 1)
    def test_full_original_and_conditions_do_not_consume_two_claim_slots(self):
        doc = ModelDoc("m", "型号", "", Path("."), snippets=[
            Snippet("S1", "spec", "重量", "原文" * 200 + "仅限配置A", "f.md"),
            Snippet("S2", "spec", "接口", "USB-A", "f.md"),
            Snippet("S3", "limit", "条件", "仅支持设备A", "f.md")])
        selected = {"selected": [{"sid": "S1", "condition_sids": ["S3"]}, {"sid": "S2"}, {"sid": "S3"}],
                    "angles": [{"id": "A", "sids": ["S1"]}, {"id": "B", "sids": ["S2"]}], "selected_angle": "A"}
        with patch.object(pipeline.llm, "ask_json", return_value=selected) as call:
            plan = pipeline.plan_content(doc, scene(), {"price_snippets": [], "platform_name": "小红书", "max_facts": 2, "price_policy": "forbid"}, {})
        self.assertIn("仅限配置A", call.call_args.args[1])
        self.assertEqual(len(plan["facts"]), 2)
        self.assertEqual(plan["facts"][0]["conditions"][0]["text"], "仅支持设备A")
        self.assertEqual(len(plan["risks"]), 1)

    def test_cache_versions_follow_evidence_content(self):
        doc = ModelDoc("m", "型号", "", Path("."), snippets=[Snippet("S1", "spec", "x", "旧资料", "f")])
        old = pipeline.context_version(doc)
        doc.snippets[0].text = "新资料"
        self.assertNotEqual(old, pipeline.context_version(doc))

    def test_judge_gets_original_request_without_author_defense_and_limits_expression_notes(self):
        article = dict(title="任务", lead="场景", cta="咨询", tags=[], blocks=[])
        strategy = dict(platform_name="朋友圈", price_policy="forbid", tone="自然", structure=[], chars=[40, 90], writing_limits={})
        out = {"overall": "needs_fix", "must_fix": [], "improvements": [{"detail": str(i)} for i in range(4)]}
        with patch.object(pipeline.llm, "ask_json", return_value=out) as model:
            result = pipeline.judge(article, [], strategy, {"issues": [{"author_defense": "辩护"}]}, task={"extra": "原始要求"},
                                    risks=[{"text": "仅配置 A 支持"}])
        payload = json.loads(model.call_args.args[1])
        self.assertEqual(payload["原始需求"]["extra"], "原始要求")
        self.assertNotIn("辩护", model.call_args.args[1])
        self.assertEqual(payload["相关风险与待确认原文"][0]["text"], "仅配置 A 支持")
        self.assertEqual(len(result["improvements"]), 2)
        self.assertEqual(result["overall"], "incomplete")

    def test_trace_closed_snapshot_cannot_accept_late_artifacts(self):
        trace = Trace()
        trace.publish("draft", {"v": 1}, "editor", "初稿")
        snap = trace.snapshot()
        trace.closed = True
        trace.publish("draft", {"v": 2}, "editor", "晚到数据")
        self.assertEqual(trace.snapshot(), snap)

    def test_review_field_location_is_normalized_by_unambiguous_block_index(self):
        article = dict(title="", lead="", cta="", tags=[], blocks=[{"type": "image", "image_id": "I1", "caption": "外观"}])
        strategy = dict(platform_name="朋友圈", price_policy="forbid", tone="自然", structure=[], chars=[40,90], writing_limits={})
        with patch.object(pipeline.llm, "ask_json", return_value={"overall":"pass", "must_fix":[], "claims":[{"where":"body", "index":0,"verdict":"no_fact_claim"}]}):
            result = pipeline.judge(article, [], strategy, {})
        self.assertEqual(result["overall"], "pass")
        self.assertEqual(result["claims"][0]["where"], "caption")

    def test_code_rejects_reviewers_false_length_alarm(self):
        article = dict(title="正好四个字", lead="", cta="", tags=[], blocks=[])
        strategy = dict(platform_name="朋友圈", price_policy="forbid", tone="自然", structure=[], chars=[40,90], writing_limits={"title":5})
        out = {"overall":"needs_fix", "must_fix":[{"where":"title","index":-1,"type":"platform","detail":"标题字符超过上限"}],
               "claims":[{"where":"title","index":-1,"verdict":"no_fact_claim"}]}
        with patch.object(pipeline.llm, "ask_json", return_value=out):
            result = pipeline.judge(article, [], strategy, {})
        self.assertEqual(result["overall"], "pass")
        self.assertEqual(result["problems"], [])
        self.assertEqual(len(result["dismissed_counting_notes"]), 1)

    def test_unsupported_claim_cannot_pass_with_an_empty_problem_list(self):
        article = dict(title="全天续航", lead="", cta="", tags=[], blocks=[])
        strategy = dict(platform_name="朋友圈", price_policy="forbid", tone="自然", structure=[], chars=[40,90], writing_limits={})
        with patch.object(pipeline.llm, "ask_json", return_value={"overall":"pass", "must_fix":[], "claims":[{"where":"title","index":-1,"verdict":"unsupported"}]}):
            result = pipeline.judge(article, [], strategy, {})
        self.assertEqual(result["overall"], "needs_fix")
        self.assertEqual(result["problems"][0]["type"], "unsupported")


if __name__ == "__main__":
    unittest.main()
