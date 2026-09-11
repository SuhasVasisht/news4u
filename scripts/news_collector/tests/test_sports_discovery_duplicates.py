from datetime import datetime, timezone
from types import SimpleNamespace

from news_collector.pipeline import sports


def test_duplicate_feed_entries_and_resolved_ids_enter_review_once(tmp_path, monkeypatch):
    now = datetime(2026, 9, 10, 20, tzinfo=timezone.utc)
    settings = SimpleNamespace(project_root=tmp_path / "scripts/news_collector", user_agent="test")
    config_dir = settings.project_root / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "sports-prompt.md").write_text("test")
    monkeypatch.setattr(sports, "config_for", lambda _: {"feeds": [{"name": "feed", "url": "https://example.org/rss", "group": "Elsewhere"}]})
    monkeypatch.setattr(sports, "collect_scores", lambda *_: ({}, []))
    monkeypatch.setattr(sports, "download", lambda *_: (b"feed", "https://example.org/rss"))
    entries = [{"title": "A major result", "link": f"https://example.org/{slug}", "published": now.isoformat()}
               for slug in ("one", "one", "alias")]
    monkeypatch.setattr(sports.feedparser, "parse", lambda _: SimpleNamespace(entries=entries))
    calls = []
    def extract(row, *_):
        calls.append(row["url"])
        return {"id": "same-resolved-id", "source": "feed"}
    monkeypatch.setattr(sports, "content_packet", extract)
    request = sports.prepare_sports(settings, None, now, "America/Los_Angeles")
    assert len(calls) == 2
    assert len(request["packets"]) == 1
    assert request["sources"][0]["candidates"] == 1
