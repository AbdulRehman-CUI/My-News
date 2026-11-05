"""Terminal-only screen contract checks. No browser or PDF renderer is invoked."""
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

from app import ROOT, create_app
from editions import edition_items, generate_edition, set_saved


class Markup(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.forms, self.links, self.stories, self.images = [], [], [], []
        self.current = None
        self.feed(html)

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if tag == "form":
            self.current = {**attributes, "fields": {}}
            self.forms.append(self.current)
        elif tag in ("input", "button", "select") and self.current is not None:
            if "name" in attributes:
                self.current["fields"].setdefault(attributes["name"], []).append(attributes.get("value", ""))
        if tag == "a":
            self.links.append(attributes.get("href", ""))
        if tag == "article" and attributes.get("id", "").startswith("story-"):
            self.stories.append(attributes)
        if tag == "img":
            self.images.append(attributes)

    def handle_endtag(self, tag):
        if tag == "form":
            self.current = None


class ScreenTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = create_app({"TESTING": True, "SECRET_KEY": "screen-test", "DATABASE": str(Path(self.temp.name) / "screen.sqlite3")})
        self.db = sqlite3.connect(self.app.config["DATABASE"])
        self.db.row_factory = sqlite3.Row
        self.addCleanup(self.db.close)
        self.prefs = {"interests": ["Technology"], "timezone": "Asia/Karachi", "morning_time": "07:00", "schedule_confirmed": True}
        self.db.execute("INSERT INTO readers(id,display_name,onboarding_complete,furthest_step) VALUES(1,'Screen reader',1,7)")
        self.db.execute("INSERT INTO preferences(reader_id,data) VALUES(1,?)", (json.dumps(self.prefs),))
        for index in range(3):
            self.db.execute("""INSERT INTO articles(id,canonical_url,title,publisher,retrieved_at,published_at,topics,categories,
                brief,detail,content_depth,content_hash,story_group_id,image_url)
                VALUES(?,?,?,?,?,?,?,'[]',?,?,'full_text',?,?,?)""",
                (f"screen-{index}", f"https://example.org/{index}", f"Stored headline {index} " + "long " * 20,
                 "Test publisher", "2026-10-17T08:00:00Z", "2026-10-16T23:30:00Z",
                 json.dumps([{"topic": "Technology", "subtopics": ["AI"]}]), f"Saved brief {index}.",
                 f"Saved detail {index}.\nAnother paragraph.", f"hash-{index}", f"group-{index}",
                 "https://example.org/image.jpg" if index != 1 else None))
        self.db.commit()
        self.edition = generate_edition(self.db, 1, self.prefs, now=datetime(2026, 10, 17, 8, tzinfo=timezone.utc))
        self.client = self.app.test_client()
        with self.client.session_transaction() as state:
            state.update(reader_id=1, csrf="screen-token")

    def paper(self):
        response = self.client.get(f"/editions/{self.edition['id']}")
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def test_story_order_content_forms_and_small_editions(self):
        original = [dict(row) for row in edition_items(self.db, self.edition["id"], 1)]
        for count in (1, 2, 3):
            with patch("app.edition_items", return_value=original[:count]):
                html = self.paper()
            markup = Markup(html)
            self.assertEqual([story["id"] for story in markup.stories], [f"story-{row['id']}" for row in original[:count]])
            self.assertEqual(sum("lead-story" in story["class"] for story in markup.stories), 1)
            self.assertEqual(len(markup.images), sum(bool(row["image_url"]) for row in original[:count]))
            for item in original[:count]:
                self.assertIn(item["title"], html)
                self.assertIn(item["brief"], html)
                self.assertIn(item["detail"], html)
                self.assertIn(item["takeaway"], html)
            self.assertIn(f"/editions/{self.edition['id']}/pdf", markup.links)
            for action in ("/paper/feedback", "/paper/visible", "/paper/save", "/paper/progress"):
                forms = [form for form in markup.forms if form["action"] == action]
                self.assertEqual(len(forms), count)
                self.assertTrue(all(form["fields"]["csrf_token"] == ["screen-token"] for form in forms))
            self.assertNotIn("linucb-v1", html)
            self.assertIn("Prepared at", html)
            self.assertIn("News updated through", html)
            self.assertIn("13:00 PKT", html)
            self.assertIn("04:30 PKT", html)
            self.assertIn('loading="eager"', html)
            if count > 1:
                self.assertIn("text-first", html)
        self.assertEqual(original, [dict(row) for row in edition_items(self.db, self.edition["id"], 1)])

    def test_navigation_archive_editor_and_discover_contracts(self):
        item = edition_items(self.db, self.edition["id"], 1)[0]
        set_saved(self.db, 1, item["article_id"], self.edition["id"], True)
        for path in ("/", "/discover", "/library", "/editor", "/profiles", "/onboarding/3", "/onboarding/6", "/onboarding/7"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            markup = Markup(response.get_data(as_text=True))
            for destination in ("/", "/discover", "/library", "/editor", "/profiles"):
                self.assertIn(destination, markup.links)
            for form in markup.forms:
                if form.get("method") == "post":
                    self.assertIn("csrf_token", form["fields"])
        discover = Markup(self.client.get("/discover").get_data(as_text=True))
        feedback = next(form for form in discover.forms if form["action"] == "/discover/feedback")
        self.assertEqual(feedback["fields"]["event_type"][:2], ["more", "less"])
        self.assertIn(feedback["fields"]["event_type"][2], ("save", "unsave"))
        self.assertIn("recommendation_id", feedback["fields"])
        self.assertIn("event_id", feedback["fields"])
        library = self.client.get("/library?q=Stored").get_data(as_text=True)
        self.assertIn(item["title"], library)
        self.assertIn(f"/editions/{self.edition['id']}/pdf", library)
        editor = Markup(self.client.get("/editor").get_data(as_text=True))
        self.assertIn("exclusions", next(f for f in editor.forms if f["action"] == "/editor/exclusions")["fields"])
        self.assertTrue(any(f["action"] == "/editor/reset-learning" for f in editor.forms))

    def test_date_formatting_and_pdf_contract_without_renderer(self):
        format_date = self.app.jinja_env.filters["reader_date"]
        self.assertEqual(format_date("2026-10-16T23:30:00Z", "Asia/Karachi"), "17 Oct 2026, 04:30 PKT")
        self.assertEqual(format_date("2026-10-17"), "Saturday, 17 October 2026")
        self.assertEqual(format_date(None), "Date unknown")
        self.assertEqual(format_date("invalid"), "Date unavailable")
        self.assertIn("UTC", format_date("2026-10-17T00:00:00Z", "Invalid/Zone"))
        with patch("app.export_pdf", return_value=(b"%PDF-test-double", False)) as export:
            response = self.client.get(f"/editions/{self.edition['id']}/pdf")
            self.assertEqual(response.mimetype, "application/pdf")
            export.assert_called_once()
        print_source = (ROOT / "templates/newspaper.html").read_text(encoding="utf-8")
        self.assertNotIn("style.css", print_source)
        self.assertNotIn("screen.js", print_source)

    def test_action_posts_still_save_progress_and_learning(self):
        item = edition_items(self.db, self.edition["id"], 1)[0]
        common = {"csrf_token": "screen-token"}
        self.assertEqual(self.client.post("/paper/visible", data={**common, "recommendation_id":item["recommendation_id"]}).status_code, 302)
        self.assertEqual(self.client.post("/paper/feedback", data={**common, "recommendation_id":item["recommendation_id"], "event_id":"screen-more", "event_type":"more"}).status_code, 302)
        self.assertEqual(self.client.post("/paper/save", data={**common, "article_id":item["article_id"], "edition_id":self.edition["id"], "saved":"1"}).status_code, 302)
        self.assertEqual(self.client.post("/paper/progress", data={**common, "item_id":item["id"], "edition_id":self.edition["id"], "completed":"1"}).status_code, 302)
        refreshed = edition_items(self.db, self.edition["id"], 1)[0]
        self.assertEqual((refreshed["saved"], refreshed["completed"]), (1, 1))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM feedback_events WHERE event_id='screen-more'").fetchone()[0], 1)
        # Native forms omit event_id so each choice, including reversals, is recorded.
        for event_type in ("more", "less"):
            self.assertEqual(self.client.post("/paper/feedback", data={**common, "recommendation_id": item["recommendation_id"], "event_type": event_type}).status_code, 302)
        self.assertEqual(self.db.execute("SELECT event_type FROM feedback_events ORDER BY rowid DESC LIMIT 1").fetchone()[0], "less")
        self.assertEqual(self.client.post("/paper/save", data={"saved":"1"}).status_code, 400)

    def test_discover_save_round_trip_and_ownership(self):
        markup = Markup(self.client.get("/discover").get_data(as_text=True))
        feedback = next(form for form in markup.forms if form["action"] == "/discover/feedback")
        recommendation_id = feedback["fields"]["recommendation_id"][0]
        article_id = self.db.execute("SELECT article_id FROM recommendations WHERE id=?", (recommendation_id,)).fetchone()[0]
        payload = {"csrf_token": "screen-token", "recommendation_id": recommendation_id,
                   "event_id": "discover-save", "event_type": "save"}
        self.assertEqual(self.client.post("/discover/feedback", data=payload).status_code, 302)
        self.assertIsNotNone(self.db.execute("SELECT 1 FROM saved_stories WHERE article_id=? AND reader_id=1", (article_id,)).fetchone())
        self.assertIn('value="unsave" aria-pressed="true"', self.client.get("/discover").get_data(as_text=True))
        self.assertEqual(article_id, self.db.execute("SELECT article_id FROM saved_stories").fetchone()[0])
        self.assertIn("Stored headline", self.client.get("/library").get_data(as_text=True))
        self.assertEqual(self.client.post("/discover/feedback", data={**payload, "event_id": "discover-unsave", "event_type": "unsave"}).status_code, 302)
        self.assertIsNone(self.db.execute("SELECT 1 FROM saved_stories WHERE article_id=?", (article_id,)).fetchone())
        # Replaying a previously applied Save must not reverse the later Unsave.
        self.assertEqual(self.client.post("/discover/feedback", data=payload).status_code, 302)
        self.assertIsNone(self.db.execute("SELECT 1 FROM saved_stories WHERE article_id=?", (article_id,)).fetchone())
        self.assertEqual(self.client.post("/discover/feedback", data={**payload, "recommendation_id": "another-reader"}).status_code, 400)

    def test_web_motion_hooks_are_separate_from_daily_reading_and_pdf(self):
        home = self.client.get("/").get_data(as_text=True)
        daily = self.paper()
        self.assertIn('class="lead-art" aria-hidden="true"', home)
        self.assertNotIn('class="lead-art"', daily)
        self.assertNotIn('data-reveal', daily)
        self.assertIn('class="nav-label"', daily)
        self.assertIn('aria-current="page"', daily)
        self.assertIn('masthead.js', daily)
        self.assertIn('class="action-status" role="status"', daily)
        self.assertIn('Begin reading', daily)
        self.assertIn('id="archive-title"', self.client.get('/library').get_data(as_text=True))
        with self.app.test_request_context('/'):
            from flask import render_template
            pdf_html = render_template('newspaper.html', edition=self.edition, items=edition_items(self.db, self.edition['id'], 1))
        for hook in ('screen.js', 'masthead.js', 'style.css', 'data-reveal', 'lead-art', 'site-header'):
            self.assertNotIn(hook, pdf_html)


if __name__ == "__main__":
    unittest.main()
