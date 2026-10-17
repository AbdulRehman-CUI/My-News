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
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urljoin, urlparse, urlunparse

from taxonomy import TOPICS

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


def _request(session, url, report, timeout=10, params=None, budget_db=None, budget_limit=80):
    for attempt in range(2):
        if budget_db is not None:
            if not _api_allowed(budget_db, budget_limit):
                report.errors.append("thenewsapi: local request budget exhausted")
                return None
            _count_api(budget_db)
        report.attempted += 1
        try:
            response = session.get(url, params=params, timeout=timeout, headers={"User-Agent": "MyNews/2.0"})
            if response.status_code == 429:
                raise RuntimeError("provider rate limit")
            response.raise_for_status()
            report.successful += 1
            return response
        except Exception as exc:
            if attempt == 1:
                report.errors.append(f"{urlparse(url).netloc}: {type(exc).__name__}")
    return None


def _feed_entries(content):
    try:
        import feedparser
        return feedparser.parse(content).entries
    except ImportError:
        raise RuntimeError("feedparser is not installed")


def _article_from_entry(entry, feed_topics):
    link = safe_public_url(entry.get("link", ""))
    if not link:
        return None
    title = clean_text(entry.get("title", ""))
    description = clean_text(entry.get("summary", entry.get("description", "")))
    text = clean_text(entry.get("content", [{}])[0].get("value", "") if entry.get("content") else "")
    if not text and link:
        text = extract_permitted_text(link)
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


def extract_permitted_text(url, session=None):
    """Extract only configured/public article pages; never follow arbitrary user URLs."""
    allowed_hosts = {urlparse(feed).hostname for feed in _configured_feeds()}
    host = urlparse(url).hostname
    if host not in allowed_hosts:
        return ""
    try:
        import requests
        response = (session or requests.Session()).get(
            url, timeout=10, headers={"User-Agent": "MyNews/2.0"}, stream=True
        )
        response.raise_for_status()
        body = response.raw.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            return ""
        import trafilatura
        return clean_text(trafilatura.extract(body.decode(response.encoding or "utf-8", errors="replace")) or "")
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
    except (TypeError, ValueError):
        return DEFAULT_FEEDS


def _api_allowed(db, limit):
    row = db.execute("SELECT window_start, requests_used FROM news_usage WHERE id = 1").fetchone()
    current = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00:00Z")
    if not row or row["window_start"] != current:
        db.execute("UPDATE news_usage SET window_start = ?, requests_used = 0 WHERE id = 1", (current,))
        return True
    return row["requests_used"] < limit


def _count_api(db):
    db.execute("UPDATE news_usage SET requests_used = requests_used + 1 WHERE id = 1")


def ingest(db, session=None, feeds=None, api_key=None, model=None, api_limit=80):
    import requests
    session = session or requests.Session()
    report = IngestReport()
    feeds = feeds or _configured_feeds()
    for url, topics in feeds.items():
        response = _request(session, url, report)
        if response is None:
            continue
        try:
            entries = _feed_entries(response.content)
        except RuntimeError as exc:
            report.errors.append(str(exc))
            continue
        for entry in entries[:20]:
            article = _article_from_entry(entry, topics)
            if article:
                _store_article(db, article, report, model)
    if api_key and _api_allowed(db, api_limit):
        for endpoint in ("top", "all"):
            response = _request(session, f"{API_BASE}/{endpoint}", report,
                                params={"api_token": api_key}, budget_db=db, budget_limit=api_limit)
            if response is None:
                continue
            try:
                payload = response.json()
                for item in payload.get("data", []):
                    article = _api_article(item)
                    if article:
                        _store_article(db, article, report, model)
            except (ValueError, TypeError):
                report.errors.append("thenewsapi: invalid response")
    db.commit()
    return report


def _api_article(item):
    link = safe_public_url(item.get("url"))
    if not link:
        return None
    title = clean_text(item.get("title"))
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
    existing = db.execute("SELECT content_hash, embedding FROM articles WHERE canonical_url = ?", (article["canonical_url"],)).fetchone()
    if existing:
        report.duplicate += 1
        article["embedding"] = json.loads(existing["embedding"]) if existing["embedding"] else None
        if existing["content_hash"] == article["content_hash"]:
            report.embeddings_reused += bool(article["embedding"])
            return
    embedding, reused = prepare_embedding(article, model, existing["content_hash"] if existing else None)
    article["embedding"] = embedding if embedding is not None else (json.loads(existing["embedding"]) if existing and existing["embedding"] else None)
    article["embedding_model"] = MODEL_ID if article["embedding"] else None
    db.execute("""INSERT INTO articles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
    if article["content_depth"] == "preview_only":
        report.preview_only += 1
    else:
        report.usable += 1
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
    row = db.execute("SELECT request_limit - requests_used FROM news_usage WHERE id = 1").fetchone()
    return max(0, row[0]) if row else 0


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
