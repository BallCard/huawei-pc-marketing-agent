"""报价按任务与证据决定；放开平台默认值后仍须逐句核对价格来源。"""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.mvp import pipeline
from src.mvp.kb import LocalKB, ModelDoc, Snippet


class PricePolicyTests(unittest.TestCase):
    def setUp(self):
        self.price = Snippet("P1", "price", "官方报价", "16GB+512GB：官方商城页面价 6999 元（核验日期 2026-10-17）", "prices.csv")
        self.kb = Mock()
        self.kb.prices.return_value = [self.price]

    def test_all_platforms_allow_available_price_evidence_without_inventing_a_constraint(self):
        for platform in pipeline.PLATFORMS:
            with self.subTest(platform=platform):
                task = {"platform": platform, "constraints": []}
                original = copy.deepcopy(task)
                strategy = pipeline.plan_strategy(task, {"top_dims": []}, self.kb, "model")
                self.assertEqual(strategy["price_policy"], "conditional")
                self.assertEqual(strategy["price_snippets"], [self.price])
                self.assertEqual(task, original)

    def test_missing_platform_price_setting_uses_evidence_instead_of_forbidding_prices(self):
        self.assertEqual(pipeline.price_policy({}, {}, self.kb, "model"), ("conditional", [self.price]))

    def test_explicit_prohibition_in_constraints_description_or_revision_takes_priority(self):
        cases = [({"constraints": [text]}, None) for text in ("不提价格", "不要提价格", "别报价", "不写金额", "禁止出现价格")]
        cases += [({"extra": "写开学季内容，不要提价格。"}, None), ({}, "这次不提价格，只讲便携。")]
        for task, instruction in cases:
            with self.subTest(task=task, instruction=instruction):
                self.kb.reset_mock()
                self.assertEqual(pipeline.price_policy(task, {}, self.kb, "model", instruction), ("forbid", []))
                self.kb.prices.assert_not_called()

    def test_budget_and_requirement_for_truthful_prices_are_not_price_prohibitions(self):
        for text in ("预算不超过7000元", "请注明对应配置和官方报价", "不要虚构价格", "不按价格排序", "不强调价格"):
            with self.subTest(text=text):
                self.assertEqual(pipeline.price_policy({"extra": text}, {}, self.kb, "model"), ("conditional", [self.price]))

    def test_no_snapshot_remains_an_evidence_gap_instead_of_a_user_constraint(self):
        self.kb.prices.return_value = []
        task = {"constraints": []}
        self.assertEqual(pipeline.price_policy(task, {}, self.kb, "model"), ("none_in_kb", []))
        self.assertEqual(task["constraints"], [])


class PriceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.doc = ModelDoc("test", "测试电脑", "", Path("."))
        self.facts = [
            {"id": "F1", "kind": "price", "text": "16GB+512GB：官方商城页面价 6999 元（核验日期 2026-10-17；仅配置 A）"},
            {"id": "F2", "kind": "spec", "text": "刷新率 120 Hz"},
            {"id": "F3", "kind": "price", "text": "另一配置：官方商城页面价 5999 元（核验日期 2026-10-17）"},
        ]

    def check(self, text, refs, policy="conditional"):
        article = dict(title="", lead="", cta="", tags=[], blocks=[{"type": "text", "text": text, "fact_refs": refs}])
        return pipeline.deterministic_check(article, self.facts, self.doc,
                                            {"platform": "poster", "price_policy": policy}, [])["issues"]

    def test_referenced_price_accepts_currency_symbols_thousands_and_decimal_notation(self):
        for quote in ("6999 元", "6,999元", "￥6999", "¥6,999.00", "6,999.00 元"):
            with self.subTest(quote=quote):
                self.assertEqual(self.check(f"配置 A 16GB+512GB 官方商城页面价 {quote}（2026-10-17 核验）", ["F1"]), [])

    def test_decimal_prices_must_match_exactly(self):
        self.facts[0]["text"] = "配置 A：官方商城页面价 6999.50 元（2026-10-17 核验）"
        self.assertEqual(self.check("￥6,999.50", ["F1"]), [])
        self.assertTrue(any(i["kind"] == "price" for i in self.check("￥6,999.51", ["F1"])))

    def test_equal_number_in_a_product_specification_is_not_price_evidence(self):
        issues = self.check("售价 120 元", ["F2"])
        self.assertFalse(any(i["kind"] == "number" for i in issues))
        self.assertTrue(any(i["kind"] == "price" for i in issues))

    def test_available_but_unreferenced_quote_cannot_supply_the_price(self):
        for text, refs in (("￥5999", ["F1"]), ("￥6999", [])):
            with self.subTest(text=text, refs=refs):
                self.assertTrue(any(i["kind"] == "price" for i in self.check(text, refs)))

    def test_explicit_prohibition_and_missing_snapshot_both_block_quotes(self):
        for policy in ("forbid", "none_in_kb"):
            with self.subTest(policy=policy):
                self.assertTrue(any(i["kind"] == "price" for i in self.check("6999 元", ["F1"], policy)))

    def test_no_quote_is_accepted_without_price_evidence(self):
        self.assertEqual(self.check("欢迎私信了解价格。", [], "none_in_kb"), [])


class ValueRecommendationTests(unittest.TestCase):
    def test_recommendation_card_preserves_snapshot_conditions_for_budget_comparison(self):
        kb = LocalKB.__new__(LocalKB)
        kb._matrix = Mock(return_value={})
        kb.load = Mock(return_value=ModelDoc("test", "测试电脑", "", Path(".")))
        text = "配置 A：官网参考起价 6999 元（2026-10-17 核验；不含配件）"
        kb.prices = Mock(return_value=[Snippet("P1", "price", "价格", text, "prices.csv")])
        self.assertEqual(kb.matrix_card("test")["官方价格快照"], [{"text": text, "source": "prices.csv"}])

    def test_unconfirmed_hard_requirement_can_ask_a_specific_question_instead_of_forcing_a_model(self):
        kb = Mock()
        kb.models.return_value = [ModelDoc("test", "测试电脑", "", Path("."))]
        kb.matrix_card.return_value = {"model_id": "test", "官方价格快照": []}
        kb.resolve.return_value = ("none", [])
        question = "预算上限对应哪一个配置？目前缺少该配置报价。"
        with patch.object(pipeline.llm, "ask_json", return_value={"primary": None, "questions": [question]}) as call:
            result = pipeline.decide_model({}, {"hard_constraints": ["预算最多7000元"]}, kb)
        self.assertEqual(result["status"], "need_info")
        self.assertEqual(result["questions"], [question])
        self.assertEqual(json.loads(call.call_args.args[1])["候选型号"][0]["官方价格快照"], [])


if __name__ == "__main__":
    unittest.main()
