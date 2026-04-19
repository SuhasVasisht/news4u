from __future__ import annotations

import re

from news_collector.collectors.base import BaseCollector
from news_collector.models import RawItem
from news_collector.utils import entity_candidates, parse_datetime, ticker_candidates


LOW_SIGNAL_TITLE_PATTERNS = [
    re.compile(r"\bsportswatch daily listings\b", re.IGNORECASE),
    re.compile(r"\bdaily listings\b", re.IGNORECASE),
    re.compile(r"\bhoroscope\b", re.IGNORECASE),
    re.compile(r"\bwordle\b", re.IGNORECASE),
    re.compile(r"\bcrossword\b", re.IGNORECASE),
]

LOW_SIGNAL_SOURCE_PATTERNS = [
    re.compile(r"sports|entertainment|lifestyle|tabloid", re.IGNORECASE),
]


class NewsAPICollector(BaseCollector):
    source_type = "api"

    def _is_low_signal(self, article: dict, query: str) -> bool:
        title = (article.get("title") or "").strip()
        summary = (article.get("description") or "").strip()
        source_name = ((article.get("source") or {}).get("name") or "").strip()
        combined = " ".join(part for part in [title, summary] if part)

        if not title or title.lower() == "[removed]":
            return True
        if any(pattern.search(title) for pattern in LOW_SIGNAL_TITLE_PATTERNS):
            return True
        if source_name and any(pattern.search(source_name) for pattern in LOW_SIGNAL_SOURCE_PATTERNS):
            return True
        if query == "technology" and not re.search(r"\b(ai|artificial intelligence|chip|semiconductor|cloud|software|developer|startup|openai|anthropic|nvidia|microsoft|google|meta|amazon|apple|datacenter|robotaxi|cyber|app|gpu)\b", combined, re.IGNORECASE):
            return True
        if query == "finance" and not re.search(r"\b(market|stock|fund|bond|bank|fed|ipo|earnings|acquisition|merger|sec|treasury|tariff|oil|crypto|bitcoin|nasdaq|s&p|dow)\b", combined, re.IGNORECASE):
            return True
        return False

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
                if self._is_low_signal(article, query):
                    continue
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
