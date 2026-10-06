from types import SimpleNamespace

import httpx

from news_collector.collectors.newsroom import NewsroomCollector


def test_dated_absolute_root_report_precedes_old_featured_news_links():
    listing = '''<main>
      <a href="/news/old">Older featured post</a>
      <a href="https://example.org/report-september"><time datetime="2026-09-10">Sep 10, 2026</time>Threat report</a>
      <a href="/news/recent"><time>Sep 1, 2026</time>Recent news</a>
      <a href="https://other.org/report"><time>Sep 11, 2026</time>External</a>
      <a href="/login">Login</a>
    </main>'''
    visited = []
    def respond(request):
        visited.append(str(request.url))
        body = listing if request.url.path == "/news" else '<main><h1>Threat report</h1><p>Publisher evidence without an article date.</p></main>'
        return httpx.Response(200, text=body)
    collector = object.__new__(NewsroomCollector)
    collector.context = SimpleNamespace(name="newsroom", config={"url": "https://example.org/news", "limit": 1, "category": "tech"})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        collector.client = client
        items = collector.collect()
    assert visited == ["https://example.org/news", "https://example.org/report-september"]
    assert len(items) == 1
    assert items[0].published_at.isoformat() == "2026-09-10T00:00:00+00:00"


def test_explicit_single_article_page_is_ingested_as_full_publisher_evidence():
    body = '''<html><head><link rel="canonical" href="https://example.org/report">
      <meta property="article:published_time" content="2026-10-05T12:00:00Z"></head>
      <main><h1>Acquisition announced</h1><p>Full transaction details.</p></main></html>'''
    collector = object.__new__(NewsroomCollector)
    collector.context = SimpleNamespace(name="publisher_news", config={
        "url": "https://example.org/report", "single_article": True,
        "category": "finance", "edition_sector": "Deals & regulation"})
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body))) as client:
        collector.client = client
        items = collector.collect()
    assert len(items) == 1
    assert items[0].url == "https://example.org/report"
    assert items[0].published_at.isoformat() == "2026-10-05T12:00:00+00:00"
    assert items[0].raw["_edition_sector"] == "Deals & regulation"
