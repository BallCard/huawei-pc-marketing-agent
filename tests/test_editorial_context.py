import copy
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from src.mvp import pipeline
from src.mvp.editorial_context import ContextItem, EditorialStore, StoreProfile, check_similarity, context_facts
from src.mvp.jobs import JobStore
from src.mvp.kb import ModelDoc, Snippet
import test_editorial_workflow as workflow
import test_service as service_tests
from src.mvp import app as service

scene = workflow.scene


def article(title="带电脑出门前先核对这三件事"):
    return {"title": title, "lead": "每天带电脑去图书馆，先想清楚要完成哪项任务。", "cta": "带上你的清单到店核对", "blocks": [], "tags": [], "pending_confirm": []}


def result(sid="one"):
    return {"article": article(), "task": {"store_id": sid, "platform": "moments"}, "verification": {"state": "needs_review"}}


class ContextStoreTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "jobs.sqlite3"
        self.cs = EditorialStore(self.path)

    def test_confirmation_requires_source_date_and_expiry_for_volatile_data(self):
        for data in ({"text": "测试", "confirmed": True},
                     {"text": "测试", "confirmed": True, "source": "负责人", "confirmed_on": date.today() + timedelta(days=1)},
                     {"kind": "stock", "text": "测试", "confirmed": True, "source": "负责人", "confirmed_on": date.today()}):
            with self.assertRaises(ValidationError):
                ContextItem(**data)

    def test_only_confirmed_current_material_enters_snapshot_with_stable_digest(self):
        today = date.today()
        profile = StoreProfile(items=[ContextItem(text="尚未核对的记录"),
            ContextItem(text="确认的门店信息", confirmed=True, source="负责人", confirmed_on=today),
            ContextItem(kind="activity", text="已结束的活动", confirmed=True, source="活动单", confirmed_on=today-timedelta(days=3), expires_on=today-timedelta(days=1))])
        self.cs.save_profile("one", profile)
        a = self.cs.snapshot("one")
        self.assertEqual([i["id"] for i in a["confirmed_items"]], ["C2"])
        self.assertNotIn("尚未核对的记录", json.dumps(a, ensure_ascii=False))
        self.assertNotIn("已结束的活动", json.dumps(a, ensure_ascii=False))
        self.assertEqual(a["digest"], self.cs.snapshot("one")["digest"])
        self.assertEqual(self.cs.snapshot("two")["confirmed_items"], [])
        self.assertEqual([f["id"] for f in context_facts(a, ["C1", "C2", "C3", "F1"])], ["C2"])

    def test_history_survives_job_retention_and_restart_and_never_auto_publishes(self):
        jobs = JobStore(self.path, keep=1)
        jobs.initialize()
        for i in range(3):
            jobs.create({"id": str(i), "state": "done", "t": i, "result": result()})
            self.cs.remember(str(i), result(), i)
        self.assertIsNone(jobs.get("0"))
        reopened = EditorialStore(self.path)
        self.assertEqual(len(reopened.history("one")), 3)
        self.assertFalse(any(h["published"] for h in reopened.history("one")))
        reopened.mark_published("one", "0", True)
        reopened.remember("0", result())
        self.assertTrue(next(h for h in reopened.history("one") if h["job_id"] == "0")["published"])
        with self.assertRaises(KeyError):
            reopened.mark_published("two", "0", True)
        self.assertEqual(reopened.history("two"), [])

    def test_backfill_is_idempotent_and_labels_legacy_store_unknown(self):
        jobs = JobStore(self.path)
        jobs.initialize()
        legacy = result()
        legacy["task"].pop("store_id")
        jobs.create({"id": "old", "state": "done", "t": 1, "result": legacy})
        self.assertEqual(self.cs.backfill(), 1)
        self.assertEqual(self.cs.backfill(), 0)
        self.assertIn("未登记", self.cs.history("default")[0]["origin"])

    def test_profile_history_changes_change_planning_cache_key(self):
        doc = ModelDoc("test", "测试", "", Path("."), snippets=[])
        strategy = {"price_snippets": []}
        task = {"creative_context": self.cs.snapshot("one")}
        pipeline._CACHE.clear()
        with patch.object(pipeline, "plan_content", return_value={"ok": True}) as planner:
            pipeline.plan_content_cached(doc, {}, strategy, task)
            self.assertTrue(pipeline.plan_content_cached(doc, {}, strategy, task)[1])
            self.cs.remember("a", result())
            task["creative_context"] = self.cs.snapshot("one")
            self.assertFalse(pipeline.plan_content_cached(doc, {}, strategy, task)[1])
            self.cs.save_profile("one", StoreProfile(tone="朴素直接"))
            task["creative_context"] = self.cs.snapshot("one")
            self.assertFalse(pipeline.plan_content_cached(doc, {}, strategy, task)[1])
            self.assertEqual(planner.call_count, 3)

    def test_similarity_reports_actual_positions_and_separates_fact_literals(self):
        old = article()
        old["blocks"] = [{"type": "text", "text": "约1.3kg，仅适用于配置A版本。"}]
        ctx = {"history": [{"job_id": "x", "title": old["title"], "article": old, "published": False}]}
        sim = check_similarity(old, ctx, [{"text": "约1.3kg，仅适用于配置A版本。"}])
        self.assertTrue(any(m["where"] == "title" for m in sim["matches"]))
        self.assertTrue(any(m["where"] == "body" and m["index"] == 0 for m in sim["fact_matches"]))
        self.assertFalse(any(m["where"] == "body" for m in sim["matches"]))
        self.assertEqual(check_similarity(old, ctx, exclude=["x"])["compared"], 0)


