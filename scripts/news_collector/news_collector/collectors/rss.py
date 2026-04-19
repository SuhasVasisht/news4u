from __future__ import annotations

import feedparser
from urllib.parse import urlparse

from news_collector.collectors.base import BaseCollector
from news_collector.models import RawItem
from news_collector.pipeline.extract import extract_image_from_feed_entry
from news_collector.utils import entity_candidates, parse_datetime, ticker_candidates


class RSSCollector(BaseCollector):
    source_type = "rss"

    def _fallback_arxiv_items(self) -> list[RawItem]:
        parsed_url = urlparse(self.context.config["url"])
        category = parsed_url.path.rsplit("/", 1)[-1]
        response = self.client.get(
            "https://export.arxiv.org/api/query",
            params={
                "search_query": f"cat:{category}",
                "start": 0,
                "max_results": 10,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            },
        )
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
        items: list[RawItem] = []
        for entry in parsed.entries:
            title = (entry.get("title") or "").strip()
            summary = (entry.get("summary") or entry.get("description") or "").strip()
            items.append(
                RawItem(
                    source=self.name,
                    source_type="rss",
                    category=self.category,
                    external_id=entry.get("id") or entry.get("guid"),
                    title=title,
                    url=entry.get("id") or entry.get("link", ""),
                    published_at=parse_datetime(entry.get("published") or entry.get("updated")),
                    author=", ".join(author.get("name", "") for author in entry.get("authors", []) if author.get("name")) or None,
                    summary=summary,
                    text=summary,
                    image_url=None,
                    tags=[tag.get("term", "") for tag in entry.get("tags", []) if tag.get("term")],
                    symbols=ticker_candidates(title, summary),
                    entities=entity_candidates(title, summary),
                    raw=dict(entry),
                )
            )
        return items

    def collect(self) -> list[RawItem]:
        response = self.client.get(self.context.config["url"])
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
        if not parsed.entries and "arxiv.org/rss/" in self.context.config["url"]:
            return self._fallback_arxiv_items()
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
