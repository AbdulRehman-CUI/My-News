"""Phase 2 news acquisition, content preparation, and embedding cache."""
import argparse
import hashlib
import ipaddress
import json
import os
import re
import socket
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from html import unescape
from urllib.parse import urljoin, urlparse, urlunparse
from taxonomy import TOPICS
from storage import transaction

MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
API_BASE = "https://api.thenewsapi.com/v1/news"
MAX_RESPONSE_BYTES = 2_000_000
DEFAULT_FEEDS = {
    "https://feeds.bbci.co.uk/news/rss.xml": ["Politics", "Business", "Science", "Technology", "Health"],
    "https://feeds.bbci.co.uk/sport/rss.xml": ["Sports"],
    "https://www.nasa.gov/rss/dyn/breaking_news.rss": ["Science", "Technology"],
    "https://www.npr.org/rss/rss.php?id=1001": ["Politics", "Culture", "Education"],
}


@dataclass
class IngestReport:
    attempted: int = 0
    successful: int = 0
    new: int = 0
    duplicate: int = 0
    usable: int = 0
    preview_only: int = 0
    embeddings_created: int = 0
    embeddings_reused: int = 0
    errors: list[str] | None = None
    provider_requests: int = 0
    processed: int = 0
    bounded: bool = False
    status: str = "running"
    total_eligible: int = 0
    last_success_at: str | None = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


def canonical_url(value):
    try:
        parsed = urlparse((value or "").strip())
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return None
        host = parsed.hostname.lower().rstrip(".")
        path = parsed.path or "/"
        return urlunparse((parsed.scheme.lower(), host + (f":{parsed.port}" if parsed.port else ""), path.rstrip("/") or "/", "", parsed.query, ""))
    except (ValueError, UnicodeError):
        return None


def safe_public_url(value):
    url = canonical_url(value)
    if not url:
        return None
    host = urlparse(url).hostname
    try:
        addresses = socket.getaddrinfo(host, None)
    except OSError:
        return url
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return None
    return url


def parse_date(value):
    if not value:
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        from email.utils import parsedate_to_datetime
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def clean_text(value):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def classify_content(description, text):
    if len(text or "") >= 700:
        return "full_text"
    if len(clean_text(description)) >= 40 or len(text or "") >= 40:
        return "feed_text"
    return "preview_only"


def extractive_summary(text, title, limit):
    source = clean_text(text)
    if not source:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", source)
    selected = []
    for sentence in sentences:
        if len(sentence) < 35:
            continue
        selected.append(sentence)
        if len(" ".join(selected)) >= limit:
            break
    return " ".join(selected)[:limit].strip() or source[:limit].strip()


def topic_matches(title, description, supplied):
    haystack = f"{title} {description}".lower()
    selected = [topic for topic in supplied if topic in TOPICS and topic.lower() in haystack]
    return selected or [topic for topic in supplied if topic in TOPICS][:1] or list(TOPICS)[:1]


def _request(session, url, report, deadline, label, timeout=4, params=None,
             budget_db=None, budget_limit=80, max_requests=16, allowed_hosts=None):
    """Bound bytes, redirects, retries, requests and remaining execution time."""
    for attempt in range(2):
        try:
            target = url
            for redirect in range(4):
                remaining = deadline - time.monotonic()
                if remaining <= 0 or report.provider_requests >= max_requests:
                    report.bounded = True
                    return None
                if not safe_public_url(target):
                    raise ValueError("unsafe provider destination")
                if allowed_hosts and urlparse(target).hostname not in allowed_hosts:
                    raise ValueError("unconfigured publisher")
                if budget_db is not None:
                    with transaction(budget_db):
                        if not _api_allowed(budget_db, budget_limit):
                            report.errors.append("thenewsapi: local request budget exhausted")
                            return None
                        _count_api(budget_db)
                report.provider_requests += 1
                response = session.get(target, params=params, timeout=min(timeout, max(0.1, remaining / 2)),
                                       headers={"User-Agent": "MyNews/2.0"}, stream=True,
                                       allow_redirects=False)
                try:
                    if response.status_code in (301, 302, 303, 307, 308):
                        # Never forward API credentials to a redirect destination.
                        if params or redirect == 3:
                            raise ValueError("provider redirect rejected")
                        target = urljoin(target, response.headers.get("Location", ""))
                        continue
                    response.raise_for_status()
                    chunks, size = [], 0
                    for chunk in response.iter_content(chunk_size=16384):
                        size += len(chunk)
                        if size > MAX_RESPONSE_BYTES:
                            raise ValueError("provider response too large")
                        if time.monotonic() >= deadline:
                            report.bounded = True
                            return None
                        chunks.append(chunk)
                    return b"".join(chunks)
                finally:
                    response.close()
        except Exception as exc:
            if attempt == 1:
                # Exception text and request URLs may contain provider credentials.
                report.errors.append(f"{label}: {type(exc).__name__}")
    return None


