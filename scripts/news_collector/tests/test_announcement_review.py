from copy import deepcopy

import pytest

from news_collector.pipeline import quality_review as quality
from news_collector.pipeline.editorial import ReviewBatch, EditionSelection
from test_editorial import packet, decision


def draft():
    return {"packets": [{**packet(), "kind": "announcement"}],
            "decisions": {"one": decision(decision="hold", kind="announcement", quality=0).model_dump()},
            "selection": {"selected_ids": [], "excluded": []}}


def test_reconsideration_is_evidence_checked_cached_and_reselected(tmp_path, monkeypatch):
    calls = []
    def review(payload, prompt, output, result_type=ReviewBatch):
        calls.append(result_type)
        if result_type is EditionSelection:
            assert payload["shortlist"][0]["id"] == "one"
            return EditionSelection(selected_ids=["one"], excluded=[])
        return ReviewBatch(decisions=[decision(kind="announcement")])
    monkeypatch.setattr(quality, "codex_review", review)
    value = draft()
    quality.reconsider_announcements(value, [], tmp_path)
    assert value["decisions"]["one"]["decision"] == "admit"
    assert value["selection"]["selected_ids"] == ["one"]
    quality.reconsider_announcements(draft(), [], tmp_path)
    assert calls.count(ReviewBatch) == 1


def test_reconsideration_cannot_promote_failed_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(quality, "codex_review", lambda *_: ReviewBatch(decisions=[decision(quality=10)]))
    with pytest.raises(ValueError, match="completeness gate"):
        quality.reconsider_announcements(draft(), [], tmp_path)
    assert not list(tmp_path.glob("announcement-*.json"))


@pytest.mark.parametrize("change", ["rejected", "truncated", "short", "reporting"])
def test_only_complete_held_announcements_are_reconsidered(tmp_path, monkeypatch, change):
    value = draft()
    if change == "rejected":
        value["decisions"]["one"]["decision"] = "reject"
    elif change == "truncated":
        value["packets"][0]["truncated"] = True
    elif change == "short":
        value["packets"][0]["wordCount"] = 20
    else:
        value["packets"][0]["kind"] = "reporting"
    before = deepcopy(value)
    monkeypatch.setattr(quality, "codex_review", lambda *_: pytest.fail("Unexpected review"))
    quality.reconsider_announcements(value, [], tmp_path)
    assert value == before
