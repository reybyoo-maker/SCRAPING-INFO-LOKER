import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { chromium } from "playwright";

const baseUrl = process.env.BASE_URL || "http://127.0.0.1:8000/";
const screenshotPath = process.env.SCREENSHOT_PATH || "artifacts/info-loker-home.png";
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
const pageErrors = [];
page.on("pageerror", error => pageErrors.push(error.message));

try {
  const response = await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 45000 });
  assert.ok(response, "Website navigation did not return an HTTP response");
  assert.equal(response.status(), 200, `Expected HTTP 200, received ${response.status()}`);
  assert.match(await page.title(), /INFO LOKER/i, "Page title should identify INFO LOKER");
  await page.getByRole("heading", { name: /Temukan peluang kerja yang tepat/i }).waitFor({ timeout: 30000 });

  await page.waitForFunction(() => {
    const raw = document.querySelector("#metricTotal")?.textContent?.trim() || "";
    const count = Number(raw.replace(/[^0-9]/g, ""));
    return raw && raw !== "—" && Number.isFinite(count) && count > 0;
  }, null, { timeout: 60000 });

  const total = await page.locator("#metricTotal").innerText();
  const bodyText = await page.locator("body").innerText();
  assert.match(bodyText, /Dataset siap|Dataset terhubung/i, "Dataset status should show successful loading");
  assert.equal(pageErrors.length, 0, `Unexpected page errors: ${pageErrors.join("; ")}`);

  await mkdir("artifacts", { recursive: true });
  await page.screenshot({ path: screenshotPath, fullPage: true, animations: "disabled" });
  console.log(`PLAYWRIGHT_PASS title=${await page.title()} jobs=${total} status=dataset-loaded screenshot=${screenshotPath}`);
} finally {
  await browser.close();
}
