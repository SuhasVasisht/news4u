import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/services/daily-sync", () => ({
  DailySyncJobError: class DailySyncJobError extends Error {
    constructor(public readonly result: unknown) {
      super("failed");
    }
  },
  runDailySyncJob: vi.fn(),
}));

describe("daily sync route", () => {
  beforeEach(() => {
    process.env.INTERNAL_API_KEY = "route-secret";
    globalThis.__dailySyncRouteState__ = undefined;
    vi.clearAllMocks();
  });

  it("rejects unauthorized requests", async () => {
    const { POST } = await import("@/app/api/internal/jobs/daily-sync/route");
    const response = await POST(new Request("http://localhost/api/internal/jobs/daily-sync", { method: "POST" }));

    expect(response.status).toBe(401);
    await expect(response.json()).resolves.toEqual({ error: "Unauthorized" });
  });

  it("returns conflict while a run is already in flight", async () => {
    globalThis.__dailySyncRouteState__ = {
      running: true,
      startedAt: "2026-04-17T12:00:00.000Z",
    };

    const { POST } = await import("@/app/api/internal/jobs/daily-sync/route");
    const response = await POST(
      new Request("http://localhost/api/internal/jobs/daily-sync", {
        method: "POST",
        headers: {
          authorization: "Bearer route-secret",
        },
      }),
    );

    expect(response.status).toBe(409);
    await expect(response.json()).resolves.toEqual({
      error: "Daily sync already running",
      startedAt: "2026-04-17T12:00:00.000Z",
    });
  });

  it("returns structured failure details from the job runner", async () => {
    const { DailySyncJobError, runDailySyncJob } = await import("@/lib/services/daily-sync");
    vi.mocked(runDailySyncJob).mockRejectedValueOnce(
      new DailySyncJobError({
        status: "failed",
        startedAt: "2026-04-17T12:00:00.000Z",
        finishedAt: "2026-04-17T12:01:00.000Z",
        durationMs: 60000,
        steps: {
          collect: { status: "ok" },
          publish: { status: "failed" },
        },
        optionalCollectorSkips: [],
      }),
    );

    const { POST } = await import("@/app/api/internal/jobs/daily-sync/route");
    const response = await POST(
      new Request("http://localhost/api/internal/jobs/daily-sync", {
        method: "POST",
        headers: {
          authorization: "Bearer route-secret",
        },
      }),
    );

    expect(response.status).toBe(500);
    await expect(response.json()).resolves.toMatchObject({
      status: "failed",
      steps: {
        publish: { status: "failed" },
      },
    });
  });
});
