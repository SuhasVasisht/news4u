from __future__ import annotations

import json
import sqlite3

from news_collector.models import RawItem, StoryCluster
from news_collector.pipeline.classify import classify_item
from news_collector.pipeline.dedupe import big_swings, cluster_items
from news_collector.pipeline.digest import build_digest, render_markdown, select_diverse
from news_collector.pipeline.normalize import normalize_item
from news_collector.pipeline.score import cluster_score, compute_item_score
from news_collector.storage.db import Database
from news_collector.storage.repository import Repository
from news_collector.utils import ticker_candidates


def test_offline_pipeline_end_to_end(tmp_path):
    db = Database(tmp_path / "news.db")
    repository = Repository(db)
    raw_items = [
        RawItem(
            source="techcrunch",
            source_type="rss",
            category="tech",
            title="OpenAI launches model",
            url="https://techcrunch.com/story?utm_source=rss",
            summary="Launch story",
            image_url="https://images.example/openai.jpg",
            entities=["OpenAI"],
        ),
        RawItem(
            source="guardian",
            source_type="api",
            category="tech",
            title="OpenAI launches model",
            url="https://www.theguardian.com/story",
            summary="Same event from another source",
            entities=["OpenAI"],
        ),
        RawItem(
            source="alphavantage_movers",
            source_type="api",
            category="finance",
            title="NVDA appears in Alpha Vantage top gainers",
            url="https://www.alphavantage.co/",
            summary="NVDA moved 8%",
            symbols=["NVDA"],
            entities=["NVDA"],
        ),
    ]
    inserted = []
    for raw in raw_items:
        repository.insert_raw_item(raw)
        item = normalize_item(raw)
        item.importance_score = compute_item_score(item, trust_score=0.8, market_impact_score=1.0 if item.symbols else 0.0)
        item_id = repository.insert_normalized_item(item)
        assert item_id is not None
        inserted.append(
            {
                "id": item_id,
                "source": item.source,
                "category": item.category,
                "title": item.title,
                "canonical_url": item.canonical_url,
                    "importance_score": item.importance_score,
                    "summary": item.summary,
                    "image_url": item.image_url,
                    "published_at": item.published_at.isoformat() if item.published_at else None,
                "entities_json": json.dumps(item.entities),
                "symbols_json": json.dumps(item.symbols),
            }
        )

    clusters = cluster_items(inserted)
    assert len(clusters) == 2
    for cluster in clusters:
        cluster.score = cluster_score(cluster, 0.8)
        repository.upsert_cluster(cluster)
        for item_id in cluster.item_ids:
            repository.update_item_cluster(item_id, cluster.cluster_id, cluster.score)

    digest = build_digest(clusters, digest_date="2026-04-16")
    markdown = render_markdown(digest)
    repository.store_digest(markdown, digest)

    assert "# Daily Digest - 2026-04-16" in markdown
    assert "OpenAI launches model" in markdown
    assert "NVDA" in markdown
    assert repository.fetch_clusters()
    assert digest.top_tech[0].image_url == "https://images.example/openai.jpg"


def test_classifier_does_not_treat_african_as_ai():
    item = RawItem(
        source="bbc_world",
        source_type="rss",
        category="world",
        title="South African politician sentenced in gun case",
        url="https://example.com",
    )
    assert classify_item(item) == "world"


def test_ticker_candidates_drop_common_non_tickers():
    assert ticker_candidates("SEC and US officials brief BBC on policy") == []


def test_symbols_alone_do_not_force_finance_category():
    item = RawItem(
        source="arxiv_cs_ai",
        source_type="rss",
        category="tech",
        title="WebXSkill: Skill Learning for Autonomous Web Agents",
        url="https://example.com",
        symbols=["WEBX"],
    )
    assert classify_item(item) == "tech"


def test_cluster_items_do_not_merge_homepage_urls_with_different_titles():
    rows = [
        {
            "id": 1,
            "source": "alphavantage_movers",
            "category": "finance",
            "title": "NVDA appears in Alpha Vantage top gainers",
            "canonical_url": "https://alphavantage.co/",
            "importance_score": 0.7,
            "summary": "NVDA moved",
            "published_at": None,
            "entities_json": json.dumps(["NVDA"]),
            "symbols_json": json.dumps(["NVDA"]),
        },
        {
            "id": 2,
            "source": "alphavantage_movers",
            "category": "finance",
            "title": "AAPL appears in Alpha Vantage top gainers",
            "canonical_url": "https://alphavantage.co/",
            "importance_score": 0.6,
            "summary": "AAPL moved",
            "published_at": None,
            "entities_json": json.dumps(["AAPL"]),
            "symbols_json": json.dumps(["AAPL"]),
        },
    ]
    assert len(cluster_items(rows)) == 2


