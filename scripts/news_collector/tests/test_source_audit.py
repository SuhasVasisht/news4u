from datetime import datetime, timezone
from news_collector.pipeline.source_audit import audit_sources


def test_audit_distinguishes_discovery_review_publication_and_disabled_sources():
    now = datetime(2026, 9, 9, 12, tzinfo=timezone.utc)
    class Repository:
        def get_source_state(self, name):
            return {"last_checked_at": now.isoformat(), "last_status": "ok"}
    rows = [{"source": "tldr_tech", "canonical_url": "https://example.com/story",
             "published_at": now.isoformat(), "raw_json": "{}", "title": "A useful report"}]
    review = {"packets": [{"id": "one", "source": "hackernews", "url": rows[0]["canonical_url"]},
                           {"id": "two", "source": "tldr_tech", "url": "https://example.com/unread"}],
              "decisions": {"one": {"decision": "admit", "quality": 90},
                            "two": {"decision": "hold", "quality": 0}}}
    snapshot = {"stories": [{"title": "A useful report", "collectors": ["hackernews", "tldr_tech"]}]}
    config = {"collectors": [{"name": "tldr_tech"}, {"name": "x_search", "enabled": False}]}
    collection = {"collected_at": now.isoformat(), "sources": [{"collector": "tldr_tech", "collected": 13}]}
    result = audit_sources(config, Repository(), rows, review, snapshot, now, collection)
    assert result[0]["collected"] == 13
    assert result[0]["candidates"] == 2
    assert result[0]["reviewed"] == 1
    assert result[0]["published"] == 1
    assert result[1]["status"] == "disabled"


def test_old_success_is_not_reported_as_a_fresh_check():
    class Repository:
        def get_source_state(self, name):
            return {"last_checked_at": "2026-09-01T00:00:00+00:00", "last_status": "ok"}
    result = audit_sources({"collectors": [{"name": "bbc_world"}]}, Repository(), [], {}, {},
                           datetime(2026, 9, 9, tzinfo=timezone.utc))
    assert result[0]["status"] == "unverified"
