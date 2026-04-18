from __future__ import annotations

import feedparser

from news_collector.collectors.base import BaseCollector
from news_collector.models import RawItem
from news_collector.pipeline.extract import extract_image_from_feed_entry
from news_collector.utils import entity_candidates, parse_datetime, ticker_candidates


class RSSCollector(BaseCollector):
    source_type = "rss"

    def collect(self) -> list[RawItem]:
        response = self.client.get(self.context.config["url"])
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
        items: list[RawItem] = []
        for entry in parsed.entries:
            title = (entry.get("title") or "").strip()
            summary = entry.get("summary") or entry.get("description")
            items.append(
                RawItem(
                    source=self.name,
                    source_type="rss",
                    category=self.category,
                    external_id=entry.get("id") or entry.get("guid"),
                    title=title,
                    url=entry.get("link", ""),
                    published_at=parse_datetime(entry.get("published") or entry.get("updated")),
                    author=entry.get("author"),
                    summary=summary,
                    text=self.resolve_text(entry.get("link", ""), summary),
                    image_url=self.resolve_image(
                        entry.get("link", ""),
                        extract_image_from_feed_entry(dict(entry)),
                    ),
                    tags=[tag.get("term", "") for tag in entry.get("tags", []) if tag.get("term")],
                    symbols=ticker_candidates(title, summary),
                    entities=entity_candidates(title, summary),
                    raw=dict(entry),
                )
            )
        return items
