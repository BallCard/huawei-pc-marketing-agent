import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from src.mvp import app as service
from src.mvp.jobs import JobStore
from src.mvp.pipeline import build_result


class ReviewResultTests(unittest.TestCase):
    def test_reviewer_objection_keeps_result_flagged_even_when_rules_pass(self):
        scene = dict(audience="学生", scenario="开学", weights={}, prior_weights={}, llm_weights={})
        strategy = dict(platform="moments", platform_name="朋友圈", images=[1, 3], chars=[40, 90],
                        structure=[], tags=False, price_policy="forbid")
        doc = SimpleNamespace(id="test-model", name="测试电脑", sources=[])
        article = dict(blocks=[], pending_confirm=[], title="测试")
        det = dict(issues=[], platform_issues=[], images=[])
        kb = SimpleNamespace(backend="local")
        for review in ({"overall": "needs_fix", "problems": [{"where": "title", "type": "overclaim", "detail": "缺版本条件"}]},
                       {"overall": "needs_fix", "problems": []}):
            result = build_result({}, scene, {"mode": "specified"}, strategy, doc, [], [], article,
                                  det, review, [], [], kb)
            self.assertEqual(result["status"], "ok_with_flags")
            self.assertTrue(result["verification"]["remaining"])


class JobStoreTests(unittest.TestCase):
    def test_restart_preserves_finished_result_and_marks_running_interrupted(self):
        with tempfile.TemporaryDirectory() as folder:
            store = JobStore(Path(folder) / "jobs.sqlite3")
            store.initialize()
            store.create(dict(id="finished", t=1, state="done", result={"article": "saved"}, steps=[]))
            store.create(dict(id="running", t=2, state="running", result=None, steps=[{"status": "running"}]))
            reopened = JobStore(store.path)
            reopened.initialize()
            self.assertEqual(reopened.get("finished")["result"], {"article": "saved"})
            self.assertEqual(reopened.get("running")["state"], "error")
            self.assertIn("中断", reopened.get("running")["error"])
            self.assertEqual(reopened.get("running")["steps"][0]["status"], "error")

    def test_retention_does_not_remove_an_old_running_task(self):
        with tempfile.TemporaryDirectory() as folder:
            store = JobStore(Path(folder) / "jobs.sqlite3", keep=1)
            store.initialize()
            for jid, state, created in (("active", "running", 0), ("old", "done", 1), ("new", "done", 2)):
                store.create(dict(id=jid, t=created, state=state))
            self.assertIsNotNone(store.get("active"))
            self.assertIsNone(store.get("old"))
            self.assertIsNotNone(store.get("new"))


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = JobStore(Path(self.folder.name) / "jobs.sqlite3")
        kb = Mock()
        kb.whoami.return_value = {"models": 1, "connected": True}
        kb.models.return_value = []
        for patcher in (patch.object(service, "STORE", self.store),
                        patch.object(service, "JOB_SLOTS", threading.BoundedSemaphore(1)),
                        patch.object(service, "get_kb", return_value=kb),
                        patch.multiple(service.settings, AUTH_USERNAME="tester", AUTH_PASSWORD="test-only-password",
                                       COOKIE_SECURE=False, HOST="127.0.0.1", KB_BACKEND="local")):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(service.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def login(self):
        response = self.client.post("/api/login", json={"username": "tester", "password": "test-only-password"})
        self.assertEqual(response.status_code, 200)
        return response

    def test_login_protects_data_static_and_task_endpoints_and_logout_revokes_cookie(self):
        self.assertEqual(self.client.get("/", follow_redirects=False).headers["location"], "/login")
        for path in ("/api/info", "/api/job/unknown", "/img/model/file.jpg", "/static/app.js"):
            self.assertEqual(self.client.get(path).status_code, 401, path)
        self.assertEqual(self.client.post("/api/run", json={}).status_code, 401)
        self.assertEqual(self.client.get("/healthz").json(), {"status": "ok"})
        self.assertEqual(self.client.get("/static/gallery/welcome.jpg").status_code, 200)
        self.assertIn("真实界面", self.client.get("/about").text)
        self.assertEqual(self.client.get("/static/gallery/private.txt").status_code, 401)
        self.assertEqual(self.client.post("/api/login", json={"username": "tester", "password": "wrong"}).status_code, 401)
        response = self.login()
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertEqual(self.client.get("/api/info").json()["version"], "1.0.0")
        self.assertEqual(self.client.get("/").headers["cache-control"], "no-store")
        self.client.post("/logout", follow_redirects=False)
        self.assertEqual(self.client.get("/api/info").status_code, 401)

    def test_expired_and_tampered_sessions_are_rejected(self):
        for token in ("invalid", service.session_token(int(time.time()) - service.SESSION_SECONDS - 1),
                      service.session_token(int(time.time())) + "bad", "1.%E4%B8%AD"):
            self.client.cookies.set("studio-session", token)
            self.assertEqual(self.client.get("/api/info").status_code, 401)
        self.assertFalse(service.valid_session("1.中文"))

    def test_overlapping_generation_is_rejected_and_slot_is_released_after_error(self):
        self.login()
        release = threading.Event()
        def work(*args, **kwargs):
            release.wait(3)
            raise RuntimeError("test failure")
        with patch.object(service.pipeline, "run", side_effect=work):
            first = self.client.post("/api/run", json={})
            jid = first.json()["job"]
            self.assertEqual(self.client.post("/api/run", json={}).status_code, 429)
            release.set()
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                snapshot = self.client.get("/api/job/" + jid).json()
                if snapshot["state"] != "running":
                    break
                time.sleep(.01)
            self.assertEqual(snapshot["state"], "error")
            self.assertTrue(service.JOB_SLOTS.acquire(timeout=1))
            service.JOB_SLOTS.release()

    def test_public_bind_requires_credentials(self):
        with patch.multiple(service.settings, HOST="0.0.0.0", AUTH_PASSWORD="", AUTH_USERNAME=""):
            with self.assertRaisesRegex(RuntimeError, "访问|AUTH_USERNAME"):
                service.settings.validate_runtime()


if __name__ == "__main__":
    unittest.main()
