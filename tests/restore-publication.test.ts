import { describe, it, expect } from "vitest";
import { mkdtemp, mkdir, readFile, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { hash } from "../scripts/lib/static-release";
import { restorePublication, headersFile } from "../scripts/lib/restore-publication";

const edition = { date: "2026-10-03", generatedAt: "2026-10-03T16:00:00Z", editorialReviewedAt: "2026-10-03T16:00:00Z", timezone: "America/Los_Angeles", windowHours: 48, sources: [], stories: [
  { id: "0123456789abcdefabcd", title: "Evidence reviewed story", summary: "A real account", sector: "Technology", url: "https://example.com/story", image: null, publishedAt: "2026-10-03T12:00:00Z", score: 8, publisher: "Example", collectors: [], coverage: [] },
] };
function fixture() {
  const files: Record<string, string> = { "index.html": `<script type="application/json" id="edition-data">${JSON.stringify(edition)}</script>`, "editions/index.html": "archive", "editions/2026-10-03/edition.json": JSON.stringify(edition), "_headers": headersFile };
  const manifest = { date: edition.date, generatedAt: edition.generatedAt, stories: 1, files: Object.fromEntries(Object.entries(files).map(([name, body]) => [name, hash(body)])) };
  return { files, manifest };
}
describe("fresh VM archive recovery", () => {
  it("restores history and reconstructs Cloudflare-only headers without private data", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "news-restore-"));
    try {
      const { files, manifest } = fixture();
      const fetch = async (url: string) => {
        const name = new URL(url).pathname.slice(1);
        if (name === "_headers") throw new Error("Cloudflare does not serve this file");
        return Buffer.from(name === "edition-manifest.json" ? JSON.stringify(manifest) : files[name]);
      };
      const restored = await restorePublication(root, "https://example.com", fetch);
      expect(restored.manifest.date).toBe("2026-10-03");
      expect(JSON.parse(await readFile(path.join(root, "data/cloudflare-published/editions/2026-10-03/edition.json"), "utf8"))).toEqual(edition);
      expect(await readFile(path.join(root, "data/cloudflare-published/_headers"), "utf8")).toBe(headersFile);
    } finally { await rm(root, { recursive: true, force: true }); }
  });
  it.each(["corrupt", "traversal", "changed"])("rejects %s recovery and preserves the previous local release", async failure => {
    const root = await mkdtemp(path.join(tmpdir(), "news-restore-"));
    try {
      const directory = path.join(root, "data/cloudflare-published");
      await mkdir(directory, { recursive: true });
      await writeFile(path.join(directory, "index.html"), "known good");
      const { files, manifest } = fixture();
      if (failure === "traversal") manifest.files["../secrets"] = hash("bad");
      let manifests = 0;
      const fetch = async (url: string) => {
        const name = new URL(url).pathname.slice(1);
        if (name === "edition-manifest.json") return Buffer.from(JSON.stringify({ ...manifest, ...(failure === "changed" && manifests++ ? { stories: 2 } : {}) }));
        return Buffer.from(failure === "corrupt" ? "corrupted file" : files[name]);
      };
      await expect(restorePublication(root, "https://example.com", fetch)).rejects.toThrow();
      expect(await readFile(path.join(directory, "index.html"), "utf8")).toBe("known good");
    } finally { await rm(root, { recursive: true, force: true }); }
  });
});
