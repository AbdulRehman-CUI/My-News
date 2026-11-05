"""Production pipeline regressions. Providers are mocked; no browser is used."""
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from app import create_app
from editions import edition_items, generate_edition, set_progress, set_saved
from news import (MAX_RESPONSE_BYTES, canonical_url, ingest, ingestion_diagnostics,
                  load_model, remaining_budget)
from recommender import learning_summary, recommend, record_feedback
from storage import transaction
from worker import _claim, run_once

FEED = "https://feed.example/rss"
RSS = b'''<rss version="2.0"><channel><title>Test</title>
<item><title>Technology from RSS</title><link>https://news.example/rss-story</link>
<description>Useful reporting about technology with enough feed text to read without extracting the full publisher page.</description>
</item></channel></rss>'''


def response(body=RSS, status=200):
    result = Mock(status_code=status)
    result.iter_content.return_value = [body]
    result.headers = {}
    return result


class ProductionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "production.sqlite3")
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test", "DATABASE": self.path,
                               "DATABASE_URL": "", "CRON_SECRET": "test-cron-secret"})
        self.db = self.connect()
        self.addCleanup(self.db.close)
        self.prefs = {"interests": ["Technology"], "timezone": "Asia/Karachi", "morning_time": "07:00"}
        for reader_id in (1, 2):
            self.db.execute("INSERT INTO readers(id,display_name,onboarding_complete) VALUES(?,?,1)",
                            (reader_id, f"Reader {reader_id}"))
            self.db.execute("INSERT INTO preferences(reader_id,data) VALUES(?,?)", (reader_id, json.dumps(self.prefs)))
        self.db.commit()
        # Even DNS is mocked: every provider result below is an offline fixture.
        self.addCleanup(patch.stopall)
        patch("news.safe_public_url", side_effect=canonical_url).start()
        self.session = Mock()
        self.session.get.side_effect = lambda *_args, **_kwargs: response()
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session.update(reader_id=1, csrf="test-csrf")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def populate(self, db=None, **kwargs):
        return ingest(db or self.db, session=self.session, feeds={FEED: ["Technology"]}, **kwargs)

    def test_rss_without_optional_packages_or_api_key(self):
        with patch.dict(sys.modules, {"sentence_transformers": None, "torch": None, "playwright": None}):
            model, error = load_model()
            self.assertIsNone(model)
            self.assertTrue(error)
            report = self.populate(model=None)
        self.assertEqual((report.attempted, report.successful, report.new, report.usable), (1, 1, 1, 1))
        row = self.db.execute("SELECT * FROM articles").fetchone()
        self.assertEqual(row["content_depth"], "feed_text")
        self.assertIsNone(row["embedding"])
        self.assertEqual(self.session.get.call_count, 1)

    def test_authentication_precedes_database_access(self):
        anonymous = self.app.test_client()
        with patch("app.get_db", side_effect=AssertionError("must authenticate first")):
            for path in ("/api/cron/ingest", "/api/admin/ingestion"):
                for header in ({}, {"Authorization": "Bearer invalid"}, {"Authorization": "Bearer é"}):
                    result = anonymous.get(path, headers=header)
                    self.assertEqual(result.status_code, 401)
                    self.assertEqual(result.json, {"error": "Unauthorized"})
                    self.assertNotIn("Set-Cookie", result.headers)
            self.app.config["CRON_SECRET"] = None
            self.assertEqual(anonymous.get("/api/cron/ingest", headers={"Authorization": "Bearer None"}).status_code, 401)

    def test_cron_initial_population_and_authenticated_counters(self):
        def refresh(db, api_key=None, model=None):
            self.assertIsNone(model)
            return self.populate(db)
        headers = {"Authorization": "Bearer test-cron-secret"}
        with patch("app.ingest", side_effect=refresh):
            self.assertEqual(self.client.head("/api/cron/ingest", headers=headers).status_code, 405)
            result = self.client.get("/api/cron/ingest", headers=headers)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json["new_articles"], 1)
        self.assertEqual(result.json["total_eligible"], 1)
        self.assertTrue(result.json["last_success_at"])
        with patch.dict("os.environ", {"VERCEL_ENV": "production"}):
            diagnostics = self.client.get("/api/admin/ingestion", headers=headers)
        self.assertEqual(diagnostics.status_code, 200)
        self.assertEqual(diagnostics.json["article_count"], 1)
        self.assertTrue(diagnostics.json["database_connected"])
        self.assertTrue(diagnostics.json["scheduled_ingestion_configured"])
        self.assertFalse(diagnostics.json["embedding_model_available"])
        self.assertNotIn("test-cron-secret", diagnostics.get_data(as_text=True))

    def test_duplicate_keeps_identity_embeddings_learning_and_counts(self):
        class Model:
            def encode(self, *_args, **_kwargs):
                return [0.5, 0.5]
        self.populate(model=Model())
        article = self.db.execute("SELECT id,embedding,embedding_model FROM articles").fetchone()
        rec = recommend(self.db, 1, self.prefs)[0]
        record_feedback(self.db, 1, rec["id"], "learn", "more")
        before = learning_summary(self.db, 1, self.prefs)
        repeated = self.populate(model=None)
        self.assertEqual((repeated.new, repeated.duplicate, repeated.usable), (0, 1, 1))
        self.assertEqual(repeated.embeddings_reused, 1)
        self.assertEqual(tuple(article), tuple(self.db.execute("SELECT id,embedding,embedding_model FROM articles").fetchone()))
        self.assertEqual(before, learning_summary(self.db, 1, self.prefs))

    def test_partial_provider_failure_is_redacted_and_other_source_persists(self):
        def fetch(url, **_kwargs):
            if "broken" in url:
                raise TimeoutError("https://broken.example/?api_token=private-credential")
            return response()
        self.session.get.side_effect = fetch
        report = ingest(self.db, session=self.session, feeds={"https://broken.example/feed": ["Science"], FEED: ["Technology"]})
        self.assertEqual((report.attempted, report.successful, report.new), (2, 1, 1))
        self.assertEqual(report.status, "partial")
        self.assertNotIn("private-credential", str(report))
        self.assertEqual(ingestion_diagnostics(self.db)["last_ingestion_status"], "partial")

    def test_optional_api_ingests_and_enforces_budget(self):
        payload = json.dumps({"data": [{"url": "https://news.example/api", "title": "Technology API report",
                                        "description": "A useful technology report with enough content to prepare a readable brief."}]}).encode()
        self.session.get.side_effect = lambda *_args, **_kwargs: response(payload)
        report = ingest(self.db, session=self.session, feeds={}, api_key="private-key", api_limit=1)
        self.assertEqual(report.new, 1)
        self.assertEqual(self.session.get.call_count, 1)
        self.assertNotIn("private-key", str(report))
        self.assertEqual(remaining_budget(self.db), 79)

    def test_changed_content_keeps_embedding_provenance_and_usable_content(self):
        self.populate()
        self.db.execute("UPDATE articles SET embedding='[0.5,0.5]',embedding_model='previous-model'")
        self.db.commit()
        self.session.get.side_effect = lambda *_args, **_kwargs: response(RSS.replace(b"Useful reporting", b"Updated reporting"))
        self.assertEqual(self.populate().duplicate, 1)
        self.assertEqual(self.db.execute("SELECT embedding_model FROM articles").fetchone()[0], "previous-model")
        self.session.get.side_effect = lambda *_args, **_kwargs: response(RSS.replace(b"Useful reporting about technology with enough feed text to read without extracting the full publisher page.", b"Short."))
        with patch("news.extract_permitted_text", return_value=""):
            self.populate()
        self.assertEqual(self.db.execute("SELECT content_depth FROM articles").fetchone()[0], "feed_text")

    def test_expired_lease_can_recover_but_failed_run_retains_last_success(self):
        self.populate()
        previous = ingestion_diagnostics(self.db)["last_success_at"]
        self.db.execute("UPDATE ingestion_state SET status='running',lease_token='expired',lease_until='2000-01-01T00:00:00Z'")
        self.db.commit()
        self.assertEqual(ingestion_diagnostics(self.db)["last_ingestion_status"], "interrupted")
        self.session.get.side_effect = TimeoutError("private-provider-token")
        report = self.populate()
        self.assertEqual(report.status, "failed")
        self.assertEqual(ingestion_diagnostics(self.db)["last_success_at"], previous)
        self.assertNotIn("private-provider-token", json.dumps(ingestion_diagnostics(self.db)))
        self.session.get.side_effect = lambda *_args, **_kwargs: response()
        self.assertEqual(self.populate().status, "succeeded")

    def test_provider_deadline_is_checked_while_reading(self):
        clock = [0]
        def fetch(*_args, **_kwargs):
            clock[0] = 36
            return response()
        self.session.get.side_effect = fetch
        with patch("news.time.monotonic", side_effect=lambda: clock[0]):
            report = self.populate()
        self.assertTrue(report.bounded)
        self.assertEqual(report.new, 0)
        self.assertEqual(self.session.get.call_count, 1)

    def test_database_error_in_admin_endpoint_is_redacted(self):
        with patch("app.get_db", side_effect=RuntimeError("password-in-connection-string")):
            result = self.client.get("/api/admin/ingestion", headers={"Authorization": "Bearer test-cron-secret"})
        self.assertEqual(result.status_code, 503)
        self.assertFalse(result.json["database_connected"])
        self.assertNotIn("password-in-connection-string", result.get_data(as_text=True))

    def test_execution_article_byte_and_request_bounds(self):
        report = self.populate(max_seconds=0)
        self.assertEqual(report.provider_requests, 0)
        self.assertTrue(report.bounded)
        report = self.populate(max_articles=0)
        self.assertEqual(report.new, 0)
        self.session.get.side_effect = lambda *_args, **_kwargs: response(b"x" * (MAX_RESPONSE_BYTES + 1))
        report = self.populate()
        self.assertEqual(report.status, "failed")
        self.assertEqual(report.provider_requests, 2)
        self.assertEqual(report.new, 0)
        self.session.get.side_effect = lambda *_args, **_kwargs: response()
        report = ingest(self.db, session=self.session, feeds={f"https://feed{i}.example/rss": ["Technology"] for i in range(100)})
        self.assertEqual(report.attempted, 4)
        self.assertLessEqual(report.provider_requests, 16)

    def test_short_previews_remain_ineligible_and_extraction_failure_keeps_feed_text(self):
        self.session.get.side_effect = lambda *_args, **_kwargs: response(RSS.replace(b"Useful reporting about technology with enough feed text to read without extracting the full publisher page.", b"Short preview."))
        with patch("news.extract_permitted_text", return_value=""):
            report = self.populate()
        self.assertEqual(report.preview_only, 1)
        self.assertEqual(recommend(self.db, 1, self.prefs), [])
        self.session.get.side_effect = lambda *_args, **_kwargs: response()
        self.populate()
        self.assertEqual(len(recommend(self.db, 1, self.prefs)), 1)

    def test_discover_without_embeddings_and_safe_distinct_empty_states(self):
        self.assertIn(b"News has not arrived yet", self.client.get("/discover").data)
        self.populate()
        page = self.client.get("/discover")
        self.assertIn(b"Technology from RSS", page.data)
        rec = recommend(self.db, 1, self.prefs)[0]
        self.assertEqual(rec["features"][3], 0)
        self.assertIn("selected interests", rec["reason"])
        self.db.execute("UPDATE preferences SET data=? WHERE reader_id=1", (json.dumps({"interests": ["Sports"]}),))
        self.db.commit()
        self.assertIn(b"No stories match your current interests", self.client.get("/discover").data)
        self.db.execute("UPDATE articles SET content_depth='preview_only'")
        self.db.commit()
        self.assertIn(b"only short previews", self.client.get("/discover").data)

    def test_empty_paper_recovers_same_id_then_remains_immutable(self):
        self.client.get("/")
        empty = self.db.execute("SELECT * FROM editions WHERE reader_id=1").fetchone()
        self.assertEqual(empty["status"], "empty")
        self.populate()
        self.assertIn(b"Technology from RSS", self.client.get("/").data)
        filled = self.db.execute("SELECT * FROM editions WHERE reader_id=1").fetchone()
        self.assertEqual(filled["id"], empty["id"])
        self.assertNotEqual(filled["status"], "empty")
        items = edition_items(self.db, filled["id"], 1)
        set_saved(self.db, 1, items[0]["article_id"], filled["id"], True)
        set_progress(self.db, 1, filled["id"], items[0]["id"], True)
        snapshot = [dict(row) for row in edition_items(self.db, filled["id"], 1)]
        self.db.execute("UPDATE articles SET title='Updated source'")
        self.db.commit()
        self.client.get("/")
        self.assertEqual(snapshot, [dict(row) for row in edition_items(self.db, filled["id"], 1)])
        self.assertEqual(dict(filled), dict(self.db.execute("SELECT * FROM editions WHERE reader_id=1").fetchone()))

    def test_cross_reader_save_progress_feedback_and_download_rejected(self):
        self.populate()
        first = generate_edition(self.db, 1, self.prefs)
        second = generate_edition(self.db, 2, self.prefs)
        item = edition_items(self.db, first["id"], 1)[0]
        with self.assertRaises(ValueError):
            set_saved(self.db, 2, item["article_id"], first["id"], True)
        with self.assertRaises(ValueError):
            set_progress(self.db, 2, second["id"], item["id"], True)
        with self.assertRaises(ValueError):
            record_feedback(self.db, 2, item["recommendation_id"], "cross-reader", "more")
        self.assertEqual(edition_items(self.db, first["id"], 2), [])
        self.assertEqual(self.client.get(f"/editions/{second['id']}").status_code, 404)
        self.assertEqual(self.client.get(f"/editions/{second['id']}/pdf").status_code, 404)

    def test_concurrent_ingestion_and_edition_recovery(self):
        entered, release = threading.Event(), threading.Event()
        def fetch(*_args, **_kwargs):
            entered.set()
            if not release.wait(5):
                raise AssertionError("test release timed out")
            return response()
        self.session.get.side_effect = fetch
        def refresh():
            db = self.connect()
            try:
                return self.populate(db)
            finally:
                db.close()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(refresh)
            self.assertTrue(entered.wait(5))
            try:
                self.assertEqual(self.populate().status, "busy")
                empty = generate_edition(self.db, 1, self.prefs)
                self.assertEqual(empty["status"], "empty")
            finally:
                release.set()
            self.assertEqual(future.result(timeout=5).new, 1)
        ready = generate_edition(self.db, 1, self.prefs)
        self.assertEqual(ready["id"], empty["id"])
        self.assertTrue(edition_items(self.db, ready["id"], 1))

    def test_simultaneous_edition_attempts_publish_one_snapshot(self):
        self.populate()
        barrier = threading.Barrier(2)
        def generate():
            db = self.connect()
            try:
                barrier.wait(timeout=5)
                return dict(generate_edition(db, 1, self.prefs))
            finally:
                db.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(generate) for _ in range(2)]
            results = [future.result(timeout=10) for future in futures]
        self.assertEqual(results[0], results[1])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM editions").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM recommendations").fetchone()[0], 1)

    def test_transaction_rolls_back_recommendations_on_snapshot_failure(self):
        self.populate()
        with patch("editions._takeaway", side_effect=RuntimeError("snapshot failed")):
            with self.assertRaises(RuntimeError):
                generate_edition(self.db, 1, self.prefs)
        for table in ("editions", "edition_items", "recommendations", "reader_learning"):
            self.assertEqual(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
        self.assertTrue(edition_items(self.db, generate_edition(self.db, 1, self.prefs)["id"], 1))

    def test_nested_transaction_does_not_commit_callers_work(self):
        with self.assertRaises(RuntimeError):
            with transaction(self.db):
                recommend(self.db, 1, self.prefs)
                raise RuntimeError("rollback")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM reader_learning").fetchone()[0], 0)

    def test_worker_claim_is_atomic_and_empty_job_is_retryable(self):
        now = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)
        self.assertTrue(_claim(self.db, 1, "2026-10-22", now))
        self.assertFalse(_claim(self.db, 1, "2026-10-22", now + timedelta(seconds=1)))
        def empty(*_args, **_kwargs):
            return {"id": "empty", "status": "empty"}
        result = run_once(self.db, now=now, generate_fn=empty)
        job = self.db.execute("SELECT status FROM worker_jobs WHERE reader_id=2").fetchone()
        self.assertEqual(job["status"], "failed")

    def test_pdf_unavailable_is_a_clear_503_without_browser(self):
        self.populate()
        edition = generate_edition(self.db, 1, self.prefs)
        with patch.dict(sys.modules, {"playwright": None, "playwright.sync_api": None}):
            result = self.client.get(f"/editions/{edition['id']}/pdf")
        self.assertEqual(result.status_code, 503)
        self.assertIn(b"requirements-local.txt", result.data)


if __name__ == "__main__":
    unittest.main()
