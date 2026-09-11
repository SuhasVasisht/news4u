"""Published editions, not collection timestamps, determine whether a story is new."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, timedelta
from rapidfuzz import fuzz
from news_collector.utils import canonicalize_url


def load_history(root, edition_date):
    directory = root / "data/cloudflare-published/editions"
    history = []
    for path in sorted(directory.glob("*/edition.json")):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(-r[a-f0-9]{12})?", path.parent.name) or path.parent.name[:10] >= edition_date:
            continue
        edition = json.loads(path.read_text())
        if edition.get("date") != path.parent.name[:10] or not edition.get("editorialReviewedAt"):
            raise ValueError("Invalid published history; cannot establish novelty")
        for story in edition["stories"]:
            entry = {"date": edition["date"], "id": story["id"], "title": story["title"],
                     "url": story["url"], "coverage": story.get("coverage", [])}
            if story.get("eventKey"):
                entry["eventKey"] = story["eventKey"]
            history.append(entry)
    return history


def history_hash(history):
    return hashlib.sha256(json.dumps(history, sort_keys=True).encode()).hexdigest()


def title_words(title):
    return " ".join(re.findall(r"[a-z0-9]+", title.lower()))


def prior_match(url, title, history, edition_date):
    canonical = canonicalize_url(url)
    normalized = title_words(title)
    for story in history:
        accounts = [{"url": story["url"], "title": story["title"]}, *story["coverage"]]
        if any(canonical == canonicalize_url(a["url"]) for a in accounts):
            return {"date": story["date"], "id": story["id"], "title": story["title"], "match": "published_url"}
        if date.fromisoformat(story["date"]) < date.fromisoformat(edition_date) - timedelta(days=7):
            continue
        for account in accounts:
            old = title_words(account["title"])
            shared = set(normalized.split()) & set(old.split())
            # Differing dates/numbers can indicate a genuinely new periodic release.
            same_numbers = re.findall(r"\b\d+\b", normalized) == re.findall(r"\b\d+\b", old)
            if normalized == old or (len(shared) >= 6 and same_numbers and fuzz.ratio(normalized, old) >= 90):
                return {"date": story["date"], "id": story["id"], "title": story["title"], "match": "published_title"}
    return None
