from __future__ import annotations

from pathlib import Path

from news_collector.settings import get_settings


def main() -> None:
    settings = get_settings()
    profile_dir = Path(settings.reddit_profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover
        raise SystemExit(f"Playwright unavailable: {exc}")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            viewport={"width": 1440, "height": 1280},
        )
        page = browser.new_page()
        page.goto("https://www.reddit.com/", wait_until="domcontentloaded")
        print("Authenticate in the opened browser window if needed, then press Enter here to save the session.")
        input()
        browser.close()


if __name__ == "__main__":
    main()
