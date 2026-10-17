"""Offline regression checks. No test writes to the real application database."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from app import EXAMPLES, create_app, validate_schedule
from taxonomy import TOPICS


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = {"TESTING": True, "SECRET_KEY": "isolated-test-secret", "DATABASE": str(Path(self.temp.name) / "test.sqlite3")}
        self.app = create_app(self.config)
        self.client = self.app.test_client()

    def post(self, path, data=None, client=None):
        client = client or self.client
        client.get("/profiles")
        with client.session_transaction() as session:
            csrf = session["csrf"]
        return client.post(path, data={"csrf_token": csrf, **(data or {})})

    def create(self, name="Test reader", client=None):
        client = client or self.client
        response = self.post("/profiles", {"display_name": name}, client)
        self.assertEqual(response.status_code, 302)
        with client.session_transaction() as session:
            return session["reader_id"]

    def stored(self, reader_id):
        with closing(sqlite3.connect(self.config["DATABASE"])) as db:
            row = db.execute("SELECT data FROM preferences WHERE reader_id = ?", (reader_id,)).fetchone()
            return json.loads(row[0])

    def step(self, step, data=None, intent="next", client=None):
        return self.post(f"/onboarding/{step}", {"intent": intent, **(data or {})}, client)

    def reach_morning(self, client=None):
        for step in range(7):
            self.assertEqual(self.step(step, intent="skip", client=client).status_code, 302)

    def test_profile_persistence_and_generated_name(self):
        reader_id = self.create("")
        restarted = create_app(self.config).test_client()
        self.assertIn(f"Reader {reader_id}".encode(), restarted.get("/profiles").data)
        self.assertEqual(self.post("/profiles/select", {"profile_id": reader_id}, restarted).status_code, 302)
        self.assertTrue(self.stored(reader_id)["general_interest"])
        with closing(sqlite3.connect(self.config["DATABASE"])) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 3)

    def test_valid_and_invalid_timezones_and_times(self):
        for timezone in ("Asia/Karachi", "America/New_York", "UTC", "Pacific/Auckland"):
            for ready in ("00:00", "07:30", "23:59"):
                validate_schedule(timezone, ready)
        for timezone, ready in (("Mars/Olympus", "07:00"), ("../UTC", "07:00"), ("", "07:00"), ("UTC", "24:00"), ("UTC", "7:00"), ("UTC", "07:60"), ("UTC", "07:00:00"), ("UTC", "")):
            with self.subTest(timezone=timezone, ready=ready), self.assertRaises(ValueError):
                validate_schedule(timezone, ready)

    def test_save_resume_back_and_refresh(self):
        reader_id = self.create()
        self.step(0, {"age": "18–29"})
        self.step(1, {"education": "Undergraduate"})
        self.step(2, {"activities": ["Studying", "Freelancing"]})
        self.step(3, {"interests": ["Technology", "Sports"]}, intent="draft")
        refreshed = self.client.get("/onboarding/3")
        self.assertIn(b'value="Technology" checked', refreshed.data)
        self.assertIn(b'value="Sports" checked', refreshed.data)
        self.step(3, {"interests": ["Technology", "Sports"]})
        self.step(4, {"subtopics": ["Technology:AI", "Sports:Cricket"]}, intent="back")
        self.assertEqual(self.stored(reader_id)["subtopics"], ["Technology:AI", "Sports:Cricket"])
        self.assertIn(b'AI', self.client.get("/onboarding/4").data)
        restarted = create_app(self.config).test_client()
        response = self.post("/profiles/select", {"profile_id": reader_id}, restarted)
        self.assertTrue(response.location.endswith("/onboarding/3"))

    def test_two_profiles_are_isolated_and_identifier_injection_rejected(self):
        first = self.create("One")
        self.step(0, {"age": "50+"})
        other = self.app.test_client()
        second = self.create("Two", other)
        self.step(0, {"age": "Under 18"}, client=other)
        before_first, before_second = self.stored(first), self.stored(second)
        for key in ("reader_id", "profile_id", "user_id"):
            response = self.step(0, {key: second, "age": "30–49"})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.stored(first), before_first)
        self.assertEqual(self.stored(second), before_second)
        self.step(0, {"age": "30–49"})
        self.assertEqual(self.stored(first)["age"], "30–49")
        self.assertEqual(self.stored(second)["age"], "Under 18")
        for client, interests in ((self.client, ["Technology", "Sports"]), (other, ["Health"])):
            self.step(1, intent="skip", client=client)
            self.step(2, intent="skip", client=client)
            self.step(3, {"interests": interests}, client=client)
        self.assertEqual(self.stored(first)["interests"], ["Technology", "Sports"])
        self.assertEqual(self.stored(second)["interests"], ["Health"])
        self.assertEqual(self.step(3, {"reader_id": second, "interests": ["Gaming"]}).status_code, 400)
        self.assertEqual(self.stored(second)["interests"], ["Health"])

    def test_full_completion_and_restart(self):
        reader_id = self.create("A reader")
        values = [{"age": "18–29"}, {"education": "College"}, {"activities": ["Studying", "Employed"]},
                  {"interests": ["Technology", "Sports"]}, {"subtopics": ["Technology:AI", "Sports:Cricket"]},
                  {"regions": ["Pakistan", "Europe"]}, {"calibration": ["setup-tech", "setup-sports"]},
                  {"timezone": "Asia/Karachi", "morning_time": "07:30", "confirmed": "yes"}]
        for step, data in enumerate(values):
            response = self.step(step, data)
            self.assertEqual(response.status_code, 302, response.data)
        self.assertIn(b"Welcome, A reader.", self.client.get("/").data)
        prefs = self.stored(reader_id)
        self.assertEqual(prefs["calibration_preferences"][0]["subtopic"], "AI")
        self.assertEqual(prefs["timezone"], "Asia/Karachi")
        restarted = create_app(self.config).test_client()
        self.assertEqual(self.post("/profiles/select", {"profile_id": reader_id}, restarted).location, "/")
        self.assertIn(b"07:30", restarted.get("/editor").data)

    def test_skips_and_required_confirmation(self):
        reader_id = self.create()
        self.reach_morning()
        prefs = self.stored(reader_id)
        self.assertTrue(prefs["general_interest"])
        self.assertEqual(prefs["interests"], [])
        self.assertEqual(prefs["regions"], ["Worldwide"])
        for data in ({"timezone": "UTC", "morning_time": "07:00"}, {"timezone": "Invalid", "morning_time": "07:00", "confirmed": "yes"}, {"timezone": "UTC", "morning_time": "24:00", "confirmed": "yes"}):
            self.assertEqual(self.step(7, data).status_code, 400)
        self.assertNotIn("schedule_confirmed", self.stored(reader_id))
        self.assertEqual(self.step(7, {"timezone": "UTC", "morning_time": "07:00", "confirmed": "yes"}).status_code, 302)

    def test_morning_drafts_persist_but_do_not_complete_setup(self):
        reader_id = self.create()
        self.reach_morning()
        self.assertEqual(self.step(7, {"timezone": "Asia/Karachi", "morning_time": "08:15"}, intent="draft").status_code, 200)
        self.assertFalse(self.stored(reader_id)["schedule_confirmed"])
        refreshed = self.client.get("/onboarding/7")
        self.assertIn(b'value="08:15"', refreshed.data)
        self.assertIn(b'value="Asia/Karachi" selected', refreshed.data)
        self.assertEqual(self.step(7, {"timezone": "UTC", "morning_time": "broken"}, intent="back").status_code, 302)
        self.assertEqual(self.stored(reader_id)["morning_time"], "08:15")
        restarted = create_app(self.config).test_client()
        self.assertTrue(self.post("/profiles/select", {"profile_id": reader_id}, restarted).location.endswith("/onboarding/6"))

    def test_validation_pruning_and_taxonomy(self):
        self.create()
        for step in range(3):
            self.step(step, intent="skip")
        self.assertEqual(self.step(3, {"interests": ["Invented"]}).status_code, 400)
        self.step(3, {"interests": ["Technology", "Sports"]})
        self.assertEqual(self.step(4, {"subtopics": ["Health:Medicine"]}).status_code, 400)
        self.step(4, {"subtopics": ["Technology:AI", "Sports:Cricket"]})
        self.assertEqual(self.step(5, {"regions": ["Worldwide", "Pakistan"]}).status_code, 400)
        self.step(5, intent="skip")
        self.assertEqual(self.step(6, {"calibration": ["setup-health"]}).status_code, 400)
        self.step(6, {"calibration": ["setup-tech", "setup-sports"]})
        self.step(3, {"interests": ["Sports"]})
        with self.client.session_transaction() as session:
            prefs = self.stored(session["reader_id"])
        self.assertEqual(prefs["subtopics"], ["Sports:Cricket"])
        self.assertEqual(prefs["calibration"], ["setup-sports"])
        self.assertEqual([p["topic"] for p in prefs["calibration_preferences"]], ["Sports"])
        for topic, subtopics in TOPICS.items():
            self.assertTrue(subtopics)
        for example in EXAMPLES:
            self.assertIn(example["subtopic"], TOPICS[example["topic"]])

    def test_security_and_all_pages(self):
        self.assertEqual(self.client.post("/profiles", data={"display_name": "Forgery"}).status_code, 400)
        self.assertEqual(self.client.post("/profiles", data={"csrf_token": "é", "display_name": "Forgery"}).status_code, 400)
        self.create("<script>alert(1)</script>")
        self.assertEqual(self.client.get("/onboarding/7").status_code, 302)
        for path in ("/", "/discover", "/library", "/editor", "/profiles", "/onboarding/0"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn(b"<script>alert(1)</script>", response.data)
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        self.assertEqual(self.client.get("/", headers={"Host": "evil.example"}).status_code, 400)
        self.assertEqual(self.post("/profiles/select", {"profile_id": "9999"}).status_code, 404)
        self.assertEqual(self.post("/profiles", {"display_name": "x" * 61}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
