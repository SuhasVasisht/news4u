import { describe, expect, it, vi } from "vitest";
import sharp from "sharp";
import { mkdtemp, mkdir, writeFile, readFile, rm } from "node:fs/promises";
import path from "node:path";
import { tmpdir } from "node:os";
import { optimizeImage, prepareMedia } from "../scripts/lib/static-media";
import type { EditionData } from "../src/lib/edition";

describe("pipeline-managed media", () => {
  it("deduplicates, resizes without enlargement and rejects tiny/non-image inputs", async () => {
    const body = await sharp({ create: { width: 2000, height: 1200, channels: 3, background: "#225588" } }).png().toBuffer();
    const first = await optimizeImage(body);
    expect(first.name).toBe((await optimizeImage(body)).name);
    expect(first.width).toBe(1600);
    expect((await sharp(first.body).metadata()).format).toBe("webp");
    await expect(optimizeImage(Buffer.from("not a photo"))).rejects.toThrow();
    const tiny = await sharp({ create: { width: 100, height: 100, channels: 3, background: "white" } }).png().toBuffer();
    await expect(optimizeImage(tiny)).rejects.toThrow("Unusable");
  });

  it("only fetches exactly approved images and retains attribution", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "news-media-"));
    try {
      await mkdir(path.join(root, "config")); await mkdir(path.join(root, "data"));
      await writeFile(path.join(root, "config/image-permissions.json"), JSON.stringify({ approved: [{ imageUrl: "https://example.com/approved.png", credit: "Photographer / CC BY", licenseUrl: "https://example.com/license" }] }));
      const body = await sharp({ create: { width: 800, height: 600, channels: 3, background: "white" } }).png().toBuffer();
      const fetcher = vi.fn().mockResolvedValue(new Response(new Uint8Array(body)));
      vi.stubGlobal("fetch", fetcher);
      const edition = { stories: [{ id: "approved", image: "https://example.com/approved.png" }, { id: "remote", image: "https://example.com/unapproved.png" }] } as EditionData;
      await prepareMedia(root, edition);
      expect(fetcher).toHaveBeenCalledTimes(1);
      expect(edition.stories[0].imageAsset?.credit).toBe("Photographer / CC BY");
      expect(edition.stories[1].imageAsset).toBeUndefined();
      expect((await readFile(path.join(root, "out", edition.stories[0].imageAsset!.src.slice(1)))).length).toBeGreaterThan(0);
    } finally { vi.unstubAllGlobals(); await rm(root, { recursive: true, force: true }); }
  });
});
