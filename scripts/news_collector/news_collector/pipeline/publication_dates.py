"""Publisher dates for articles discovered through dated newsletters."""
import json

from selectolax.parser import HTMLParser

from news_collector.utils import parse_datetime


def needs_publisher_date(row):
    raw = json.loads(row.get("raw_json") or "{}")
    return row.get("source") in {"tldr_tech", "tldr_ai"} or raw.get("_date_basis") == "newsletter_sent_at"


def article_publication_date(html):
    page = HTMLParser(html)
    for selector in ('meta[property="article:published_time"]', 'meta[name="datePublished"]',
                     'meta[itemprop="datePublished"]', 'time[itemprop="datePublished"]'):
        node = page.css_first(selector)
        if node:
            date = parse_datetime(node.attributes.get("content") or node.attributes.get("datetime") or node.text())
            if date:
                return date

    def articles(value):
        if isinstance(value, list):
            for item in value:
                yield from articles(item)
        elif isinstance(value, dict):
            types = value.get("@type", [])
            types = [types] if isinstance(types, str) else types
            if any(kind in {"Article", "NewsArticle", "BlogPosting", "TechArticle"} for kind in types):
                yield value
            yield from articles(value.get("@graph", []))

    for node in page.css('script[type="application/ld+json"]'):
        try:
            payload = json.loads(node.text())
        except (ValueError, TypeError):
            continue
        for article in articles(payload):
            date = parse_datetime(article.get("datePublished"))
            if date:
                return date
    return None
