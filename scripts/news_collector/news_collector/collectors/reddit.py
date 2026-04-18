from __future__ import annotations

import re
from pathlib import Path

from news_collector.collectors.base import BaseCollector, CollectorDegraded
from news_collector.models import RawItem
from news_collector.utils import entity_candidates, ticker_candidates


class RedditCollector(BaseCollector):
    source_type = "scrape"

    def collect(self) -> list[RawItem]:
        profile_dir = Path(self.context.settings.reddit_profile_dir)
        if not profile_dir.exists():
            raise CollectorDegraded("missing persistent Reddit browser profile")
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # pragma: no cover
            raise CollectorDegraded(f"Playwright unavailable: {exc}")

        subreddits = self.context.config.get("subreddits", [])
        if not subreddits:
            raise CollectorDegraded("no subreddits configured")

        items: list[RawItem] = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=True,
                viewport={"width": 1440, "height": 1280},
            )
            try:
                page = browser.new_page()
                for subreddit in subreddits[: int(self.context.config.get("max_subreddits_per_run", len(subreddits)))]:
                    items.extend(self._collect_subreddit(page, subreddit))
            finally:
                browser.close()
        if not items:
            raise CollectorDegraded("Reddit collector found no posts")
        return items

    def _collect_subreddit(self, page, subreddit: str) -> list[RawItem]:
        url = f"https://www.reddit.com/r/{subreddit}/"
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(3000)
        body_text = page.locator("body").inner_text(timeout=5000)
        lowered = body_text.lower()
        if "blocked by network security" in lowered or "wait for verification" in lowered:
            raise CollectorDegraded(f"Reddit subreddit {subreddit} returned a block or verification page")

        posts = page.locator("a[href*='/comments/']")
        items: list[RawItem] = []
        seen_urls: set[str] = set()
        limit = int(self.context.config.get("max_posts_per_subreddit", 10))
        for idx in range(posts.count()):
            if len(items) >= limit:
                break
            link = posts.nth(idx)
            href = link.get_attribute("href")
            title = link.inner_text(timeout=2000).strip()
            if not href or not title:
                continue
            permalink = href if href.startswith("http") else f"https://www.reddit.com{href}"
            if permalink in seen_urls:
                continue
            seen_urls.add(permalink)
            container_text = link.locator("xpath=ancestor::*[self::article or self::div][1]").inner_text(timeout=2000)
            outbound_urls = [candidate for candidate in re.findall(r"https?://\S+", container_text) if "reddit.com" not in candidate]
            items.append(
                RawItem(
                    source=self.name,
                    source_type="scrape",
                    category=self.category,
                    external_id=permalink.rstrip("/").rsplit("/", 1)[-1],
                    title=title,
                    url=outbound_urls[0] if outbound_urls else permalink,
                    author=f"r/{subreddit}",
                    summary=container_text[:600],
                    text=self.resolve_text(outbound_urls[0], container_text[:4000]) if outbound_urls else container_text[:4000],
                    image_url=None,
                    symbols=ticker_candidates(title, container_text),
                    entities=entity_candidates(title, container_text),
                    engagement={"subreddit": subreddit, "permalink": permalink, "linked_urls": outbound_urls},
                    raw={"subreddit": subreddit, "permalink": permalink},
                )
            )
        return items
