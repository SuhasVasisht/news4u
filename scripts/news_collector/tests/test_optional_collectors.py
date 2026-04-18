from __future__ import annotations

from news_collector.collectors.base import CollectorContext
from news_collector.collectors.reddit import RedditCollector
from news_collector.collectors.x_search import XSearchCollector
from news_collector.settings import Settings
from news_collector.storage.db import Database
from news_collector.storage.repository import Repository


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
        app_base_url="http://127.0.0.1:3000",
        app_sync_api_key="secret",
        app_sync_batch_size=200,
        replay_batch_size=200,
        x_profile_dir=tmp_path / "missing-x",
        reddit_profile_dir=tmp_path / "missing-reddit",
    )


def build_repository(tmp_path):
    return Repository(Database(tmp_path / "news.db"))


def test_x_collector_degrades_without_persistent_profile(tmp_path):
    collector = XSearchCollector(
        CollectorContext(
            name="x_search",
            config={"category": "tech", "accounts": ["OpenAI"]},
            defaults={"request_timeout_seconds": 1},
            settings=build_settings(tmp_path),
            repository=build_repository(tmp_path),
        )
    )

    result = collector.run(force=True)

    assert result.status == "degraded"
    assert result.reason == "missing persistent X browser profile"


def test_reddit_collector_degrades_without_persistent_profile(tmp_path):
    collector = RedditCollector(
        CollectorContext(
            name="reddit",
            config={"category": "tech", "subreddits": ["selfhosted"]},
            defaults={"request_timeout_seconds": 1},
            settings=build_settings(tmp_path),
            repository=build_repository(tmp_path),
        )
    )

    result = collector.run(force=True)

    assert result.status == "degraded"
    assert result.reason == "missing persistent Reddit browser profile"
