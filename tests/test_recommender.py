import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app import create_app
from recommender import (
    FEATURE_NAMES, learning_summary, recommend, record_feedback,
    reset_learning, set_exclusions,
)


class RecommenderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "recommend.sqlite3")
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test", "DATABASE": self.path})
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("INSERT INTO readers(id, display_name, onboarding_complete) VALUES (1, 'One', 1)")
        self.db.execute("INSERT INTO readers(id, display_name, onboarding_complete) VALUES (2, 'Two', 1)")
        prefs = json.dumps({"interests": ["Technology"], "general_interest": False})
        self.db.execute("INSERT INTO preferences(reader_id, data) VALUES (1, ?)", (prefs,))
        self.db.execute("INSERT INTO preferences(reader_id, data) VALUES (2, ?)", (json.dumps({"interests": ["Sports"]}),))
        for index, (topic, title) in enumerate((
            ("Technology", "Technology report"),
            ("Science", "Science report"),
            ("Sports", "Sports report"),
        )):
            self.db.execute("""INSERT INTO articles
                (id, canonical_url, title, publisher, retrieved_at, categories, topics,
                 article_text, brief, detail, content_depth, content_hash, story_group_id, embedding)
                VALUES (?, ?, ?, ?, '2026-10-17T00:00:00Z', '[]', ?, ?, ?, ?, 'full_text', ?, ?, ?)""",
                (f"a{index}", f"https://example.com/{index}", title, "Example",
                 json.dumps([{"topic": topic, "subtopics": []}]), "A" * 800,
                 f"{title} brief", f"{title} detail", f"h{index}", f"g{index}",
                 json.dumps([1.0 if index == 0 else 0.0, 1.0 if index == 1 else 0.0])))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_cold_start_recommendations_have_features_and_reasons(self):
        result = recommend(self.db, 1, {"interests": ["Technology"]}, limit=3)
        self.assertGreaterEqual(len(result), 2)
        self.assertEqual(len(result[0]["features"]), len(FEATURE_NAMES))
        self.assertIn("selected interests", result[0]["reason"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM recommendations").fetchone()[0], len(result))

    def test_feedback_updates_policy_once_and_correction_changes_reward(self):
        result = recommend(self.db, 1, {"interests": ["Technology"]}, limit=3)
        recommendation_id = result[0]["id"]
        before = learning_summary(self.db, 1, {}).get("policy_b")
        self.assertTrue(record_feedback(self.db, 1, recommendation_id, "event-1", "more"))
        after_more = learning_summary(self.db, 1, {}).get("policy_b")
        self.assertFalse(record_feedback(self.db, 1, recommendation_id, "event-1", "more"))
        self.assertEqual(after_more, learning_summary(self.db, 1, {}).get("policy_b"))
        self.assertTrue(record_feedback(self.db, 1, recommendation_id, "event-2", "less"))
        after_less = learning_summary(self.db, 1, {}).get("policy_b")
        self.assertNotEqual(before, after_more)
        self.assertNotEqual(after_more, after_less)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM feedback_events").fetchone()[0], 2)
        self.assertEqual(self.db.execute("SELECT covariance_applied FROM recommendations").fetchone()[0], 1)

    def test_exclusions_reset_and_reader_isolation_persist(self):
        result = recommend(self.db, 1, {"interests": ["Technology"]}, limit=3)
        record_feedback(self.db, 1, result[0]["id"], "event-reader-one", "more")
        first_state = learning_summary(self.db, 1, {})
        second_state = learning_summary(self.db, 2, {})
        self.assertNotEqual(first_state["policy_b"], second_state["policy_b"])
        set_exclusions(self.db, 1, ["Science"])
        filtered = recommend(self.db, 1, {"interests": ["Technology"]}, limit=3)
        self.assertTrue(all("Science" not in {item["topic"] for item in json.loads(row["topics"])} for row in [x["article"] for x in filtered]))
        generation = first_state["generation"]
        reset_learning(self.db, 1)
        reset = learning_summary(self.db, 1, {})
        self.assertEqual(reset["policy_b"], [0.0] * len(FEATURE_NAMES))
        self.assertGreater(reset["generation"], generation)
        reopened = sqlite3.connect(self.path)
        reopened.row_factory = sqlite3.Row
        self.assertEqual(json.loads(reopened.execute("SELECT policy_b FROM reader_learning WHERE reader_id=1").fetchone()[0]), reset["policy_b"])
        reopened.close()

    def test_discover_route_uses_cached_pool(self):
        client = self.app.test_client()
        with client.session_transaction() as state:
            state["reader_id"] = 1
            state["csrf"] = "token"
        page = client.get("/discover")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Technology report", page.data)
