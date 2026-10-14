"""An independent, evidence-bound factual gate for the selected sports prose."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

from .edition_audit import StoryAuditReview

PROMPT = Path(__file__).resolve().parents[2] / "config/sports-factual-audit-prompt.md"


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def factual_request(request, decisions, selected):
    packets = {packet["id"]: packet for packet in request["packets"]}
    by_id = {decision.id: decision.model_dump(mode="json") for decision in decisions}
    return {"policy": fingerprint({"version": 1, "prompt": PROMPT.read_text()}),
            "cutoff": request["generatedAt"], "sourceRequestHash": request["requestHash"],
            "auditStoryIds": list(selected), "packets": [packets[key] for key in selected],
            "decisions": [by_id[key] for key in selected]}


def validate_factual_checks(result, payload):
    ids = payload["auditStoryIds"]
    if len(ids) != len(set(ids)) or len(result.stories) != len(ids) or {story.id for story in result.stories} != set(ids):
        raise ValueError("Sports factual audit must check every selected story exactly once")
    packets = {packet["id"]: packet for packet in payload["packets"]}
    decisions = {decision["id"]: decision for decision in payload["decisions"]}
    held = []
    for story in result.stories:
        decision = decisions[story.id]
        passages = [decision["headline"], decision["summary"], *decision["points"], *decision.get("caveats", []),
                    *[text for section in decision["sections"] for text in (section["heading"], section["body"])]]
        passages = {text for text in passages if text.strip()}
        refs = {chunk["id"] for chunk in packets[story.id]["chunks"]}
        for claim in story.claims:
            if claim.passage not in passages:
                raise ValueError("Sports factual checks must quote complete published prose blocks")
            if not set(claim.evidence) <= refs or (claim.verdict == "supported" and not claim.evidence):
                raise ValueError("Sports factual check references missing or unknown source evidence")
        if not passages <= {claim.passage for claim in story.claims}:
            raise ValueError("Sports factual audit must check every published prose block")
        if (story.verdict != "pass" or not story.attributionChecked or not story.publicationDatesChecked
                or story.promotional or any(claim.verdict != "supported" for claim in story.claims)):
            held.append(story.id)
    return held


def factual_proof(payload, checks):
    return {"input": payload, "inputHash": fingerprint(payload), "reviewedAt": datetime.now(timezone.utc).isoformat(),
            "review": checks.model_dump(mode="json")}


def verify_factual_proof(proof, now, expected=None, stories=None):
    if not proof:
        raise ValueError("Independent sports factual audit is required before publication")
    payload = proof["input"]
    if (proof["inputHash"] != fingerprint(payload) or (expected is not None and payload != expected)
            or payload["policy"] != fingerprint({"version": 1, "prompt": PROMPT.read_text()})):
        raise ValueError("Sports factual audit does not match current source evidence and prose")
    reviewed_at = datetime.fromisoformat(proof["reviewedAt"])
    if reviewed_at.tzinfo is None or not timedelta(minutes=-5) <= now - reviewed_at <= timedelta(hours=24):
        raise ValueError("Sports factual audit requires a current timezone-aware review")
    result = StoryAuditReview.model_validate(proof["review"])
    if validate_factual_checks(result, payload):
        raise ValueError("Sports factual audit holds selected stories")
    if stories is not None:
        if [story["id"] for story in stories] != payload["auditStoryIds"]:
            raise ValueError("Export changed the fact-audited sports selection")
        packets = {packet["id"]: packet for packet in payload["packets"]}
        for story, decision in zip(stories, payload["decisions"]):
            if (story["title"] != decision["headline"] or any(story.get(key, []) != decision.get(key, [])
                    for key in ("summary", "points", "sections", "caveats"))):
                raise ValueError("Export changed fact-audited sports prose")
            packet = packets[story["id"]]
            if story["url"] != packet["url"] or story["publishedAt"] != packet["publishedAt"]:
                raise ValueError("Export changed fact-audited sports source metadata")
    return result
