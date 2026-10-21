import json
import unittest
from unittest.mock import patch

from src.mvp import clarification, pipeline, settings


class ClarificationTests(unittest.TestCase):
    def test_screenshot_software_question_does_not_receive_computer_options(self):
        models = ["HUAWEI MateBook 14（鸿蒙版）", "HUAWEI MateBook Fold 非凡大师"]
        text = "用户所需的‘编程与设计类专业软件’具体名称及版本是什么？（用于确认对CPU架构、GPU类型、内存容量及操作系统的硬性要求）"
        result = clarification.form_result({"status": "need_info", "questions": [text], "candidates": models}, {})
        self.assertEqual(result["question_specs"][0]["field"], "software")
        self.assertEqual(result["question_specs"][0]["options"], [])
        self.assertEqual(result["candidates"], [])

    def test_bound_options_survive_and_wrong_options_are_removed(self):
        result = clarification.form_result({"status": "need_info", "questions": [
            {"question": "需要什么软件？", "field": "product", "options": ["Python 开发", "CAD 建模", "HUAWEI MateBook 14"]}]}, {})
        self.assertEqual(result["question_specs"][0]["options"], ["Python 开发", "CAD 建模"])
        self.assertEqual(result["question_specs"][0]["field"], "software")

    def test_answered_question_is_skipped(self):
        task = {"clarify_answers": [{"id": "budget", "question": "预算多少？", "answer": "5000 元以内"}]}
        specs = clarification.prepare_questions([
            {"id": "budget", "question": "预算大约多少？"}, {"question": "必须使用 Windows 吗？", "field": "system"}], task)
        self.assertEqual(specs[0]["field"], "system")
        self.assertEqual(len(specs), 1)

    def test_system_followup_about_software_retains_its_explicit_field(self):
        specs = clarification.prepare_questions([{"id": "runtime", "field": "system",
            "question": "这些软件需要在 Windows 本机直接运行吗？",
            "options": ["必须本机运行", "可以使用云电脑"]}], {})
        self.assertEqual(specs[0]["field"], "system")

    def test_same_dimension_can_narrow_to_a_new_question(self):
        specs = clarification.prepare_questions([{"id": "software_name", "field": "software", "question": "具体使用哪些设计软件？"}],
            {"clarify_answers": [{"id": "software_use", "question": "主要做什么？", "answer": "设计"}]})
        self.assertEqual(specs[0]["id"], "software_name")

    def test_product_options_allow_recommendation_instead_of_forcing_first_model(self):
        result = clarification.form_result({"status": "need_info", "question_field": "product",
            "questions": ["确认具体型号？"], "candidates": ["A", "B", "C", "D"]}, {"clarify_round": 1})
        self.assertEqual(result["question_specs"][0]["options"], ["A", "B", "C", "按需求帮我推荐"])
        self.assertEqual(result["clarification"]["round"], 2)

    def test_input_checks_also_stop_after_two_rounds(self):
        result = clarification.form_result(pipeline.check_task({}), {"clarify_round": 2})
        self.assertEqual(result["status"], "input_required")
        self.assertEqual(result["questions"], [])

    def test_scene_receives_answer_history_and_round_cache_is_separate(self):
        task = {"audience": "学生", "scenario": "上课", "platform": "moments", "clarify_round": 1,
                "clarify_answers": [{"id": "use", "field": "software", "question": "主要做什么？", "answer": "Python 开发"}]}
        with patch.object(pipeline.llm, "ask_json", return_value={}) as call:
            pipeline.parse_scene(task, None)
        payload = json.loads(call.call_args.args[1])
        self.assertEqual(payload["问询"]["已回答"], task["clarify_answers"])
        with patch.object(pipeline, "parse_scene", return_value={"need_info": {"blocking": False}}) as call:
            pipeline.parse_scene_cached({**task, "extra": "cache regression", "clarify_round": 0}, None)
            pipeline.parse_scene_cached({**task, "extra": "cache regression", "clarify_round": 1}, None)
        self.assertEqual(call.call_count, 2)

    def test_visual_route_is_independent_from_text_model(self):
        with patch.dict("os.environ", {"FAST_LLM_BASE_URL": "https://text.invalid/v1", "FAST_LLM_EXTRA_BODY": "{}"}), \
                patch.object(settings, "IMAGE_VERIFY_BASE_URL", "https://vision.invalid/v1"):
            self.assertEqual(settings.llm_config("image_verify")["base_url"], "https://vision.invalid/v1")
            self.assertEqual(settings.llm_config("fast")["base_url"], "https://text.invalid/v1")
