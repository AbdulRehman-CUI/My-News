"""Persisted Phase 3 recommendations and per-reader LinUCB learning."""
import json
import math
import uuid
from datetime import datetime, timezone

import numpy as np

from news import MODEL_ID
from taxonomy import TOPICS

FEATURE_VERSION = "features-v1"
POLICY_VERSION = "linucb-v1"
FEATURE_NAMES = (
    "explicit_match", "learned_topic", "recent_topic", "semantic_match",
    "freshness", "significance", "diversity", "exploration",
)
REWARDS = {
    "more": 1.0, "less": -1.0, "save": 0.6, "active_read": 0.3,
    "source_open": 0.1, "skip": -0.1,
}
ADJACENT_TOPICS = {
    "Technology": {"Science", "Education", "Gaming"},
    "Science": {"Technology", "Health", "Environment", "Education"},
    "Business": {"Technology", "Politics", "Education"},
    "Sports": {"Health", "Entertainment"},
    "Entertainment": {"Culture", "Gaming", "Sports"},
    "Politics": {"Business", "Environment", "Education"},
    "Health": {"Science", "Sports", "Education"},
    "Education": {"Science", "Technology", "Business"},
    "Environment": {"Science", "Politics", "Travel"},
    "Culture": {"Entertainment", "Travel", "Education"},
    "Travel": {"Culture", "Environment", "Business"},
    "Gaming": {"Technology", "Entertainment"},
}


def _json(value):
    return json.dumps(value, separators=(",", ":"))


def _now():
    return datetime.now(timezone.utc)


def _default_state(prefs):
    explicit = list(prefs.get("interests", []))
    return {
        "topic_weights": {topic: 0.0 for topic in TOPICS},
        "recent_weights": {topic: 0.0 for topic in TOPICS},
        "anchors": [],
        "evidence": {topic: 0 for topic in TOPICS},
        "exclusions": [],
        "policy_a": (np.eye(len(FEATURE_NAMES)) * 1.0).tolist(),
        "policy_b": [0.0] * len(FEATURE_NAMES),
        "policy_version": POLICY_VERSION,
        "generation": 1,
        "explicit": explicit,
    }


def ensure_state(db, reader_id, prefs):
    row = db.execute("SELECT * FROM reader_learning WHERE reader_id = ?", (reader_id,)).fetchone()
    if row:
        state = {key: row[key] for key in ("topic_weights", "recent_weights", "anchors", "evidence", "exclusions", "policy_a", "policy_b")}
        for key in ("topic_weights", "recent_weights", "anchors", "evidence", "exclusions", "policy_a", "policy_b"):
            state[key] = json.loads(state[key])
        state.update(policy_version=row["policy_version"], generation=row["generation"])
        state["explicit"] = list(prefs.get("interests", []))
        return state
    state = _default_state(prefs)
    calibration_ids = prefs.get("calibration", [])
    for article_id in calibration_ids:
        article = db.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        if article:
            for topic in _topics(article):
                state["topic_weights"][topic] = 0.2
                state["recent_weights"][topic] = 0.2
            embedding = _embedding(article)
            if embedding:
                state["anchors"].append(embedding)
    state["anchors"] = state["anchors"][-5:]
    _save_state(db, reader_id, state)
    db.commit()
    return state


def _save_state(db, reader_id, state):
    db.execute("""INSERT INTO reader_learning
        (reader_id, topic_weights, recent_weights, anchors, evidence, exclusions, policy_a, policy_b, policy_version, generation)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(reader_id) DO UPDATE SET topic_weights=excluded.topic_weights,
        recent_weights=excluded.recent_weights, anchors=excluded.anchors, evidence=excluded.evidence,
        exclusions=excluded.exclusions, policy_a=excluded.policy_a, policy_b=excluded.policy_b,
        policy_version=excluded.policy_version, generation=excluded.generation,
        updated_at=CURRENT_TIMESTAMP""",
        (reader_id, _json(state["topic_weights"]), _json(state["recent_weights"]),
         _json(state["anchors"]), _json(state["evidence"]), _json(state["exclusions"]),
         _json(state["policy_a"]), _json(state["policy_b"]), state["policy_version"], state["generation"]))


def _topics(row):
    return {item["topic"] for item in json.loads(row["topics"] or "[]") if item.get("topic") in TOPICS}


def _embedding(row):
    return json.loads(row["embedding"]) if row["embedding"] else None


def _cosine(left, right):
    if not left or not right:
        return 0.0
    left, right = np.asarray(left), np.asarray(right)
    denominator = np.linalg.norm(left) * np.linalg.norm(right)
    return max(0.0, float(np.dot(left, right) / denominator)) if denominator else 0.0


