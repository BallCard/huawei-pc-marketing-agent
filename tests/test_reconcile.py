import copy
import json
import unittest
from unittest.mock import patch

from src.mvp import llm, reconcile, review


class CrossReviewTests(unittest.TestCase):
    def setUp(self):
        self.article = {"title": "配置 A 约 1.3 kg。", "lead": "配备 USB-A 接口。", "cta": "到店核对软件适配情况。",
                        "blocks": [], "fact_refs": {"title": ["F1"], "lead": ["F2"]}}
        self.facts = [{"id": "F1", "text": "配置 A 约 1.3 kg。"}, {"id": "F2", "text": "配备 USB-A 接口。"}]
        self.issue = {"where": "title", "index": -1, "type": "unsupported", "detail": "重量缺少依据"}

    def check(self, problems, decisions, **kwargs):
        with patch.object(llm, "chat", return_value=json.dumps({"decisions": decisions}, ensure_ascii=False)) as call:
            result = reconcile.cross_check({"overall": "needs_fix", "problems": problems, **kwargs},
                                           self.article, self.facts, {}, {})
        self.assertEqual(call.call_args.kwargs["role"], "judge")
        return result

    def decision(self, p=None, **overrides):
        return {"id": reconcile.issue_id(p or self.issue), "decision": "dismiss", "reason": "实际原句与引用完整原文完全一致",
                "verdict": "supported", "article_quote": self.article["title"],
                "evidence": [{"fact_id": "F1", "quote": self.facts[0]["text"]}], **overrides}

    def test_nine_opinions_leave_one_important_question_and_preserve_audit(self):
        optional = [{"type": "expression", "detail": f"个人语气偏好 {n}"} for n in range(4)]
        second = {"where": "lead", "index": -1, "type": "unsupported", "detail": "接口缺少依据"}
        unknown = [{"where": "body", "index": n, "type": "unsupported", "detail": f"软件版本条件未核实 {n}"} for n in range(3)]
        self.article["blocks"] = [{"type": "text", "text": f"软件适配 {n}", "fact_refs": ["F3"]} for n in range(3)]
        problems = optional + [self.issue, second] + unknown
        decisions = [self.decision(), self.decision(second, article_quote=self.article["lead"],
                      evidence=[{"fact_id": "F2", "quote": self.facts[1]["text"]}])]
        decisions += [{"id": reconcile.issue_id(p), "decision": "unresolved", "reason": "资料未确认指定软件版本",
                       "root_cause": "指定软件版本适配范围缺失"} for p in unknown]
        out = self.check(problems, decisions)
        form = review.questions({"article": self.article, "verification": {"judge": out}})
        self.assertEqual(len(out["original_problems"]), 9)
        self.assertEqual(form["summary"], {"human": 1, "automatic": 0, "optional": 4, "dismissed": 2, "merged": 2})
        self.assertEqual(form["questions"][0]["occurrences"], 3)
        result = {"article": self.article, "verification": {"judge": out}}
        decision = review.validate_decision(result, {"token": form["token"], "resolution": "continue",
            "answers": [{"id": form["questions"][0]["id"], "choice": "fix"}]})
        self.assertEqual(len(review.instructions(decision)), 3)

    def test_forged_unrelated_partial_and_missing_citations_cannot_clear_risk(self):
        for evidence in ([], [{"fact_id": "F9", "quote": self.facts[0]["text"]}],
                         [{"fact_id": "F1", "quote": "配置 B 约 1.0 kg。"}],
                         [{"fact_id": "F1", "quote": "1.3 kg"}],
                         [{"fact_id": "F2", "quote": self.facts[1]["text"]}]):
            with self.subTest(evidence=evidence):
                out = self.check([self.issue], [self.decision(evidence=evidence)])
                self.assertEqual(out["problems"][0]["cross_check"], "unresolved")

    def test_actual_missing_qualifier_cannot_be_dismissed_with_a_valid_but_irrelevant_fact(self):
        self.article["title"] = "约 1.3 kg。"
        self.facts[0]["conditions"] = ["仅配置 A"]
        out = self.check([self.issue], [self.decision(evidence=[{"fact_id": "F1", "quote": "配置 A 约 1.3 kg。仅配置 A"}])])
        self.assertEqual(len(out["problems"]), 1)

    def test_missing_duplicate_or_unknown_decision_retains_risk(self):
        for decisions in ([], [self.decision(id="unknown")], [self.decision(), self.decision()]):
            self.assertEqual(self.check([self.issue], decisions)["problems"][0]["cross_check"], "unresolved")

    def test_failed_cross_review_preserves_important_risk_and_budget_propagates(self):
        for error in (llm.LLMError("timeout"), ValueError("invalid JSON")):
            with patch.object(llm, "chat", side_effect=error):
                out = reconcile.cross_check({"overall": "needs_fix", "problems": [self.issue]}, self.article, self.facts, {}, {})
            self.assertEqual(out["problems"], [self.issue])
            self.assertEqual(out["cross_review"]["status"], "incomplete")
        with patch.object(llm, "chat", side_effect=llm.BudgetExceeded("budget")):
            with self.assertRaises(llm.BudgetExceeded):
                reconcile.cross_check({"overall": "needs_fix", "problems": [self.issue]}, self.article, self.facts, {}, {})

    def test_invitation_is_not_relabelled_as_a_supported_product_promise(self):
        p = {"where": "cta", "index": -1, "type": "unsupported", "detail": "软件兼容未验证"}
        out = self.check([p], [self.decision(p, verdict="no_fact_claim", evidence=[], article_quote=self.article["cta"])],
                         claims=[{"where": "cta", "index": -1, "verdict": "unsupported"}])
        self.assertEqual(out["overall"], "pass")
        self.assertEqual(out["claims"][0]["verdict"], "no_fact_claim")

    def test_confirmed_error_goes_to_automatic_repair_and_deterministic_rule_is_protected(self):
        out = self.check([self.issue], [self.decision(decision="confirm")])
        result = {"article": self.article, "verification": {"judge": out,
                  "rules": {"issues": [{"where": "title", "index": -1, "kind": "model", "detail": "型号错误"}]}}}
        form = review.questions(result)
        self.assertEqual(form["summary"]["human"], 0)
        self.assertEqual(form["summary"]["automatic"], 2)
        with self.assertRaises(ValueError):
            review.validate_decision(result, {"token": form["token"], "answers": [], "resolution": "adopt"})
        decision = review.validate_decision(result, {"token": form["token"], "answers": [], "resolution": "continue"})
        self.assertEqual(decision["mode"], "automatic")
        self.assertEqual(len(review.instructions(decision)), 2)

    def test_optional_only_does_not_block_or_require_another_model_call(self):
        with patch.object(llm, "chat") as call:
            out = reconcile.cross_check({"overall": "needs_fix", "problems": [{"type": "expression", "detail": "语气再轻松些"}]}, {}, [], {}, {})
        call.assert_not_called()
        self.assertEqual(out["overall"], "pass")
        self.assertEqual(review.questions({"verification": {"judge": out}})["questions"], [])

    def test_same_vague_root_cannot_merge_independent_price_and_compatibility_risks(self):
        problems = [{"where": "title", "type": "unsupported", "detail": "价格没有依据", "root_cause": "资料不足"},
                    {"where": "lead", "type": "unsupported", "detail": "软件兼容没有依据", "root_cause": "资料不足"}]
        self.article["fact_refs"]["lead"] = ["F1"]
        form = review.questions({"article": self.article, "verification": {"judge": {"overall": "needs_fix", "problems": problems}}})
        self.assertEqual(len(form["questions"]), 2)

    def test_incomplete_is_retry_not_a_request_for_human_to_approve_an_unreviewed_article(self):
        result = {"verification": {"judge": {"overall": "incomplete"}, "remaining": ["独立评审未通过或未完成，需要复核。"]}}
        form = review.questions(result)
        self.assertEqual(form["questions"], [])
        decision = review.validate_decision(result, {"token": form["token"], "answers": [], "resolution": "continue"})
        self.assertTrue(all(a["choice"] == "recheck" for a in decision["answers"]))

    def test_user_purchase_budget_is_an_important_unknown_not_a_request_to_retry_review(self):
        form = review.questions({"verification": {"judge": {"overall": "pass"}, "remaining": ["用户购机预算无法确认"]}})
        self.assertEqual(form["summary"]["human"], 1)
        self.assertEqual(form["summary"]["automatic"], 0)

    def test_deterministic_issue_cannot_be_dismissed_even_with_a_valid_fact(self):
        p = {**self.issue, "deterministic": True}
        out = self.check([p], [self.decision(p)])
        self.assertEqual(len(out["problems"]), 1)

    def test_expression_label_does_not_hide_lost_conditions_or_high_risk_claims(self):
        for p in ({"type": "expression", "detail": "未保留重量配置限定"},
                  {"type": "expression", "detail": "无依据承诺软件兼容"},
                  {"type": "expression", "severity": "high", "detail": "需要检查"}):
            out = reconcile.normalize({"overall": "needs_fix", "problems": [p]})
            self.assertEqual(out["problems"], [p])


if __name__ == "__main__":
    unittest.main()
