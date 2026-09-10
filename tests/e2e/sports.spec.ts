import { expect, test } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import path from "node:path";
import { editionSchema } from "../../src/lib/edition";

test("sports back page stays compact, readable without JS, and links to dedicated reports", async ({ browser }) => {
  test.skip(!existsSync("out/index.html"), "Build the static edition first");
  const edition = editionSchema.parse(JSON.parse(readFileSync("data/edition.json", "utf8")));
  test.skip(!edition.sports, "Prepare a reviewed sports snapshot first");
  const context = await browser.newContext({ javaScriptEnabled: false, offline: true });
  const page = await context.newPage();
  await page.goto(pathToFileURL(path.resolve("out/index.html")).href);
  const section = page.locator("#sector-sports");
  await expect(page.locator(".news-sector").last()).toHaveAttribute("id", "sector-sports");
  await expect(section.getByRole("heading", { name: "Sports in brief" })).toBeVisible();
  await expect(section.locator(".major-report, .brief")).toHaveCount(edition.stories.filter(s => s.sportsGroup).length);
  for (const group of ["NFL", "Soccer", "NBA"]) {
    const stories = edition.stories.filter(s => s.sportsGroup === group);
    const roundup = section.getByRole("region", { name: `${group} roundup`, exact: true });
    await expect(roundup.locator(".major-report")).toHaveCount(stories.length ? 1 : 0);
    if (stories[0]?.image) await expect(roundup.locator(".major-report img")).toHaveAttribute("src", stories[0].imageAsset?.src || stories[0].image);
    await expect(roundup.getByRole("complementary", { name: `${group} scores` })).toBeVisible();
  }
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  const firstClosed = section.locator("details:not([open])").first();
  if (await firstClosed.count()) {
    const index = await firstClosed.evaluate(node => Array.from(document.querySelectorAll("#sector-sports details")).indexOf(node));
    const details = section.locator("details").nth(index);
    const summary = details.locator(":scope > summary");
    await summary.click();
    await expect(details).toHaveAttribute("open", "");
  }
  await section.locator(".headline-link").first().click();
  await expect(page.locator(".report-page")).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await context.close();
});
