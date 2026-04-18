from __future__ import annotations

from news_collector.collectors.base import BaseCollector, CollectorDegraded
from news_collector.models import RawItem
from news_collector.utils import entity_candidates, parse_datetime, ticker_candidates


PRODUCTHUNT_QUERY = """
query LatestPosts($first: Int!) {
  posts(first: $first) {
    edges {
      node {
        id
        name
        tagline
        url
        website
        votesCount
        createdAt
        thumbnail {
          url
        }
        topics {
          edges {
            node {
              name
            }
          }
        }
      }
    }
  }
}
"""


class ProductHuntCollector(BaseCollector):
    source_type = "api"

    def collect(self) -> list[RawItem]:
        token = self.context.settings.producthunt_token
        if not token:
            raise CollectorDegraded("missing Product Hunt API token")

        response = self.client.post(
            "https://api.producthunt.com/v2/api/graphql",
            json={
                "query": PRODUCTHUNT_QUERY,
                "variables": {"first": int(self.context.config.get("limit", 20))},
            },
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            raise CollectorDegraded(str(payload["errors"][0].get("message", "Product Hunt API error")))

        items: list[RawItem] = []
        for edge in payload.get("data", {}).get("posts", {}).get("edges", []):
            post = edge.get("node") or {}
            title = post.get("name", "").strip()
            summary = post.get("tagline")
            post_url = post.get("url", "")
            topics = [
                topic_edge.get("node", {}).get("name")
                for topic_edge in post.get("topics", {}).get("edges", [])
                if topic_edge.get("node", {}).get("name")
            ]
            items.append(
                RawItem(
                    source=self.name,
                    source_type="api",
                    category=self.category,
                    external_id=post.get("id"),
                    title=title,
                    url=post_url,
                    published_at=parse_datetime(post.get("createdAt")),
                    author="Product Hunt",
                    summary=summary,
                    text=self.resolve_text(post_url, summary),
                    image_url=self.resolve_image(
                        post_url,
                        (post.get("thumbnail") or {}).get("url"),
                    ),
                    tags=topics,
                    symbols=ticker_candidates(title, summary),
                    entities=entity_candidates(title, summary),
                    engagement={"votes": int(post.get("votesCount", 0) or 0), "website": post.get("website")},
                    raw=post,
                )
            )
        return items
