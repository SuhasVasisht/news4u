from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    project_root: Path
    db_path: Path
    output_dir: Path
    user_agent: str
    newsapi_key: str | None
    guardian_api_key: str | None
    alphavantage_api_key: str | None
    producthunt_token: str | None
    x_profile_dir: Path
    reddit_profile_dir: Path
    sync_outbox_dir: Path | None = None
    app_base_url: str | None = None
    app_sync_api_key: str | None = None
    app_sync_batch_size: int = 200
    replay_batch_size: int = 200


def load_dotenv(project_root: Path) -> None:
    env_path = project_root / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def get_settings() -> Settings:
    project_root = Path(__file__).resolve().parent.parent
    load_dotenv(project_root)
    db_path = Path(os.environ.get("NEWS_COLLECTOR_DB_PATH", project_root / "data/news_collector.db"))
    output_dir = Path(os.environ.get("NEWS_COLLECTOR_OUTPUT_DIR", project_root / "output"))
    sync_outbox_dir = Path(os.environ.get("NEWS_COLLECTOR_SYNC_OUTBOX_DIR", output_dir / "sync"))
    return Settings(
        project_root=project_root,
        db_path=db_path,
        output_dir=output_dir,
        sync_outbox_dir=sync_outbox_dir,
        user_agent=os.environ.get(
            "NEWS_COLLECTOR_USER_AGENT",
            "news-collector/0.1 (local development; contact@example.com)",
        ),
        newsapi_key=os.environ.get("NEWSAPI_KEY") or None,
        guardian_api_key=os.environ.get("GUARDIAN_API_KEY") or None,
        alphavantage_api_key=os.environ.get("ALPHAVANTAGE_API_KEY") or None,
        producthunt_token=os.environ.get("PRODUCTHUNT_TOKEN") or None,
        app_base_url=os.environ.get("NEWS_APP_BASE_URL") or None,
        app_sync_api_key=os.environ.get("NEWS_APP_SYNC_API_KEY") or None,
        app_sync_batch_size=int(os.environ.get("NEWS_APP_SYNC_BATCH_SIZE", "200")),
        replay_batch_size=int(os.environ.get("NEWS_COLLECTOR_REPLAY_BATCH_SIZE", "200")),
        x_profile_dir=Path(os.environ.get("NEWS_COLLECTOR_X_PROFILE_DIR", project_root / "data/x_profile")),
        reddit_profile_dir=Path(
            os.environ.get("NEWS_COLLECTOR_REDDIT_PROFILE_DIR", project_root / "data/reddit_profile")
        ),
    )
