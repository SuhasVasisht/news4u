import pytest

from news_collector.pipeline.editorial import Decision, validate_ranking_review


def review(reason="Held at edition screening: lower incremental value", **changes):
    packets = [{"id": str(i), "wordCount": 500, "truncated": False} for i in range(4)]
    decisions = [Decision(id=p["id"], decision="hold", quality=0, importance=0,
                          kind="reporting", reason=reason, headline="", summary="",
                          points=[], sections=[], caveats=[], evidence=[], duplicate_of=None)
                 .model_copy(update=changes) for p in packets]
    return decisions, packets


def test_bulk_unscored_priority_dismissals_fail_before_selection():
    with pytest.raises(ValueError, match="Blanket ranking holds"):
        validate_ranking_review(*review())


def test_scored_and_item_specific_editorial_decisions_remain_valid():
    validate_ranking_review(*review(quality=70, importance=35))
    decisions, packets = review()
    for i, decision in enumerate(decisions):
        decision.reason += f": event {i} was already covered in yesterday's report"
    validate_ranking_review(decisions, packets)


def test_evidence_failures_promotions_and_explicit_duplicates_are_not_ranking_failures():
    validate_ranking_review(*review(reason="Sponsor copy and affiliate promotion, no reporting"))
    validate_ranking_review(*review(reason="Paywall prevents verifying claims"))
    validate_ranking_review(*review(duplicate_of="other"))
    decisions, packets = review()
    for packet in packets:
        packet["wordCount"] = 30
    validate_ranking_review(decisions, packets)
    for packet in packets:
        packet.update(wordCount=500, truncated=True)
    validate_ranking_review(decisions, packets)
