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
  await page.getByRole("heading", { name: /Temukan lowongan kerja Indonesia/i }).waitFor({ timeout: 30000 });

  assert.equal(await page.locator('link[rel="canonical"]').getAttribute("href"),
    "https://reybyoo-maker.github.io/SCRAPING-INFO-LOKER/",
    "Canonical URL should use the real GitHub Pages project URL");
  assert.doesNotMatch(await page.content(), /DOMAIN-KAMU\.com|TODO|isi sendiri/i,
    "The published HTML should not contain domain or implementation placeholders");
  assert.equal(await page.locator('a[href="#lowongan"]').count() >= 1, true,
    "Top navigation should include the job listings section");
  assert.equal(await page.locator('a[href="#fitur"]').count(), 1, "Navigation should include the features section");
  assert.equal(await page.locator('a[href="#faq"]').count(), 1, "Navigation should include the FAQ section");
  assert.equal(await page.locator("#fitur").count(), 1, "Features section should be present");
  assert.equal(await page.locator("#faq").count(), 1, "FAQ section should be present");

  await page.waitForFunction(() => {
    const raw = document.querySelector("#metricTotal")?.textContent?.trim() || "";
    const count = Number(raw.replace(/[^0-9]/g, ""));
    return raw && raw !== "—" && Number.isFinite(count) && count > 0;
  }, null, { timeout: 60000 });

  const total = await page.locator("#metricTotal").innerText();
  assert.equal(await page.locator('#source option[value="__company_sites__"]').count(), 1,
    "Source filter should include Company Sites");
  assert.equal(await page.locator('#source option[value="__job_portal__"]').count(), 1,
    "Source filter should include Job Portal");
  const bodyText = await page.locator("body").innerText();
  assert.match(bodyText, /Dataset siap|Dataset terhubung/i, "Dataset status should show successful loading");

  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
    "Desktop layout should not create horizontal overflow");

  // Theme persistence and switching should remain functional.
  assert.equal(await page.locator("html").getAttribute("data-theme"), "dark",
    "The new website should start in its dark theme by default");
  await page.locator("#themeToggle").click();
  assert.equal(await page.locator("html").getAttribute("data-theme"), "light",
    "Theme switch should enable light mode");
  await page.locator("#themeToggle").click();
  assert.equal(await page.locator("html").getAttribute("data-theme"), "dark",
    "Theme switch should return to dark mode");

  // Company directory and company-to-search handoff.
  await page.locator("#famousCompaniesNav").click();
  assert.equal(await page.locator("#companyDialog").evaluate(dialog => dialog.open), true,
    "Famous companies button should open the company directory");
  await page.locator("#companyKeyword").fill("Pertamina");
  assert.equal(await page.locator(".cc").count(), 1,
    "Company directory search should filter to matching companies");
  await page.locator('[data-company-search="Pertamina"]').click();
  assert.equal(await page.locator("#keyword").inputValue(), "Pertamina",
    "Company selection should populate the job search");
  await page.locator("#keyword").fill("");

  // Advanced filters should open, and quick filters should retain their active state.
  await page.locator("#toggleFilters").click();
  assert.equal(await page.locator("#advancedFilters").isVisible(), true,
    "Advanced filters should open");
  await page.locator("#toggleFilters").click();
  await page.locator('[data-quick="remote"]').click();
  assert.equal(await page.locator('[data-quick="remote"]').getAttribute("class").then(v => v.includes("active")), true,
    "Quick filter selection should be reflected in the UI");
  await page.locator('[data-quick="all"]').click();

  // Saving a job and viewing its detail must continue to work.
  const firstSave = page.locator("#jobList [data-save]").first();
  await firstSave.click();
  assert.equal(await page.locator("#savedCount").innerText(), "1",
    "Saving a job should update the saved counter");
  await page.locator("#savedNav").click();
  await page.waitForFunction(() => document.querySelector("#resultCount")?.textContent?.includes("1 lowongan"));
  assert.equal(await page.locator("#jobList [data-job]").count(), 1,
    "Saved-jobs view should show the saved listing");
  await page.locator("#savedNav").click();
  const detailButton = page.locator("#jobList [data-detail]").first();
  await detailButton.click();
  assert.equal(await page.locator("#jobDialog").evaluate(dialog => dialog.open), true,
    "Job details button should open the detail dialog");
  await page.locator("#closeDialog").click();
  assert.equal(await page.locator("#jobDialog").evaluate(dialog => dialog.open), false,
    "Detail dialog close button should close the dialog");

  // Check that the supplied logo assets load when available in the served tree.
  const logoState = await page.locator('img[src="logo.jpg"]').first().evaluate(img => ({
    complete: img.complete,
    width: img.naturalWidth
  }));
  assert.ok(logoState.complete && logoState.width > 0,
    "The provided brand logo should load successfully");

  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
    "Mobile layout should not create horizontal page overflow");

  assert.equal(pageErrors.length, 0, `Unexpected page errors: ${pageErrors.join("; ")}`);

  await mkdir("artifacts", { recursive: true });
  await page.screenshot({ path: screenshotPath, fullPage: true, animations: "disabled" });
  console.log(`PLAYWRIGHT_PASS title=${await page.title()} jobs=${total} status=dataset-loaded screenshot=${screenshotPath}`);
} finally {
  await browser.close();
}
