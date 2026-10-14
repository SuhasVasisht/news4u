from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest

from news_collector.jobs import sports as job
from news_collector.pipeline import quality_review, sports
from news_collector.pipeline.audit_repair import ProseCorrections
from news_collector.pipeline.editorial import Decision
from news_collector.pipeline.sports_facts import factual_request, verify_factual_proof
from sports_fact_fixtures import passing_checks
from test_editorial import packet, decision
from test_sports import review_fixture, NOW


def england_request():
    now = datetime.now(timezone.utc).isoformat()
    evidence = {**packet(), "sportsGroup": "Soccer", "publishedAt": now,
                "chunks": [{"id": "p1", "text": "England scored four goals in the first half. James scored twice, Russo once and Stanway once."},
                           {"id": "p2", "text": "Russo scored again late in the second half. England won 5-0 and advanced 8-1 on aggregate."}]}
    request = {"generatedAt": now, "requestHash": "bound-source-request", "packets": [evidence], "previouslyPublished": []}
    proposed = decision(summary="England beat Greece 4-0. James and Russo scored twice each, and Stanway scored once.")
    return request, proposed, {"selected_ids": [proposed.id], "excluded": []}


def install_auditor(monkeypatch):
    calls = []
    def audit(payload, _prompt, _output, result_type, **kwargs):
        calls.append(payload)
        result = passing_checks(payload)
        if "4-0" in payload["decisions"][0]["summary"]:
            result.stories[0].verdict = "hold"
            result.stories[0].claims[1].verdict = "unsupported"
            result.stories[0].claims[1].reason = "Four goals describes the first half; the later Russo goal made the final score 5-0."
            result.stories[0].claims[1].evidence = ["p1", "p2"]
        return result
    monkeypatch.setattr(quality_review, "codex_review", audit)
    return calls


def install_repair(monkeypatch, unchanged=False):
    calls = []
    def repair(payload, _prompt, _output, result_type, **kwargs):
        assert result_type is ProseCorrections
        calls.append(payload)
        original = payload["decisions"][0]
        summary = original["summary"] if unchanged else original["summary"].replace("4-0", "5-0")
        return ProseCorrections(corrections=[{key: (summary if key == "summary" else original[key])
            for key in ("id", "headline", "summary", "points", "sections", "caveats")}])
    monkeypatch.setattr(job, "codex_review", repair)
    return calls


def test_actual_halftime_final_score_error_is_repaired_then_independently_reaudited(tmp_path, monkeypatch):
    request, proposed, selection = england_request()
    audits = install_auditor(monkeypatch)
    repairs = install_repair(monkeypatch)
    decisions, final, proof = job.audit_selected_sports(request, [proposed], selection, tmp_path)
    assert "5-0" in decisions[0].summary
    assert final["selected_ids"] == [proposed.id]
    assert len(audits) == 2 and len(repairs) == 1
    assert "4-0" in audits[0]["decisions"][0]["summary"]
    assert "5-0" in audits[1]["decisions"][0]["summary"]
    verify_factual_proof(proof, datetime.now(timezone.utc), expected=factual_request(request, decisions, final["selected_ids"]))
    # Retry the original unapproved draft: held work, repair and corrected audit
    # are reused rather than asking for a lucky approval of the same bad prose.
    resumed, _, _ = job.audit_selected_sports(request, [proposed], selection, tmp_path)
    assert resumed[0].summary == decisions[0].summary
    assert len(audits) == 2 and len(repairs) == 1


def test_unchanged_repair_cannot_turn_a_cached_hold_into_a_pass_or_empty_success(tmp_path, monkeypatch):
    request, proposed, selection = england_request()
    audits = install_auditor(monkeypatch)
    repairs = install_repair(monkeypatch, unchanged=True)
    for _ in range(2):
        with pytest.raises(ValueError, match="no publishable"):
            job.audit_selected_sports(request, [proposed], selection, tmp_path)
    assert len(audits) == 1 and len(repairs) == 1


