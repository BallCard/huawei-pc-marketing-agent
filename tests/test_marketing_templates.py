"""审核名单、事实边界以及实际传入生成链路的样板信息。"""
import copy
import hashlib
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image as PILImage

from src.mvp import app as service, marketing_templates as mt, pipeline as p, poster, reconcile, settings
from src.mvp.editorial_context import EditorialStore
from src.mvp.kb import Image, ModelDoc
import test_editorial_workflow as workflow
import test_service as service_tests

REAL_COMPOSE = p.compose


def task(**overrides):
    return dict(prompt_variant='differentiated', platform='poster', marketing_template='auto',
                creative_context={'confirmed_items': [], 'history': [], 'methods': [{'id': 'old'}]}, **overrides)


class TemplateTests(unittest.TestCase):
    def test_library_exactly_preserves_user_decisions_notes_and_reference_patterns(self):
        review_path = settings.ROOT / 'PC营销案例审核.json'
        review = json.loads(review_path.read_text(encoding='utf-8-sig'))
        data = mt.library()
        approved = {r['id']: r for r in review['cases'] if r['status'] == 'approved'}
        self.assertEqual({t['id'] for t in data['templates']}, set(approved))
        self.assertEqual(len(data['templates']), 11)
        self.assertEqual(set(data['review']['rejected']), {'C03', 'C05', 'C06', 'C11', 'C12'})
        self.assertEqual(data['review']['sha256'], hashlib.sha256(review_path.read_bytes()).hexdigest())
        for t in data['templates']:
            self.assertEqual(t['user_note'], approved[t['id']]['note'])
            self.assertEqual(t['reference_pattern'], approved[t['id']]['proposed_pattern'])

    def test_candidates_require_platform_demo_subject_topic_and_store_data(self):
        ids = lambda t: {c['id'] for c in mt.candidates(t)[0]}
        plain = ids(task())
        self.assertTrue({'C01', 'C02', 'C07', 'C08', 'C13', 'C14'}.issubset(plain))
        self.assertTrue({'C04', 'C09', 'C10', 'C15', 'C16'}.isdisjoint(plain))
        demo = ids(task(demo_mode=True, concept_subject='原创纸飞机 IP'))
        self.assertTrue({'C04', 'C09', 'C10', 'C16'}.issubset(demo))
        self.assertNotIn('C02', ids({**task(), 'platform': 'moments'}))
        with patch.object(mt, 'topic_valid', return_value=True):
            self.assertIn('C15', ids(task()))
        confirmed = {**task(), 'creative_context': {'confirmed_items': [{'kind': 'service'}]}}
        self.assertIn('C16', ids(confirmed))

    def test_topic_dates_and_urls_are_checked_without_claiming_online_verification(self):
        topic = {'title': '校园读书日', 'source': 'https://example.com/event', 'checked_on': '2026-10-20'}
        self.assertTrue(mt.topic_valid(topic, date(2026, 10, 21)))
        for change in ({'checked_on': '2026-10-22'}, {'checked_on': '2026-10-13'}, {'source': 'https:fake'}, {'title': ''}):
            self.assertFalse(mt.topic_valid({**topic, **change}, date(2026, 10, 21)))

    def test_baseline_untouched_and_b_snapshot_stays_fixed_for_continuation(self):
        a = {**task(), 'prompt_variant': 'baseline'}
        original = copy.deepcopy(a)
        self.assertIs(mt.prepare_task(a), a)
        self.assertEqual(a, original)
        b = mt.prepare_task(task(demo_mode=True))
        self.assertEqual(b['creative_context']['methods'], [])
        self.assertNotIn('approved_templates', original['creative_context'])
        with patch.object(mt, 'library', side_effect=AssertionError('续审不重载')):
            self.assertEqual(mt.prepare_task(b), b)

    def test_requested_template_is_enforced_fallback_is_visible_and_bad_refs_drop(self):
        facts = [{'id': 'F1', 'sid': 'S1', 'text': '真实事实'}]
        chosen = mt.bind_plan({'template_id': 'C03', 'template_slots': 'bad'}, task(), facts)
        self.assertEqual(chosen['id'], 'C13')
        self.assertIn('规则回退', chosen['selection_source'])
        requested = {**task(), 'marketing_template': 'C01'}
        chosen = mt.bind_plan({'template_id': 'C13', 'template_slots': [
            {'slot': '真实细节', 'text': '产品细节', 'refs': ['S1', 'C99', {'fake': True}]}]}, requested, facts)
        self.assertEqual(chosen['id'], 'C01')
        self.assertEqual(chosen['filled_slots'][0]['refs'], ['S1'])
        with self.assertRaisesRegex(ValueError, '概念演示'):
            mt.validate_task({**task(), 'marketing_template': 'C04'})

    def test_demo_facts_are_separate_labels_survive_normalization_and_history_skips_demo(self):
        t = mt.prepare_task({**task(demo_mode=True), 'marketing_template': 'C16'})
        facts = [{'id': 'F1', 'sid': 'S1', 'text': '约 1.3 kg', 'kind': 'spec'}]
        selected = mt.bind_plan({}, t, facts)
        mt.bind_plan({}, t, facts)
        self.assertEqual([f['id'] for f in facts], ['F1', 'D1', 'D2'])
        self.assertEqual(facts[-1]['evidence_type'], 'fictional_demo')
        raw = {'title': '体验邀请', 'blocks': [], 'disclosures': ['模型试图删换的标识']}
        article = p.normalize_article(raw, facts, [], task=t, plan={'template': selected})
        self.assertEqual(article['disclosures'], mt.disclosures(t, selected))
        with tempfile.TemporaryDirectory() as folder:
            store = EditorialStore(Path(folder) / 'jobs.sqlite3')
            self.assertFalse(store.remember('demo', {'task': t, 'article': article}))
            self.assertEqual(store.history('default'), [])

    def test_real_invitation_must_actually_select_confirmed_service_evidence(self):
        t = {**task(), 'marketing_template': 'C16', 'creative_context': {'confirmed_items': [{'id': 'C1', 'kind': 'service'}]}}
        facts = [{'id': 'F1', 'sid': 'S1'}]
        with self.assertRaisesRegex(ValueError, '未选入'):
            mt.bind_plan({}, t, facts)
        facts.append({'id': 'C1', 'sid': 'C1', 'kind': 'store_context', 'source': {'material_kind': 'service'}})
        self.assertEqual(mt.bind_plan({}, t, facts)['id'], 'C16')

    def test_comic_checker_rejects_three_panels_even_if_text_is_short(self):
        spec = p.platforms_cfg()['poster']
        strategy = {**spec, 'platform': 'poster', 'price_policy': 'forbid'}
        article = dict(title='', lead='', cta='', tags=[], blocks=[{'type': 'text', 'text': '情景', 'fact_refs': []}] * 3)
        checks = p.deterministic_check(article, [], ModelDoc('test', '测试电脑', '', Path('.')), strategy, [], {'_template_plan': {'id': 'C07'}})
        self.assertTrue(any('恰好四个' in i for i in checks['platform_issues']))

    def test_comic_normalization_only_removes_duplicate_metadata_and_keeps_fact_conditions(self):
        t = {**task(), 'product': 'HUAWEI MateBook 14（鸿蒙版）', '_template_plan': {'id': 'C07'}}
        original = {'lead': '重复介绍分镜', 'blocks': [{'type': 'text', 'text': '第三格｜HUAWEI MateBook 14（鸿蒙版）圆键盘含电池约1.33kg；重量因配置、工艺、测量而异。', 'fact_refs': ['F1']}]}
        out = mt.normalize_structure(original, t, None, [])
        self.assertEqual(out['lead'], '')
        self.assertEqual(out['blocks'][0]['text'], '圆键盘含电池约1.33kg；重量因配置、工艺、测量而异。')
        self.assertEqual(out['blocks'][0]['fact_refs'], ['F1'])
        self.assertEqual(len(out['structure_adjustments']), 2)
        self.assertEqual(original['lead'], '重复介绍分镜')
        self.assertEqual(mt.normalize_structure(original, {**t, 'prompt_variant': 'baseline'}, None, []), original)
        duplicate = {'lead': '', 'blocks': [{'type': 'text', 'text': '四格漫画·情景演绎', 'fact_refs': []}, *original['blocks']]}
        out = mt.normalize_structure(duplicate, t, None, [])
        self.assertEqual(len(out['blocks']), 1)
        self.assertIn('disclosures', out['structure_adjustments'][0]['reason'])

    def test_demo_activity_time_cannot_support_same_number_product_parameter(self):
        doc = ModelDoc('test', '测试电脑', '', Path('.'))
        spec = p.platforms_cfg()['moments']
        strategy = {**spec, 'platform': 'moments', 'price_policy': 'forbid'}
        facts = [{'id': 'D2', 'sid': 'D2', 'text': '演示安排：周六14:00—17:00', 'kind': 'demo_context'}]
        article = dict(title='', lead='', cta='', tags=[], blocks=[{'type': 'text', 'text': '周六14:00—17:00', 'fact_refs': ['D2']}])
        checks = p.deterministic_check(article, facts, doc, strategy, [])
        self.assertFalse([i for i in checks['issues'] if i['kind'] == 'number'])
        article['blocks'][0]['text'] = '电脑内存14GB'
        checks = p.deterministic_check(article, facts, doc, strategy, [])
        self.assertTrue([i for i in checks['issues'] if i['kind'] == 'number'])

    def test_cross_review_only_accepts_exact_demo_setting_with_visible_labels(self):
        t = {**task(demo_mode=True), '_template_plan': {'id': 'C16'}}
        fact = {'id': 'D1', 'kind': 'demo_context', 'text': '春风体验点（虚构门店）'}
        article = {'blocks': [{'type': 'text', 'text': fact['text'], 'fact_refs': ['D1']}]}
        problem = {'where': 'body', 'index': 0}
        decision = {'reason': '仅演示', 'verdict': 'supported', 'article_quote': fact['text'],
                    'evidence': [{'fact_id': 'D1', 'quote': fact['text']}]}
        self.assertFalse(reconcile._supported_dismissal(decision, problem, article, [fact], t))
        article['disclosures'] = mt.disclosures(t, t['_template_plan'])
        self.assertTrue(reconcile._supported_dismissal(decision, problem, article, [fact], t))
        article['blocks'][0]['text'] += '，保证流畅'
        self.assertFalse(reconcile._supported_dismissal(decision, problem, article, [fact], t))


