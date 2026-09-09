import { describe, expect, it } from "vitest";
import { mkdtemp, mkdir, writeFile, readFile, readdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { assertNewEdition, assertPublicFile, prepareRelease, publicFile, releaseFiles, retainPublishedRelease } from "../scripts/lib/static-release";
import { archiveEdition } from "../scripts/lib/edition-archive";
import { dateInZone } from "../src/lib/edition";

describe("Cloudflare static release", () => {
  it("allows reader artifacts only, never runtime files, screenshots, or functions", () => {
    for (const name of ["index.html", "404.html", "_headers", "report-0123456789abcdefabcd.html", "reader-20260908T120000Z.js", "editions/2026-09-08/edition.json", "editions/index.html", `media/${"a".repeat(64)}.webp`]) expect(publicFile(name)).toBe(true);
    for (const name of [".env", "qa.png", "_worker.js", "functions/index.js", "../index.html", "edition-audit.json", "news_collector.db", "editions/../index.html", "media/x.svg", "editions/2026-09-08/.env"]) expect(publicFile(name)).toBe(false);
  });

  it("rejects credentials and files exceeding the free upload limit", () => {
    expect(() => assertPublicFile("index.html", Buffer.from("secret-token-value"), ["secret-token-value"])).toThrow("Credential");
    expect(() => assertPublicFile("index.html", Buffer.alloc(25 * 1024 * 1024 + 1), [])).toThrow("limit");
  });

  it("stages only a matching reviewed edition and preserves previously staged reports", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "news-release-test-"));
    try {
      await mkdir(path.join(root, "data"));
      await mkdir(path.join(root, "out"));
      const now = new Date().toISOString();
      const edition = { date: dateInZone(now, "America/Los_Angeles"), generatedAt: now,
        timezone: "America/Los_Angeles", windowHours: 48, editorialReviewedAt: now, sources: [],
        stories: [{ id: "0123456789abcdefabcd", title: "Reviewed story", summary: "Evidence", sector: "Technology",
          url: "https://example.com/report", image: null, publishedAt: now, score: 8, publisher: "Example", collectors: [], coverage: [] }] };
      const key = now.replace(/[^a-zA-Z0-9]/g, "");
      await writeFile(path.join(root, "out", `reader-${key}.css`), "body{color:black}");
      await writeFile(path.join(root, "out", `reader-${key}.js`), "void 0;");
      await writeFile(path.join(root, "out/qa.png"), "not public");
      async function snapshot() {
        await writeFile(path.join(root, "data/edition.json"), JSON.stringify(edition));
        await writeFile(path.join(root, "out/index.html"), `<script type="application/json" id="edition-data">${JSON.stringify(edition)}</script>`);
        await writeFile(path.join(root, "out", `report-${edition.stories[0].id}.html`), "Reviewed story");
      }
      await snapshot();
      await mkdir(path.join(root, "data/cloudflare-bundle"));
      const yesterday = { ...edition, date: "2020-01-01", stories: [{ ...edition.stories[0], id: "11111111111111111111", url: "https://example.com/older", title: "Original archived headline" }] };
      expect(() => assertNewEdition(edition, { ...yesterday, stories: edition.stories })).toThrow("Previously published");
      expect(() => assertNewEdition(edition, { ...yesterday, stories: [{ ...yesterday.stories[0], url: "https://example.com/report?utm_source=old" }] })).toThrow("Previously published");
      await writeFile(path.join(root, "data/cloudflare-bundle/index.html"), `<script type="application/json" id="edition-data">${JSON.stringify(yesterday)}</script>`);
      const release = await prepareRelease(root, []);
      expect(await readdir(release.bundle)).not.toContain("qa.png");
      await archiveEdition(release.bundle, yesterday, key);
      const frozen = await readFile(path.join(release.bundle, "editions/2020-01-01/index.html"), "utf8");
      expect(frozen).toContain("Original archived headline");
      expect(await readFile(path.join(release.bundle, "editions/2020-01-01/report-11111111111111111111.html"), "utf8")).toContain("Original archived headline");
      await retainPublishedRelease(root);
      await writeFile(path.join(release.bundle, "report-aaaaaaaaaaaaaaaaaaaa.html"), "Unpublished staging file");
      const repeat = await prepareRelease(root, []);
      expect(await readdir(repeat.bundle)).not.toContain("report-aaaaaaaaaaaaaaaaaaaa.html");
      expect(await readFile(path.join(repeat.bundle, "editions/2020-01-01/index.html"), "utf8")).toBe(frozen);
      expect(await releaseFiles(repeat.bundle)).toContain("editions/2020-01-01/report-11111111111111111111.html");
      edition.stories[0].id = "abcdef0123456789abcd";
      await snapshot();
      await expect(prepareRelease(root, [])).rejects.toThrow("immutable");
      expect(await readFile(path.join(release.bundle, "index.html"), "utf8")).not.toContain("abcdef0123456789abcd");
      const revision = await prepareRelease(root, [], { reviseToday: true });
      expect(revision.manifest.revisions).toHaveLength(1);
      const older = revision.manifest.revisions[0];
      expect(await readFile(path.join(revision.bundle, "editions", older.path, "report-0123456789abcdefabcd.html"), "utf8")).toContain("Reviewed story");
      expect(await readFile(path.join(revision.bundle, "editions", edition.date, "edition.json"), "utf8")).toContain("abcdef0123456789abcd");
      await writeFile(path.join(root, "out/index.html"), "Wrong edition");
      await expect(prepareRelease(root, [])).rejects.toThrow("differs");
    } finally { await rm(root, { recursive: true, force: true }); }
  });
});
