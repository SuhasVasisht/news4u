from copy import deepcopy
import json

import pytest

from news_collector.pipeline.publication_history import history_hash
from news_collector.pipeline.quality_review import audit_request, verify_final_audit
from news_collector.pipeline import quality_review
from test_edition_audit import fixture, NOW


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
