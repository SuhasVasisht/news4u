from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from news_collector.pipeline import sports

NOW = datetime(2026, 9, 10, 3, tzinfo=timezone.utc)


def event(state="post", completed=True, date=None):
    return {"id": "1", "date": (date or NOW - timedelta(hours=2)).isoformat(),
            "status": {"type": {"state": state, "completed": completed, "detail": "Final"}},
            "competitions": [{"competitors": [
                {"homeAway": "home", "team": {"displayName": "Home"}, "score": "21"},
                {"homeAway": "away", "team": {"displayName": "Away"}, "score": "17"},
            ]}], "links": [{"href": "https://www.espn.com/nfl/game/_/gameId/1"}]}


def parse(*events):
    return sports.score_games({"events": list(events)}, NOW - timedelta(hours=24), NOW + timedelta(hours=24), NOW)


def test_scores_keep_home_away_final_and_timezone_window():
    games = parse(event(), event(), event(date=NOW - timedelta(hours=25)))
    assert len(games) == 1
    assert games[0]["home"] == {"name": "Home", "score": "21"}
    assert games[0]["away"]["score"] == "17"
    assert games[0]["completed"]


def test_scheduled_games_have_no_scores_and_live_is_not_final():
    scheduled = parse(event("pre", False, NOW + timedelta(hours=3)))[0]
    assert scheduled["home"]["score"] is None
    live = parse(event("in", False))[0]
    assert live["state"] == "in" and not live["completed"]
    with pytest.raises(ValueError, match="Future"):
        parse(event(date=NOW + timedelta(hours=3)))
    with pytest.raises(ValueError, match="state"):
        parse(event("in", True))


def test_empty_schedule_is_valid_but_broken_payload_and_missing_scores_are_not():
    assert parse() == []
    with pytest.raises(ValueError, match="events"):
        sports.score_games({}, NOW, NOW, NOW)
    broken = event()
    broken["competitions"][0]["competitors"][0].pop("score")
    with pytest.raises(ValueError, match="score"):
        parse(broken)


def standing_entry(team, rank, wins=10):
    return {"team": {"displayName": team}, "stats": [{"name": k, "value": v, "displayValue": str(v)} for k, v in {"playoffSeed": rank, "wins": wins, "losses": 0}.items()]}


def test_standings_use_provider_rank_not_unsorted_api_order_and_keep_season():
    data = {"children": [{"name": "Eastern Conference", "standings": {"seasonDisplayName": "2025-26", "entries": [standing_entry("Third", 3), standing_entry("First", 1), standing_entry("Second", 2)]}}]}
    table = sports.standings_tables(data, "NBA")[0]
    assert table["season"] == "2025-26"
    assert [r["team"] for r in table["rows"]] == ["First", "Second", "Third"]
    assert table["rows"][0]["record"] == "10-0"
    for e in data["children"][0]["standings"]["entries"]:
        e["stats"] = standing_entry(e["team"]["displayName"], 1, 0)["stats"]
    assert not sports.standings_tables(data, "NFL")[0]["started"]


def test_score_feed_error_is_not_reported_as_no_games():
    class Broken:
        def get(self, *args, **kwargs):
            raise RuntimeError("Unavailable")
    result, health = sports.collect_scores({"leagues": [{"id": "nba", "group": "NBA", "name": "NBA", "path": "basketball/nba", "url": "https://www.espn.com/nba/scoreboard"}]}, NOW, Broken())
    assert result["leagues"][0]["scheduleStatus"] == "unavailable"
    assert all(h["status"] == "error" for h in health)


