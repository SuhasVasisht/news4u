import argparse
import json
import os
from datetime import datetime, timezone

from news_collector.runtime import build_runtime
from news_collector.pipeline.editorial import codex_review, ReviewBatch, validate_decisions, reader_profile
from news_collector.pipeline.sports import prepare_sports, publish_sports, write_json, config_for, fingerprint


class SportsReview(ReviewBatch):
    pass


def review_candidates(request, prompt, output):
    decisions = []
    for group in dict.fromkeys(p["sportsGroup"] for p in request["packets"]):
        packets = [p for p in request["packets"] if p["sportsGroup"] == group]
        payload = {"packets": packets, "previouslyPublished": request["previouslyPublished"]}
        key = fingerprint({"input": payload, "prompt": prompt.read_text(), "profile": reader_profile(),
                           "model": os.environ.get("NEWS_EDITOR_MODEL", "default")})
        cache = output / f"review-{key}.json"
        print(f"Sports review: {group}, {len(packets)} candidates", flush=True)
        result = SportsReview.model_validate_json(cache.read_text()) if cache.exists() else codex_review(payload, prompt, output, SportsReview)
        validate_decisions(result, packets)
        write_json(cache, result.model_dump(mode="json"))
        decisions.extend(result.decisions)
    return SportsReview(decisions=decisions)


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
        request = prepare_sports(settings, repository, now, zone)
        write_json(output / "review-request.json", request)
        if args.prepare_review:
            print(json.dumps({"request": str(output / "review-request.json"), "candidates": len(request["packets"]), "sources": request["sources"]}, indent=2))
            return
        result = review_candidates(request, settings.project_root / "config/sports-prompt.md", output)
        review = {"requestHash": request["requestHash"], "reviewer": "Sports editorial desk", "reviewedAt": datetime.now(timezone.utc).isoformat(),
                  "decisions": [d.model_dump() for d in result.decisions], "selection": {"selected_ids": [d.id for d in sorted(result.decisions, key=lambda d: (-d.importance, -d.quality)) if d.decision == "admit"], "excluded": []}}
    write_json(output / "review-response.json", review)
    snapshot = publish_sports(request, review, settings, repository, datetime.now(timezone.utc), zone)
    write_json(output / "latest.json", snapshot)
    print(json.dumps({"stories": len(snapshot["stories"]), "checkedAt": snapshot["sports"]["checkedAt"], "output": str(output / "latest.json")}))


if __name__ == "__main__":
    main()
