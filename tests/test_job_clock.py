import unittest
from src.mvp.jobs import public_snapshot


class JobClockTests(unittest.TestCase):
    def test_running_snapshot_advances_without_new_progress_events(self):
        job = {"state": "running", "started_at": 100, "t": 99, "elapsed_ms": 5000}
        self.assertEqual(public_snapshot(job, now=110)["elapsed_ms"], 10000)
        self.assertEqual(public_snapshot(job, now=115)["elapsed_ms"], 15000)
        self.assertEqual(job["elapsed_ms"], 5000)

    def test_legacy_job_uses_creation_time_and_completed_job_freezes_at_result_total(self):
        job = {"state": "running", "t": 100, "elapsed_ms": 5000}
        self.assertEqual(public_snapshot(job, now=120)["elapsed_ms"], 20000)
        job.update(state="done", result={"total_ms": 21000})
        self.assertEqual(public_snapshot(job, now=99999)["elapsed_ms"], 21000)

    def test_failed_job_does_not_continue_counting(self):
        self.assertEqual(public_snapshot({"state": "error", "t": 100, "elapsed_ms": 15000}, now=99999)["elapsed_ms"], 15000)
