from __future__ import annotations

import re

from selectolax.parser import HTMLParser

from news_collector.collectors.base import BaseCollector, CollectorDegraded
from news_collector.models import RawItem
from news_collector.pipeline.extract import extract_image_from_page_html, extract_text_from_html
from news_collector.utils import entity_candidates, parse_datetime


class APCollector(BaseCollector):
    source_type = "scrape"

    @staticmethod
    def _is_challenge_page(html: str) -> bool:
        lowered = html.lower()
        signals = [
            "request rate threshold exceeded",
            "access denied",
            "verify you are human",
            "cf-chl",
            "__cf_bm",
        ]
        return any(signal in lowered for signal in signals)

    def collect(self) -> list[RawItem]:
        state = self.get_state()
        seen_urls = set() if self._force_run else set(state.get("seen_urls", []))
        response = self.client.get(self.context.config["url"])
        response.raise_for_status()
        if self._is_challenge_page(response.text):
            raise CollectorDegraded("AP hub returned challenge page")
        urls = list(
            dict.fromkeys(
                re.findall(r"href=['\"](https://apnews\.com/article/[A-Za-z0-9_-]+)['\"]", response.text)
                or re.findall(r"https://apnews\.com/article/[A-Za-z0-9_-]+", response.text)
            )
        )
        items: list[RawItem] = []
        stale_count = 0
        max_requests = int(self.context.config.get("max_requests_per_run", 8))
        for article_url in urls:
            if article_url in seen_urls:
                stale_count += 1
                if not self._force_run and stale_count >= 2:
                    break
                continue
            article_response = self.client.get(article_url)
            if article_response.status_code >= 400:
                continue
            if self._is_challenge_page(article_response.text):
                raise CollectorDegraded("AP article page returned challenge page")
            parser = HTMLParser(article_response.text)
            title = parser.css_first("title").text(strip=True) if parser.css_first("title") else article_url
            summary_node = parser.css_first('meta[name="description"]')
            summary = summary_node.attributes.get("content") if summary_node else None
            image_url = extract_image_from_page_html(article_response.text, article_url)
            text = extract_text_from_html(article_response.text, article_url)
            published = None
            ld_json = parser.css_first('script[type="application/ld+json"]')
            if ld_json:
                published_match = re.search(r'"datePublished"\s*:\s*"([^"]+)"', ld_json.text())
                if published_match:
                    published = parse_datetime(published_match.group(1))
            items.append(
                RawItem(
                    source=self.name,
                    source_type="scrape",
                    category=self.category,
                    title=title.replace(" | AP News", ""),
                    url=article_url,
                    published_at=published,
                    summary=summary,
                    text=text,
                    image_url=image_url,
                    entities=entity_candidates(title, summary),
                    raw={"hub_url": self.context.config["url"], "article_html_excerpt": article_response.text[:500]},
                )
            )
            seen_urls.add(article_url)
            if len(items) >= max_requests:
                break
            if not self._force_run:
                self.sleep_range(
                    float(self.context.config.get("min_request_delay_seconds", 0)),
                    float(self.context.config.get("max_request_delay_seconds", 0)),
                )
        state["seen_urls"] = list(seen_urls)[-100:]
        self.set_state(state)
        return items
