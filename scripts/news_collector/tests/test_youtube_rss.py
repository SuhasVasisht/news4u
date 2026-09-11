import pytest

from news_collector.collectors.base import CollectorContext
from news_collector.collectors.rss import RSSCollector
from tests.helpers import FakeResponse
from tests.test_collectors import make_repository, make_settings


def make_collector(tmp_path, url):
    return RSSCollector(CollectorContext(name="video", config={"url": url, "category": "tech"},
        defaults={}, settings=make_settings(tmp_path), repository=make_repository(tmp_path)))


def test_youtube_transient_false_404_retries_with_original_identity(tmp_path, monkeypatch):
    collector = make_collector(tmp_path, "https://www.youtube.com/feeds/videos.xml?channel_id=example")
    statuses = iter([404, 500, 200])
    calls = []
    def get(url):
        calls.append(url)
        return FakeResponse(status_code=next(statuses))
    monkeypatch.setattr(collector.client, "get", get)
    monkeypatch.setattr("news_collector.collectors.rss.time.sleep", lambda seconds: None)
    assert collector._feed_response().status_code == 200
    assert len(calls) == 3
    assert collector.client.headers["User-Agent"] == "test-agent"


@pytest.mark.parametrize("url,status,attempts", [
    ("https://www.youtube.com/feeds/videos.xml?channel_id=missing", 404, 3),
    ("https://www.youtube.com/feeds/videos.xml?channel_id=blocked", 403, 1),
    ("https://example.com/feed", 404, 1),
    ("https://www.youtube.com.evil.test/feeds/videos.xml", 500, 1),
])
def test_persistent_failures_stay_failed_and_retries_are_scoped(tmp_path, monkeypatch, url, status, attempts):
    collector = make_collector(tmp_path, url)
    calls = []
    def get(url):
        calls.append(url)
        return FakeResponse(status_code=status)
    monkeypatch.setattr(collector.client, "get", get)
    monkeypatch.setattr("news_collector.collectors.rss.time.sleep", lambda seconds: None)
    with pytest.raises(RuntimeError, match=f"HTTP {status}"):
        collector._feed_response()
    assert len(calls) == attempts