def review_fixture(tmp_path, monkeypatch, number=1):
    settings = SimpleNamespace(project_root=tmp_path / "scripts/news_collector", user_agent="Test")
    config_dir = settings.project_root / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "sports-prompt.md").write_text("Test policy")
    monkeypatch.setattr(sports, "config_for", lambda _: {"enabled": True})
    monkeypatch.setattr(sports, "quality_image", lambda *_: {"image": None})
    packets = [{"id": str(i), "url": f"https://www.espn.com/nfl/story/{i}", "title": f"Report {i}", "source": "espn_nfl", "sportsGroup": "NFL", "kind": "reporting", "wordCount": 100, "truncated": False, "chunks": [{"id": "p1", "text": "Evidence " * 100}], "publishedAt": NOW.isoformat(), "basis": "Publisher article"} for i in range(number)]
    request = {"date": "2026-09-09", "generatedAt": NOW.isoformat(), "packets": packets, "scores": {"checkedAt": NOW.isoformat(), "leagues": []}, "sources": [], "policy": sports.fingerprint({"version": sports.SPORTS_REQUEST_VERSION, "config": {"enabled": True}, "prompt": "Test policy"}), "historyHash": sports.history_hash([])}
    request["requestHash"] = sports.fingerprint(request)
    decisions = [{"id": p["id"], "decision": "admit", "quality": 80, "importance": 60, "kind": "reporting", "reason": "Supported", "headline": ["Quarterback returns from injury", "Franchise sale wins approval", "Championship winner announced"][i], "summary": "A concise supported report.", "points": [], "sections": [], "caveats": [], "evidence": ["p1"], "duplicate_of": None} for i, p in enumerate(packets)]
    review = {"requestHash": request["requestHash"], "reviewer": "Test desk", "reviewedAt": NOW.isoformat(), "decisions": decisions, "selection": {"selected_ids": [p["id"] for p in packets], "excluded": []}}
    return settings, request, review


def test_sports_review_is_evidence_bound_and_preserves_group(tmp_path, monkeypatch):
    settings, request, review = review_fixture(tmp_path, monkeypatch)
    result = sports.publish_sports(request, review, settings, None, NOW, "America/Los_Angeles")
    assert result["stories"][0]["sportsGroup"] == "NFL"
    tampered = deepcopy(request)
    tampered["scores"]["leagues"] = [{}]
    with pytest.raises(ValueError, match="integrity"):
        sports.publish_sports(tampered, review, settings, None, NOW, "America/Los_Angeles")
    review["decisions"][0]["evidence"] = ["p99"]
    with pytest.raises(ValueError, match="evidence"):
        sports.publish_sports(request, review, settings, None, NOW, "America/Los_Angeles")


def test_sports_quota_and_freshness_fail_closed(tmp_path, monkeypatch):
    settings, request, review = review_fixture(tmp_path, monkeypatch, 3)
    with pytest.raises(ValueError, match="budget"):
        sports.publish_sports(request, review, settings, None, NOW, "America/Los_Angeles")
    with pytest.raises(ValueError, match="fresh"):
        sports.publish_sports(request, review, settings, None, NOW + timedelta(hours=7), "America/Los_Angeles")


def test_attach_rejects_yesterdays_sports_and_duplicate_main_report():
    edition = {"date": "2026-09-09", "stories": [{"id": "one"}], "sources": []}
    data = {"date": "2026-09-08", "stories": [], "sports": {"checkedAt": NOW.isoformat()}, "sources": []}
    with pytest.raises(ValueError, match="stale"):
        sports.attach_sports(edition, data, NOW)
    data.update(date=edition["date"], stories=[{"id": "one"}])
    with pytest.raises(ValueError, match="duplicates"):
        sports.attach_sports(edition, data, NOW)


def test_prior_publication_is_checked_again_when_sports_review_is_applied(tmp_path, monkeypatch):
    settings, request, review = review_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(sports, "prior_match", lambda *_: {"date": "2026-09-08"})
    with pytest.raises(ValueError, match="Previously published"):
        sports.publish_sports(request, review, settings, None, NOW, "America/Los_Angeles")


def test_carryover_is_explicit_and_expires_after_one_edition():
    config = {"carryover": {"date": "2026-09-10", "story_ids": ["allowed"]}}
    prior = {"date": "2026-09-09", "id": "allowed"}
    assert sports.permitted_carryover(config, prior, "2026-09-10")
    assert not sports.permitted_carryover(config, prior, "2026-09-11")
    assert not sports.permitted_carryover(config, {**prior, "id": "another"}, "2026-09-10")
    assert not sports.permitted_carryover(config, {**prior, "date": "2026-09-08"}, "2026-09-10")


