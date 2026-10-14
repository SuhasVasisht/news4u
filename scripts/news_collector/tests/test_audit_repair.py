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
    # An unrelated missing must-cover event is not worsened by removing held copy.
    assert prunable_optional_ids(report, checklist) == ["a"]
    checklist["events"][0]["mustCover"] = False
    report.review.coverage[0].story_ids = ["a"]
    report.review.coverage[0].status = "covered"
    report.review.coverage[0].cause = "covered"
    assert prunable_optional_ids(report, checklist) == ["a"]
    checklist["events"][0]["mustCover"] = True
    assert prunable_optional_ids(report, checklist) == []
    checklist["events"][0]["mustCover"] = False
    report.blockers.append("Edition-wide blocker")
    assert prunable_optional_ids(report, checklist) == []


def test_unchanged_passed_check_can_be_reused():
    request, envelope = fixture()
    report = validate_audit(envelope, request, NOW)
    result = reusable_story_checks(request, deepcopy(request), report)
    assert [story.id for story in result] == ["a"]
    assert result[0] is not report.review.stories[0]
    assert repairable_ids(report) == []


@pytest.mark.parametrize("key", ["policy", "cutoff", "packets", "selection", "history", "decisions"])
def test_changed_review_inputs_prevent_reuse(key):
    request, envelope = fixture()
    report = validate_audit(envelope, request, NOW)
    changed = deepcopy(request)
    if key == "decisions":
        changed[key][0]["headline"] = "Changed published headline"
    else:
        changed[key] = None
    assert not reusable_story_checks(request, changed, report)


def test_held_and_incomplete_checks_remain_findings_for_unchanged_evidence():
    request, envelope = fixture()
    report = validate_audit(envelope, request, NOW)
    report.review.stories[0].verdict = "hold"
    assert reusable_story_checks(request, request, report)[0].verdict == "hold"
    report.review.stories[0].verdict = "pass"
    report.blockers.append("a: headline lacks checks")
    assert len(reusable_story_checks(request, request, report)) == 1
    report.review.stories[0].claims[0].verdict = "uncertain"
    assert repairable_ids(report) == ["a"]


def test_plain_prose_removes_internal_chunk_markers_without_changing_claims():
    from test_editorial import decision
    from news_collector.pipeline.editorial import ReviewBatch
    item = decision(summary='The company said revenue grew 10% [p1, p2]. It remains a claim [p3].')
    before = item.evidence.copy()
    result = plain_review_prose(ReviewBatch(decisions=[item])).decisions[0]
    assert result.summary == 'The company said revenue grew 10%. It remains a claim.'
    assert result.evidence == before


def test_selection_changes_reuse_only_unchanged_individual_story_checks():
    request, envelope = fixture()
    report = validate_audit(envelope, request, NOW)
    before = deepcopy(request)
    before['selection']['selected_ids'].append('b')
    before['packets'].append({**before['packets'][0], 'id': 'b'})
    before['decisions'].append({**before['decisions'][0], 'id': 'b'})
    assert [story.id for story in reusable_story_checks(before, request, report)] == ['a']
    assert [story.id for story in reusable_story_checks(request, before, report)] == ['a']
    changed = deepcopy(request)
    changed['packets'][0]['chunks'][0]['text'] = 'Changed evidence'
    assert reusable_story_checks(before, changed, report) == []


def test_new_discovery_requires_fresh_coverage_but_can_reuse_identical_factual_checks():
    request, envelope = fixture()
    report = validate_audit(envelope, request, NOW)
    changed = deepcopy(request)
    changed["checklist"]["events"][0]["event"] = "New independently researched coverage context"
    assert [story.id for story in reusable_story_checks(request, changed, report)] == ["a"]


