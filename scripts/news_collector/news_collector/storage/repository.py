from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from news_collector.models import DigestDocument, NewsItem, RawItem, StoryCluster
from news_collector.storage.db import Database


def _as_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class Repository:
    def __init__(self, db: Database):
        self.db = db

    def insert_raw_item(self, item: RawItem) -> int:
        return self.db.insert_json_row(
            "raw_items",
            {
                "source": item.source,
                "source_type": item.source_type,
                "category": item.category,
                "external_id": item.external_id,
                "title": item.title,
                "url": item.url,
                "published_at": _as_iso(item.published_at),
                "author": item.author,
                "summary": item.summary,
                "image_url": item.image_url,
                "text": item.text,
                "tags_json": json.dumps(item.tags),
                "symbols_json": json.dumps(item.symbols),
                "entities_json": json.dumps(item.entities),
                "engagement_json": json.dumps(item.engagement),
                "raw_json": json.dumps(item.raw),
                "fetched_at": item.fetched_at.isoformat(),
            },
        )

    def insert_normalized_item(self, item: NewsItem) -> int | None:
        try:
            return self.db.insert_json_row(
                "normalized_items",
                {
                    "source": item.source,
                    "source_type": item.source_type,
                    "category": item.category,
                    "title": item.title,
                    "url": item.url,
                    "canonical_url": item.canonical_url,
                    "published_at": _as_iso(item.published_at),
                    "author": item.author,
                    "image_url": item.image_url,
                    "text": item.text,
                    "summary": item.summary,
                    "symbols_json": json.dumps(item.symbols),
                    "entities_json": json.dumps(item.entities),
                    "tags_json": json.dumps(item.tags),
                    "engagement_json": json.dumps(item.engagement),
                    "importance_score": item.importance_score,
                    "fingerprint": item.fingerprint,
                    "cluster_id": item.cluster_id,
                    "raw_json": json.dumps(item.raw),
                },
            )
        except sqlite3.IntegrityError:
            with self.db.connect() as conn:
                conn.execute("UPDATE normalized_items SET text = ?, summary = ?, raw_json = ? WHERE fingerprint = ?",
                             (item.text, item.summary, json.dumps(item.raw), item.fingerprint))
            return None

    def update_item_cluster(self, item_id: int, cluster_id: str, score: float) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE normalized_items SET cluster_id = ?, importance_score = ? WHERE id = ?",
                (cluster_id, score, item_id),
            )

    def upsert_cluster(self, cluster: StoryCluster) -> None:
        self.db.upsert_cluster(
            {
                "cluster_id": cluster.cluster_id,
                "category": cluster.category,
                "title": cluster.title,
                "canonical_url": cluster.canonical_url,
                "representative_source": cluster.representative_source,
                "published_at": _as_iso(cluster.published_at),
                "image_url": cluster.image_url,
                "score": cluster.score,
                "confirmation_count": cluster.confirmation_count,
                "entities_json": json.dumps(cluster.entities),
                "symbols_json": json.dumps(cluster.symbols),
                "item_ids_json": json.dumps(cluster.item_ids),
                "summary": cluster.summary,
            }
        )

    def store_digest(self, markdown: str, digest: DigestDocument) -> None:
        self.db.replace_digest(
            digest.digest_date,
            digest.generated_at.isoformat(),
            markdown,
            digest.model_dump(mode="json"),
        )

    def get_source_state(self, source: str) -> dict[str, Any]:
        return self.db.get_source_state(source)

    def set_source_state(self, source: str, state: dict[str, Any]) -> None:
        self.db.set_source_state(source, state)

    def fetch_recent_items(self, limit_hours: int = 48) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM normalized_items
                WHERE julianday(published_at) >= julianday('now', ?)
                  AND julianday(published_at) <= julianday('now', '+5 minutes')
                ORDER BY julianday(published_at) DESC, id DESC
                """,
                (f"-{limit_hours} hours",),
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_clusters(self) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM story_clusters ORDER BY score DESC, published_at DESC").fetchall()
        return [dict(row) for row in rows]

    def source_counts(self, table: str) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(f"SELECT source, COUNT(*) AS count FROM {table} GROUP BY source ORDER BY count DESC").fetchall()
        return [dict(row) for row in rows]

    def get_cached_image(self, canonical_url: str) -> str | None | bool:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT image_url FROM media_cache WHERE canonical_url = ?",
                (canonical_url,),
            ).fetchone()
        if row is None:
            return False
        return row["image_url"]

    def get_image_quality(self, canonical_url: str) -> dict | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT result_json FROM image_quality_cache WHERE canonical_url = ?", (canonical_url,)).fetchone()
        return json.loads(row["result_json"]) if row else None

    def source_discoveries(self) -> list[dict]:
        from news_collector.utils import canonicalize_url
        with self.db.connect() as conn:
            rows = conn.execute("SELECT source, url, title, published_at, raw_json FROM raw_items ORDER BY id DESC").fetchall()
        unique = {}
        for row in rows:
            canonical = canonicalize_url(row["url"])
            unique.setdefault((row["source"], canonical), {**dict(row), "canonical_url": canonical})
        return list(unique.values())

    def set_image_quality(self, canonical_url: str, result: dict) -> None:
        with self.db.connect() as conn:
            conn.execute("INSERT INTO image_quality_cache VALUES (?, ?) ON CONFLICT(canonical_url) DO UPDATE SET result_json=excluded.result_json", (canonical_url, json.dumps(result)))

    def replace_article_image(self, url: str, image_url: str | None) -> None:
        from news_collector.utils import canonicalize_url
        canonical = canonicalize_url(url)
        with self.db.connect() as conn:
            conn.execute("UPDATE raw_items SET image_url = ? WHERE url = ? OR url = ?", (image_url, url, canonical))
            conn.execute("UPDATE normalized_items SET image_url = ? WHERE canonical_url = ?", (image_url, canonical))
            conn.execute("UPDATE story_clusters SET image_url = ? WHERE canonical_url = ?", (image_url, canonical))

    def set_cached_image(self, canonical_url: str, image_url: str | None, checked_at: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO media_cache (canonical_url, image_url, checked_at)
                VALUES (?, ?, ?)
                ON CONFLICT(canonical_url) DO UPDATE SET
                    image_url=excluded.image_url,
                    checked_at=excluded.checked_at
                """,
                (canonical_url, image_url, checked_at),
            )

    def get_cached_content(self, canonical_url: str) -> dict[str, Any] | bool:
        row = self.db.get_content_cache(canonical_url)
        if row is None:
            return False
        return dict(row)

    def set_cached_content(
        self,
        canonical_url: str,
        content_text: str | None,
        checked_at: str,
        status: str = "ok",
        error: str | None = None,
    ) -> None:
        self.db.set_content_cache(canonical_url, content_text, status, checked_at, error)

    def update_raw_item_content(self, raw_item_id: int, text: str | None, image_url: str | None) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE raw_items SET text = COALESCE(?, text), image_url = COALESCE(?, image_url) WHERE id = ?",
                (text, image_url, raw_item_id),
            )

    def update_normalized_item_content(
        self,
        canonical_url: str,
        text: str | None,
        image_url: str | None,
    ) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE normalized_items
                SET text = COALESCE(?, text),
                    image_url = COALESCE(?, image_url)
                WHERE canonical_url = ?
                """,
                (text, image_url, canonical_url),
            )

    def fetch_raw_items(
        self,
        limit: int,
        min_id: int | None = None,
    ) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if min_id is not None:
            clauses.append("id > ?")
            params.append(min_id)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM raw_items
                {where_sql}
                ORDER BY id ASC
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_recent_raw_items_by_source(
        self,
        source: str,
        limit: int = 25,
        limit_hours: int = 168,
    ) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM raw_items
                WHERE source = ?
                  AND (published_at IS NULL OR published_at >= datetime('now', ?))
                ORDER BY COALESCE(published_at, fetched_at) DESC, id DESC
                LIMIT ?
                """,
                (source, f"-{limit_hours} hours", limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_all_raw_items(self, limit: int, offset: int = 0) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM raw_items
                ORDER BY id ASC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [dict(row) for row in rows]
