from __future__ import annotations

from news_collector.collectors.base import BaseCollector
from news_collector.models import RawItem
from news_collector.utils import entity_candidates, parse_datetime, sleep_if_needed


class GDELTCollector(BaseCollector):
    source_type = "api"

    def collect(self) -> list[RawItem]:
        items: list[RawItem] = []
        last_called_at = None
        for query in self.context.config.get("queries", []):
            last_called_at = sleep_if_needed(
                last_called_at,
                float(self.context.defaults.get("gdelt_min_interval_seconds", 5)),
            )
            response = self.client.get(
                "https://api.gdeltproject.org/api/v2/doc/doc",
                params={"query": query, "mode": "artlist", "maxrecords": 10, "format": "json"},
            )
            if response.status_code == 429:
                break
            response.raise_for_status()
            try:
                payload = response.json()
            except ValueError:
                break
            for article in payload.get("articles", []):
                title = article.get("title", "").strip()
                items.append(
                    RawItem(
                        source=self.name,
                        source_type="api",
                        category=self._category_for_query(query),
                        title=title,
                        url=article.get("url", ""),
                        published_at=parse_datetime(article.get("seendate")),
                        summary=article.get("domain"),
                        text=self.resolve_text(article.get("url", ""), title),
                        image_url=self.resolve_image(
                            article.get("url", ""),
                            article.get("socialimage"),
                            article.get("image"),
                        ),
                        entities=entity_candidates(title),
                        raw=article,
                    )
                )
        return items

    @staticmethod
    def _category_for_query(query: str) -> str:
        lowered = query.lower()
        if "ai" in lowered or "technology" in lowered or "semiconductor" in lowered or "cloud" in lowered:
            return "tech"
        if "election" in lowered or "parliament" in lowered:
            return "politics"
        return "world"
