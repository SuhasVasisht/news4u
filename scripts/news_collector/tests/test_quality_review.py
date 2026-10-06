from copy import deepcopy
from datetime import datetime
import json

import pytest

from news_collector.pipeline.publication_history import history_hash
from news_collector.pipeline.quality_review import audit_request, normalize_batch_ids, verify_final_audit
from news_collector.pipeline import quality_review
from test_edition_audit import fixture, NOW
from news_collector.pipeline.edition_audit import AuditReview, CoverageAuditReview, StoryAuditReview
from test_editorial import decision as editorial_decision


def reviewed_fixture():
    request, envelope = fixture()
    packet = {**request["packets"][0], "title": "Bank cuts rates", "url": "https://example.org/decision",
              "source": "bank", "wordCount": 300, "publishedAt": NOW.isoformat()}
    decision = {**request["decisions"][0], "reason": "Verified primary announcement"}
    review = {"packets": [packet], "decisions": {"a": decision}, "selection": request["selection"],
              "historyHash": history_hash([]), "generatedAt": NOW.isoformat(), "cutoff": NOW.isoformat()}
    bound = audit_request(review, [], request["checklist"])
    envelope["requestHash"] = bound["requestHash"]
    review["finalAudit"] = {"checklist": request["checklist"], "envelope": envelope}
    return review


def test_valid_final_audit_can_be_verified_at_export():
    assert verify_final_audit(reviewed_fixture(), [], NOW).status == "passed"


def test_export_requires_independent_audit():
    with pytest.raises(ValueError, match="required before export"):
        verify_final_audit({}, [], NOW)


def test_coverage_request_explains_pre_review_exclusions():
    review = reviewed_fixture()
    review["excluded"] = [{"url": "https://example.org/missed", "source": "bank", "reason": "candidate_budget"}]
    request = audit_request(review, [], review["finalAudit"]["checklist"])
    assert request["candidate_index"][-1]["decision"] == "excluded_before_review"
    assert request["candidate_index"][-1]["reason"] == "candidate_budget"


def test_story_batch_normalizes_one_character_opaque_id_typo():
    story = StoryAuditReview.model_validate({
        "stories": reviewed_fixture()["finalAudit"]["envelope"]["review"]["stories"]
    }).stories[0]
    story.id = "b"
    normalize_batch_ids([story], ["a"])
    assert story.id == "a"


def test_story_batch_rejects_reordered_known_ids():
    template = reviewed_fixture()["finalAudit"]["envelope"]["review"]["stories"][0]
    stories = StoryAuditReview.model_validate({"stories": [
        {**template, "id": "b"}, {**template, "id": "a"},
    ]}).stories
    with pytest.raises(ValueError, match="changed or reordered"):
        normalize_batch_ids(stories, ["a", "b"])