def _freshness(row):
    if not row["published_at"]:
        return 0.2
    try:
        age = max(0.0, (_now() - datetime.fromisoformat(row["published_at"].replace("Z", "+00:00"))).total_seconds())
        return max(0.0, 1.0 - age / (7 * 86400))
    except ValueError:
        return 0.2


def _feature_vector(row, prefs, state, group_counts, adjacent=False):
    topics = _topics(row)
    explicit = set(prefs.get("interests", []))
    learned = state["topic_weights"]
    recent = state["recent_weights"]
    explicit_match = 1.0 if topics & explicit else 0.0
    learned_match = max((learned.get(topic, 0.0) for topic in topics), default=0.0)
    recent_match = max((recent.get(topic, 0.0) for topic in topics), default=0.0)
    anchor_match = max((_cosine(_embedding(row), anchor) for anchor in state["anchors"]), default=0.0)
    significance = min(1.0, (group_counts.get(row["story_group_id"], 1) - 1) / 3)
    diversity = 1.0 / max(1, group_counts.get(row["story_group_id"], 1))
    exploration = 1.0 if adjacent else 0.0
    return np.asarray([
        explicit_match, max(-1.0, min(1.0, learned_match)),
        max(-1.0, min(1.0, recent_match)), anchor_match, _freshness(row),
        significance, diversity, exploration,
    ], dtype=float)


def _reason(features, topics, adjacent):
    labels = dict(zip(FEATURE_NAMES, features))
    evidence = []
    if labels["explicit_match"]:
        evidence.append("matches selected interests")
    if labels["learned_topic"] > 0.05:
        evidence.append("matches learned reading signals")
    if labels["recent_topic"] > 0.05:
        evidence.append("matches recent interest")
    if labels["semantic_match"] > 0.05:
        evidence.append("is semantically close to saved signals")
    if labels["significance"] > 0:
        evidence.append("has coverage from multiple publishers")
    if adjacent:
        evidence.append("bounded adjacent-topic exploration")
    if not evidence:
        evidence.append("balanced general-interest candidate")
    return "; ".join(evidence) + f" ({', '.join(sorted(topics))})"


