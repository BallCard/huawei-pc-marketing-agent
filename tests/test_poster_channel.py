import base64
import hashlib
import importlib.util
import io
import json
import os
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from src.mvp import app as service, poster, settings
from src.mvp.jobs import JobStore
from src.mvp.poster_channel import PosterChannel


class PrivatePosterTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.channel = PosterChannel(self.folder / "jobs.sqlite3")
        self.posters = self.folder / "posters"
        image = io.BytesIO()
        Image.new("RGB", (90, 120), "white").save(image, "PNG")
        self.png = image.getvalue()
        self.encoded = base64.b64encode(self.png).decode()
        self.key = "scoped-test-worker-key"
        for patcher in (
            patch.object(service, "STORE", JobStore(self.channel.path)),
            patch.multiple(settings, AUTH_USERNAME="tester", AUTH_PASSWORD="test-login-only",
                           POSTER_WORKER_TOKEN=self.key, JOB_DB=self.channel.path,
                           POSTER_DIR=self.posters, POSTER_IMAGE_PROVIDER="private_worker"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(service.app)
        self.headers = {"X-Poster-Worker-Key": self.key}

    def task(self, job="a"*32, expires=None):
        return self.channel.create(job, {"prompt":"测试，不提交上游"}, expires or time.time()+600)

    def test_scoped_key_cannot_read_workbench_and_cookie_cannot_claim(self):
        self.assertEqual(self.client.post("/api/poster-worker/claim").status_code, 401)
        self.assertEqual(self.client.get("/api/info", headers=self.headers).status_code, 401)
        self.client.cookies.set("studio-session", service.session_token(int(time.time())))
        self.assertEqual(self.client.post("/api/poster-worker/claim").status_code, 401)
        self.assertEqual(self.client.post("/api/poster-worker/heartbeat", headers=self.headers,
                                         json={"ready":True}).status_code, 200)
        with patch.object(settings, "POSTER_WORKER_TOKEN", ""):
            self.assertEqual(self.client.post("/api/poster-worker/claim", headers=self.headers).status_code, 401)

    def test_invalid_and_chunked_oversize_bodies_are_bounded(self):
        path = "/api/poster-worker/heartbeat"
        for size in ("abc", "-1"):
            self.assertEqual(self.client.post(path, headers={**self.headers,"content-length":size}, content=b"{}").status_code, 400)
        response = self.client.post(path, headers=self.headers, content=iter([b"x"*(30*1024*1024)]))
        self.assertEqual(response.status_code, 413)

    def test_parallel_claims_only_deliver_one_task(self):
        task_id = self.task()
        self.task("b"*32)
        with ThreadPoolExecutor(2) as pool:
            claims = list(pool.map(lambda _: self.channel.claim(), range(2)))
        self.assertEqual(sum(bool(claim) for claim in claims), 1)
        self.assertEqual(next(c for c in claims if c)["id"], task_id)
        self.assertEqual(self.task(), task_id)

    def test_lost_running_claim_expires_without_requeuing(self):
        now = time.time()
        task_id = self.task(expires=now+10)
        self.channel.claim()
        second = self.task("b"*32, expires=now+500)
        with patch("src.mvp.poster_channel.time.time", return_value=now+140):
            self.assertEqual(self.channel.claim()["id"], second)
        self.assertEqual(self.channel.get(task_id)["state"], "error")
        self.assertEqual(self.task(), task_id)

    def test_delivery_is_authenticated_and_idempotent(self):
        task_id = self.task()
        claim = self.channel.claim()
        with self.assertRaisesRegex(ValueError, "凭证"):
            self.channel.finish(task_id, "wrong", self.encoded, None, self.posters)
        self.channel.finish(task_id, claim["claim_token"], self.encoded, None, self.posters)
        metadata = self.channel.get(task_id)["result"]
        self.channel.finish(task_id, claim["claim_token"], None, "late failure", self.posters)
        self.assertEqual(self.channel.get(task_id)["state"], "done")
        self.assertEqual(metadata["sha256"], hashlib.sha256((self.posters / ("a"*32) / "poster.png").read_bytes()).hexdigest())

    def test_bad_image_returns_validation_error_then_can_report_failure(self):
        task_id = self.task()
        claim = self.channel.claim()
        path = f"/api/poster-worker/{task_id}/result"
        body = {"claim_token":claim["claim_token"], "image":base64.b64encode(b"not a PNG").decode()}
        self.assertEqual(self.client.post(path, headers=self.headers, json=body).status_code, 400)
        self.assertEqual(self.channel.get(task_id)["state"], "running")
        self.assertEqual(self.client.post(path, headers=self.headers,
            json={"claim_token":claim["claim_token"],"error":"invalid_image"}).status_code, 200)
        self.assertEqual(self.channel.get(task_id)["state"], "error")

    def test_completed_original_task_is_resumed_without_claim_or_resubmission(self):
        task_id = self.task()
        claim = self.channel.claim()
        self.channel.finish(task_id, claim["claim_token"], self.encoded, None, self.posters)
        with patch.object(PosterChannel, "create", side_effect=AssertionError("重复提交")):
            result = poster.generate({}, self.posters/("b"*32), lambda _:None,
                                     time.monotonic()+3, existing_task_id=task_id)
        self.assertEqual(result["task_id"], task_id)
        self.assertEqual(result["width"], 90)

    def test_private_queue_and_authenticated_image_receipt_complete_generation(self):
        self.channel.heartbeat(True)
        product = self.folder / "reference.png"
        product.write_bytes(self.png)
        prepared = {"prompt":"中文测试海报", "product_path":product,"reference_path":product}
        claims = []
        def deliver(_):
            claim = self.client.post("/api/poster-worker/claim", headers=self.headers).json()["task"]
            claims.append(claim)
            self.assertEqual(len(claim["payload"]["images"]), 2)
            self.assertEqual(self.client.post(f'/api/poster-worker/{claim["id"]}/result', headers=self.headers,
                json={"claim_token":claim["claim_token"],"image":self.encoded}).status_code, 200)
        with patch.object(poster.time, "sleep", side_effect=deliver):
            result = poster.generate(prepared, self.posters/("a"*32), lambda _:None,time.monotonic()+10)
        self.assertEqual(len(claims), 1)
        self.assertEqual(result["height"], 120)

    def test_worker_multipart_has_exactly_two_images_and_one_submission(self):
        with patch.dict(os.environ, {"POSTER_WORKER_URL":"https://workbench.example",
                                    "POSTER_WORKER_TOKEN":self.key,"GPTWEB_API_KEY":"test-local-key"}):
            spec = importlib.util.spec_from_file_location("poster_worker", settings.ROOT/"deploy/gpt-direct/worker.py")
            worker = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(worker)
        reference = "data:image/jpeg;base64,"+self.encoded
        with patch.object(worker, "request", return_value={"data":[{"b64_json":self.encoded}]}) as request:
            self.assertEqual(worker.generate({"payload":{"prompt":"中文", "images":[reference,reference]}}), self.encoded)
        request.assert_called_once()
        self.assertEqual(request.call_args.args[0], "http://127.0.0.1:17889/v1/images/edits")
        body = request.call_args.args[1]
        self.assertEqual(body.count(b'name="image"; filename='), 2)
        self.assertIn("中文".encode(), body)


if __name__ == "__main__":
    unittest.main()
