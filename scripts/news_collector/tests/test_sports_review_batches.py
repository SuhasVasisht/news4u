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


def test_large_group_is_reviewed_in_bounded_batches(tmp_path, monkeypatch):
    packets = [{**packet(), "id": str(i), "sportsGroup": "Soccer"} for i in range(21)]
    sizes = []
    def review(payload, *_):
        sizes.append(len(payload["packets"]))
        return sports.SportsReview(decisions=[decision(id=p["id"]) for p in payload["packets"]])
    monkeypatch.setattr(sports, "codex_review", review)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Review")
    result = sports.review_candidates({"packets": packets, "previouslyPublished": []}, prompt, tmp_path)
    assert len(result.decisions) == 21
    assert sizes == [5, 5, 5, 5, 1]


def test_final_selection_caps_admissions_across_batches():
    decisions = [decision(id=str(i)) for i in range(5)]
    headlines = ["Arsenal win at Sunderland", "Barcelona sign a goalkeeper", "Milan dismiss their coach",
                 "Bayern report a defender injury", "Paris club opens a stadium"]
    summaries = ["A completed league match ended with an away victory.", "A veteran goalkeeper signed a confirmed contract.",
                 "The manager departed after a board decision.", "The defender will miss six weeks after surgery.",
                 "The new venue hosted its first competitive fixture."]
    for item, headline, summary in zip(decisions, headlines, summaries):
        item.headline, item.summary = headline, summary
    packets = {str(i): {"sportsGroup": "Soccer"} for i in range(5)}
    selected = sports.select_sports(decisions, packets)
    assert len(selected["selected_ids"]) == 3
    assert {item["id"] for item in selected["excluded"]} == {"3", "4"}


def test_final_selection_removes_cross_batch_duplicate_event():
    first = decision(id="a")
    first.headline = "Raya save and Guimaraes strike keep Arsenal winning"
    first.summary = "Arsenal won at Sunderland after David Raya saved a penalty and Bruno Guimaraes scored."
    second = decision(id="b")
    second.headline = "Raya and Guimaraes extend Arsenal winning run at Sunderland"
    second.summary = "David Raya saved a penalty before Bruno Guimaraes scored as Arsenal beat Sunderland."
    selected = sports.select_sports([first, second], {
        "a": {"sportsGroup": "Soccer"}, "b": {"sportsGroup": "Soccer"}})
    assert selected["selected_ids"] == ["a"]
    assert selected["excluded"][0]["id"] == "b"
