import argparse
import json
import os
from datetime import datetime, timezone

from news_collector.runtime import build_runtime
from news_collector.pipeline.editorial import codex_review, ReviewBatch
from news_collector.pipeline.sports import prepare_sports, publish_sports, write_json, config_for


class SportsReview(ReviewBatch):
    pass


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
        result = codex_review({"packets": request["packets"], "previouslyPublished": request["previouslyPublished"]}, settings.project_root / "config/sports-prompt.md", output, SportsReview)
        review = {"requestHash": request["requestHash"], "reviewer": "Sports editorial desk", "reviewedAt": datetime.now(timezone.utc).isoformat(),
                  "decisions": [d.model_dump() for d in result.decisions], "selection": {"selected_ids": [d.id for d in sorted(result.decisions, key=lambda d: (-d.importance, -d.quality)) if d.decision == "admit"], "excluded": []}}
    snapshot = publish_sports(request, review, settings, repository, datetime.now(timezone.utc), zone)
    write_json(output / "latest.json", snapshot)
    print(json.dumps({"stories": len(snapshot["stories"]), "checkedAt": snapshot["sports"]["checkedAt"], "output": str(output / "latest.json")}))


if __name__ == "__main__":
    main()
