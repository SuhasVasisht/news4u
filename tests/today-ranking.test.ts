import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/auth", () => ({
  auth: async () => null,
}));

import { getTodayFeed, syncArticles } from "@/lib/services/news-service";

describe("today ranking and quality filtering", () => {
  beforeEach(() => {
    (globalThis as { __memoryNewsStore__?: unknown }).__memoryNewsStore__ = undefined;
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-04-17T18:00:00.000Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("prefers tech stories when scores are otherwise close", async () => {
    await syncArticles([
      {
        external_id: "tech-close-call",
        title: "Inference tooling budgets hold up as teams cut broader software spend",
        summary: "Enterprise buyers are still funding AI operations and observability even while reducing other software categories.",
        author: "Desk",
        url: "https://example.com/tech-close-call",
        image_url: null,
        published_at: "2026-04-17T17:45:00.000Z",
        content_text:
          "Operators are continuing to fund inference routing, observability, and governance layers because those systems expose measurable savings. Teams described the tools as durable infrastructure rather than discretionary experimentation.",
        score: 8.4,
        payload_json: null,
        source: {
          slug: "plain-desk",
          name: "Plain Desk",
          homepage_url: "https://example.com",
          icon_url: null,
        },
        topics: [{ slug: "technology", name: "Technology" }],
      },
      {
        external_id: "macro-close-call",
        title: "Credit desks stay defensive as refinancing calendars thicken",
        summary: "Bond investors are still leaning cautious as companies return to market with larger funding needs.",
        author: "Desk",
        url: "https://example.com/macro-close-call",
        image_url: null,
        published_at: "2026-04-17T17:45:00.000Z",
        content_text:
          "Portfolio managers said they are still willing to own quality credit, but broader demand is becoming more selective as refinancing needs climb. Traders framed the tone as cautious rather than disorderly.",
        score: 8.4,
        payload_json: null,
        source: {
          slug: "plain-macro",
          name: "Plain Macro",
          homepage_url: "https://example.org",
          icon_url: null,
        },
        topics: [{ slug: "markets", name: "Markets" }],
      },
    ]);

    const orderedTitles = [...(await getTodayFeed()).important, ...(await getTodayFeed()).other].map(
      (story) => story.canonicalHeadline,
    );

    expect(orderedTitles.indexOf("Inference tooling budgets hold up as teams cut broader software spend")).toBeLessThan(
      orderedTitles.indexOf("Credit desks stay defensive as refinancing calendars thicken"),
    );
  });

  it("still lets clearly bigger non-tech stories outrank weaker tech filler", async () => {
    await syncArticles([
      {
        external_id: "huge-world-story",
        title: "Shipping disruption forces emergency reroutes across major trade corridors",
        summary: "Governments and freight operators are scrambling to keep high-volume routes open after a sudden disruption.",
        author: "Desk",
        url: "https://example.com/huge-world-story",
        image_url: null,
        published_at: "2026-04-17T17:50:00.000Z",
        content_text:
          "Ports, carriers, and insurers were all forced to adjust route assumptions after the disruption widened. Analysts described the change as globally significant because it altered transit times, insurance pricing, and inventory planning across multiple industries.",
        score: 10,
        payload_json: null,
        source: {
          slug: "world-wire",
          name: "World Wire",
          homepage_url: "https://example.net",
          icon_url: null,
        },
        topics: [{ slug: "policy", name: "Policy" }],
      },
      {
        external_id: "weaker-tech-story",
        title: "A startup tweaks its developer dashboard for small inference teams",
        summary: "The release is relevant to tooling buyers but does not appear to have broad market impact.",
        author: "Desk",
        url: "https://example.com/weaker-tech-story",
        image_url: null,
        published_at: "2026-04-17T17:40:00.000Z",
        content_text:
          "The company shipped a modest product update focused on dashboard polish and a few deployment quality-of-life improvements for smaller engineering teams.",
        score: 7.1,
        payload_json: null,
        source: {
          slug: "builder-notes",
          name: "Builder Notes",
          homepage_url: "https://example.dev",
          icon_url: null,
        },
        topics: [{ slug: "technology", name: "Technology" }],
      },
    ]);

    const orderedTitles = [...(await getTodayFeed()).important, ...(await getTodayFeed()).other].map(
      (story) => story.canonicalHeadline,
    );

    expect(orderedTitles.indexOf("Shipping disruption forces emergency reroutes across major trade corridors")).toBeLessThan(
      orderedTitles.indexOf("A startup tweaks its developer dashboard for small inference teams"),
    );
  });

  it("keeps low-quality items out of Today while still ingesting them", async () => {
    await syncArticles([
      {
        external_id: "junk-story",
        title: "Crypto rumor thread says something might happen",
        summary: "Brief rumor summary.",
        author: "Desk",
        url: "https://example.com/junk-story",
        image_url: null,
        published_at: "2026-04-17T17:55:00.000Z",
        content_text: "Too short to be useful.",
        score: 9.5,
        payload_json: null,
        source: {
          slug: "rumor-mill",
          name: "Rumor Mill",
          homepage_url: "https://example.biz",
          icon_url: null,
        },
        topics: [{ slug: "markets", name: "Markets" }],
      },
    ]);

    const orderedTitles = [...(await getTodayFeed()).important, ...(await getTodayFeed()).other].map(
      (story) => story.canonicalHeadline,
    );

    expect(orderedTitles).not.toContain("Crypto rumor thread says something might happen");
  });
});
