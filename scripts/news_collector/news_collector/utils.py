from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
from dateutil import parser as date_parser


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "at_medium",
    "at_campaign",
    "rss",
}

TICKER_STOPWORDS = {
    "AP",
    "BBC",
    "EU",
    "FDA",
    "GOP",
    "ICE",
    "IEA",
    "IRS",
    "NATO",
    "PM",
    "SEC",
    "UK",
    "UN",
    "US",
}


def get_http_client(user_agent: str, timeout: float = 20.0) -> httpx.Client:
    return httpx.Client(
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
        follow_redirects=True,
        timeout=timeout,
    )


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    text = str(value).strip()
    if text.isdigit():
        try:
            return datetime.fromtimestamp(int(text), tz=timezone.utc)
        except Exception:
            pass
    if not text:
        return None
    for parser in (parsedate_to_datetime, date_parser.parse):
        try:
            parsed = parser(text)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k.lower() not in TRACKING_PARAMS]
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = re.sub(r"/+$", "", parsed.path or "") or "/"
    return urlunparse((parsed.scheme or "https", netloc, path, "", urlencode(query), ""))


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return cleaned or "item"


def normalize_title(title: str) -> str:
    text = re.sub(r"\s+", " ", title or "").strip().lower()
    return re.sub(r"[^a-z0-9 ]+", "", text)


def fingerprint_for(canonical_url: str, title: str, published_at: datetime | None, entities: list[str]) -> str:
    bucket = published_at.strftime("%Y-%m-%d-%H") if published_at else "na"
    payload = "|".join([canonical_url, normalize_title(title), bucket, ",".join(sorted(set(entities))[:5])])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def entity_candidates(title: str, summary: str | None = None) -> list[str]:
    text = " ".join(part for part in [title, summary or ""] if part)
    matches = re.findall(r"\b(?:[A-Z][a-zA-Z0-9&.-]+(?:\s+[A-Z][a-zA-Z0-9&.-]+){0,3})\b", text)
    seen: list[str] = []
    for match in matches:
        if match not in seen and len(match) > 2:
            seen.append(match)
    return seen[:10]


def ticker_candidates(title: str, summary: str | None = None) -> list[str]:
    text = " ".join(part for part in [title, summary or ""] if part)
    tickers = []
    for candidate in re.findall(r"\b[A-Z]{2,5}\b", text):
        if candidate in TICKER_STOPWORDS:
            continue
        tickers.append(candidate)
    return list(dict.fromkeys(tickers))[:8]


def safe_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def sleep_if_needed(last_called_at: float | None, minimum_gap_seconds: float) -> float:
    now = time.time()
    if last_called_at is not None:
        delta = now - last_called_at
        if delta < minimum_gap_seconds:
            time.sleep(minimum_gap_seconds - delta)
    return time.time()
