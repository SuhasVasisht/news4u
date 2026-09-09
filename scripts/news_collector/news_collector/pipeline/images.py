"""Source-image quality gate shared by collection and publishing."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import ipaddress
from datetime import datetime, timedelta, timezone
import socket
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

import httpx
from PIL import Image
from news_collector.pipeline.extract import extract_image_from_page_html


def public_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username:
        raise ValueError("Public HTTP URL required")
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError("Non-public address")
    return url


def download(client, url, limit):
    for _ in range(5):
        with client.stream("GET", public_url(url)) as response:
            if response.is_redirect:
                url = str(response.url.join(response.headers["location"]))
                continue
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > limit:
                    raise ValueError("Response too large")
            return bytes(body), str(response.url)
    raise ValueError("Too many redirects")


def larger_image(url):
    if not url:
        return None
    parts = urlparse(url)
    if parts.hostname == "i.guim.co.uk":
        query = dict(parse_qsl(parts.query))
        # The Guardian image CDN supports width and quality transforms.
        query.update(w="1200", quality="85")
        return urlunparse(parts._replace(query=urlencode(query)))
    return url


def resolve_quality_image(client, page_url, candidates):
    choices = []
    try:
        html, final_url = download(client, page_url, 3_000_000)
        choices.append(extract_image_from_page_html(html.decode("utf-8", errors="replace"), final_url))
    except Exception:
        pass
    choices.extend(larger_image(url) for url in candidates)
    best = {"image": None, "width": 0, "height": 0, "status": "unavailable"}
    for candidate in dict.fromkeys(choices):
        if not candidate:
            continue
        try:
            data, final_url = download(client, candidate, 12_000_000)
            with Image.open(BytesIO(data)) as image:
                width, height = image.size
                image.verify()
            if width >= 400 and height >= 200 and width > best["width"]:
                best = {"image": final_url, "width": width, "height": height, "status": "verified"}
            if width >= 1000 and height >= 500:
                break
        except Exception:
            continue
    return best


def quality_image(repository, page_url, candidates, user_agent):
    from news_collector.utils import canonicalize_url
    key = canonicalize_url(page_url)
    cached = repository.get_image_quality(key)
    candidates = list(dict.fromkeys([url for url in [*candidates, *(cached or {}).get("candidates", [])] if url]))
    now = datetime.now(timezone.utc)
    # Recheck successful images weekly; transient failures retry after six hours.
    if cached:
        age = now - datetime.fromisoformat(cached["checked_at"])
        ttl = timedelta(days=7) if cached["image"] else timedelta(hours=6)
        if timedelta(0) <= age < ttl:
            return cached
    with httpx.Client(timeout=12, follow_redirects=False, headers={"User-Agent": user_agent}) as client:
        result = resolve_quality_image(client, page_url, candidates)
    result["checked_at"] = now.isoformat()
    result["candidates"] = candidates
    repository.set_image_quality(key, result)
    return result


def prepare_images(items, repository, user_agent):
    """Validate before raw storage and normalization, including cache-returned items."""
    def prepare(item):
        result = quality_image(repository, item.url, [item.image_url], user_agent)
        item.image_url = result["image"]
        repository.replace_article_image(item.url, result["image"])
        return result["status"]

    with ThreadPoolExecutor(max_workers=6) as pool:
        statuses = list(pool.map(prepare, items))
    return {"checked": len(statuses), "verified": statuses.count("verified"),
            "omitted": statuses.count("unavailable")}


def refresh_recent_images(repository, user_agent):
    """Keep existing and deduplicated rows under the same policy on every run."""
    rows = repository.fetch_recent_items(limit_hours=168)
    unique = {row["canonical_url"]: row for row in rows}
    def refresh(row):
        result = quality_image(repository, row["canonical_url"], [row["image_url"]], user_agent)
        repository.replace_article_image(row["url"], result["image"])
        return result["status"]
    with ThreadPoolExecutor(max_workers=6) as pool:
        statuses = list(pool.map(refresh, unique.values()))
    return {"checked": len(statuses), "verified": statuses.count("verified"),
            "omitted": statuses.count("unavailable")}
