"""Build a public, credential-free snapshot and a separate ingestion audit."""
from __future__ import annotations

import hashlib
import argparse
import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from selectolax.parser import HTMLParser
from rapidfuzz import fuzz

from news_collector.pipeline.dedupe import cluster_items
from news_collector.pipeline.publishers import publisher
from news_collector.pipeline.publication_dates import needs_publisher_date
from news_collector.pipeline.editorial import Decision, exclusion, validate_decisions, ReviewBatch, source_hash, LONGFORM
from news_collector.runtime import build_runtime
from news_collector.utils import parse_datetime, normalize_title

SECTORS = {"tech": "Technology", "finance": "Markets", "world": "World", "politics": "Policy"}


def plain(value: str | None, limit: int = 550) -> str:
    text = " ".join(HTMLParser(value or "").text(separator=" ").split())
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "..."


def public_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    return value if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username else None




def build_snapshot(rows: list[dict], now: datetime, timezone_name: str = "America/Los_Angeles") -> tuple[dict, dict]:
    cutoff = now - timedelta(days=7)
    fresh, excluded = [], Counter()
    for row in rows:
        published = parse_datetime(row.get("published_at"))
        if not published:
            excluded["undated"] += 1
        elif published > now + timedelta(minutes=5):
            excluded["future"] += 1
        elif published < cutoff:
            excluded["older_than_7_days"] += 1
        elif not public_url(row.get("canonical_url")) or not plain(row.get("title")):
            excluded["invalid"] += 1
        elif row["source"] == "alphavantage_movers":
            excluded["market_snapshot_not_article"] += 1
        else:
            fresh.append(row)
    clusters = cluster_items(fresh)
    lookup = {row["id"]: row for row in fresh}
    stories = []
    for cluster in clusters:
        members = [lookup[item_id] for item_id in cluster.item_ids]
        best = max(members, key=lambda row: (row["importance_score"], bool(row.get("summary"))))
        url = best["canonical_url"]
        summary = plain(best.get("summary"))
        if summary.lower().startswith(("hacker news comments:", "support the ")):
            summary = ""
        priority = float(best["importance_score"]) * 10
        if best["source"] == "producthunt":
            priority -= 2
        if re.search(r"here.s how much|invested.*years ago|average recommendation|price target|stock rating", best["title"], re.I):
            priority -= 2
        if not summary:
            priority -= 1
        if re.search(r"\(20[0-2][0-5]\)", best["title"]):
            priority -= 2
        coverage = {r["canonical_url"]: {"title": plain(r["title"], 500), "url": r["canonical_url"], "publisher": publisher(r["canonical_url"])} for r in members}
        stories.append({
            "id": hashlib.sha256(min(coverage).encode()).hexdigest()[:20],
            "title": plain(best["title"], 500), "summary": summary,
            "url": url, "image": public_url(best.get("image_url")) if best.get("image_url") != url and not (best.get("image_url") or "").endswith(".html") else None,
            "publishedAt": parse_datetime(best["published_at"]).isoformat(),
            "publisher": publisher(url), "sector": SECTORS.get(best["category"], "Other"),
            "score": round(max(0, min(10, priority)), 1),
            "collectors": sorted(set(r["source"] for r in members)), "coverage": list(coverage.values()),
        })
    stories.sort(key=lambda s: (s["score"], s["publishedAt"]), reverse=True)
    # Retain a finite, publisher-diverse daily edition without losing the audit denominator.
    selected, counts = [], Counter()
    for story in stories:
        bucket = (story["sector"], story["publisher"])
        if counts[bucket] >= (3 if story["publisher"] == "producthunt.com" else 8) or sum(s["sector"] == story["sector"] for s in selected) >= 30:
            continue
        selected.append(story)
        counts[bucket] += 1
    near_pairs = []
    for i, a in enumerate(stories):
        for b in stories[i + 1:]:
            score = fuzz.ratio(normalize_title(a["title"]), normalize_title(b["title"]))
            if score >= 70:
                near_pairs.append({"similarity": round(score, 1), "a": a["title"], "b": b["title"], "urls": [a["url"], b["url"]]})
    date = now.astimezone(ZoneInfo(timezone_name)).date().isoformat()
    snapshot = {"date": date, "generatedAt": now.isoformat(), "timezone": timezone_name, "windowHours": 48, "stories": selected, "sources": []}
    audit = {"generated_at": now.isoformat(), "edition_date": date, "normalized_total": len(rows), "excluded": dict(excluded), "eligible_7day_rows": len(fresh), "unique_article_urls": len(set(r["canonical_url"] for r in fresh)), "story_clusters": len(stories), "collapsed_rows": len(fresh) - len(stories), "selected_stories": len(selected), "selected_today_published": sum(parse_datetime(s["publishedAt"]).astimezone(ZoneInfo(timezone_name)).date().isoformat() == date for s in selected), "selected_with_images": sum(bool(s["image"]) for s in selected), "possible_remaining_pairs_not_confirmed_duplicates": sorted(near_pairs, key=lambda p: p["similarity"], reverse=True)[:40], "multi_article_clusters": [{"title": s["title"], "reports": s["coverage"], "collectors": s["collectors"]} for s in stories if len(s["coverage"]) > 1]}
    return snapshot, audit


