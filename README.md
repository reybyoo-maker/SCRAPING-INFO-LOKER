# INFO LOKER Indonesia — Website and Automated Collector

INFO LOKER is a static job-search website backed by a collector. The system normalizes listings, retains original source links, deduplicates records, maintains run status, and publishes `data/jobs.json` plus `index.html`.

## Currently configured sources

### Three existing RSS/API sources
- **Google News RSS** — searches public news-feed results for Indonesian vacancy/recruitment terms by province and city. It stores result metadata and outbound links; it does not crawl every linked article.
- **Jobicy public API**
- **Remote OK public API**

### Four additional HTML adapters enabled
- **Kalibrr**
- **Dealls**
- **Tech in Asia Jobs**
- **Maganghub**

The HTML adapters use ordinary HTTPS requests only. Before requesting a search page, each adapter reads and checks its source `robots.txt`; if robots rules cannot be verified or disallow the URL, that source is skipped and the reason is logged. A 403/429 response is logged as `blocked`; the adapter remains configured and can retry on a later scheduled run. A zero-record parse is logged as `no_records` so selectors/search URLs can be updated without permanently disabling the adapter.

### Sources that require written permission or an authorized feed before direct scraping
- **JobStreet** — its published terms prohibit automated data gathering/scraping without prior written consent.
- **Indeed** — its current terms require express written permission for automated scraper/data extraction and limit crawling to the conditions set in its robots.txt; crawling permission is not automatically permission to extract/re-publish job data.
- **Glints** — its terms prohibit screen scraping/data mining to reproduce website information without prior written consent; its robots.txt also disallows the configured jobs-explore URL.
- **Karir.com** — its terms prohibit automated data collection without permission.
- **Loker.id** — its terms restrict reproducing/copying/distributing website content without written permission.
- **Disnakerja** — its terms restrict copying/reproducing/distributing website content without written consent.
- **LinkedIn Jobs** — disabled by default; use authorized API/partner access only.

Official source policy links reviewed for this configuration:
- JobStreet: https://id.jobstreet.com/id/terms
- Indeed: https://id.indeed.com/legal
- Glints: https://glints.com/about/terms and https://glints.com/robots.txt
- Karir.com: https://karir.com/info/terms-conditions
- Loker.id: https://www.loker.id/disclaimer
- Disnakerja: https://disnakerja.id/blog/terms-of-service/
- Tech in Asia robots policy/sitemap: https://www.techinasia.com/robots.txt
- Dealls: https://dealls.com/terms-and-condition
- MagangHub official information: https://maganghub.kemnaker.go.id/magang-nasional/faq

A page being publicly visible or indexed by a search engine is not by itself a grant to scrape and republish all of its contents. This configuration uses the documented site policies and machine-readable robots rules as gates. Enable a permission-gated site only after its owner grants access or provides an approved feed.

## Adapter framework and normalized output

The repository contains eleven separate HTML adapter files under `scrapers/`:
`jobstreet.py`, `indeed.py`, `glints.py`, `kalibrr.py`, `karir.py`, `dealls.py`, `linkedin.py`, `lokerid.py`, `disnakerja.py`, `techinasia.py`, and `maganghub.py`.

All inherit from `scrapers/base.py` and normalize to these fields:
`id`, `title`, `company`, `location`, `source`, `url`, `posted_at`, `salary`, `job_type`, `description_snippet`, and `scraped_at`.
Compatibility aliases are preserved for the current website and existing collector.

Each request has a 30-second maximum timeout, up to three attempts for transient failures, a descriptive User-Agent, and a global 2–5 second spacing between HTTP request starts. Each run uses at most four workers. A source failure does not cancel other sources. The adapter does not use stealth browsers, proxy rotation, login automation, private endpoint probing, or anti-bot bypass.

## Architecture

- `scraper/main.py`: original public RSS/API collector.
- `scripts/run_all.py`: calls the original collector, runs enabled adapters, normalizes/deduplicates records, saves one daily backup, writes `data/run_status.json`, and renders the Jinja template into `index.html`.
- `scrapers/base.py`: common request, robots, JSON-LD/HTML parsing, and schema normalizer.
- `config.yaml`: per-source on/off and authorization flags.
- `config/source_registry.json`: source inventory/status notes.
- `data/jobs.json`: published job dataset.
- `data/run_status.json`: counts, errors, blocked sources, and timestamps.
- `templates/index.html.j2`: source template for the current static website.

## Automation

- `.github/workflows/scrape.yml`: hourly cron `0 * * * *` and manual `workflow_dispatch`; installs pinned dependencies and runs `python scripts/run_all.py`.
- `.github/workflows/deploy.yml`: validates HTML/JavaScript/JSON, builds the static artifact, deploys GitHub Pages after a successful scraping run, and supports manual deployment.
- `.github/workflows/healthcheck.yml`: checks every six hours and on demand; checks valid JSON, at least 100 job records, and a newest `scraped_at` under three hours old. On failure it opens or updates a `scraper-broken` issue.
- `.github/workflows/tests.yml`: runs Python tests, checks the live Pages URL with `curl -sSf`, runs a headless Playwright browser smoke test, and uploads a screenshot artifact for seven days.

GitHub Actions scheduled jobs are best-effort and can be delayed. The repository's Actions feature must be enabled and Pages must use GitHub Actions as its source.

## Local run

Python 3.12+:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/run_all.py
python scripts/healthcheck.py
python3 -m http.server 8000
```

Open `http://localhost:8000`; keep the server running while testing so the website can fetch `data/jobs.json`.

## Optional API/feed sources

- Jooble is skipped without `JOOBLE_API_KEY`.
- Adzuna is skipped without `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` and country support verification.
- Employer RSS/Atom feeds can be added to `config/approved_feeds.json` after confirming aggregation/republication is allowed.
- Remotive remains disabled pending a provider-approved redistribution arrangement.
- Himalayas remains disabled in the public GitHub dataset pipeline because the provider has attribution, expiry, and redistribution restrictions.

## Troubleshooting

- Read `data/run_status.json` for per-source `ok`, `no_records`, `blocked`, `skipped`, and `error` statuses.
- A `no_records` status means parsing found no supported JSON-LD or HTML cards. It does not disable the source; review its search URL and selectors.
- A `blocked` status means HTTP 403/429. The source remains enabled and can be retried on the next scheduled run; do not bypass the provider's restrictions.
- A `skipped` status may mean robots.txt disallowed the URL or could not be verified.
- If the website test fails, inspect the uploaded `info-loker-playwright-screenshot` artifact and the Actions logs.
