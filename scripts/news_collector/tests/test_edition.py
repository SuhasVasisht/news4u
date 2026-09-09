import json
from datetime import datetime, timedelta, timezone

from news_collector.jobs.export_edition import build_snapshot
from news_collector.collectors.tldr import TLDRCollector
from news_collector.pipeline.dedupe import cluster_items
from news_collector.collectors.guardian import GuardianCollector
from news_collector.collectors.gdelt import GDELTCollector
from news_collector.collectors.rss import RSSCollector
from news_collector.collectors.base import CollectorContext, BaseCollector
from news_collector.models import RawItem
from tests.helpers import FakeClient, FakeResponse
from tests.test_collectors import make_settings, make_repository


def row(id=1, **kwargs):
    return {"id": id, "source": "techcrunch", "category": "tech", "title": "A new compiler launches", "summary": "<p>A new <b>compiler</b>.</p>", "canonical_url": "https://example.com/story", "published_at": "2026-09-08T07:00:00+00:00", "importance_score": .8, "entities_json": "[]", "symbols_json": "[]", **kwargs}


def test_snapshot_rejects_stale_undated_and_future_and_counts_dedupe():
    now = datetime(2026, 9, 8, 8, tzinfo=timezone.utc)
    rows = [row(), row(2), row(3, published_at=None), row(4, published_at="2026-04-18T12:00:00Z"), row(5, published_at="2026-09-09T12:00:00Z")]
    snapshot, audit = build_snapshot(rows, now)
    assert len(snapshot["stories"]) == 1
    assert snapshot["stories"][0]["summary"] == "A new compiler."
    assert audit["collapsed_rows"] == 1
    assert audit["selected_today_published"] == 1
    assert audit["excluded"] == {"undated": 1, "older_than_7_days": 1, "future": 1}


def test_recurring_headlines_do_not_merge_across_weeks():
    assert len(cluster_items([row(), row(2, canonical_url="https://example.com/last-week", published_at="2026-09-01T07:00:00Z")])) == 2
    assert len(cluster_items([row(), row(2, published_at="2026-09-01T07:00:00Z")])) == 1


def test_tldr_decodes_all_arrays_nested_data_and_unicode():
    payload = {"featuredStories": [{"url": "https://example.com/a", "title": "Alpha", "tags": ["AI"]}], "tech": [{"url": "https://example.com/b", "title": "Caf\u00e9 compiler", "newsletter": "tech"}]}
    html = f'<script>self.__next_f.push({json.dumps([1, json.dumps(payload)])})</script>'
    stories = TLDRCollector._extract_story_blobs(html)
    assert [s["title"] for s in stories] == ["Alpha", "Caf\u00e9 compiler"]


def test_guardian_rejected_key_uses_public_section_feeds(tmp_path, monkeypatch):
    c = GuardianCollector(CollectorContext(name="guardian", config={"category": "world", "sections": ["world", "technology"]}, defaults={}, settings=make_settings(tmp_path), repository=make_repository(tmp_path)))
    c.client = FakeClient({"https://content.guardianapis.com/search": FakeResponse(status_code=401)})
    feeds = []
    def collect(rss):
        feeds.append(rss.context.config["url"])
        return [RawItem(source="guardian", source_type="rss", category=rss.category, title="Report", url="https://example.com/report")]
    monkeypatch.setattr(RSSCollector, "collect", collect)
    assert len(c.collect()) == 2
    assert feeds == ["https://www.theguardian.com/world/rss", "https://www.theguardian.com/technology/rss"]
    assert c.get_state()["transport"] == "rss-fallback"


def test_gdelt_keeps_results_when_a_later_query_fails(tmp_path, monkeypatch):
    c = GDELTCollector(CollectorContext(name="gdelt", config={"category": "world", "queries": ["technology", "election"]}, defaults={"gdelt_min_interval_seconds": 0}, settings=make_settings(tmp_path), repository=make_repository(tmp_path)))
    good = FakeResponse(json_data={"articles": [{"title": "Current report", "url": "https://example.com/report", "seendate": "20260908T070000Z", "socialimage": "https://example.com/photo.jpg"}]})
    replies = iter([good, None])
    monkeypatch.setattr(c, "_request", lambda q: next(replies))
    result = c.run()
    assert result.status == "partial"
    assert len(result.items) == 1
    assert "disconnected" in result.reason


def test_cache_replay_does_not_renew_freshness(tmp_path, monkeypatch):
    c = BaseCollector(CollectorContext(name="test", config={"category": "tech"}, defaults={}, settings=make_settings(tmp_path), repository=make_repository(tmp_path)))
    cached_at = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
    item = RawItem(source="test", source_type="api", category="tech", title="Cached report", url="https://example.com/report")
    c.set_state({"last_success_items_at": cached_at, "last_success_items": [item.model_dump(mode="json")]})
    monkeypatch.setattr(c, "collect", lambda: c.cached_items())
    result = c.run()
    assert result.status == "cached"
    assert c.get_state()["last_success_items_at"] == cached_at
