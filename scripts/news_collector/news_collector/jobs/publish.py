from __future__ import annotations

import json

from news_collector.runtime import build_runtime
from news_collector.sync import publish_articles


def main() -> None:
    settings, _config, repository, _collectors = build_runtime()
    state = repository.get_source_state("publisher")
    last_published_raw_id = int(state.get("last_published_raw_id", 0))
    rows = repository.fetch_raw_items(limit=settings.app_sync_batch_size, min_id=last_published_raw_id)
    if not rows:
        print(json.dumps({"published": 0, "reason": "no new raw items"}, indent=2))
        return

    result = publish_articles(
        repository,
        settings,
        rows,
        batch_label=f"incremental-{rows[0]['id']}-{rows[-1]['id']}",
    )
    state["last_published_raw_id"] = result.last_raw_item_id
    repository.set_source_state("publisher", state)
    print(
        json.dumps(
            {
                "published": result.received,
                "inserted": result.inserted,
                "updated": result.updated,
                "outbox_dir": result.outbox_dir,
                "feed_dates": result.feed_dates,
                "last_raw_item_id": result.last_raw_item_id,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
