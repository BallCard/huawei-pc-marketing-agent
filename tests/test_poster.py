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
        self.assertEqual(result["verification"], source["verification"])
        self.assertNotIn("poster", source)


if __name__ == "__main__":
    unittest.main()
