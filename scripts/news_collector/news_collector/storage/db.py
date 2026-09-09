from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from news_collector.config import ensure_parent_dir


SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_type TEXT NOT NULL,
    category TEXT NOT NULL,
    external_id TEXT,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    published_at TEXT,
    author TEXT,
    summary TEXT,
    image_url TEXT,
    text TEXT,
    tags_json TEXT NOT NULL,
    symbols_json TEXT NOT NULL,
    entities_json TEXT NOT NULL,
    engagement_json TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS normalized_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_type TEXT NOT NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    published_at TEXT,
    author TEXT,
    image_url TEXT,
    text TEXT,
    summary TEXT,
    symbols_json TEXT NOT NULL,
    entities_json TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    engagement_json TEXT NOT NULL,
    importance_score REAL NOT NULL,
    fingerprint TEXT NOT NULL,
    cluster_id TEXT,
    raw_json TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_normalized_fingerprint ON normalized_items(fingerprint);

CREATE TABLE IF NOT EXISTS story_clusters (
    cluster_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    representative_source TEXT NOT NULL,
    published_at TEXT,
    image_url TEXT,
    score REAL NOT NULL,
    confirmation_count INTEGER NOT NULL,
    entities_json TEXT NOT NULL,
    symbols_json TEXT NOT NULL,
    item_ids_json TEXT NOT NULL,
    summary TEXT
);

CREATE TABLE IF NOT EXISTS digests (
    digest_date TEXT PRIMARY KEY,
    generated_at TEXT NOT NULL,
    markdown TEXT NOT NULL,
    json_payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_state (
    source TEXT PRIMARY KEY,
    state_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS media_cache (
    canonical_url TEXT PRIMARY KEY,
    image_url TEXT,
    checked_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS image_quality_cache (
    canonical_url TEXT PRIMARY KEY,
    result_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS content_cache (
    canonical_url TEXT PRIMARY KEY,
    content_text TEXT,
    status TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    error TEXT
);

CREATE TABLE IF NOT EXISTS run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    details TEXT
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        ensure_parent_dir(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)
            self._migrate(conn)

    @staticmethod
    def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return any(row["name"] == column for row in rows)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        for table in ("raw_items", "normalized_items", "story_clusters"):
            if not self._column_exists(conn, table, "image_url"):
                conn.execute(f"ALTER TABLE {table} ADD COLUMN image_url TEXT")
        if not self._column_exists(conn, "raw_items", "text"):
            conn.execute("ALTER TABLE raw_items ADD COLUMN text TEXT")
        if not self._column_exists(conn, "normalized_items", "text"):
            conn.execute("ALTER TABLE normalized_items ADD COLUMN text TEXT")
        content_cache = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='content_cache'"
        ).fetchone()
        if content_cache is None:
            conn.execute(
                """
                CREATE TABLE content_cache (
                    canonical_url TEXT PRIMARY KEY,
                    content_text TEXT,
                    status TEXT NOT NULL,
                    checked_at TEXT NOT NULL,
                    error TEXT
                )
                """
            )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def insert_json_row(self, table: str, values: dict[str, Any]) -> int:
        columns = ", ".join(values.keys())
        placeholders = ", ".join("?" for _ in values)
        with self.connect() as conn:
            cursor = conn.execute(
                f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
                tuple(values.values()),
            )
            return int(cursor.lastrowid)

    def upsert_cluster(self, values: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO story_clusters (
                    cluster_id, category, title, canonical_url, representative_source,
                    published_at, image_url, score, confirmation_count, entities_json, symbols_json,
                    item_ids_json, summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cluster_id) DO UPDATE SET
                    category=excluded.category,
                    title=excluded.title,
                    canonical_url=excluded.canonical_url,
                    representative_source=excluded.representative_source,
                    published_at=excluded.published_at,
                    image_url=excluded.image_url,
                    score=excluded.score,
                    confirmation_count=excluded.confirmation_count,
                    entities_json=excluded.entities_json,
                    symbols_json=excluded.symbols_json,
                    item_ids_json=excluded.item_ids_json,
                    summary=excluded.summary
                """,
                (
                    values["cluster_id"],
                    values["category"],
                    values["title"],
                    values["canonical_url"],
                    values["representative_source"],
                    values["published_at"],
                    values["image_url"],
                    values["score"],
                    values["confirmation_count"],
                    values["entities_json"],
                    values["symbols_json"],
                    values["item_ids_json"],
                    values["summary"],
                ),
            )

    def replace_digest(self, digest_date: str, generated_at: str, markdown: str, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO digests (digest_date, generated_at, markdown, json_payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(digest_date) DO UPDATE SET
                    generated_at=excluded.generated_at,
                    markdown=excluded.markdown,
                    json_payload=excluded.json_payload
                """,
                (digest_date, generated_at, markdown, json.dumps(payload)),
            )

    def get_content_cache(self, canonical_url: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT content_text, status, checked_at, error FROM content_cache WHERE canonical_url = ?",
                (canonical_url,),
            ).fetchone()

    def set_content_cache(
        self,
        canonical_url: str,
        content_text: str | None,
        status: str,
        checked_at: str,
        error: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO content_cache (canonical_url, content_text, status, checked_at, error)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(canonical_url) DO UPDATE SET
                    content_text=excluded.content_text,
                    status=excluded.status,
                    checked_at=excluded.checked_at,
                    error=excluded.error
                """,
                (canonical_url, content_text, status, checked_at, error),
            )

    def get_source_state(self, source: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT state_json FROM source_state WHERE source = ?", (source,)).fetchone()
            return json.loads(row["state_json"]) if row else {}

    def set_source_state(self, source: str, state: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO source_state (source, state_json)
                VALUES (?, ?)
                ON CONFLICT(source) DO UPDATE SET state_json=excluded.state_json
                """,
                (source, json.dumps(state)),
            )
