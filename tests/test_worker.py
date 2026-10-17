import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app import create_app
from worker import due_readers, run_once, scheduled_instant


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "worker.sqlite3")
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test", "DATABASE": self.path})
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("INSERT INTO readers(id,display_name,onboarding_complete) VALUES (1,'One',1)")
        self.db.execute("INSERT INTO readers(id,display_name,onboarding_complete) VALUES (2,'Two',1)")
        for reader_id, zone, ready in ((1, "UTC", "07:00"), (2, "Asia/Karachi", "18:00")):
            self.db.execute("INSERT INTO preferences(reader_id,data) VALUES (?,?)",
                            (reader_id, json.dumps({"timezone": zone, "morning_time": ready, "interests": []})))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_due_readers_handle_timezone_date_boundary(self):
        now = datetime(2026, 10, 17, 13, 30, tzinfo=timezone.utc)
        due = {item["reader_id"]: item["due"] for item in due_readers(self.db, now)}
        self.assertEqual(due, {1: True, 2: True})

    def test_dst_policy_and_duplicate_claim(self):
        ambiguous = scheduled_instant(datetime(2026, 11, 1).date(), "America/New_York", "01:30")
        self.assertEqual(ambiguous.fold, 0)
        nonexistent = scheduled_instant(datetime(2026, 3, 8).date(), "America/New_York", "02:30")
        self.assertGreaterEqual(nonexistent.astimezone(timezone.utc).astimezone(nonexistent.tzinfo).hour, 3)
        now = datetime(2026, 10, 17, 8, tzinfo=timezone.utc)
        calls = []

        def generate(db, reader_id, prefs, now=None):
            calls.append(reader_id)
            return {"id": f"edition-{reader_id}", "status": "empty"}

        first = run_once(self.db, now=now, generate_fn=generate)
        second = run_once(self.db, now=now, generate_fn=generate)
        self.assertEqual([item["status"] for item in first["results"]], ["empty", "not_due"])
        self.assertEqual(second["results"][0]["status"], "already_claimed")
        self.assertEqual(calls, [1])

    def test_recoverable_failure_is_bounded_and_previous_work_is_preserved(self):
        now = datetime(2026, 10, 17, 8, tzinfo=timezone.utc)
        def fail(*_args, **_kwargs):
            raise TimeoutError("provider unavailable")
        result = run_once(self.db, now=now, generate_fn=fail)
        self.assertEqual(result["results"][0]["status"], "failed")
        job = self.db.execute("SELECT status,attempts,last_error FROM worker_jobs WHERE reader_id=1").fetchone()
        self.assertEqual(job["status"], "failed")
        self.assertIn("provider unavailable", job["last_error"])
