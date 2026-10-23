"""门店／私域营销模式候选库：默认不改变生成，审核后才进入 approved_templates。"""
import hashlib
import json
import unittest
from unittest.mock import patch

import yaml
from pydantic import ValidationError

from src.mvp import app as service, marketing_templates as mt, settings


def task(**overrides):
    base = dict(prompt_variant='differentiated', platform='moments', marketing_template='auto',
                creative_context={'confirmed_items': [], 'history': [], 'methods': []})
    base.update(overrides)
    return base


def store_yaml():
    return yaml.safe_load((settings.PKG / 'config' / 'store_private_templates.yaml').read_text(encoding='utf-8'))


def approved_library(ids):
    data = store_yaml()
    data['review'] = {**data['review'], 'approved': list(ids)}
    data['templates'] = [t for t in data['templates'] if t['id'] in ids]
    return data


class StorePatternTests(unittest.TestCase):
    def test_default_library_keeps_eleven_approved_templates(self):
        self.assertEqual(mt.store_library()['templates'], [])
        data = mt.library()
        self.assertEqual(len(data['templates']), 11)
        self.assertTrue(all(t['id'].startswith('C') for t in data['templates']))
        self.assertNotIn('store_review', data)

    def test_audit_file_and_yaml_stay_consistent(self):
        review_path = settings.ROOT / '门店私域案例审核.json'
        review = json.loads(review_path.read_text(encoding='utf-8-sig'))
        data = store_yaml()
        self.assertEqual(data['review']['sha256'], hashlib.sha256(review_path.read_bytes()).hexdigest())
        cases = {c['id']: c for c in review['cases']}
        self.assertEqual(set(cases), {t['id'] for t in data['templates']})
        approved_in_review = {c['id'] for c in review['cases'] if c['status'] == 'approved'}
        self.assertEqual(set(data['review']['approved']), approved_in_review)
        for t in data['templates']:
            self.assertEqual(t['reference_pattern'], cases[t['id']]['proposed_pattern'])

    def test_store_patterns_need_matching_touchpoint(self):
        with patch.object(mt, 'store_library', return_value=approved_library(['S03'])):
            eligible, unavailable = mt.candidates(task(touchpoints=[]))
            self.assertNotIn('S03', {t['id'] for t in eligible})
            reason = next(u['reason'] for u in unavailable if u['id'] == 'S03')
            self.assertEqual(reason, '本轮未选择该样板对应的私域触点')
            eligible, _ = mt.candidates(task(touchpoints=['朋友圈']))
            self.assertIn('S03', {t['id'] for t in eligible})

    def test_store_gated_patterns_need_confirmed_store_facts(self):
        with patch.object(mt, 'store_library', return_value=approved_library(['S05'])):
            eligible, unavailable = mt.candidates(task(touchpoints=['门店社群']))
            self.assertNotIn('S05', {t['id'] for t in eligible})
            reason = next(u['reason'] for u in unavailable if u['id'] == 'S05')
            self.assertEqual(reason, '需要有效的门店活动／服务资料，或使用明确标注的演示数据')
            confirmed = task(touchpoints=['门店社群'],
                             creative_context={'confirmed_items': [{'kind': 'activity'}], 'history': [], 'methods': []})
            eligible, _ = mt.candidates(confirmed)
            self.assertIn('S05', {t['id'] for t in eligible})

    def test_unapproved_store_pattern_cannot_be_requested(self):
        with self.assertRaisesRegex(ValueError, '样板 S01 暂不能使用'):
            mt.validate_task(mt.prepare_task(task(marketing_template='S01')))

    def test_bind_plan_selects_approved_store_pattern_and_fills_slots(self):
        with patch.object(mt, 'store_library', return_value=approved_library(['S01'])):
            prepared = mt.prepare_task(task(touchpoints=['企业微信私信']))
            out = {'template_id': 'S01', 'template_reason': '一对一承接适合企微开场',
                   'template_slots': [
                       {'slot': '当场可得的理由', 'text': '到店可现场试接口', 'refs': []},
                       {'slot': '加微信之后的下一步', 'text': '发一份适配清单', 'refs': []},
                       {'slot': '到店或咨询的入口', 'text': '本周六到店体验', 'refs': []}]}
            plan = mt.bind_plan(out, prepared, facts=[])
        self.assertEqual(plan['id'], 'S01')
        self.assertEqual(plan['selection_source'], '策划模型选择')
        self.assertEqual(len(plan['filled_slots']), 3)
        self.assertEqual(plan['filled_slots'][1]['text'], '发一份适配清单')

    def test_task_accepts_allowed_touchpoints_and_rejects_unknown(self):
        accepted = service.TaskIn(prompt_variant='differentiated', touchpoints=['企业微信私信', '门店社群'])
        self.assertEqual(accepted.touchpoints, ['企业微信私信', '门店社群'])
        with self.assertRaises(ValidationError):
            service.TaskIn(touchpoints=['抖音私信'])

    def test_disclosure_field_is_carried_into_labels(self):
        template = {'id': 'S04', 'disclosure': '活动信息以门店确认资料为准，非品牌官方活动'}
        self.assertIn('活动信息以门店确认资料为准，非品牌官方活动',
                      mt.disclosures({'demo_mode': False}, template))


if __name__ == '__main__':
    unittest.main()
