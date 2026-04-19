from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from news_collector.models import NewsItem, RawItem
from news_collector.pipeline.extract import extract_image_from_page_html, extract_text_from_html
from news_collector.pipeline.score import compute_item_score
from news_collector.settings import Settings
from news_collector.storage.repository import Repository
from news_collector.utils import canonicalize_url, get_http_client, parse_datetime, slugify


CATEGORY_TOPIC_MAP = {
    "tech": ("technology", "Technology"),
    "finance": ("markets", "Markets"),
    "politics": ("policy", "Policy"),
    "world": ("world", "World"),
    "other": ("general", "General"),
}

KNOWN_TAG_TOPICS = {
    "technology": ("technology", "Technology"),
    "tech": ("technology", "Technology"),
    "business": ("markets", "Markets"),
    "finance": ("markets", "Markets"),
    "markets": ("markets", "Markets"),
    "politics": ("policy", "Policy"),
    "policy": ("policy", "Policy"),
    "world": ("world", "World"),
}

FORCE_SUMMARY_ONLY_SOURCES = {"alphavantage_movers"}


@dataclass
class PublishResult:
    received: int
    inserted: int
    updated: int
    outbox_dir: str
    feed_dates: list[str]
    last_raw_item_id: int


def raw_item_from_row(row: dict[str, Any]) -> RawItem:
    return RawItem(
        source=row["source"],
        source_type=row["source_type"],
        category=row["category"],
        external_id=row.get("external_id"),
        title=row["title"],
        url=row["url"],
        published_at=parse_datetime(row.get("published_at")),
        author=row.get("author"),
        summary=row.get("summary"),
        image_url=row.get("image_url"),
        text=row.get("text"),
        tags=json.loads(row.get("tags_json") or "[]"),
        symbols=json.loads(row.get("symbols_json") or "[]"),
        entities=json.loads(row.get("entities_json") or "[]"),
        engagement=json.loads(row.get("engagement_json") or "{}"),
        raw=json.loads(row.get("raw_json") or "{}"),
        fetched_at=parse_datetime(row.get("fetched_at")) or datetime.now(timezone.utc),
    )


