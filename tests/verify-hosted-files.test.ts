import { afterEach, describe, expect, it, vi } from "vitest";
import { verifyHostedFiles } from "../scripts/lib/verify-hosted-files";
import { hash } from "../scripts/lib/static-release";

afterEach(() => vi.unstubAllGlobals());
describe("hosted release byte verification", () => {
  it("checks every file and caps concurrent requests", async () => {
    const bytes = Buffer.from("approved bytes");
    const files = Object.fromEntries(Array.from({ length: 19 }, (_, i) => [`archive/${i}.html`, hash(bytes)]));
    let active = 0, maximum = 0;
    const seen = new Set<string>();
    vi.stubGlobal("fetch", vi.fn(async (url: URL) => {
      active++; maximum = Math.max(maximum, active); seen.add(url.pathname);
      await new Promise(resolve => setTimeout(resolve, 2));
      active--;
      return new Response(bytes);
    }));
    const progress = vi.fn();
    await verifyHostedFiles("https://example.org", files, { concurrency: 3, progress });
    expect(maximum).toBe(3);
    expect(seen.size).toBe(19);
    expect(progress).toHaveBeenLastCalledWith(19, 19);
  });
  it("retries network failure and 503 while retaining the exact hash gate", async () => {
    const bytes = Buffer.from("approved bytes");
    const fetch = vi.fn().mockRejectedValueOnce(new Error("connection reset"))
      .mockResolvedValueOnce(new Response("unavailable", { status: 503 }))
      .mockResolvedValueOnce(new Response(bytes));
    vi.stubGlobal("fetch", fetch);
    await verifyHostedFiles("https://example.org", { "report.html": hash(bytes) }, { retryDelayMs: 0 });
    expect(fetch).toHaveBeenCalledTimes(3);
  });
  it.each(["changed", "missing"])("fails closed for %s content without retrying", async condition => {
    const fetch = vi.fn(async () => new Response("wrong bytes", { status: condition === "missing" ? 404 : 200 }));
    vi.stubGlobal("fetch", fetch);
    await expect(verifyHostedFiles("https://example.org", { "report.html": hash(Buffer.from("approved")) }, { retryDelayMs: 0 }))
      .rejects.toThrow(/report.html/);
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("bounds transport retries and waits for in-flight checks before failing", async () => {
    let active = 0;
    const fetch = vi.fn(async () => {
      active++; await new Promise(resolve => setTimeout(resolve, 2)); active--;
      throw new Error("connection reset");
    });
    vi.stubGlobal("fetch", fetch);
    await expect(verifyHostedFiles("https://example.org", { a: "hash", b: "hash", c: "hash" }, { concurrency: 2, attempts: 2, retryDelayMs: 0 }))
      .rejects.toThrow("connection reset");
    expect(fetch).toHaveBeenCalledTimes(4);
    expect(active).toBe(0);
  });
});
