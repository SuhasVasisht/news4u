from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from news_collector.settings import get_settings


def load_config() -> dict[str, Any]:
    settings = get_settings()
    config_path = settings.project_root / "config" / "sources.yaml"
    return yaml.safe_load(config_path.read_text())


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

