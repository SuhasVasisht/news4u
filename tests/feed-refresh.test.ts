import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/auth", () => ({
  auth: async () => null,
}));

import { generateDailyFeed, getTodayFeed, syncArticles } from "@/lib/services/news-service";

describe("feed refresh", () => {
  beforeEach(() => {
    (globalThis as { __memoryNewsStore__?: unknown }).__memoryNewsStore__ = undefined;
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-04-17T18:00:00.000Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("rebuilds an existing feed run when late articles arrive", async () => {
    await generateDailyFeed({ feedDate: "2026-04-17" });
    const initial = await getTodayFeed();
    const initialTitles = [...initial.important, ...initial.other].map((story) => story.canonicalHeadline);

    await syncArticles([
      {
        external_id: "late-breaking-1",
        title: "Late-breaking chip supply story reaches the top of the queue",
        summary: "A newly synced story should appear after a forced feed refresh.",
        author: "Desk",
        url: "https://example.com/late-breaking-chip-story",
        image_url: "https://images.example.com/late-chip.jpg",
        published_at: "2026-04-17T18:30:00.000Z",
        content_text:
          "Full body text for the late-arriving article with enough detail to satisfy the current feed eligibility rules. It includes added context, follow-up reporting, and enough length to cross the minimum body threshold.",
        score: 10,
        payload_json: null,
        source: {
          slug: "example-wire",
          name: "Example Wire",
          homepage_url: "https://example.com",
          icon_url: null,
        },
        topics: [{ slug: "technology", name: "Technology" }],
      },
    ]);

    await generateDailyFeed({ feedDate: "2026-04-17", forceRefresh: true });
    const refreshed = await getTodayFeed();
    const refreshedTitles = [...refreshed.important, ...refreshed.other].map((story) => story.canonicalHeadline);

    expect(initialTitles).not.toContain("Late-breaking chip supply story reaches the top of the queue");
    expect(refreshedTitles).toContain("Late-breaking chip supply story reaches the top of the queue");
  });
});
