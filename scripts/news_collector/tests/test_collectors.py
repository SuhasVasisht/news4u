from __future__ import annotations

from dataclasses import replace

from news_collector.collectors.ap import APCollector
from news_collector.collectors.base import CollectorContext
from news_collector.collectors.producthunt import ProductHuntCollector
from news_collector.collectors.reddit import RedditCollector
from news_collector.collectors.rss import RSSCollector
from news_collector.collectors.techmeme import TechmemeCollector
from news_collector.collectors.tldr import TLDRCollector
from news_collector.collectors.x_search import XSearchCollector
from news_collector.storage.db import Database
from news_collector.storage.repository import Repository
from news_collector.settings import Settings

from tests.helpers import FakeClient, FakeResponse


def make_settings(tmp_path):
    return Settings(
        project_root=tmp_path,
        db_path=tmp_path / "data.db",
        output_dir=tmp_path / "output",
        user_agent="test-agent",
        newsapi_key=None,
        guardian_api_key="test",
        alphavantage_api_key="demo",
        producthunt_token=None,
        x_profile_dir=tmp_path / "x_profile",
        reddit_profile_dir=tmp_path / "reddit_profile",
    )


def make_repository(tmp_path):
    return Repository(Database(tmp_path / "news.db"))


def test_rss_collector_parses_feed(tmp_path):
    collector = RSSCollector(
        CollectorContext(
            name="techcrunch",
            config={"url": "https://example.com/feed", "category": "tech"},
            defaults={"request_timeout_seconds": 5},
            settings=make_settings(tmp_path),
            repository=make_repository(tmp_path),
        )
    )
    collector.client = FakeClient(
        {
            "https://example.com/feed": FakeResponse(
                text="""<?xml version="1.0"?><rss><channel>
                <item><title>OpenAI ships new model</title><link>https://example.com/a?utm_source=rss</link>
                <pubDate>Thu, 16 Apr 2026 15:00:00 GMT</pubDate><description>Model launch</description></item>
                </channel></rss>"""
            ),
            "https://example.com/a?utm_source=rss": FakeResponse(
                text='<html><head><meta property="og:image" content="https://example.com/og.jpg"></head></html>'
            ),
        }
    )
    items = collector.collect()
    assert len(items) == 1
    assert items[0].title == "OpenAI ships new model"
    assert items[0].summary == "Model launch"
    assert items[0].image_url == "https://example.com/og.jpg"


def test_rss_collector_prefers_media_thumbnail(tmp_path):
    collector = RSSCollector(
        CollectorContext(
            name="bbc_world",
            config={"url": "https://example.com/feed", "category": "world"},
            defaults={"request_timeout_seconds": 5},
            settings=make_settings(tmp_path),
            repository=make_repository(tmp_path),
        )
    )
    collector.client = FakeClient(
        {
            "https://example.com/feed": FakeResponse(
                text="""<?xml version="1.0"?><rss xmlns:media="http://search.yahoo.com/mrss/"><channel>
                <item><title>World update</title><link>https://example.com/b</link>
                <media:thumbnail url="https://example.com/thumb.jpg" />
                </item></channel></rss>"""
            )
        }
    )
    items = collector.collect()
    assert items[0].image_url == "https://example.com/thumb.jpg"


def test_tldr_collector_extracts_embedded_json(tmp_path):
    repository = make_repository(tmp_path)
    collector = TLDRCollector(
        CollectorContext(
            name="tldr_ai",
            config={"url": "https://tldr.tech/ai", "category": "tech", "newsletter": "ai"},
            defaults={"request_timeout_seconds": 5},
            settings=make_settings(tmp_path),
            repository=repository,
        )
    )
    collector.client = FakeClient(
        {
            "https://tldr.tech/ai": FakeResponse(
                text='prefix self.__next_f.push([1,"5:[\\"$\\",\\"$L16\\",null,{\\"searchParams\\":{},\\"featuredStories\\":[{\\"url\\":\\"https://example.com/story\\",\\"totalClicks\\":\\"99\\",\\"newsletter\\":\\"ai\\",\\"newsletter_date\\":\\"2026-04-16\\",\\"id\\":1,\\"title\\":\\"Anthropic ships tool\\",\\"tldr\\":\\"Short summary\\",\\"date\\":\\"2026-04-16\\",\\"category\\":\\"ai\\",\\"imageUrl\\":\\"https://example.com/image.png\\"}],\\"showStories\\":true}]"]) suffix'
            )
        }
    )
    items = collector.collect()
    assert len(items) == 1
    assert items[0].title == "Anthropic ships tool"
    assert items[0].engagement["clicks"] == 99
    assert items[0].image_url == "https://example.com/image.png"