def _feed_entries(content):
    try:
        import feedparser
        parsed = feedparser.parse(content)
        if not parsed.version:
            raise RuntimeError("invalid RSS/Atom response")
        return parsed.entries
    except ImportError:
        raise RuntimeError("feedparser is not installed")


def _article_from_entry(entry, feed_topics, extractor=None):
    link = safe_public_url(entry.get("link", ""))
    if not link:
        return None
    title = clean_text(entry.get("title", ""))
    if not title:
        return None
    description = clean_text(entry.get("summary", entry.get("description", "")))
    text = clean_text(entry.get("content", [{}])[0].get("value", "") if entry.get("content") else "")
    if not text and len(description) < 40 and extractor:
        text = extractor(link)
    topics = topic_matches(title, description, feed_topics)
    content = text or description
    depth = classify_content(description, text)
    content_hash = hashlib.sha256(f"{title}\n{content}".encode("utf-8")).hexdigest()
    return {
        "id": hashlib.sha256(link.encode("utf-8")).hexdigest()[:24],
        "canonical_url": link, "title": title[:500], "publisher": urlparse(link).netloc,
        "language": entry.get("language"), "image_url": None,
        "published_at": parse_date(entry.get("published") or entry.get("updated")),
        "categories": entry.get("tags", []),
        "topics": [{"topic": topic, "subtopics": TOPICS[topic]} for topic in topics],
        "description": description[:2000], "article_text": content[:20000],
        "brief": extractive_summary(content, title, 420),
        "detail": extractive_summary(content, title, 1800),
        "content_depth": depth, "content_hash": content_hash,
        "story_group_id": hashlib.sha256(re.sub(r"\W+", " ", title.lower()).encode()).hexdigest()[:24],
    }


def extract_permitted_text(url, session=None, report=None, deadline=None):
    """Extract only configured/public article pages; never follow arbitrary user URLs."""
    allowed_hosts = {urlparse(feed).hostname for feed in _configured_feeds()}
    host = urlparse(url).hostname
    if host not in allowed_hosts or not safe_public_url(url):
        return ""
    try:
        import requests
        body = _request(session or requests.Session(), url, report or IngestReport(),
                        deadline or time.monotonic() + 8, "extraction", allowed_hosts=allowed_hosts)
        if not body:
            return ""
        import trafilatura
        return clean_text(trafilatura.extract(body.decode("utf-8", errors="replace")) or "")
    except Exception:
        return ""


def _embedding(text, model):
    result = model.encode(text, normalize_embeddings=True)
    return result.tolist() if hasattr(result, "tolist") else list(result)


def prepare_embedding(article, model, existing_hash=None):
    if existing_hash == article["content_hash"]:
        return None, True
    if model is None:
        return None, False
    selected = " ".join((article["title"], article["brief"], article["detail"][:6000]))
    return _embedding(selected, model), False


def load_model():
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(MODEL_ID, device="cpu"), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {str(exc)[:160]}"


