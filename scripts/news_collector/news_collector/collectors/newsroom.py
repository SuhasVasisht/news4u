from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone
import re

from selectolax.parser import HTMLParser

from news_collector.collectors.base import BaseCollector
from news_collector.models import RawItem
from news_collector.pipeline.extract import extract_image_from_page_html, extract_text_from_html
from news_collector.utils import parse_datetime


class NewsroomCollector(BaseCollector):
    source_type = "scrape"

    def collect(self):
        base = self.context.config["url"]
        response = self.client.get(base)
        response.raise_for_status()
        page = HTMLParser(response.text)
        links = {}
        for anchor in page.css("a[href]"):
            url = urljoin(base, anchor.attributes["href"])
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.hostname != urlparse(base).hostname or parsed.fragment:
                continue
            time = anchor.css_first("time")
            dated = parse_datetime(time.attributes.get("datetime") or time.text()) if time else None
            if not dated and not parsed.path.startswith("/news/"):
                continue
            links[url] = dated or links.get(url)
        # Featured cards can be older than the chronological list, and new reports
        # may live outside /news/. The publisher's dated card is the discovery signal.
        urls = sorted(links, key=lambda url: links[url] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        items = []
        for url in urls[:self.context.config.get("limit", 6)]:
            if urlparse(url).hostname != urlparse(base).hostname:
                continue
            response = self.client.get(url)
            response.raise_for_status()
            html = HTMLParser(response.text)
            heading = html.css_first("h1")
            main = html.css_first("main")
            if not heading or not main:
                continue
            text = main.text(separator="\n")
            date = re.search(r"\b[A-Z][a-z]{2,8} \d{1,2}, 20\d{2}\b", text[:1500])
            published = links[url] or (parse_datetime(date.group()) if date else None)
            if not published:
                continue
            body = extract_text_from_html(response.text, url) or text
            items.append(RawItem(source=self.name, source_type="scrape", category=self.category,
                title=heading.text(), url=url, published_at=published, text=body, summary=body[:800],
                image_url=extract_image_from_page_html(response.text, url),
                raw={"_editorial_type": "announcement"}))
        return items
