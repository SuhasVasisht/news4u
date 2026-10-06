"""Independent discovery and a final factual/coverage gate for the daily build."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from news_collector.pipeline.coverage_discovery import discover_coverage
from news_collector.pipeline.publishers import publisher, limit_publishers
from news_collector.pipeline.edition_audit import (AuditReview, CoverageAuditReview,
    StoryAuditReview, build_audit_request, validate_audit, require_publishable)
from news_collector.pipeline.editorial import codex_review, reader_profile, ReviewBatch, EditionSelection, validate_decisions
from news_collector.pipeline.publication_history import load_history, history_hash
from news_collector.pipeline.audit_repair import repairable_ids, reusable_story_checks, prunable_optional_ids, ProseCorrections, apply_corrections


def audit_request(review, history, checklist):
    if review["historyHash"] != history_hash(history):
        raise ValueError("Publication history changed before final audit")
    selected = set(review["selection"]["selected_ids"])
    index = [{"id": p["id"], "title": p["title"], "url": p["url"], "source": p["source"],
              "wordCount": p["wordCount"], "publishedAt": p["publishedAt"],
              "decision": review["decisions"][p["id"]]["decision"],
              "reason": review["decisions"][p["id"]]["reason"]} for p in review["packets"]]
    index.extend({**item, "decision": "excluded_before_review"} for item in review.get("excluded", []))
    return build_audit_request([p for p in review["packets"] if p["id"] in selected],
                              [d for key, d in review["decisions"].items() if key in selected],
                              review["selection"], history, checklist,
                              datetime.fromisoformat(review.get("cutoff", review["generatedAt"])),
                              candidate_index=index)


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temporary.replace(path)


def cached_audit(payload, prompt, output, result_type, validate):
    identity = {"version": 1, "payload": payload, "prompt": prompt.read_text(),
                "model": os.environ.get("NEWS_EDITOR_MODEL", "default"),
                "effort": os.environ.get("NEWS_EDITOR_REASONING_EFFORT", "default")}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    cache = output / "audit-calls" / f"{key}.json"
    if cache.exists():
        result = result_type.model_validate_json(cache.read_text())
        validate(result)
        print("Reusing validated audit call for unchanged evidence", flush=True)
        return result
    result = codex_review(payload, prompt, output, result_type, allow_web=True, validate_result=validate)
    validate(result)
    # Preserve holds as findings, not approvals. Repair/pruning must change the
    # inputs; repeated calls must not turn the same evidence into a lucky pass.
    atomic_json(cache, result.model_dump(mode="json"))
    return result


def normalize_batch_ids(stories, expected):
    """Repair only an unambiguous one-character transcription of an opaque ID."""
    if len(stories) != len(expected) or len({story.id for story in stories}) != len(stories):
        raise ValueError("Final audit story batch must check every requested ID exactly once")
    known = set(expected)
    for story, wanted in zip(stories, expected):
        if story.id == wanted:
            continue
        differences = sum(left != right for left, right in zip(story.id, wanted))
        if story.id in known or len(story.id) != len(wanted) or differences != 1:
            raise ValueError("Final audit story batch changed or reordered a requested ID")
        story.id = wanted
    if [story.id for story in stories] != expected:
        raise ValueError("Final audit story batch must preserve requested ID order")


def run_batched_audit(request, prompt, output, reused, batch_size=5):
    """Audit evidence in bounded calls, then reconcile coverage independently."""
    reused_ids = {story.id for story in reused}
    pending = [key for key in request["selection"]["selected_ids"] if key not in reused_ids]
    packets = {packet["id"]: packet for packet in request["packets"]}
    decisions = {decision["id"]: decision for decision in request["decisions"]}
    story_reviews = []
    for offset in range(0, len(pending), batch_size):
        ids = pending[offset:offset + batch_size]
        payload = {
            "auditMode": "story_claims",
            "policy": request["policy"],
            "cutoff": request["cutoff"],
            "auditStoryIds": ids,
            "packets": [packets[key] for key in ids],
            "decisions": [decisions[key] for key in ids],
            "history": request["history"],
            "selectedStoryIndex": [
                {"id": key, "headline": decisions[key]["headline"]}
                for key in request["selection"]["selected_ids"]
            ],
        }
        number = offset // batch_size + 1
        total = (len(pending) + batch_size - 1) // batch_size
        print(f"Final factual audit: story batch {number}/{total} ({len(ids)} stories)", flush=True)
        def validate_batch(result):
            normalize_batch_ids(result.stories, ids)
            # Validate citation/quotation contracts before accepting this call, so
            # malformed output gets the same bounded retry as schema violations.
            # Substantive holds remain findings for the complete audit and repair.
            partial = build_audit_request(payload["packets"], payload["decisions"],
                {"selected_ids": ids, "excluded": []}, request["history"], None,
                datetime.fromisoformat(request["cutoff"]))
            validate_audit({"requestHash": partial["requestHash"], "reviewer": "batch-contract-check",
                "reviewedAt": datetime.now(timezone.utc).isoformat(),
                "review": {"stories": [s.model_dump(mode="json") for s in result.stories], "coverage": []}}, partial)
        result = cached_audit(payload, prompt, output, StoryAuditReview, validate_batch)
        story_reviews.extend(result.stories)

    all_story_reviews = [*story_reviews, *reused]
    coverage_payload = {
        "auditMode": "coverage_reconciliation",
        "policy": request["policy"],
        "cutoff": request["cutoff"],
        "selection": request["selection"],
        "selectedStories": [
            {"id": key, "headline": decisions[key]["headline"],
             "summary": decisions[key]["summary"], "event_key": next(
                 story.event_key for story in all_story_reviews if story.id == key)}
            for key in request["selection"]["selected_ids"]
        ],
        "checklist": request["checklist"],
        "history": request["history"],
        "candidate_index": request["candidate_index"],
    }
    print(f"Final coverage audit: {len(request['checklist']['events']) if request['checklist'] else 0} independently discovered events", flush=True)
    def validate_coverage(result):
        validate_audit({"requestHash": request["requestHash"], "reviewer": "coverage-contract-check",
            "reviewedAt": datetime.now(timezone.utc).isoformat(),
            "review": {"stories": [s.model_dump(mode="json") for s in all_story_reviews],
                       "coverage": [c.model_dump(mode="json") for c in result.coverage]}}, request)
    coverage = cached_audit(coverage_payload, prompt, output, CoverageAuditReview, validate_coverage)
    validate_coverage(coverage)
    return AuditReview(stories=all_story_reviews, coverage=coverage.coverage)


def verify_final_audit(review, history, now=None):
    final = review.get("finalAudit")
    if not final:
        raise ValueError("Independent final edition audit is required before export")
    request = audit_request(review, history, final["checklist"])
    report = validate_audit(final["envelope"], request, now)
    require_publishable(report)
    return report


def reconsider_announcements(review, history, output, checklist=None, findings=None):
    prompt = Path(__file__).resolve().parents[2] / "config/announcement-review-prompt.md"
    promoted = False
    for packet in review["packets"]:
        initial = review["decisions"][packet["id"]]
        if (packet["kind"] != "announcement" or initial["decision"] != "hold"
                or packet["truncated"] or packet["wordCount"] < 80):
            continue
        payload = {"packets": [packet], "initialAssessment": initial}
        key = hashlib.sha256((json.dumps(payload, sort_keys=True) + prompt.read_text()
                              + json.dumps(reader_profile(), sort_keys=True)
                              + os.environ.get("NEWS_EDITOR_MODEL", "default")).encode()).hexdigest()
        cache = output / f"announcement-{key}.json"
        print(f"Reconsidering announcement evidence: {packet['id']}", flush=True)
        result = ReviewBatch.model_validate_json(cache.read_text()) if cache.exists() else codex_review(payload, prompt, output)
        validate_decisions(result, [packet])
        atomic_json(cache, result.model_dump(mode="json"))
        decision = result.decisions[0].model_dump(mode="json")
        if decision != initial:
            review["decisions"][packet["id"]] = decision
            promoted = promoted or decision["decision"] == "admit"
    if promoted or checklist:
        shortlist = [{**review["decisions"][p["id"]], "source": p["source"], "url": p["url"], "publishedAt": p["publishedAt"], "publisher": publisher(p["url"])}
                     for p in review["packets"] if review["decisions"][p["id"]]["decision"] == "admit"]
        selection_prompt = prompt.with_name("edition-selection-prompt.md")
        payload = {"shortlist": shortlist, "previouslyPublished": history}
        if checklist:
            payload["coverageChecklist"] = checklist
        if findings:
            payload["coverageFindings"] = findings
        key = hashlib.sha256((json.dumps(payload, sort_keys=True) + selection_prompt.read_text()
                              + json.dumps(reader_profile(), sort_keys=True)
                              + os.environ.get("NEWS_EDITOR_MODEL", "default")).encode()).hexdigest()
        cache = output / f"coverage-selection-{key}.json"
        print("Final selection: reconciling admitted stories with independent coverage", flush=True)
        selection = EditionSelection.model_validate_json(cache.read_text()) if cache.exists() else codex_review(payload, selection_prompt, output, EditionSelection)
        accounted = selection.selected_ids + [item.id for item in selection.excluded]
        if len(accounted) != len(set(accounted)) or set(accounted) != {p["id"] for p in shortlist} or len(selection.selected_ids) > 28:
            raise ValueError("Reconsidered selection must account for every admission once, maximum 28")
        atomic_json(cache, selection.model_dump(mode="json"))
        review["selection"] = limit_publishers(selection.model_dump(mode="json"), review["packets"])


def prune_optional_audit_failures(root, review, history, checklist, request, report, output, date):
    """Drop held optional stories only when their removal leaves coverage valid."""
    pruned = prunable_optional_ids(report, checklist)
    selected = review["selection"]["selected_ids"]
    if not pruned or len(selected) <= len(pruned):
        return None
    print(f"Dropping {len(pruned)} optional stories held by the final audit", flush=True)
    original = review
    review = deepcopy(review)
    review["selection"]["selected_ids"] = [key for key in selected if key not in pruned]
    review["selection"].setdefault("excluded", []).extend(
        {"id": key, "reason": "Held by the independent final factual audit; omitted without replacement"}
        for key in pruned)
    updated = audit_request(review, history, checklist)
    kept = [story for story in report.review.stories if story.id not in pruned]
    coverage = deepcopy(report.review.coverage)
    for item in coverage:
        if set(pruned).intersection(item.story_ids):
            # A removed factual hold cannot support coverage, even when another
            # mapped story remains. Record the omission conservatively.
            item.story_ids = []
            item.status = "missing"
            item.cause = "selection"
            item.reason = "Coverage removed because its selected story failed the independent factual audit."

    envelope = {"requestHash": updated["requestHash"],
                "reviewer": f"{report.reviewer}; fail-closed optional-story pruning",
                "reviewedAt": datetime.now(timezone.utc).isoformat(),
                "review": {"stories": [story.model_dump(mode="json") for story in kept],
                           "coverage": [item.model_dump(mode="json") for item in coverage]}}
    result = validate_audit(envelope, updated)
    original.clear()
    original.update(review)
    atomic_json(output / "quality-review-request.json", updated)
    atomic_json(output / "quality-review-response.json", envelope)
    atomic_json(output / "quality-audit.json", result.model_dump(mode="json"))
    atomic_json(root / "data/quality/history" / f"{date}-{updated['requestHash']}.json",
                result.model_dump(mode="json"))
    if result.status == "passed":
        review["finalAudit"] = {"checklist": checklist, "envelope": envelope}
        original["finalAudit"] = review["finalAudit"]
        atomic_json(output / "latest.json", review)
    return result


def run_quality_review(root, review, checklist_file=None, audit_file=None, _repair_attempt=0,
                      _previous_audit=None):
    output = root / "data/editorial"
    cutoff = datetime.fromisoformat(review.get("cutoff", review["generatedAt"]))
    profile = reader_profile()
    date = cutoff.astimezone(ZoneInfo(profile["timezone"])).date().isoformat()
    history = load_history(root, date)
    checklist = discover_coverage(output / "checklist.json", cutoff, profile, checklist_file)
    response_path = output / "quality-review-response.json"
    current_hash = audit_request(review, history, checklist)["requestHash"]
    already_selected = response_path.exists() and json.loads(response_path.read_text()).get("requestHash") == current_hash
    if not audit_file and not already_selected and not _repair_attempt:
        reconsider_announcements(review, history, output, checklist)
    review["selection"] = limit_publishers(review["selection"], review["packets"])
    request = audit_request(review, history, checklist)
    reused = []
    previous_path = output / "quality-review-request.json"
    response_path = output / "quality-review-response.json"
    if _previous_audit:
        previous_request, previous_report = _previous_audit
        reused = reusable_story_checks(previous_request, request, previous_report)
    elif not audit_file and previous_path.exists() and response_path.exists():
        previous_request = json.loads(previous_path.read_text())
        previous_response = json.loads(response_path.read_text())
        # An interrupted run can leave a new request beside an older response.
        # Only reuse a response that is bound to both the saved and current request.
        saved_hash = previous_request.get("requestHash")
        if previous_response.get("requestHash") == saved_hash:
            previous_report = validate_audit(previous_response, previous_request)
            atomic_json(output / f"audit-record-{previous_report.requestHash}.json",
                        {"request": previous_request, "response": previous_response})
            pruned_report = (prune_optional_audit_failures(
                root, review, history, checklist, request, previous_report, output, date)
                if saved_hash == request["requestHash"] else None)
            if pruned_report and pruned_report.status == "passed":
                return pruned_report
            request = audit_request(review, history, checklist)
            reused = reusable_story_checks(previous_request, request, previous_report)
    if not audit_file:
        review.pop("finalAudit", None)
        atomic_json(output / "latest.json", review)
    atomic_json(output / "quality-review-request.json", request)
    if audit_file:
        envelope = json.loads(Path(audit_file).read_text())
    else:
        prompt = Path(__file__).resolve().parents[2] / "config/edition-audit-prompt.md"
        pending = [key for key in request["selection"]["selected_ids"] if key not in {story.id for story in reused}]
        print(f"Final factual audit: {len(pending)} stories; {len(reused)} unchanged checks reused", flush=True)
        result = run_batched_audit(request, prompt, output, reused)
        envelope = {"requestHash": request["requestHash"], "reviewer": f"independent-final-desk; {len(reused)} unchanged checks reused",
                    "reviewedAt": datetime.now(timezone.utc).isoformat(), "review": result.model_dump(mode="json")}
    atomic_json(output / "quality-review-response.json", envelope)
    report = validate_audit(envelope, request)
    payload = report.model_dump(mode="json")
    atomic_json(output / "quality-audit.json", payload)
    atomic_json(root / "data/quality/history" / f"{date}-{request['requestHash']}.json", payload)
    if report.status == "blocked" and not audit_file and _repair_attempt:
        pruned_report = prune_optional_audit_failures(
            root, review, history, checklist, request, report, output, date)
        if pruned_report:
            if pruned_report.status == "passed":
                return pruned_report
            report = pruned_report
    if report.status == "blocked" and not audit_file and _repair_attempt == 0:
        ids = repairable_ids(report)
        missing_selection = [item.model_dump(mode="json") for item in report.review.coverage
                             if item.status == "missing" and item.cause == "selection"
                             and any(event["id"] == item.event_id and event["mustCover"]
                                     for event in checklist["events"])]
        if not ids and not missing_selection:
            pruned_report = prune_optional_audit_failures(
                root, review, history, checklist, request, report, output, date)
            if pruned_report and pruned_report.status == "passed":
                return pruned_report
            require_publishable(pruned_report or report)
        print("Final audit blocked publication; attempting one bounded repair and recheck", flush=True)
        if ids:
            packets = [packet for packet in review["packets"] if packet["id"] in ids]
            prompt = Path(__file__).resolve().parents[2] / "config/audit-repair-prompt.md"
            payload = {"packets": packets,
                       "decisions": [review["decisions"][key] for key in ids],
                       "findings": [story.model_dump(mode="json") for story in report.review.stories if story.id in ids]}
            print(f"Repairing {len(ids)} stories with unresolved claims", flush=True)
            corrections = codex_review(payload, prompt, output, ProseCorrections)
            repaired = apply_corrections(review["decisions"], corrections, packets)
            for decision in repaired.decisions:
                review["decisions"][decision.id] = decision.model_dump(mode="json")
        if missing_selection:
            reconsider_announcements(review, history, output, checklist, findings=missing_selection)
            atomic_json(output / "latest.json", review)
        atomic_json(output / "latest.json", review)
        # Reuse the exact checklist that produced this audit. Rediscovering coverage
        # during a repair can move the goalposts and waste a second research pass.
        return run_quality_review(root, review, output / "checklist.json", _repair_attempt=1,
                                  _previous_audit=(request, report))
    require_publishable(report)
    review["finalAudit"] = {"checklist": checklist, "envelope": envelope}
    atomic_json(output / "latest.json", review)
    return report
