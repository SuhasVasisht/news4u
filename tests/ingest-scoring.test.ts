import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/auth", () => ({
  auth: async () => null,
}));

import { collectorImportanceToArticleScore } from "@/lib/scoring";
import { getTodayFeed, syncArticles } from "@/lib/services/news-service";

describe("article ingest scoring", () => {
  beforeEach(() => {
    (globalThis as { __memoryNewsStore__?: unknown }).__memoryNewsStore__ = undefined;
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-04-17T18:00:00.000Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("recomputes collector-backed scores from payload metadata instead of trusting the incoming score", async () => {
    const expectedScore = collectorImportanceToArticleScore({
      publishedAt: "2026-04-17T17:00:00.000Z",
      trustScore: 0.86,
      engagement: { clicks: 1250 },
      symbols: ["NVDA"],
      now: new Date(),
    });

    await syncArticles([
      {
        external_id: "collector-score-1",
        title: "Collector score recompute story",
        summary: "The app should ignore the top-level synced score for collector-backed items.",
        author: "Desk",
        url: "https://example.com/collector-score-recompute-story",
        image_url: "https://images.example.com/collector-score.jpg",
        published_at: "2026-04-17T17:00:00.000Z",
        content_text:
          "Full body text for the collector-backed scoring test with enough detail to satisfy the current feed eligibility rules. It adds context, supporting facts, and extra explanation so the story remains visible in the generated feed.",
        score: 999,
        payload_json: {
          collector: {
            source_type: "rss",
            category: "tech",
            trust_score: 0.86,
            importance_score: 0.1234,
            tags: ["technology"],
            entities: ["Nvidia"],
            symbols: ["NVDA"],
            engagement: { clicks: 1250 },
            raw: {},
            content_source: "source_text",
          },
        },
        source: {
          slug: "techcrunch",
          name: "TechCrunch",
          homepage_url: "https://techcrunch.com",
          icon_url: null,
        },
        topics: [{ slug: "technology", name: "Technology" }],
      },
    ]);

    const feed = await getTodayFeed();
    const story = [...feed.important, ...feed.other].find(
      (entry) => entry.canonicalHeadline === "Collector score recompute story",
    );

    expect(story).toBeDefined();
    expect(story?.representativeArticle.score).toBe(expectedScore);
    expect(story?.representativeArticle.score).not.toBe(999);
    expect(story?.importanceScore).toBe(expectedScore * 10);
  });

  it("keeps explicit scores and the legacy default for non-collector payloads", async () => {
    await syncArticles([
      {
        external_id: "non-collector-score-1",
        title: "Explicit scored story",
        summary: "This item should keep its explicit app-side score.",
        author: "Desk",
        url: "https://example.com/explicit-scored-story",
        image_url: null,
        published_at: "2026-04-17T16:30:00.000Z",
        content_text:
          "Body for explicit score test with enough supporting detail to satisfy the current feed eligibility rules and keep the story visible in the generated feed output.",
        score: 7,
        payload_json: null,
        source: {
          slug: "example-wire",
          name: "Example Wire",
          homepage_url: "https://example.com",
          icon_url: null,
        },
        topics: [{ slug: "technology", name: "Technology" }],
      },
      {
        external_id: "non-collector-score-2",
        title: "Default scored story",
        summary: "This item should fall back to the legacy default score.",
        author: "Desk",
        url: "https://example.com/default-scored-story",
        image_url: null,
        published_at: "2026-04-17T16:00:00.000Z",
        content_text:
          "Body for default score test with enough supporting detail to satisfy the current feed eligibility rules and keep the story visible in the generated feed output.",
        payload_json: null,
        source: {
          slug: "example-desk",
          name: "Example Desk",
          homepage_url: "https://example.org",
          icon_url: null,
        },
        topics: [{ slug: "technology", name: "Technology" }],
      },
      {
        external_id: "non-collector-score-3",
        title: "Default scored story",
        summary: "This second source keeps the default-scored story eligible for the feed.",
        author: "Desk",
        url: "https://example.net/default-scored-story",
        image_url: null,
        published_at: "2026-04-17T16:05:00.000Z",
        content_text:
          "Body for default score corroboration with enough supporting detail to satisfy the current feed eligibility rules and keep the story visible in the generated feed output.",
        payload_json: null,
        source: {
          slug: "example-second-desk",
          name: "Example Second Desk",
          homepage_url: "https://example.net",
          icon_url: null,
        },
        topics: [{ slug: "technology", name: "Technology" }],
      },
    ]);

    const feed = await getTodayFeed();
    const items = [...feed.important, ...feed.other];
    const explicit = items.find((entry) => entry.canonicalHeadline === "Explicit scored story");
    const fallback = items.find((entry) => entry.canonicalHeadline === "Default scored story");

    expect(explicit?.representativeArticle.score).toBe(7);
    expect(fallback?.representativeArticle.score).toBe(5);
  });
});
