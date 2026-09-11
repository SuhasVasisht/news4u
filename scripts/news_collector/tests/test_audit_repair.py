from copy import deepcopy
import hashlib
import json

import pytest

from news_collector.pipeline.audit_repair import repairable_ids, reusable_story_checks, prunable_optional_ids, plain_review_prose, ProseCorrections, apply_corrections
from news_collector.pipeline.edition_audit import validate_audit
from news_collector.pipeline.editorial import ReviewBatch
from test_editorial import decision, packet
from test_edition_audit import fixture, NOW


def test_citations_are_parsed_before_audit_without_losing_attribution():
    reviewed = ReviewBatch(decisions=[decision(summary="As [WIRED **reports**](https://example.org/a_(b)), the claim remains unconfirmed.")])
    assert plain_review_prose(reviewed).decisions[0].summary == "As WIRED reports, the claim remains unconfirmed."
    reviewed.decisions[0].summary = "An ![image](https://example.org/a.png)"
    with pytest.raises(ValueError, match="Images"):
        plain_review_prose(reviewed)


def test_copy_edit_cannot_change_admission_scores_or_evidence():
    original = decision().model_dump()
    fields = {key: original[key] for key in ("id", "headline", "summary", "points", "sections", "caveats")}
    fields["headline"] = "A more precise headline"
    correction = ProseCorrections(corrections=[fields])
    result = apply_corrections({"one": original}, correction, [packet()]).decisions[0]
    assert result.headline == fields["headline"]
    assert result.quality == original["quality"] and result.evidence == original["evidence"]
    with pytest.raises(ValueError):
        ProseCorrections(corrections=[{**fields, "quality": 100}])
    with pytest.raises(ValueError, match="exactly once"):
        apply_corrections({"one": original}, ProseCorrections(corrections=[]), [packet()])


def test_only_optional_unmapped_story_holds_can_be_pruned():
    request, envelope = fixture()
    envelope["review"]["stories"][0]["verdict"] = "hold"
    envelope["review"]["coverage"][0].update(story_ids=[], status="missing", cause="selection")
    request["checklist"]["events"][0]["mustCover"] = False
    body = {key: value for key, value in request.items() if key != "requestHash"}
    request["requestHash"] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    envelope["requestHash"] = request["requestHash"]
    report = validate_audit(envelope, request, NOW)
    checklist = request["checklist"]
    assert prunable_optional_ids(report, checklist) == ["a"]
    checklist["events"][0]["mustCover"] = True
    assert prunable_optional_ids(report, checklist) == []
    checklist["events"][0]["mustCover"] = False
    report.review.coverage[0].story_ids = ["a"]
    report.review.coverage[0].status = "covered"
    report.review.coverage[0].cause = "covered"
    assert prunable_optional_ids(report, checklist) == []
    report.blockers.append("Edition-wide blocker")
    assert prunable_optional_ids(report, checklist) == []


def test_unchanged_passed_check_can_be_reused():
    request, envelope = fixture()
    report = validate_audit(envelope, request, NOW)
    result = reusable_story_checks(request, deepcopy(request), report)
    assert [story.id for story in result] == ["a"]
    assert result[0] is not report.review.stories[0]
    assert repairable_ids(report) == []


@pytest.mark.parametrize("key", ["policy", "cutoff", "packets", "selection", "history", "checklist", "decisions"])
def test_changed_review_inputs_prevent_reuse(key):
    request, envelope = fixture()
    report = validate_audit(envelope, request, NOW)
    changed = deepcopy(request)
    if key == "decisions":
        changed[key][0]["headline"] = "Changed published headline"
    else:
        changed[key] = None
    assert not reusable_story_checks(request, changed, report)


def test_held_and_incomplete_checks_cannot_be_reused():
    request, envelope = fixture()
    report = validate_audit(envelope, request, NOW)
    report.review.stories[0].verdict = "hold"
    assert not reusable_story_checks(request, request, report)
    report.review.stories[0].verdict = "pass"
    report.blockers.append("a: headline lacks checks")
    assert not reusable_story_checks(request, request, report)
    report.review.stories[0].claims[0].verdict = "uncertain"
    assert repairable_ids(report) == ["a"]
