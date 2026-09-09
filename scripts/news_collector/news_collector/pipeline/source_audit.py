"""Explain every configured source's path from ingestion to the selected edition."""
from collections import Counter
from datetime import timedelta
from news_collector.pipeline.editorial import exclusion
from news_collector.utils import parse_datetime


def audit_sources(config, repository, rows, review, snapshot, now, collection=None):
    results = []
    decisions = review.get("decisions", {})
    collected_at = parse_datetime((collection or {}).get("collected_at"))
    runs = {r["collector"]: r for r in (collection or {}).get("sources", [])} if collected_at and now - collected_at < timedelta(hours=24) else {}
    for source in config["collectors"]:
        name = source["name"]
        state = repository.get_source_state(name)
        stored = [r for r in rows if r["source"] == name]
        eligible = [r for r in stored if not exclusion(r, now)]
        urls = {r["canonical_url"] for r in stored}
        packets = [p for p in review.get("packets", []) if p["source"] == name or p["url"] in urls]
        reviewed = [p for p in packets if decisions.get(p["id"], {}).get("quality", 0) > 0]
        published = [s for s in snapshot.get("stories", []) if name in s["collectors"]]
        reasons = Counter(e["reason"] for e in review.get("excluded", []) if e.get("source") == name)
        states = Counter(decisions.get(p["id"], {}).get("decision", "pending") for p in packets)
        dates = [parse_datetime(r.get("published_at")) for r in stored]
        dates = [d for d in dates if d]
        enabled = source.get("enabled", True)
        checked = parse_datetime(state.get("last_checked_at"))
        status = state.get("last_status", "unverified") if enabled else "disabled"
        if enabled and (not checked or now - checked > timedelta(hours=24)):
            status = "unverified"
        collected = runs.get(name, {}).get("collected", state.get("last_collected", 0))
        if checked and collected_at and checked > collected_at:
            collected = state.get("last_collected", collected)
        results.append({"name": name, "status": status, "count": len(stored),
                        "latest": max(dates).isoformat() if dates else None,
                        "reason": state.get("last_reason") if enabled else "Disabled in configuration",
                        "checkedAt": state.get("last_checked_at"),
                        "collected": collected, "eligible": len(eligible),
                        "candidates": len(packets), "reviewed": len(reviewed),
                        "published": len(published), "decisions": dict(states),
                        "exclusions": dict(reasons),
                        "publishedTitles": [s["title"] for s in published]})
    return results
