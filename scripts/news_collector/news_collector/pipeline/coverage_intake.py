"""Bring independently discovered mandatory articles into the ordinary news desk."""
from datetime import datetime, timedelta
import json

import httpx
from selectolax.parser import HTMLParser

from news_collector.models import RawItem
from news_collector.utils import canonicalize_url
from .extract import extract_text_from_html, extract_image_from_page_html
from .images import download, prepare_images
from .normalize import normalize_item
from .publication_dates import article_publication_date


def collect_required_sources(checklist, cutoff, repository, user_agent):
    sources = {canonicalize_url(source["url"]): source
               for event in checklist["events"] if event["mustCover"]
               for source in event["sources"]}
    if len(sources) > 30:
        raise ValueError("Mandatory coverage intake is limited to 30 direct sources")
    existing = {row["canonical_url"] for row in repository.fetch_recent_items(limit_hours=48)}
    available = set()
    with httpx.Client(timeout=10, follow_redirects=False, headers={"User-Agent": user_agent}) as client:
        for url, source in sources.items():
            if url in existing:
                available.add(url)
                continue
            try:
                body, final_url = download(client, source["url"], 2_000_000)
                html = body.decode("utf-8", errors="replace")
                date = article_publication_date(html)
                text = extract_text_from_html(html, final_url) or ""
                claimed = datetime.fromisoformat(source["publishedAt"])
                if (not date or date.tzinfo is None or len(text.split()) < 80
                        or not cutoff - timedelta(hours=48) <= date <= cutoff + timedelta(minutes=5)
                        or claimed.date() not in {date.date(), date.astimezone(cutoff.tzinfo).date()}):
                    raise ValueError("Unavailable, stale, undated or mismatched publisher evidence")
                page = HTMLParser(html)
                meta = page.css_first('meta[property="og:title"]')
                heading = page.css_first("h1") or page.css_first("title")
                title = (meta.attributes.get("content", "") if meta else "") or (heading.text().strip() if heading else "")
                if not title:
                    raise ValueError("Publisher article has no title")
                raw = RawItem(source="coverage_research", source_type="scrape", category="world",
                              title=title, url=final_url, published_at=date, text=text,
                              image_url=extract_image_from_page_html(html, final_url),
                              raw={"_coverage_discovery_url": url})
                prepare_images([raw], repository, user_agent)
                normalized = normalize_item(raw)
                repository.insert_raw_item(raw)
                repository.insert_normalized_item(normalized)
                available.add(normalized.canonical_url)
                print(json.dumps({"event": "coverage_intake", "url": url, "status": "collected",
                                  "publisherDate": date.isoformat(), "articleWords": len(text.split())}), flush=True)
            except (httpx.HTTPError, ValueError, OSError) as exc:
                # Intake failure never waives the event; the final audit still blocks it.
                print(json.dumps({"event": "coverage_intake", "url": url, "status": "unavailable",
                                  "reason": str(exc)[:300]}), flush=True)
    return available
