from __future__ import annotations

from news_collector.collectors.base import BaseCollector, CollectorContext
from news_collector.collectors.rss import RSSCollector
from news_collector.models import RawItem
from news_collector.utils import entity_candidates, parse_datetime, ticker_candidates


class GuardianCollector(BaseCollector):
    source_type = "api"

    def collect(self) -> list[RawItem]:
        api_key = self.context.settings.guardian_api_key or "test"
        items: list[RawItem] = []
        for section in self.context.config.get("sections", []):
            response = self.client.get(
                "https://content.guardianapis.com/search",
                params={
                    "api-key": api_key,
                    "page-size": 10,
                    "section": section,
                    "show-fields": "headline,trailText,thumbnail,bodyText",
                    "order-by": "newest",
                },
            )
            if response.status_code in {401, 403}:
                # Public section feeds keep coverage available when the API key expires.
                fallback = []
                for feed_section in self.context.config.get("sections", []):
                    collector = RSSCollector(CollectorContext(
                        name=self.name,
                        config={"url": f"https://www.theguardian.com/{feed_section}/rss", "category": self._category_for_section(feed_section)},
                        defaults=self.context.defaults, settings=self.context.settings, repository=self.repository,
                    ))
                    try:
                        fallback.extend(collector.collect()[:10])
                    finally:
                        collector.client.close()
                state = self.get_state()
                state["transport"] = "rss-fallback"
                state["collection_warning"] = "Public RSS fallback; API credentials rejected"
                self.set_state(state)
                return fallback
            response.raise_for_status()
            for article in response.json().get("response", {}).get("results", []):
                title = article.get("fields", {}).get("headline") or article.get("webTitle", "")
                summary = article.get("fields", {}).get("trailText")
                items.append(
                    RawItem(
                        source=self.name,
                        source_type="api",
                        category=self._category_for_section(section),
                        external_id=article.get("id"),
                        title=title,
                        url=article.get("webUrl", ""),
                        published_at=parse_datetime(article.get("webPublicationDate")),
                        summary=summary,
                        text=self.resolve_text(
                            article.get("webUrl", ""),
                            article.get("fields", {}).get("bodyText"),
                            summary,
                            fetch_page=False,
                        ),
                        image_url=self.resolve_image(
                            article.get("webUrl", ""),
                            article.get("fields", {}).get("thumbnail"),
                        ),
                        tags=[article.get("sectionName", "")],
                        symbols=ticker_candidates(title, summary),
                        entities=entity_candidates(title, summary),
                        raw=article,
                    )
                )
        state = self.get_state()
        state["transport"] = "api"
        state["collection_warning"] = None
        self.set_state(state)
        return items

    @staticmethod
    def _category_for_section(section: str) -> str:
        if section == "technology":
            return "tech"
        if section == "business":
            return "finance"
        if section == "us-news":
            return "politics"
        return "world"
