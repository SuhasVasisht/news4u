import { expect, test } from "@playwright/test";

test("daily edition is a newspaper without inbox actions", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "News 4 u." })).toBeVisible();
  await expect(page.locator(".story-actions,.report-top,.edition-filters,.sector-index")).toHaveCount(0);
  if (await page.locator(".headline-link").count()) {
    await page.locator(".headline-link").first().click();
    await expect(page.locator(".report-page")).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.reload();
    await expect(page.locator(".report-page")).toBeVisible();
    await expect(page.getByRole("link", { name: "Read original" })).toHaveAttribute("target", "_blank");
  }
  await page.goto("/sources");
  await expect(page.getByRole("heading", { name: "Sources", exact: true })).toBeVisible();
  for (const legacy of ["/settings", "/saved", "/archived", "/catchup"]) {
    await page.goto(legacy);
    await expect(page.getByRole("button", { name: "The paper", exact: true })).toHaveAttribute("aria-current", "page");
  }
  expect(errors).toEqual([]);
});

test("short edition ranks eight stories and opens real report pages", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "I do not have time", exact: true }).click();
  await expect(page.locator(".briefing-story")).toHaveCount(8);
  await expect(page.locator(".shared-spread")).toHaveCount(0);
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.locator(".briefing-story .headline-link").first().click();
  await expect(page).toHaveURL(/\/story\//);
  await expect(page.locator(".report-page")).toBeVisible();
  await page.getByRole("button", { name: "I do not have time", exact: true }).click();
  await expect(page.locator(".briefing-story")).toHaveCount(8);
});

test("podcast notes are visible in today's paper and readable on their own page", async ({ page }) => {
  await page.goto("/");
  const listening = page.locator('[id="sector-listening room"]');
  test.skip(await listening.count() === 0, "This edition has no podcast");
  await expect(listening).toBeVisible();
  await listening.locator(".headline-link").first().click();
  await expect(page.locator(".episode-audio audio")).toHaveAttribute("preload", "none");
  await expect(page.getByRole("heading", { name: "The takeaways", exact: true })).toBeVisible();
  expect(await page.locator(".note-section").count()).toBeGreaterThanOrEqual(6);
  expect((await page.locator(".report-notes").innerText()).split(/\s+/).length).toBeGreaterThan(500);
  for (const width of [1440, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.getByRole("navigation", { name: "Episode topics" }).getByRole("link").last().click();
  await expect(page).toHaveURL(/#note-/);
});

test("neutral, responsive spreads use a single document scroll", async ({ page }) => {
  await page.goto("/");
  for (const width of [1440, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(await page.locator(".news-sector").evaluateAll(elements => elements.every(e => !["sticky", "fixed"].includes(getComputedStyle(e).position)))).toBe(true);
    expect(await page.locator(".spread-briefs").evaluateAll(elements => elements.every(e => getComputedStyle(e).position === "static"))).toBe(true);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  if (await page.locator(".spread-briefs").count()) {
    const positions = () => page.evaluate(() => [".major-report", ".spread-briefs"].map(s => document.querySelector(s)!.getBoundingClientRect().y));
    const before = await positions();
    await page.evaluate(() => window.scrollBy({ top: 150, behavior: "instant" }));
    const after = await positions();
    expect(after.map((y, i) => Math.round(y - before[i]))).toEqual([-150, -150]);
  }
});

test("saved long-form reports do not leak back into future daily editions", async ({ page }) => {
  await page.goto("/");
  await page.evaluate(() => localStorage.setItem("news4u-reader-v1", JSON.stringify({
    saved: ["old-podcast"], library: [{ id: "old-podcast", title: "An older saved interview",
      summary: "Preserved in the library", sector: "Listening room", publisher: "Example",
      url: "https://example.com/episode", image: null, publishedAt: "2026-01-01T12:00:00Z",
      score: 9, collectors: [], coverage: [], kind: "podcast", longform: true }],
  })));
  await page.reload();
  await expect(page.getByRole("heading", { name: "An older saved interview" })).toHaveCount(0);
  await page.getByRole("button", { name: "I do not have time", exact: true }).click();
  await expect(page.getByRole("heading", { name: "An older saved interview" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Saved/ })).toHaveCount(0);
});
