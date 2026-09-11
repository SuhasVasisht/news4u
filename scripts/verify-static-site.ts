import { chromium, expect } from "@playwright/test";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { briefingStories, editionSchema, sportsGamesForDisplay } from "../src/lib/edition";
import { hash } from "./lib/static-release";
import { embeddedEdition } from "./lib/edition-archive";

export async function verifyStaticSite(base: string, root = process.cwd()) {
  const edition = editionSchema.parse(JSON.parse(await readFile(path.join(root, "data/edition.json"), "utf8")));
  const expected = await readFile(path.join(root, "data/cloudflare-bundle/index.html"));
  const response = await fetch(base, { cache: "no-store", signal: AbortSignal.timeout(30000) });
  if (!response.ok || hash(Buffer.from(await response.arrayBuffer())) !== hash(expected)) throw new Error(`Hosted index does not match the local release: ${base}`);
  const manifest = await fetch(new URL("/edition-manifest.json", base), { cache: "no-store", signal: AbortSignal.timeout(30000) });
  if (!manifest.ok || hash(Buffer.from(await manifest.arrayBuffer())) !== hash(await readFile(path.join(root, "data/cloudflare-bundle/edition-manifest.json")))) throw new Error("Hosted release manifest differs from the local release");
  const browser = await chromium.launch();
  const output = path.join(root, "data/cloudflare-verification", new URL(base).hostname);
  await mkdir(output, { recursive: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const page = await context.newPage();
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("console", message => { if (message.type() === "error" && /hydrat|minified react error/i.test(message.text())) errors.push(message.text()); });
    await page.goto(base);
    await expect(page.getByRole("heading", { name: "News 4 u.", exact: true })).toBeVisible();
    await expect(page.locator(".masthead-mark")).toBeVisible();
    const markSize = await page.locator(".masthead-mark").boundingBox();
    if (!markSize || markSize.width < 36 || Math.abs(markSize.width - markSize.height) > 1) throw new Error("Masthead mark is not rendered at its intended size");
    await expect(page.locator('link[rel="icon"]')).toHaveAttribute("href", "/news-mark.svg");
    await expect(page.locator(".major-report,.brief")).toHaveCount(edition.stories.length);
    await page.locator("img").evaluateAll(images => images.forEach(image => { (image as HTMLImageElement).loading = "eager"; }));
    await page.waitForFunction(() => [...document.images].every(image => image.complete));
    await page.evaluate(() => Promise.all([...document.images].map(image => image.decode().catch(() => {}))));
    const images = await page.locator("img").evaluateAll(images => images.map(image => ({ width: (image as HTMLImageElement).naturalWidth, height: (image as HTMLImageElement).naturalHeight })));
    if (images.some(image => image.width < 400 || image.height < 200)) throw new Error("Unusable image rendered on hosted site");
    if (edition.stories.some(story => story.image) && !images.length) throw new Error("None of the edition's images loaded");
    await page.screenshot({ path: path.join(output, "desktop.png") });
    if (edition.sports) {
      const sports = page.locator("#sector-sports");
      await expect(page.locator(".news-sector").last()).toHaveAttribute("id", "sector-sports");
      await expect(sports.locator(".major-report, .brief")).toHaveCount(edition.stories.filter(s => s.sportsGroup).length);
      await expect(sports.locator(".sports-header time")).toHaveAttribute("datetime", edition.sports.checkedAt);
      for (const league of edition.sports.leagues) {
        const details = sports.locator(".sports-league").filter({ has: page.locator("summary", { hasText: league.name }) });
        await details.evaluate(element => { (element as HTMLDetailsElement).open = true; });
        for (const game of sportsGamesForDisplay(league.games)) {
          const link = details.locator(".sports-games a").filter({ hasText: game.away.name });
          await expect(link).toContainText(game.home.name);
          await expect(link.locator("strong")).toHaveText([game.away.score ?? "-", game.home.score ?? "-"]);
        }
      }
      for (const width of [1440, 390, 320]) {
        await page.setViewportSize({ width, height: 1000 });
        await sports.evaluate(element => element.scrollIntoView({ block: "start", behavior: "instant" }));
        if (!await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)) throw new Error(`Sports overflow at ${width}px`);
        await page.screenshot({ path: path.join(output, `sports-${width}.png`) });
      }
      await page.setViewportSize({ width: 1440, height: 1000 });
    }
    for (const sector of await page.locator(".news-sector").all()) {
      await sector.evaluate(element => element.scrollIntoView({ block: "start", behavior: "instant" }));
      const id = (await sector.getAttribute("id"))!.replace(/[^a-z0-9-]/gi, "-");
      await page.screenshot({ path: path.join(output, `${id}.png`) });
    }
    await page.evaluate(() => scrollTo({ top: 0, behavior: "instant" }));
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 });
      await page.evaluate(() => scrollTo({ top: 0, behavior: "instant" }));
      if (!await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)) throw new Error(`Overflow at ${width}px`);
      await page.screenshot({ path: path.join(output, `mobile-${width}.png`) });
    }
    await page.getByRole("button", { name: "Sources", exact: true }).click();
    await expect(page.locator(".source-row")).toHaveCount(edition.sources.length);
    for (const source of edition.sources) {
      const row = page.locator(".source-row").filter({ has: page.locator("strong", { hasText: new RegExp(`^${source.name}$`) }) });
      await expect(row).toContainText(`${source.published ?? 0} published`);
      await expect(row).toContainText(`${source.collected ?? 0} collected`);
    }
    for (const width of [1440, 390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      if (!await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)) throw new Error(`Sources overflow at ${width}px`);
      await page.screenshot({ path: path.join(output, `sources-${width}.png`) });
    }
    await page.getByRole("button", { name: "I do not have time", exact: true }).click();
    await expect(page.locator(".briefing-story")).toHaveCount(briefingStories(edition.stories).length);
    await page.screenshot({ path: path.join(output, "short-edition.png") });
    await page.locator(".headline-link").first().click();
    await expect(page.locator(".report-page")).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.reload();
    await expect(page.locator(".report-page")).toBeVisible();
    await expect(page.locator(".story-actions")).toHaveCount(0);
    await page.goBack();
    await page.getByRole("button", { name: "The paper", exact: true }).click();
    await expect(page.locator(".report-top,.edition-filters,.sector-index,.story-actions")).toHaveCount(0);
    await page.locator(".headline-link").first().click();
    await page.getByRole("link", { name: "Back to the edition", exact: true }).click();
    await expect(page.locator(".major-report,.brief")).toHaveCount(edition.stories.length);
    for (const story of edition.stories) {
      const result = await page.goto(new URL(`/report-${story.id}.html`, base).href);
      if (result?.status() !== 200) throw new Error(`Report unavailable: ${story.id}`);
      await expect(page.locator("#reader-title")).toHaveText(story.title);
      for (const note of story.sections || []) {
        const section = page.locator(".note-section").filter({ has: page.getByRole("heading", { name: note.heading, exact: true }) });
        await expect(section.locator("p")).toHaveText(note.body.split(/\n\n+/));
      }
      if (story.kind === "podcast") {
        await expect(page.locator("audio")).toHaveAttribute("src", story.audioUrl!);
        expect(await page.locator(".note-section").count()).toBeGreaterThanOrEqual(6);
        await page.screenshot({ path: path.join(output, `podcast-${story.id}.png`) });
        await page.locator(".note-section").last().scrollIntoViewIfNeeded();
        await page.screenshot({ path: path.join(output, `podcast-${story.id}-end.png`) });
      }
    }
    await page.goto(new URL("/editions/", base).href);
    await expect(page.getByRole("heading", { name: "Past editions", exact: true })).toBeVisible();
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 });
      if (!await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)) throw new Error(`Archive overflow at ${width}px`);
      await page.screenshot({ path: path.join(output, `archive-mobile-${width}.png`) });
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.screenshot({ path: path.join(output, "archive-desktop.png") });
    const release = JSON.parse(await readFile(path.join(root, "data/cloudflare-bundle/edition-manifest.json"), "utf8")) as { editions: { date: string; stories: number; path?: string }[]; revisions?: { date: string; stories: number; path: string }[]; files: Record<string, string> };
    if (!release.editions?.some(item => item.date === edition.date)) throw new Error("Current edition missing from archive");
    for (const archived of [...release.editions, ...(release.revisions || [])]) {
      const archivedPath = `/editions/${archived.path || archived.date}/`;
      const result = await page.goto(new URL(archivedPath, base).href);
      if (result?.status() !== 200) throw new Error(`Archived edition unavailable: ${archived.date}`);
      const expectedArchive = embeddedEdition(await readFile(path.join(root, "data/cloudflare-bundle", archivedPath, "index.html"), "utf8"));
      await expect(page.locator(".edition-date time")).toHaveAttribute("datetime", archived.date);
      await expect(page.getByRole("button", { name: "Edition", exact: true })).toBeVisible();
      await page.locator(".headline-link").first().click();
      if (!new URL(page.url()).pathname.startsWith(archivedPath)) throw new Error("Archived report escaped its edition");
      await expect(page.locator("#reader-title")).toBeVisible();
      await page.getByRole("link", { name: "Back to the edition", exact: true }).click();
      await expect(page.locator(".edition-date time")).toHaveAttribute("datetime", archived.date);
      // Verify every archived report's bytes, not just the first navigation target.
      for (const story of expectedArchive.stories) {
        const name = `editions/${archived.path || archived.date}/report-${story.id}.html`;
        const report = await fetch(new URL(`/${name}`, base), { signal: AbortSignal.timeout(30000) });
        if (!report.ok || hash(Buffer.from(await report.arrayBuffer())) !== release.files[name]) throw new Error(`Archived report changed or missing: ${name}`);
      }
    }
    for (const name of Object.keys(release.files).filter(name => name === "news-mark.svg" || name.startsWith("media/"))) {
      const asset = await fetch(new URL(`/${name}`, base), { signal: AbortSignal.timeout(30000) });
      if (!asset.ok || hash(Buffer.from(await asset.arrayBuffer())) !== release.files[name]) throw new Error(`Media asset changed or missing: ${name}`);
    }
    const noJs = await browser.newContext({ javaScriptEnabled: false });
    const plain = await noJs.newPage();
    await plain.goto(base);
    await plain.locator(".headline-link").first().click();
    await expect(plain.locator(".report-page")).toBeVisible();
    await plain.getByRole("link", { name: "Past editions", exact: true }).click();
    await plain.locator("article h2 a").first().click();
    await plain.locator(".headline-link").first().click();
    await expect(plain.locator(".report-page")).toBeVisible();
    for (const route of ["/this-report-does-not-exist", "/.env", "/data/edition-audit.json"]) {
      const missing = await fetch(new URL(route, base), { signal: AbortSignal.timeout(30000) });
      if (missing.status !== 404) throw new Error(`Non-public paths must return 404: ${route}`);
    }
    if (errors.length) throw new Error(`Browser errors: ${errors.join("; ")}`);
    const result = { url: base, verifiedAt: new Date().toISOString(), date: edition.date, reports: edition.stories.length, images: images.length, editions: release.editions, browserErrors: errors, screenshots: output };
    await writeFile(path.join(output, "result.json"), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result, null, 2));
  } finally { await browser.close(); }
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  verifyStaticSite(process.argv[2] || "https://news.suhasv.com").catch(error => { console.error(error.message); process.exitCode = 1; });
}