class TemplateWorkflowTests(unittest.TestCase):
    setUp = workflow.WorkflowTests.setUp

    def test_actual_planner_passes_candidates_and_writer_receives_selected_template(self):
        t = {**self.task, 'prompt_variant': 'differentiated', 'marketing_template': 'C13'}
        spec = p.platforms_cfg()['moments']
        strat = {**spec, 'platform': 'moments', 'platform_name': spec['name'], 'price_policy': 'forbid', 'price_snippets': []}
        raw = {'template_id': 'C03', 'template_reason': '用重量回答携带问题',
               'selected': [{'sid': 'S1'}], 'angles': [{'id': 'A'}, {'id': 'B'}], 'selected_angle': 'A'}
        with patch.object(p.llm, 'ask_json', return_value=raw) as model:
            plan = p.plan_content(self.doc, workflow.scene(), strat, t)
            payload = json.loads(model.call_args.args[1])
        self.assertTrue(payload['创作上下文']['approved_templates'])
        self.assertEqual(plan['template']['id'], 'C13')
        for previous in (None, self.article):
            with patch.object(p.llm, 'ask_json', return_value={}) as model:
                REAL_COMPOSE(t, workflow.scene(), strat, plan['facts'], [], None, previous=previous, plan=plan)
            payload = json.loads(model.call_args.args[1])
            self.assertEqual(payload['采用的已审核样板']['id'], 'C13')

    def test_continuation_keeps_selected_template_and_program_labels(self):
        t = {**self.task, 'prompt_variant': 'differentiated', 'demo_mode': True}
        self.plan['template'] = mt.bind_plan({'template_id': 'C08'}, t, self.facts)
        source = p.run(t)
        source['article'].pop('disclosures')
        decision = {'answers': [{'choice': 'fix', 'detail': '修句', 'where': 'body', 'index': 0, 'quote': '', 'direction': '', 'reason': ''}]}
        result = p.continue_review(source, decision)
        self.assertEqual(result['marketing_template']['id'], 'C08')
        self.assertTrue(result['article']['disclosures'])
        self.assertEqual(self.mocks[3].call_args.kwargs['plan']['template']['id'], 'C08')


