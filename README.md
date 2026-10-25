# INFO LOKER Indonesia — Website and Automated Collector

INFO LOKER is a static job-search website backed by a scheduled collector. It normalizes job metadata, keeps links to original listings, deduplicates records, records source health, and publishes data/jobs.json plus index.html.

## Current source status

### Active public RSS/API sources
- **Google News RSS** — searches public news-feed results for Indonesian vacancy and recruitment terms by province/city. The collector keeps metadata and outbound links; it does not crawl every linked article.
- **Jobicy public jobs API**
- **Remote OK public jobs API**

### Enabled site adapters
- **Kalibrr** — public listing adapter; robots.txt is checked before fetching.
- **Dealls** — public listing adapter; robots.txt is checked before fetching.
- **MagangHub** — remains configured for a respectful retry only when robots.txt permits the URL. Requests keep the identifiable INFO LOKER User-Agent, send Accept-Language starting with id-ID, and use 5–10 seconds between request starts. A 403/429 is recorded as blocked; the collector does not disguise itself as a human browser, reuse cookies, use proxies, or bypass the block.

An adapter being enabled is not a guarantee that its host will return records. Check data/run_status.json for the result of the latest run.


## Official company career-site expansion

The company-site collector uses three discovery layers:

1. **Curated targets (Layer A).** config/company_targets.yaml contains 400+ employer entries across banking/fintech, telecom, tech/startups, conglomerates, BUMN, manufacturing/energy, retail/FMCG, healthcare, property, logistics, education, and media. A target row needs id, name, domain, website, career_url, career_url_verified, category, and enabled; optional specific_parser chooses one of the selector overrides.
2. **Automatic career-path discovery (Layer B).** If the seed URL does not return an HTTP 200 page containing job/career keywords, the collector checks ordered public paths such as /careers, /career, /karir, /karier, /jobs, /lowongan, /loker, /join-us, /joinus, /work-with-us, /about/careers, /about-us/careers, /tentang-kami/karir, /en/careers, and /id/careers. HTTP redirects are followed one hop at a time, with robots checks on each host. A 404 is skipped.
3. **Robots and sitemap discovery (Layer C).** The collector reads /robots.txt, checks published Sitemap directives and /sitemap.xml, then finds URLs whose paths match career/job/karir/lowongan/vacancy/hiring patterns. Detail pages are fetched only if robots permits the URL, with a per-target sitemap limit to protect company sites.

career_url in the YAML is a first candidate, not a claim that every career route has been independently verified. The discovery workflow validates pages and records the resulting URL/status in data/company_career_registry.json. The initial curated list includes 400+ entries; duplicate domains are coalesced to one scan per run to avoid repeated hits.

### Company scraper implementation

- scrapers/company_sites/base_company.py — clear InfoLokerBot/1.0 User-Agent, Indonesian Accept-Language, HTTPS-only requests, per-host robots checks, safe redirect handling, rate limiting, and persisted blocklist.
- scrapers/company_sites/discovery.py — three-layer career URL and sitemap discovery.
- scrapers/company_sites/generic_parser.py — JSON-LD JobPosting, job/career card heuristics, data-attribute selectors, and URL/text-based fallback extraction.
- scrapers/company_sites/categories/ — one selector fallback module per configured company category (Bank & Fintech, Fintech, Telecom, Startup, Corporate, Healthcare, Properti, Manufaktur, BUMN, Retail, Transport & Logistics, Education, Media).
- scrapers/company_sites/specific/ — 20 selector overrides for Astra, Unilever, Telkom, Gojek, Tokopedia, Mandiri, BCA, BRI, BNI, Pertamina, PLN, Telkomsel, Traveloka, Bukalapak, Kalbe, Indofood, Shopee, Blibli, Freeport, and Mayora. Each also falls back to the generic parser.
- scripts/discover_company_careers.py — one-shot discovery/validation. Run without arguments to record career URLs; pass --scrape --force to also collect and publish results immediately.
- data/blocked_domains.json — persistent blocklist. An HTTP 403/429 adds the hostname and stops further requests to that hostname on future runs until a maintainer manually removes the entry after reviewing the site's policy.

Company-site runs use at most 8 workers, at least 2 seconds between request starts to the same hostname, and at most 50 requests per hostname per run. A blocked hostname is never retried automatically. One company failure is logged as blocked, no-career-page, or parse-error and cannot terminate the rest of the scan. Company results use the same normalized listing schema as the original collector, with source set to company:<official-domain>, source_group set to Company Sites, and category copied from the curated target. Records are deduplicated against the existing dataset.

The hourly scripts/run_all.py checks whether the six-hour company-site interval is due; normal job portal/feed/API collection remains hourly. The company run does not need a second hourly schedule. For a manual one-shot validation:

    python scripts/discover_company_careers.py

To collect and write the company listings immediately:

    python scripts/discover_company_careers.py --scrape --force

### Website source filter

The advanced “Sumber lowongan” filter now provides **Job Portal**, **Company Sites**, and the categories available in the company target data, including **BUMN**, **Startup**, **Corporate**, **Manufaktur**, **Fintech**, and **Healthcare**. Individual company listings retain their original apply/source link; the category filter does not replace direct source verification.

