import { expect, test } from "@playwright/test";

test("critical routes render and anonymous controls respond", async ({ page }) => {
  const pageErrors: string[] = [];
  const failedResponses: string[] = [];

  await page.addInitScript(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("response", (response) => {
    if (response.status() >= 400) {
      failedResponses.push(`${response.status()} ${response.url()}`);
    }
  });

  await page.goto("/");
  await expect(page.getByText("The highest-signal stories for today, with tech leading the mix.")).toBeVisible();
  const markReadButtons = page.getByRole("button", { name: /Mark read/i });
  if ((await markReadButtons.count()) > 0) {
    await markReadButtons.first().click();
  } else {
    await expect(page.getByText("Nothing else is visible right now.")).toBeVisible();
  }

  await page.goto("/catchup");
  await expect(page.getByText("Unread prior days, compressed.")).toBeVisible();

  await page.goto("/search?q=market");
  await expect(page.getByText(/Showing .* result/i)).toBeVisible();
  await expect(page.getByRole("heading", { name: /market/i }).first()).toBeVisible();

  await page.getByRole("link", { name: /Open story/i }).first().click();
  await expect(page.getByText("Story cluster")).toBeVisible();

  await page.goto("/settings");
  await expect(page.getByText("Quiet defaults for a single-reader workflow.")).toBeVisible();

  expect(pageErrors).toEqual([]);
  expect(failedResponses).toEqual([]);
});

test("mobile shell uses News 4 u branding without the old sidebar hero", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  await expect(page.locator("div.lg\\:hidden").getByText("News 4 u")).toBeVisible();
  await expect(page.getByText("Finite daily feed, not endless churn.")).toHaveCount(0);
  await expect(page.getByRole("link", { name: /today/i }).first()).toBeVisible();
});
