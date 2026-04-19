from __future__ import annotations

from news_collector.collectors.base import BaseCollector, CollectorDegraded
from news_collector.models import RawItem
from news_collector.utils import entity_candidates, parse_datetime


class AlphaVantageNewsCollector(BaseCollector):
    source_type = "api"

    def collect(self) -> list[RawItem]:
        api_key = self.context.settings.alphavantage_api_key or "demo"
        items: list[RawItem] = []
        for topic in self.context.config.get("topics", []):
            response = self.client.get(
                "https://www.alphavantage.co/query",
                params={
                    "function": "NEWS_SENTIMENT",
                    "topics": topic,
                    "limit": 10,
                    "apikey": api_key,
                },
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("Information"):
                cached = self.cached_items()
                if cached:
                    return cached
                raise CollectorDegraded(payload["Information"])
            for article in payload.get("feed", []):
                title = article.get("title", "")
                summary = article.get("summary")
                items.append(
                    RawItem(
                        source=self.name,
                        source_type="api",
                        category="finance" if "financial" in topic or "mergers" in topic else "tech",
                        title=title,
                        url=article.get("url", ""),
                        published_at=parse_datetime(article.get("time_published")),
                        author=", ".join(article.get("authors", [])) or None,
                        summary=summary,
                        text=self.resolve_text(article.get("url", ""), summary),
                        image_url=self.resolve_image(article.get("url", ""), article.get("banner_image")),
                        tags=[t.get("topic") for t in article.get("topics", []) if t.get("topic")],
                        symbols=[t.get("ticker") for t in article.get("ticker_sentiment", []) if t.get("ticker")],
                        entities=entity_candidates(title, summary),
                        raw=article,
                    )
                )
        return items


class AlphaVantageMoversCollector(BaseCollector):
    source_type = "api"

    def collect(self) -> list[RawItem]:
        api_key = self.context.settings.alphavantage_api_key or "demo"
        response = self.client.get(
            "https://www.alphavantage.co/query",
            params={"function": "TOP_GAINERS_LOSERS", "apikey": api_key},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("Information"):
            cached = self.cached_items()
            if cached:
                return cached
            raise CollectorDegraded(payload["Information"])
        items: list[RawItem] = []
        for bucket in ("top_gainers", "top_losers", "most_actively_traded"):
            for entry in payload.get(bucket, [])[:10]:
                symbol = entry.get("ticker", "")
                title = f"{symbol} appears in Alpha Vantage {bucket.replace('_', ' ')}"
                items.append(
                    RawItem(
                        source=self.name,
                        source_type="api",
                        category="finance",
                        external_id=f"{bucket}:{symbol}",
                        title=title,
                        url="https://www.alphavantage.co/",
                        published_at=parse_datetime(payload.get("last_updated")),
                        summary=f"{symbol} moved {entry.get('change_percentage')} on volume {entry.get('volume')}",
                        text=f"{symbol} moved {entry.get('change_percentage')} on volume {entry.get('volume')}",
                        image_url=self.resolve_image("https://www.alphavantage.co/", fetch_page=False),
                        symbols=[symbol],
                        entities=[symbol],
                        engagement={"bucket": bucket, "volume": entry.get("volume")},
                        raw={"bucket": bucket, "metadata": payload.get("metadata"), "entry": entry},
                    )
                )
        if not items:
            cached = self.cached_items()
            if cached:
                return cached
        return items
