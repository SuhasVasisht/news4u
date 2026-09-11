from __future__ import annotations

import feedparser
from selectolax.parser import HTMLParser
from urllib.parse import urlparse

from news_collector.collectors.base import BaseCollector
from news_collector.models import RawItem
from news_collector.pipeline.extract import extract_image_from_feed_entry
from news_collector.utils import entity_candidates, parse_datetime, ticker_candidates


class TechmemeCollector(BaseCollector):
    source_type = "rss"

    def collect(self) -> list[RawItem]:
        response = self.client.get(self.context.config["url"])
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
        items: list[RawItem] = []
        for entry in parsed.entries:
            description = entry.get("description") or ""
            article_url, publication = self._extract_primary_link(description)
            url = article_url or entry.get("link", "")
            title = self._extract_title(description) or (entry.get("title") or "").strip()
            summary = self._extract_summary(description)
            items.append(
                RawItem(
                    source=self.name,
                    source_type="rss",
                    category=self.category,
                    external_id=entry.get("id") or entry.get("guid") or entry.get("link"),
                    title=title,
                    url=url,
                    published_at=parse_datetime(entry.get("published") or entry.get("updated")),
                    author=publication,
                    summary=summary,
                    text=self.resolve_text(url, summary),
                    image_url=self.resolve_image(url, extract_image_from_feed_entry(dict(entry))),
                    tags=[publication] if publication else [],
                    symbols=ticker_candidates(title, summary),
                    entities=entity_candidates(title, summary),
                    raw={
                        "techmeme_link": entry.get("link"),
                        "description": description,
                        "publication": publication,
                    },
                )
            )
        return items

    @staticmethod
    def _extract_primary_link(description: str) -> tuple[str | None, str | None]:
        parser = HTMLParser(description)
        def external(link):
            parsed = urlparse(link.attributes.get("href", ""))
            host = (parsed.hostname or "").removeprefix("www.")
            return parsed.scheme in {"http", "https"} and host and host != "techmeme.com" and not host.endswith(".techmeme.com")

        links = [link for link in parser.css("a") if external(link)]
        articles = [link for link in links if urlparse(link.attributes["href"]).path.strip("/")]
        # Without a thumbnail, the publisher homepage precedes the actual headline.
        headline = next((link for link in parser.css("span b a, b a")
                         if external(link) and urlparse(link.attributes["href"]).path.strip("/")), None)
        article = headline or next((link for link in articles if link.css_first("img")), None)
        if article is None:
            article = next(iter(articles), None)
        article_url = article.attributes["href"] if article is not None else None
        host = urlparse(article_url or "").hostname
        publication = next((link.text(strip=True) for link in links
                            if link.attributes["href"] != article_url
                            and urlparse(link.attributes["href"]).hostname == host
                            and not urlparse(link.attributes["href"]).path.strip("/")
                            and link.text(strip=True)), None)
        return article_url, publication

    @staticmethod
    def _extract_title(description: str) -> str | None:
        parser = HTMLParser(description)
        node = parser.css_first("span b a") or parser.css_first("b a")
        return node.text(strip=True) if node else None

    @staticmethod
    def _extract_summary(description: str) -> str | None:
        parser = HTMLParser(description)
        text = parser.text(separator=" ", strip=True)
        parts = [part.strip() for part in text.split("—") if part.strip()]
        if len(parts) >= 2:
            return parts[-1]
        return text or None
