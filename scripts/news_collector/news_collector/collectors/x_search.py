from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from news_collector.collectors.base import BaseCollector, CollectorDegraded
from news_collector.models import RawItem
from news_collector.utils import entity_candidates, parse_datetime, ticker_candidates


class XSearchCollector(BaseCollector):
    source_type = "x"

    def collect(self) -> list[RawItem]:
        profile_dir = Path(self.context.settings.x_profile_dir)
        if not profile_dir.exists():
            raise CollectorDegraded("missing persistent X browser profile")
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # pragma: no cover - import path validated by runtime/tests
            raise CollectorDegraded(f"Playwright unavailable: {exc}")

        state = self.get_state()
        accounts = self.context.config.get("accounts", [])
        if not accounts:
            raise CollectorDegraded("no tracked X accounts configured")
        cursor = int(state.get("rotation_cursor", 0))
        batch_size = int(self.context.config.get("max_accounts_per_run", 5))
        selected_accounts = [accounts[(cursor + offset) % len(accounts)] for offset in range(min(batch_size, len(accounts)))]
        state["rotation_cursor"] = (cursor + len(selected_accounts)) % len(accounts)
        self.set_state(state)

        items: list[RawItem] = []
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch_persistent_context(
                    user_data_dir=str(profile_dir),
                    headless=True,
                    viewport={"width": 1440, "height": 1280},
                )
            except Exception as exc:
                raise CollectorDegraded(f"unable to launch persistent X browser context: {exc}")
            page = browser.new_page()
            try:
                for index, account in enumerate(selected_accounts):
                    items.extend(self._collect_account_posts(page, account))
                    if index < len(selected_accounts) - 1:
                        self.sleep_range(
                            float(self.context.config.get("min_account_delay_seconds", 0)),
                            float(self.context.config.get("max_account_delay_seconds", 0)),
                        )
            finally:
                browser.close()
        if not items:
            raise CollectorDegraded("X collector found no timeline posts from tracked accounts")
        return items

    def _collect_account_posts(self, page, account: str) -> list[RawItem]:
        from playwright.sync_api import TimeoutError

        url = f"https://x.com/{account}"
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
        except TimeoutError as exc:
            raise CollectorDegraded(f"timed out loading X account {account}: {exc}")

        self.sleep_range(
            float(self.context.config.get("min_scroll_delay_seconds", 1.5)),
            float(self.context.config.get("max_scroll_delay_seconds", 4)),
        )
        html = page.content()
        lowered = html.lower()
        if "something went wrong" in lowered or "verifying your request" in lowered or "log in" in lowered:
            raise CollectorDegraded(f"X account {account} returned an error or verification page")

        scroll_count_min = int(self.context.config.get("scroll_count_min", 2))
        scroll_count_max = int(self.context.config.get("scroll_count_max", scroll_count_min))
        scroll_pixels_min = int(self.context.config.get("scroll_pixels_min", 400))
        scroll_pixels_max = int(self.context.config.get("scroll_pixels_max", scroll_pixels_min))
        for _ in range(scroll_count_min):
            page.mouse.wheel(0, scroll_pixels_min)
            self.sleep_range(
                float(self.context.config.get("min_scroll_delay_seconds", 1.5)),
                float(self.context.config.get("max_scroll_delay_seconds", 4)),
            )
        for _ in range(max(0, scroll_count_max - scroll_count_min)):
            page.mouse.wheel(0, scroll_pixels_max)
            self.sleep_range(
                float(self.context.config.get("min_scroll_delay_seconds", 1.5)),
                float(self.context.config.get("max_scroll_delay_seconds", 4)),
            )

        articles = page.locator("article")
        count = min(articles.count(), int(self.context.config.get("max_posts_per_account", 2)) * 3)
        filters = [term.lower() for term in self.context.config.get("query_filters", [])]
        max_posts = int(self.context.config.get("max_posts_per_account", 2))
        hours_back = int(self.context.config.get("hours_back", 24))
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        items: list[RawItem] = []

        for idx in range(count):
            article = articles.nth(idx)
            try:
                text = article.inner_text(timeout=5000).strip()
            except Exception:
                continue
            if not text:
                continue
            text_lower = text.lower()
            if filters and not any(term.lower() in text_lower for term in filters):
                continue
            status_link = article.locator("a[href*='/status/']").first
            href = status_link.get_attribute("href")
            if not href or "/status/" not in href:
                continue
            full_url = href if href.startswith("http") else f"https://x.com{href}"
            time_node = article.locator("time").first
            published_at = parse_datetime(time_node.get_attribute("datetime") if time_node else None)
            if published_at and published_at < cutoff:
                continue
            outbound_urls = re.findall(r"https?://\S+", text)
            if self.context.config.get("link_required") and not outbound_urls:
                continue
            image_url = None
            try:
                images = article.locator("img")
                for image_idx in range(images.count()):
                    candidate = images.nth(image_idx).get_attribute("src")
                    if candidate and "profile_images" not in candidate and "emoji" not in candidate:
                        image_url = candidate
                        break
            except Exception:
                image_url = None
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            title = lines[0][:280]
            items.append(
                RawItem(
                    source=self.name,
                    source_type="x",
                    category=self.category,
                    external_id=full_url.rsplit("/", 1)[-1],
                    title=title,
                    url=full_url,
                    published_at=published_at,
                    author=f"@{account}",
                    summary=text[:600],
                    image_url=image_url,
                    text=text[:4000],
                    symbols=ticker_candidates(text),
                    entities=entity_candidates(text),
                    engagement={"linked_urls": outbound_urls, "account": account},
                    raw={"account": account, "url": full_url},
                )
            )
            if len(items) >= max_posts:
                break
        return items
