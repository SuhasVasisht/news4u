from __future__ import annotations

import json

from news_collector.jobs import publish as publish_job


class FakeRepository:
    def __init__(self):
        self.state = {}
        self.calls = 0
        self.saved_states: list[tuple[str, dict]] = []

    def get_source_state(self, source: str):
        assert source == "publisher"
        return dict(self.state)

    def set_source_state(self, source: str, state: dict):
        assert source == "publisher"
        self.state = dict(state)
        self.saved_states.append((source, dict(state)))

    def fetch_raw_items(self, limit: int, min_id: int | None = None):
        self.calls += 1
        if self.calls == 1:
            return [{"id": 1}, {"id": 2}]
        if self.calls == 2:
            return [{"id": 3}]
        return []


class FakeSettings:
    app_sync_batch_size = 2


class FakeResult:
    def __init__(self, received: int, inserted: int, updated: int, outbox_dir: str, feed_dates: list[str], last_raw_item_id: int):
        self.received = received
        self.inserted = inserted
        self.updated = updated
        self.outbox_dir = outbox_dir
        self.feed_dates = feed_dates
        self.last_raw_item_id = last_raw_item_id


def test_publish_job_flushes_all_batches(monkeypatch, capsys):
    repository = FakeRepository()
    settings = FakeSettings()
    results = [
        FakeResult(2, 2, 0, "output/sync/batch-1", ["2026-04-17", "2026-04-18"], 2),
        FakeResult(1, 1, 0, "output/sync/batch-2", ["2026-04-18"], 3),
    ]

    monkeypatch.setattr(publish_job, "build_runtime", lambda: (settings, {}, repository, []))
    monkeypatch.setattr(publish_job, "publish_articles", lambda *args, **kwargs: results.pop(0))

    publish_job.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "published": 3,
        "inserted": 3,
        "updated": 0,
        "batches": 2,
        "outbox_dirs": ["output/sync/batch-1", "output/sync/batch-2"],
        "feed_dates": ["2026-04-17", "2026-04-18"],
        "last_raw_item_id": 3,
    }
    assert repository.state["last_published_raw_id"] == 3

