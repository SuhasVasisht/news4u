from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
import json

from news_collector.models import RawItem
from news_collector.pipeline.extract import extract_image_from_page_html, extract_text_from_html, first_image_url
from news_collector.utils import canonicalize_url
from news_collector.utils import get_http_client


@dataclass
class CollectorContext:
    name: str
    config: dict[str, Any]
    defaults: dict[str, Any]
    settings: Any
    repository: Any


@dataclass
class CollectorRunResult:
    collector: str
    status: str
    items: list[RawItem] = field(default_factory=list)
    reason: str | None = None
    stats: dict[str, Any] = field(default_factory=dict)


class CollectorDegraded(RuntimeError):
    """Signal a collector that should be treated as degraded, not crashed."""


class BaseCollector:
    source_type = "api"

    def __init__(self, context: CollectorContext):
        self.context = context
        self._force_run = False
        self._used_cache = False
        timeout = float(context.defaults.get("request_timeout_seconds", 20))
        self.client = get_http_client(context.settings.user_agent, timeout=timeout)

    @property
    def name(self) -> str:
        return self.context.name

    @property
    def category(self) -> str:
        return self.context.config["category"]

    @property
    def repository(self):
        return self.context.repository

    def get_state(self) -> dict[str, Any]:
        return self.repository.db.get_source_state(self.name)

    def set_state(self, state: dict[str, Any]) -> None:
        self.repository.db.set_source_state(self.name, state)

    def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def cached_items(self, max_age_hours: float = 72.0) -> list[RawItem]:
        state = self.get_state()
        cached_at = state.get("last_success_items_at")
        serialized = state.get("last_success_items")
        items: list[RawItem] = []
        if cached_at and isinstance(serialized, list):
            try:
                age = datetime.now(timezone.utc) - datetime.fromisoformat(cached_at)
            except ValueError:
                age = None
            if age is not None and timedelta(0) <= age <= timedelta(hours=max_age_hours):
                for payload in serialized:
                    try:
                        items.append(RawItem.model_validate(payload))
                    except Exception:
                        continue
        if items:
            self._used_cache = True
            return items
        fallback_rows = self.repository.fetch_recent_raw_items_by_source(
            self.name,
            limit=25,
            limit_hours=int(max_age_hours),
        )
        for row in fallback_rows:
            try:
                items.append(
                    RawItem(
                        source=row["source"],
                        source_type=row["source_type"],
                        category=row["category"],
                        external_id=row.get("external_id"),
                        title=row["title"],
                        url=row["url"],
                        published_at=datetime.fromisoformat(row["published_at"]) if row.get("published_at") else None,
                        author=row.get("author"),
                        summary=row.get("summary"),
                        image_url=row.get("image_url"),
                        text=row.get("text"),
                        tags=json.loads(row.get("tags_json") or "[]"),
                        symbols=json.loads(row.get("symbols_json") or "[]"),
                        entities=json.loads(row.get("entities_json") or "[]"),
                        engagement=json.loads(row.get("engagement_json") or "{}"),
                        raw=json.loads(row.get("raw_json") or "{}"),
                        fetched_at=datetime.fromisoformat(row["fetched_at"]),
                    )
                )
            except Exception:
                continue
        if items:
            self._used_cache = True
        return items

    def is_in_cooldown(self, state: dict[str, Any]) -> tuple[bool, str | None]:
        cooldown_until = state.get("cooldown_until")
        if not cooldown_until:
            return False, None
        try:
            if datetime.fromisoformat(cooldown_until) > datetime.now(timezone.utc):
                return True, cooldown_until
        except ValueError:
            return False, None
        return False, None

    def should_run_on_schedule(self, state: dict[str, Any]) -> bool:
        schedule_hours = self.context.config.get("schedule_hours")
        if not schedule_hours:
            return True
        last_run_at = state.get("last_run_at")
        if not last_run_at:
            return True
        try:
            last_run = datetime.fromisoformat(last_run_at)
        except ValueError:
            return True
        return datetime.now(timezone.utc) - last_run >= timedelta(hours=float(schedule_hours))

    def sleep_range(self, min_seconds: float, max_seconds: float) -> None:
        if max_seconds <= 0:
            return
        time.sleep(random.uniform(min_seconds, max_seconds))

    def maybe_initial_delay(self) -> None:
        delay = self.context.config.get("human_initial_delay_seconds") or self.context.defaults.get(
            "unofficial_initial_delay_seconds",
            {},
        )
        if not self.context.config.get("unofficial"):
            return
        min_seconds = float(delay.get("min", 0))
        max_seconds = float(delay.get("max", min_seconds))
        self.sleep_range(min_seconds, max_seconds)

    def run(self, force: bool = False, check_now: bool = False) -> CollectorRunResult:
        state = self.get_state()
        self._force_run = force
        self._used_cache = False
        if not force:
            in_cooldown, until = self.is_in_cooldown(state)
            if in_cooldown:
                return CollectorRunResult(self.name, "degraded", reason=f"cooldown until {until}", stats=state)
            if not check_now and not self.should_run_on_schedule(state):
                return CollectorRunResult(self.name, "skipped", reason="scheduled later", stats=state)

        if not force:
            state["last_run_at"] = self.now_iso()
            self.set_state(state)
        try:
            self.maybe_initial_delay()
            items = self.collect()
        except CollectorDegraded as exc:
            if not force:
                state = self.get_state()
                cooldown_hours = float(self.context.config.get("cooldown_hours", 24))
                state["last_blocked_at"] = self.now_iso()
                state["cooldown_until"] = (datetime.now(timezone.utc) + timedelta(hours=cooldown_hours)).isoformat()
                state["last_reason"] = str(exc)
                state["last_status"] = "degraded"
                self.set_state(state)
            return CollectorRunResult(self.name, "degraded", reason=str(exc), stats=state)
        except Exception as exc:
            state["last_status"] = "error"
            state["last_reason"] = str(exc).split("?", 1)[0]
            self.set_state(state)
            return CollectorRunResult(self.name, "error", reason=state["last_reason"], stats=state)
        finally:
            self._force_run = False

        state = self.get_state()
        if items and not self._used_cache:
            state["last_success_items_at"] = self.now_iso()
            state["last_success_items"] = [item.model_dump(mode="json") for item in items[:25]]
        if not force and not self._used_cache:
            state["last_success_at"] = self.now_iso()
            state["cooldown_until"] = None
            state["last_reason"] = None
            state["consecutive_zero_runs"] = 0 if items else int(state.get("consecutive_zero_runs", 0)) + 1
        state["last_status"] = "ok" if items else "degraded"
        if self._used_cache:
            state["last_status"] = "cached"
            state["last_reason"] = "Using cached items; upstream did not provide a fresh response"
        elif items and state.get("collection_warning"):
            state["last_status"] = "partial"
            state["last_reason"] = state["collection_warning"]
        if not items:
            state["last_reason"] = "collector returned zero items"
        self.set_state(state)
        return CollectorRunResult(
            self.name,
            state["last_status"],
            items=items,
            reason=state.get("last_reason") if self._used_cache or state.get("collection_warning") else None if items else "collector returned zero items",
            stats=state,
        )

    def collect(self) -> list[RawItem]:
        raise NotImplementedError

    def resolve_image(
        self,
        item_url: str,
        *candidates: str | None,
        fetch_page: bool = True,
    ) -> str | None:
        image_url = first_image_url(*candidates)
        if image_url or not item_url:
            return image_url

        canonical_url = canonicalize_url(item_url)
        cached_image = self.repository.get_cached_image(canonical_url)
        if cached_image is not False:
            return cached_image

        resolved = None
        if fetch_page:
            try:
                response = self.client.get(item_url)
                if response.status_code < 400:
                    resolved = extract_image_from_page_html(response.text, item_url)
            except Exception:
                resolved = None
        self.repository.set_cached_image(canonical_url, resolved, self.now_iso())
        return resolved

    def resolve_text(
        self,
        item_url: str,
        *candidates: str | None,
        fetch_page: bool = True,
    ) -> str | None:
        for candidate in candidates:
            if candidate and candidate.strip():
                return candidate.strip()
        if not item_url:
            return None

        canonical_url = canonicalize_url(item_url)
        cached_content = self.repository.get_cached_content(canonical_url)
        if cached_content is not False:
            return cached_content.get("content_text")

        extracted = None
        error = None
        if fetch_page:
            try:
                response = self.client.get(item_url)
                if response.status_code < 400:
                    extracted = extract_text_from_html(response.text, item_url)
                else:
                    error = f"http {response.status_code}"
            except Exception as exc:
                error = str(exc)
        self.repository.set_cached_content(
            canonical_url,
            extracted,
            self.now_iso(),
            status="ok" if extracted else "missing",
            error=error,
        )
        return extracted
