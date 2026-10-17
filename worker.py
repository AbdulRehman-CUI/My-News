"""Standalone local worker for scheduled MyNews editions."""
import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from editions import generate_edition
from news import ingest, load_model
from storage import close_db, get_db, init_db

PREPARE_AHEAD = timedelta(hours=6)
REFRESH_NEAR_CUTOFF = timedelta(minutes=30)
CLAIM_TIMEOUT = timedelta(minutes=15)
MAX_ATTEMPTS = 3


def _utc(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_time(value):
    hour, minute = (int(part) for part in value.split(":", 1))
    return hour, minute


def scheduled_instant(local_date, timezone_name, ready_time):
    """Resolve scheduled local time: first ambiguous occurrence, first valid after a gap."""
    zone = ZoneInfo(timezone_name)
    hour, minute = _parse_time(ready_time)
    wall = datetime(local_date.year, local_date.month, local_date.day, hour, minute)
    for offset in range(181):
        candidate = wall + timedelta(minutes=offset)
        aware = candidate.replace(tzinfo=zone, fold=0)
        roundtrip = aware.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)
        if roundtrip >= wall:
            return aware
    raise ValueError("Unable to resolve scheduled local time.")


def due_readers(db, now):
    rows = db.execute("""SELECT r.id, p.data FROM readers r
        JOIN preferences p ON p.reader_id=r.id
        WHERE r.onboarding_complete=1""").fetchall()
    due = []
    for row in rows:
        prefs = json.loads(row["data"])
        timezone_name = prefs.get("timezone") or "UTC"
        local_now = now.astimezone(ZoneInfo(timezone_name))
        scheduled = scheduled_instant(local_now.date(), timezone_name, prefs.get("morning_time", "07:00"))
        due.append({
            "reader_id": row["id"], "prefs": prefs, "local_date": local_now.date().isoformat(),
            "scheduled": scheduled, "due": local_now >= scheduled,
            "until": scheduled - now.astimezone(timezone.utc),
        })
    return due


def _claim(db, reader_id, local_date, now):
    stamp = _utc(now)
    db.execute("""INSERT INTO worker_jobs(reader_id, local_date, status, attempts, claimed_at)
        VALUES (?, ?, 'claimed', 1, ?)
        ON CONFLICT(reader_id, local_date) DO UPDATE SET
        status='claimed', attempts=worker_jobs.attempts+1, claimed_at=excluded.claimed_at,
        last_error=NULL
        WHERE worker_jobs.attempts < ?
          AND (worker_jobs.status != 'succeeded'
           OR worker_jobs.claimed_at IS NULL
           OR worker_jobs.claimed_at < ?)""",
        (reader_id, local_date, stamp, MAX_ATTEMPTS, _utc(now - CLAIM_TIMEOUT)))
    db.commit()
    row = db.execute("SELECT * FROM worker_jobs WHERE reader_id=? AND local_date=?",
                     (reader_id, local_date)).fetchone()
    return bool(row and row["status"] == "claimed" and row["claimed_at"] == stamp and row["attempts"] <= MAX_ATTEMPTS)


def run_once(db, now=None, ingest_fn=None, generate_fn=generate_edition):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    due = due_readers(db, now)
    needs_content = any(item["until"] <= PREPARE_AHEAD for item in due)
    near_cutoff = any(item["until"] <= REFRESH_NEAR_CUTOFF for item in due)
    content_error = None
    if needs_content and ingest_fn:
        try:
            ingest_fn(refresh=near_cutoff)
        except Exception as exc:
            content_error = f"{type(exc).__name__}: {str(exc)[:180]}"
    results = []
    for item in due:
        if not item["due"]:
            results.append({"reader_id": item["reader_id"], "status": "not_due"})
            continue
        if not _claim(db, item["reader_id"], item["local_date"], now):
            results.append({"reader_id": item["reader_id"], "status": "already_claimed"})
            continue
        try:
            db.execute("UPDATE worker_jobs SET status='generating' WHERE reader_id=? AND local_date=?",
                       (item["reader_id"], item["local_date"]))
            db.commit()
            edition = generate_fn(db, item["reader_id"], item["prefs"], now=now)
            db.execute("""UPDATE worker_jobs SET status='succeeded', completed_at=?, last_error=?
                WHERE reader_id=? AND local_date=?""",
                (_utc(now), content_error, item["reader_id"], item["local_date"]))
            db.commit()
            results.append({"reader_id": item["reader_id"], "status": edition["status"], "edition_id": edition["id"]})
        except Exception as exc:
            db.rollback()
            message = content_error or f"{type(exc).__name__}: {str(exc)[:180]}"
            db.execute("""UPDATE worker_jobs SET status='failed', completed_at=?, last_error=?
                WHERE reader_id=? AND local_date=?""",
                (_utc(now), message, item["reader_id"], item["local_date"]))
            db.commit()
            results.append({"reader_id": item["reader_id"], "status": "failed", "error": message})
    return {"prepared": needs_content, "refreshed": near_cutoff, "results": results}


def main():
    parser = argparse.ArgumentParser(description="Run the local MyNews edition worker.")
    parser.add_argument("--database", default="instance/mynews.sqlite3")
    parser.add_argument("--once", action="store_true", help="Run one scheduling pass and exit.")
    parser.add_argument("--interval", type=int, default=300)
    args = parser.parse_args()
    import flask
    app = flask.Flask("mynews-worker", instance_path=str(Path(args.database).resolve().parent))
    app.config["DATABASE"] = args.database
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
        db = get_db()
        model, model_error = load_model()
        if model_error:
            print(f"embedding status: unavailable ({model_error})")

        def prepare_content(refresh=False):
            report = ingest(db, api_key=os.environ.get("THENEWSAPI_KEY"), model=model)
            print(f"content refresh={'yes' if refresh else 'ahead'} new={report.new} duplicates={report.duplicate} errors={len(report.errors)}")

        while True:
            report = run_once(db, ingest_fn=prepare_content)
            print(json.dumps(report, separators=(",", ":")))
            if args.once:
                break
            time.sleep(max(10, args.interval))


if __name__ == "__main__":
    main()
