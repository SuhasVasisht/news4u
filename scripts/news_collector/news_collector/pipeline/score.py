from __future__ import annotations

from datetime import datetime, timezone

from news_collector.models import NewsItem, StoryCluster


def recency_score(published_at) -> float:
    if not published_at:
        return 0.3
    age_hours = max((datetime.now(timezone.utc) - published_at).total_seconds() / 3600, 0)
    return max(0.0, 1.0 - min(age_hours / 48.0, 1.0))


def engagement_score(engagement: dict) -> float:
    if not engagement:
        return 0.0
    if "score" in engagement:
        return min(float(engagement.get("score", 0)) / 500.0, 1.0)
    if "clicks" in engagement:
        return min(float(engagement.get("clicks", 0)) / 2500.0, 1.0)
    linked_urls = engagement.get("linked_urls") or []
    if linked_urls:
        return 0.3
    return 0.0


def compute_item_score(
    item: NewsItem,
    trust_score: float,
    confirmation_score: float = 0.0,
    market_impact_score: float = 0.0,
) -> float:
    item_engagement_score = engagement_score(item.engagement)
    return round(
        recency_score(item.published_at) * 0.35
        + trust_score * 0.20
        + confirmation_score * 0.20
        + item_engagement_score * 0.10
        + market_impact_score * 0.15,
        4,
    )


def cluster_score(cluster: StoryCluster, trust_score: float) -> float:
    base_recency = recency_score(cluster.published_at)
    confirmation = min(cluster.confirmation_count / 5.0, 1.0)
    impact = 1.0 if cluster.symbols else 0.2
    return round(base_recency * 0.35 + trust_score * 0.20 + confirmation * 0.20 + 0.0 * 0.10 + impact * 0.15, 4)
