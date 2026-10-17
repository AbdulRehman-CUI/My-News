"""Optional Neon integration checks; skipped when no DATABASE_URL is configured."""
import os
import unittest
import uuid
import json

from app import create_app


@unittest.skipUnless(os.environ.get("DATABASE_URL"), "DATABASE_URL is not configured")
class PostgresIntegrationTests(unittest.TestCase):
    def test_schema_and_reader_round_trip(self):
        app = create_app({
            "TESTING": True,
            "DATABASE_URL": os.environ["DATABASE_URL"],
            "SECRET_KEY": "postgres-integration-test-secret",
        })
        with app.app_context():
            from storage import get_db
            db = get_db()
            name = "integration-" + uuid.uuid4().hex[:12]
            row = db.execute(
                "INSERT INTO readers(display_name) VALUES (?) RETURNING id", (name,)
            ).fetchone()
            reader_id = row["id"]
            db.execute(
                "INSERT INTO preferences(reader_id, data) VALUES (?, ?)",
                (reader_id, '{"interests":["Technology"]}'),
            )
            saved = db.execute(
                "SELECT data FROM preferences WHERE reader_id = ?", (reader_id,)
            ).fetchone()
            self.assertEqual(json.loads(saved["data"]), {"interests": ["Technology"]})
            db.execute("DELETE FROM readers WHERE id = ?", (reader_id,))
            db.commit()
