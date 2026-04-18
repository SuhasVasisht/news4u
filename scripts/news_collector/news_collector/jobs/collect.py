from __future__ import annotations

import json
from datetime import datetime, timezone

from news_collector.models import StoryCluster
from news_collector.pipeline.dedupe import cluster_items
from news_collector.pipeline.normalize import normalize_item
from news_collector.pipeline.score import cluster_score, compute_item_score
from news_collector.runtime import build_runtime


def main() -> None:
    settings, config, repository, collectors = build_runtime()
    trust_scores = config["trust_scores"]
    inserted_rows: list[dict] = []
    errors: list[str] = []
    source_results: list[dict] = []
    for collector in collectors:
        result = collector.run()
        raw_items = result.items
        inserted_count = 0
        deduped_count = 0
        for raw_item in raw_items:
            repository.insert_raw_item(raw_item)
            normalized = normalize_item(raw_item)
            normalized.importance_score = compute_item_score(
                normalized,
                trust_scores.get(normalized.source, 0.5),
                market_impact_score=1.0 if normalized.symbols else 0.0,
            )
            item_id = repository.insert_normalized_item(normalized)
            if item_id is None:
                deduped_count += 1
                continue
            inserted_count += 1
            inserted_rows.append(
                {
                    "id": item_id,
                    "source": normalized.source,
                    "category": normalized.category,
                    "title": normalized.title,
                    "canonical_url": normalized.canonical_url,
                    "importance_score": normalized.importance_score,
                    "summary": normalized.summary,
                    "image_url": normalized.image_url,
                    "published_at": normalized.published_at.isoformat() if normalized.published_at else None,
                    "entities_json": json.dumps(normalized.entities),
                    "symbols_json": json.dumps(normalized.symbols),
                }
            )
        source_results.append(
            {
                "collector": collector.name,
                "status": result.status,
                "reason": result.reason,
                "collected": len(raw_items),
                "inserted": inserted_count,
                "deduped": deduped_count,
            }
        )
        if result.status == "error":
            errors.append(f"{collector.name}: {result.reason}")

    clusters = cluster_items(inserted_rows or repository.fetch_recent_items())
    for cluster in clusters:
        cluster.score = cluster_score(cluster, trust_scores.get(cluster.representative_source, 0.5))
        repository.upsert_cluster(cluster)
        for item_id in cluster.item_ids:
            repository.update_item_cluster(item_id, cluster.cluster_id, cluster.score)

    print(
        json.dumps(
            {
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "collectors": len(collectors),
                "new_items": len(inserted_rows),
                "clusters": len(clusters),
                "sources": source_results,
                "errors": errors,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
