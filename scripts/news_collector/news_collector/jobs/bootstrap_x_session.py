from __future__ import annotations

import json

from news_collector.settings import get_settings


def main() -> None:
    settings = get_settings()
    settings.x_profile_dir.mkdir(parents=True, exist_ok=True)
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - runtime environment dependent
        raise SystemExit(f"Playwright unavailable: {exc}")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch_persistent_context(
            user_data_dir=str(settings.x_profile_dir),
            headless=False,
            viewport={"width": 1440, "height": 1280},
        )
        page = browser.new_page()
        page.goto("https://x.com/login", wait_until="domcontentloaded")
        print(
            json.dumps(
                {
                    "status": "awaiting_login",
                    "profile_dir": str(settings.x_profile_dir),
                    "message": "Log in to X in the opened browser window, then press Enter here to close it.",
                },
                indent=2,
            )
        )
        input()
        browser.close()


if __name__ == "__main__":
    main()