def test_ap_collector_discovers_articles_from_hub(tmp_path):
    collector = APCollector(
        CollectorContext(
            name="ap_top_news",
            config={"url": "https://apnews.com/hub/apf-topnews", "category": "world", "max_requests_per_run": 2},
            defaults={"request_timeout_seconds": 5},
            settings=make_settings(tmp_path),
            repository=make_repository(tmp_path),
        )
    )
    hub_html = """
    <html><body>
    https://apnews.com/article/example-story-1234567890abcdef
    </body></html>
    """
    article_html = """
    <html><head>
    <title>Example Story | AP News</title>
    <meta name="description" content="AP summary"/>
    <meta property="og:image" content="https://example.com/ap.jpg"/>
    <script type="application/ld+json">{"datePublished":"2026-04-16T12:00:00Z"}</script>
    </head><body></body></html>
    """
    collector.client = FakeClient(
        {
            "https://apnews.com/hub/apf-topnews": FakeResponse(text=hub_html),
            "https://apnews.com/article/example-story-1234567890abcdef": FakeResponse(text=article_html),
        }
    )
    items = collector.collect()
    assert len(items) == 1
    assert items[0].title == "Example Story"
    assert items[0].summary == "AP summary"
    assert items[0].image_url == "https://example.com/ap.jpg"
    assert collector.get_state()["seen_urls"] == ["https://apnews.com/article/example-story-1234567890abcdef"]


def test_techmeme_collector_parses_primary_link_and_image(tmp_path):
    collector = TechmemeCollector(
        CollectorContext(
            name="techmeme",
            config={"url": "https://www.techmeme.com/feed.xml", "category": "tech"},
            defaults={"request_timeout_seconds": 5},
            settings=make_settings(tmp_path),
            repository=make_repository(tmp_path),
        )
    )
    collector.client = FakeClient(
        {
            "https://www.techmeme.com/feed.xml": FakeResponse(
                text="""<?xml version="1.0"?><rss><channel><item>
                <title>Fallback title</title>
                <link>https://www.techmeme.com/260417/p1#a260417p1</link>
                <pubDate>Fri, 17 Apr 2026 03:25:03 -0400</pubDate>
                <description><![CDATA[
                <a href="https://publisher.example/story"><img src="https://www.techmeme.com/260417/i1.jpg" /></a>
                <p><a href="https://www.techmeme.com/260417/p1#a260417p1">Permalink</a> Jane Doe / <a href="https://publisher.example/">Publisher</a>:
                <span><b><a href="https://publisher.example/story">Primary story title</a></b></span> &mdash; concise summary</p>
                ]]></description>
                </item></channel></rss>"""
            )
        }
    )
    items = collector.collect()
    assert len(items) == 1
    assert items[0].title == "Primary story title"
    assert items[0].url == "https://publisher.example/story"
    assert items[0].author == "Publisher"
    assert items[0].image_url == "https://www.techmeme.com/260417/i1.jpg"


def test_producthunt_collector_maps_graphql_response(tmp_path):
    settings = replace(make_settings(tmp_path), producthunt_token="token")
    collector = ProductHuntCollector(
        CollectorContext(
            name="producthunt",
            config={"category": "tech", "limit": 5},
            defaults={"request_timeout_seconds": 5},
            settings=settings,
            repository=make_repository(tmp_path),
        )
    )
    collector.client = FakeClient(
        {
            ("https://api.producthunt.com/v2/api/graphql", "POST"): FakeResponse(
                json_data={
                    "data": {
                        "posts": {
                            "edges": [
                                {
                                    "node": {
                                        "id": "123",
                                        "name": "Launchy",
                                        "tagline": "Fast launches",
                                        "url": "https://www.producthunt.com/posts/launchy",
                                        "website": "https://launchy.example",
                                        "votesCount": 77,
                                        "createdAt": "2026-04-17T00:00:00Z",
                                        "thumbnail": {"url": "https://images.example/launchy.png"},
                                        "topics": {"edges": [{"node": {"name": "Developer Tools"}}]},
                                    }
                                }
                            ]
                        }
                    }
                }
            )
        }
    )
    items = collector.collect()
    assert len(items) == 1
    assert items[0].title == "Launchy"
    assert items[0].image_url == "https://images.example/launchy.png"
    assert items[0].engagement["votes"] == 77


def test_producthunt_collector_degrades_without_token(tmp_path):
    collector = ProductHuntCollector(
        CollectorContext(
            name="producthunt",
            config={"category": "tech"},
            defaults={"request_timeout_seconds": 5},
            settings=make_settings(tmp_path),
            repository=make_repository(tmp_path),
        )
    )
    result = collector.run(force=True)
    assert result.status == "degraded"
    assert "missing Product Hunt API token" in (result.reason or "")


def test_reddit_collector_degrades_without_saved_profile(tmp_path):
    collector = RedditCollector(
        CollectorContext(
            name="reddit",
            config={"subreddits": ["programming"], "category": "tech"},
            defaults={"request_timeout_seconds": 5},
            settings=make_settings(tmp_path),
            repository=make_repository(tmp_path),
        )
    )
    result = collector.run(force=True)
    assert result.status == "degraded"
    assert "missing persistent Reddit browser profile" in (result.reason or "")


def test_x_collector_degrades_without_saved_profile(tmp_path):
    collector = XSearchCollector(
        CollectorContext(
            name="x_search",
            config={"accounts": ["OpenAI"], "category": "tech"},
            defaults={"request_timeout_seconds": 5},
            settings=make_settings(tmp_path),
            repository=make_repository(tmp_path),
        )
    )
    result = collector.run(force=True)
    assert result.status == "degraded"
    assert "missing persistent X browser profile" in (result.reason or "")
