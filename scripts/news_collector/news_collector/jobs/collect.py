from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from news_collector.models import StoryCluster
from news_collector.pipeline.dedupe import cluster_items
from news_collector.pipeline.normalize import normalize_item
from news_collector.pipeline.images import prepare_images, refresh_recent_images
from news_collector.pipeline.score import cluster_score, compute_item_score
from news_collector.runtime import build_runtime


def main() -> None:
    settings, config, repository, collectors = build_runtime()
    force_run = os.environ.get("NEWS_COLLECTOR_FORCE_RUN") == "1"
    selected_sources = set(filter(None, os.environ.get("NEWS_COLLECTOR_SOURCES", "").split(",")))
    if selected_sources:
        collectors = [c for c in collectors if c.name in selected_sources]
    trust_scores = config["trust_scores"]
    inserted_rows: list[dict] = []
    errors: list[str] = []
    source_results: list[dict] = []
    for collector in collectors:
        result = collector.run(force=force_run, check_now=os.environ.get("NEWS_COLLECTOR_CHECK_NOW") == "1")
        raw_items = result.items
        image_quality = prepare_images(raw_items, repository, settings.user_agent)
        if result.status != "skipped":
            state = repository.get_source_state(collector.name)
            state["last_status"] = result.status
            state["last_reason"] = result.reason
            state["last_checked_at"] = datetime.now(timezone.utc).isoformat()
            state["last_collected"] = len(raw_items)
            repository.set_source_state(collector.name, state)
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
                "images": image_quality,
            }
        )
        if result.status == "error":
            errors.append(f"{collector.name}: {result.reason}")

    image_review = refresh_recent_images(repository, settings.user_agent)
    # Compare against earlier runs too, not only this run's new arrivals.
    clusters = cluster_items(repository.fetch_recent_items())
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
                "image_quality": image_review,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
