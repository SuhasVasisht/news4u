"""Independent discovery and a final factual/coverage gate for the daily build."""
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from news_collector.pipeline.coverage_discovery import discover_coverage
from news_collector.pipeline.edition_audit import AuditReview, build_audit_request, validate_audit, require_publishable
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


def verify_final_audit(review, history, now=None):
    final = review.get("finalAudit")
    if not final:
        raise ValueError("Independent final edition audit is required before export")
    request = audit_request(review, history, final["checklist"])
    report = validate_audit(final["envelope"], request, now)
    require_publishable(report)
    return report


def reconsider_announcements(review, history, output, checklist=None):
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
        shortlist = [{**review["decisions"][p["id"]], "source": p["source"], "url": p["url"], "publishedAt": p["publishedAt"]}
                     for p in review["packets"] if review["decisions"][p["id"]]["decision"] == "admit"]
        selection_prompt = prompt.with_name("edition-selection-prompt.md")
        payload = {"shortlist": shortlist, "previouslyPublished": history}
        if checklist:
            payload["coverageChecklist"] = checklist
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
        review["selection"] = selection.model_dump(mode="json")


def run_quality_review(root, review, checklist_file=None, audit_file=None, _repair_attempt=0):
    output = root / "data/editorial"
    cutoff = datetime.fromisoformat(review.get("cutoff", review["generatedAt"]))
    profile = reader_profile()
    date = cutoff.astimezone(ZoneInfo(profile["timezone"])).date().isoformat()
    history = load_history(root, date)
    checklist = discover_coverage(output / "checklist.json", cutoff, profile, checklist_file)
    response_path = output / "quality-review-response.json"
    current_hash = audit_request(review, history, checklist)["requestHash"]
    already_selected = response_path.exists() and json.loads(response_path.read_text()).get("requestHash") == current_hash
    if not audit_file and not already_selected:
        reconsider_announcements(review, history, output, checklist)
    request = audit_request(review, history, checklist)
    reused = []
    previous_path = output / "quality-review-request.json"
    response_path = output / "quality-review-response.json"
    if not audit_file and previous_path.exists() and response_path.exists():
        previous_request = json.loads(previous_path.read_text())
        previous_response = json.loads(response_path.read_text())
        # An interrupted recheck may have written its new request but not a new
        # response. Recover the original pair only when its hash still matches.
        if previous_response.get("requestHash") == request["requestHash"]:
            previous_request = request
        if previous_request.get("requestHash") == request["requestHash"]:
            previous_report = validate_audit(previous_response, previous_request)
            atomic_json(output / f"audit-record-{previous_report.requestHash}.json",
                        {"request": previous_request, "response": previous_response})
            pruned = prunable_optional_ids(previous_report, checklist)
            if pruned:
                print(f"Dropping {len(pruned)} optional stories held by the final audit; no replacements added", flush=True)
                review["selection"]["selected_ids"] = [key for key in review["selection"]["selected_ids"] if key not in pruned]
                review["selection"].setdefault("excluded", []).extend(
                    {"id": key, "reason": "Held by the independent final factual audit; omitted without replacement"}
                    for key in pruned)
                request = audit_request(review, history, checklist)
                kept = [story for story in previous_report.review.stories if story.id not in pruned]
                envelope = {"requestHash": request["requestHash"],
                            "reviewer": f"{previous_report.reviewer}; fail-closed optional-story pruning",
                            "reviewedAt": datetime.now(timezone.utc).isoformat(),
                            "review": {"stories": [story.model_dump(mode="json") for story in kept],
                                       "coverage": [item.model_dump(mode="json") for item in previous_report.review.coverage]}}
                atomic_json(output / "quality-review-request.json", request)
                atomic_json(output / "quality-review-response.json", envelope)
                report = validate_audit(envelope, request)
                require_publishable(report)
                atomic_json(output / "quality-audit.json", report.model_dump(mode="json"))
                atomic_json(root / "data/quality/history" / f"{date}-{request['requestHash']}.json",
                            report.model_dump(mode="json"))
                review["finalAudit"] = {"checklist": checklist, "envelope": envelope}
                atomic_json(output / "latest.json", review)
                return report
            ids = repairable_ids(previous_report)
            if ids:
                prompt = Path(__file__).resolve().parents[2] / "config/audit-repair-prompt.md"
                packets = [packet for packet in review["packets"] if packet["id"] in ids]
                payload = {"packets": packets, "decisions": [review["decisions"][key] for key in ids],
                           "findings": [story.model_dump(mode="json") for story in previous_report.review.stories if story.id in ids]}
                print(f"Repairing {len(ids)} stories with unresolved claims", flush=True)
                corrections = codex_review(payload, prompt, output, ProseCorrections)
                repaired = apply_corrections(review["decisions"], corrections, packets)
                for decision in repaired.decisions:
                    review["decisions"][decision.id] = decision.model_dump(mode="json")
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
        payload = {**request, "auditStoryIds": pending,
                   "verifiedStoryReviews": [story.model_dump(mode="json") for story in reused]}
        print(f"Final factual audit: {len(pending)} stories; {len(reused)} unchanged checks reused", flush=True)
        result = codex_review(payload, prompt, output, AuditReview, allow_web=True)
        if sorted(story.id for story in result.stories) != sorted(pending):
            raise ValueError("Final audit must check every pending story exactly once")
        result.stories.extend(reused)
        envelope = {"requestHash": request["requestHash"], "reviewer": f"independent-final-desk; {len(reused)} unchanged checks reused",
                    "reviewedAt": datetime.now(timezone.utc).isoformat(), "review": result.model_dump(mode="json")}
    atomic_json(output / "quality-review-response.json", envelope)
    report = validate_audit(envelope, request)
    payload = report.model_dump(mode="json")
    atomic_json(output / "quality-audit.json", payload)
    atomic_json(root / "data/quality/history" / f"{date}-{request['requestHash']}.json", payload)
    if report.status == "blocked" and not audit_file and _repair_attempt == 0:
        print("Final audit blocked publication; attempting one bounded repair and recheck", flush=True)
        return run_quality_review(root, review, checklist_file, _repair_attempt=1)
    require_publishable(report)
    review["finalAudit"] = {"checklist": checklist, "envelope": envelope}
    atomic_json(output / "latest.json", review)
    return report
