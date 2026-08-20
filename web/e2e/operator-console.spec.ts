import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { ChildProcess, spawn } from "node:child_process";
import { rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

let processHandle: ChildProcess;
let operatorUrl: string;
let runtimeRoot: string;

test.beforeAll(async ({ browserName: _browserName }, workerInfo) => {
  const port = workerInfo.project.name === "mobile" ? 8878 : _browserName === "chromium" ? 8877 : 8879;
  operatorUrl = `http://127.0.0.1:${port}`;
  runtimeRoot = join(tmpdir(), `mso-v050-operator-${workerInfo.project.name}`);
  rmSync(runtimeRoot, { recursive: true, force: true });
  processHandle = spawn(
    process.env.PYTHON ?? "python",
    ["-m", "market_state_observatory.runtime.operator_console", "--port", String(port)],
    {
      cwd: resolve("."),
      env: { ...process.env, MSO_RUNTIME_ROOT: runtimeRoot, PYTHONPATH: resolve("src") },
      stdio: "ignore",
    },
  );
  for (let attempt = 0; attempt < 50; attempt += 1) {
    try {
      const response = await fetch(`${operatorUrl}/api/status`);
      if (response.ok) return;
    } catch {
      await new Promise((done) => setTimeout(done, 100));
    }
  }
  throw new Error("Private Operator Console did not start");
});

test.afterAll(() => {
  processHandle?.kill();
  rmSync(runtimeRoot, { recursive: true, force: true });
});

test("private Operator Console pages remain factual and candidate-labeled", async ({ page }) => {
  await page.goto(operatorUrl);
  await expect(page.getByRole("heading", { name: /Market State Observatory/ })).toBeVisible();
  await expect(page.getByText("127.0.0.1 only")).toBeVisible();
  await expect(page.getByText("Positions / orders")).toBeVisible();
  const more = page.getByRole("button", { name: "More" });
  if (await more.isVisible()) await more.click();
  await page.getByRole("button", { name: "Experiments" }).click();
  await expect(page.getByText("NOT CALIBRATED")).toBeVisible();
  await expect(page.getByText("MODEL_SHADOW_ONLY")).toBeVisible();
  if (await more.isVisible()) await more.click();
  await page.getByRole("button", { name: "Promotion Gates" }).click();
  await expect(page.getByText("UNAVAILABLE")).toBeVisible();
});

test("private Operator Console has no serious accessibility violations", async ({ page }) => {
  await page.goto(operatorUrl);
  await expect(page.getByText("Latest completed evidence")).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  const severe = results.violations.filter((item) => ["serious", "critical"].includes(item.impact ?? ""));
  expect(severe, JSON.stringify(severe, null, 2)).toEqual([]);
});
