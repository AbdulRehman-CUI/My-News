"""MyNews local application. Run with the project's virtual environment."""
import json
import os
import re
import secrets
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from flask import Flask, abort, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.exceptions import SecurityError

from storage import close_db, get_db, init_db, preferences
from news import calibration_articles
from recommender import (
    learning_summary, mark_visible, recommend, record_feedback, reset_learning,
    set_exclusions,
)
from editions import archive, edition_items, generate_edition, get_today, saved_stories, set_progress, set_saved
from pdf_export import export_pdf
from taxonomy import ACTIVITIES, AGES, EDUCATION, REGIONS, STEPS, TOPICS

ROOT = Path(__file__).resolve().parent
EXAMPLES = json.loads((ROOT / "setup_examples.json").read_text(encoding="utf-8"))
TIMEZONES = sorted(available_timezones() - {"localtime", "posixrules"})


def calibration_candidates(prefs):
    """Return cached real stories, with fictional examples only before ingestion."""
    db = get_db()
    rows = calibration_articles(db, prefs)
    if rows:
        candidates = []
        for row in rows:
            topic_data = json.loads(row["topics"])
            if not topic_data:
                continue
            topic = topic_data[0]["topic"]
            subtopics = topic_data[0].get("subtopics") or TOPICS.get(topic, [])
            candidates.append({
                "id": row["id"], "topic": topic,
                "subtopic": subtopics[0] if subtopics else "General",
                "title": row["title"], "publisher": row["publisher"],
                "published_at": row["published_at"], "real": True
            })
        if candidates:
            return candidates
    interests = prefs.get("interests", [])
    return [x for x in EXAMPLES if not interests or x["topic"] in interests][:6]


def validate_schedule(timezone, morning_time):
    if timezone not in TIMEZONES:
        raise ValueError("Choose a valid IANA timezone from the list.")
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("That timezone is unavailable. Choose another timezone.") from None
    if not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", morning_time):
        raise ValueError("Enter a valid ready time using hours and minutes (00:00–23:59).")


def save_choices(step, form, prefs, skip=False, confirm_schedule=True):
    """Validate selectable values at the boundary; never infer from demographics."""
    key = STEPS[step][0]
    if key in ("age", "education"):
        value = "" if skip else form.get(key, "")
        allowed = AGES if key == "age" else EDUCATION
        if value and value not in allowed:
            raise ValueError("Choose one of the listed options, or skip this question.")
        prefs[key] = value or None
    elif key == "morning":
        timezone, ready = form.get("timezone", ""), form.get("morning_time", "")
        validate_schedule(timezone, ready)
        if confirm_schedule and form.get("confirmed") != "yes":
            raise ValueError("Confirm your timezone and ready time to finish setup.")
        prefs.update(timezone=timezone, morning_time=ready, schedule_confirmed=confirm_schedule)
    else:
        allowed = {
            "activities": ACTIVITIES, "interests": list(TOPICS), "regions": REGIONS,
            "subtopics": [f"{topic}:{sub}" for topic in prefs.get("interests", []) for sub in TOPICS[topic]],
            "calibration": [x["id"] for x in calibration_candidates(prefs)],
        }[key]
        values = [] if skip else list(dict.fromkeys(form.getlist(key)))
        if any(value not in allowed for value in values):
            raise ValueError("One of those choices is unavailable. Please use the listed options.")
        if key == "regions" and "Worldwide" in values and len(values) > 1:
            raise ValueError("Choose Worldwide on its own, or choose specific regions.")
        prefs[key] = values or (["Worldwide"] if key == "regions" else [])
        if key == "interests":
            prefs["general_interest"] = not bool(values)
            prefs["subtopics"] = [v for v in prefs.get("subtopics", []) if v.split(":", 1)[0] in values]
            valid_ids = {x["id"] for x in calibration_candidates(prefs)}
            prefs["calibration"] = [v for v in prefs.get("calibration", []) if v in valid_ids]
        if key == "calibration":
            prefs["calibration_preferences"] = [
                {"example_id": x["id"], "topic": x["topic"], "subtopic": x["subtopic"]}
                for x in calibration_candidates(prefs) if x["id"] in values
            ]
    # Keep seeded calibration metadata in sync after broad interests change.
    if key == "interests":
        prefs["calibration_preferences"] = [x for x in prefs.get("calibration_preferences", []) if x["example_id"] in prefs["calibration"]]


