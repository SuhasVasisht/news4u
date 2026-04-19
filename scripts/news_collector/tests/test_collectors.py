from __future__ import annotations

from dataclasses import replace

from news_collector.collectors.ap import APCollector
from news_collector.collectors.alpha_vantage import AlphaVantageNewsCollector
from news_collector.collectors.base import CollectorContext
from news_collector.collectors.gdelt import GDELTCollector
from news_collector.collectors.newsapi import NewsAPICollector
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


def test_rss_collector_falls_back_to_arxiv_api_when_rss_is_empty(tmp_path):
    collector = RSSCollector(
        CollectorContext(
            name="arxiv_cs_ai",
            config={"url": "https://arxiv.org/rss/cs.AI", "category": "tech"},
            defaults={"request_timeout_seconds": 5},
            settings=make_settings(tmp_path),
            repository=make_repository(tmp_path),
        )
    )
    collector.client = FakeClient(
        {
            "https://arxiv.org/rss/cs.AI": FakeResponse(
                text="""<?xml version="1.0"?><rss><channel><title>cs.AI</title></channel></rss>"""
            ),
            (
                "https://export.arxiv.org/api/query",
                (
                    ("max_results", 10),
                    ("search_query", "cat:cs.AI"),
                    ("sortBy", "submittedDate"),
                    ("sortOrder", "descending"),
                    ("start", 0),
                ),
            ): FakeResponse(
                text="""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
                <entry>
                  <id>https://arxiv.org/abs/2604.00001</id>
                  <updated>2026-04-18T12:00:00Z</updated>
                  <published>2026-04-18T12:00:00Z</published>
                  <title>Reasoning Agents</title>
                  <summary>Paper abstract.</summary>
                  <author><name>Jane Doe</name></author>
                </entry>
                </feed>"""
            ),
        }
    )
    items = collector.collect()
    assert len(items) == 1
    assert items[0].title == "Reasoning Agents"
    assert items[0].text == "Paper abstract."


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
    <a href='https://apnews.com/article/example-story-1234567890abcdef'>story</a>
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


def test_ap_collector_force_run_ignores_seen_urls(tmp_path):
    collector = APCollector(
        CollectorContext(
            name="ap_top_news",
            config={"url": "https://apnews.com/hub/apf-topnews", "category": "world", "max_requests_per_run": 2},
            defaults={"request_timeout_seconds": 5},
            settings=make_settings(tmp_path),
            repository=make_repository(tmp_path),
        )
    )
    collector.set_state({"seen_urls": ["https://apnews.com/article/example-story-1234567890abcdef"]})
    collector._force_run = True
    collector.client = FakeClient(
        {
            "https://apnews.com/hub/apf-topnews": FakeResponse(
                text="<html><body><a href='https://apnews.com/article/example-story-1234567890abcdef'>story</a></body></html>"
            ),
            "https://apnews.com/article/example-story-1234567890abcdef": FakeResponse(
                text="""<html><head><title>Example Story | AP News</title><meta name="description" content="AP summary"/></head></html>"""
            ),
        }
    )
    items = collector.collect()
    assert len(items) == 1


def test_gdelt_collector_wraps_or_queries(tmp_path):
    collector = GDELTCollector(
        CollectorContext(
            name="gdelt",
            config={"category": "world", "queries": ["ai OR semiconductor OR cloud"]},
            defaults={"request_timeout_seconds": 5, "gdelt_min_interval_seconds": 0},
            settings=make_settings(tmp_path),
            repository=make_repository(tmp_path),
        )
    )
    collector.client = FakeClient(
        {
            (
                "https://api.gdeltproject.org/api/v2/doc/doc",
                (
                    ("format", "json"),
                    ("maxrecords", 10),
                    ("mode", "artlist"),
                    ("query", "(ai OR semiconductor OR cloud)"),
                ),
            ): FakeResponse(json_data={"articles": []})
        }
    )
    assert collector.collect() == []


def test_newsapi_collector_filters_low_signal_articles(tmp_path):
    settings = replace(make_settings(tmp_path), newsapi_key="token")
    collector = NewsAPICollector(
        CollectorContext(
            name="newsapi",
            config={"category": "other", "queries": ["technology", "finance"]},
            defaults={"request_timeout_seconds": 5},
            settings=settings,
            repository=make_repository(tmp_path),
        )
    )
    collector.client = FakeClient(
        {
            (
                "https://newsapi.org/v2/everything",
                (("apiKey", "token"), ("language", "en"), ("pageSize", 10), ("q", "technology"), ("sortBy", "publishedAt")),
            ): FakeResponse(
                json_data={
                    "articles": [
                        {"title": "Pennsylvania Sportswatch Daily Listings", "description": "Schedule", "url": "https://example.com/junk", "publishedAt": "2026-04-18T12:00:00Z", "source": {"name": "AP Sports"}},
                        {"title": "OpenAI expands inference stack", "description": "Cloud and GPU demand rise", "url": "https://example.com/good", "publishedAt": "2026-04-18T12:00:00Z", "source": {"name": "Tech Desk"}},
                    ]
                }
            ),
            (
                "https://newsapi.org/v2/everything",
                (("apiKey", "token"), ("language", "en"), ("pageSize", 10), ("q", "finance"), ("sortBy", "publishedAt")),
            ): FakeResponse(json_data={"articles": []}),
            "https://example.com/good": FakeResponse(text="<html></html>"),
        }
    )
    items = collector.collect()
    assert len(items) == 1
    assert items[0].title == "OpenAI expands inference stack"


def test_alpha_vantage_news_uses_cached_items_when_rate_limited(tmp_path):
    collector = AlphaVantageNewsCollector(
        CollectorContext(
            name="alphavantage_news",
            config={"category": "finance", "topics": ["technology"]},
            defaults={"request_timeout_seconds": 5},
            settings=make_settings(tmp_path),
            repository=make_repository(tmp_path),
        )
    )
    collector.set_state(
        {
            "last_success_items_at": "2026-04-18T12:00:00+00:00",
            "last_success_items": [
                {
                    "source": "alphavantage_news",
                    "source_type": "api",
                    "category": "tech",
                    "title": "Cached market story",
                    "url": "https://example.com/cached",
                    "summary": "Cached summary",
                    "text": "Cached summary",
                    "raw": {},
                    "fetched_at": "2026-04-18T12:00:00+00:00",
                }
            ],
        }
    )
    collector.client = FakeClient(
        {
            (
                "https://www.alphavantage.co/query",
                (("apikey", "demo"), ("function", "NEWS_SENTIMENT"), ("limit", 10), ("topics", "technology")),
            ): FakeResponse(json_data={"Information": "rate limit"})
        }
    )
    items = collector.collect()
    assert len(items) == 1
    assert items[0].title == "Cached market story"


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
