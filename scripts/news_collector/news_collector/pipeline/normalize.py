from __future__ import annotations

from news_collector.models import NewsItem, RawItem
from news_collector.pipeline.classify import classify_item
from news_collector.utils import canonicalize_url, fingerprint_for


def normalize_item(raw: RawItem) -> NewsItem:
    category = classify_item(raw)
    canonical_url = canonicalize_url(raw.url)
    return NewsItem(
        source=raw.source,
        source_type=raw.source_type,
        category=category,
        title=raw.title.strip(),
        url=raw.url,
        canonical_url=canonical_url,
        published_at=raw.published_at,
        author=raw.author,
        image_url=raw.image_url,
        text=raw.text,
        summary=raw.summary,
        symbols=raw.symbols,
        entities=raw.entities,
        tags=raw.tags,
        engagement=raw.engagement,
        fingerprint=fingerprint_for(canonical_url, raw.title, raw.published_at, raw.entities),
        raw=raw.raw,
    )
