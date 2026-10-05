"""Fail-closed, evidence-bound final desk review independent of story selection."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DiscoverySource(StrictModel):
    url: HttpUrl
    publishedAt: datetime
    finding: str = Field(min_length=20)


class DiscoveryEvent(StrictModel):
    id: str = Field(min_length=1)
    event: str = Field(min_length=10)
    sector: str = Field(min_length=1)
    mustCover: bool
    sources: list[DiscoverySource] = Field(min_length=1)


class IndependentChecklist(StrictModel):
    checkedAt: datetime
    method: Literal["independent_web_research"]
    researcher: str = Field(min_length=1)
    scope: list[str] = Field(min_length=1)
    queries: list[str] = Field(min_length=1)
    events: list[DiscoveryEvent] = Field(min_length=1)


class ClaimCheck(StrictModel):
    # Exact passages make a review inspectable; a reference ID alone proves little.
    passage: str = Field(min_length=1)
    verdict: Literal["supported", "unsupported", "uncertain"]
    critical: bool
    evidence: list[str]
    reason: str = Field(min_length=10)


class StoryAudit(StrictModel):
    id: str
    event_key: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    verdict: Literal["pass", "hold"]
    reason: str = Field(min_length=10)
    attributionChecked: bool
    publicationDatesChecked: bool
    promotional: bool
    claims: list[ClaimCheck] = Field(min_length=1)
    priorStoryIds: list[str]
    materialUpdate: str | None
    materialUpdateEvidence: list[str]


class CoverageAudit(StrictModel):
    event_id: str
    story_ids: list[str]
    prior_story_ids: list[str] = Field(default_factory=list)
    status: Literal["covered", "missing", "not_applicable"]
    cause: Literal["covered", "discovery", "extraction", "deduplication", "selection", "after_cutoff", "out_of_scope", "previously_published"]
    reason: str = Field(min_length=10)


class AuditReview(StrictModel):
    stories: list[StoryAudit]
    coverage: list[CoverageAudit]


class StoryAuditReview(StrictModel):
    stories: list[StoryAudit]


class CoverageAuditReview(StrictModel):
    coverage: list[CoverageAudit]


class ExternalAudit(StrictModel):
    requestHash: str
    reviewer: str = Field(min_length=1)
    reviewedAt: datetime
    review: AuditReview


class AuditReport(StrictModel):
    requestHash: str
    reviewedAt: datetime
    reviewer: str
    status: Literal["passed", "blocked"]
    blockers: list[str]
    metrics: dict[str, int | float]
    review: AuditReview


def _plain(value):
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _current(value, now):
    return value.tzinfo is not None and timedelta(minutes=-5) <= now - value <= timedelta(hours=24)


def _must_cover(event):
    if not event.mustCover:
        return False
    hosts = {urlparse(str(source.url)).hostname or "" for source in event.sources}
    authoritative = any(host.endswith((".gov", ".gov.uk", ".europa.eu", ".int"))
                        or host in {"ecb.europa.eu", "who.int"} for host in hosts)
    return authoritative or len(hosts) >= 2


def build_audit_request(packets, decisions, selection, history, checklist, now=None, candidate_index=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Audit cutoff must be timezone-aware")
    body = {"policy": "edition-audit-v1", "cutoff": now.isoformat(), "packets": _plain(packets),
            "decisions": _plain(decisions), "selection": _plain(selection),
            "history": _plain(history), "checklist": _plain(checklist),
            "candidate_index": _plain(candidate_index)}
    body["requestHash"] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    return body


def validate_audit(payload, request, now=None):
    now = now or datetime.now(timezone.utc)
    audit = ExternalAudit.model_validate(payload)
    body = {key: value for key, value in request.items() if key != "requestHash"}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    if audit.requestHash != digest or request.get("requestHash") != digest:
        raise ValueError("Audit does not match current evidence, selection and discovery checklist")
    if not _current(audit.reviewedAt, now) or not _current(datetime.fromisoformat(request["cutoff"]), now):
        raise ValueError("Audit and evidence require current timezone-aware timestamps")
    selected = request["selection"]["selected_ids"]
    reviews = audit.review.stories
    if len(selected) != len(set(selected)) or Counter(s.id for s in reviews) != Counter(selected):
        raise ValueError("Audit must review every selected story exactly once")
    packets = {p["id"]: p for p in request["packets"]}
    decisions = {d["id"]: d for d in request["decisions"]}
    prior_ids = {p["id"] for p in request["history"]}
    blockers = []
    if not selected:
        blockers.append("Edition has no selected stories")
    unsupported = 0
    for story in reviews:
        if story.id not in packets or story.id not in decisions or decisions[story.id]["decision"] != "admit":
            raise ValueError("Audit references missing or unadmitted source evidence")
        refs = {c["id"] for c in packets[story.id]["chunks"]}
        decision = decisions[story.id]
        passages = [decision["headline"], decision["summary"], *decision["points"],
                    *decision.get("caveats", []),
                    *[text for s in decision["sections"] for text in (s.get("heading", ""), s["body"])]]
        for claim in story.claims:
            if not any(claim.passage in passage for passage in passages):
                raise ValueError("Claim check must quote a passage actually being published")
            if not set(claim.evidence) <= refs or (claim.verdict == "supported" and not claim.evidence):
                raise ValueError(f"Claim check has missing or unknown evidence references for {story.id}; "
                                 f"received={claim.evidence}; valid={sorted(refs)}. "
                                 "Use only supplied chunk IDs; supported claims require evidence.")
            if claim.verdict != "supported":
                unsupported += 1
                blockers.append(f"{story.id}: unresolved claim ({claim.verdict})")
        if any(passage.strip() and not any(
            claim.passage in passage and len(claim.passage.strip()) >= min(20, len(passage.strip()))
            for claim in story.claims
        ) for passage in passages):
            blockers.append(f"{story.id}: headline, summary, points or notes lack claim checks")
        if not set(story.priorStoryIds) <= prior_ids or not set(story.materialUpdateEvidence) <= refs:
            raise ValueError("Novelty review references unknown prior stories or evidence")
        matching_events = {p["id"] for p in request["history"] if p.get("eventKey") == story.event_key}
        if matching_events and not matching_events.intersection(story.priorStoryIds):
            blockers.append(f"{story.id}: prior event identity omitted from novelty review")
        if story.priorStoryIds and (not story.materialUpdate or len(story.materialUpdate.strip()) < 20 or not story.materialUpdateEvidence):
            blockers.append(f"{story.id}: repeat event without evidence-backed material update")
        if story.verdict != "pass" or not story.attributionChecked or not story.publicationDatesChecked or story.promotional:
            blockers.append(f"{story.id}: held, promotional, or incomplete factual review")
    repeated = [key for key, count in Counter(s.event_key for s in reviews).items() if count > 1]
    for key in repeated:
        group = [s for s in reviews if s.event_key == key]
        # One original account and explicit evidence-backed updates, not parallel rewrites.
        if sum(bool(s.materialUpdate and len(s.materialUpdate.strip()) >= 20 and s.materialUpdateEvidence) for s in group) < len(group) - 1:
            blockers.append(f"Duplicate selected event: {key}")
    events = []
    if request["checklist"] is None:
        blockers.append("Independent discovery checklist is missing")
    else:
        checklist = IndependentChecklist.model_validate(request["checklist"])
        events = checklist.events
        if not _current(checklist.checkedAt, now):
            blockers.append("Independent discovery checklist is stale")
        if len({e.id for e in events}) != len(events):
            raise ValueError("Discovery event IDs must be unique")
        for event in events:
            if any(source.publishedAt.tzinfo is None or source.publishedAt > checklist.checkedAt + timedelta(minutes=5) for source in event.sources):
                blockers.append(f"{event.id}: discovery source date unverified or in the future")
    coverage = audit.review.coverage
    if Counter(c.event_id for c in coverage) != Counter(e.id for e in events):
        raise ValueError("Audit must account for every independently discovered event exactly once")
    required = {e.id for e in events if _must_cover(e)}
    omissions = 0
    for item in coverage:
        if (len(set(item.story_ids)) != len(item.story_ids)
                or not set(item.story_ids) <= set(selected)
                or len(set(item.prior_story_ids)) != len(item.prior_story_ids)
                or not set(item.prior_story_ids) <= prior_ids):
            raise ValueError("Coverage must reference unique selected stories")
        if item.status == "covered" and (not item.story_ids or item.prior_story_ids or item.cause != "covered"):
            raise ValueError("Covered event requires selected stories and covered cause")
        if item.status != "covered" and (item.story_ids or item.cause == "covered"):
            raise ValueError("Uncovered event cannot claim selected coverage")
        if item.cause == "previously_published" and (item.status != "not_applicable" or not item.prior_story_ids):
            raise ValueError("Previously published coverage requires known prior story IDs")
        if item.status == "not_applicable" and item.cause not in {"after_cutoff", "out_of_scope", "previously_published"}:
            raise ValueError("Not-applicable event needs explicit scope or cutoff reason")
        if item.status == "missing":
            omissions += 1
        if (item.event_id in required and item.status != "covered"
                and item.cause != "previously_published"):
            blockers.append(f"Must-cover event unresolved: {item.event_id} ({item.cause})")
    metrics = {"selectedStories": len(selected), "reviewedStories": len(reviews),
               "discoveredEvents": len(events), "mustCoverEvents": len(required),
               "missingEvents": omissions, "coveredEvents": sum(c.status == "covered" for c in coverage),
               "duplicateEventGroups": len(repeated), "unresolvedClaims": unsupported,
               "promotionalStories": sum(s.promotional for s in reviews),
               "materialUpdates": sum(bool(s.materialUpdate and s.materialUpdateEvidence) for s in reviews)}
    for cause in ("discovery", "extraction", "deduplication", "selection"):
        metrics[f"missing_{cause}"] = sum(c.status == "missing" and c.cause == cause for c in coverage)
    return AuditReport(requestHash=digest, reviewedAt=audit.reviewedAt, reviewer=audit.reviewer,
                       status="blocked" if blockers else "passed", blockers=blockers, metrics=metrics,
                       review=audit.review)


def require_publishable(report):
    if report.status != "passed":
        raise ValueError("Final edition audit blocked publication: " + "; ".join(report.blockers))


def audit_edition(packets, decisions, selection, history, checklist, runner, now=None, candidate_index=None):
    request = build_audit_request(packets, decisions, selection, history, checklist, now, candidate_index)
    return validate_audit(runner(request), request, now)