def assemble_reviewed(rows, review, now, timezone_name, history=None, discoveries=None, audited_selection=False, edition_date=None):
    from news_collector.pipeline.publication_history import prior_match, history_hash
    if history is not None and review.get("historyHash") != history_hash(history):
        raise RuntimeError("Publication history changed; repeat editorial review")
    reviewed_at = parse_datetime(review.get("generatedAt"))
    if not reviewed_at or now - reviewed_at > timedelta(hours=24) or reviewed_at > now + timedelta(minutes=5):
        raise RuntimeError("Current editorial review required before publishing")
    edition_date = edition_date or now.astimezone(ZoneInfo(timezone_name)).date().isoformat()
    packets = {p["id"]: p for p in review["packets"]}
    decisions = {key: Decision.model_validate(value) for key, value in review["decisions"].items()}
    if any(key != decision.id for key, decision in decisions.items()):
        raise ValueError("Editorial decision key does not match its ID")
    # Duplicate references belong to the complete review, not a single-story slice.
    validate_decisions(ReviewBatch(decisions=list(decisions.values())), review["packets"])
    by_url = {}
    for row in rows:
        by_url.setdefault(row["canonical_url"], []).append(row)
    stories, rejected = [], []
    selection_reasons = {item["id"]: item["reason"] for item in review.get("selection", {}).get("excluded", [])}
    for key, decision in decisions.items():
        packet = packets[key]
        if decision.decision != "admit" or key not in review.get("selection", {}).get("selected_ids", review["decisions"]):
            rejected.append({"id": key, "reason": selection_reasons.get(key, decision.reason)})
            continue
        matching = [row for row in by_url.get(packet["url"], []) if row["source"] == packet["source"]]
        row = next((r for r in matching if not packet.get("inputHash") or source_hash(r) == packet["inputHash"]), None)
        if not row:
            raise RuntimeError("Source changed since editorial review; review again before publication")
        if row and needs_publisher_date(row) and packet.get("publicationDateBasis") != "publisher_metadata":
            raise RuntimeError("Newsletter-linked article requires publisher date verification; repeat editorial review")
        if not row or exclusion({**row, "published_at": packet["publishedAt"]}, now):
            rejected.append({"id": key, "reason": selection_reasons.get(key, decision.reason)})
            continue
        prior = prior_match(packet["url"], packet["title"], history or [], edition_date)
        if prior:
            raise RuntimeError(f"Previously published story selected again: {key} from {prior['date']}")
        sector = "Listening room" if decision.kind == "podcast" else decision.sector or packet.get("sector") or SECTORS.get(packet["category"], "Other")
        if decision.kind == "analysis" and now - parse_datetime(row["published_at"]) > timedelta(hours=48):
            sector = "Reading room"
        stories.append({
            "id": key, "title": decision.headline, "summary": decision.summary,
            "sector": sector, "url": packet["url"], "image": public_url(row.get("image_url")),
            "publishedAt": packet["publishedAt"], "score": round((decision.quality * .7 + decision.importance * .3) / 10, 1),
            "publisher": "Theo - t3.gg" if row["source"] == "theo_video" else publisher(packet["url"]),
            "collectors": sorted({r["source"] for r in matching} | {r["source"] for r in discoveries or [] if r["canonical_url"] == packet["url"]}),
            "coverage": [{"title": plain(row["title"], 500), "publisher": publisher(packet["url"]), "url": packet["url"]}],
            "kind": decision.kind, "points": decision.points,
            "sections": [{"heading": section.heading, "body": section.body} for section in decision.sections],
            "caveats": decision.caveats, "contentBasis": packet["basis"],
            "audioUrl": packet["audio"], "duration": packet["duration"],
            "quality": decision.quality, "importance": decision.importance, "editorialReason": decision.reason,
            "longform": row["source"] in LONGFORM,
        })
    # Podcast notes have a small dedicated allowance, not a breaking-news freshness contest.
    order = {key: i for i, key in enumerate(review.get("selection", {}).get("selected_ids", []))}
    stories.sort(key=lambda s: order.get(s["id"], 999))
    selected, counts = [], Counter()
    for story in stories:
        if counts[story["publisher"]] >= 4 or len(selected) >= 28:
            if audited_selection:
                raise RuntimeError("Audited selection exceeds edition or publisher limits; repeat final selection")
            continue
        # A verified event-level desk decision must not be silently rewritten by title similarity.
        duplicate = None if audited_selection else next((s for s in selected if fuzz.token_set_ratio(s["title"], story["title"]) >= 85), None)
        if duplicate:
            duplicate["coverage"].extend(story["coverage"])
            continue
        selected.append(story)
        counts[story["publisher"]] += 1
    for rank, story in enumerate(selected):
        story["editorialRank"] = rank
    if not selected:
        raise RuntimeError("Editorial gate admitted no stories; previous edition retained")
    snapshot = {"date": edition_date,
                "generatedAt": now.isoformat(), "timezone": timezone_name, "windowHours": 48,
                "stories": selected, "sources": [], "editorialReviewedAt": review["generatedAt"]}
    eligible_rows = [row for row in rows if not exclusion(row, now)]
    eligible_urls = {row["canonical_url"] for row in eligible_rows}
    audit = {"generated_at": now.isoformat(), "selected_stories": len(selected),
             "screened_candidates": len(packets),
             "reviewed_candidates": sum(d.quality > 0 for d in decisions.values()), "editorial_rejections": rejected,
             "pipeline_exclusions": review["excluded"], "policy": review["policy"],
             "deduplication": {"eligible_rows_before_candidate_budget": len(eligible_rows),
                               "unique_urls_before_candidate_budget": len(eligible_urls),
                               "same_url_rediscoveries": len(eligible_rows) - len(eligible_urls),
                               "final_selection_exclusions": review.get("selection", {}).get("excluded", []),
                               "note": "URL rediscovery counts are not semantic duplicate recall. Final selection also removes overlapping coverage."},
             "selected_podcasts": sum(s["kind"] == "podcast" for s in selected)}
    return snapshot, audit


