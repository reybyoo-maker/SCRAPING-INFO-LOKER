# INFO LOKER Indonesia — scraper & daily data pipeline

This repository is the collection engine for a future Indonesian job-search website. It collects **public feed/API records**, normalizes them into one schema, deduplicates repeats, adds city/province filters and a transparent HOT / MEDIUM / LOW information-quality label, and publishes the dataset at data/jobs.json.

## What runs automatically

- GitHub Actions runs three times a day (approximately 07:15, 15:15 and 23:15 WIB) and can also be started manually from Actions → Daily Job Scraper → Run workflow.
- Each run rotates through location-specific Indonesian Google News RSS searches so the pipeline covers national, provincial and city queries over the day.
- Public job APIs are queried where available. Optional connectors for Jooble and Adzuna are only enabled when the corresponding API credentials are supplied and the provider supports Indonesia.
- Duplicate records are merged. The pipeline preserves first-seen/last-seen timestamps, marks old data as stale, extracts any salary/education/contact/social links available in the feed, and can OCR flyer images exposed by approved RSS feeds.
- data/jobs.json is the website-ready JSON dataset; data/run_status.json records counts, errors and source health.

## Data fields

The normalized record may contain: job title/position, employer (only when detected), original listing link, application link when explicitly available, source/publisher, source update date, last scraped time, city/province and location confidence, work arrangement, employment type, salary, minimum education, requirements/description excerpt, public contact phone, social links, walk-in interview details, flyer image URL/OCR text, application deadline, risk flags, quality score and HOT/MEDIUM/LOW label.

**Missing fields are left blank.** A headline or partial record can still be listed, but it is marked as low-information rather than inventing details. HOT/MEDIUM/LOW measures completeness, freshness and source signals; it is not a guarantee that an employer is legitimate. Users should verify a vacancy on its original source.

## Sources and responsible collection

Enabled by default:
- Google News RSS searches for Indonesian vacancy/recruitment terms by province and major city. Items link out to the source; the collector does not crawl every linked website.
- Public remote-job APIs: Jobicy, Remote OK and Himalayas. Remote records are included only when the API indicates Indonesia, APAC/worldwide availability, or no restrictions that block Indonesia. Remotive is left disabled because its public API terms restrict redistribution to third-party job boards; enable it only after obtaining explicit permission.

You can add a source's official RSS feed to config/approved_feeds.json. Flyer image OCR is bounded per run and runs only for images exposed by those feeds. Do not add a feed or crawler unless its terms, robots instructions, license and permission allow republication/aggregation.

**Do not enable direct scraping of Jobstreet, Karir.com, Indeed, LinkedIn, Glints, Kalibrr, Dealls, KitaLulus, Instagram, Facebook or TikTok without an authorized API/feed or written permission.** Some of these services restrict automated collection. For example, Jobstreet's terms prohibit screen scraping and automated data gathering without prior written consent: https://id.jobstreet.com/id/terms. Prefer an official API, partner feed or employer-provided RSS. Store source links and only the minimum metadata needed; don't copy full copyrighted job descriptions or mirror flyer files.

## First-time setup

1. Open Settings → Actions → General in this repository and ensure Actions are enabled.
2. Check Settings → Actions → General → Workflow permissions. The workflow declares contents: write so it can commit dataset updates.
3. On the Actions tab, run Daily Job Scraper once manually to test the workflow.
4. After a successful run, inspect data/run_status.json and data/jobs.json.
5. Add authorized feeds to config/approved_feeds.json and optional API keys under Settings → Secrets and variables → Actions:
   - JOOBLE_API_KEY
   - ADZUNA_APP_ID, ADZUNA_APP_KEY (only if Adzuna confirms Indonesia coverage for your account)
   - ENABLE_FLYER_OCR=1 to enable OCR for flyer images in approved RSS items.
   - ENABLE_HIMALAYAS_API=1 only after owned-site/backend integration that follows the provider's attribution and no-redistribution terms; leave it at 0 for the public GitHub feed.
6. Keep this repository public only if you intend the dataset and source metadata to be public. A public repository's scheduled workflow may be disabled by GitHub after 60 days without repository activity, so check the Actions tab periodically.

## Website integration

The website can fetch data/jobs.json from this repository's raw URL or consume it through a small API/Cloudflare Worker. For a production site, move the persistent data to a database (e.g. Cloudflare D1) and serve it through your own API; do not rely on a large Git history as a permanent database. Recommended user-facing filters: province, city, category/position, minimum education, salary disclosed/not disclosed, work mode, job type, walk-in interview, freshness and quality label.

## Local run

Python 3.12+:

    pip install -r requirements.txt
    python -m scraper.main

The collector is deliberately polite and bounded: timeouts, retries, limited feed batches, source-specific parsing and capped flyer OCR. A feed can be temporarily unavailable without stopping the whole run.
