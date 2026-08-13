import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("Today loads public state without presenting a signed decision", async ({ page }) => {
  await page.goto("/#/today");
  await expect(page.getByRole("heading", { name: "Today", exact: true })).toBeVisible();
  await expect(page.getByText("DATA SHADOW 0 / 20")).toBeVisible();
  await expect(page.getByText("NO BUY / SELL OUTPUT")).toBeVisible();
  await expect(page.getByText("Direction positive")).toHaveCount(0);
  await expect(page.locator("canvas.evidence-graph")).toBeVisible();
});

test("theme routing and evidence drawer work with keyboard", async ({ page }) => {
  await page.goto("/#/themes");
  await page.getByRole("button", { name: "Open theme" }).first().focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/theme=semiconductors/);
  await page.getByRole("button", { name: /Open evidence/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("certificate JSON and data-quality views are reachable", async ({ page }) => {
  await page.goto("/#/certificates?theme=semiconductors");
  await expect(page.getByRole("heading", { name: "Certificates" })).toBeVisible();
  await expect(page.getByText("DATA BLOCKED NO DECISION")).toBeVisible();
  await page.goto("/#/data-quality");
  await expect(page.getByRole("heading", { name: "Data Quality" })).toBeVisible();
  await expect(page.getByText("Missed").first()).toBeVisible();
});

test("all internal navigation links resolve", async ({ page }) => {
  await page.goto("/#/today");
  const links = await page.locator("a[href^='#/']").evaluateAll((items) => [...new Set(items.map((item) => item.getAttribute("href")))].filter(Boolean));
  for (const href of links) {
    await page.goto(`/${href}`);
    await expect(page.locator("main")).toBeVisible();
  }
});

test("Today has no serious or critical automated accessibility violations", async ({ page }) => {
  await page.goto("/#/today");
  await expect(page.getByRole("heading", { name: "Today", exact: true })).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  const severe = results.violations.filter((item) => ["serious", "critical"].includes(item.impact ?? ""));
  expect(severe, JSON.stringify(severe, null, 2)).toEqual([]);
});
