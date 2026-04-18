from __future__ import annotations

import json
from pathlib import Path

from news_collector.pipeline.digest import build_digest, render_markdown
from news_collector.runtime import build_runtime
from news_collector.models import StoryCluster


def main() -> None:
    settings, _config, repository, _collectors = build_runtime()
    rows = repository.fetch_clusters()
    clusters = [
        StoryCluster.model_validate(
            {
                "cluster_id": row["cluster_id"],
                "category": row["category"],
                "title": row["title"],
                "canonical_url": row["canonical_url"],
                "representative_source": row["representative_source"],
                "published_at": row["published_at"],
                "image_url": row["image_url"],
                "score": row["score"],
                "confirmation_count": row["confirmation_count"],
                "entities": json.loads(row["entities_json"]),
                "symbols": json.loads(row["symbols_json"]),
                "item_ids": json.loads(row["item_ids_json"]),
                "summary": row["summary"],
            }
        )
        for row in rows
    ]
    digest = build_digest(clusters)
    markdown = render_markdown(digest)
    output_dir = settings.output_dir / digest.digest_date
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "digest.md").write_text(markdown)
    (output_dir / "digest.json").write_text(json.dumps(digest.model_dump(mode="json"), indent=2))
    repository.store_digest(markdown, digest)
    print(json.dumps({"digest_date": digest.digest_date, "output_dir": str(output_dir)}, indent=2))


if __name__ == "__main__":
    main()
