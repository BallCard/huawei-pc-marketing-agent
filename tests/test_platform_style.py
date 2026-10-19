"""平台成稿必须真的短，不能只靠前端截断。"""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from src.mvp.kb import Image
from src.mvp.pipeline import judge, platforms_cfg
from src.mvp.verify import check_platform, count_chars


class PlatformStyleTests(unittest.TestCase):
    def setUp(self):
        self.spec = copy.deepcopy(platforms_cfg()["xiaohongshu"])
        self.article = {
            "title": "去图书馆，轻一点出发",
            "lead": "课本已经够重，电脑就想轻一点。",
            "blocks": [
                {"type": "text", "text": "MateBook 14 鸿蒙版，圆键盘版约 1.33 kg，放进通勤包。"},
                {"type": "text", "text": "HDMI 和 USB-A 接口，课堂投影、拷课件都用得上。"},
                {"type": "text", "text": "专业软件和外设是否适配 HarmonyOS 6，选前记得核对。"},
                *[{"type": "image", "caption": "同型号整机外观"} for _ in range(3)],
            ],
            "cta": "带上常用软件清单，到店试试。",
            "tags": ["#开学季"],
        }

    def test_short_native_post_is_accepted(self):
        self.assertEqual(check_platform(self.article, self.spec), [])

    def test_body_upper_bound_has_no_thirty_percent_slack(self):
        article = copy.deepcopy(self.article)
        article["lead"] = ""
        article["cta"] = ""
        article["blocks"] = [{"type": "text", "text": "字" * 221}, *article["blocks"][3:]]
        self.assertTrue(any("超过小红书上限 220" in item for item in check_platform(article, self.spec)))

    def test_long_paragraph_is_rejected_inside_total_budget(self):
        article = copy.deepcopy(self.article)
        article["blocks"][0]["text"] = "字" * 56
        self.assertLess(count_chars(article), self.spec["chars"][1])
        self.assertTrue(any("正文 56 字" in item for item in check_platform(article, self.spec)))

    def test_title_caption_and_cta_have_their_own_limits(self):
        article = copy.deepcopy(self.article)
        article["title"] = "字" * 21
        article["cta"] = "字" * 31
        article["blocks"][3]["caption"] = "字" * 31
        messages = check_platform(article, self.spec)
        for label in ("标题 21 字", "行动引导 31 字", "图注 31 字"):
            self.assertTrue(any(label in item for item in messages), label)

    def test_whitespace_is_not_a_word_count_workaround(self):
        article = copy.deepcopy(self.article)
        original = count_chars(article)
        article["blocks"][0]["text"] += "\n\n   "
        self.assertEqual(count_chars(article), original)
        self.assertEqual(check_platform(article, self.spec), [])

    def test_reviewer_receives_tags_and_image_evidence_for_native_post(self):
        strategy = {
            "platform_name": self.spec["name"], "price_policy": "forbid",
            **{key: self.spec[key] for key in ("tone", "structure", "chars", "writing_limits")},
        }
        illustration = Image(id="diagram.png", model="测试型号", path=Path("diagram.png"),
                             caption="界面示意图", page="", url="", kind="screen_ui",
                             vision="屏幕界面与手写笔操作示意", shows_device=True)
        with patch("src.mvp.pipeline.llm.ask_json", return_value={"overall": "pass"}) as review:
            judge(self.article, [], strategy, {"issues": []}, images=[illustration])
        payload = json.loads(review.call_args.args[1])
        self.assertEqual(payload["软文"]["tags"], self.article["tags"])
        self.assertEqual(payload["配图资料"][0]["视觉描述"], illustration.vision)
        self.assertEqual(payload["配图资料"][0]["画面类型"], "screen_ui")


if __name__ == "__main__":
    unittest.main()