def test_invalid_factual_cache_is_regenerated_without_discarding_valid_held_work(tmp_path, monkeypatch):
    request, proposed, selection = england_request()
    audits = install_auditor(monkeypatch)
    repairs = install_repair(monkeypatch)
    job.audit_selected_sports(request, [proposed], selection, tmp_path)
    for cache in (tmp_path / "audit-calls").glob("*.json"):
        value = json.loads(cache.read_text())
        if value["stories"][0]["verdict"] == "pass":
            value["stories"][0]["claims"][0]["evidence"] = ["unknown-source-chunk"]
            cache.write_text(json.dumps(value))
    updated, _, proof = job.audit_selected_sports(request, [proposed], selection, tmp_path)
    assert "5-0" in updated[0].summary
    assert len(audits) == 3 and len(repairs) == 1
    verify_factual_proof(proof, datetime.now(timezone.utc))


@pytest.mark.parametrize("damage", ["missing_block", "unknown_citation", "substring_passage", "missing_story"])
def test_factual_contract_requires_every_complete_block_and_known_evidence(damage):
    from news_collector.pipeline.sports_facts import validate_factual_checks
    request, proposed, selection = england_request()
    payload = factual_request(request, [proposed], selection["selected_ids"])
    checks = passing_checks(payload)
    if damage == "missing_block":
        checks.stories[0].claims.pop()
    elif damage == "unknown_citation":
        checks.stories[0].claims[0].evidence = ["not-supplied"]
    elif damage == "substring_passage":
        checks.stories[0].claims[0].passage = checks.stories[0].claims[0].passage[:5]
    else:
        checks.stories = []
    with pytest.raises(ValueError):
        validate_factual_checks(checks, payload)


@pytest.mark.parametrize("damage", ["prose", "source", "selection", "proof", "claim"])
def test_final_publication_requires_the_exact_fact_audited_sports_artifact(tmp_path, monkeypatch, damage):
    settings, request, review = review_fixture(tmp_path, monkeypatch)
    if damage == "prose":
        review["decisions"][0]["summary"] = "An unreviewed score was added."
    elif damage == "source":
        request["packets"][0]["chunks"][0]["text"] = "Different source evidence"
        request["requestHash"] = sports.fingerprint({key: value for key, value in request.items() if key != "requestHash"})
        review["requestHash"] = request["requestHash"]
    elif damage == "selection":
        review["factualAudit"]["input"]["auditStoryIds"] = ["not-selected"]
    elif damage == "proof":
        review.pop("factualAudit")
    else:
        review["factualAudit"]["review"]["stories"][0]["claims"][0]["verdict"] = "unsupported"
    with pytest.raises(ValueError, match="factual audit"):
        sports.publish_sports(request, review, settings, None, NOW, "America/Los_Angeles")


@pytest.mark.parametrize("damage", ["missing_proof", "summary", "source_date", "source_request"])
def test_export_rechecks_sports_factual_proof_and_exact_published_fields(tmp_path, monkeypatch, damage):
    settings, request, review = review_fixture(tmp_path, monkeypatch)
    snapshot = sports.publish_sports(request, review, settings, None, NOW, "America/Los_Angeles")
    edition = {"date": snapshot["date"], "stories": [], "sources": []}
    sports.attach_sports(edition, snapshot, NOW)
    changed = deepcopy(snapshot)
    if damage == "missing_proof":
        changed.pop("factualAudit")
    elif damage == "summary":
        changed["stories"][0]["summary"] = "Different unaudited final score."
    elif damage == "source_date":
        changed["stories"][0]["publishedAt"] = "2026-09-01T12:00:00Z"
    else:
        changed["requestHash"] = "another-source-request"
    with pytest.raises(ValueError, match="factual audit|fact-audited"):
        sports.attach_sports({"date": snapshot["date"], "stories": [], "sources": []}, changed, NOW)
