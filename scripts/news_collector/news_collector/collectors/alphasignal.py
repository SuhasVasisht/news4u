"""Read AlphaSignal's public news pages with publisher-provided metadata."""
from __future__ import annotations

import json
from urllib.parse import urljoin, urlparse

from selectolax.parser import HTMLParser

from news_collector.collectors.base import BaseCollector, CollectorDegraded
from news_collector.models import RawItem
from news_collector.pipeline.extract import extract_text_from_html, first_image_url
from news_collector.utils import entity_candidates, parse_datetime


class AlphaSignalCollector(BaseCollector):
    source_type = "scrape"

    def collect(self) -> list[RawItem]:
        state = self.get_state()
        state.pop("collection_warning", None)
        self.set_state(state)
        base = self.context.config["url"]
        response = self.client.get(base)
        response.raise_for_status()
        page = HTMLParser(response.text)
        urls = []
        for link in page.css("a[href]"):
            url = urljoin(base, link.attributes["href"])
            if (urlparse(url).hostname == urlparse(base).hostname
                    and urlparse(url).path.startswith("/news/") and url not in urls):
                urls.append(url)
        if not urls:
            raise CollectorDegraded("no AlphaSignal news links found")
        items = []
        failures = 0
        for url in urls[:int(self.context.config.get("limit", 20))]:
            try:
                response = self.client.get(url)
                response.raise_for_status()
                item = self._parse_article(response.text, url)
                if item:
                    items.append(item)
                else:
                    failures += 1
            except Exception:
                failures += 1
        if not items:
            raise CollectorDegraded("unable to parse dated AlphaSignal articles")
        if failures:
            state = self.get_state()
            state["collection_warning"] = f"{failures} AlphaSignal article pages unavailable or unparseable"
            self.set_state(state)
        return items

    def _parse_article(self, html: str, url: str) -> RawItem | None:
        page = HTMLParser(html)
        for script in page.css('script[type="application/ld+json"]'):
            try:
                payload = json.loads(script.text())
            except ValueError:
                continue
            nodes = payload if isinstance(payload, list) else [payload]
            for node in nodes:
                if isinstance(node, dict) and isinstance(node.get("@graph"), list):
                    nodes = nodes + node["@graph"]
            for node in nodes:
                if not isinstance(node, dict) or node.get("@type") != "NewsArticle":
                    continue
                date = parse_datetime(node.get("datePublished"))
                title = node.get("headline")
                if not date or not title:
                    continue
                summary = node.get("description")
                mentions = node.get("mentions") or []
                tags = [m["name"] for m in mentions if isinstance(m, dict) and m.get("name")]
                images = node.get("image") or []
                if isinstance(images, str):
                    images = [images]
                if isinstance(images, dict):
                    images = [images.get("url")]
                return RawItem(
                    source=self.name, source_type=self.source_type, category=self.category,
                    external_id=url, url=url, title=title, published_at=date,
                    summary=summary, text=extract_text_from_html(html, url) or summary,
                    image_url=first_image_url(*[i for i in images if isinstance(i, str)]),
                    tags=tags, entities=entity_candidates(title, summary),
                    raw={**node, "_editorial_type": "reporting"},
                )
        return None
