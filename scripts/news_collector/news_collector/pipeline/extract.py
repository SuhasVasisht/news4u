from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin

import trafilatura
from selectolax.parser import HTMLParser


def extract_text(url: str) -> str | None:
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return None
    return trafilatura.extract(downloaded, include_comments=False, include_tables=False)


def extract_text_from_html(html: str, url: str) -> str | None:
    return trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=False,
    )


def first_image_url(*candidates: str | None) -> str | None:
    for candidate in candidates:
        if candidate and candidate.strip():
            return candidate.strip()
    return None


def extract_image_from_feed_entry(entry: dict[str, Any]) -> str | None:
    for key in ("image", "image_url", "banner_image", "urlToImage", "thumbnail"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    for field in ("media_thumbnail", "media_content", "enclosures"):
        values = entry.get(field) or []
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, dict):
                continue
            image_url = value.get("url") or value.get("href")
            if isinstance(image_url, str) and image_url.strip():
                return image_url.strip()

    return extract_image_from_html_fragment(entry.get("summary") or entry.get("description"), base_url=entry.get("link"))


def extract_image_from_html_fragment(html: str | None, base_url: str | None = None) -> str | None:
    if not html:
        return None
    parser = HTMLParser(html)
    for img in parser.css("img"):
        src = img.attributes.get("src") or img.attributes.get("data-src")
        if src:
            return urljoin(base_url or "", src.strip())
    return None


def extract_image_from_page_html(html: str, page_url: str) -> str | None:
    parser = HTMLParser(html)
    for selector in (
        'meta[property="og:image"]',
        'meta[property="og:image:url"]',
        'meta[name="twitter:image"]',
        'meta[name="twitter:image:src"]',
    ):
        node = parser.css_first(selector)
        if node:
            content = node.attributes.get("content")
            if content:
                return urljoin(page_url, content.strip())

    for script in parser.css('script[type="application/ld+json"]'):
        image_url = _extract_json_ld_image(script.text(), page_url)
        if image_url:
            return image_url

    for selector in ("article img", "main img", "img"):
        node = parser.css_first(selector)
        if not node:
            continue
        src = node.attributes.get("src") or node.attributes.get("data-src")
        if src:
            return urljoin(page_url, src.strip())
    return None


def _extract_json_ld_image(blob: str, page_url: str) -> str | None:
    try:
        payload = json.loads(blob)
    except json.JSONDecodeError:
        return None
    return _find_image_value(payload, page_url)


def _find_image_value(value: Any, page_url: str) -> str | None:
    if isinstance(value, str) and re.match(r"^https?://|^/", value):
        return urljoin(page_url, value.strip())
    if isinstance(value, dict):
        for key in ("image", "thumbnailUrl", "contentUrl", "url"):
            candidate = value.get(key)
            if isinstance(candidate, str) and re.match(r"^https?://|^/", candidate):
                return urljoin(page_url, candidate.strip())
            if isinstance(candidate, (dict, list)):
                nested = _find_image_value(candidate, page_url)
                if nested:
                    return nested
        for nested_value in value.values():
            nested = _find_image_value(nested_value, page_url)
            if nested:
                return nested
    if isinstance(value, list):
        for item in value:
            nested = _find_image_value(item, page_url)
            if nested:
                return nested
    return None
