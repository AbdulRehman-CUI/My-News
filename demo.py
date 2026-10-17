"""Create isolated, labeled local demo profiles without fictional news."""
import argparse
import json
import sqlite3

from storage import init_db


def seed(db):
    profiles = (
        ("Demo — Technology reader", {"interests": ["Technology"], "subtopics": ["Technology:AI"], "regions": ["Worldwide"], "timezone": "UTC", "morning_time": "07:00", "schedule_confirmed": True, "general_interest": False}),
        ("Demo — General reader", {"interests": [], "subtopics": [], "regions": ["Worldwide"], "timezone": "UTC", "morning_time": "08:00", "schedule_confirmed": True, "general_interest": True}),
    )
    created = []
    for name, prefs in profiles:
        row = db.execute("SELECT id FROM readers WHERE display_name=?", (name,)).fetchone()
        if row:
            created.append(row[0])
            continue
        cursor = db.execute("""INSERT INTO readers(display_name, onboarding_complete, current_step, furthest_step)
            VALUES (?, 1, 7, 7)""", (name,))
        db.execute("INSERT INTO preferences(reader_id,data) VALUES (?,?)", (cursor.lastrowid, json.dumps(prefs)))
        created.append(cursor.lastrowid)
    db.commit()
    return created


def main():
    parser = argparse.ArgumentParser(description="Seed isolated local MyNews demo profiles.")
    parser.add_argument("--database", default="instance/mynews.sqlite3")
    args = parser.parse_args()
    import flask
    app = flask.Flask("mynews-demo", instance_path=".")
    app.config["DATABASE"] = args.database
    with app.app_context():
        init_db()
        db = sqlite3.connect(args.database)
        print(f"created or reused demo readers: {seed(db)}")
        db.close()


if __name__ == "__main__":
    main()
