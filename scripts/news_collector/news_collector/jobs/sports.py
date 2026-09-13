import argparse
import json
import os
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from rapidfuzz import fuzz

from news_collector.runtime import build_runtime
from news_collector.pipeline.editorial import codex_review, ReviewBatch, validate_decisions, reader_profile
from news_collector.pipeline.sports import LIMITS, prepare_sports, publish_sports, write_json, config_for, fingerprint
from news_collector.utils import parse_datetime


class SportsReview(ReviewBatch):
    pass


REVIEW_BATCH_SIZE = 5


def overlapping_story(left, right):
    return (fuzz.token_set_ratio(left.headline, right.headline) >= 70
            and fuzz.token_set_ratio(left.summary, right.summary) >= 50)


def review_candidates(request, prompt, output):
    decisions = []
    for group in dict.fromkeys(p["sportsGroup"] for p in request["packets"]):
        group_packets = [p for p in request["packets"] if p["sportsGroup"] == group]
        for offset in range(0, len(group_packets), REVIEW_BATCH_SIZE):
            packets = group_packets[offset:offset + REVIEW_BATCH_SIZE]
            payload = {"packets": packets, "previouslyPublished": request["previouslyPublished"]}
            key = fingerprint({"input": payload, "prompt": prompt.read_text(), "profile": reader_profile(),
                               "model": os.environ.get("NEWS_EDITOR_MODEL", "default")})
            cache = output / f"review-{key}.json"
            batch = offset // REVIEW_BATCH_SIZE + 1
            total = (len(group_packets) + REVIEW_BATCH_SIZE - 1) // REVIEW_BATCH_SIZE
            print(f"Sports review: {group}, batch {batch}/{total}, {len(packets)} candidates", flush=True)
            result = SportsReview.model_validate_json(cache.read_text()) if cache.exists() else codex_review(payload, prompt, output, SportsReview)
            validate_decisions(result, packets)
            write_json(cache, result.model_dump(mode="json"))
            decisions.extend(result.decisions)
    return SportsReview(decisions=decisions)


def select_sports(decisions, packets):
    ranked = sorted((decision for decision in decisions if decision.decision == "admit"),
                    key=lambda decision: (-decision.importance, -decision.quality))
    selected, excluded, counts, chosen = [], [], {}, []
    for decision in ranked:
        group = packets[decision.id]["sportsGroup"]
        if any(packets[item.id]["sportsGroup"] == group and overlapping_story(decision, item)
               for item in chosen):
            excluded.append({"id": decision.id, "reason": f"Duplicate {group} event already represented by a stronger account"})
            continue
        counts[group] = counts.get(group, 0) + 1
        if counts[group] <= LIMITS[group]:
            selected.append(decision.id)
            chosen.append(decision)
        else:
            excluded.append({"id": decision.id, "reason": f"Lower-ranked {group} item beyond the section limit"})
    return {"selected_ids": selected, "excluded": excluded}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-review", action="store_true")
    parser.add_argument("--review-file")
    args = parser.parse_args()
    settings, _, repository, _ = build_runtime()
    if not config_for(settings).get("enabled", True):
        return
    output = settings.project_root.parent.parent / "data/sports"
    now, zone = datetime.now(timezone.utc), os.environ.get("APP_TIMEZONE", "America/Los_Angeles")
    if args.review_file:
        request = json.loads((output / "review-request.json").read_text())
        review = json.loads(open(args.review_file).read())
    else:
        req_file = output / "review-request.json"
        if not args.prepare_review and req_file.exists():
            cached_req = json.loads(req_file.read_text())
            gen = parse_datetime(cached_req.get("generatedAt"))
            today = now.astimezone(ZoneInfo(zone)).date().isoformat()
            if cached_req.get("date") == today and gen and timedelta(0) <= now - gen <= timedelta(hours=6):
                request = cached_req
            else:
                request = prepare_sports(settings, repository, now, zone)
                write_json(req_file, request)
        else:
            request = prepare_sports(settings, repository, now, zone)
            write_json(req_file, request)
        if args.prepare_review:
            print(json.dumps({"request": str(output / "review-request.json"), "candidates": len(request["packets"]), "sources": request["sources"]}, indent=2))
            return
        result = review_candidates(request, settings.project_root / "config/sports-prompt.md", output)
        packets = {packet["id"]: packet for packet in request["packets"]}
        review = {"requestHash": request["requestHash"], "reviewer": "Sports editorial desk", "reviewedAt": datetime.now(timezone.utc).isoformat(),
                  "decisions": [d.model_dump() for d in result.decisions], "selection": select_sports(result.decisions, packets)}
    write_json(output / "review-response.json", review)
    snapshot = publish_sports(request, review, settings, repository, datetime.now(timezone.utc), zone)
    write_json(output / "latest.json", snapshot)
    print(json.dumps({"stories": len(snapshot["stories"]), "checkedAt": snapshot["sports"]["checkedAt"], "output": str(output / "latest.json")}))


if __name__ == "__main__":
    main()
