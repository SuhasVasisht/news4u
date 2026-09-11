"""Independent discovery and a final factual/coverage gate for the daily build."""
from datetime import datetime, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from news_collector.pipeline.coverage_discovery import discover_coverage
from news_collector.pipeline.edition_audit import AuditReview, build_audit_request, validate_audit, require_publishable
from news_collector.pipeline.editorial import codex_review, reader_profile
from news_collector.pipeline.publication_history import load_history, history_hash


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


def run_quality_review(root, review, checklist_file=None, audit_file=None):
    output = root / "data/editorial"
    cutoff = datetime.fromisoformat(review.get("cutoff", review["generatedAt"]))
    profile = reader_profile()
    date = cutoff.astimezone(ZoneInfo(profile["timezone"])).date().isoformat()
    history = load_history(root, date)
    checklist = discover_coverage(output / "checklist.json", cutoff, profile, checklist_file)
    request = audit_request(review, history, checklist)
    atomic_json(output / "quality-review-request.json", request)
    if audit_file:
        envelope = json.loads(Path(audit_file).read_text())
    else:
        prompt = Path(__file__).resolve().parents[2] / "config/edition-audit-prompt.md"
        result = codex_review(request, prompt, output, AuditReview)
        envelope = {"requestHash": request["requestHash"], "reviewer": "independent-final-desk",
                    "reviewedAt": datetime.now(timezone.utc).isoformat(), "review": result.model_dump(mode="json")}
    atomic_json(output / "quality-review-response.json", envelope)
    report = validate_audit(envelope, request)
    payload = report.model_dump(mode="json")
    atomic_json(output / "quality-audit.json", payload)
    atomic_json(root / "data/quality/history" / f"{date}-{request['requestHash']}.json", payload)
    require_publishable(report)
    review["finalAudit"] = {"checklist": checklist, "envelope": envelope}
    atomic_json(output / "latest.json", review)
    return report
