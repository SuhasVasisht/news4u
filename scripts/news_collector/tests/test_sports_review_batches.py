import pytest

from news_collector.jobs import sports
from test_editorial import packet, decision


def test_reviews_each_sport_and_reuses_only_validated_cache(tmp_path, monkeypatch):
    packets = [{**packet(), "id": group, "sportsGroup": group} for group in ("NFL", "NBA")]
    calls = []
    def review(payload, *_):
        calls.append(payload)
        return sports.SportsReview(decisions=[decision(id=p["id"]) for p in payload["packets"]])
    monkeypatch.setattr(sports, "codex_review", review)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Review each sport")
    request = {"packets": packets, "previouslyPublished": []}
    assert len(sports.review_candidates(request, prompt, tmp_path).decisions) == 2
    assert len(calls) == 2
    assert all(len(c["packets"]) == 1 for c in calls)
    sports.review_candidates(request, prompt, tmp_path)
    assert len(calls) == 2


def test_incomplete_sports_review_is_not_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(sports, "codex_review", lambda *_: sports.SportsReview(decisions=[]))
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Review")
    with pytest.raises(ValueError, match="every candidate"):
        sports.review_candidates({"packets": [{**packet(), "sportsGroup": "NFL"}], "previouslyPublished": []}, prompt, tmp_path)
    assert not list(tmp_path.glob("review-*.json"))
