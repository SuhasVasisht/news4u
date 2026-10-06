from __future__ import annotations

import json
from typing import Iterable
from urllib.parse import urlparse

from rapidfuzz import fuzz

from news_collector.models import StoryCluster
from news_collector.utils import parse_datetime
from news_collector.utils import normalize_title, slugify


def _is_homepage_url(url: str) -> bool:
    return urlparse(url).path in {"", "/"}


def cluster_items(rows: Iterable[dict]) -> list[StoryCluster]:
    groups: list[list[dict]] = []
    # Parse each row once. Date/JSON/title parsing inside the pairwise loop made
    # a normal daily collection spend minutes of CPU on unchanged inputs.
    rows = list(rows)
    metadata = {id(row): (normalize_title(row["title"]),
                         set(json.loads(row["entities_json"])),
                         set(json.loads(row["symbols_json"])),
                         parse_datetime(row.get("published_at")),
                         _is_homepage_url(row["canonical_url"])) for row in rows}
    for row in rows:
        placed = False
        row_title, row_entities, row_symbols, row_date, row_homepage = metadata[id(row)]
        for group in groups:
            candidate = group[0]
            candidate_title, candidate_entities, candidate_symbols, candidate_date, _ = metadata[id(candidate)]
            score = fuzz.ratio(row_title, candidate_title)
            homepage_overlap = bool((row_entities & candidate_entities) or (row_symbols & candidate_symbols))
            if row["canonical_url"] == candidate["canonical_url"] and (
                not row_homepage or (score >= 85 and homepage_overlap)
            ):
                group.append(row)
                placed = True
                break
            if (
                row_homepage
                and row["canonical_url"] == candidate["canonical_url"]
                and not homepage_overlap
            ):
                continue
            if row_date and candidate_date and abs((row_date - candidate_date).total_seconds()) > 72 * 3600:
                continue
            if score >= 92 or (score >= 85 and row_entities and candidate_entities and row_entities & candidate_entities):
                group.append(row)
                placed = True
                break
        if not placed:
            groups.append([row])

    clusters: list[StoryCluster] = []
    for group in groups:
        representative = max(group, key=lambda item: item["importance_score"])
        entities = list(dict.fromkeys(e for row in group for e in json.loads(row["entities_json"])))
        symbols = list(dict.fromkeys(s for row in group for s in json.loads(row["symbols_json"])))
        cluster_id = slugify(f"{representative['title']}-{representative['canonical_url'][-16:]}")
        clusters.append(
            StoryCluster(
                cluster_id=cluster_id,
                category=representative["category"],
                title=representative["title"],
                canonical_url=representative["canonical_url"],
                representative_source=representative["source"],
                published_at=parse_datetime(representative.get("published_at")),
                image_url=representative.get("image_url"),
                confirmation_count=len({(urlparse(row["canonical_url"]).hostname or "").removeprefix("www.") for row in group}),
                entities=entities[:10],
                symbols=symbols[:10],
                item_ids=[row["id"] for row in group],
                summary=representative["summary"],
            )
        )
    return clusters


def rising_story_candidates(clusters: list[StoryCluster]) -> list[StoryCluster]:
    ordered = sorted(clusters, key=lambda cluster: (cluster.confirmation_count, cluster.score), reverse=True)
    return ordered[:10]


def big_swings(clusters: list[StoryCluster]) -> list[dict]:
    swings = []
    for cluster in clusters:
        if (
            cluster.category == "finance"
            and cluster.symbols
            and cluster.representative_source in {"alphavantage_movers", "alphavantage_news", "sec_press"}
        ):
            swings.append(
                {
                    "symbol": cluster.symbols[0],
                    "title": cluster.title,
                    "score": cluster.score,
                    "url": cluster.canonical_url,
                }
            )
    return swings[:10]
