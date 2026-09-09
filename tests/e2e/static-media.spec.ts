import { expect, test } from "@playwright/test";
import { createElement } from "react";
import { renderToString } from "react-dom/server";
import { readFile } from "node:fs/promises";
import sharp from "sharp";
import { build } from "esbuild";
import { createRequire } from "node:module";
import path from "node:path";
import { optimizeImage } from "../../scripts/lib/static-media";
import type { EditionData } from "../../src/lib/edition";

test("approved local images retain credits and stable lead/sidebar dimensions", async ({ page }) => {
  const input = await sharp({ create: { width: 2000, height: 1200, channels: 3, background: "#226688" } }).png().toBuffer();
  const asset = await optimizeImage(input);
  const now = new Date().toISOString();
  const edition: EditionData = { date: now.slice(0, 10), generatedAt: now, timezone: "UTC", windowHours: 48, sources: [], stories: [0, 1, 2].map(i => ({
    id: String(i).repeat(20), title: `Fixture report ${i}`, summary: "A test of the actual static reader image layout.", sector: "Technology", url: "https://example.com/report", image: "https://example.com/original.png", publishedAt: now, score: 9 - i, publisher: "Fixture", collectors: [], coverage: [],
    imageAsset: { src: `/media/${asset.name}`, width: asset.width, height: asset.height, credit: "Fixture photographer", licenseUrl: "https://example.com/license" },
  })) };
  // Compile with the production JSX runtime, not Playwright's component-test transform.
  const compiled = await build({ entryPoints: ["src/components/edition/news-edition.tsx"], bundle: true, write: false, platform: "node", format: "cjs", packages: "external", jsx: "automatic" });
  const renderer = { exports: {} as typeof import("../../src/components/edition/news-edition") };
  new Function("require", "module", "exports", compiled.outputFiles[0].text)(createRequire(path.join(process.cwd(), "package.json")), renderer, renderer.exports);
  const body = renderToString(createElement(renderer.exports.NewsEdition, { edition, staticMode: true }));
  const css = await readFile("src/components/edition/edition.css", "utf8");
  await page.route("https://fixture.test/**", route => {
    if (new URL(route.request().url()).pathname.startsWith("/media/")) return route.fulfill({ contentType: "image/webp", body: asset.body });
    return route.fulfill({ status: 404 });
  });
  await page.setContent(`<base href="https://fixture.test/"><style>${css}</style>${body}`);
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const image of await page.locator("figure img").all()) {
      await image.scrollIntoViewIfNeeded();
      await expect(image).toHaveJSProperty("naturalWidth", 1600);
      await expect(image).toHaveCSS("object-fit", "contain");
      const bounds = await image.boundingBox();
      expect(bounds!.height).toBeLessThan(bounds!.width * 1.1);
    }
    await expect(page.locator(".brief-photo figcaption")).toHaveCount(2);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});
