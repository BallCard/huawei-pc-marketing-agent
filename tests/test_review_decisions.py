import copy
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from src.mvp import app as service, review
from src.mvp.jobs import JobStore


def result_fixture():
    return {"task": {"platform": "moments"}, "article": {"title": "每天带着走"},
            "verification": {"article_version": 2, "judge": {"overall": "needs_fix", "problems": [
                {"where": "title", "index": -1, "quote": "每天带着走", "type": "requirement",
                 "detail": "标题未点明使用场景", "direction": "增加通勤场景"}]},
                "remaining": ["审核模型：标题未点明使用场景"]}, "evidence": {"facts": []}, "status": "ok_with_flags"}


class ReviewQuestionsTests(unittest.TestCase):
    def test_same_explanation_for_distinct_poster_lines_keeps_each_question(self):
        result = result_fixture()
        result["poster"] = {"review":{"problems":[
            {"where":"poster","quote":"约1.31 kg","detail":"成图缺少批准文案"},
            {"where":"poster","quote":"重量依配置与测量方法而异","detail":"成图缺少批准文案"}]}}
        questions = [q for q in review.questions(result)["questions"] if q["origin"] == "poster"]
        self.assertEqual(len(questions), 2)
        self.assertNotEqual(questions[0]["id"], questions[1]["id"])

    def test_questions_come_from_actual_final_issues_and_deduplicate_remaining(self):
        form = review.questions(result_fixture())
        self.assertEqual(len(form["questions"]), 1)
        self.assertEqual(form["questions"][0]["quote"], "每天带着走")

    def test_changed_article_rejects_old_token_and_disagreement_needs_reason(self):
        result = result_fixture()
        form = review.questions(result)
        payload = {"token": form["token"], "resolution": "adopt", "answers": [
            {"id": form["questions"][0]["id"], "choice": "disagree", "reason": ""}]}
        with self.assertRaisesRegex(ValueError, "理由"):
            review.validate_decision(result, payload)
        result["article"]["title"] = "通勤轻一点"
        with self.assertRaises(review.ReviewConflict):
            review.validate_decision(result, payload)


class ReviewAPITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = JobStore(Path(temporary.name) / "jobs.sqlite3")
        kb = Mock()
        kb.whoami.return_value = {}
        kb.models.return_value = []
        for patcher in (patch.object(service, "STORE", self.store),
                        patch.object(service, "JOB_SLOTS", threading.BoundedSemaphore(1)),
                        patch.object(service, "get_kb", return_value=kb),
                        patch.multiple(service.settings, AUTH_USERNAME="", AUTH_PASSWORD="", HOST="127.0.0.1")):
            patcher.start(); self.addCleanup(patcher.stop)
        self.client = TestClient(service.app)
        self.client.__enter__(); self.addCleanup(self.client.__exit__, None, None, None)
        self.original = result_fixture()
        self.store.create({"id": "source", "t": 1, "state": "done", "result": copy.deepcopy(self.original)})

    def payload(self, choice, resolution, reason=""):
        form = self.client.get("/api/job/source/review").json()
        return {"token": form["token"], "resolution": resolution,
                "answers": [{"id": q["id"], "choice": choice, "reason": reason} for q in form["questions"]]}

    def test_manual_adoption_preserves_automatic_verdict_and_survives_reopen(self):
        response = self.client.post("/api/job/source/review", json=self.payload("disagree", "adopt", "原稿已明确携带场景，采用原文"))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["job"])
        saved = JobStore(self.store.path).get("source")
        self.assertEqual(saved["result"]["human_review"]["state"], "adopted")
        self.assertEqual(saved["result"]["verification"], self.original["verification"])
        self.assertEqual(saved["result"]["status"], "ok_with_flags")
        self.assertEqual(len(saved["review_history"]), 1)

    def test_fix_cannot_adopt_unchanged_and_missing_answers_are_rejected(self):
        payload = self.payload("fix", "adopt")
        self.assertEqual(self.client.post("/api/job/source/review", json=payload).status_code, 422)
        payload["answers"] = []
        self.assertEqual(self.client.post("/api/job/source/review", json=payload).status_code, 422)

    def test_continue_uses_saved_article_and_passes_feedback_to_new_job(self):
        done = threading.Event()
        captured = []
        def resume(source, decision, on_update):
            captured.append((source, decision)); done.set()
            return {**result_fixture(), "article": {"title": "通勤轻一点"}}
        with patch.object(service.pipeline, "continue_review", side_effect=resume):
            response = self.client.post("/api/job/source/review", json=self.payload("fix", "continue"))
            self.assertEqual(response.status_code, 200)
            self.assertTrue(done.wait(2))
            self.assertNotEqual(response.json()["job"], "source")
            self.assertEqual(captured[0][0]["article"], self.original["article"])
            self.assertEqual(captured[0][1]["answers"][0]["detail"], "标题未点明使用场景")
        self.assertEqual(self.client.post("/api/job/source/review", json=self.payload("fix", "continue")).status_code, 409)

    def test_confirmed_errors_continue_without_a_questionnaire_or_fake_human_adoption(self):
        source = copy.deepcopy(self.original)
        source["verification"]["judge"]["problems"][0]["cross_check"] = "confirmed"
        self.store.update("source", result=source)
        form = self.client.get("/api/job/source/review").json()
        self.assertEqual(form["questions"], [])
        with patch.object(service, "_start", return_value="automatic-next") as start:
            response = self.client.post("/api/job/source/review", json={"token": form["token"], "answers": [], "resolution": "continue"})
        self.assertEqual(response.status_code, 200)
        saved = self.store.get("source")["result"]
        self.assertNotIn("human_review", saved)
        self.assertEqual(saved["automatic_followup"]["mode"], "automatic")
        self.assertEqual(start.call_args.kwargs["decision"]["answers"][0]["choice"], "fix")
        self.assertEqual(self.client.post("/api/job/source/review", json={"token": form["token"], "answers": [], "resolution": "continue"}).status_code, 409)

    def test_all_seven_completed_fix_answers_can_be_submitted_together(self):
        source = copy.deepcopy(self.original)
        first = source["verification"]["judge"]["problems"][0]
        source["verification"]["judge"]["problems"] = [{**first, "detail": f"第 {i+1} 条需要修改"} for i in range(7)]
        source["verification"]["remaining"] = []
        self.store.update("source", result=source)
        payload = self.payload("fix", "continue")
        self.assertEqual(len(payload["answers"]), 7)
        with patch.object(service, "_start", return_value="seven-fixed") as start:
            response = self.client.post("/api/job/source/review", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["job"], "seven-fixed")
        self.assertEqual(len(start.call_args.kwargs["decision"]["answers"]), 7)
        self.assertTrue(all(a["choice"] == "fix" for a in start.call_args.kwargs["decision"]["answers"]))


if __name__ == "__main__":
    unittest.main()