def _configured_feeds():
    raw = os.environ.get("MYNEWS_RSS_FEEDS")
    if not raw:
        return DEFAULT_FEEDS
    try:
        data = json.loads(raw)
        return {str(url): list(topics) for url, topics in data.items()}
    except (TypeError, ValueError, AttributeError):
        return DEFAULT_FEEDS


def _api_allowed(db, limit):
    sql = "SELECT window_start, requests_used FROM news_usage WHERE id = 1"
    if getattr(db, "is_postgres", False):
        sql += " FOR UPDATE"
    row = db.execute(sql).fetchone()
    current = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00:00Z")
    if not row or parse_date(row["window_start"]) != current:
        db.execute("UPDATE news_usage SET window_start = ?, requests_used = 0 WHERE id = 1", (current,))
        return True
    return row["requests_used"] < limit


def _count_api(db):
    db.execute("UPDATE news_usage SET requests_used = requests_used + 1 WHERE id = 1")


def article_counts(db):
    row = db.execute("""SELECT COUNT(*) AS articles,
        COALESCE(SUM(CASE WHEN content_depth != 'preview_only' THEN 1 ELSE 0 END),0) AS eligible,
        MAX(retrieved_at) AS latest_article_ingestion_at FROM articles""").fetchone()
    return dict(row)


def ingestion_diagnostics(db):
    counts = article_counts(db)
    state = db.execute("SELECT * FROM ingestion_state WHERE id=1").fetchone()
    status = state["status"]
    if status == "running" and state["lease_until"] and parse_date(state["lease_until"]) < _stamp():
        status = "interrupted"
    return {"database_connected": True, "article_count": counts["articles"],
            "eligible_article_count": counts["eligible"],
            "latest_article_ingestion_at": counts["latest_article_ingestion_at"],
            "last_ingestion_status": status, "last_ingestion_started_at": state["started_at"],
            "last_ingestion_completed_at": state["completed_at"],
            "last_success_at": state["last_success_at"], "last_report": json.loads(state["report"])}


