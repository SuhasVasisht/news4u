import { expect, test } from "@playwright/test";
import { pathToFileURL } from "node:url";
import path from "node:path";

test("compact header reveals news immediately and keeps secondary navigation available", async ({ page }) => {
  await page.goto(pathToFileURL(path.resolve("out/index.html")).href);
  const total = await page.locator(".major-report,.brief").count();
  for (const width of [1440, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await page.evaluate(() => scrollTo({ top: 0, behavior: "instant" }));
    const headline = await page.locator(".major-report h3").first().boundingBox();
    expect(headline!.y).toBeLessThan(width > 600 ? 300 : 250);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.locator(".section-menu > summary").click();
    await expect(page.getByRole("navigation", { name: "Newspaper sections" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.locator(".section-menu")).not.toHaveAttribute("open", "");
  }
  await page.getByRole("button", { name: "Search the paper" }).click();
  await page.getByRole("searchbox", { name: "Search the edition" }).fill("zzzz-no-matching-story");
  await expect(page.getByRole("heading", { name: "No matching stories." })).toBeVisible();
  await page.getByRole("button", { name: "Close search" }).click();
  await expect(page.locator(".major-report,.brief")).toHaveCount(total);
  await page.getByRole("button", { name: "Sources", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Sources", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "The paper", exact: true }).click();
  await expect(page.locator(".major-report,.brief")).toHaveCount(total);
  await expect(page.getByRole("button", { name: /save story|mark read|archive story|delete post|move up/i })).toHaveCount(0);
});
