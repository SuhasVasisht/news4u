import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";
import sharp from "sharp";
import { z } from "zod";
import type { EditionData } from "../../src/lib/edition";

const permissionSchema = z.object({ approved: z.array(z.object({
  imageUrl: z.string().url().startsWith("https://"), credit: z.string().min(1),
  licenseUrl: z.string().url().startsWith("https://"),
})) });

export async function optimizeImage(body: Buffer) {
  if (body.length > 20 * 1024 * 1024) throw new Error("Image exceeds 20 MiB");
  const source = sharp(body, { limitInputPixels: 40_000_000 });
  const meta = await source.metadata();
  if (!["jpeg", "png", "webp", "avif"].includes(meta.format || "") || !meta.width || !meta.height || meta.width < 400 || meta.height < 200) throw new Error("Unusable source image");
  const result = await source.rotate().resize({ width: 1600, withoutEnlargement: true }).webp({ quality: 85 }).toBuffer({ resolveWithObject: true });
  if (result.info.width < 400 || result.info.height < 200) throw new Error("Unusable optimized image");
  return { body: result.data, width: result.info.width, height: result.info.height, name: `${createHash("sha256").update(result.data).digest("hex")}.webp` };
}

export async function prepareMedia(root: string, edition: EditionData) {
  const permissions = permissionSchema.parse(JSON.parse(await readFile(path.join(root, "config/image-permissions.json"), "utf8")));
  const audit: { story: string; status: string; reason?: string }[] = [];
  await mkdir(path.join(root, "out/media"), { recursive: true });
  for (const story of edition.stories) {
    delete story.imageAsset;
    const permission = permissions.approved.find(item => item.imageUrl === story.image);
    if (!permission) { if (story.image) audit.push({ story: story.id, status: "publisher-hosted", reason: "No approved redistribution permission" }); continue; }
    try {
      // Exact approved URLs only; redirects require their own permission entry.
      const response = await fetch(permission.imageUrl, { redirect: "error", signal: AbortSignal.timeout(20000) });
      if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);
      const chunks: Buffer[] = []; let bytes = 0;
      const reader = response.body.getReader();
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          bytes += value.length;
          if (bytes > 20 * 1024 * 1024) throw new Error("Image exceeds 20 MiB");
          chunks.push(Buffer.from(value));
        }
      } finally { await reader.cancel(); }
      const optimized = await optimizeImage(Buffer.concat(chunks));
      await writeFile(path.join(root, "out/media", optimized.name), optimized.body);
      story.imageAsset = { src: `/media/${optimized.name}`, width: optimized.width, height: optimized.height, credit: permission.credit, licenseUrl: permission.licenseUrl };
      audit.push({ story: story.id, status: "self-hosted" });
    } catch (error) { audit.push({ story: story.id, status: "publisher-hosted", reason: (error as Error).message }); }
  }
  await writeFile(path.join(root, "data/media-audit.json"), JSON.stringify(audit, null, 2));
  return edition;
}
