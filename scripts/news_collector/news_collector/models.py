from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


Category = Literal["tech", "world", "politics", "finance", "other"]
SourceType = Literal["rss", "api", "scrape", "x"]


class RawItem(BaseModel):
    source: str
    source_type: SourceType
    category: Category
    external_id: str | None = None
    title: str
    url: str
    published_at: datetime | None = None
    author: str | None = None
    summary: str | None = None
    image_url: str | None = None
    text: str | None = None
    tags: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    engagement: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class NewsItem(BaseModel):
    source: str
    source_type: SourceType
    category: Category
    title: str
    url: str
    canonical_url: str
    published_at: datetime | None = None
    author: str | None = None
    image_url: str | None = None
    text: str | None = None
    summary: str | None = None
    symbols: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    engagement: dict[str, Any] = Field(default_factory=dict)
    importance_score: float = 0.0
    fingerprint: str
    cluster_id: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class StoryCluster(BaseModel):
    cluster_id: str
    category: Category
    title: str
    canonical_url: str
    representative_source: str
    published_at: datetime | None = None
    image_url: str | None = None
    score: float = 0.0
    confirmation_count: int = 1
    entities: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    item_ids: list[int] = Field(default_factory=list)
    summary: str | None = None


class DigestDocument(BaseModel):
    digest_date: str
    generated_at: datetime
    top_tech: list[StoryCluster] = Field(default_factory=list)
    top_world_politics: list[StoryCluster] = Field(default_factory=list)
    top_finance: list[StoryCluster] = Field(default_factory=list)
    rising_stories: list[StoryCluster] = Field(default_factory=list)
    big_swings: list[dict[str, Any]] = Field(default_factory=list)
