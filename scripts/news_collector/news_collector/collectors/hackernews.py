from __future__ import annotations

from news_collector.collectors.base import BaseCollector
from news_collector.models import RawItem
from news_collector.utils import entity_candidates, parse_datetime, ticker_candidates


class HackerNewsCollector(BaseCollector):
    source_type = "api"

    def collect(self) -> list[RawItem]:
        limit = int(self.context.config.get("limit", 20))
        stories_response = self.client.get("https://hacker-news.firebaseio.com/v0/topstories.json")
        stories_response.raise_for_status()
        story_ids = stories_response.json()[:limit]
        items: list[RawItem] = []
        for story_id in story_ids:
            response = self.client.get(f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json")
            response.raise_for_status()
            story = response.json()
            if story.get("type") != "story" or not story.get("url"):
                continue
            title = story.get("title", "")
            engagement = {"score": story.get("score", 0), "descendants": story.get("descendants", 0)}
            items.append(
                RawItem(
                    source=self.name,
                    source_type="api",
                    category=self.category,
                    external_id=str(story.get("id")),
                    title=title,
                    url=story.get("url", ""),
                    published_at=parse_datetime(story.get("time")),
                    author=story.get("by"),
                    summary=f"Hacker News comments: https://news.ycombinator.com/item?id={story_id}",
                    text=self.resolve_text(story.get("url", ""), title),
                    image_url=self.resolve_image(story.get("url", "")),
                    symbols=ticker_candidates(title),
                    entities=entity_candidates(title),
                    engagement=engagement,
                    raw=story,
                )
            )
        return items