def create_app(test_config=None):
    app = Flask(__name__, instance_path=str(ROOT / "instance"))
    app.config.from_mapping(
        DATABASE=str(ROOT / "instance" / "mynews.sqlite3"),
        SECRET_KEY=os.environ.get("MYNEWS_SECRET_KEY"),
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=False,  # Local HTTP only. Public hosting requires HTTPS/auth.
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        MAX_CONTENT_LENGTH=32 * 1024,
        TRUSTED_HOSTS=["localhost", "127.0.0.1", "[::1]"],
    )
    if test_config:
        app.config.update(test_config)
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    if not app.config["SECRET_KEY"]:
        secret_file = Path(app.instance_path) / "secret.key"
        try:
            with secret_file.open("x", encoding="utf-8") as secret:
                secret.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        app.config["SECRET_KEY"] = secret_file.read_text(encoding="utf-8").strip()
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()

    @app.before_request
    def prepare_request():
        session.setdefault("csrf", secrets.token_urlsafe(32))
        if request.method == "POST":
            token = request.form.get("csrf_token", "")
            if not token.isascii() or not secrets.compare_digest(token, session["csrf"]):
                abort(400, description="This form has expired. Refresh the page and try again.")
        g.reader = get_db().execute("SELECT * FROM readers WHERE id = ?", (session.get("reader_id"),)).fetchone()

    @app.after_request
    def secure_response(response):
        response.headers["Content-Security-Policy"] = "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.context_processor
    def template_context():
        return {"reader": g.get("reader"), "csrf_token": session.get("csrf", ""), "steps": STEPS}

    @app.route("/profiles", methods=["GET", "POST"])
    def profiles():
        error = None
        if request.method == "POST":
            name = request.form.get("display_name", "").strip()
            if len(name) > 60 or any(ord(c) < 32 for c in name):
                error = "Use a display name of up to 60 characters without control characters."
            else:
                db = get_db()
                with db:
                    cursor = db.execute("INSERT INTO readers(display_name) VALUES (?)", (name or "New reader",))
                    reader_id = cursor.lastrowid
                    if not name:
                        db.execute("UPDATE readers SET display_name = ? WHERE id = ?", (f"Reader {reader_id}", reader_id))
                    db.execute("INSERT INTO preferences(reader_id, data) VALUES (?, ?)", (reader_id, json.dumps({"general_interest": True, "interests": [], "regions": ["Worldwide"]})))
                session.clear()
                session.update(reader_id=reader_id, csrf=secrets.token_urlsafe(32), _permanent=True)
                return redirect(url_for("onboarding", step=0))
        readers = get_db().execute("SELECT * FROM readers ORDER BY id").fetchall()
        return render_template("profiles.html", readers=readers, error=error), 400 if error else 200

    @app.post("/profiles/select")
    def select_profile():
        selected = get_db().execute("SELECT * FROM readers WHERE id = ?", (request.form.get("profile_id"),)).fetchone()
        if selected is None:
            abort(404, description="That local profile could not be found.")
        session.clear()
        session.update(reader_id=selected["id"], csrf=secrets.token_urlsafe(32), _permanent=True)
        return redirect(url_for("paper") if selected["onboarding_complete"] else url_for("onboarding", step=selected["current_step"]))

    @app.route("/onboarding/<int:step>", methods=["GET", "POST"])
    def onboarding(step):
        if g.reader is None:
            return redirect(url_for("profiles"))
        if step >= len(STEPS):
            abort(404)
        if step > g.reader["furthest_step"]:
            return redirect(url_for("onboarding", step=g.reader["current_step"]))
        prefs = preferences(g.reader["id"])
        error = None
        if request.method == "POST":
            if any(key in request.form for key in ("reader_id", "profile_id", "user_id")):
                abort(400, description="Preferences belong to the session-selected reader. Submitted reader identifiers are not accepted.")
            intent = request.form.get("intent", "next")
            if intent not in ("next", "back", "skip", "draft") or (step == 7 and intent == "skip"):
                abort(400, description="That setup action is unavailable.")
            db = get_db()
            try:
                db.execute("BEGIN IMMEDIATE")
                prefs = preferences(g.reader["id"])
                if step == 7 and intent == "back":
                    # Back remains available even when unfinished fields are invalid.
                    try:
                        save_choices(step, request.form, prefs, confirm_schedule=False)
                    except ValueError:
                        pass
                else:
                    save_choices(step, request.form, prefs, skip=intent == "skip", confirm_schedule=intent != "draft")
                complete = step == 7 and intent == "next"
                target = max(0, step - 1) if intent == "back" else min(7, step + 1)
                if intent == "draft":
                    target = step
                db.execute("UPDATE preferences SET data = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE reader_id = ?", (json.dumps(prefs), g.reader["id"]))
                db.execute("UPDATE readers SET current_step = ?, furthest_step = max(furthest_step, ?), onboarding_complete = ? WHERE id = ?", (target, target, int(complete), g.reader["id"]))
                db.commit()
                if intent == "draft":
                    return jsonify(saved=True)
                if complete:
                    generate_edition(db, g.reader["id"], prefs)
                return redirect(url_for("paper", welcome=1) if complete else url_for("onboarding", step=target))
            except ValueError as exc:
                db.rollback()
                error = str(exc)
                if intent == "draft":
                    return jsonify(error=error), 400
        return render_template("onboarding.html", step=step, key=STEPS[step][0], prefs=prefs,
                               error=error, ages=AGES, education=EDUCATION, activities=ACTIVITIES,
                               topics=TOPICS, regions=REGIONS, examples=calibration_candidates(prefs),
                               timezones=TIMEZONES, submitted=request.form if error else None), 400 if error else 200

    def shell_page(page):
        if g.reader is None:
            return redirect(url_for("profiles"))
        prefs = preferences(g.reader["id"])
        recommendations = recommend(get_db(), g.reader["id"], prefs) if page == "discover" else []
        learning = learning_summary(get_db(), g.reader["id"], prefs)
        edition = None
        items = []
        editions = []
        if page == "paper" and g.reader["onboarding_complete"]:
            edition = get_today(get_db(), g.reader["id"], prefs.get("timezone", "UTC"))
            if edition is None:
                edition = generate_edition(get_db(), g.reader["id"], prefs)
            items = edition_items(get_db(), edition["id"], g.reader["id"])
        if page == "library":
            query = request.args.get("q", "")
            editions = archive(get_db(), g.reader["id"], query)
        saved = saved_stories(get_db(), g.reader["id"], request.args.get("q", "")) if page == "library" else []
        return render_template("shell.html", page=page, prefs=prefs,
                               recommendations=recommendations, learning=learning,
                               edition=edition, items=items, editions=editions, saved=saved,
                               library_query=request.args.get("q", ""))

    @app.get("/")
    def paper():
        return shell_page("paper")

    @app.get("/discover")
    def discover():
        return shell_page("discover")

    @app.post("/discover/feedback")
    def discover_feedback():
        if g.reader is None:
            return redirect(url_for("profiles"))
        try:
            record_feedback(
                get_db(), g.reader["id"], request.form.get("recommendation_id", ""),
                request.form.get("event_id", secrets.token_hex(16)),
                request.form.get("event_type", ""),
            )
        except ValueError as exc:
            abort(400, description=str(exc))
        return redirect(url_for("discover"))

    @app.post("/discover/visible")
    def discover_visible():
        if g.reader is None:
            return redirect(url_for("profiles"))
        mark_visible(get_db(), g.reader["id"], request.form.get("recommendation_id", ""))
        return redirect(url_for("discover"))

    @app.post("/paper/feedback")
    def paper_feedback():
        if g.reader is None:
            return redirect(url_for("profiles"))
        try:
            record_feedback(
                get_db(), g.reader["id"], request.form.get("recommendation_id", ""),
                request.form.get("event_id", secrets.token_hex(16)),
                request.form.get("event_type", ""),
            )
        except ValueError as exc:
            abort(400, description=str(exc))
        return redirect(url_for("paper"))

    @app.post("/paper/save")
    def paper_save():
        if g.reader is None:
            return redirect(url_for("profiles"))
        set_saved(get_db(), g.reader["id"], request.form.get("article_id", ""),
                  request.form.get("edition_id", ""), request.form.get("saved") == "1")
        return redirect(url_for("paper"))

    @app.post("/paper/progress")
    def paper_progress():
        if g.reader is None:
            return redirect(url_for("profiles"))
        try:
            set_progress(get_db(), g.reader["id"], request.form.get("edition_id", ""),
                         int(request.form.get("item_id", "0")), request.form.get("completed") == "1")
        except (ValueError, TypeError):
            abort(400, description="That reading progress update is invalid.")
        return redirect(url_for("paper"))

    @app.post("/paper/visible")
    def paper_visible():
        if g.reader is None:
            return redirect(url_for("profiles"))
        mark_visible(get_db(), g.reader["id"], request.form.get("recommendation_id", ""))
        return redirect(url_for("paper"))

    @app.get("/library")
    def library():
        return shell_page("library")

    @app.get("/editions/<edition_id>/pdf")
    def download_edition_pdf(edition_id):
        if g.reader is None:
            return redirect(url_for("profiles"))
        db = get_db()
        edition = db.execute(
            "SELECT * FROM editions WHERE id=? AND reader_id=?", (edition_id, g.reader["id"])
        ).fetchone()
        if edition is None:
            abort(404, description="That edition could not be found.")
        try:
            payload, _cached = export_pdf(ROOT, edition, edition_items(db, edition_id, g.reader["id"]))
        except RuntimeError as exc:
            abort(503, description=str(exc))
        response = app.response_class(payload, mimetype="application/pdf")
        response.headers["Content-Disposition"] = f'attachment; filename="mynews-{edition["local_date"]}.pdf"'
        return response

    @app.get("/editions/<edition_id>")
    def view_edition(edition_id):
        if g.reader is None:
            return redirect(url_for("profiles"))
        edition = get_db().execute(
            "SELECT * FROM editions WHERE id=? AND reader_id=?", (edition_id, g.reader["id"])
        ).fetchone()
        if edition is None:
            abort(404, description="That edition could not be found.")
        prefs = preferences(g.reader["id"])
        return render_template("shell.html", page="paper", prefs=prefs, edition=edition,
                               items=edition_items(get_db(), edition_id, g.reader["id"]),
                               recommendations=[], learning=learning_summary(get_db(), g.reader["id"], prefs),
                               reader=g.reader, editions=archive(get_db(), g.reader["id"]),
                               saved=saved_stories(get_db(), g.reader["id"]), library_query="")

    @app.get("/editor")
    def editor():
        return shell_page("editor")

    @app.post("/editor/exclusions")
    def editor_exclusions():
        if g.reader is None:
            return redirect(url_for("profiles"))
        set_exclusions(get_db(), g.reader["id"], request.form.getlist("exclusions"))
        return redirect(url_for("editor"))

    @app.post("/editor/reset-learning")
    def editor_reset_learning():
        if g.reader is None:
            return redirect(url_for("profiles"))
        reset_learning(get_db(), g.reader["id"])
        return redirect(url_for("editor"))

    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(413)
    def error_page(error):
        if isinstance(error, SecurityError):
            return error.get_response()
        return render_template("error.html", error=error), error.code

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=False)
