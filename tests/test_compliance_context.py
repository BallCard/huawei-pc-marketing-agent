import unittest

from src.mvp.verify import check_numbers, scan_compliance


class ComplianceContextTests(unittest.TestCase):
    def test_ordinal_and_ordinary_advice_are_not_ranking_or_competitor_claims(self):
        for text in ("第一次给孩子选电脑，先看课程要求。", "开学第一课，先把资料准备好。", "与其堆配置，不如先看常用软件。"):
            self.assertEqual(scan_compliance(text), [], text)

    def test_unsupported_ranking_and_competitor_attack_are_still_flagged(self):
        for text in ("销量第一", "性能第一", "全球第一", "第一名", "竞品太落后"):
            self.assertTrue(scan_compliance(text), text)

    def test_future_verification_invitation_is_not_fabricated_experience(self):
        for text in ("欢迎带上外设到店实测。", "建议到门店实际实测兼容性。", "带上自己的软件清单来门店实测。", "先去线下门店掂掂重量，实测你的专业软件吧！"):
            self.assertFalse(any(h["rule"] == "虚构体验评价" for h in scan_compliance(text)), text)

    def test_past_and_personal_test_claims_still_require_evidence(self):
        for text in ("我到店实测了一个月。", "到店实测发现所有软件都兼容。", "实测续航全天。", "亲测完全不卡顿。"):
            self.assertTrue(any(h["rule"] == "虚构体验评价" for h in scan_compliance(text)), text)

    def test_trailing_integer_zeroes_are_not_dropped_when_matching_facts(self):
        self.assertEqual(check_numbers("重量 1000 g", {"1"}), ["1000"])
        self.assertEqual(check_numbers("厚度 130 mm", {"13"}), ["130"])
        self.assertEqual(check_numbers("约 1.30 kg", {"1.3"}), [])


if __name__ == "__main__":
    unittest.main()
