import { describe, expect, it } from "vitest";
import { mockAppPreferences, sampleSyncPayload } from "@/lib/mock-data";

function normalizeTitle(title: string) {
  return title
    .toLowerCase()
    .replace(/\s+-\s+[a-z0-9 .]+$/i, "")
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\b(the|a|an|to|from|into|for|of|and|or|on|in|with|without|another)\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function fingerprint(title: string) {
  return normalizeTitle(title).split(" ").slice(0, 6).join("-");
}

function diceCoefficient(left: string, right: string) {
  const a = normalizeTitle(left).split(" ");
  const b = normalizeTitle(right).split(" ");
  const shared = a.filter((token) => b.includes(token)).length;
  return (2 * shared) / (a.length + b.length);
}

describe("story feed fixtures", () => {
  it("keeps near-duplicate enterprise contract headlines in the same similarity band", () => {
    expect(diceCoefficient(sampleSyncPayload[0].title, sampleSyncPayload[1].title)).toBeGreaterThanOrEqual(0.7);
    expect(fingerprint(sampleSyncPayload[0].title).startsWith("open-model-startups")).toBe(true);
  });

  it("keeps default app preferences stable", () => {
    expect(mockAppPreferences).toEqual({
      theme: "system",
      feedDensity: "comfortable",
      openOriginalInNewTab: true,
    });
  });
});
