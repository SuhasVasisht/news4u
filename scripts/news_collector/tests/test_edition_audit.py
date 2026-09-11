from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from news_collector.pipeline.edition_audit import (
    build_audit_request, require_publishable, validate_audit,
)

NOW = datetime(2026, 9, 10, 20, tzinfo=timezone.utc)


def fixture():
    packets = [{"id": "a", "chunks": [{"id": "p1", "text": "The bank cut rates today."}]}]
    decisions = [{"id": "a", "decision": "admit", "headline": "Bank cuts rates",
                  "summary": "The bank cut rates today.", "points": [], "sections": []}]
    checklist = {"checkedAt": NOW.isoformat(), "method": "independent_web_research",
                 "researcher": "separate desk", "scope": ["Economy"], "queries": ["central bank decision today"],
                 "events": [{"id": "rates", "event": "Bank cuts rates today", "sector": "Economy", "mustCover": True,
                             "sources": [{"url": "https://example.org/decision", "publishedAt": NOW.isoformat(),
                                          "finding": "The bank announced a rate cut today."}]}]}
    request = build_audit_request(packets, decisions, {"selected_ids": ["a"]}, [], checklist, NOW)
    claims = [{"passage": text, "verdict": "supported", "critical": True, "evidence": ["p1"],
               "reason": "The primary evidence states this clearly."} for text in (decisions[0]["headline"], decisions[0]["summary"])]
    payload = {"requestHash": request["requestHash"], "reviewer": "independent desk", "reviewedAt": NOW.isoformat(),
               "review": {"stories": [{"id": "a", "event_key": "bank-rate-decision", "verdict": "pass",
                                       "reason": "Primary announcement supports the summary.",
                                       "attributionChecked": True, "publicationDatesChecked": True, "promotional": False,
                                       "claims": claims, "priorStoryIds": [], "materialUpdate": None, "materialUpdateEvidence": []}],
                          "coverage": [{"event_id": "rates", "story_ids": ["a"], "status": "covered", "cause": "covered",
                                        "reason": "The selected report covers the bank decision."}]}}
    return request, payload


def rebind(request, payload):
    request = build_audit_request(request["packets"], request["decisions"], request["selection"],
                                 request["history"], request["checklist"], NOW)
    payload["requestHash"] = request["requestHash"]
    return request


def test_valid_audit_is_publishable_and_measurable():
    request, payload = fixture()
    report = validate_audit(payload, request, NOW)
    require_publishable(report)
    assert report.metrics["coveredEvents"] == 1
    assert report.metrics["unresolvedClaims"] == 0


def test_stored_event_identity_requires_explicit_prior_coverage_review():
    request, payload = fixture()
    request["history"] = [{"id": "old", "eventKey": "bank-rate-decision"}]
    request = rebind(request, payload)
    with pytest.raises(ValueError, match="prior event identity"):
        require_publishable(validate_audit(payload, request, NOW))


def test_request_hash_binds_selection_and_evidence():
    request, payload = fixture()
    request["packets"][0]["chunks"][0]["text"] = "Different facts"
    with pytest.raises(ValueError, match="does not match"):
        validate_audit(payload, request, NOW)


@pytest.mark.parametrize("date", [NOW - timedelta(hours=25), NOW + timedelta(minutes=6), NOW.replace(tzinfo=None)])
def test_stale_future_or_naive_audits_rejected(date):
    request, payload = fixture()
    payload["reviewedAt"] = date.isoformat()
    with pytest.raises(ValueError, match="timestamps"):
        validate_audit(payload, request, NOW)


@pytest.mark.parametrize("change", ["missing", "duplicate", "unknown"])
def test_exact_story_accounting(change):
    request, payload = fixture()
    stories = payload["review"]["stories"]
    if change == "missing":
        stories.clear()
    elif change == "duplicate":
        stories.append(deepcopy(stories[0]))
    else:
        stories[0]["id"] = "unknown"
    with pytest.raises(ValueError, match="exactly once"):
        validate_audit(payload, request, NOW)


@pytest.mark.parametrize("evidence", [[], ["p99"]])
def test_claim_evidence_is_required_and_known(evidence):
    request, payload = fixture()
    payload["review"]["stories"][0]["claims"][0]["evidence"] = evidence
    with pytest.raises(ValueError, match="evidence references"):
        validate_audit(payload, request, NOW)


def test_unpublished_claim_cannot_satisfy_audit():
    request, payload = fixture()
    payload["review"]["stories"][0]["claims"][0]["passage"] = "Invented quote"
    with pytest.raises(ValueError, match="actually being published"):
        validate_audit(payload, request, NOW)


@pytest.mark.parametrize("field,value", [("verdict", "hold"), ("promotional", True),
                                         ("attributionChecked", False), ("publicationDatesChecked", False)])
