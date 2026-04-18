import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/auth", () => ({
  auth: async () => null,
}));

import { getStartupCatchupState } from "@/lib/services/startup-catchup";

declare global {
  // eslint-disable-next-line no-var
  var __memoryNewsStore__:
    | undefined
    | {
        initialized: boolean;
      };
}

describe("startup catch-up", () => {
  beforeEach(() => {
    globalThis.__memoryNewsStore__ = undefined;
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-04-17T18:00:00.000Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("requests catch-up when the current feed run is missing", async () => {
    await expect(getStartupCatchupState()).resolves.toMatchObject({
      enabled: false,
      feedDate: "2026-04-17",
      needed: false,
      reason: "database unavailable",
    });
  });

  it("uses the prior Pacific date before the daily reset hour", async () => {
    await expect(getStartupCatchupState(new Date("2026-04-17T11:30:00.000Z"))).resolves.toMatchObject({
      enabled: false,
      feedDate: "2026-04-16",
      needed: false,
      reason: "database unavailable",
    });
  });
});
