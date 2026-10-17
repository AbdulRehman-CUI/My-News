"""SQLite storage for MyNews. Each request gets its own connection."""
import json
import sqlite3
from flask import current_app, g


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version > 2:
        raise RuntimeError("This database needs a newer version of MyNews.")
    if version == 0:
        db.executescript("""
            BEGIN IMMEDIATE;
            CREATE TABLE readers (
                id INTEGER PRIMARY KEY,
                display_name TEXT NOT NULL CHECK(length(display_name) BETWEEN 1 AND 60),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
                onboarding_complete INTEGER NOT NULL DEFAULT 0 CHECK(onboarding_complete IN (0,1)),
                current_step INTEGER NOT NULL DEFAULT 0 CHECK(current_step BETWEEN 0 AND 7),
                furthest_step INTEGER NOT NULL DEFAULT 0 CHECK(furthest_step BETWEEN 0 AND 7)
            );
            CREATE TABLE preferences (
                reader_id INTEGER PRIMARY KEY REFERENCES readers(id) ON DELETE CASCADE,
                data TEXT NOT NULL CHECK(json_valid(data)),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            );
            PRAGMA user_version = 1;
            COMMIT;
        """)
        version = 1
    if version == 1:
        db.executescript("""
            BEGIN IMMEDIATE;
            CREATE TABLE articles (
                id TEXT PRIMARY KEY,
                canonical_url TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                publisher TEXT NOT NULL,
                language TEXT,
                image_url TEXT,
                published_at TEXT,
                retrieved_at TEXT NOT NULL,
                categories TEXT NOT NULL CHECK(json_valid(categories)),
                topics TEXT NOT NULL CHECK(json_valid(topics)),
                description TEXT,
                article_text TEXT,
                brief TEXT,
                detail TEXT,
                content_depth TEXT NOT NULL CHECK(content_depth IN ('full_text','feed_text','preview_only')),
                content_hash TEXT NOT NULL,
                story_group_id TEXT NOT NULL,
                embedding_model TEXT,
                embedding TEXT CHECK(embedding IS NULL OR json_valid(embedding))
            );
            CREATE INDEX articles_published_idx ON articles(published_at);
            CREATE INDEX articles_content_hash_idx ON articles(content_hash);
            CREATE TABLE news_usage (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                window_start TEXT NOT NULL,
                requests_used INTEGER NOT NULL DEFAULT 0,
                request_limit INTEGER NOT NULL DEFAULT 80
            );
            INSERT INTO news_usage(id, window_start) VALUES (1, strftime('%Y-%m-%dT%H:00:00Z','now'));
            PRAGMA user_version = 2;
            COMMIT;
        """)


def preferences(reader_id):
    row = get_db().execute("SELECT data FROM preferences WHERE reader_id = ?", (reader_id,)).fetchone()
    return json.loads(row["data"]) if row else {}
