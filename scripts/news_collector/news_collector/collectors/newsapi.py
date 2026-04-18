from __future__ import annotations

from news_collector.collectors.base import BaseCollector
from news_collector.models import RawItem
from news_collector.utils import entity_candidates, parse_datetime, ticker_candidates


class NewsAPICollector(BaseCollector):
    source_type = "api"

    def collect(self) -> list[RawItem]:
        if not self.context.settings.newsapi_key:
            return []
        items: list[RawItem] = []
        for query in self.context.config.get("queries", []):
            response = self.client.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": query,
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": 10,
                    "apiKey": self.context.settings.newsapi_key,
                },
            )
            response.raise_for_status()
            for article in response.json().get("articles", []):
                title = article.get("title", "")
                summary = article.get("description")
                items.append(
                    RawItem(
                        source=self.name,
                        source_type="api",
                        category=self.category,
                        title=title,
                        url=article.get("url", ""),
                        published_at=parse_datetime(article.get("publishedAt")),
                        author=article.get("author"),
                        summary=summary,
                        text=self.resolve_text(article.get("url", ""), summary),
                        image_url=self.resolve_image(article.get("url", ""), article.get("urlToImage")),
                        entities=entity_candidates(title, summary),
                        symbols=ticker_candidates(title, summary),
                        raw=article,
                    )
                )
        return items
