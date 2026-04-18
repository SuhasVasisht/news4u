from __future__ import annotations

import json
import re

from news_collector.collectors.base import BaseCollector, CollectorDegraded
from news_collector.models import RawItem
from news_collector.utils import entity_candidates, parse_datetime, safe_json_loads, ticker_candidates


class TLDRCollector(BaseCollector):
    source_type = "scrape"

    def collect(self) -> list[RawItem]:
        html = self._fetch_story_html()
        stories = self._extract_story_blobs(html)
        newsletter = self.context.config.get("newsletter")
        items: list[RawItem] = []
        for story in stories:
            if newsletter and story.get("newsletter") != newsletter:
                continue
            title = story.get("title", "")
            summary = story.get("tldr")
            items.append(
                RawItem(
                    source=self.name,
                    source_type="scrape",
                    category=self.category,
                    external_id=str(story.get("id") or story.get("url")),
                    title=title,
                    url=story.get("url", ""),
                    published_at=parse_datetime(story.get("newsletter_date") or story.get("date")),
                    summary=summary,
                    text=self.resolve_text(story.get("url", ""), summary),
                    image_url=self.resolve_image(
                        story.get("url", ""),
                        story.get("imageUrl"),
                    ),
                    tags=[story.get("category", "")] if story.get("category") else [],
                    entities=entity_candidates(title, summary),
                    symbols=ticker_candidates(title, summary),
                    engagement={"clicks": int(story.get("totalClicks", 0) or 0)},
                    raw=story,
                )
            )
            if len(items) >= int(self.context.config.get("max_items_per_run", 25)):
                break
        if not items:
            raise CollectorDegraded("unable to parse TLDR hydration payload")
        return items

    def _fetch_story_html(self) -> str:
        primary_response = self.client.get(self.context.config["url"])
        primary_response.raise_for_status()
        primary_html = primary_response.text
        if self._extract_story_blobs(primary_html):
            return primary_html
        fallback_response = self.client.get("https://tldr.tech")
        fallback_response.raise_for_status()
        return fallback_response.text

    @staticmethod
    def _extract_story_blobs(html: str) -> list[dict]:
        for pattern in (
            r'featuredStories\\":(\[.*?\])[,}]',
            r'product\\":(\[.*?\])[,}]',
            r'ai\\":(\[.*?\])[,}]',
            r'tech\\":(\[.*?\])[,}]',
        ):
            for match in re.finditer(pattern, html):
                decoded = bytes(match.group(1), "utf-8").decode("unicode_escape")
                parsed = safe_json_loads(decoded)
                if isinstance(parsed, list) and parsed:
                    stories = [
                        story
                        for story in parsed
                        if isinstance(story, dict) and story.get("url") and story.get("title")
                    ]
                    if stories:
                        return stories
        # Fallback for legacy simple embedded blobs.
        blobs = re.findall(r'\{"url":"https?://.*?"title":".*?"\}', html)
        stories = []
        for blob in blobs:
            parsed = safe_json_loads(blob)
            if isinstance(parsed, dict) and parsed.get("url") and parsed.get("title"):
                stories.append(parsed)
        return stories