def test_big_swings_only_uses_market_sources():
    clusters = [
        StoryCluster(
            cluster_id="one",
            category="finance",
            title="NYPD investigates after video",
            canonical_url="https://example.com/a",
            representative_source="guardian",
            symbols=["NYPD"],
        ),
        StoryCluster(
            cluster_id="two",
            category="finance",
            title="NVDA appears in Alpha Vantage top gainers",
            canonical_url="https://example.com/b",
            representative_source="alphavantage_movers",
            symbols=["NVDA"],
        ),
    ]
    assert big_swings(clusters) == [
        {
            "symbol": "NVDA",
            "title": "NVDA appears in Alpha Vantage top gainers",
            "score": 0.0,
            "url": "https://example.com/b",
        }
    ]


def test_tldr_clicks_contribute_to_item_score():
    low_engagement = normalize_item(
        RawItem(
            source="techcrunch",
            source_type="rss",
            category="tech",
            title="Routine infra update",
            url="https://example.com/tc",
            engagement={},
        )
    )
    high_engagement = normalize_item(
        RawItem(
            source="tldr_tech",
            source_type="scrape",
            category="tech",
            title="Major AI tooling shift",
            url="https://example.com/tldr",
            engagement={"clicks": 2400},
        )
    )
    assert compute_item_score(high_engagement, trust_score=0.72) > compute_item_score(low_engagement, trust_score=0.72)


def test_select_diverse_caps_repeated_sources():
    clusters = [
        StoryCluster(cluster_id=f"a{i}", category="tech", title=f"A{i}", canonical_url=f"https://a/{i}", representative_source="arxiv_cs_ai", score=1.0 - i * 0.01)
        for i in range(4)
    ] + [
        StoryCluster(cluster_id="tldr", category="tech", title="TLDR", canonical_url="https://tldr", representative_source="tldr_tech", score=0.8),
        StoryCluster(cluster_id="hn", category="tech", title="HN", canonical_url="https://hn", representative_source="hackernews", score=0.79),
    ]
    chosen = select_diverse(clusters, limit=4, max_per_source=2)
    assert [cluster.representative_source for cluster in chosen] == ["arxiv_cs_ai", "arxiv_cs_ai", "tldr_tech", "hackernews"]


def test_database_migrates_existing_schema_with_image_columns(tmp_path):
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE raw_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            source_type TEXT NOT NULL,
            category TEXT NOT NULL,
            external_id TEXT,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            published_at TEXT,
            author TEXT,
            summary TEXT,
            text TEXT,
            tags_json TEXT NOT NULL,
            symbols_json TEXT NOT NULL,
            entities_json TEXT NOT NULL,
            engagement_json TEXT NOT NULL,
            raw_json TEXT NOT NULL,
            fetched_at TEXT NOT NULL
        );
        CREATE TABLE normalized_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            source_type TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            canonical_url TEXT NOT NULL,
            published_at TEXT,
            author TEXT,
            text TEXT,
            summary TEXT,
            symbols_json TEXT NOT NULL,
            entities_json TEXT NOT NULL,
            tags_json TEXT NOT NULL,
            engagement_json TEXT NOT NULL,
            importance_score REAL NOT NULL,
            fingerprint TEXT NOT NULL,
            cluster_id TEXT,
            raw_json TEXT NOT NULL
        );
        CREATE TABLE story_clusters (
            cluster_id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            canonical_url TEXT NOT NULL,
            representative_source TEXT NOT NULL,
            published_at TEXT,
            score REAL NOT NULL,
            confirmation_count INTEGER NOT NULL,
            entities_json TEXT NOT NULL,
            symbols_json TEXT NOT NULL,
            item_ids_json TEXT NOT NULL,
            summary TEXT
        );
        """
    )
    conn.close()

    db = Database(path)
    with db.connect() as migrated:
        raw_cols = [row["name"] for row in migrated.execute("PRAGMA table_info(raw_items)").fetchall()]
        normalized_cols = [row["name"] for row in migrated.execute("PRAGMA table_info(normalized_items)").fetchall()]
        cluster_cols = [row["name"] for row in migrated.execute("PRAGMA table_info(story_clusters)").fetchall()]
        media_cache = migrated.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='media_cache'"
        ).fetchone()
        content_cache = migrated.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='content_cache'"
        ).fetchone()

    assert "image_url" in raw_cols
    assert "text" in raw_cols
    assert "image_url" in normalized_cols
    assert "text" in normalized_cols
    assert "image_url" in cluster_cols
    assert media_cache is not None
    assert content_cache is not None
