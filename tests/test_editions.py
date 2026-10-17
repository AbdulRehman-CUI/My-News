import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from flask import render_template

from app import create_app
from editions import edition_items, generate_edition, set_progress, set_saved


class EditionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "edition.sqlite3")
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test", "DATABASE": self.path})
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("INSERT INTO readers(id, display_name, onboarding_complete) VALUES (1,'One',1)")
        self.db.execute("INSERT INTO readers(id, display_name, onboarding_complete) VALUES (2,'Two',1)")
        self.prefs = {"interests": ["Technology"], "timezone": "UTC", "morning_time": "07:00"}
        self.db.execute("INSERT INTO preferences(reader_id,data) VALUES (1,?)", (json.dumps(self.prefs),))
        self.db.execute("INSERT INTO preferences(reader_id,data) VALUES (2,?)", (json.dumps({"interests":["Sports"],"timezone":"UTC"}),))
        for index, topic in enumerate(("Technology", "Science", "Technology")):
            self.db.execute("""INSERT INTO articles
                (id,canonical_url,title,publisher,retrieved_at,categories,topics,article_text,brief,detail,
                 content_depth,content_hash,story_group_id,embedding)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (f"a{index}", f"https://example.com/{index}", f"Story {index}", "Example",
                 "2026-10-17T00:00:00Z", "[]", json.dumps([{"topic":topic,"subtopics":[]}]),
                 "text " * 200, f"Brief for story {index}. " * 15, f"Detail for story {index}. " * 30,
                 "full_text", f"hash{index}", f"group{index}", json.dumps([1.0, 0.0])))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_generation_is_idempotent_and_snapshots_content(self):
        now = datetime(2026, 10, 17, 8, tzinfo=timezone.utc)
        first = generate_edition(self.db, 1, self.prefs, now=now, limit=3)
        second = generate_edition(self.db, 1, self.prefs, now=now, limit=3)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM editions").fetchone()[0], 1)
        original = self.db.execute("SELECT title,brief FROM edition_items").fetchone()
        self.db.execute("UPDATE articles SET title='Changed', brief='Changed brief' WHERE id='a0'")
        self.db.commit()
        stored = self.db.execute("SELECT title,brief FROM edition_items").fetchone()
        self.assertEqual(tuple(stored), tuple(original))

    def test_print_template_preserves_snapshot_order(self):
        edition = generate_edition(self.db, 1, self.prefs, now=datetime(2026, 10, 17, 8, tzinfo=timezone.utc), limit=3)
        with self.app.test_request_context("/"):
            html = render_template("newspaper.html", edition=edition, items=edition_items(self.db, edition["id"], 1))
        positions = [html.index(f">{number}. Story") for number in (1, 2, 3)]
        self.assertEqual(positions, sorted(positions))

    def test_personalization_and_persistent_save_progress(self):
        now = datetime(2026, 10, 17, 8, tzinfo=timezone.utc)
        first = generate_edition(self.db, 1, self.prefs, now=now, limit=3)
        other = generate_edition(self.db, 2, {"interests":["Sports"],"timezone":"UTC"}, now=now, limit=3)
        self.assertNotEqual(first["id"], other["id"])
        items = edition_items(self.db, first["id"], 1)
        self.assertTrue(items)
        item = items[0]
        set_saved(self.db, 1, item["article_id"], first["id"], True)
        set_progress(self.db, 1, first["id"], item["id"], True)
        refreshed = edition_items(self.db, first["id"], 1)[0]
        self.assertEqual(refreshed["saved"], 1)
        self.assertEqual(refreshed["completed"], 1)
        with self.assertRaises(ValueError):
            set_progress(self.db, 2, first["id"], item["id"], True)

    def test_library_search_and_owned_archive_download_route(self):
        first = generate_edition(self.db, 1, self.prefs, now=datetime(2026, 10, 17, 8, tzinfo=timezone.utc), limit=3)
        client = self.app.test_client()
        with client.session_transaction() as state:
            state["reader_id"] = 1
        response = client.get("/library?q=Story+0")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Story 0", response.data)
        self.assertIn(first["local_date"].encode(), response.data)
        pdf = client.get(f"/editions/{first['id']}/pdf")
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf.mimetype, "application/pdf")
        self.assertTrue(pdf.data.startswith(b"%PDF-"))
        with client.session_transaction() as state:
            state["reader_id"] = 2
        self.assertEqual(client.get(f"/editions/{first['id']}/pdf").status_code, 404)

    def test_onboarding_completion_creates_first_empty_or_ready_edition(self):
        client = self.app.test_client()
        client.get("/profiles")
        with client.session_transaction() as state:
            csrf = state["csrf"]
        response = client.post("/profiles", data={"csrf_token": csrf, "display_name": "New"})
        self.assertEqual(response.status_code, 302)
        for step in range(7):
            with client.session_transaction() as state:
                csrf = state["csrf"]
            client.post(f"/onboarding/{step}", data={"csrf_token":csrf, "intent":"skip"})
        with client.session_transaction() as state:
            csrf = state["csrf"]
        response = client.post("/onboarding/7", data={"csrf_token":csrf, "intent":"next",
            "timezone":"UTC", "morning_time":"07:00", "confirmed":"yes"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM editions").fetchone()[0], 1)
        self.assertEqual(client.get("/").status_code, 200)
        self.assertEqual(client.get("/library").status_code, 200)
        edition_id = self.db.execute("SELECT id FROM editions ORDER BY generated_at DESC LIMIT 1").fetchone()[0]
        self.assertEqual(client.get(f"/editions/{edition_id}").status_code, 200)
