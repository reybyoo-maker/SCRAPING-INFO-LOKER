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
  assert.equal(await page.locator('#source option[value="__company_sites__"]').count(), 1,
    "Source filter should include Company Sites");
  assert.equal(await page.locator('#source option[value="__job_portal__"]').count(), 1,
    "Source filter should include Job Portal");
  const bodyText = await page.locator("body").innerText();
  assert.match(bodyText, /Dataset siap|Dataset terhubung/i, "Dataset status should show successful loading");
  assert.equal(await page.locator("#sidebar").count(), 1,
    "A left-side workspace menu should be present");
  assert.equal(await page.locator("#desktopSidebarToggle").count(), 1,
    "Desktop should expose a sidebar collapse control");
  const expandedLayout = await page.evaluate(() => ({
    sidebarRight: document.querySelector("#sidebar").getBoundingClientRect().right,
    mainLeft: document.querySelector("main").getBoundingClientRect().left,
    mainRight: document.querySelector("main").getBoundingClientRect().right,
    viewportWidth: window.innerWidth
  }));
  assert.ok(Math.abs(expandedLayout.mainLeft - expandedLayout.sidebarRight) <= 2,
    `Main content should align to the sidebar edge: ${JSON.stringify(expandedLayout)}`);
  assert.ok(expandedLayout.mainRight <= expandedLayout.viewportWidth + 1,
    `Main content should not create horizontal overflow: ${JSON.stringify(expandedLayout)}`);
  await page.locator("#desktopSidebarToggle").click();
  await page.waitForTimeout(220);
  const collapsedLayout = await page.evaluate(() => ({
    sidebarWidth: document.querySelector("#sidebar").getBoundingClientRect().width,
    mainLeft: document.querySelector("main").getBoundingClientRect().left
  }));
  assert.ok(collapsedLayout.sidebarWidth < expandedLayout.sidebarRight,
    "Desktop sidebar should shrink when the collapse control is clicked");
  assert.ok(Math.abs(collapsedLayout.mainLeft - collapsedLayout.sidebarWidth) <= 2,
    "Main content should move left with the collapsed sidebar");
  assert.equal(await page.locator("#sidebar").evaluate(sidebar => getComputedStyle(sidebar).overflowY), "auto",
    "Sidebar should allow vertical scrolling");
  await page.locator("#desktopSidebarToggle").click();
  await page.waitForTimeout(220);
  assert.ok(await page.locator("#sidebar").evaluate(sidebar => sidebar.scrollHeight >= sidebar.clientHeight),
    "Sidebar container should support vertical scrolling when contents overflow");
  assert.equal(await page.locator("#famousCompaniesNav").count(), 1,
    "Sidebar should expose the famous companies directory");

  await page.locator("#themeToggle").click();
  assert.equal(await page.locator("html").getAttribute("data-theme"), "dark",
    "Theme switch should enable dark mode");
  await page.locator("#themeToggle").click();
  assert.equal(await page.locator("html").getAttribute("data-theme"), "light",
    "Theme switch should return to light mode");

  await page.locator("#famousCompaniesNav").click();
  assert.equal(await page.locator("#companyDialog").evaluate(dialog => dialog.open), true,
    "Famous companies button should open the company directory");
  await page.locator("#companyKeyword").fill("Pertamina");
  assert.equal(await page.locator(".company-card").count(), 1,
    "Company directory search should filter results");
  await page.locator('[data-company-search="Pertamina"]').click();
  assert.equal(await page.locator("#keyword").inputValue(), "Pertamina",
    "Company selection should populate the job search");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator("#mobileMenuToggle").click();
  assert.equal(await page.locator("#sidebar").evaluate(sidebar => sidebar.classList.contains("is-open")), true,
    "Mobile menu button should open the responsive sidebar");
  assert.equal(await page.locator("body").evaluate(body => body.classList.contains("sidebar-open")), true,
    "Opening the mobile sidebar should lock background scrolling");
  await page.locator("#sidebarScrim").click({ position: { x: 350, y: 400 } });
  assert.equal(await page.locator("#sidebar").evaluate(sidebar => sidebar.classList.contains("is-open")), false,
    "Backdrop should close the responsive sidebar");
  assert.equal(await page.locator("body").evaluate(body => body.classList.contains("sidebar-open")), false,
    "Closing the mobile sidebar should restore background scrolling");
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
    "Mobile layout should not create horizontal page overflow");

  assert.equal(pageErrors.length, 0, `Unexpected page errors: ${pageErrors.join("; ")}`);

  await mkdir("artifacts", { recursive: true });
  await page.screenshot({ path: screenshotPath, fullPage: true, animations: "disabled" });
  console.log(`PLAYWRIGHT_PASS title=${await page.title()} jobs=${total} status=dataset-loaded screenshot=${screenshotPath}`);
} finally {
  await browser.close();
}