def test_authorized_carryover_requires_visible_label_and_source_date(tmp_path, monkeypatch):
    settings, request, review = review_fixture(tmp_path, monkeypatch)
    config = {"enabled": True, "carryover": {"date": "2026-09-09", "story_ids": ["0"]}}
    monkeypatch.setattr(sports, "config_for", lambda _: config)
    monkeypatch.setattr(sports, "prior_match", lambda *_: {"date": "2026-09-08", "id": "0"})
    request["policy"] = sports.fingerprint({"version": sports.SPORTS_REQUEST_VERSION, "config": config, "prompt": "Test policy"})
    request["packets"][0]["carryoverFrom"] = "2026-09-08"
    request["packets"][0]["publishedAt"] = "2026-09-08T20:00:00-07:00"
    request["requestHash"] = sports.fingerprint({k: v for k, v in request.items() if k != "requestHash"})
    review["requestHash"] = request["requestHash"]
    with pytest.raises(ValueError, match="explicit reader label"):
        sports.publish_sports(request, review, settings, None, NOW, "America/Los_Angeles")
    review["decisions"][0]["summary"] = "From yesterday's late edition: A concise supported report."
    result = sports.publish_sports(request, review, settings, None, NOW, "America/Los_Angeles")
    assert result["stories"][0]["publishedAt"] == "2026-09-08T20:00:00-07:00"


@pytest.mark.parametrize('changed', [None, 'policy', 'history', 'integrity', 'date'])
def test_sports_request_bindings_are_checked_before_reusing_work(tmp_path, monkeypatch, changed):
    from news_collector.pipeline.publication_history import history_hash
    settings = SimpleNamespace(project_root=tmp_path / 'scripts/news_collector')
    prompt = settings.project_root / 'config/sports-prompt.md'
    prompt.parent.mkdir(parents=True)
    prompt.write_text('Current policy')
    monkeypatch.setattr(sports, 'config_for', lambda *_: {'enabled': True})
    monkeypatch.setattr(sports, 'load_history', lambda *_: [])
    request = {'date': '2026-09-09', 'generatedAt': NOW.isoformat(), 'historyHash': history_hash([]),
               'policy': sports.fingerprint({'version': sports.SPORTS_REQUEST_VERSION, 'config': {'enabled': True}, 'prompt': 'Current policy'})}
    if changed == 'policy': request['policy'] = 'old-policy'
    if changed == 'history': request['historyHash'] = 'old-history'
    if changed == 'date': request['date'] = '2026-09-08'
    request['requestHash'] = sports.fingerprint(request)
    if changed == 'integrity': request['policy'] = 'tampered'
    if changed:
        with pytest.raises(ValueError):
            sports.validate_sports_request(request, settings, NOW, 'America/Los_Angeles')
    else:
        assert sports.validate_sports_request(request, settings, NOW, 'America/Los_Angeles') == []


def test_scoreboards_use_individual_days_and_merge_duplicate_provider_events(monkeypatch):
    calls = []
    def get(client, url, params=None):
        if url.endswith('/scoreboard'):
            calls.append(params['dates'])
            assert len(params['dates']) == 8 and params['dates'].isdigit()
            return {'events': [event()], 'leagues': [{'season': {'displayName': '2026'}}]}
        return {'children': [{'name': 'Division', 'standings': {'entries': [standing_entry('First', 1)]}}]}
    monkeypatch.setattr(sports, 'get_json', get)
    result, health = sports.collect_scores({'leagues': [{'id': 'nfl', 'group': 'NFL', 'name': 'NFL',
        'path': 'football/nfl', 'url': 'https://www.espn.com/nfl/scoreboard'}]}, NOW, None)
    assert calls == ['20260909', '20260910', '20260911']
    assert len(result['leagues'][0]['games']) == 1
    assert result['leagues'][0]['scheduleStatus'] == 'ok'
    assert all(item['status'] == 'ok' for item in health)
