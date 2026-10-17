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
    if version > 5:
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
        version = 2
    if version == 2:
        db.executescript("""
            BEGIN IMMEDIATE;
            CREATE TABLE reader_learning (
                reader_id INTEGER PRIMARY KEY REFERENCES readers(id) ON DELETE CASCADE,
                topic_weights TEXT NOT NULL CHECK(json_valid(topic_weights)),
                recent_weights TEXT NOT NULL CHECK(json_valid(recent_weights)),
                anchors TEXT NOT NULL CHECK(json_valid(anchors)),
                evidence TEXT NOT NULL CHECK(json_valid(evidence)),
                exclusions TEXT NOT NULL CHECK(json_valid(exclusions)),
                policy_a TEXT NOT NULL CHECK(json_valid(policy_a)),
                policy_b TEXT NOT NULL CHECK(json_valid(policy_b)),
                policy_version TEXT NOT NULL DEFAULT 'linucb-v1',
                generation INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            );
            CREATE TABLE recommendations (
                id TEXT PRIMARY KEY,
                reader_id INTEGER NOT NULL REFERENCES readers(id) ON DELETE CASCADE,
                article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
                surface TEXT NOT NULL CHECK(surface IN ('discover')),
                position INTEGER NOT NULL,
                features TEXT NOT NULL CHECK(json_valid(features)),
                score REAL NOT NULL,
                reason TEXT NOT NULL,
                policy_version TEXT NOT NULL,
                generation INTEGER NOT NULL,
                visible INTEGER NOT NULL DEFAULT 0 CHECK(visible IN (0,1)),
                effective_reward REAL,
                covariance_applied INTEGER NOT NULL DEFAULT 0 CHECK(covariance_applied IN (0,1)),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            );
            CREATE INDEX recommendations_reader_idx ON recommendations(reader_id, created_at);
            CREATE TABLE feedback_events (
                event_id TEXT PRIMARY KEY,
                reader_id INTEGER NOT NULL REFERENCES readers(id) ON DELETE CASCADE,
                recommendation_id TEXT NOT NULL REFERENCES recommendations(id) ON DELETE CASCADE,
                event_type TEXT NOT NULL CHECK(event_type IN ('more','less','save','unsave','source_open','skip','active_read')),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            );
            CREATE INDEX feedback_recommendation_idx ON feedback_events(recommendation_id);
            PRAGMA user_version = 3;
            COMMIT;
        """)
        version = 3
    if version == 3:
        db.executescript("""
            BEGIN IMMEDIATE;
            CREATE TABLE editions (
                id TEXT PRIMARY KEY,
                reader_id INTEGER NOT NULL REFERENCES readers(id) ON DELETE CASCADE,
                local_date TEXT NOT NULL,
                timezone TEXT NOT NULL,
                scheduled_time TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                cutoff_at TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('ready','short','empty','failed')),
                profile_snapshot TEXT NOT NULL CHECK(json_valid(profile_snapshot)),
                policy_version TEXT NOT NULL,
                UNIQUE(reader_id, local_date)
            );
            CREATE TABLE edition_items (
                id INTEGER PRIMARY KEY,
                edition_id TEXT NOT NULL REFERENCES editions(id) ON DELETE CASCADE,
                position INTEGER NOT NULL,
                section TEXT NOT NULL,
                article_id TEXT NOT NULL,
                recommendation_id TEXT,
                title TEXT NOT NULL,
                publisher TEXT NOT NULL,
                canonical_url TEXT NOT NULL,
                published_at TEXT,
                brief TEXT NOT NULL,
                detail TEXT NOT NULL,
                takeaway TEXT NOT NULL,
                reason TEXT NOT NULL,
                word_count INTEGER NOT NULL,
                UNIQUE(edition_id, position)
            );
            CREATE INDEX edition_reader_date_idx ON editions(reader_id, local_date DESC);
            CREATE TABLE saved_stories (
                reader_id INTEGER NOT NULL REFERENCES readers(id) ON DELETE CASCADE,
                article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
                edition_id TEXT REFERENCES editions(id) ON DELETE SET NULL,
                saved_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
                PRIMARY KEY(reader_id, article_id)
            );
            CREATE TABLE reading_progress (
                reader_id INTEGER NOT NULL REFERENCES readers(id) ON DELETE CASCADE,
                edition_id TEXT NOT NULL REFERENCES editions(id) ON DELETE CASCADE,
                item_id INTEGER NOT NULL REFERENCES edition_items(id) ON DELETE CASCADE,
                completed INTEGER NOT NULL DEFAULT 0 CHECK(completed IN (0,1)),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
                PRIMARY KEY(reader_id, edition_id, item_id)
            );
            PRAGMA user_version = 4;
            COMMIT;
        """)
        version = 4
    if version == 4:
        db.executescript("""
            BEGIN IMMEDIATE;
            ALTER TABLE edition_items ADD COLUMN image_url TEXT;
            PRAGMA user_version = 5;
            COMMIT;
        """)
        version = 5


def preferences(reader_id):
    row = get_db().execute("SELECT data FROM preferences WHERE reader_id = ?", (reader_id,)).fetchone()
    return json.loads(row["data"]) if row else {}