def synthetic_external_id(item: RawItem) -> str:
    payload = "|".join(
        [
            item.source,
            canonicalize_url(item.url),
            item.published_at.isoformat() if item.published_at else "na",
            item.title.strip(),
        ]
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"synthetic:{digest}"


def looks_article_like(url: str) -> bool:
    if not url.startswith("http"):
        return False
    canonical = canonicalize_url(url)
    if canonical.endswith("/"):
        return False
    path = canonical.split("://", 1)[-1].split("/", 1)
    if len(path) < 2:
        return False
    article_path = path[1]
    return len(article_path) > 8 and article_path.count("/") >= 1


def compact_text(value: str | None, fallback: str) -> str:
    candidate = (value or "").strip()
    if candidate:
        return candidate[:20000]
    return fallback.strip()[:20000]


def content_source(item: RawItem, used_page_fetch: bool) -> str:
    if item.source_type == "x":
        return "post_text"
    if item.text and item.text.strip():
        return "html_extract" if used_page_fetch else "source_text"
    if item.summary and item.summary.strip():
        return "summary_fallback"
    return "title_fallback"


def map_topics(item: RawItem) -> list[dict[str, str]]:
    topics: list[dict[str, str]] = []
    default_slug, default_name = CATEGORY_TOPIC_MAP.get(item.category, CATEGORY_TOPIC_MAP["other"])
    topics.append({"slug": default_slug, "name": default_name})
    for tag in item.tags:
        mapped = KNOWN_TAG_TOPICS.get((tag or "").strip().lower())
        if not mapped:
            continue
        topic = {"slug": mapped[0], "name": mapped[1]}
        if topic not in topics:
            topics.append(topic)
    return topics


def feed_date_for_timestamp(timestamp: datetime | None) -> str:
    return (timestamp or datetime.now(timezone.utc)).date().isoformat()


def utc_isoformat(timestamp: datetime) -> str:
    return timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def collector_importance_score(item: RawItem, trust_score: float) -> float:
    normalized = NewsItem(
        source=item.source,
        source_type=item.source_type,
        category=item.category,
        title=item.title.strip(),
        url=item.url,
        canonical_url=canonicalize_url(item.url),
        published_at=item.published_at,
        author=item.author,
        image_url=item.image_url,
        text=item.text,
        summary=item.summary,
        symbols=item.symbols,
        entities=item.entities,
        tags=item.tags,
        engagement=item.engagement,
        fingerprint="sync-payload",
        raw=item.raw,
    )
    return compute_item_score(
        normalized,
        trust_score=trust_score,
        confirmation_score=0.0,
        market_impact_score=1.0 if normalized.symbols else 0.0,
    )


def enrich_item(
    item: RawItem,
    repository: Repository,
    client: httpx.Client,
    checked_at: str | None = None,
) -> tuple[RawItem, bool]:
    checked_at = checked_at or datetime.now(timezone.utc).isoformat()
    canonical_url = canonicalize_url(item.url)
    used_page_fetch = False

    cached_image = repository.get_cached_image(canonical_url) if canonical_url else False
    cached_content = repository.get_cached_content(canonical_url) if canonical_url else False

    image_url = item.image_url if item.image_url and item.image_url.strip() else None
    if not image_url and cached_image is not False:
        image_url = cached_image

    text = item.text.strip() if item.text and item.text.strip() else None
    if not text and cached_content is not False:
        text = (cached_content.get("content_text") or "").strip() or None

    should_fetch_page = (
        item.source not in FORCE_SUMMARY_ONLY_SOURCES
        and looks_article_like(item.url)
        and (not text or not image_url)
        and item.source_type != "x"
    )

    if should_fetch_page:
        used_page_fetch = True
        extracted_text = None
        extracted_image = None
        error = None
        try:
            response = client.get(item.url)
            if response.status_code < 400:
                extracted_text = extract_text_from_html(response.text, item.url)
                extracted_image = extract_image_from_page_html(response.text, item.url)
            else:
                error = f"http {response.status_code}"
        except Exception as exc:
            error = str(exc)

        if extracted_text and not text:
            text = extracted_text.strip()
        if extracted_image and not image_url:
            image_url = extracted_image.strip()
        if canonical_url:
            repository.set_cached_content(
                canonical_url,
                extracted_text.strip() if extracted_text else None,
                checked_at,
                status="ok" if extracted_text else "missing",
                error=error,
            )
            repository.set_cached_image(canonical_url, extracted_image.strip() if extracted_image else image_url, checked_at)

    text = compact_text(text, item.summary or item.title)
    if canonical_url:
        if cached_content is False and not should_fetch_page:
            repository.set_cached_content(
                canonical_url,
                text,
                checked_at,
                status="ok" if text else "missing",
                error=None,
            )
        if cached_image is False and image_url is not None:
            repository.set_cached_image(canonical_url, image_url, checked_at)

    enriched = item.model_copy(update={"text": text, "image_url": image_url})
    return enriched, used_page_fetch


def build_sync_article(item: RawItem, used_page_fetch: bool, *, trust_score: float) -> dict[str, Any]:
    topic_rows = map_topics(item)
    external_id = item.external_id or synthetic_external_id(item)
    summary = (item.summary or item.title).strip() or item.title.strip()
    importance_score = collector_importance_score(item, trust_score)
    payload_json = {
        "collector": {
            "source_type": item.source_type,
            "category": item.category,
            "trust_score": trust_score,
            "importance_score": importance_score,
            "tags": item.tags,
            "entities": item.entities,
            "symbols": item.symbols,
            "engagement": item.engagement,
            "raw": item.raw,
            "content_source": content_source(item, used_page_fetch),
        }
    }
    return {
        "external_id": external_id,
        "title": item.title.strip(),
        "summary": summary,
        "author": item.author,
        "url": item.url,
        "image_url": item.image_url,
        "published_at": utc_isoformat(item.published_at or datetime.now(timezone.utc)),
        "content_text": compact_text(item.text, summary),
        "score": None,
        "payload_json": payload_json,
        "source": {
            "slug": slugify(item.source),
            "name": item.source.replace("_", " ").title(),
            "homepage_url": None,
            "icon_url": None,
        },
        "topics": topic_rows,
    }


def write_outbox_bundle(
    settings: Settings,
    articles: list[dict[str, Any]],
    *,
    batch_label: str,
    feed_dates: list[str],
    source_counts: dict[str, int],
) -> Path:
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{batch_label}"
    outbox_dir = settings.sync_outbox_dir / run_id
    outbox_dir.mkdir(parents=True, exist_ok=True)
    payload_path = outbox_dir / "articles.json"
    payload_path.write_text(json.dumps({"articles": articles}, indent=2))
    checksum = hashlib.sha256(payload_path.read_bytes()).hexdigest()
    manifest = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "article_count": len(articles),
        "feed_dates": feed_dates,
        "source_counts": source_counts,
        "checksum": checksum,
        "attempt_count": 0,
        "delivered_at": None,
        "last_status_code": None,
    }
    (outbox_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return outbox_dir


def update_outbox_manifest(
    outbox_dir: Path,
    *,
    status_code: int | None,
    delivered: bool,
    response_payload: dict[str, Any] | None = None,
) -> None:
    manifest_path = outbox_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["attempt_count"] = int(manifest.get("attempt_count", 0)) + 1
    manifest["last_status_code"] = status_code
    manifest["delivered_at"] = datetime.now(timezone.utc).isoformat() if delivered else None
    manifest_path.write_text(json.dumps(manifest, indent=2))
    if response_payload is not None:
        (outbox_dir / "last_response.json").write_text(json.dumps(response_payload, indent=2))


def refresh_feed_dates(
    client: httpx.Client,
    settings: Settings,
    feed_dates: list[str],
) -> None:
    if not settings.app_base_url or not settings.app_sync_api_key:
        return
    endpoint = settings.app_base_url.rstrip("/") + "/api/internal/feed/generate"
    headers = {"Authorization": f"Bearer {settings.app_sync_api_key}"}
    # Rebuilding historical feed dates from current story rollups leaks future
    # state into older snapshots. Refresh the current app feed only.
    response = client.post(endpoint, headers=headers, json={"force_refresh": True})
    response.raise_for_status()


def publish_articles(
    repository: Repository,
    settings: Settings,
    rows: list[dict[str, Any]],
    *,
    trust_scores: dict[str, float],
    batch_label: str,
) -> PublishResult:
    if not settings.app_base_url or not settings.app_sync_api_key:
        raise RuntimeError("NEWS_APP_BASE_URL and NEWS_APP_SYNC_API_KEY are required for publishing")

    client = get_http_client(settings.user_agent, timeout=30.0)
    sync_articles: list[dict[str, Any]] = []
    source_counts: dict[str, int] = {}
    feed_dates: set[str] = set()
    last_raw_item_id = 0

    for row in rows:
        raw_item = raw_item_from_row(row)
        enriched_item, used_page_fetch = enrich_item(raw_item, repository, client)
        repository.update_raw_item_content(row["id"], enriched_item.text, enriched_item.image_url)
        repository.update_normalized_item_content(canonicalize_url(enriched_item.url), enriched_item.text, enriched_item.image_url)
        payload = build_sync_article(
            enriched_item,
            used_page_fetch,
            trust_score=trust_scores.get(enriched_item.source, 0.5),
        )
        sync_articles.append(payload)
        source_counts[payload["source"]["slug"]] = source_counts.get(payload["source"]["slug"], 0) + 1
        feed_dates.add(feed_date_for_timestamp(enriched_item.published_at))
        last_raw_item_id = max(last_raw_item_id, int(row["id"]))

    outbox_dir = write_outbox_bundle(
        settings,
        sync_articles,
        batch_label=batch_label,
        feed_dates=sorted(feed_dates),
        source_counts=source_counts,
    )

    endpoint = settings.app_base_url.rstrip("/") + "/api/internal/articles/sync"
    response = client.post(
        endpoint,
        headers={"Authorization": f"Bearer {settings.app_sync_api_key}"},
        json={"articles": sync_articles},
    )
    response_payload = response.json()
    update_outbox_manifest(outbox_dir, status_code=response.status_code, delivered=response.is_success, response_payload=response_payload)
    response.raise_for_status()
    refresh_feed_dates(client, settings, sorted(feed_dates) or [feed_date_for_timestamp(None)])

    return PublishResult(
        received=response_payload.get("received", len(sync_articles)),
        inserted=response_payload.get("inserted", 0),
        updated=response_payload.get("updated", 0),
        outbox_dir=str(outbox_dir),
        feed_dates=sorted(feed_dates),
        last_raw_item_id=last_raw_item_id,
    )
