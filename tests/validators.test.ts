import { describe, expect, it } from "vitest";
import { syncPayloadSchema } from "@/lib/validators/articles";

describe("sync payload schema", () => {
  it("accepts a valid payload", () => {
    const result = syncPayloadSchema.safeParse({
      articles: [
        {
          external_id: "abc-123",
          title: "A real title",
          summary: "A real summary",
          url: "https://example.com/story",
          published_at: "2026-04-16T08:00:00.000Z",
          content_text: "Article body",
          source: {
            slug: "example",
            name: "Example",
          },
          topics: [{ slug: "policy", name: "Policy" }],
        },
      ],
    });

    expect(result.success).toBe(true);
  });

  it("rejects payloads without content text", () => {
    const result = syncPayloadSchema.safeParse({
      articles: [
        {
          external_id: "abc-123",
          title: "A real title",
          summary: "A real summary",
          url: "https://example.com/story",
          published_at: "2026-04-16T08:00:00.000Z",
          content_text: "",
          source: {
            slug: "example",
            name: "Example",
          },
          topics: [{ slug: "policy", name: "Policy" }],
        },
      ],
    });

    expect(result.success).toBe(false);
  });
});
