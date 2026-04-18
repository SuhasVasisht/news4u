from __future__ import annotations

from datetime import datetime, timezone

from news_collector.models import DigestDocument, StoryCluster
from news_collector.pipeline.dedupe import big_swings, rising_story_candidates


def select_diverse(clusters: list[StoryCluster], limit: int, max_per_source: int = 2) -> list[StoryCluster]:
    chosen: list[StoryCluster] = []
    per_source: dict[str, int] = {}
    for cluster in clusters:
        count = per_source.get(cluster.representative_source, 0)
        if count >= max_per_source:
            continue
        chosen.append(cluster)
        per_source[cluster.representative_source] = count + 1
        if len(chosen) >= limit:
            break
    return chosen


def build_digest(clusters: list[StoryCluster], digest_date: str | None = None) -> DigestDocument:
    digest_date = digest_date or datetime.now(timezone.utc).date().isoformat()
    tech = select_diverse([cluster for cluster in clusters if cluster.category == "tech"], limit=10)
    world_politics = select_diverse([cluster for cluster in clusters if cluster.category in {"world", "politics"}], limit=10)
    finance = select_diverse([cluster for cluster in clusters if cluster.category == "finance"], limit=10)
    return DigestDocument(
        digest_date=digest_date,
        generated_at=datetime.now(timezone.utc),
        top_tech=tech,
        top_world_politics=world_politics,
        top_finance=finance,
        rising_stories=rising_story_candidates(clusters),
        big_swings=big_swings(clusters),
    )


def render_markdown(digest: DigestDocument) -> str:
    def render_section(title: str, clusters: list[StoryCluster]) -> list[str]:
        lines = [f"## {title}", ""]
        if not clusters:
            lines.append("- No stories collected.")
        for cluster in clusters:
            lines.append(
                f"- [{cluster.title}]({cluster.canonical_url}) | source: `{cluster.representative_source}` | "
                f"score: `{cluster.score}` | confirmations: `{cluster.confirmation_count}`"
            )
        lines.append("")
        return lines

    lines = [f"# Daily Digest - {digest.digest_date}", ""]
    lines.extend(render_section("Top Tech", digest.top_tech))
    lines.extend(render_section("Top World / Politics", digest.top_world_politics))
    lines.extend(render_section("Top Finance", digest.top_finance))
    lines.extend(render_section("Rising Stories", digest.rising_stories))
    lines.append("## Big Swings")
    lines.append("")
    if not digest.big_swings:
        lines.append("- No big swings detected.")
    for swing in digest.big_swings:
        lines.append(f"- `{swing['symbol']}`: [{swing['title']}]({swing['url']}) | score: `{swing['score']}`")
    lines.append("")
    return "\n".join(lines)
