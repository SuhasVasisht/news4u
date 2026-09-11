import pytest
import json
from datetime import datetime, timedelta, timezone

from news_collector.pipeline.publication_dates import article_publication_date
from news_collector.pipeline import editorial
from news_collector.jobs.export_edition import assemble_reviewed
from test_editorial import row, packet, decision


@pytest.mark.parametrize("html", [
    '<meta property="article:published_time" content="2026-09-09T12:00:00Z">',
    '<time itemprop="datePublished" datetime="2026-09-09T12:00:00Z"></time>',
    '<script type="application/ld+json">{"@type":"BlogPosting","datePublished":"2026-09-09T12:00:00Z"}</script>',
    '<script type="application/ld+json">{"@graph":[{"@type":["Article"],"datePublished":"2026-09-09T12:00:00Z"}]}</script>',
])
def test_extracts_original_publisher_date(html):
    assert article_publication_date(html).isoformat() == "2026-09-09T12:00:00+00:00"


@pytest.mark.parametrize("html", [
    '<meta property="article:modified_time" content="2026-09-10T12:00:00Z">',
    '<script type="application/ld+json">{"@type":"WebSite","datePublished":"2026-09-09"}</script>',
    '<script type="application/ld+json">invalid</script><p>Newsletter sent September 10</p>',
])
def test_does_not_substitute_modified_or_discovery_dates(html):
    assert article_publication_date(html) is None


def test_newsletter_packet_uses_publisher_date_and_preserves_source_hash(monkeypatch):
    now = datetime.now(timezone.utc)
    original = (now - timedelta(hours=24)).isoformat()
    source = row(source="tldr_email", published_at=now.isoformat(), text="Evidence " * 500,
                 raw_json=json.dumps({"_date_basis": "newsletter_sent_at"}))
    monkeypatch.setattr(editorial, "download", lambda *_: (
        f'<meta property="article:published_time" content="{original}">'.encode(), source["url"]))
    result = editorial.content_packet(source, None, "Test")
    assert result["publishedAt"] == original
    assert result["publicationDateBasis"] == "publisher_metadata"
    assert result["inputHash"] == editorial.source_hash(source)
    monkeypatch.setattr(editorial, "download", lambda *_: (b"<p>No publication metadata</p>", source["url"]))
    with pytest.raises(ValueError, match="verified publisher publication date"):
        editorial.content_packet(source, None, "Test")


def test_export_uses_reviewed_original_date_and_rejects_unverified_newsletter_date():
    now = datetime.now(timezone.utc)
    original = (now - timedelta(hours=24)).isoformat()
    source = row(source="tldr_email", published_at=now.isoformat(),
                 raw_json=json.dumps({"_date_basis": "newsletter_sent_at"}))
    evidence = {**packet(), "publishedAt": original, "publicationDateBasis": "publisher_metadata"}
    review = {"generatedAt": now.isoformat(), "packets": [evidence],
              "decisions": {"one": decision().model_dump()}, "selection": {"selected_ids": ["one"]},
              "excluded": [], "policy": "test"}
    snapshot, _ = assemble_reviewed([source], review, now, "America/Los_Angeles")
    assert snapshot["stories"][0]["publishedAt"] == original
    del evidence["publicationDateBasis"]
    with pytest.raises(RuntimeError, match="publisher date verification"):
        assemble_reviewed([source], review, now, "America/Los_Angeles")
