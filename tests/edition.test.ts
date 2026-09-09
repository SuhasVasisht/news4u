import { describe, expect, it } from "vitest";
import { briefingStories, dateInZone, editionStorySchema, parseReaderState, sectorStories, validateBuildFreshness, type EditionStory, type EditionData } from "@/lib/edition";

const story: EditionStory = { id: "a", title: "Report", summary: "Summary", sector: "Technology", url: "https://example.com/a", image: null, publishedAt: "2026-09-08T07:30:00Z", score: 8, publisher: "Example", collectors: ["rss"], coverage: [] };
describe("shared edition", () => {
  it("preserves desk ordering and uses importance for the condensed paper", () => {
    const items = [{ ...story, id: "deep-read", score: 9.5, importance: 65, editorialRank: 1 },
      { ...story, id: "breaking", score: 8, importance: 98, editorialRank: 0 }];
    expect(sectorStories(items, "editorial", []).map(s => s.id)).toEqual(["breaking", "deep-read"]);
    expect(briefingStories(items, 1).map(s => s.id)).toEqual(["breaking"]);
  });
  it("balances the short edition and down-ranks routine stock alerts", () => {
    const items = [
      { ...story, id: "filing", title: "Fund takes a large position in stock", score: 10 },
      { ...story, id: "lead", score: 9 },
      { ...story, id: "world", sector: "World", publisher: "World publisher", score: 8 },
    ];
    expect(briefingStories(items, 2).map(s => s.id)).toEqual(["lead", "world"]);
    expect(briefingStories([])).toEqual([]);
    expect(items[0].id).toBe("filing");
  });
  it("validates browser state instead of trusting storage", () => {
    expect(parseReaderState({ saved: "not-an-array" }).saved).toEqual([]);
    expect(parseReaderState({ saved: ["a"] }).saved).toEqual(["a"]);
  });
  it("orders within a supplied sector without mutating source data", () => {
    const items = [story, { ...story, id: "b", score: 9, publishedAt: "2026-09-08T06:00:00Z" }];
    expect(sectorStories(items, "editorial", []).map(s => s.id)).toEqual(["b", "a"]);
    expect(sectorStories(items, "latest", []).map(s => s.id)).toEqual(["a", "b"]);
    expect(sectorStories(items, "custom", ["b", "a"]).map(s => s.id)).toEqual(["b", "a"]);
    expect(items[0].id).toBe("a");
  });
  it("uses Pacific dates across midnight", () => {
    expect(dateInZone("2026-09-08T06:59:00Z", "America/Los_Angeles")).toBe("2026-09-07");
    expect(dateInZone("2026-09-08T07:00:00Z", "America/Los_Angeles")).toBe("2026-09-08");
  });
  it("rejects executable publisher links", () => {
    expect(editionStorySchema.safeParse({ ...story, url: "javascript:alert(1)" }).success).toBe(false);
  });
  it("rejects stale, empty, future, and duplicate editions before publishing", () => {
    const edition: EditionData = { date: "2026-09-08", generatedAt: "2026-09-08T08:00:00Z", timezone: "America/Los_Angeles", windowHours: 48, stories: [story], sources: [] };
    const now = new Date("2026-09-08T09:00:00Z");
    expect(validateBuildFreshness(edition, now)).toBe("2026-09-08");
    expect(() => validateBuildFreshness({ ...edition, date: "2026-09-07" }, now)).toThrow(/stale/);
    expect(() => validateBuildFreshness({ ...edition, stories: [] }, now)).toThrow(/No stories/);
    expect(() => validateBuildFreshness({ ...edition, generatedAt: "2026-09-08T10:00:00Z" }, now)).toThrow(/future/);
    expect(() => validateBuildFreshness({ ...edition, stories: [story, story] }, now)).toThrow(/Duplicate/);
  });
  it("retains saved excerpts even after the daily feed changes", () => {
    const state = parseReaderState({ saved: [story.id], library: [story] });
    expect(state.library[0].title).toBe(story.title);
  });
});
