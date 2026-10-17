import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from app import create_app
from news import canonical_url, extract_permitted_text, ingest


RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>New technology story</title><link>https://news.example/story?id=1</link>
<description>A useful technology report with enough context for a feed brief.</description>
<pubDate>not-a-date</pubDate></item>
</channel></rss>"""


class NewsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "news.sqlite3")
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test", "DATABASE": self.path})
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_rss_only_deduplicates_and_preserves_unknown_date(self):
        response = Mock(content=RSS, status_code=200)
        response.raise_for_status.return_value = None
        session = Mock()
        session.get.return_value = response
        first = ingest(self.db, session=session, feeds={"https://feed.example/rss": ["Technology"]}, model=None)
        second = ingest(self.db, session=session, feeds={"https://feed.example/rss": ["Technology"]}, model=None)
        self.assertEqual(first.new, 1)
        self.assertEqual(second.duplicate, 1)
        row = self.db.execute("SELECT published_at, content_depth FROM articles").fetchone()
        self.assertIsNone(row["published_at"])
        self.assertEqual(row["content_depth"], "feed_text")

    def test_migration_preserves_existing_profile(self):
        app = self.app
        with app.test_client() as client:
            client.get("/profiles")
            with client.session_transaction() as session:
                csrf = session["csrf"]
            response = client.post("/profiles", data={"csrf_token": csrf, "display_name": "Existing"})
            self.assertEqual(response.status_code, 302)
        row = self.db.execute("SELECT display_name FROM readers").fetchone()
        self.assertEqual(row["display_name"], "Existing")
        self.assertEqual(self.db.execute("PRAGMA user_version").fetchone()[0], 3)

    def test_unsafe_extraction_and_embedding_fallback(self):
        self.assertIsNone(canonical_url("file:///etc/passwd"))
        self.assertEqual(extract_permitted_text("http://127.0.0.1/private"), "")

    def test_embedding_cache_reuses_existing_vector(self):
        class Model:
            def encode(self, text, normalize_embeddings=True):
                return [0.1, 0.2]
        response = Mock(content=RSS, status_code=200)
        response.raise_for_status.return_value = None
        session = Mock()
        session.get.return_value = response
        first = ingest(self.db, session=session, feeds={"https://feed.example/rss": ["Technology"]}, model=Model())
        second = ingest(self.db, session=session, feeds={"https://feed.example/rss": ["Technology"]}, model=Model())
        self.assertEqual(first.embeddings_created, 1)
        self.assertGreaterEqual(second.embeddings_reused, 1)

    def test_real_cached_headline_is_rendered_for_calibration(self):
        response = Mock(content=RSS, status_code=200)
        response.raise_for_status.return_value = None
        session = Mock()
        session.get.return_value = response
        ingest(self.db, session=session, feeds={"https://feed.example/rss": ["Technology"]}, model=None)
        with self.app.test_client() as client:
            client.get("/profiles")
            with client.session_transaction() as state:
                csrf = state["csrf"]
            client.post("/profiles", data={"csrf_token": csrf, "display_name": "Reader"})
            for step in range(6):
                with client.session_transaction() as state:
                    token = state["csrf"]
                payload = {"csrf_token": token, "intent": "skip"}
                if step == 3:
                    payload = {"csrf_token": token, "intent": "next", "interests": "Technology"}
                client.post(f"/onboarding/{step}", data=payload)
            page = client.get("/onboarding/6")
            self.assertIn(b"New technology story", page.data)
            self.assertIn(b"news.example", page.data)
