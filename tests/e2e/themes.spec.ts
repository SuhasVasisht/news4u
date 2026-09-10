import { expect, test } from "@playwright/test";
import { existsSync } from "node:fs";
import { pathToFileURL } from "node:url";
import path from "node:path";
import { editionThemes } from "../../src/lib/edition-themes";

test("theme tiles recolor the paper, persist, and remain keyboard accessible", async ({ browser }) => {
  test.skip(!existsSync("out/index.html"), "Build static HTML first");
  const context = await browser.newContext({ offline: true });
  const page = await context.newPage();
  await page.goto(pathToFileURL(path.resolve("out/index.html")).href);
  const trigger = page.getByRole("button", { name: "Choose theme" });
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    for (const theme of editionThemes) {
      await trigger.click();
      const menu = page.getByRole("menu", { name: "Paper theme" });
      await expect(menu.getByRole("menuitemradio")).toHaveCount(5);
      const box = await menu.boundingBox();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(width);
      await menu.getByRole("menuitemradio", { name: theme.name }).click();
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme.id);
      expect(await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--paper").trim())).toBe(theme.paper === "#ffffff" ? "#fff" : theme.paper);
      await expect(menu).toHaveCount(0);
      await expect(trigger).toBeFocused();
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "pop");
  await trigger.focus();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Home");
  await expect(page.getByRole("menuitemradio", { name: "Broadsheet" })).toBeFocused();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("Enter");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "night");
  await trigger.click();
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
  await expect(page.getByRole("menu")).toHaveCount(0);
  await trigger.click();
  await page.locator(".masthead-main h1").click();
  await expect(page.getByRole("menu")).toHaveCount(0);
  await context.close();
});
