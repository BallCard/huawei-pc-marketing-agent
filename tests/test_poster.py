import base64
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from PIL import Image

from src.mvp import llm, poster, settings


class PosterTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.image = self.folder / "product.png"
        Image.new("RGB", (960, 1280), "white").save(self.image)
        self.prepared = {"board_path":self.image, "reference_path":self.image, "product_path":self.image, "copy":["HUAWEI", "约1.31 kg"], "prompt":"中文海报"}

    def test_reference_registry_only_contains_the_two_user_approved_images(self):
        rows = poster.references()
        self.assertEqual([r["id"] for r in rows], ["fresh-green", "minimal-product"])
        self.assertTrue(all(r["approved_by"] == "user" and r["usage"] == "visual_style_only" for r in rows))

    def test_async_generation_posts_once_retries_only_polling_and_never_sends_token_to_image_host(self):
        png = self.image.read_bytes()
        calls = []
        polls = 0
        def respond(request):
            nonlocal polls
            calls.append(request)
            if request.method == "POST":
                data = json.loads(request.content)
                images = data["image_url"] if isinstance(data["image_url"], list) else [data["image_url"]]
                self.assertTrue(all(image.startswith("data:image/jpeg;base64,") for image in images))
                self.assertEqual(data["model"], settings.POSTER_IMAGE_MODEL)
                return httpx.Response(200, json={"task_id":"test-task"})
            if "/tasks/" in request.url.path:
                polls += 1
                if polls == 1: return httpx.Response(503)
                if polls == 2: return httpx.Response(200, json={"task_status":"RUNNING"})
                return httpx.Response(200, json={"task_status":"SUCCEED", "output_images":["https://image.example/result.png"]})
            self.assertNotIn("authorization", request.headers)
            return httpx.Response(200, content=png)
        client = httpx.Client(transport=httpx.MockTransport(respond))
        with patch.object(poster.httpx, "Client", return_value=client), patch.object(poster.time, "sleep"), \
             patch.object(settings, "POSTER_IMAGE_API_KEY", "test-only-token"):
            events = []
            output = poster.generate(self.prepared, self.folder, events.append, time.monotonic() + 10)
        self.assertEqual(sum(r.method == "POST" for r in calls), 1)
        self.assertEqual(output["width"], 960)
        self.assertEqual(events[-1]["provider_status"], "SUCCEED")

    def test_submit_rejection_does_not_silently_retry(self):
        calls = []
        def respond(request):
            calls.append(request); return httpx.Response(429)
        client = httpx.Client(transport=httpx.MockTransport(respond))
        with patch.object(poster.httpx, "Client", return_value=client), patch.object(settings, "POSTER_IMAGE_API_KEY", "test-only-token"):
            with self.assertRaisesRegex(llm.LLMError, "HTTP 429"):
                poster.generate(self.prepared, self.folder, lambda _:None, time.monotonic() + 10)
        self.assertEqual(len(calls), 1)

    def test_continue_waiting_reuses_provider_task_without_another_post(self):
        calls = []
        def respond(request):
            calls.append(request)
            if request.method == "POST": self.fail("继续等待不得重复提交生图")
            if "/tasks/" in request.url.path:
                self.assertTrue(request.url.path.endswith("/existing-task"))
                return httpx.Response(200, json={"task_status":"SUCCEED", "output_images":["https://image.example/result.png"]})
            return httpx.Response(200, content=self.image.read_bytes())
        client = httpx.Client(transport=httpx.MockTransport(respond))
        with patch.object(poster.httpx, "Client", return_value=client), patch.object(settings, "POSTER_IMAGE_API_KEY", "test-only-token"):
            output = poster.generate(self.prepared, self.folder, lambda _:None, time.monotonic() + 10, existing_task_id="existing-task")
        self.assertEqual(output["task_id"], "existing-task")
        self.assertTrue(all(r.method == "GET" for r in calls))

    def test_gemini_proxy_submits_two_references_once_and_accepts_base64_image(self):
        calls = []
        def respond(request):
            calls.append(request)
            body = json.loads(request.content)
            self.assertEqual(len(body["image"]), 2)
            self.assertEqual(body["response_format"], "b64_json")
            self.assertNotIn("X-ModelScope-Async-Mode", request.headers)
            return httpx.Response(200, json={"data":[{"b64_json":base64.b64encode(self.image.read_bytes()).decode()}]})
        client = httpx.Client(transport=httpx.MockTransport(respond))
        with patch.object(settings, "POSTER_IMAGE_PROVIDER", "gemini_web_proxy"), \
             patch.object(settings, "POSTER_IMAGE_API_KEY", "proxy-test-only"), \
             patch.object(poster.httpx, "Client", return_value=client):
            output = poster.generate(self.prepared, self.folder, lambda _:None, time.monotonic() + 90)
        self.assertEqual(output["height"], 1280)
        self.assertNotIn("task_id", output)
        self.assertEqual(len(calls), 1)

    def test_gemini_proxy_does_not_retry_timeout_or_claim_resumable_task(self):
        calls = []
        def respond(request):
            calls.append(request)
            raise httpx.ReadTimeout("test timeout", request=request)
        client = httpx.Client(transport=httpx.MockTransport(respond))
        with patch.object(settings, "POSTER_IMAGE_API_KEY", "proxy-test-only"), \
             patch.object(poster.httpx, "Client", return_value=client):
            with self.assertRaisesRegex(llm.BudgetExceeded, "上游可能仍在生成"):
                poster.generate_web_proxy(self.prepared, self.folder, lambda _:None, time.monotonic() + 90)
        self.assertEqual(len(calls), 1)

    def test_gemini_text_only_reply_cannot_count_as_generated_image(self):
        client = httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200, json={"data":[],"text":"完成了"})))
        with patch.object(settings, "POSTER_IMAGE_API_KEY", "proxy-test-only"), \
             patch.object(poster.httpx, "Client", return_value=client):
            with self.assertRaisesRegex(llm.LLMError, "没有返回 b64_json"):
                poster.generate_web_proxy(self.prepared, self.folder, lambda _:None, time.monotonic() + 90)

    def test_chatgpt_proxy_uses_its_reference_field_and_records_confirmed_uploads(self):
        def respond(request):
            body = json.loads(request.content)
            self.assertEqual(len(body["reference_images"]), 2)
            self.assertNotIn("image", body)
            self.assertEqual(body["aspect_ratio"], "3:4")
            self.assertEqual(body["n"], 1)
            return httpx.Response(200, json={"data":[{"b64_json":base64.b64encode(self.image.read_bytes()).decode()}],
                                             "applied":{"references_attached":2,"aspect_ratio":"3:4"}})
        client = httpx.Client(transport=httpx.MockTransport(respond))
        with patch.object(settings, "POSTER_IMAGE_PROVIDER", "chatgpt_web_proxy"), \
             patch.object(settings, "POSTER_IMAGE_API_KEY", "proxy-test-only"), \
             patch.object(poster.httpx, "Client", return_value=client):
            output = poster.generate(self.prepared, self.folder, lambda _:None, time.monotonic() + 90)
        self.assertEqual(output["provider_applied"]["references_attached"], 2)

    def test_chatgpt_missing_reference_upload_is_flagged_and_image_is_preserved(self):
        client = httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200, json={
            "data":[{"b64_json":base64.b64encode(self.image.read_bytes()).decode()}], "applied":{"references_attached":1}})))
        with patch.object(settings, "POSTER_IMAGE_PROVIDER", "chatgpt_web_proxy"), \
             patch.object(settings, "POSTER_IMAGE_API_KEY", "proxy-test-only"), \
             patch.object(poster.httpx, "Client", return_value=client):
            generated = poster.generate(self.prepared, self.folder, lambda _:None, time.monotonic() + 90)
        self.assertIn("未确认两张参考图", generated["reference_upload_warning"])
        self.assertTrue((self.folder / "poster.png").exists())

    def test_web_proxy_basic_auth_avoids_modelscope_sdk_token_interception(self):
        def respond(request):
            self.assertEqual(request.headers["Authorization"], "Basic " + base64.b64encode(b"api:proxy-test-only").decode())
            return httpx.Response(200, json={"data":[{"b64_json":base64.b64encode(self.image.read_bytes()).decode()}]})
        client = httpx.Client(transport=httpx.MockTransport(respond))
        with patch.object(settings, "POSTER_IMAGE_PROVIDER", "gemini_web_proxy"), \
             patch.object(settings, "POSTER_IMAGE_AUTH_MODE", "basic"), \
             patch.object(settings, "POSTER_IMAGE_API_KEY", "proxy-test-only"), \
             patch.object(poster.httpx, "Client", return_value=client):
            poster.generate(self.prepared, self.folder, lambda _:None, time.monotonic() + 90)

    def test_review_credentials_are_independent_of_image_provider(self):
        with patch.object(settings, "POSTER_IMAGE_API_KEY", "image-only-test"), \
             patch.object(settings, "POSTER_REVIEW_API_KEY", "review-only-test"), \
             patch.object(settings, "POSTER_REVIEW_BASE_URL", "https://review.example/v1"):
            cfg = settings.llm_config("poster_review")
        self.assertEqual(cfg["api_key"], "review-only-test")
        self.assertEqual(cfg["base_url"], "https://review.example/v1")

    def test_visual_model_pass_cannot_hide_missing_qualifier_or_changed_number(self):
        source = {"model":{"name":"测试电脑"}}
        for actual in (["HUAWEI", "1.31 kg"], ["HUAWEI", "约1.33 kg"]):
            with patch.object(llm, "chat", return_value=json.dumps({"overall":"pass", "observed_texts":actual, "problems":[]})):
                checked = poster.inspect_image(source, self.prepared, self.image)
            self.assertEqual(checked["overall"], "needs_fix")
            self.assertTrue(any(p["type"] == "text" for p in checked["problems"]))

    def test_missing_transcription_is_not_a_pass(self):
        with patch.object(llm, "chat", return_value='{"overall":"pass","problems":[]}'):
            with self.assertRaises(llm.LLMError):
                poster.inspect_image({"model":{}}, self.prepared, self.image)

    def test_cross_image_review_dismisses_visible_false_alarm_but_preserves_missing_copy(self):
        from src.mvp.reconcile import issue_id
        appearance = {"where": "poster", "type": "appearance", "quote": "银色机身", "detail": "机身颜色可能不符"}
        missing = {"where": "poster", "type": "text", "quote": "约1.31 kg", "detail": "缺少限定", "deterministic": True}
        data = {"decisions": [{"id": issue_id(appearance), "decision": "dismiss", "reason": "两图机身均为银色且清晰可见",
                 "verdict": "matching_visible_feature", "generated_observation": "海报中央机身为银色",
                 "reference_observation": "依据图中央机身同为银色"},
                 {"id": issue_id(missing), "decision": "dismiss", "reason": "不应接受对此程序检查的撤销"}]}
        with patch.object(llm, "chat", return_value=json.dumps(data)) as call:
            checked = poster.cross_check_image({"overall": "needs_fix", "problems": [appearance, missing]}, {}, self.prepared, self.image)
        self.assertEqual(checked["overall"], "needs_fix")
        self.assertEqual(len(checked["cross_review"]["dismissed"]), 1)
        self.assertTrue(checked["problems"][0]["deterministic"])
        self.assertEqual(sum(c["type"] == "image_url" for c in call.call_args.args[0][1]["content"]), 2)

    def test_cross_image_review_cannot_dismiss_unknown_structure_or_uncited_text(self):
        from src.mvp.reconcile import issue_id
        risk = {"where": "poster", "type": "uncertain", "detail": "新增接口在原图不可见"}
        with patch.object(llm, "chat", return_value=json.dumps({"decisions": [{"id": issue_id(risk), "decision": "dismiss", "reason": "看起来合理"}]})):
            out = poster.cross_check_image({"overall": "needs_fix", "problems": [risk]}, {}, self.prepared, self.image)
        self.assertEqual(out["problems"][0]["cross_check"], "unresolved")
        self.assertEqual(out["overall"], "needs_fix")

    def test_failed_cross_image_review_preserves_original_problem(self):
        risk = {"where": "poster", "type": "appearance", "detail": "疑似接口改变"}
        with patch.object(llm, "chat", side_effect=llm.LLMError("timeout")):
            out = poster.cross_check_image({"overall": "needs_fix", "problems": [risk]}, {}, self.prepared, self.image)
        self.assertEqual(out["problems"], [risk])
        self.assertEqual(out["cross_review"]["status"], "incomplete")

    def test_only_style_suggestions_do_not_block_image_delivery(self):
        responses = [json.dumps({"observed_texts": self.prepared["copy"]}), json.dumps({"overall": "needs_fix", "problems": [
            {"type": "expression", "detail": "背景颜色可更暖些"}]})]
        with patch.object(llm, "chat", side_effect=responses) as call:
            checked = poster.inspect_image({"model": {}}, self.prepared, self.image)
        self.assertEqual(call.call_count, 2)
        self.assertEqual(checked["overall"], "pass")
        self.assertEqual(len(checked["improvements"]), 1)

    def test_blind_transcription_does_not_receive_expected_copy_or_borrow_later_review_text(self):
        responses = [json.dumps({"observed_texts":["HUAWEI", "PRODUCT"], "unreadable":[]}),
                     json.dumps({"overall":"pass", "observed_texts":["HUAWEI", "约1.31 kg"], "problems":[]})]
        with patch.object(llm, "chat", side_effect=responses) as model:
            checked = poster.inspect_image({"model":{}}, self.prepared, self.image)
        self.assertNotIn("约1.31", model.call_args_list[0].args[0][0]["content"][0]["text"])
        self.assertEqual(checked["observed_texts"], ["HUAWEI", "PRODUCT"])
        self.assertEqual(checked["overall"], "needs_fix")

    def test_unapproved_text_blocks_image_calls_and_preserves_original_verdict(self):
        source = {"article":{"title":"测试"}, "verification":{"state":"needs_review", "remaining":["数字未确认"]}}
        with patch.object(poster, "generate") as generate:
            result = poster.attach(source, "a"*32)
        generate.assert_not_called()
        self.assertEqual(result["poster"]["status"], "blocked")
        self.assertEqual({k:result["verification"][k] for k in source["verification"]}, source["verification"])
        self.assertNotIn("poster", source)

    def test_primary_failure_falls_back_to_free_modelscope_once(self):
        attempts = []
        def fake_generate(prepared, folder, on_activity, deadline, existing_task_id=None, provider=None, model=None):
            used = provider or settings.POSTER_IMAGE_PROVIDER
            attempts.append((used, model or settings.POSTER_IMAGE_MODEL, existing_task_id))
            if used == "private_worker":
                raise llm.LLMError("生图账号连接尚未就绪，请完成账号连接后重试。")
            return {"sha256":"x", "width":960, "height":1280, "task_id":"ms-task"}
        with patch.object(settings, "POSTER_IMAGE_PROVIDER", "private_worker"), \
             patch.object(settings, "POSTER_IMAGE_MODEL", "chatgpt-web"), \
             patch.object(settings, "POSTER_FALLBACK_PROVIDER", "modelscope"), \
             patch.object(settings, "POSTER_FALLBACK_MODEL", "Qwen/Qwen-Image-Edit-2511"), \
             patch.object(poster, "generate", side_effect=fake_generate):
            events = []
            output = poster.generate_with_fallback(self.prepared, self.folder, events.append, time.monotonic() + 300)
        self.assertEqual([a[0] for a in attempts], ["private_worker", "modelscope"])
        self.assertIsNone(attempts[1][2], "备选链路必须是新任务，不能复用主链路任务号")
        self.assertEqual(output["provider"], "modelscope")
        self.assertEqual(output["model"], "Qwen/Qwen-Image-Edit-2511")
        self.assertEqual(output["fallback_from"], "private_worker")
        self.assertIn("连接尚未就绪", output["fallback_reason"])
        self.assertTrue(any(e.get("provider_status") == "FALLBACK" for e in events))

    def test_primary_timeout_is_not_turned_into_a_second_generation(self):
        with patch.object(settings, "POSTER_IMAGE_PROVIDER", "private_worker"), \
             patch.object(settings, "POSTER_FALLBACK_PROVIDER", "modelscope"), \
             patch.object(poster, "generate", side_effect=llm.BudgetExceeded("等待已超时")) as generate:
            with self.assertRaises(llm.BudgetExceeded):
                poster.generate_with_fallback(self.prepared, self.folder, lambda _:None, time.monotonic() + 300)
        self.assertEqual(generate.call_count, 1)

    def test_fallback_is_skipped_when_no_time_is_left(self):
        with patch.object(settings, "POSTER_IMAGE_PROVIDER", "private_worker"), \
             patch.object(settings, "POSTER_FALLBACK_PROVIDER", "modelscope"), \
             patch.object(settings, "POSTER_FALLBACK_MIN_SECONDS", 180), \
             patch.object(poster, "generate", side_effect=llm.LLMError("连接未就绪")) as generate:
            with self.assertRaisesRegex(llm.LLMError, "剩余时间不足"):
                poster.generate_with_fallback(self.prepared, self.folder, lambda _:None, time.monotonic() + 30)
        self.assertEqual(generate.call_count, 1)

    def test_fallback_disabled_keeps_original_failure(self):
        with patch.object(settings, "POSTER_IMAGE_PROVIDER", "private_worker"), \
             patch.object(settings, "POSTER_FALLBACK_PROVIDER", ""), \
             patch.object(poster, "generate", side_effect=llm.LLMError("连接未就绪")) as generate:
            with self.assertRaisesRegex(llm.LLMError, "连接未就绪"):
                poster.generate_with_fallback(self.prepared, self.folder, lambda _:None, time.monotonic() + 300)
        self.assertEqual(generate.call_count, 1)

    def test_fallback_image_cannot_be_delivered_as_verified(self):
        source = {"article":{"title":"测试","lead":"导语","blocks":[],"disclosures":[],"cta":"到店"}, "model":{"name":"测试电脑"},
                  "task":{}, "verification":{"state":"passed"}, "evidence":{"facts":[]}}
        generated = {"sha256":"x", "width":960, "height":1280, "provider":"modelscope",
                     "model":"Qwen/Qwen-Image-Edit-2511", "fallback_from":"private_worker", "fallback_reason":"生图服务尚未配置私有连接。"}
        prepared = {**self.prepared, "reference":{"id":"minimal-product", "name":"极简产品展示", "source_url":"", "sha256":"r"},
                    "style_input_sha256":"s", "product_image":"I1", "prompt_sha256":"p"}
        with patch.object(poster, "prepare", return_value=prepared), \
             patch.object(poster, "generate_with_fallback", return_value=generated), \
             patch.object(poster, "inspect_image", return_value={"overall":"pass", "problems":[], "cross_review":{"status":"not_needed"}}), \
             patch.object(settings, "POSTER_DIR", self.folder):
            result = poster.attach(source, "b"*32)
        output = result["poster"]
        self.assertEqual(output["provider"], "modelscope")
        self.assertEqual(output["fallback_from"], "private_worker")
        self.assertEqual(output["status"], "needs_review")
        self.assertTrue(any(p["type"] == "provider" and p.get("deterministic") for p in output["review"]["problems"]))


if __name__ == "__main__":
    unittest.main()
