from __future__ import annotations

import json

from news_collector.settings import Settings
from news_collector.storage.db import Database
from news_collector.storage.repository import Repository
from news_collector.sync import build_sync_article, enrich_item, publish_articles, raw_item_from_row
from tests.helpers import FakeClient, FakeResponse


def build_settings(tmp_path):
    return Settings(
        project_root=tmp_path,
        db_path=tmp_path / "news.db",
        output_dir=tmp_path / "output",
        sync_outbox_dir=tmp_path / "output" / "sync",
        user_agent="test-agent",
        newsapi_key=None,
        guardian_api_key=None,
        alphavantage_api_key=None,
        producthunt_token=None,
        app_base_url="https://news-app.example.com",
        app_sync_api_key="secret",
        app_sync_batch_size=200,
        replay_batch_size=200,
        x_profile_dir=tmp_path / "x",
        reddit_profile_dir=tmp_path / "reddit",
    )


def insert_raw(repository: Repository) -> dict:
    raw_id = repository.insert_raw_item(
        raw_item_from_row(
            {
                "source": "techcrunch",
                "source_type": "rss",
                "category": "tech",
                "external_id": "story-1",
                "title": "Collector sync title",
                "url": "https://example.com/news/story-1",
                "published_at": "2026-04-17T08:00:00+00:00",
                "author": "Reporter",
                "summary": "Short summary",
                "image_url": None,
                "text": None,
                "tags_json": json.dumps(["technology"]),
                "symbols_json": json.dumps([]),
                "entities_json": json.dumps(["OpenAI"]),
                "engagement_json": json.dumps({}),
                "raw_json": json.dumps({"publisher": "TechCrunch"}),
                "fetched_at": "2026-04-17T08:05:00+00:00",
            }
        )
    )
    return repository.fetch_raw_items(limit=10, min_id=raw_id - 1)[0]


def test_enrich_item_fetches_and_caches_body_and_image(tmp_path):
    repository = Repository(Database(tmp_path / "news.db"))
    row = insert_raw(repository)
    client = FakeClient(
        {
            "https://example.com/news/story-1": FakeResponse(
                text="""
                <html>
                  <head>
                    <meta property="og:image" content="https://images.example.com/story.jpg" />
                  </head>
                  <body>
                    <article><p>First paragraph.</p><p>Second paragraph.</p></article>
                  </body>
                </html>
                """
            )
        }
    )
    item = raw_item_from_row(row)
    enriched, used_page_fetch = enrich_item(item, repository, client, checked_at="2026-04-17T09:00:00+00:00")
    assert used_page_fetch is True
    assert "First paragraph" in enriched.text
    assert enriched.image_url == "https://images.example.com/story.jpg"
    cached = repository.get_cached_content("https://example.com/news/story-1")
    assert cached is not False
    assert "First paragraph" in cached["content_text"]


def test_build_sync_article_uses_topic_mapping_and_fallback_text(tmp_path):
    row = {
        "source": "guardian",
        "source_type": "api",
        "category": "politics",
        "external_id": None,
        "title": "Policy shift headline",
        "url": "https://example.com/news/policy-shift",
        "published_at": "2026-04-17T08:00:00+00:00",
        "author": None,
        "summary": "Policy shift summary",
        "image_url": None,
        "text": None,
        "tags_json": json.dumps(["technology", "politics"]),
        "symbols_json": json.dumps([]),
        "entities_json": json.dumps([]),
        "engagement_json": json.dumps({}),
        "raw_json": json.dumps({}),
        "fetched_at": "2026-04-17T08:05:00+00:00",
    }
    payload = build_sync_article(raw_item_from_row(row), used_page_fetch=False)
    assert payload["content_text"] == "Policy shift summary"
    assert payload["published_at"] == "2026-04-17T08:00:00Z"
    assert payload["topics"] == [
        {"slug": "policy", "name": "Policy"},
        {"slug": "technology", "name": "Technology"},
    ]
    assert payload["external_id"].startswith("synthetic:")


def test_publish_articles_writes_outbox_and_refreshes_feed_dates(tmp_path, monkeypatch):
    repository = Repository(Database(tmp_path / "news.db"))
    row = insert_raw(repository)
    settings = build_settings(tmp_path)

    client = FakeClient(
        {
            "https://example.com/news/story-1": FakeResponse(
                text="<html><head><meta property='og:image' content='https://images.example.com/story.jpg'></head><body><article><p>Full body text.</p></article></body></html>"
            ),
            ("https://news-app.example.com/api/internal/articles/sync", "POST"): FakeResponse(
                json_data={"received": 1, "inserted": 1, "updated": 0}
            ),
            ("https://news-app.example.com/api/internal/feed/generate", "POST"): FakeResponse(
                json_data={"feedDate": "2026-04-17"}
            ),
        }
    )
    monkeypatch.setattr("news_collector.sync.get_http_client", lambda *args, **kwargs: client)

    result = publish_articles(repository, settings, [row], batch_label="test-batch")
    assert result.received == 1
    manifest_path = settings.sync_outbox_dir / next(settings.sync_outbox_dir.iterdir()).name / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["article_count"] == 1
    assert manifest["attempt_count"] == 1
    assert manifest["delivered_at"] is not None