def verify_snapshot_images(snapshot, repository):
    verified = []
    for story in snapshot["stories"]:
        if not story["image"]:
            continue
        quality = repository.get_image_quality(story["url"])
        if not quality or quality["image"] != story["image"] or quality["width"] < 400 or quality["height"] < 200:
            raise RuntimeError("Unverified image in source database; run the collection pipeline before export")
        verified.append({"story_id": story["id"], "width": quality["width"], "height": quality["height"]})
    return {"verified": len(verified), "omitted": len(snapshot["stories"]) - len(verified), "images": verified}


def export_date(review, now, zone, requested=None):
    today = now.astimezone(ZoneInfo(zone)).date()
    if requested is None:
        return today.isoformat()
    target = datetime.strptime(requested, "%Y-%m-%d").date()
    cutoff = parse_datetime(review.get("cutoff"))
    if (not cutoff or target.isoformat() != requested or target != cutoff.astimezone(ZoneInfo(zone)).date()
            or not timedelta(0) <= today - target <= timedelta(days=1)
            or not timedelta(0) <= now - cutoff <= timedelta(hours=24)):
        raise ValueError("Late revision must match a current review's original edition date")
    return requested


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--edition-date")
    args = parser.parse_args()
    settings, config, repository, _ = build_runtime()
    now = datetime.now(timezone.utc)
    with repository.db.connect() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM normalized_items")]
        raw_stats = [dict(r) for r in conn.execute("SELECT source, COUNT(*) AS total, COUNT(DISTINCT url) AS distinct_urls FROM raw_items GROUP BY source")]
    review_path = settings.project_root.parent.parent / "data/editorial/latest.json"
    if not review_path.exists():
        raise RuntimeError("Run the editorial pipeline before export; unreviewed publication is disabled")
    review = json.loads(review_path.read_text())
    if "selection" not in review or any("inputHash" not in packet for packet in review["packets"]):
        raise RuntimeError("Complete editorial and final-edition review required before export")
    from news_collector.pipeline.publication_history import load_history
    zone = os.environ.get("APP_TIMEZONE", "America/Los_Angeles")
    edition_date = export_date(review, now, zone, args.edition_date)
    history = load_history(settings.project_root.parent.parent, edition_date)
    enabled = {s["name"] for s in config["collectors"] if s.get("enabled", True)}
    discoveries = repository.source_discoveries()
    from news_collector.pipeline.quality_review import verify_final_audit
    final_audit = verify_final_audit(review, history, now)
    snapshot, audit = assemble_reviewed(rows, review, now, zone, history,
                                       [r for r in discoveries if r["source"] in enabled], audited_selection=True, edition_date=edition_date)
    if [s["id"] for s in snapshot["stories"]] != review["selection"]["selected_ids"]:
        raise RuntimeError("Export changed the audited selection; resolve duplicate/publisher limits at the final desk")
    event_keys = {story.id: story.event_key for story in final_audit.review.stories}
    for story in snapshot["stories"]:
        story["eventKey"] = event_keys[story["id"]]
    audit["final_quality_review"] = final_audit.model_dump(mode="json")
    audit["publication_history"] = {"prior_stories": len(history), "repeats_in_edition": 0,
                                    "blocked_candidates": sum(e["reason"] == "previously_published" for e in review["excluded"])}
    audit["image_quality"] = verify_snapshot_images(snapshot, repository)
    health = []
    for source in config["collectors"]:
        state = repository.get_source_state(source["name"])
        recent = [r for r in rows if r["source"] == source["name"] and (parse_datetime(r.get("published_at")) or datetime.min.replace(tzinfo=timezone.utc)) >= now - timedelta(days=7)]
        checked = parse_datetime(state.get("last_success_at"))
        status = "disabled" if not source.get("enabled", True) else state.get("last_status") or ("degraded" if state.get("last_reason") else "ok" if checked and checked >= now - timedelta(hours=24) else "unverified")
        reason = state.get("last_reason")
        if state.get("transport") == "rss-fallback":
            reason = "Public RSS fallback; API credentials rejected"
        health.append({"name": source["name"], "status": status, "count": len(recent), "latest": max((r["published_at"] for r in recent if r.get("published_at")), default=None), "reason": reason if status != "disabled" else "Disabled in configuration"})
    snapshot["sources"] = health
    audit["source_health"] = health
    from news_collector.pipeline.source_audit import audit_sources
    collection_path = settings.project_root.parent.parent / "data/collection-run.json"
    collection = json.loads(collection_path.read_text()) if collection_path.exists() else None
    source_audit = audit_sources(config, repository, discoveries, review, snapshot, now, collection)
    snapshot["sources"] = source_audit
    from news_collector.pipeline.sports import config_for, attach_sports
    if config_for(settings).get("enabled", True):
        sports_path = settings.project_root.parent.parent / "data/sports/latest.json"
        if not sports_path.exists():
            raise RuntimeError("Sports review required; run the sports pipeline before export")
        attach_sports(snapshot, json.loads(sports_path.read_text()), now)
        audit["sports"] = {"stories": sum(s.get("sportsGroup") is not None for s in snapshot["stories"]), "checkedAt": snapshot["sports"]["checkedAt"]}
        audit["selected_stories"] = len(snapshot["stories"])
        audit["image_quality"] = verify_snapshot_images(snapshot, repository)
    audit["source_health"] = source_audit
    audit["historical_raw_counts_not_semantic_duplicates"] = raw_stats
    root = settings.project_root.parent.parent
    out = root / "data"
    out.mkdir(exist_ok=True)
    for name, payload in [("edition.json", snapshot), ("edition-audit.json", audit),
                          ("source-audit.json", {"generatedAt": now.isoformat(), "sources": source_audit})]:
        temporary = out / (name + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2))
        temporary.replace(out / name)
    print(json.dumps({"generated_at": audit["generated_at"], "selected_stories": len(snapshot["stories"]),
                      "reviewed_candidates": audit["reviewed_candidates"],
                      "podcasts": audit["selected_podcasts"],
                      "verified_images": audit["image_quality"]["verified"],
                      "audit": str(out / "edition-audit.json")}, indent=2))


if __name__ == "__main__":
    main()
