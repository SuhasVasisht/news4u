import { expect, test } from "@playwright/test";

test("critical routes render and anonymous controls respond", async ({ page }) => {
  const pageErrors: string[] = [];
  const failedResponses: string[] = [];

  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("response", (response) => {
    if (response.status() >= 400) {
      failedResponses.push(`${response.status()} ${response.url()}`);
    }
  });

  await page.goto("/");
  await expect(page.getByText("Today is finite, stable, and meant to actually clear.")).toBeVisible();
  await expect(page.getByRole("heading", { name: /open-model startups/i }).first()).toBeVisible();
  await page.getByRole("button", { name: /Mark read/i }).first().click();

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