def test_interrupted_request_does_not_reuse_an_older_response(tmp_path, monkeypatch):
    review = reviewed_fixture()
    final = review.pop("finalAudit")
    output = tmp_path / "data/editorial"
    output.mkdir(parents=True)
    (output / "quality-review-request.json").write_text(json.dumps(
        audit_request(review, [], final["checklist"])))
    stale = deepcopy(final["envelope"])
    stale["requestHash"] = "older-edition"
    (output / "quality-review-response.json").write_text(json.dumps(stale))
    monkeypatch.setattr(quality_review, "load_history", lambda *_: [])
    monkeypatch.setattr(quality_review, "discover_coverage", lambda *_: final["checklist"])
    monkeypatch.setattr(quality_review, "reconsider_announcements", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(quality_review, "run_batched_audit", lambda *_: AuditReview.model_validate(final["envelope"]["review"]))
    clock = type("Clock", (datetime,), {
        "now": classmethod(lambda cls, tz=None: NOW),
    })
    monkeypatch.setattr(quality_review, "datetime", clock)
    monkeypatch.setattr("news_collector.pipeline.edition_audit.datetime", clock)
    assert quality_review.run_quality_review(tmp_path, review).status == "passed"


@pytest.mark.parametrize("passed", [True, False])
def test_quality_job_saves_metrics_but_only_replaces_draft_when_passed(tmp_path, monkeypatch, passed):
    review = reviewed_fixture()
    final = review.pop("finalAudit")
    monkeypatch.setattr(quality_review, "load_history", lambda *_: [])
    monkeypatch.setattr(quality_review, "discover_coverage", lambda *_: final["checklist"])
    if not passed:
        final["envelope"]["review"]["stories"][0]["verdict"] = "hold"
    source = tmp_path / "audit.json"
    source.write_text(json.dumps(final["envelope"]))
    output = tmp_path / "data/editorial"
    output.mkdir(parents=True)
    (output / "latest.json").write_text('{"previous": true}')
    # Bind this deterministic test to the evidence time, independent of the wall clock.
    real_validate = quality_review.validate_audit
    monkeypatch.setattr(quality_review, "validate_audit", lambda envelope, request: real_validate(envelope, request, NOW))
    if passed:
        quality_review.run_quality_review(tmp_path, review, audit_file=source)
        assert "finalAudit" in json.loads((output / "latest.json").read_text())
    else:
        with pytest.raises(ValueError, match="blocked publication"):
            quality_review.run_quality_review(tmp_path, review, audit_file=source)
        assert json.loads((output / "latest.json").read_text()) == {"previous": True}
    assert len(list((tmp_path / "data/quality/history").glob("*.json"))) == 1
    assert (output / "quality-review-response.json").exists()


@pytest.mark.parametrize("target", ["evidence", "summary", "candidate_reason"])
def test_final_gate_rejects_changes_after_review(target):
    review = deepcopy(reviewed_fixture())
    if target == "evidence":
        review["packets"][0]["chunks"][0]["text"] = "Changed evidence"
    else:
        review["decisions"]["a"]["summary" if target == "summary" else "reason"] = "Changed content"
    with pytest.raises(ValueError, match="does not match"):
        verify_final_audit(review, [], NOW)


def test_unrepairable_hold_does_not_spend_a_second_audit_or_bypass_publication(tmp_path, monkeypatch):
    review = reviewed_fixture()
    final = review.pop("finalAudit")
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW
    monkeypatch.setattr(quality_review, "datetime", Clock)
    monkeypatch.setattr("news_collector.pipeline.edition_audit.datetime", Clock)
    monkeypatch.setattr(quality_review, "load_history", lambda *_: [])
    checklist_inputs = []
    def coverage(output, cutoff, profile, source=None):
        checklist_inputs.append(source)
        return final["checklist"]
    monkeypatch.setattr(quality_review, "discover_coverage", coverage)
    monkeypatch.setattr(quality_review, "reconsider_announcements", lambda *_args, **_kwargs: None)
    calls = []
    def audit(payload, prompt, output, result_type, *, allow_web=False, validate_result=None):
        assert allow_web
        calls.append(payload)
        if result_type is StoryAuditReview:
            result = StoryAuditReview(stories=final["envelope"]["review"]["stories"])
            result.stories[0].verdict = "hold"
            if validate_result:
                validate_result(result)
            return result
        assert result_type is CoverageAuditReview
        return CoverageAuditReview(coverage=final["envelope"]["review"]["coverage"])
    monkeypatch.setattr(quality_review, "codex_review", audit)
    with pytest.raises(ValueError, match="blocked publication"):
        quality_review.run_quality_review(tmp_path, review)
    assert "finalAudit" not in json.loads((tmp_path / "data/editorial/latest.json").read_text())
    assert [call["auditMode"] for call in calls] == ["story_claims", "coverage_reconciliation"]
    assert checklist_inputs == [None]


def test_bounded_recheck_applies_first_audit_claim_findings(tmp_path, monkeypatch):
    review = reviewed_fixture()
    final = review.pop("finalAudit")
    review["decisions"]["a"] = editorial_decision(
        id="a", headline="Bank cuts rates", summary="The bank cut rates today.",
        points=[], evidence=["p1"]
    ).model_dump()
    review["packets"][0].update(wordCount=100, truncated=False, kind="reporting")
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW
    monkeypatch.setattr(quality_review, "datetime", Clock)
    monkeypatch.setattr("news_collector.pipeline.edition_audit.datetime", Clock)
    monkeypatch.setattr(quality_review, "load_history", lambda *_: [])
    monkeypatch.setattr(quality_review, "discover_coverage", lambda *_: final["checklist"])
    monkeypatch.setattr(quality_review, "reconsider_announcements", lambda *_args, **_kwargs: None)
    correction_inputs = []
    def correct(payload, prompt, output, result_type, **kwargs):
        correction_inputs.append(payload)
        original = payload["decisions"][0]
        return quality_review.ProseCorrections(corrections=[{
            "id": original["id"], "headline": "The bank cut rates today",
            "summary": original["summary"], "points": original["points"],
            "sections": original.get("sections", []), "caveats": original.get("caveats", []),
        }])
    monkeypatch.setattr(quality_review, "codex_review", correct)
    audits = []
    def audit(request, prompt, output, reused):
        audits.append((request, reused))
        result = deepcopy(final["envelope"]["review"])
        result["stories"][0]["claims"][0]["passage"] = request["decisions"][0]["headline"]
        if len(audits) == 1:
            result["stories"][0]["verdict"] = "hold"
            result["stories"][0]["claims"][0]["verdict"] = "unsupported"
            result["coverage"][0].update(status="missing", story_ids=[], cause="selection")
        return AuditReview.model_validate(result)
    monkeypatch.setattr(quality_review, "run_batched_audit", audit)

    result = quality_review.run_quality_review(tmp_path, review)

    assert result.status == "passed"
    assert len(audits) == 2
    assert correction_inputs[0]["findings"][0]["claims"][0]["verdict"] == "unsupported"
    assert audits[1][0]["decisions"][0]["headline"] == "The bank cut rates today"
