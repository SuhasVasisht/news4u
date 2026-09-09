from __future__ import annotations

import time
import httpx

from news_collector.collectors.base import BaseCollector, CollectorDegraded
from news_collector.models import RawItem
from news_collector.utils import entity_candidates, parse_datetime, sleep_if_needed


class GDELTCollector(BaseCollector):
    source_type = "api"

    def _request(self, query: str):
        for attempt in range(2):
            try:
                return self.client.get(
                    "https://api.gdeltproject.org/api/v2/doc/doc",
                    params={"query": query, "mode": "artlist", "maxrecords": 10, "format": "json", "timespan": "48h"},
                )
            except httpx.RequestError:
                if attempt:
                    return None
                time.sleep(float(self.context.defaults.get("gdelt_min_interval_seconds", 5)))

    @staticmethod
    def _normalize_query(query: str) -> str:
        if " OR " in query and not query.strip().startswith("("):
            return f"({query})"
        return query

    def collect(self) -> list[RawItem]:
        items: list[RawItem] = []
        failures: list[str] = []
        last_called_at = None
        for query in self.context.config.get("queries", []):
            normalized_query = self._normalize_query(query) + " sourcelang:english"
            last_called_at = sleep_if_needed(
                last_called_at,
                float(self.context.defaults.get("gdelt_min_interval_seconds", 5)),
            )
            response = self._request(normalized_query)
            if response is None:
                failures.append("one query disconnected after retry")
                continue
            if response.status_code == 429:
                time.sleep(float(self.context.defaults.get("gdelt_min_interval_seconds", 5)) + 1)
                response = self._request(normalized_query)
                if response is None:
                    failures.append("one query disconnected after retry")
                    continue
            if response.status_code == 429:
                failures.append("rate limited (HTTP 429)")
                continue
            if response.status_code >= 400:
                failures.append(f"one query returned HTTP {response.status_code}")
                continue
            try:
                payload = response.json()
            except ValueError:
                failures.append("non-JSON response")
                continue
            for article in payload.get("articles", []):
                title = article.get("title", "").strip()
                items.append(
                    RawItem(
                        source=self.name,
                        source_type="api",
                        category=self._category_for_query(normalized_query),
                        title=title,
                        url=article.get("url", ""),
                        published_at=parse_datetime(article.get("seendate")),
                        summary=None,
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
        if not items and failures:
            raise CollectorDegraded("GDELT: " + "; ".join(sorted(set(failures))))
        state = self.get_state()
        state["collection_warning"] = "; ".join(sorted(set(failures))) or None
        self.set_state(state)
        return items

    @staticmethod
    def _category_for_query(query: str) -> str:
        lowered = query.lower()
        if "ai" in lowered or "technology" in lowered or "semiconductor" in lowered or "cloud" in lowered:
            return "tech"
        if "election" in lowered or "parliament" in lowered:
            return "politics"
        return "world"