def test_incomplete_or_low_quality_story_blocks(field, value):
    request, payload = fixture()
    payload["review"]["stories"][0][field] = value
    with pytest.raises(ValueError, match="blocked publication"):
        require_publishable(validate_audit(payload, request, NOW))


def test_all_published_sections_need_claim_checks():
    request, payload = fixture()
    request["decisions"][0]["sections"] = [{"body": "Unchecked long notes"}]
    request = rebind(request, payload)
    assert validate_audit(payload, request, NOW).status == "blocked"


def test_unsupported_claim_cannot_pass_even_if_marked_noncritical():
    request, payload = fixture()
    claim = payload["review"]["stories"][0]["claims"][0]
    claim.update(verdict="unsupported", critical=False)
    report = validate_audit(payload, request, NOW)
    assert report.status == "blocked"
    assert report.metrics["unresolvedClaims"] == 1


def test_independent_discovery_cannot_be_skipped():
    request, payload = fixture()
    request["checklist"] = None
    payload["review"]["coverage"] = []
    request = rebind(request, payload)
    assert "Independent discovery checklist is missing" in validate_audit(payload, request, NOW).blockers


@pytest.mark.parametrize("must_cover", [True, False])
def test_missing_event_reports_cause_and_blocks_only_required(must_cover):
    request, payload = fixture()
    request["checklist"]["events"][0]["mustCover"] = must_cover
    request = rebind(request, payload)
    payload["review"]["coverage"][0].update(status="missing", story_ids=[], cause="selection")
    report = validate_audit(payload, request, NOW)
    assert report.status == ("blocked" if must_cover else "passed")
    assert report.metrics["missing_selection"] == 1


def test_must_cover_cannot_be_dismissed_as_out_of_scope():
    request, payload = fixture()
    payload["review"]["coverage"][0].update(status="not_applicable", story_ids=[], cause="out_of_scope")
    assert validate_audit(payload, request, NOW).status == "blocked"


def test_prior_coverage_requires_material_change_and_evidence():
    request, payload = fixture()
    request["history"] = [{"id": "yesterday"}]
    request = rebind(request, payload)
    story = payload["review"]["stories"][0]
    story["priorStoryIds"] = ["yesterday"]
    assert validate_audit(payload, request, NOW).status == "blocked"
    story.update(materialUpdate="New rate decision changes the prior rate guidance.", materialUpdateEvidence=["p1"])
    assert validate_audit(payload, request, NOW).status == "passed"


def test_duplicate_event_requires_material_update():
    request, payload = fixture()
    for field in ("packets", "decisions"):
        second = deepcopy(request[field][0])
        second["id"] = "b"
        request[field].append(second)
    request["selection"]["selected_ids"].append("b")
    second = deepcopy(payload["review"]["stories"][0])
    second["id"] = "b"
    payload["review"]["stories"].append(second)
    request = rebind(request, payload)
    report = validate_audit(payload, request, NOW)
    assert report.status == "blocked"
    assert report.metrics["duplicateEventGroups"] == 1


def test_coverage_cannot_reference_unselected_story():
    request, payload = fixture()
    payload["review"]["coverage"][0]["story_ids"] = ["missing"]
    with pytest.raises(ValueError, match="selected stories"):
        validate_audit(payload, request, NOW)


def test_candidate_index_is_optional_and_hash_bound():
    request, payload = fixture()
    index = [{"id": "rejected", "title": "Other event", "decision": "reject", "reason": "Thin excerpt"}]
    indexed = build_audit_request(request["packets"], request["decisions"], request["selection"],
                                  request["history"], request["checklist"], NOW, candidate_index=index)
    assert indexed["candidate_index"] == index
    assert indexed["requestHash"] != request["requestHash"]
    payload["requestHash"] = indexed["requestHash"]
    assert validate_audit(payload, indexed, NOW).status == "passed"
    indexed["candidate_index"][0]["reason"] = "Changed reason"
    with pytest.raises(ValueError, match="does not match"):
        validate_audit(payload, indexed, NOW)


@pytest.mark.parametrize("excerpt", ["T", "The bank cut rates "])
def test_short_or_padded_excerpt_cannot_satisfy_block_coverage(excerpt):
    request, payload = fixture()
    payload["review"]["stories"][0]["claims"][1]["passage"] = excerpt
    assert validate_audit(payload, request, NOW).status == "blocked"


def test_short_published_block_requires_complete_excerpt():
    request, payload = fixture()
    payload["review"]["stories"][0]["claims"][0]["passage"] = "Bank cuts"
    assert validate_audit(payload, request, NOW).status == "blocked"


def test_twenty_character_excerpt_counts_for_long_block():
    request, payload = fixture()
    payload["review"]["stories"][0]["claims"][1]["passage"] = "The bank cut rates today"
    assert validate_audit(payload, request, NOW).status == "passed"