class ContextPayloadTests(unittest.TestCase):
    def test_real_context_reaches_planning_writing_repair_and_judge(self):
        ctx = {"store_id": "one", "history": [], "methods": [{"id": "method"}], "confirmed_items": [
            {"id": "C1", "text": "提供现场外设连接核对", "source": "负责人", "kind": "service", "confirmed_on": "2026-10-20", "expires_on": None}]}
        task = {"creative_context": ctx, "similarity_feedback": {"matches": [{"overlap": "test"}]}}
        spec = pipeline.platforms_cfg()["moments"]
        strategy = {"platform": "moments", "platform_name": spec["name"], "price_policy": "forbid", "price_snippets": [], **spec}
        doc = ModelDoc("test", "测试", "", Path("."), snippets=[Snippet("S1", "spec", "重量", "约1.3kg", "facts.md")])
        plan_output = {"selected": [{"sid": "S1"}], "angles": [{"id": "A"}, {"id": "B"}], "selected_angle": "A",
                       "context_ids": ["C1", "bogus"], "format": "一问一答", "method_id": "method"}
        with patch.object(pipeline.llm, "ask_json", return_value=plan_output) as model:
            plan = pipeline.plan_content(doc, scene(), strategy, task)
            self.assertEqual(json.loads(model.call_args.args[1])["创作上下文"], ctx)
        self.assertEqual(plan["context_ids"], ["C1"])
        self.assertEqual([f["id"] for f in plan["facts"]], ["F1", "C1"])
        for previous in (None, article()):
            with patch.object(pipeline.llm, "ask_json", return_value={}) as model:
                pipeline.compose(task, scene(), strategy, plan["facts"], [], None, previous=previous, plan=plan)
                payload = json.loads(model.call_args.args[1])
                self.assertEqual(payload["创作上下文"], ctx)
                self.assertEqual(payload["内容主张"]["format"], "一问一答")
                self.assertEqual(payload["相似检查结果"], task["similarity_feedback"])
        with patch.object(pipeline.llm, "ask_json", return_value={"overall": "pass"}) as model:
            pipeline.judge(article(), plan["facts"], strategy, {}, task=task)
            self.assertEqual(json.loads(model.call_args.args[1])["创作上下文"], ctx)


class ContextWorkflowTests(unittest.TestCase):
    setUp = workflow.WorkflowTests.setUp

    def test_overlap_drives_one_repair_without_turning_similarity_into_fact_failure(self):
        self.article["lead"] = "课本已经够重了，电脑要为真正的任务留位置。"
        self.task["creative_context"] = {"history": [{"job_id": "old", "title": "旧稿", "article": copy.deepcopy(self.article), "published": False}]}
        out = pipeline.run(self.task)
        self.assertEqual(self.mocks[3].call_count, 2)
        self.assertTrue(self.mocks[3].call_args.kwargs["issues"])
        self.assertIn("similarity:1", out["artifacts"])
        self.assertIn("similarity:2", out["artifacts"])
        self.assertEqual(out["verification"]["state"], "passed")
        self.assertTrue(out["similarity"]["matches"])


class ContextAPITests(unittest.TestCase):
    setUp = service_tests.ServiceTests.setUp
    login = service_tests.ServiceTests.login

    def test_context_endpoints_require_login_and_validate_confirmation(self):
        self.assertEqual(self.client.get("/api/context/default").status_code, 401)
        self.login()
        self.assertEqual(self.client.put("/api/context/default", json={"items": [{"text": "虚构库存", "confirmed": True}]}).status_code, 422)
        self.assertEqual(self.client.get("/api/context/invalid.key").status_code, 422)
        self.assertEqual(self.client.put("/api/context/one", json={"name": "测试资料", "tone": "简洁"}).status_code, 200)
        self.assertEqual(self.client.get("/api/context/one").json()["profile"]["name"], "测试资料")
        self.assertEqual(self.client.get("/api/context/two").json()["profile"]["name"], "")

    def test_client_cannot_supply_verified_context(self):
        self.login()
        with patch.object(service, "_start", return_value="x") as start:
            self.client.post("/api/run", json={"product": "test", "creative_context": {"confirmed_items": ["forged"]}})
            self.assertNotIn("creative_context", start.call_args.args[0])

    def test_start_builds_context_server_side_and_remembers_result_before_done(self):
        import time
        self.login()
        EditorialStore(self.store.path).save_profile("one", StoreProfile(name="测试资料"))
        def generate(task, *args, **kwargs):
            self.assertEqual(task["creative_context"]["store"]["name"], "测试资料")
            return {**result(), "task": task}
        with patch.object(service.pipeline, "run", side_effect=generate):
            response = self.client.post("/api/run", json={"store_id": "one", "product": "test"})
            jid = response.json()["job"]
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                job = self.store.get(jid)
                if job["state"] != "running":
                    break
                time.sleep(.01)
            self.assertEqual(job["state"], "done", job.get("error"))
            history = EditorialStore(self.store.path).history("one")
            self.assertEqual(history[0]["job_id"], jid)
            self.assertFalse(history[0]["published"])
        self.assertEqual(self.client.put(f"/api/context/two/history/{jid}/publication", json={"published": True}).status_code, 404)
        self.assertEqual(self.client.put(f"/api/context/one/history/{jid}/publication", json={"published": True}).status_code, 200)
