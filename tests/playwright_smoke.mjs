import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { chromium } from "playwright";

const baseUrl = process.env.BASE_URL || "http://127.0.0.1:8000/";
const screenshotPath = process.env.SCREENSHOT_PATH || "artifacts/info-loker-home.png";
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
const pageErrors = [];
page.on("pageerror", error => pageErrors.push(error.message));

// Inject two visually identical records with different IDs and URLs. The UI
// must collapse them before metrics, filtering, pagination, and rendering.
let injectedRawRecordCount = 0;
let duplicateFixtureInjected = false;
await page.route("**/data/jobs.json*", async route => {
  const response = await route.fetch();
  if (!response.ok()) {
    await route.fulfill({ response });
    return;
  }
  let payload;
  try {
    payload = await response.json();
  } catch {
    await route.fulfill({ response });
    return;
  }
  const jobs = Array.isArray(payload) ? payload : payload?.jobs;
  if (!Array.isArray(jobs) || jobs.length === 0) {
    await route.fulfill({ response });
    return;
  }
  const noiseTitles = new Set([
    "english", "apply", "apply now", "apply here", "sign up", "sign in",
    "see more", "see all", "view all", "read more", "learn more",
    "lamar sekarang", "pendaftaran", "academics", "lompat ke konten utama"
  ]);
  const baseIndex = jobs.findIndex(job => {
    if (!job || !(job.position || job.title) || !job.company_name) return false;
    const title = String(job.position || job.title).normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
    return !noiseTitles.has(title);
  });
  if (baseIndex < 0) {
    await route.fulfill({ response });
    return;
  }
  const base = jobs[baseIndex];
  const duplicates = [1, 2].map(n => ({
    ...base,
    id: `dedupe-smoke-${n}`,
    collector_id: `dedupe-smoke-${n}`,
    legacy_id: `dedupe-smoke-${n}`,
    listing_url: `https://duplicate-fixture.invalid/jobs/${n}`,
    application_url: `https://duplicate-fixture.invalid/apply/${n}`,
    source_updated_at: "2099-01-01T00:00:00.000Z",
    published_at: "2099-01-01T00:00:00.000Z"
  }));
  const noiseFixtures = [
    "English", "Apply", "Sign up", "See More", "Lamar sekarang",
    "Lompat ke konten utama", "Academics", "Pendaftaran"
  ].map((title, index) => ({
    ...base,
    id: `noise-fixture-${index}`,
    collector_id: `noise-fixture-${index}`,
    legacy_id: `noise-fixture-${index}`,
    position: title,
    title,
    company_name: `Navigation Fixture ${index}`,
    listing_url: `https://noise-fixture.invalid/jobs/${index}`,
    application_url: `https://noise-fixture.invalid/apply/${index}`,
    source_updated_at: "2099-01-01T00:00:00.000Z",
    published_at: "2099-01-01T00:00:00.000Z",
    last_seen_at: "2099-01-01T00:00:00.000Z"
  }));
  const sharedLandingUrl = "https://careers-fixture.invalid/careers";
  const samePageFixtures = [
    { title: "Network Engineer", position: "Network Engineer", id: "shared-page-role-a" },
    { title: "Network Analyst", position: "Network Analyst", id: "shared-page-role-b" }
  ].map((job, index) => ({
    ...base,
    ...job,
    collector_id: job.id,
    legacy_id: job.id,
    company_name: "Shared Page Company",
    listing_url: sharedLandingUrl,
    application_url: sharedLandingUrl,
    source_updated_at: "2099-01-01T00:00:00.000Z",
    published_at: "2099-01-01T00:00:00.000Z",
    last_seen_at: "2099-01-01T00:00:00.000Z"
  }));

  // A feed can repeat a role with inconsistent company names. Identical source,
  // location, pay, and role metadata should still collapse into one visible card.
  const crossCompanyTitle = "Cross-company duplicate fixture";
  const crossCompanyFixtures = ["Fixture Company A", "Fixture Company B"].map((company_name, index) => ({
    ...base,
    id: `cross-company-dedupe-${index}`,
    collector_id: `cross-company-dedupe-${index}`,
    legacy_id: `cross-company-dedupe-${index}`,
    title: crossCompanyTitle,
    position: crossCompanyTitle,
    company_name,
    source_name: "Dealls",
    source: "Dealls",
    listing_url: `https://cross-company-fixture.invalid/jobs/${index}`,
    application_url: `https://cross-company-fixture.invalid/apply/${index}`,
    city: "Tangerang",
    province: "Banten",
    location_label: "Tangerang, Banten",
    job_category: "Retail",
    employment_type: "intern",
    work_mode: "onsite",
    salary_text: "Rp2.500.000 – 3.000.000",
    salary_min_idr: 2500000,
    salary_max_idr: 3000000,
    source_updated_at: "2099-01-01T00:00:00.000Z",
    published_at: "2099-01-01T00:00:00.000Z",
    last_seen_at: "2099-01-01T00:00:00.000Z"
  }));
  const expandedJobs = [
    ...jobs.slice(0, baseIndex + 1), ...duplicates, ...samePageFixtures,
    ...crossCompanyFixtures, ...noiseFixtures, ...jobs.slice(baseIndex + 1)
  ];
  injectedRawRecordCount = expandedJobs.length;
  const modified = Array.isArray(payload)
    ? expandedJobs
    : { ...payload, jobs: expandedJobs, total: expandedJobs.length };
  await route.fulfill({
    status: response.status(),
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
    body: JSON.stringify(modified)
  });
  duplicateFixtureInjected = true;
});

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
  assert.equal(duplicateFixtureInjected, true, "Smoke test must inject duplicate job records");
  const dedupedMetricTotal = Number(total.replace(/[^0-9]/g, ""));
  assert.ok(dedupedMetricTotal < injectedRawRecordCount,
    "Repeated job records should be removed before totals and filters are calculated");
  const renderedSignatures = await page.locator("#jobList .job").evaluateAll(cards => {
    const normalize = value => {
      const text = String(value || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
      if (!text || /^(unknown|not known|not specified|not available|n\/?a|none|null|undefined|[-–—]|lokasi belum diketahui|bidang belum diketahui|tipe belum diketahui|sistem kerja tidak diketahui|pendidikan belum diketahui|tidak diketahui|belum diketahui|belum dicantumkan|tidak dicantumkan|gaji tidak dicantumkan|belum tersedia)$/.test(text)) return "";
      return text.replace(/&/g, " and ").replace(/[^a-z0-9]+/g, " ").trim();
    };
    return cards.map(card => {
      const get = selector => card.querySelector(selector)?.textContent || "";
      const title = normalize(get(".jt"));
      const company = normalize(get(".co"));
      if (!title || !company) return null;
      return [
        title, company, normalize(get(".meta .mi:first-child")),
        ...Array.from(card.querySelectorAll(".tags .tag")).map(tag => normalize(tag.textContent)).sort(),
        normalize(get(".sdv"))
      ].join("|");
    }).filter(Boolean);
  });
  assert.equal(new Set(renderedSignatures).size, renderedSignatures.length,
    "The visible job list must not show visually duplicated listings");
  const visibleTitles = await page.locator("#jobList .jt").allTextContents();
  assert.equal(visibleTitles.filter(title => title === crossCompanyTitle).length, 1,
    "Near-duplicate roles with the same source, location, and salary must render only once even if employer text changes");
  const rejectedNavigationTitles = new Set([
    "english", "apply", "sign up", "see more", "lamar sekarang",
    "lompat ke konten utama", "academics", "pendaftaran"
  ]);
  assert.equal(
    visibleTitles.some(title => rejectedNavigationTitles.has(
      title.normalize("NFKD").replace(/[\u0300-\u036f]/g, "")
        .toLowerCase().replace(/[^a-z0-9]+/g, " ").trim()
    )),
    false,
    "Navigation and CTA text must never appear as job titles"
  );
  assert.ok(visibleTitles.includes("Network Engineer"),
    "A valid role should remain visible even when its URL is a shared career landing page");
  assert.ok(visibleTitles.includes("Network Analyst"),
    "A second valid role on the same career landing URL must not be merged into the first");
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

  // Check that all local brand and SEO assets are served in the static bundle.
  for (const asset of ["logo.svg", "favicon.svg", "og-image.svg", "site.webmanifest", "robots.txt", "sitemap.xml"]) {
    const assetResponse = await page.request.get(new URL(asset, baseUrl).href);
    assert.equal(assetResponse.status(), 200, `The ${asset} asset should load successfully`);
  }
  const logoState = await page.locator('img[src^="logo.svg"]').first().evaluate(img => ({
    complete: img.complete,
    width: img.naturalWidth
  }));
  assert.ok(logoState.complete && logoState.width > 0,
    "The provided brand logo should load successfully");
  const smallLogoStyle = await page.locator(".top .logo").evaluate(el => ({
    width: parseFloat(getComputedStyle(el).width),
    objectFit: getComputedStyle(el.querySelector("img")).objectFit,
    transform: getComputedStyle(el.querySelector("img")).transform
  }));
  assert.ok(smallLogoStyle.width >= 44 && smallLogoStyle.objectFit === "contain",
    "The official AGA logo should be enlarged and fully visible without cropping");
  assert.equal(smallLogoStyle.transform, "none",
    "The logo artwork should not be stretched with a transform");
  const logoSvg = await (await page.request.get(new URL("logo.svg", baseUrl).href)).text();
  assert.match(logoSvg, /width="512" height="380" viewBox="12 55 360 275"/,
    "The logo SVG should crop excess black padding so the official AGA artwork is legible in the navbar");

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
