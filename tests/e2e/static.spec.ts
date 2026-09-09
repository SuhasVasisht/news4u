import { expect, test } from "@playwright/test";
import { existsSync } from "node:fs";
import { pathToFileURL } from "node:url";
import path from "node:path";

const artifact = path.resolve("out/index.html");
test("static edition works offline without a backend", async ({ browser }) => {
  test.skip(!existsSync(artifact), "Run npm run build:daily first");
  const context = await browser.newContext({ offline: true });
  const page = await context.newPage();
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto(pathToFileURL(artifact).href);
  await expect(page.getByRole("heading", { name: "News 4 u." })).toBeVisible();
  await page.locator(".major-report").first().getByRole("button", { name: "Save story", exact: true }).click();
  await page.getByRole("button", { name: "Saved 1", exact: true }).click();
  await expect(page.locator(".major-report,.brief")).toHaveCount(1);
  await page.reload();
  await page.getByRole("button", { name: "Saved 1", exact: true }).click();
  await expect(page.locator(".major-report,.brief")).toHaveCount(1);
  await page.locator(".headline-link").first().click();
  await expect(page.locator(".report-page")).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.reload();
    await expect(page.locator(".report-page")).toBeVisible();
  expect(errors).toEqual([]);
  await context.close();
});

test("static HTML contains readable news before JavaScript", async ({ browser }) => {
  test.skip(!existsSync(artifact), "Run npm run build:daily first");
  const context = await browser.newContext({ javaScriptEnabled: false, offline: true });
  const page = await context.newPage();
  await page.goto(pathToFileURL(artifact).href);
  expect(await page.locator(".major-report").count()).toBeGreaterThan(0);
  await expect(page.locator(".report-tail a").first()).toHaveAttribute("href", /^https?:\/\//);
  await page.locator(".headline-link").first().click();
  await expect(page.locator(".report-page")).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await context.close();
});

test("podcast notes are included in static report HTML without JavaScript", async ({ browser }) => {
  test.skip(!existsSync(artifact), "Run npm run build:daily first");
  const context = await browser.newContext({ javaScriptEnabled: false, offline: true });
  const page = await context.newPage();
  await page.goto(pathToFileURL(artifact).href);
  await page.locator('[id="sector-listening room"] .headline-link').first().click();
  await expect(page.locator(".report-page audio")).toHaveAttribute("preload", "none");
  expect(await page.locator(".note-section").count()).toBeGreaterThanOrEqual(6);
  expect((await page.locator(".report-notes").innerText()).split(/\s+/).length).toBeGreaterThan(500);
  await context.close();
});
