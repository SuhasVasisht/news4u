from __future__ import annotations

from pathlib import Path
import os
from typing import Any

import yaml

from news_collector.settings import get_settings


def load_config() -> dict[str, Any]:
    settings = get_settings()
    config_path = settings.project_root / "config" / "sources.yaml"
    config = yaml.safe_load(config_path.read_text())
    for source in config["collectors"]:
        if source.get("enabled_env"):
            source["enabled"] = source.get("enabled", True) and os.environ.get(source["enabled_env"]) == "1"
    return config


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
