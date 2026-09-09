import pytest
from datetime import datetime, timedelta, timezone
from io import BytesIO
from PIL import Image
from news_collector.pipeline import images
from news_collector.pipeline.extract import extract_image_from_feed_entry, extract_image_from_page_html
from news_collector.models import RawItem
from news_collector.pipeline.normalize import normalize_item
from news_collector.storage.db import Database
from news_collector.storage.repository import Repository
from news_collector.pipeline.images import larger_image, public_url


def test_guardian_thumbnail_uses_large_source_transform():
    result = larger_image("https://i.guim.co.uk/img/media/photo.jpg?w=140&quality=45&fit=max")
    assert "w=1200" in result
    assert "quality=85" in result
    assert "fit=max" in result


def test_unknown_image_hosts_are_not_rewritten():
    url = "https://example.com/image.jpg?w=140"
    assert larger_image(url) == url
    assert larger_image(None) is None


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://127.0.0.1/photo", "http://[::1]/photo"])
def test_image_fetch_rejects_local_urls(url):
    with pytest.raises(ValueError):
        public_url(url)


def png(width, height):
    output = BytesIO()
    Image.new("RGB", (width, height)).save(output, format="PNG")
    return output.getvalue()


def test_publisher_original_replaces_feed_thumbnail(monkeypatch):
    responses = {
        "https://example.com/story": b'<meta property="og:image" content="/original.png">',
        "https://example.com/original.png": png(1200, 800),
        "https://example.com/thumb.png": png(140, 90),
    }
    monkeypatch.setattr(images, "download", lambda client, url, limit: (responses[url], url))
    result = images.resolve_quality_image(None, "https://example.com/story", ["https://example.com/thumb.png"])
    assert result["image"] == "https://example.com/original.png"
    assert (result["width"], result["height"]) == (1200, 800)


def test_failed_page_uses_valid_feed_image_and_rejects_tiny_images(monkeypatch):
    def download(client, url, limit):
        if url.endswith("/story"):
            raise TimeoutError()
        return png(140, 90) if "tiny" in url else png(800, 600), url
    monkeypatch.setattr(images, "download", download)
    assert images.resolve_quality_image(None, "https://example.com/story", ["https://example.com/tiny"])["image"] is None
    assert images.resolve_quality_image(None, "https://example.com/story", ["https://example.com/large"])["width"] == 800


def test_cache_retries_failures_and_expires_successes(tmp_path, monkeypatch):
    repository = Repository(Database(tmp_path / "news.db"))
    calls = []
    def resolve(*args):
        calls.append(1)
        return {"image": None, "width": 0, "height": 0, "status": "unavailable"}
    monkeypatch.setattr(images, "resolve_quality_image", resolve)
    url = "https://example.com/story"
    result = images.quality_image(repository, url, [], "test")
    images.quality_image(repository, url, [], "test")
    assert len(calls) == 1
    result["checked_at"] = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
    repository.set_image_quality(url, result)
    images.quality_image(repository, url, [], "test")
    assert len(calls) == 2
    result.update(image="https://example.com/large.png", status="verified",
                  checked_at=(datetime.now(timezone.utc) - timedelta(days=8)).isoformat())
    repository.set_image_quality(url, result)
    images.quality_image(repository, url, [], "test")
    assert len(calls) == 3


def test_collection_gate_updates_duplicates_and_can_clear_bad_images(tmp_path, monkeypatch):
    repository = Repository(Database(tmp_path / "news.db"))
    item = RawItem(source="rss", source_type="rss", category="tech", title="Story",
                   url="https://example.com/story", image_url="https://example.com/tiny.png",
                   published_at=datetime.now(timezone.utc))
    repository.insert_raw_item(item)
    repository.insert_normalized_item(normalize_item(item))
    result = {"image": "https://example.com/large.png", "width": 1200, "height": 800, "status": "verified"}
    monkeypatch.setattr(images, "resolve_quality_image", lambda *args: result.copy())
    assert images.prepare_images([item], repository, "test")["verified"] == 1
    assert repository.insert_normalized_item(normalize_item(item)) is None
    assert repository.fetch_recent_items()[0]["image_url"] == result["image"]
    assert repository.fetch_raw_items(1)[0]["image_url"] == result["image"]
    images.prepare_images([item], repository, "test")
    assert item.image_url == result["image"]
    result.update(image=None, width=0, height=0, status="unavailable",
                  checked_at=datetime.now(timezone.utc).isoformat())
    repository.set_image_quality(item.url, result)
    images.refresh_recent_images(repository, "test")
    assert repository.fetch_recent_items()[0]["image_url"] is None
    assert repository.fetch_raw_items(1)[0]["image_url"] is None


def test_feed_selects_largest_media_not_thumbnail():
    entry = {"media_thumbnail": [{"url": "tiny.jpg", "width": "140"}],
             "media_content": [{"url": "small.jpg", "width": "300"}, {"url": "large.jpg", "width": "1200"}]}
    assert extract_image_from_feed_entry(entry) == "large.jpg"


def test_json_ld_does_not_mistake_article_or_publisher_url_for_image():
    html = '<script type="application/ld+json">{"@type":"NewsArticle","url":"https://example.com/story","publisher":{"logo":{"url":"https://example.com/logo.png"}}}</script>'
    assert extract_image_from_page_html(html, "https://example.com/story") is None
    html = '<script type="application/ld+json">{"@type":"NewsArticle","image":{"url":"/photo.jpg"}}</script>'
    assert extract_image_from_page_html(html, "https://example.com/story") == "https://example.com/photo.jpg"


def test_export_requires_verified_database_images(tmp_path):
    from news_collector.jobs.export_edition import verify_snapshot_images
    repository = Repository(Database(tmp_path / "news.db"))
    url = "https://example.com/story"
    snapshot = {"stories": [{"id": "one", "url": url, "image": "https://example.com/photo.png"}]}
    with pytest.raises(RuntimeError, match="Unverified"):
        verify_snapshot_images(snapshot, repository)
    repository.set_image_quality(url, {"image": snapshot["stories"][0]["image"], "width": 1200, "height": 800})
    assert verify_snapshot_images(snapshot, repository)["verified"] == 1
    snapshot["stories"][0]["image"] = "https://example.com/tiny.png"
    with pytest.raises(RuntimeError, match="Unverified"):
        verify_snapshot_images(snapshot, repository)


def test_retry_keeps_original_feed_candidate_after_image_is_omitted(tmp_path, monkeypatch):
    repository = Repository(Database(tmp_path / "news.db"))
    url = "https://example.com/story"
    original = "https://example.com/feed-photo.png"
    repository.set_image_quality(url, {"image": None, "status": "unavailable",
        "width": 0, "height": 0, "candidates": [original],
        "checked_at": (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()})
    seen = []
    def resolve(client, page_url, candidates):
        seen.extend(candidates)
        return {"image": original, "width": 1200, "height": 800, "status": "verified"}
    monkeypatch.setattr(images, "resolve_quality_image", resolve)
    assert images.quality_image(repository, url, [None], "test")["image"] == original
    assert seen == [original]
