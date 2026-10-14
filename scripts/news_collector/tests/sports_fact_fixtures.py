"""Deterministic auditor responses for sports pipeline contract tests."""
from news_collector.pipeline.edition_audit import StoryAuditReview
from news_collector.pipeline.editorial import Decision
from news_collector.pipeline.sports_facts import factual_request, factual_proof


def passing_checks(payload):
    return StoryAuditReview(stories=[{
        "id": decision["id"], "event_key": "sports-event-" + str(index), "verdict": "pass",
        "reason": "All published assertions match the source evidence.",
        "attributionChecked": True, "publicationDatesChecked": True, "promotional": False,
        "claims": [{"passage": text, "verdict": "supported", "critical": True,
                    "evidence": [payload["packets"][index]["chunks"][0]["id"]],
                    "reason": "This complete prose block matches the supplied source evidence."}
                   for text in [decision["headline"], decision["summary"], *decision["points"], *decision["caveats"],
                                *[text for section in decision["sections"] for text in (section["heading"], section["body"])]] if text],
        "priorStoryIds": [], "materialUpdate": None, "materialUpdateEvidence": []}
        for index, decision in enumerate(payload["decisions"])])


def attach_test_proof(request, review, now):
    payload = factual_request(request, [Decision.model_validate(item) for item in review["decisions"]],
                              review["selection"]["selected_ids"])
    proof = factual_proof(payload, passing_checks(payload))
    proof["reviewedAt"] = now.isoformat()
    review["factualAudit"] = proof