class TemplateAPITests(unittest.TestCase):
    setUp = service_tests.ServiceTests.setUp
    login = service_tests.ServiceTests.login

    def test_invalid_selection_returns_422_without_starting_worker_or_leaking_slot(self):
        self.login()
        with patch.object(service.pipeline, 'run') as run:
            for overrides in ({'marketing_template': 'C04'}, {'marketing_template': 'C02', 'platform': 'moments'},
                              {'marketing_template': 'C15'}, {'marketing_template': 'C16'},
                              {'marketing_template': 'C10', 'demo_mode': True}, {'marketing_template': 'C03'}):
                response = self.client.post('/api/run', json={'prompt_variant': 'differentiated', 'platform': 'poster', **overrides})
                self.assertEqual(response.status_code, 422, response.text)
            run.assert_not_called()
        self.assertTrue(service.JOB_SLOTS.acquire(blocking=False))
        service.JOB_SLOTS.release()
        self.assertEqual(self.client.post('/api/run', json={'demo_mode': True}).status_code, 422)


class TemplatePosterTests(unittest.TestCase):
    def test_poster_receives_comic_direction_exact_copy_and_required_labels(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            PILImage.new('RGB', (600, 400), 'white').save(path / 'product.png')
            image = Image('product.png', '测试电脑', path / 'product.png', '', '', '', kind='device', shows_device=True)
            doc = SimpleNamespace(id='test', name='测试电脑', images=[image])
            t = {**task(), '_template_plan': {'id': 'C07'}}
            selected = mt.bind_plan({'template_id': 'C07'}, t, [{'id': 'F1', 'sid': 'S1'}])
            article = mt.decorate({'title': '带电脑去图书馆', 'cta': '到店看看',
                'blocks': [{'type': 'text', 'text': text} for text in ['收好课程资料', '包里已经够满', '配置A约1.3kg', '出发去图书馆']]}, t)
            result = {'task': t, 'planning': {'template': selected}, 'article': article, 'model': {'id': 'test', 'name': '测试电脑'}}
            with patch.object(poster, 'get_kb', return_value=Mock(load=Mock(return_value=doc))), \
                 patch('src.mvp.web_images.cached_images', return_value=[]):
                prepared = poster.prepare(result, path / 'prepared')
            self.assertEqual(prepared['marketing_template']['case_id'], 'C07')
            self.assertIn('清晰的四格动漫', prepared['prompt'])
            self.assertIn('四格逐字文案', prepared['prompt'])
            self.assertIn('四格漫画·情景演绎', prepared['copy'])
            self.assertIn('清晰可读', prepared['prompt'])

    def test_product_pairs_bind_huawei_model_and_prebuilt_fallback(self):
        from src.mvp import marketing_product_pairs as pairs
        data = pairs.library()
        self.assertEqual(set(data['pairs']), {'C01','C02','C04','C07','C08','C09','C10','C13','C14','C15','C16'})
        for case_id, row in data['pairs'].items():
            self.assertTrue(row['model_id'])
            self.assertTrue(row['model_name'].startswith('HUAWEI '))
            self.assertTrue(pairs.fallback_url(case_id).startswith('/static/fallback-samples/'))

    def test_poster_generation_failure_returns_prebuilt_sample_without_final_image(self):
        with tempfile.TemporaryDirectory() as folder:
            poster_dir = Path(folder)
            task_data = {**task(), 'marketing_template': 'C01', 'product': 'HUAWEI MateBook 14（鸿蒙版）'}
            selected = mt.bind_plan({'template_id': 'C01'}, mt.prepare_task(task_data), [{'id': 'F1', 'sid': 'S1'}])
            source = {'task': task_data, 'article': {'title': '选一个颜色', 'lead': '', 'cta': '到店看看', 'blocks': []},
                      'planning': {'template': selected}, 'model': {'id': 'HUAWEI MateBook 14', 'name': 'HUAWEI MateBook 14（鸿蒙版）'},
                      'verification': {'state': 'passed', 'remaining': []}}
            prepared = {'reference': {'id':'r','name':'r','source_url':'','sha256':'x'}, 'style_input_sha256':'s',
                        'product_image':'p', 'copy':['HUAWEI'], 'prompt_sha256':'p', 'marketing_template':
                        {'case_id':'C01', 'fallback_url':'/static/fallback-samples/c01-matebook14-color-interaction.png',
                         'product_pair': {'fallback_note':'预制样例'}}}
            with patch.object(settings, 'POSTER_DIR', poster_dir), patch.object(poster, 'prepare', return_value=prepared), \
                 patch.object(poster, 'generate', side_effect=poster.llm.LLMError('生图服务不可用')):
                result = poster.attach(source, 'b' * 32)
            self.assertEqual(result['poster']['status'], 'fallback')
            self.assertTrue(result['poster']['fallback_used'])
            self.assertEqual(result['poster']['fallback_image_url'], prepared['marketing_template']['fallback_url'])
            self.assertNotIn('image_url', result['poster'])