def test_same_edition_retry_preserves_hold_when_only_clock_and_other_selections_change():
    from datetime import timedelta
    request, envelope = fixture()
    report = validate_audit(envelope, request, NOW)
    report.review.stories[0].verdict = "hold"
    later = deepcopy(request)
    later['cutoff'] = (NOW + timedelta(hours=1)).isoformat()
    later['selection']['selected_ids'].append('b')
    later['packets'].append({**deepcopy(later['packets'][0]), 'id': 'b'})
    later['decisions'].append({**deepcopy(later['decisions'][0]), 'id': 'b'})
    assert reusable_story_checks(request, later, report)[0].verdict == 'hold'
    later['cutoff'] = (NOW + timedelta(hours=24)).isoformat()
    assert reusable_story_checks(request, later, report) == []


@pytest.mark.parametrize('change', [None, 'evidence', 'prose', 'history', 'next_day', 'late_same_day'])
def test_archived_unchanged_hold_wins_over_a_later_accidental_approval(tmp_path, monkeypatch, change):
    from datetime import datetime, timedelta
    from news_collector.pipeline import quality_review
    from news_collector.pipeline.edition_audit import build_audit_request
    request, envelope = fixture()
    history = [{'id': 'yesterday', 'eventKey': 'bank-rate-decision'}]
    old = build_audit_request(request['packets'], request['decisions'], request['selection'],
                              history, request['checklist'], NOW - timedelta(hours=1))
    held = deepcopy(envelope)
    held.update(requestHash=old['requestHash'], reviewedAt=(NOW - timedelta(hours=1)).isoformat())
    held['review']['stories'][0].update(verdict='hold', priorStoryIds=['yesterday'])
    current = build_audit_request(old['packets'], old['decisions'], old['selection'], history, old['checklist'], NOW)
    accidental = deepcopy(envelope)
    accidental['requestHash'] = current['requestHash']
    accidental['review']['stories'][0]['event_key'] = 'mistaken-new-event-label'
    assert validate_audit(accidental, current, NOW).status == 'passed'
    (tmp_path / 'audit-record-a-held.json').write_text(json.dumps({'request': old, 'response': held}))
    (tmp_path / 'audit-record-z-passed.json').write_text(json.dumps({'request': current, 'response': accidental}))
    clock = type('Clock', (datetime,), {'now': classmethod(lambda cls, tz=None: NOW)})
    monkeypatch.setattr(quality_review, 'datetime', clock)
    monkeypatch.setattr('news_collector.pipeline.edition_audit.datetime', clock)
    if change == 'evidence':
        current['packets'][0]['chunks'][0]['text'] = 'Changed source facts'
    elif change == 'prose':
        current['decisions'][0]['summary'] = 'A changed draft needs its own audit.'
    elif change == 'history':
        current['history'].append({'id': 'another-published-story'})
    elif change == 'next_day':
        current['cutoff'] = (NOW + timedelta(days=1)).isoformat()
    elif change == 'late_same_day':
        current['cutoff'] = (NOW + timedelta(hours=7)).isoformat()
    reused = [] if change else quality_review.StoryAuditReview(stories=accidental['review']['stories']).stories
    checks = quality_review.archived_story_checks(tmp_path, current, reused, 'America/Los_Angeles')
    if change and change != 'late_same_day':
        assert checks == []
    else:
        assert checks[0].verdict == 'hold' and checks[0].priorStoryIds == ['yesterday']


@pytest.mark.parametrize('finding', ['approval', 'hold', 'incomplete_review', 'unresolved_claim'])
def test_late_same_day_reuses_blocks_but_expires_approvals(finding):
    from datetime import timedelta
    request, envelope = fixture()
    story = envelope['review']['stories'][0]
    if finding == 'hold':
        story['verdict'] = 'hold'
    elif finding == 'incomplete_review':
        story['attributionChecked'] = False
    elif finding == 'unresolved_claim':
        story['claims'][0]['verdict'] = 'uncertain'
    report = validate_audit(envelope, request, NOW)
    later = deepcopy(request)
    later['cutoff'] = (NOW + timedelta(hours=8)).isoformat()
    checks = reusable_story_checks(request, later, report)
    assert [check.id for check in checks] == ([] if finding == 'approval' else ['a'])
