import argparse
import json
import os
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict
from datetime import datetime, timezone
from rapidfuzz import fuzz

from news_collector.runtime import build_runtime
from news_collector.pipeline.editorial import codex_review, ReviewBatch, validate_decisions, reader_profile, EditionSelection, validate_selection
from news_collector.pipeline.sports import LIMITS, prepare_sports, publish_sports, write_json, config_for, fingerprint, validate_sports_request


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
            result = None
            if cache.exists():
                try:
                    result = SportsReview.model_validate_json(cache.read_text())
                    validate_decisions(result, packets)
                except ValueError as exc:
                    # A cache entry is reusable only while its evidence contract
                    # remains valid. Discard stale/malformed output and ask the
                    # normal bounded-retry reviewer to regenerate the batch.
                    print(f"Discarding invalid cached sports review: {str(exc)[:300]}", flush=True)
                    cache.unlink()
                    result = None
            if result is None:
                result = codex_review(payload, prompt, output, SportsReview)
                validate_decisions(result, packets)
            write_json(cache, result.model_dump(mode="json"))
            decisions.extend(result.decisions)
    return SportsReview(decisions=decisions)


def select_sports(decisions, packets, *, deduplicate=True):
    ranked = sorted((decision for decision in decisions if decision.decision == "admit"),
                    key=lambda decision: (-decision.importance, -decision.quality))
    selected, excluded, counts, chosen = [], [], {}, []
    for decision in ranked:
        group = packets[decision.id]["sportsGroup"]
        if deduplicate and any(packets[item.id]["sportsGroup"] == group and overlapping_story(decision, item)
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




class SportsNoveltyItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    status: Literal["new", "repeat", "material_update"]
    prior_story_ids: list[str]
    material_update: str | None
    evidence: list[str]
    reason: str


class SportsNoveltyReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stories: list[SportsNoveltyItem]


def sports_history_details(history, root=None):
    details = {}
    if root:
        for path in sorted((root / "data/cloudflare-published/editions").glob("*/edition.json")):
            edition = json.loads(path.read_text())
            for story in edition.get("stories", []):
                details.setdefault((edition["date"], story["id"]), story)
    result = {}
    for previous in history:
        story = details.get((previous["date"], previous["id"]), {})
        if story and story.get("sector") != "Sports":
            continue
        result[previous["id"]] = {**previous, **{key: story[key] for key in
            ("summary", "points", "publishedAt") if key in story}}
    return list(result.values())


def review_sports_novelty(request, decisions, output, root=None):
    history = sports_history_details(request["previouslyPublished"], root)
    if not history or not decisions:
        return [], []
    ids = {decision.id for decision in decisions}
    packets = [packet for packet in request["packets"] if packet["id"] in ids]
    payload = {"packets": packets, "proposedStories": [d.model_dump(mode="json") for d in decisions],
               "previouslyPublished": history}
    prompt = Path(__file__).resolve().parents[2] / "config/sports-novelty-prompt.md"
    key = fingerprint({"input": payload, "prompt": prompt.read_text(), "profile": reader_profile(),
                       "model": os.environ.get("NEWS_EDITOR_MODEL", "default"),
                       "effort": os.environ.get("NEWS_EDITOR_REASONING_EFFORT", "default")})
    cache = output / f"novelty-{key}.json"
    def validate(result):
        actual = [item.id for item in result.stories]
        if len(actual) != len(ids) or set(actual) != ids:
            raise ValueError("Sports novelty review must account for every proposed story exactly once")
        prior_ids = {item["id"] for item in history}
        refs = {p["id"]: {c["id"] for c in p["chunks"]} for p in packets}
        for item in result.stories:
            if not set(item.prior_story_ids) <= prior_ids or not set(item.evidence) <= refs[item.id]:
                raise ValueError("Sports novelty proof references unknown history or source evidence")
            if len(item.reason.strip()) < 10:
                raise ValueError("Sports novelty review requires a specific explanation")
            if item.status == "new" and (item.prior_story_ids or item.material_update or not item.evidence):
                raise ValueError("New sports event needs source evidence and no prior-event match")
            if item.status == "repeat" and (not item.prior_story_ids or item.material_update):
                raise ValueError("Repeated sports event needs a known prior story and cannot claim an update")
            if item.status == "material_update" and (not item.prior_story_ids or not item.evidence
                    or not item.material_update or len(item.material_update.strip()) < 20):
                raise ValueError("Sports update needs prior IDs, a concrete new development and cited source chunks")
    print(f"Sports cross-edition novelty audit: {len(decisions)} selected stories", flush=True)
    result = None
    if cache.exists():
        try:
            result = SportsNoveltyReview.model_validate_json(cache.read_text())
            validate(result)
        except ValueError:
            result = None
    if result is None:
        result = codex_review(payload, prompt, output, SportsNoveltyReview, validate_result=validate)
        validate(result)
    write_json(cache, result.model_dump(mode="json"))
    write_json(output / "novelty-latest.json", {"inputHash": key, "requestHash": request.get("requestHash"),
        "review": result.model_dump(mode="json")})
    carryover = {packet["id"] for packet in packets if packet.get("carryoverFrom")}
    repeats = [{"id": item.id, "reason": item.reason} for item in result.stories
               if item.status == "repeat" and item.id not in carryover]
    updates = [item.model_dump(mode="json") for item in result.stories if item.status == "material_update"]
    return repeats, updates

def reconcile_sports_events(request, decisions, prompt, output, history_root=None):
    packets = {packet["id"]: packet for packet in request["packets"]}
    shortlist = [{**decision.model_dump(mode="json"), "sportsGroup": packets[decision.id]["sportsGroup"],
                  "url": packets[decision.id]["url"], "publishedAt": packets[decision.id]["publishedAt"]}
                 for decision in decisions if decision.decision == "admit"]
    if not shortlist:
        return {"selected_ids": [], "excluded": []}
    payload = {"shortlist": shortlist, "previouslyPublished": request["previouslyPublished"]}
    key = fingerprint({"input": payload, "prompt": prompt.read_text(), "profile": reader_profile(),
                       "model": os.environ.get("NEWS_EDITOR_MODEL", "default"),
                       "effort": os.environ.get("NEWS_EDITOR_REASONING_EFFORT", "default")})
    cache = output / f"event-selection-{key}.json"
    print(f"Sports final event selection: {len(shortlist)} admitted candidates", flush=True)
    result = None
    if cache.exists():
        try:
            result = EditionSelection.model_validate_json(cache.read_text())
            validate_selection(result, shortlist)
        except ValueError:
            cache.unlink()
            result = None
    if result is None:
        result = codex_review(payload, prompt, output, EditionSelection)
        validate_selection(result, shortlist)
    write_json(cache, result.model_dump(mode="json"))
    chosen = set(result.selected_ids)
    selection = select_sports([decision for decision in decisions if decision.id in chosen], packets, deduplicate=False)
    selection["excluded"].extend(item.model_dump(mode="json") for item in result.excluded)
    repeats, _ = review_sports_novelty(request,
        [decision for decision in decisions if decision.id in selection["selected_ids"]], output, history_root)
    repeated = {item["id"] for item in repeats}
    selection["selected_ids"] = [key for key in selection["selected_ids"] if key not in repeated]
    selection["excluded"].extend(repeats)
    return selection

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
            try:
                validate_sports_request(cached_req, settings, now, zone)
                request = cached_req
            except (ValueError, KeyError, TypeError):
                print("Regenerating sports request after date, policy, history or integrity changed", flush=True)
                request = prepare_sports(settings, repository, now, zone)
                write_json(req_file, request)
        else:
            request = prepare_sports(settings, repository, now, zone)
            write_json(req_file, request)
        if args.prepare_review:
            print(json.dumps({"request": str(output / "review-request.json"), "candidates": len(request["packets"]), "sources": request["sources"]}, indent=2))
            return
        result = review_candidates(request, settings.project_root / "config/sports-prompt.md", output)
        review = {"requestHash": request["requestHash"], "reviewer": "Sports editorial desk", "reviewedAt": datetime.now(timezone.utc).isoformat(),
                  "decisions": [d.model_dump() for d in result.decisions], "selection": reconcile_sports_events(request, result.decisions,
                     settings.project_root / "config/sports-event-selection-prompt.md", output, settings.project_root.parent.parent)}
    write_json(output / "review-response.json", review)
    snapshot = publish_sports(request, review, settings, repository, datetime.now(timezone.utc), zone)
    write_json(output / "latest.json", snapshot)
    print(json.dumps({"stories": len(snapshot["stories"]), "checkedAt": snapshot["sports"]["checkedAt"], "output": str(output / "latest.json")}))


if __name__ == "__main__":
    main()
