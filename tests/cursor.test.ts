import { describe, expect, it } from "vitest";
import { decodeCursor, encodeCursor } from "@/lib/utils/cursor";

describe("cursor helpers", () => {
  it("round-trips cursor payloads", () => {
    const encoded = encodeCursor({
      publishedAt: "2026-04-16T08:00:00.000Z",
      id: "art-1",
    });

    expect(decodeCursor(encoded)).toEqual({
      publishedAt: "2026-04-16T08:00:00.000Z",
      id: "art-1",
    });
  });

  it("returns null for invalid cursors", () => {
    expect(decodeCursor("not-a-cursor")).toBeNull();
  });
});
