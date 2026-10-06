from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest

from news_collector.pipeline import coverage_discovery as discovery
from news_collector.pipeline import editorial


NOW = datetime(2026, 9, 11, 4, 50, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def freeze_clock(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)
    monkeypatch.setattr(discovery, "datetime", Clock)


def checklist():
    return {"checkedAt": NOW.isoformat(), "method": "independent_web_research",
            "researcher": "Independent researcher", "scope": ["AI", "Economy"],
            "queries": ["September 10 2026 AI regulation"],
            "events": [{"id": "senate-inquiry", "event": "Senate opens inquiry into AI incident",
                        "sector": "Policy", "mustCover": True,
                        "sources": [{"url": "https://example.org/news/inquiry",
                                     "publishedAt": "2026-09-10T09:00:00Z",
                                     "finding": "Official announcement confirms a new inquiry."}]}]}


@pytest.mark.parametrize("date", ["2026-09-10T21:00:00Z", "2026-09-11T05:00:00Z", "2026-09-11T04:50:00"])
def test_rejects_stale_future_or_naive_checklist(date):
    payload = checklist()
    payload["checkedAt"] = date
    with pytest.raises(ValueError):
        discovery.validate_checklist(payload, NOW, {}, now=NOW)


def test_rejects_previous_local_day_even_when_recent():
    with pytest.raises(ValueError):
        discovery.validate_checklist(checklist(), datetime(2026, 9, 11, 7, 1, tzinfo=timezone.utc), {})


def test_research_can_finish_after_the_selection_cutoff():
    payload = checklist()
    payload["checkedAt"] = (NOW + timedelta(hours=1)).isoformat()
    assert discovery.validate_checklist(payload, NOW, {}, now=NOW + timedelta(hours=1))
    payload["events"][0]["sources"][0]["publishedAt"] = (NOW + timedelta(minutes=20)).isoformat()
    with pytest.raises(ValueError, match="after cutoff"):
        discovery.validate_checklist(payload, NOW, {}, now=NOW + timedelta(hours=1))


def test_rejects_future_source_and_empty_queries():
    payload = checklist()
    payload["events"][0]["sources"][0]["publishedAt"] = "2026-09-12T00:00:00Z"
    with pytest.raises(ValueError):
        discovery.validate_checklist(payload, NOW, {})
    payload = checklist()
    payload["queries"] = [" "]
    with pytest.raises(ValueError):
        discovery.validate_checklist(payload, NOW, {})


def test_file_mode_validates_before_replacing(tmp_path):
    source, target = tmp_path / "review.json", tmp_path / "checklist.json"
    source.write_text(json.dumps(checklist()))
    assert discovery.discover_coverage(target, NOW, {}, source)["events"][0]["mustCover"]
    prior = target.read_bytes()
    source.write_text("{}")
    with pytest.raises(ValueError):
        discovery.discover_coverage(target, NOW, {}, source)
    assert target.read_bytes() == prior


def test_cli_isolated_live_research_and_fail_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(editorial.shutil, "which", lambda _: "/bin/codex")
    monkeypatch.setenv("SECRET_TOKEN", "private")

    def run(command, **kwargs):
        assert 'web_search="live"' in command
        assert "--ignore-user-config" in command and "--ephemeral" in command
        assert "shell_tool" in command and "apps" in command and "hooks" in command
        assert "SECRET_TOKEN" not in kwargs["env"]
        research = json.loads(kwargs["input"].split("UNTRUSTED SOURCE PACKETS:\n")[1])
        assert set(research) == {"cutoff", "profile", "windowStart"}
        discovery.Path(command[command.index("-o") + 1]).write_text(json.dumps(checklist()))
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(editorial.subprocess, "run", run)
    target = tmp_path / "checklist.json"
    discovery.discover_coverage(target, NOW, {"timezone": "America/Los_Angeles"})
    before = target.read_bytes()
    monkeypatch.setattr(editorial.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=1, stderr="authentication failed"))
    with pytest.raises(RuntimeError, match="review failed"):
        discovery.discover_coverage(target, NOW, {})
    assert target.read_bytes() == before


def test_old_background_cannot_create_a_daily_must_cover_requirement():
    payload = checklist()
    payload['events'][0]['sources'][0]['publishedAt'] = (NOW - timedelta(days=8)).isoformat()
    result = discovery.validate_checklist(payload, NOW, {})
    assert result['events'][0]['mustCover'] is False


def test_current_discovery_reused_but_stale_research_requires_a_new_call(tmp_path, monkeypatch):
    calls = []
    def review(*args, **kwargs):
        calls.append(1)
        return discovery.IndependentChecklist.model_validate(checklist())
    monkeypatch.setattr(editorial, 'codex_review', review)
    target = tmp_path / 'checklist.json'
    discovery.discover_coverage(target, NOW, {})
    discovery.discover_coverage(target, NOW, {})
    assert len(calls) == 1
    old = checklist()
    old['checkedAt'] = (NOW - timedelta(hours=7)).isoformat()
    target.write_text(json.dumps(old))
    discovery.discover_coverage(target, NOW, {})
    assert len(calls) == 2
