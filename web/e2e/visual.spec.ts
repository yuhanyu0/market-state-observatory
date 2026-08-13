import { expect, test } from "@playwright/test";

test("capture public-safe responsive product screenshots", async ({ page }, testInfo) => {
  await page.goto("/#/today");
  await expect(page.getByRole("heading", { name: "Today", exact: true })).toBeVisible();
  await page.screenshot({
    path: `test-results/screenshots/today-${testInfo.project.name}.png`,
    fullPage: true,
  });
  if (testInfo.project.name === "desktop") {
    await page.goto("/#/themes?theme=semiconductors");
    await expect(page.getByRole("heading", { name: "Semiconductors" })).toBeVisible();
    await page.screenshot({
      path: "test-results/screenshots/theme-detail-desktop.png",
      fullPage: true,
    });
  }
});
