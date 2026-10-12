"""Bound model working context while keeping authoritative audit inputs intact."""
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import math
import re


def _subjects(value):
    if isinstance(value, list):
        return " ".join(_subjects(item) for item in value)
    if not isinstance(value, dict):
        return str(value) if isinstance(value, str) else ""
    prose = {"title", "headline", "summary", "points", "sections", "heading", "body",
             "caveats", "event", "finding", "text"}
    containers = {"packets", "decisions", "shortlist", "selectedStories", "checklist",
                  "events", "sources", "chunks"}
    return " ".join(_subjects(item) for key, item in value.items() if key in prose | containers)


def bounded_history(history, subjects, cutoff, budget=350_000):
    """Retrieve topical older prose and recent context, never cut an entry mid-text.

    Exact archived-URL rejection still runs against the full archive before review.
    This retrieval is a model input view, not the history used for hashes/validation.
    """
    unique = {json.dumps(entry, sort_keys=True, ensure_ascii=False): entry for entry in history}
    entries = list(unique.values())
    stop = {"the", "and", "for", "with", "from", "that", "this", "were", "said", "will",
            "have", "has", "was", "are", "but", "not", "its", "into", "their", "more"}
    def words(text):
        return set(re.findall(r"[\w-]{3,}", text.lower())) - stop
    query = words(subjects)
    tokens = [words(_subjects(entry)) for entry in entries]
    frequency = Counter(word for group in tokens for word in group)
    ranked = []
    for entry, group in zip(entries, tokens):
        overlap = query & group
        score = sum(math.log1p(len(entries) / (1 + frequency[word])) for word in overlap)
        score += 2 * len(query & words(entry.get("title", "")))
        if overlap:
            ranked.append((score, entry))
    ranked.sort(key=lambda item: item[0], reverse=True)
    selected, selected_keys, size = [], set(), 0
    def append(entry, identity):
        nonlocal size
        length = len(json.dumps(entry, ensure_ascii=False)) + 2
        if size + length <= budget:
            selected.append(entry)
            selected_keys.add(identity)
            size += length
    # Reserve room for recent summaries as well as the strongest topical matches.
    for _, entry in ranked:
        identity = json.dumps(entry, sort_keys=True, ensure_ascii=False)
        if size < budget * .65:
            append(entry, identity)
    brief_fields = {"id", "date", "title", "url", "eventKey", "summary", "points", "coverage"}
    recent = (cutoff - timedelta(days=7)).date().isoformat()
    for entry in sorted(entries, key=lambda item: item.get("date", ""), reverse=True):
        identity = json.dumps(entry, sort_keys=True, ensure_ascii=False)
        if identity not in selected_keys and entry.get("date", "") >= recent:
            append({key: value for key, value in entry.items() if key in brief_fields}, identity)
    return selected


def bound_context(payload):
    if not isinstance(payload, dict):
        return payload
    result = dict(payload)
    keys = [key for key in ("history", "previouslyPublished", "publicationHistory")
            if isinstance(payload.get(key), list)]
    if not keys:
        return result
    cutoff = datetime.fromisoformat(payload["cutoff"]) if payload.get("cutoff") else datetime.now(timezone.utc)
    scope = {}
    for key in keys:
        result[key] = bounded_history(payload[key], _subjects(payload), cutoff, budget=350_000 // len(keys))
        scope[key] = {"archiveEntries": len(payload[key]), "retrievedEntries": len(result[key])}
    result["history_context_scope"] = scope
    return result
