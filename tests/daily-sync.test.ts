import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { runDailySyncJob } from "@/lib/services/daily-sync";

describe("daily sync job", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-04-17T12:00:00.000Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("runs the collector pipeline before cleanup and feed refresh", async () => {
    const calls: string[] = [];
    const result = await runDailySyncJob({
      now: () => new Date(),
      runPythonJob: async (name) => {
        calls.push(name);
        return {
          name,
          status: "ok",
          command: `python3 -m ${name}`,
          startedAt: new Date().toISOString(),
          finishedAt: new Date().toISOString(),
          durationMs: 0,
          stdout: "",
          stderr: "",
          json:
            name === "collect"
              ? {
                  sources: [
                    {
                      collector: "x_search",
                      status: "degraded",
                      reason: "missing persistent X browser profile",
                    },
                  ],
                }
              : null,
        };
      },
      cleanupFeed: async () => {
        calls.push("cleanup");
        return { removedStories: 2 };
      },
      refreshFeed: async () => {
        calls.push("feedRefresh");
        return { feedDate: "2026-04-17" };
      },
    });

    expect(calls).toEqual(["collect", "digest", "publish", "cleanup", "feedRefresh"]);
    expect(result.status).toBe("ok");
    expect(result.optionalCollectorSkips).toEqual([
      {
        collector: "x_search",
        status: "degraded",
        reason: "missing persistent X browser profile",
      },
    ]);
    expect(result.steps.cleanup?.result).toEqual({ removedStories: 2 });
    expect(result.steps.feedRefresh?.result).toEqual({ feedDate: "2026-04-17" });
  });

  it("returns partial step results when publish fails", async () => {
    await expect(
      runDailySyncJob({
        now: () => new Date(),
        runPythonJob: async (name) => ({
          name,
          status: name === "publish" ? "failed" : "ok",
          command: `python3 -m ${name}`,
          startedAt: new Date().toISOString(),
          finishedAt: new Date().toISOString(),
          durationMs: 0,
          stdout: "",
          stderr: name === "publish" ? "publish failed" : "",
          json: null,
        }),
        cleanupFeed: async () => ({ ok: true }),
        refreshFeed: async () => ({ ok: true }),
      }),
    ).rejects.toMatchObject({
      result: {
        status: "failed",
        steps: {
          collect: { status: "ok" },
          digest: { status: "ok" },
          publish: { status: "failed" },
        },
      },
    });
  });
});