def recommend(db, reader_id, prefs, surface="discover", limit=10):
    state = ensure_state(db, reader_id, prefs)
    state["recent_weights"] = {
        topic: max(-1.0, min(1.0, weight * 0.98))
        for topic, weight in state["recent_weights"].items()
    }
    rows = db.execute("SELECT * FROM articles WHERE content_depth != 'preview_only' OR content_depth IS NULL ORDER BY published_at IS NULL, published_at DESC").fetchall()
    group_counts = {}
    for row in rows:
        group_counts[row["story_group_id"]] = group_counts.get(row["story_group_id"], 0) + 1
    explicit = set(prefs.get("interests", []))
    exclusions = set(state["exclusions"])
    candidates = []
    seen_groups = set()
    for row in rows:
        topics = _topics(row)
        if topics & exclusions or row["story_group_id"] in seen_groups:
            continue
        direct = bool(topics & explicit)
        adjacent = bool(explicit) and not direct and any(
            candidate_topic in ADJACENT_TOPICS.get(selected, set())
            for selected in explicit for candidate_topic in topics
        )
        if explicit and not direct and not adjacent:
            continue
        features = _feature_vector(row, prefs, state, group_counts, adjacent)
        A = np.asarray(state["policy_a"], dtype=float)
        b = np.asarray(state["policy_b"], dtype=float)
        theta = np.linalg.solve(A, b)
        uncertainty = math.sqrt(max(0.0, float(features @ np.linalg.solve(A, features))))
        score = float(theta @ features + 0.35 * uncertainty)
        candidates.append((score, row, features, adjacent))
        seen_groups.add(row["story_group_id"])
    candidates.sort(key=lambda value: (-value[0], value[1]["id"]))
    selected = candidates[:limit]
    if explicit:
        adjacent_candidate = next((item for item in candidates[limit:] if item[3]), None)
        if adjacent_candidate and len(selected) >= 10:
            selected[-1] = adjacent_candidate
    result = []
    for position, (score, row, features, adjacent) in enumerate(selected, 1):
        recommendation_id = uuid.uuid4().hex
        result.append({
            "id": recommendation_id, "article": row, "score": score,
            "features": features.tolist(), "reason": _reason(features, _topics(row), adjacent),
            "position": position, "policy_version": FEATURE_VERSION + "/" + state["policy_version"],
            "generation": state["generation"],
        })
        db.execute("""INSERT INTO recommendations
            (id, reader_id, article_id, surface, position, features, score, reason, policy_version, generation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (recommendation_id, reader_id, row["id"], surface, position, _json(features.tolist()),
             score, result[-1]["reason"], result[-1]["policy_version"], state["generation"]))
    db.commit()
    _save_state(db, reader_id, state)
    db.commit()
    return result


def mark_visible(db, reader_id, recommendation_id):
    db.execute("UPDATE recommendations SET visible=1 WHERE id=? AND reader_id=?", (recommendation_id, reader_id))
    db.commit()


def _effective_reward(db, recommendation_id):
    events = db.execute(
        "SELECT event_type FROM feedback_events WHERE recommendation_id=? ORDER BY created_at DESC, event_id DESC",
        (recommendation_id,),
    ).fetchall()
    types = {event["event_type"] for event in events}
    for event in events:
        if event["event_type"] in ("more", "less"):
            return REWARDS[event["event_type"]]
    for event in events:
        if event["event_type"] in ("save", "unsave"):
            if event["event_type"] == "save":
                return REWARDS["save"]
            break
    for event_type in ("active_read", "source_open", "skip"):
        if event_type in types:
            return REWARDS[event_type]
    return None


def _apply_profile_delta(state, article, delta):
    topics = _topics(article)
    for topic in topics:
        state["topic_weights"][topic] = max(-1.0, min(1.0, state["topic_weights"].get(topic, 0.0) + delta))
        state["recent_weights"][topic] = max(-1.0, min(1.0, state["recent_weights"].get(topic, 0.0) + delta))
        state["evidence"][topic] = state["evidence"].get(topic, 0) + (1 if delta > 0 else 0)
    embedding = _embedding(article)
    if delta > 0 and embedding:
        state["anchors"] = (state["anchors"] + [embedding])[-5:]


def record_feedback(db, reader_id, recommendation_id, event_id, event_type):
    if event_type not in REWARDS and event_type not in ("save", "unsave"):
        raise ValueError("Unsupported feedback event.")
    rec = db.execute("SELECT * FROM recommendations WHERE id=? AND reader_id=?", (recommendation_id, reader_id)).fetchone()
    if rec is None:
        raise ValueError("That recommendation does not belong to this reader.")
    inserted = db.execute("""INSERT INTO feedback_events
        (event_id, reader_id, recommendation_id, event_type) VALUES (?, ?, ?, ?)
        ON CONFLICT(event_id) DO NOTHING""",
        (event_id, reader_id, recommendation_id, event_type)).rowcount
    if not inserted:
        return False
    state = ensure_state(db, reader_id, {})
    new_reward = _effective_reward(db, recommendation_id)
    old_reward = rec["effective_reward"]
    delta = (new_reward or 0.0) - (old_reward or 0.0)
    if delta:
        features = np.asarray(json.loads(rec["features"]), dtype=float)
        state["policy_b"] = (np.asarray(state["policy_b"], dtype=float) + delta * features).tolist()
        _apply_profile_delta(state, db.execute("SELECT * FROM articles WHERE id=?", (rec["article_id"],)).fetchone(), delta)
    if not rec["covariance_applied"]:
        features = np.asarray(json.loads(rec["features"]), dtype=float)
        state["policy_a"] = (np.asarray(state["policy_a"], dtype=float) + np.outer(features, features)).tolist()
        db.execute("UPDATE recommendations SET covariance_applied=1 WHERE id=?", (recommendation_id,))
    db.execute("UPDATE recommendations SET effective_reward=? WHERE id=?", (new_reward, recommendation_id))
    _save_state(db, reader_id, state)
    db.commit()
    return True


def set_exclusions(db, reader_id, exclusions):
    state = ensure_state(db, reader_id, {})
    state["exclusions"] = sorted(set(exclusions) & set(TOPICS))
    _save_state(db, reader_id, state)
    db.commit()


def reset_learning(db, reader_id):
    state = ensure_state(db, reader_id, {})
    state.update(topic_weights={topic: 0.0 for topic in TOPICS},
                 recent_weights={topic: 0.0 for topic in TOPICS},
                 anchors=[], evidence={topic: 0 for topic in TOPICS},
                 policy_a=(np.eye(len(FEATURE_NAMES))).tolist(), policy_b=[0.0] * len(FEATURE_NAMES),
                 generation=state["generation"] + 1)
    _save_state(db, reader_id, state)
    db.commit()


def learning_summary(db, reader_id, prefs):
    state = ensure_state(db, reader_id, prefs)
    return state
