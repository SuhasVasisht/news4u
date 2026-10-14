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


def test_invalid_cached_evidence_is_discarded_and_regenerated(tmp_path, monkeypatch):
    candidate = {**packet(), "sportsGroup": "NFL"}
    request = {"packets": [candidate], "previouslyPublished": []}
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Review")
    payload = {"packets": [candidate], "previouslyPublished": []}
    key = sports.fingerprint({"input": payload, "prompt": prompt.read_text(), "profile": sports.reader_profile(),
                              "model": __import__("os").environ.get("NEWS_EDITOR_MODEL", "default")})
    stale = sports.SportsReview(decisions=[decision(id=candidate["id"], evidence=["not-in-packet"])])
    (tmp_path / f"review-{key}.json").write_text(stale.model_dump_json())
    calls = []
    monkeypatch.setattr(sports, "codex_review", lambda *_: calls.append(True) or sports.SportsReview(
        decisions=[decision(id=candidate["id"])]))
    result = sports.review_candidates(request, prompt, tmp_path)
    assert len(calls) == 1
    assert result.decisions[0].evidence == ["p1"]


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


def test_stale_request_is_regenerated_before_any_model_review(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    settings = SimpleNamespace(project_root=tmp_path / 'scripts/news_collector')
    output = tmp_path / 'data/sports'
    output.mkdir(parents=True)
    (output / 'review-request.json').write_text(json.dumps({'policy': 'old'}))
    calls = []
    monkeypatch.setattr('sys.argv', ['sports-job'])
    monkeypatch.setattr(sports, 'build_runtime', lambda: (settings, {}, None, None))
    monkeypatch.setattr(sports, 'config_for', lambda *_: {'enabled': True})
    def validate(*args):
        calls.append('validate')
        raise ValueError('Sports policy changed')
    monkeypatch.setattr(sports, 'validate_sports_request', validate)
    def prepare(*args):
        calls.append('prepare')
        return {'policy': 'new', 'packets': [], 'requestHash': 'fresh'}
    monkeypatch.setattr(sports, 'prepare_sports', prepare)
    def review(request, *args):
        assert request['policy'] == 'new'
        calls.append('review')
        return sports.SportsReview(decisions=[])
    monkeypatch.setattr(sports, 'review_candidates', review)
    monkeypatch.setattr(sports, 'publish_sports', lambda *args: {'stories': [], 'sports': {'checkedAt': 'now'}})
    sports.main()
    assert calls == ['validate', 'prepare', 'review']


def test_final_event_review_handles_different_headlines_and_caches_validated_selection(tmp_path, monkeypatch):
    from news_collector.pipeline.editorial import EditionSelection
    first = decision(id='a', headline='Player prepares for final national-team appearance')
    second = decision(id='b', headline='A celebrated international career reaches its conclusion')
    packets = [{**packet(), 'id': key, 'sportsGroup': 'Soccer'} for key in ('a', 'b')]
    request = {'packets': packets, 'previouslyPublished': []}
    calls = []
    def review(payload, *args):
        calls.append(payload)
        return EditionSelection(selected_ids=['a'], excluded=[{'id': 'b', 'reason': 'Same farewell event already represented'}])
    monkeypatch.setattr(sports, 'codex_review', review)
    prompt = tmp_path / 'events.md'
    prompt.write_text('One account per sports event')
    result = sports.reconcile_sports_events(request, [first, second], prompt, tmp_path)
    assert result['selected_ids'] == ['a']
    assert result['excluded'][0]['id'] == 'b'
    assert sports.reconcile_sports_events(request, [first, second], prompt, tmp_path) == result
    assert len(calls) == 1
    assert calls[0]['shortlist'][0]['sportsGroup'] == 'Soccer'


@pytest.mark.parametrize("second_group", ["NFL", "Elsewhere"])
def test_model_selected_overlaps_are_resolved_before_publication_and_cache_resume(tmp_path, monkeypatch, second_group):
    from news_collector.pipeline.editorial import Decision, EditionSelection
    from news_collector.pipeline import sports as sports_pipeline
    from test_sports import review_fixture, NOW
    settings, request, response = review_fixture(tmp_path, monkeypatch, 2)
    request["previouslyPublished"] = []
    request["packets"][1]["sportsGroup"] = second_group
    request["requestHash"] = sports.fingerprint({key: value for key, value in request.items() if key != "requestHash"})
    response["requestHash"] = request["requestHash"]
    for item in response["decisions"]:
        item["headline"] = "Quarterback returns from injury before Sunday's game"
        item["summary"] = "The quarterback returned to practice after recovering from a shoulder injury."
    response["decisions"][0]["importance"] = 80
    decisions = [Decision.model_validate(item) for item in response["decisions"]]
    calls = []
    monkeypatch.setattr(sports, "codex_review", lambda *_: calls.append(True) or EditionSelection(
        selected_ids=["0", "1"], excluded=[]))
    prompt = tmp_path / "events.md"
    prompt.write_text("Choose distinct sports events")
    selection = sports.reconcile_sports_events(request, decisions, prompt, tmp_path)
    assert selection["selected_ids"] == ["0"]
    assert {item["id"] for item in selection["excluded"]} == {"1"}
    assert sports.reconcile_sports_events(request, decisions, prompt, tmp_path) == selection
    assert len(calls) == 1
    response["selection"] = selection
    result = sports_pipeline.publish_sports(request, response, settings, None, NOW, "America/Los_Angeles")
    assert [story["id"] for story in result["stories"]] == ["0"]
