"""Phase 4 immutable daily edition generation and reading persistence."""
import json
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from recommender import recommend

READING_WORDS_PER_MINUTE = 220


def _utc_now():
    return datetime.now(timezone.utc)


def _date_for(timezone_name, now=None):
    return (now or _utc_now()).astimezone(ZoneInfo(timezone_name)).date().isoformat()


def _takeaway(brief):
    words = brief.split()
    return " ".join(words[:22]).rstrip(".,;:") + ("…" if len(words) > 22 else "")


def _section(article):
    topics = json.loads(article["topics"] or "[]")
    return topics[0]["topic"] if topics else "General"


def _profile_snapshot(prefs):
    return {
        "interests": list(prefs.get("interests", [])),
        "subtopics": list(prefs.get("subtopics", [])),
        "regions": list(prefs.get("regions", [])),
        "timezone": prefs.get("timezone", "UTC"),
        "morning_time": prefs.get("morning_time", "07:00"),
    }


def get_today(db, reader_id, timezone_name, now=None):
    local_date = _date_for(timezone_name, now)
    return db.execute(
        "SELECT * FROM editions WHERE reader_id=? AND local_date=?",
        (reader_id, local_date),
    ).fetchone()


def generate_edition(db, reader_id, prefs, now=None, limit=10):
    timezone_name = prefs.get("timezone") or "UTC"
    local_date = _date_for(timezone_name, now)
    existing = db.execute(
        "SELECT * FROM editions WHERE reader_id=? AND local_date=?",
        (reader_id, local_date),
    ).fetchone()
    if existing:
        return existing
    generated_at = (now or _utc_now()).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    recommendations = recommend(db, reader_id, prefs, surface="discover", limit=limit)
    status = "ready" if recommendations else "empty"
    if recommendations and sum(len(item["article"]["brief"] or "") for item in recommendations) < 1200:
        status = "short"
    edition_id = uuid.uuid4().hex
    policy_version = recommendations[0]["policy_version"] if recommendations else "linucb-v1"
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute("""INSERT INTO editions
            (id, reader_id, local_date, timezone, scheduled_time, generated_at, cutoff_at,
             status, profile_snapshot, policy_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (edition_id, reader_id, local_date, timezone_name, prefs.get("morning_time", "07:00"),
             generated_at, generated_at, status, json.dumps(_profile_snapshot(prefs)), policy_version))
        for position, item in enumerate(recommendations, 1):
            article = item["article"]
            brief = article["brief"] or article["description"] or "Source material is limited."
            detail = article["detail"] or brief
            db.execute("""INSERT INTO edition_items
                (edition_id, position, section, article_id, recommendation_id, title, publisher,
                 canonical_url, published_at, brief, detail, takeaway, reason, word_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (edition_id, position, _section(article), article["id"], item["id"], article["title"],
                 article["publisher"], article["canonical_url"], article["published_at"], brief, detail,
                 _takeaway(brief), item["reason"], len(brief.split())))
        db.commit()
    except Exception:
        db.rollback()
        existing = db.execute(
            "SELECT * FROM editions WHERE reader_id=? AND local_date=?",
            (reader_id, local_date),
        ).fetchone()
        if existing:
            return existing
        raise
    return db.execute("SELECT * FROM editions WHERE id=?", (edition_id,)).fetchone()


def edition_items(db, edition_id, reader_id):
    return db.execute("""SELECT ei.*, COALESCE(rp.completed, 0) AS completed,
        CASE WHEN ss.article_id IS NULL THEN 0 ELSE 1 END AS saved
        FROM edition_items ei
        JOIN editions e ON e.id=ei.edition_id AND e.reader_id=?
        LEFT JOIN reading_progress rp ON rp.item_id=ei.id AND rp.reader_id=?
        LEFT JOIN saved_stories ss ON ss.article_id=ei.article_id AND ss.reader_id=?
        WHERE ei.edition_id=? ORDER BY ei.position""",
        (reader_id, reader_id, reader_id, edition_id)).fetchall()


def archive(db, reader_id):
    return db.execute("SELECT * FROM editions WHERE reader_id=? ORDER BY local_date DESC", (reader_id,)).fetchall()


def saved_stories(db, reader_id):
    return db.execute("""SELECT ss.*, a.title, a.publisher, a.canonical_url, a.brief
        FROM saved_stories ss JOIN articles a ON a.id=ss.article_id
        WHERE ss.reader_id=? ORDER BY ss.saved_at DESC""", (reader_id,)).fetchall()


def set_saved(db, reader_id, article_id, edition_id, saved):
    if saved:
        db.execute("INSERT OR REPLACE INTO saved_stories(reader_id, article_id, edition_id) VALUES (?, ?, ?)",
                   (reader_id, article_id, edition_id))
    else:
        db.execute("DELETE FROM saved_stories WHERE reader_id=? AND article_id=?", (reader_id, article_id))
    db.commit()


def set_progress(db, reader_id, edition_id, item_id, completed):
    owner = db.execute("SELECT 1 FROM editions WHERE id=? AND reader_id=?", (edition_id, reader_id)).fetchone()
    if not owner:
        raise ValueError("That edition does not belong to this reader.")
    db.execute("""INSERT INTO reading_progress(reader_id, edition_id, item_id, completed)
        VALUES (?, ?, ?, ?) ON CONFLICT(reader_id, edition_id, item_id)
        DO UPDATE SET completed=excluded.completed, updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')""",
        (reader_id, edition_id, item_id, int(bool(completed))))
    db.commit()
