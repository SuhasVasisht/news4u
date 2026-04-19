from __future__ import annotations

import json

from news_collector.runtime import build_runtime
from news_collector.sync import publish_articles


def main() -> None:
    settings, _config, repository, _collectors = build_runtime()
    state = repository.get_source_state("publisher")
    last_published_raw_id = int(state.get("last_published_raw_id", 0))
    total_received = 0
    total_inserted = 0
    total_updated = 0
    batches = 0
    outbox_dirs: list[str] = []
    seen_feed_dates: set[str] = set()
    feed_dates: list[str] = []

    while True:
        rows = repository.fetch_raw_items(limit=settings.app_sync_batch_size, min_id=last_published_raw_id)
        if not rows:
            break

        result = publish_articles(
            repository,
            settings,
            rows,
            batch_label=f"incremental-{rows[0]['id']}-{rows[-1]['id']}",
        )
        last_published_raw_id = result.last_raw_item_id
        state["last_published_raw_id"] = result.last_raw_item_id
        repository.set_source_state("publisher", state)

        total_received += result.received
        total_inserted += result.inserted
        total_updated += result.updated
        batches += 1
        outbox_dirs.append(result.outbox_dir)
        for feed_date in result.feed_dates:
            if feed_date not in seen_feed_dates:
                seen_feed_dates.add(feed_date)
                feed_dates.append(feed_date)

    if batches == 0:
        print(json.dumps({"published": 0, "reason": "no new raw items"}, indent=2))
        return

    print(
        json.dumps(
            {
                "published": total_received,
                "inserted": total_inserted,
                "updated": total_updated,
                "batches": batches,
                "outbox_dirs": outbox_dirs,
                "feed_dates": feed_dates,
                "last_raw_item_id": last_published_raw_id,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
