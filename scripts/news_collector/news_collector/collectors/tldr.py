from __future__ import annotations

import json
import re
from html import unescape
from urllib.parse import urlparse

from selectolax.parser import HTMLParser

from news_collector.collectors.base import BaseCollector, CollectorDegraded
from news_collector.models import RawItem
from news_collector.utils import entity_candidates, parse_datetime, safe_json_loads, ticker_candidates


class TLDRCollector(BaseCollector):
    source_type = "scrape"

    def collect(self) -> list[RawItem]:
        html = self._fetch_story_html()
        stories = (self._extract_issue_stories(html, self.context.config.get("newsletter"))
                   if self.context.config.get("daily_issue") else self._extract_story_blobs(html))
        newsletter = self.context.config.get("newsletter")
        items: list[RawItem] = []
        for story in stories:
            if newsletter and story.get("newsletter") != newsletter:
                continue
            title = story.get("title", "")
            if re.search(r"\b(sponsor|sponsored)\b", title, re.I):
                continue
            summary = story.get("tldr")
            items.append(
                RawItem(
                    source=self.name,
                    source_type="scrape",
                    category=self.category,
                    external_id=str(story.get("id") or story.get("url")),
                    title=title,
                    url=story.get("url", ""),
                    published_at=parse_datetime(story.get("newsletter_date") or story.get("date")),
                    summary=summary,
                    text=self.resolve_text(story.get("url", ""), summary),
                    image_url=self.resolve_image(
                        story.get("url", ""),
                        story.get("imageUrl"),
                    ),
                    tags=[story.get("category", "")] if story.get("category") else [],
                    entities=entity_candidates(title, summary),
                    symbols=ticker_candidates(title, summary),
                    engagement={"clicks": int(story.get("totalClicks", 0) or 0)},
                    raw=story,
                )
            )
            if len(items) >= int(self.context.config.get("max_items_per_run", 25)):
                break
        if not items:
            raise CollectorDegraded("unable to parse TLDR hydration payload")
        return items

    def _fetch_story_html(self) -> str:
        primary_response = self.client.get(self.context.config["url"])
        primary_response.raise_for_status()
        primary_html = primary_response.text
        if self.context.config.get("daily_issue"):
            return primary_html
        if self._extract_story_blobs(primary_html):
            return primary_html
        fallback_response = self.client.get("https://tldr.tech")
        fallback_response.raise_for_status()
        return fallback_response.text

    @staticmethod
    def _extract_issue_stories(html: str, newsletter: str) -> list[dict]:
        page = HTMLParser(html)
        heading = page.css_first("h1")
        date = re.search(r"\b\d{4}-\d{2}-\d{2}\b", heading.text() if heading else "")
        if not date:
            return []
        stories = {}
        for article in page.css("article"):
            link = article.css_first("a:has(h3)")
            summary = article.css_first(".newsletter-html")
            if not link or not summary:
                continue
            title = link.text().strip()
            url = unescape(link.attributes.get("href", ""))
            host = urlparse(url).hostname or ""
            if (urlparse(url).scheme not in {"http", "https"}
                    or re.search(r"\b(sponsor|sponsored)\b", title, re.I)
                    or host in {"jobs.ashbyhq.com", "jobs.tldr.tech"}):
                continue
            title = re.sub(r"\s*\((?:\d+ minute read|GitHub Repo|\d+ minute video)\)\s*$", "", title)
            stories[url] = {"title": title, "url": url, "tldr": summary.text(separator=" ").strip(),
                            "newsletter": newsletter, "newsletter_date": date.group(),
                            "_newsletter_url": f"https://tldr.tech/{newsletter}/{date.group()}"}
        return list(stories.values())

    @staticmethod
    def _extract_story_blobs(html: str) -> list[dict]:
        decoder = json.JSONDecoder()
        chunks = []
        for match in re.finditer(r'self\.__next_f\.push\(', html):
            try:
                payload, _ = decoder.raw_decode(html[match.end():])
                if isinstance(payload, list) and len(payload) > 1 and isinstance(payload[1], str):
                    chunks.append(payload[1])
            except (ValueError, TypeError):
                continue
        decoded_html = "".join(chunks)
        found = {}
        for match in re.finditer(r'"(?:featuredStories|product|ai|tech)"\s*:\s*', decoded_html):
            try:
                values, _ = decoder.raw_decode(decoded_html[match.end():])
                if isinstance(values, list):
                    for story in values:
                        if isinstance(story, dict) and story.get("url") and story.get("title"):
                            found[story["url"]] = story
            except (ValueError, TypeError):
                continue
        if found:
            return list(found.values())
        for pattern in (
            r'featuredStories\\":(\[.*?\])[,}]',
            r'product\\":(\[.*?\])[,}]',
            r'ai\\":(\[.*?\])[,}]',
            r'tech\\":(\[.*?\])[,}]',
        ):
            for match in re.finditer(pattern, html):
                decoded = bytes(match.group(1), "utf-8").decode("unicode_escape")
                parsed = safe_json_loads(decoded)
                if isinstance(parsed, list) and parsed:
                    stories = [
                        story
                        for story in parsed
                        if isinstance(story, dict) and story.get("url") and story.get("title")
                    ]
                    if stories:
                        return stories
        # Fallback for legacy simple embedded blobs.
        blobs = re.findall(r'\{"url":"https?://.*?"title":".*?"\}', html)
        stories = []
        for blob in blobs:
            parsed = safe_json_loads(blob)
            if isinstance(parsed, dict) and parsed.get("url") and parsed.get("title"):
                stories.append(parsed)
        return stories
