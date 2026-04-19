from __future__ import annotations

import json

from news_collector.runtime import build_runtime
from news_collector.sync import publish_articles


def main() -> None:
    settings, config, repository, _collectors = build_runtime()
    trust_scores = config.get("trust_scores", {})
    offset = 0
    total_received = 0
    total_inserted = 0
    total_updated = 0
    last_raw_item_id = 0
    while True:
        rows = repository.fetch_all_raw_items(limit=settings.replay_batch_size, offset=offset)
        if not rows:
            break
        result = publish_articles(
            repository,
            settings,
            rows,
            trust_scores=trust_scores,
            batch_label=f"replay-{rows[0]['id']}-{rows[-1]['id']}",
        )
        total_received += result.received
        total_inserted += result.inserted
        total_updated += result.updated
        last_raw_item_id = result.last_raw_item_id
        offset += len(rows)

    print(
        json.dumps(
            {
                "replayed": total_received,
                "inserted": total_inserted,
                "updated": total_updated,
                "last_raw_item_id": last_raw_item_id,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
