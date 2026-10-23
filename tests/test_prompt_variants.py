import copy
import hashlib
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from src.mvp import pipeline as p, prompt_variants as pv, prompt_comparison as comparison, app as service
import test_editorial_workflow as workflow
import test_service as service_tests


class PromptVariantTests(unittest.TestCase):
    def tearDown(self):
        p._CACHE.clear()

    def test_baseline_matches_recorded_pre_change_snapshot(self):
        root = pv.directory('baseline')
        metadata = json.loads(root.joinpath('snapshot.json').read_text(encoding='utf-8'))
        for name in pv.STEPS:
            self.assertEqual(hashlib.sha256(root.joinpath(name + '.md').read_bytes()).hexdigest(), metadata['sha256'][name + '.md'])

    def test_explicit_selection_is_thread_safe_and_versions_have_distinct_digests(self):
        variants = ['baseline', 'differentiated'] * 8
        with ThreadPoolExecutor(4) as pool:
            actual = list(pool.map(lambda v: p.prompt('compose', v), variants))
        for variant, text in zip(variants, actual):
            self.assertEqual(text, pv.prompt('compose', variant))
        self.assertNotEqual(pv.manifest('baseline')['digest'], pv.manifest('differentiated')['digest'])
        with self.assertRaises(ValueError):
            p.prompt('compose', '../../wrong')

    def test_scene_cache_does_not_reuse_another_variant(self):
        with patch.object(p, 'parse_scene', return_value=workflow.scene()) as parse:
            task = {'audience': '大学生', 'platform': 'moments'}
            p.parse_scene_cached({**task, 'prompt_variant': 'baseline'}, None)
            p.parse_scene_cached({**task, 'prompt_variant': 'differentiated'}, None)
            p.parse_scene_cached({**task, 'prompt_variant': 'baseline'}, None)
            self.assertEqual(parse.call_count, 2)

    def test_writer_switches_system_but_keeps_identical_payload(self):
        spec = p.platforms_cfg()['moments']
        strategy = {**spec, 'platform': 'moments', 'platform_name': spec['name'], 'price_policy': 'forbid'}
        calls = []
        for variant in pv.VARIANTS:
            with patch.object(p.llm, 'ask_json', return_value={}) as model:
                p.compose({'prompt_variant': variant, 'creative_context': {'history': []}}, workflow.scene(), strategy, [], [], None)
                calls.append(model.call_args)
        self.assertNotEqual(calls[0].args[0], calls[1].args[0])
        self.assertEqual(calls[0].args[1], calls[1].args[1])
        self.assertEqual(calls[0].kwargs, calls[1].kwargs)


class ComparisonTests(unittest.TestCase):
    setUp = workflow.WorkflowTests.setUp

    def test_one_shared_plan_two_writers_common_reviewer_no_history_mutation(self):
        original = copy.deepcopy(self.task)
        out = comparison.compare(self.task)
        self.assertEqual(out['status'], 'comparison')
        self.assertEqual(self.mocks[2].call_count, 1)
        self.assertEqual(self.mocks[3].call_count, 2)
        self.assertEqual([call.args[0]['prompt_variant'] for call in self.mocks[3].call_args_list], ['baseline', 'differentiated'])
        self.assertEqual([call.args[6]['prompt_variant'] for call in self.mocks[5].call_args_list], ['differentiated', 'differentiated'])
        self.assertEqual(self.task, original)
        self.assertEqual(out['variants']['baseline']['shared_digest'], out['variants']['differentiated']['shared_digest'])
        self.assertEqual(out['variants']['baseline']['writer_system_digest'], hashlib.sha256(p.prompt('compose', 'baseline').encode()).hexdigest())

    def test_failed_first_branch_does_not_erase_second_branch(self):
        self.mocks[3].side_effect = [p.llm.LLMError('测试失败'), self.article]
        out = comparison.compare(self.task)
        self.assertEqual(out['variants']['baseline']['status'], 'error')
        self.assertEqual(out['variants']['differentiated']['status'], 'ok')

    def test_unfinished_review_cannot_pass(self):
        self.mocks[5].side_effect = p.llm.BudgetExceeded('审核超时')
        out = comparison.compare(self.task)
        for r in out['variants'].values():
            self.assertEqual(r['verification']['state'], 'needs_review')
            self.assertTrue(r['error'])

    def test_missing_model_returns_preparation_questions(self):
        self.kb.resolve.return_value = ('ambiguous', ['test'])
        self.kb.info.return_value.name = '测试型号'
        out = comparison.compare(self.task)
        self.assertEqual(out['status'], 'comparison_incomplete')
        self.assertEqual(out['variants']['preparation']['status'], 'need_info')
        self.mocks[3].assert_not_called()

    def test_review_continuation_preserves_original_variant(self):
        task = {**self.task, 'prompt_variant': 'baseline'}
        source = p.run(task)
        self.mocks[3].reset_mock()
        with patch('src.mvp.review.instructions', return_value=['开头具体']):
            p.continue_review(source, {'answers': [{'id': 'x', 'choice': 'fix', 'detail': '开头具体'}], 'resolution': 'continue'})
        self.assertEqual(self.mocks[3].call_args.args[0]['prompt_variant'], 'baseline')


class PromptAPITests(unittest.TestCase):
    setUp = service_tests.ServiceTests.setUp
    login = service_tests.ServiceTests.login

    def test_auth_and_variant_validation(self):
        self.assertEqual(self.client.get('/api/prompts/baseline').status_code, 401)
        self.assertEqual(self.client.post('/api/compare', json={}).status_code, 401)
        self.login()
        self.assertEqual(self.client.post('/api/run', json={'prompt_variant': 'invalid'}).status_code, 422)
        self.assertEqual(self.client.post('/api/compare', json={'platform': 'poster'}).status_code, 422)
        self.assertIn('compose', self.client.get('/api/prompts/baseline').json()['steps'])

    def test_comparison_keeps_server_context_authority(self):
        self.login()
        with patch.object(service, '_start', return_value='x') as start:
            response = self.client.post('/api/compare', json={'creative_context': {'forged': True}, 'prompt_variant': 'differentiated'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(start.call_args.kwargs['comparison'])
        self.assertNotIn('creative_context', start.call_args.args[0])

    def test_comparison_job_persists_without_polluting_editorial_history(self):
        import time
        from src.mvp.editorial_context import EditorialStore
        self.login()
        def generate(task, instruction, on_update):
            self.assertIn('creative_context', task)
            on_update({'steps': [{'step': 'compare', 'status': 'done'}]})
            return {'mode': 'prompt_comparison', 'status': 'comparison', 'variants': {}, 'task': task}
        with patch.object(comparison, 'compare', side_effect=generate):
            jid = self.client.post('/api/compare', json={'platform': 'moments'}).json()['job']
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                job = self.store.get(jid)
                if job['state'] != 'running':
                    break
                time.sleep(.01)
            self.assertEqual(job['state'], 'done', job.get('error'))
        self.assertEqual(self.client.get('/api/job/' + jid).json()['result']['mode'], 'prompt_comparison')
        self.assertEqual(EditorialStore(self.store.path).history('default'), [])


if __name__ == '__main__':
    unittest.main()