## Investigated sources that remain inactive

### Karir.com API candidate — prepared, not activated
A third-party reference mentions POST https://karir-ms-beta.karir.com/v2/search/opportunities with keyword/limit/offset parameters. This endpoint is **not documented in official Karir.com developer documentation** in the sources reviewed. Karir.com's terms state that automated data collection without permission is prohibited: https://karir.com/info/terms-conditions.

A guarded JSON adapter has been prepared to parse a documented response fixture, but it is disabled in config.yaml and the live endpoint was not probed. Do not enable it until Karir.com gives written permission or publishes terms/documentation expressly authorizing this use, and the request/response schema is confirmed.

### Tech in Asia Jobs — inactive, no Jobs RSS feed verified
The official robots.txt exposes a sitemap for job URLs but disallows paths matching */feed for the applicable crawler groups. The general feed is therefore not a safe substitute for a Jobs RSS feed. No official Jobs-specific RSS endpoint was verified, so the source remains disabled as requested. The existing adapter file is retained for a future officially permitted feed or other authorized integration.

Policy reference: https://www.techinasia.com/robots.txt

### Inactive — written permission required
The following sources remain disabled until written permission or an authorized feed/API is provided:
- **JobStreet** — https://id.jobstreet.com/id/terms
- **Indeed** — https://id.indeed.com/legal
- **Glints** — https://glints.com/about/terms and https://glints.com/robots.txt
- **LinkedIn Jobs** — https://www.linkedin.com/legal/user-agreement
- **Loker.id** — https://www.loker.id/disclaimer
- **Disnakerja** — https://disnakerja.id/blog/terms-of-service/

Karir.com is also inactive pending written permission/official API authorization, as described above. A page being public or indexed by a search engine does not by itself authorize automated extraction or republication.

## Adapter framework and normalized output

The repository retains adapter files for JobStreet, Indeed, Glints, Kalibrr, Karir.com, Dealls, LinkedIn, Loker.id, Disnakerja, Tech in Asia, and MagangHub. Permission-gated adapters stay in the source registry for future use if permission is obtained.

All adapters use the shared normalized fields: id, title, company, location, source, url, posted_at, salary, job_type, description_snippet, and scraped_at. Compatibility aliases remain for the current website and legacy collector.

The shared HTTP client uses HTTPS, an identifiable User-Agent, Indonesian Accept-Language, robots.txt checks, bounded timeouts, and per-source request pacing. MagangHub uses a 5–10 second minimum/maximum spacing. A 403 is not retried in the same request loop; it is recorded as blocked. The collector does not use stealth browsers, proxy rotation, login automation, private endpoint probing, or anti-bot bypass.

## Architecture

- scraper/main.py — original public RSS/API collector.
- scripts/run_all.py — runs the original collector and enabled authorized adapters, deduplicates records, saves a daily backup, writes data/run_status.json, and renders index.html.
- scrapers/base.py — common request pacing, robots checks, and shared HTML/job normalizer.
- scrapers/karir.py — prepared JSON API adapter gated behind explicit enablement and authorization.
- config.yaml — per-source activation, authorization, endpoint, and delay settings.
- config/source_registry.json — source inventory and policy status.
- data/jobs.json — published dataset.
- data/run_status.json — record counts, source statuses, errors, and timestamps.
- templates/index.html.j2 — source template for the static website.

## Automation

- .github/workflows/scrape.yml — hourly schedule and manual workflow_dispatch for the collector.
- .github/workflows/deploy.yml — validates and deploys GitHub Pages after a successful collection, and supports manual deployment.
- .github/workflows/healthcheck.yml — checks JSON health, minimum dataset size, and freshness; opens or updates a scraper-broken issue if checks fail.
- .github/workflows/tests.yml — Python tests, live Pages curl check, headless Playwright smoke test, and screenshot artifact.

Scheduled GitHub Actions jobs are best-effort and may be delayed. GitHub Actions must be enabled, and Pages must use GitHub Actions as its source.

## Local run

Python 3.12+:

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python scripts/run_all.py
    python scripts/healthcheck.py
    python3 -m http.server 8000

Open http://localhost:8000 and keep the server running while testing so the site can fetch data/jobs.json.

## Optional API/feed sources

- Jooble is skipped without JOOBLE_API_KEY.
- Adzuna is skipped without ADZUNA_APP_ID and ADZUNA_APP_KEY and country-support verification.
- Employer RSS/Atom feeds can be added to config/approved_feeds.json after confirming aggregation/republication is allowed.
- Remotive remains disabled pending a provider-approved redistribution arrangement.
- Himalayas remains disabled in the public GitHub dataset pipeline because the provider has attribution, expiry, and redistribution restrictions.

## Troubleshooting

- Read data/run_status.json for per-source ok, no_records, blocked, skipped, and error statuses.
- no_records means no supported records were parsed. It does not prove the source has no vacancies.
- blocked means HTTP 403/429. Do not bypass the provider's restriction; check the permission/feed path and retry only through an allowed route.
- skipped may mean robots.txt disallowed the URL or could not be verified.
- If the website smoke test fails, inspect the info-loker-playwright-screenshot artifact in the GitHub Actions run.