def _stamp(now=None):
    return (now or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z")


def ingest(db, session=None, feeds=None, api_key=None, model=None, api_limit=80,
           max_seconds=35, max_articles=40, per_source=6,
           max_entries_per_feed=None, fetch_full_text=True):
    """One bounded refresh, independent of reader setup and optional ML packages."""
    if db.in_transaction:
        raise ValueError("Ingestion requires an idle connection to publish its lease.")
    deadline = time.monotonic() + min(35, max(0, max_seconds))
    max_articles, per_source = max(0, min(40, max_articles)), max(0, min(10, per_source))
    if max_entries_per_feed is not None:
        per_source = min(per_source, max(0, max_entries_per_feed))
    token = uuid.uuid4().hex
    with transaction(db):
        claimed = db.execute("""UPDATE ingestion_state SET lease_token=?, lease_until=?,
            started_at=?, status='running' WHERE id=1
            AND (lease_token IS NULL OR lease_until < ?)""",
            (token, _stamp(datetime.now(timezone.utc) + timedelta(seconds=120)), _stamp(), _stamp())).rowcount
    report = IngestReport()
    if not claimed:
        report.status = "busy"
        report.total_eligible = article_counts(db)["eligible"]
        report.last_success_at = ingestion_diagnostics(db)["last_success_at"]
        return report
    own_session = session is None
    import requests
    session = session or requests.Session()
    def exhausted():
        hit = time.monotonic() >= deadline or report.processed >= max_articles
        report.bounded |= hit
        return hit

    def store(article):
        if article:
            report.processed += 1
            with transaction(db):
                sql = "SELECT lease_token FROM ingestion_state WHERE id=1"
                if getattr(db, "is_postgres", False):
                    sql += " FOR UPDATE"
                if db.execute(sql).fetchone()["lease_token"] != token:
                    raise RuntimeError("ingestion lease lost")
                _store_article(db, article, report, model)

    extractions = 0
    def extract(url):
        nonlocal extractions
        if extractions >= 4 or exhausted():
            return ""
        extractions += 1
        return extract_permitted_text(url, session=session, report=report, deadline=deadline)

    try:
        configured = _configured_feeds() if feeds is None else feeds
        sources = [(f"rss:{i+1}", url, topics) for i, (url, topics) in enumerate(list(configured.items())[:4])]
        if api_key:
            sources += [(f"thenewsapi:{endpoint}", f"{API_BASE}/{endpoint}", None) for endpoint in ("top", "all")]
        for label, url, topics in sources:
            if exhausted():
                break
            report.attempted += 1
            is_api = topics is None
            body = _request(session, url, report, deadline, label,
                            params={"api_token": api_key, "limit": per_source} if is_api else None,
                            budget_db=db if is_api else None, budget_limit=api_limit)
            if body is None:
                continue
            try:
                entries = json.loads(body).get("data", []) if is_api else _feed_entries(body)
                if not isinstance(entries, list):
                    raise ValueError("invalid entries")
            except (TypeError, ValueError, RuntimeError, AttributeError):
                report.errors.append(f"{label}: invalid response")
                continue
            report.successful += 1
            for entry in entries[:per_source]:
                if exhausted():
                    break
                try:
                    article = _api_article(entry) if is_api else _article_from_entry(
                        entry, topics, extractor=extract if fetch_full_text else None)
                except (TypeError, ValueError, KeyError, AttributeError):
                    report.errors.append(f"{label}: invalid article")
                    continue
                store(article)
        report.status = "partial" if report.errors and report.successful else ("succeeded" if report.successful else "failed")
    except Exception as exc:
        report.status = "failed"
        report.errors.append(f"ingestion: {type(exc).__name__}")
    finally:
        if own_session:
            session.close()
        with transaction(db):
            report.total_eligible = article_counts(db)["eligible"]
            previous = db.execute("SELECT last_success_at FROM ingestion_state WHERE id=1").fetchone()
            report.last_success_at = _stamp() if report.status in ("succeeded", "partial") else previous["last_success_at"]
            db.execute("""UPDATE ingestion_state SET lease_token=NULL, lease_until=NULL,
                completed_at=?, last_success_at=?, status=?, report=? WHERE id=1 AND lease_token=?""",
                (_stamp(), report.last_success_at, report.status, json.dumps(asdict(report)), token))
    return report


def _api_article(item):
    link = safe_public_url(item.get("url"))
    if not link:
        return None
    title = clean_text(item.get("title"))
    if not title:
        return None
    description = clean_text(item.get("description"))
    text = clean_text(item.get("content"))
    topics = topic_matches(title, description, [x for x in TOPICS])
    content = text or description
    return {
        "id": hashlib.sha256(link.encode()).hexdigest()[:24], "canonical_url": link,
        "title": title[:500], "publisher": clean_text(item.get("source")) or urlparse(link).netloc,
        "language": item.get("language"), "image_url": safe_public_url(item.get("image_url")),
        "published_at": parse_date(item.get("published_at")), "categories": item.get("categories", []),
        "topics": [{"topic": topic, "subtopics": TOPICS[topic]} for topic in topics],
        "description": description[:2000], "article_text": content[:20000],
        "brief": extractive_summary(content, title, 420), "detail": extractive_summary(content, title, 1800),
        "content_depth": classify_content(description, text),
        "content_hash": hashlib.sha256(f"{title}\n{content}".encode()).hexdigest(),
        "story_group_id": hashlib.sha256(re.sub(r"\W+", " ", title.lower()).encode()).hexdigest()[:24],
    }


def _store_article(db, article, report, model):
    existing = db.execute("SELECT content_hash, embedding, embedding_model, content_depth FROM articles WHERE canonical_url = ?", (article["canonical_url"],)).fetchone()
    if article["content_depth"] == "preview_only":
        report.preview_only += 1
    else:
        report.usable += 1
    if existing:
        report.duplicate += 1
        article["embedding"] = json.loads(existing["embedding"]) if existing["embedding"] else None
        if existing["content_hash"] == article["content_hash"] and (existing["embedding"] or model is None):
            report.embeddings_reused += bool(article["embedding"])
            return
    embedding, reused = prepare_embedding(article, model, existing["content_hash"] if existing and existing["embedding"] else None)
    article["embedding"] = embedding if embedding is not None else (json.loads(existing["embedding"]) if existing and existing["embedding"] else None)
    article["embedding_model"] = MODEL_ID if embedding is not None else (existing["embedding_model"] if existing else None)
    # A temporary extraction failure must not downgrade previously usable content.
    if existing and existing["content_depth"] != "preview_only" and article["content_depth"] == "preview_only":
        return
    db.execute("""INSERT INTO articles
        (id, canonical_url, title, publisher, language, image_url, published_at, retrieved_at,
         categories, topics, description, article_text, brief, detail, content_depth,
         content_hash, story_group_id, embedding_model, embedding)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(canonical_url) DO UPDATE SET title=excluded.title, publisher=excluded.publisher,
        language=excluded.language, image_url=excluded.image_url, published_at=excluded.published_at,
        retrieved_at=excluded.retrieved_at, categories=excluded.categories, topics=excluded.topics,
        description=excluded.description, article_text=excluded.article_text, brief=excluded.brief,
        detail=excluded.detail, content_depth=excluded.content_depth, content_hash=excluded.content_hash,
        story_group_id=excluded.story_group_id, embedding_model=excluded.embedding_model, embedding=excluded.embedding""",
        (article["id"], article["canonical_url"], article["title"], article["publisher"], article["language"],
         article["image_url"], article["published_at"], datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
         json.dumps(article["categories"]), json.dumps(article["topics"]), article["description"], article["article_text"],
         article["brief"], article["detail"], article["content_depth"], article["content_hash"], article["story_group_id"],
         article["embedding_model"], json.dumps(article["embedding"]) if article["embedding"] else None))
    if embedding is not None:
        report.embeddings_created += 1
    elif reused:
        report.embeddings_reused += 1
    if not existing:
        report.new += 1


def calibration_articles(db, prefs, limit=6):
    interests = prefs.get("interests", [])
    rows = db.execute("SELECT * FROM articles ORDER BY published_at IS NULL, published_at DESC LIMIT 100").fetchall()
    result = []
    for row in rows:
        topics = json.loads(row["topics"])
        names = {item["topic"] for item in topics}
        if interests and not names.intersection(interests):
            continue
        result.append(row)
        if len(result) == limit:
            break
    return result


def remaining_budget(db):
    row = db.execute("SELECT request_limit - requests_used AS remaining FROM news_usage WHERE id = 1").fetchone()
    return max(0, row["remaining"]) if row else 0


def main():
    parser = argparse.ArgumentParser(description="Fetch and prepare the shared MyNews article pool.")
    parser.add_argument("--database", default="instance/mynews.sqlite3")
    args = parser.parse_args()
    import sqlite3
    from storage import init_db
    class App:
        config = {"DATABASE": args.database}
    import flask
    app = flask.Flask("news-cli", instance_path=os.path.dirname(os.path.abspath(args.database)))
    app.config["DATABASE"] = args.database
    with app.app_context():
        init_db()
        db = flask.g.get("db")
        from storage import get_db
        db = get_db()
        model, model_error = load_model()
        report = ingest(db, api_key=os.environ.get("THENEWSAPI_KEY"), model=model)
        print(f"sources attempted: {report.attempted}; successful: {report.successful}")
        print(f"new: {report.new}; duplicates: {report.duplicate}; usable: {report.usable}; preview-only: {report.preview_only}")
        print(f"embeddings created: {report.embeddings_created}; reused: {report.embeddings_reused}; remaining API allowance: {remaining_budget(db)}")
        if model_error:
            print(f"embedding status: unavailable ({model_error}); no neural embeddings created")
        for error in report.errors:
            print(f"error: {error}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
